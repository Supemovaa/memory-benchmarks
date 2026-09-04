数据分析完成。以下是完整报告。

## 一、整体表现

`predicted_locomo-2`：1540 题（10 段对话，4 类），每题在 6 个 retrieval cutoff 上各生成+评判一次。

| cutoff  | acc        | 边际增益 |
| ------- | ---------- | -------- |
| top_10  | 80.32%     | —        |
| top_20  | 85.26%     | +4.94    |
| top_50  | 88.51%     | +3.25    |
| top_60  | 88.90%     | +0.39    |
| top_100 | 90.26%     | +1.36    |
| top_200 | **91.82%** | +1.56    |

分类别（acc@10 → acc@200）：

| 类别 | n | @10 | @200 |
|---|---|---|---|
| multi-hop | 282 | 0.809 | 0.954 |
| temporal | 321 | 0.841 | 0.935 |
| single-hop | 841 | 0.809 | 0.925 |
| **open-domain** | 96 | **0.615** | **0.698** |

关键结构性事实：**75 题（4.9%）在所有 6 个 cutoff 全错**，无论给多少 memory 都答不对；**202 题靠加深度被救回**；**25 题反被深度带偏**（噪声干扰）。90 题（5.8%）判定在 cutoff 间反复翻转 ≥2 次，说明这部分是抽样噪声而非能力边界。

---

## 二、错误归因：检索 vs 生成

用 gold answer 的内容词在检索上下文中的覆盖率归因：

|                                | wrong@10 (303) | wrong@200 (126) |
| ------------------------------ | -------------- | --------------- |
| 上下文里没有答案 → 检索失败    | **67.3%**      | 15.1%           |
| 上下文里有答案 → 生成/推理失败 | 14.5%          | **57.1%**       |
| 部分覆盖                       | 18.2%          | 27.8%           |

**错误的性质随深度反转**：浅检索时瓶颈在 recall，深检索时瓶颈在从长上下文中挑对答案。

gold evidence 首次出现的排名分布：
- rank 1–10: 58.5%
- rank 11–20: 5.1% 
- 21–50: 4.8% 
- 51–100: 3.1% 
- 101–200: 2.7%
- 200 条内始终未覆盖: **25.8%**

条件正确率极其分化：
- gold 在 top10 内（n=901）：acc@10 = **0.942**，acc@200 = 0.967
- gold 在 top10 外或缺失（n=639）：acc@10 = **0.607**，acc@200 = 0.850

即**只要检索命中，答题环节几乎不出错（94%）**；整体 80% 的 acc@10 被 41.5% 的 top-10 miss rate 拖住。top-1 相似度也有强预测力：score<0.7 时 acc@10=0.74，score≥0.8 时 acc@10=0.89。

---

## 三、七类错误模式（按可修复性排序）

### 1. 记忆抽取有损（提取层，非检索层）— 最根本`chunk_size=1`（`benchmarks/locomo/run.py:88`），逐轮抽取，导致**答案所需的限定细节在写入时就被抹掉**。原文→memory 的对比：

| 原文 | 存下来的 memory | 问题 | GT | 模型答 |
|---|---|---|---|---|
| "Here's one I did last week. It's inspired by the sunsets" + caption `painting of a sunset with a pink sky` | "Melanie created **a landscape painting of a sunset with a pink sky** around **October 6**" | 10/13 展示的画 | pink sky sunset | "abstract painting, blue background" || "dairy-free vanilla with strawberry filling and **coconut cream frosting**" | "Joanna made a cake with **white frosting**" | 什么 frosting | coconut cream | white frosting |
| "**Eagles** have always mesmerized me" | 池中 200 条**无一条含 eagle** | 哪种鸟 | Eagles | "birds" |
| "makes me feel **connected to my body**"（Deborah 说的） | 只留下 "connected to nature" | 运动让她感觉如何 | connected to her body | calm/relaxed |

量化：37 题的 gold 词出现在原始对话但在 200 条 memory 池中完全消失，其中 **21.6% 判错**（对照组"gold 在池中"只有 5.6% 错）。这类是**上限损失**——加检索深度、换 prompt 都救不回来。

`chunk_size=1` 还造成第二个伤害：单轮独立抽取导致 memory 严重碎片化+重复。conv3 有 29 条含 "coconut" 的记忆挤在 top-70，全是同一话题的近似重述，把真正的答案挤出窗口。

### 2. Open-domain 的评测协议错配 — 占比最高的类别性失败（30% 错）
29 个 open-domain 错误里绝大多数不是"答错"，而是**gold 是一个未在对话中明说的单一主观推断，judge 又要求实体级匹配**：

- "What might John's degree be in?" GT=`Political science` / 答=`Mechanical Engineering`（对话只说他在机械工程公司当助理经理）
- "What underlying condition might Joanna have based on her allergies?" GT=`asthma` / 答=`Lactose Intolerance`（对话反复提她乳糖不耐）- "Which US state do Audrey and Andrew live in?" GT=`Minnesota` / 答="未指明"
- "What might Melanie say Caroline's traits are?" GT=`Thoughtful, authentic, driven` / 答=`supportive, reliable, creative`- "Did John and James study together?" GT=`Yes` / 答=`No`（模型区分了"一起学编程"和"一起上学"）

这类的 acc 从 top_10 到 top_200 只涨 8pt（0.615→0.698），**加深度无效**，因为信息不在记忆里而在标注者的先验里。gold 含 "because/since/likely" 的 25 题 acc=0.80，也印证是开放推断题。**建议把 open-domain 单列报告，或改用软性 judge**，否则它会持续吃掉 ~2pt 总分且不可优化。

### 3. 计数/时长题系统性少数 — 明确可优化
`how many / how long / how often`：n=71，acc@10=**0.620**，acc@200=0.831（非计数题 0.922）。方向高度偏斜：**少数 8 : 多数 3**（全部数值型 wrong@200 是 under 18 : over 5）。

原因是同一事件被拆成多条 memory，模型去重时过度合并；或多轮事件散落在 rank 100+ 未被扫全。例：`How many video game tournaments has Nate participated in?` GT=9，模型枚举到 3 条就被截断。

### 4. 输出截断吞掉最终答案 — 立即可修73 次生成（49 个不同问题）泄漏了 Step 1–7 的思维链且**没有产出 `ANSWER:` 段**。长度 p50 = 14481 字符，最大 17173，**61/73 在句子中间断掉** → 撞上 `max_tokens=4096` 默认值。`run.py:467` 的 `if "ANSWER:" in ...` 找不到锚点，就把整段 CoT 当答案交给 judge，必然判错。

代价：wrong@200 中 9 例（+0.58pt），全部 cutoff 累计更多。答案长度与正确率也单调负相关（<30 字符 acc=0.934，>400 字符 acc=0.806）。

**修法**：把 `max_tokens` 提到 8192–16384，并在 `ANSWER:` 缺失时回退取最后一段而非全文。

### 5. 违反 prompt 的弃答 — prompt 已禁止但仍发生
Step 7 明确写了 `NEVER say "not specified"`，实际仍有 51 次（top_10）/17 次（top_200）弃答，其中 **86%–94% 判错**（因为 LoCoMo 的 gold 从不为空）。贡献 wrong@200 的 11 例（+0.71pt）。深度越大弃答越少，说明主因是浅层确实检索不到。

### 6. 答案抽象层级过高（hypernym）`birds`↔`Eagles`、`a colleague`↔`Rob`、`her home country`↔`Sweden`、`A book that reminds her to pursue her dreams`↔`"Becoming Nicole"`。检索到的 memory 本身就已被泛化（见第 1 类），模型只能复述泛化版本。仅 4 例是纯粹的"模型有具体信息却给了泛称"，多数根因仍在抽取层。

### 7. 时间实体消歧 — 已大幅缓解，剩余为混淆题
temporal acc@200=0.935，257 道 "when" 题 acc=0.946，其中仅 2 例年份错。**relative gold（"the Sunday before…"）0.936 vs absolute gold 0.934，无差异** —— 说明 prompt 的 Step 5 时间锚定已生效，这不再是主要错误源。

剩余 21 例是"同类事件多次发生"的选错：
- `When did John have his first firefighter call-out?` GT=7/2，memory 说 7/30（**记忆本身与 gold 矛盾**，抽取时把复述日期当事件日期）
- `When did Evan have a drunken night?` GT=2023-01-09，答 2024-01-09（跨年同日）- `When did John go camping with Max?` GT=summer 2022，答 summer 2023（记忆只带了会话日期）

共性：**event date 与 utterance date 未分离存储**。第 3 例这类，memory 里只有 `created_at`，事件真实时间已丢失。

---

## 四、优先级建议

按"每 pt 收益 / 实现成本"排序：

1. **`max_tokens` → 8192+ 并修 `ANSWER:` 回退**（`run.py:466`）：+0.6pt，10 分钟。
2. **`CHUNK_SIZE` 1 → 4~6**（`run.py:88`）：让抽取器看到相邻上下文，直接攻击第 1 类（上限损失）+ 第 3 类（碎片化去重）。这是唯一能动 25.8% "gold 从不出现"的杠杆。需重跑 ingestion。3. **抽取时强制保留修饰语与显式事件日期**：把 `blip_caption` 的具体属性（pink sky / coconut cream / eagles）与"事件时间 ≠ 说话时间"写进 memory schema。4. **计数题走独立路径**：先按实体+谓词做 memory 聚合与显式去重表，再计数；针对 under-count 偏斜放宽合并阈值。
5. **open-domain 单列或换 judge**：当前 96 题拉低总分约 2pt 且无优化空间，混在总分里会误导后续迭代方向。
6. **检索用 top_50 而非 top_10 作为默认工作点**：+8.2pt，边际增益在 top_60 后急剧衰减（+0.39pt），50 是明显的性价比拐点。

需要我落手实施其中哪几项？第 1 项可以立刻改；第 2 项要重跑 ingestion，建议先在单条对话上验证抽取质量。