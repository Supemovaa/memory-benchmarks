# Mem0 memory 添加机制与大量重复原因分析

本文整理 LOCOMO 评测中发现的 memory 重复问题，依据当前 benchmark 代码、运行中的 Mem0 OSS 服务代码以及 `memories_qwen25_7b_instruct` collection 的实际数据。

## 结论摘要

重复的根因不是 Qdrant 自己“误复制”了 point，而是当前 Mem0 V3 的去重范围非常有限：

```text
LLM 抽取范围：当前 chunk + 最近 10 条消息 + 当前 chunk 的 Existing Memories
去重范围：当前 chunk 语义检索得到的 top-10 Existing Memories
```

因此，LLM 可以从最近消息中重新生成一个旧事实，但随后用于 hash 去重的 top-10 检索结果中可能没有该旧事实。此时同样文本会被分配新的随机 UUID 并再次写入 Qdrant。

当前 collection 中已经观察到：

- 1666 个 point；
- 1518 个 unique hash；
- 91 个重复 hash group，共多出 148 个重复 point；
- 事实 `Caroline joined a new LGBTQ activist group called 'Connected LGBTQ Activists' last Tuesday` 出现 9 个不同 UUID，文本和 MD5 hash 完全相同。

## 1. 一个 chunk 与 memory 数量的关系

`benchmarks/locomo/run.py` 当前设置 `CHUNK_SIZE = 1`，所以一个 chunk 只有一条对话消息；这不代表一个 chunk 只能产生一条 memory。

每个 chunk 调用一次 `mem0.add()`，一次调用由 LLM 返回：

```json
{"memory": [
  {"text": "..."},
  {"text": "..."}
]}
```

数组可以为空、包含一条或包含多条 memory。Mem0 会对数组中的所有文本批量 embedding，然后逐条生成记录并写入。因此“chunk 数”和“memory 数”不是一对一关系。

## 2. 当前 memory 添加流程

### 2.1 Benchmark runner

LOCOMO ingestion 对每个 conversation 按 session 和 chunk 顺序处理：

```python
for chunk_idx, messages in enumerate(chunks):
    response = await mem0.add(messages, user_id, timestamp=session_epoch)
```

当前这段 runner 逻辑本身是串行的：下一个 chunk 要等上一个 `add()` 返回后才提交。runner 不做客户端去重，只负责 checkpoint 和保存进度。

### 2.2 Mem0 客户端

`benchmarks/common/mem0_client.py` 的 OSS 路径直接向 `/memories` POST 当前消息。客户端不计算 hash，也不查询已有 memory 做去重。

客户端默认允许失败重试（最多 5 次）。只有请求异常或服务端 5xx 时才重试；普通成功响应不会再次提交。当前客户端的并发 limiter 基本不构成限制。服务端容器则以 `uvicorn --workers 50` 启动，存在多个独立 worker 实例；如果有并发客户端、超时后的重试或其他请求来源，服务端可能出现竞态。这是重复放大的潜在因素，但不能把它当作当前 9 个重复事实的唯一已证实原因。

### 2.3 Mem0 服务端 V3 `add()`

当前运行的 `mem0/memory/main.py` 大致分为以下阶段。

#### 阶段 A：读取最近上下文

```python
last_messages = self.db.get_last_messages(session_scope, limit=10)
parsed_messages = parse_messages(messages)
```

SQLite 只保存每个 scope 最近 10 条消息。当前 chunk 在本次抽取完成后才保存，所以后续调用会把它作为 `Last k Messages` 看到。

#### 阶段 B：按当前 chunk 检索 Existing Memories

```python
query_embedding = self.embedding_model.embed(parsed_messages, "search")
existing_results = self.vector_store.search(
    query=parsed_messages,
    vectors=query_embedding,
    top_k=10,
    filters=search_filters,
)
```

这里的查询是当前 chunk 的原始消息，不是 LLM 即将输出的 memory；结果固定只取语义相似度最高的 10 条，并按 `user_id` 等 scope 过滤。

#### 阶段 C：把多种上下文交给 LLM

LLM 的 prompt 同时包含：

1. `New Messages`：当前 chunk；
2. `Last k Messages`：最近 10 条历史消息；
3. `Existing Memories`：阶段 B 得到的 top-10 memory。

system prompt 要求 Existing Memories 只用于去重和 linking、不要从中抽取新 memory，但这只是自然语言约束，不是程序级隔离。Qwen 仍可能复述 Last k 或 Existing Memories 中的事实。

#### 阶段 D：一个响应内批量处理所有抽取结果

```python
mem_texts = [m.get("text", "") for m in extracted_memories]
mem_embeddings_list = self.embedding_model.embed_batch(mem_texts, "add")
```

这一步允许一个 chunk 生成多条 memory。

#### 阶段 E：局部精确 hash 去重

Mem0 对每条文本计算：

```python
mem_hash = hashlib.md5(text.encode()).hexdigest()
```

然后只检查两组 hash：

```python
existing_hashes = {mem.payload["hash"] for mem in existing_results}
seen_hashes = set()  # 当前 LLM 响应内部
```

判断逻辑相当于：

```text
如果 hash 在当前 chunk 的 top-10 中，跳过
如果 hash 已在本次响应中出现，跳过
否则写入
```

这不是整个 collection 的全量 hash 去重，也不是语义去重。MD5 只识别完全相同的字节串；措辞稍有变化就会得到不同 hash。

#### 阶段 F：随机 UUID 写入 Qdrant

每条未被跳过的 memory 使用 `uuid.uuid4()` 生成新的 point ID，再插入 Qdrant。Qdrant 的 point ID 不同，就会接受为不同 point；payload 中相同的 `hash` 并不会自动形成唯一约束。

## 3. 为什么“重复抽取”和“检索不到旧 memory”可以同时发生

这两个动作的输入集合不同。

以 D10 会话为例：

1. D10:5 明确出现组织名 `Connected LGBTQ Activists`，此时模型可能首次生成完整事实 m。
2. 到 D10:6、D10:7 等后续 chunk 时，当前消息可能只是赞扬组织、询问活动或讨论 pride parade；这些消息的向量与 m 的相似度逐渐降低。
3. 但 D10:5 仍可能位于后续调用的 `Last k Messages` 滑动窗口内。Qwen 的 prompt 仍能看到这段文字，于是可能再次输出 m。
4. Mem0 的去重检查却只使用当前消息的 top-10 向量结果。m 如果排在第 11 名以后，就不在 `existing_hashes` 中，重复写入。

对当前 collection 做回放查询可以看到这种趋势（这些 rank 是在已污染 collection 上的事后查询，只用于说明语义窗口变化，不等同于当时插入瞬间的精确 rank）：

| 当前消息 | 完整事实 m 的示例 rank |
|---|---:|
| D10:5（包含组织名） | 约 7 |
| D10:6（组织相关追问） | 约 159 |
| D10:7（pride parade） | 约 334 |
| D10:8（转到 beach） | 约 754 |

所以“后面的 chunk 能抽取 m”不能推出“m 必然在后面的 chunk 的 top-10 中”。它可能是：

- 从 `Last k Messages` 复述出来的；
- 从 top-10 Existing Memories 中复述出来的；
- 当前消息与历史内容有弱语义关联，但旧 m 仍排在 top-10 之外；
- 对当前消息独立抽取出的同一事实，但向量排序仍未把旧 point 排入 top-10。

只有在旧 point 进入阶段 B 的 top-10 时，阶段 E 的精确 hash 检查才有机会拦截它。

## 4. 为什么会形成“大量”重复

### 4.1 Prompt 要求穷举，增加了重复输出概率

当前 extraction prompt 要求“extract ALL memorable information”，并强调不要漏掉中间和末尾主题。对 Qwen 这类模型来说，这会提高每次响应的抽取数量；当 Last k 包含旧事实时，也增加重复复述的机会。

### 4.2 Last k 是可见上下文，但不是全局去重表

最近 10 条消息用于解析代词和上下文，本意不是作为新的事实来源。但程序把它原样放入 LLM prompt，模型可能把其中已经处理过的事实再次输出。

### 4.3 top-10 去重窗口过窄

新消息的语义主题一变，旧 memory 很容易掉出 top-10。collection 越大、主题越多，固定 top-10 越不能代表“所有可能重复的历史 memory”。

### 4.4 去重是精确字符串匹配，不是语义匹配

下面两条文本的事实可能相同，但 MD5 不同，因此当前 hash 逻辑不会认为它们重复：

```text
Caroline joined a new LGBTQ activist group last Tuesday.
Caroline recently became part of the Connected LGBTQ Activists organization.
```

这会造成两类重复：完全相同文本的重复 point，以及不同措辞但事实相同的近重复 point。

### 4.5 Qdrant 没有按 payload hash 自动唯一化

Mem0 使用随机 UUID 作为 point ID。只要 UUID 不同，Qdrant 就会保存多个相同 payload/hash 的 point。当前 search 客户端和 LOCOMO answer prompt 也没有二次去重：搜索结果按 score 排序后直接返回，cutoff 直接切片，重复 memory 可能再次进入答案上下文。

### 4.6 并发和重试是额外放大器

当前 LOCOMO ingestion 循环是串行的，因此不能仅凭 runner 代码断言“同一个 chunk 被并发提交”。不过 50 个 Uvicorn worker、多个客户端、请求超时重试等情况可能使多个 `add()` 同时读取相同旧状态，再各自通过局部 hash 检查并写入。即使没有这种竞态，前述“LLM 上下文范围大于去重范围”也足以产生重复。

## 5. 三个可行的潜在解决方案

### 方案一：使用 scope+hash 生成确定性 point ID（推荐用于完全相同文本）

将 `(user_id, normalized_text_hash)` 映射为稳定 UUID，而不是每次使用 `uuid4()`；写入时使用 Qdrant 的幂等 upsert，或使用存储层的 create-if-absent 语义。

```text
point_id = UUID5(namespace, user_id + ":" + md5(normalized_text))
```

优点：不需要先检索 top-10；同一个 scope 下相同文本天然指向同一个 point，对并发和重试更稳健。实施时需要定义文本规范化规则，并清理现有随机 UUID 重复 point；如果使用 upsert，还要保留最早的 `created_at` 和正确的历史记录，避免重复写入覆盖业务元数据。

### 方案二：建立全局 exact-hash 索引，在持久化前做原子检查

保留当前 top-10 检索用于 prompt 和 linking，但把“是否已经存在同一文本”改为独立的全量检查：按 `user_id + hash` 在 Qdrant payload 索引或 SQLite/专用 KV 表中查询。检查与插入必须由同一锁、事务或唯一约束保护，不能只是两个无锁请求，否则 50 worker 仍可能发生 check-then-insert 竞态。

优点：改动可以集中在 Mem0 服务端，能够兼容现有随机 UUID，并且保留当前 prompt 的语义检索行为。缺点是需要额外索引/存储访问，并要对现有重复 group 选择 canonical point 后做一次清理。

### 方案三：收紧抽取来源，并扩大/增强候选 memory 的语义去重

分两部分实施：

1. 在 extraction prompt 和代码层面明确 `New Messages` 是唯一事实来源；`Last k Messages` 仅作为代词解析上下文，或先标记为不可抽取的引用内容，避免模型把旧事实当成新事实输出。
2. 对 LLM 输出的候选 memory，使用更大的候选集（例如 top-100/全局 hash 查询）和 embedding/BM25 相似度阈值做二次语义去重；完全相同文本仍优先使用方案一或二的 exact hash 保护。

优点：不仅减少完全相同文本，也能抑制“同一事实不同措辞”的近重复。缺点是阈值需要用 LOCOMO 数据调参，过于激进会误删真正的更新事件；扩大检索还会增加 embedding、延迟和上下文成本。

## 建议的落地顺序

先用方案一或方案二消除 exact duplicate 的数据膨胀，再用方案三处理模型重复抽取和 paraphrase duplicate。answer/search 阶段仍可以增加按 hash 的展示去重，但那只能改善回答上下文，不能修复已经写入 collection 的重复 point。
