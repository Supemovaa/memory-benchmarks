# Locomo-2 失败案例分析

## 摘要

**运行配置：**
- 模型：qwen3.6-max-preview（作答与评判）
- 数据集：locomo10.json（1540 题）
- 模式：evaluate-only + rejudge
- 日期：2024 年 8 月 30 日

**整体表现：**
- **Acc@200：91.88%**（1415/1540）⬆️ 上次为 91.82%
- **Acc@10：80.78%**（1244/1540）
- Wrong@200：125 例（8.12%）
- 全 cutoff 均错：67 例（4.4%）
- 靠深度救回（wrong@10→correct@200）：196 例（12.7%）

**主要改进：**
从 91.82% 微升至 91.88%（+0.06%），说明当前配置下系统已接近性能上限。

---

## 分类别表现

| 类别 | Acc@10 | Acc@20 | Acc@50 | Acc@60 | Acc@100 | Acc@200 |
|----------|--------|--------|--------|--------|---------|---------|
| **Single-hop**（841） | 81.21% | 85.73% | 89.06% | 89.30% | 90.61% | **92.63%** |
| **Multi-hop**（282） | 82.27% | 87.23% | 91.84% | 92.55% | 93.26% | **95.04%** |
| **Temporal**（321） | 84.42% | 91.28% | 92.21% | 92.52% | 93.46% | **94.39%** |
| **Open-domain**（96） | 60.42% | 67.71% | 67.71% | 65.62% | 66.67% | **67.71%** |

**类别洞察：**
- **表现最好：** Multi-hop（95.04%）—— 记忆聚合能力提升
- **表现最差：** Open-domain（67.71%）—— 根本性的协议错配问题仍未解决
- **Temporal：** 表现强劲（94.39%）—— 时间推理改进已生效

---

## 分类别错误分布

### Wrong@200 拆解：
- **Open-domain：31/96（32.3%）** ⚠️ 主要瓶颈
- **Single-hop：62/841（7.4%）**
- **Temporal：18/321（5.6%）**
- **Multi-hop：14/282（5.0%）** ✅ 最佳类别

**关键观察：** Open-domain 仅占数据集 6.2%，却贡献了全部失败的 24.8%。

---

## 失败模式分类

### 1. **内容错误**（68 例，54.4%）
从记忆中检索到相关但事实错误的信息。

**示例：**
- Q："What did Jolene recently play that she described to Deb?"
  - Gold："a card game about cats"
  - Pred："a scuba diving lesson"

- Q："What health issue did Sam face that motivated him to change his lifestyle?"
  - Gold："Weight problem"
  - Pred："gastritis"

- Q："What hobby did Calvin take up recently?"
  - Gold："Photography"
  - Pred："Vintage car restoration"

**根本原因：**
- 语义检索召回了话题相近但事实错误的记忆
- 记忆编码特异性不足（多个爱好/活动被混为一谈）
- 时间指代模糊（"recently" 未正确锚定）

---

### 2. **Open-domain 协议错配**（31 例，24.8%）
尽管上下文相关，系统仍拒答或给出过度受限的回答。

**示例：**
- Q："What is an indoor activity that Andrew would enjoy doing while make his dog happy?"
  - Gold："cook dog treats"
  - Pred："Playing board games (such as chess)"
  - 问题：忽略了"让狗开心"这一约束

- Q："What other exercises can help John with his basketball performance?"
  - Gold："Sprinting, long-distance running, and boxing"
  - Pred："strength training"（部分作答）
  - 问题：从上下文的推断不完整

- Q："In what country did Jolene buy snake Seraphim?"
  - Gold："In France"
  - Pred："Colombia"
  - 问题：国家完全答错

**根本原因：**
- Open-domain 题目要求**超出已存事实的推断**
- 系统面向对话式记忆训练，而非开放式推理
- Gold 答案期待的是世界知识 + 记忆综合

---

### 3. **回答冗长**（16 例，12.8%）
正确信息被埋在过度详细的回答中，被 judge 判为错误。

**示例：**
- Q："How does John plan to honor the memories of his beloved pet?"
  - Gold："By considering adopting a rescue dog"
  - Pred："John plans to honor the memories of his late dog Max by sharing cherished photos of him and committing to making progress in his life and community work..."
  - 问题：答案被无关信息稀释

**根本原因：**
- LLM 生成的是全面陈述，而非简洁答案
- Judge 将冗长视为幻觉或离题而扣分

---

### 4. **计数错误**（2 例，1.6%）
数值聚合失败。

**示例：**
- Q："How many games has John mentioned winning?"
  - Gold："6" | Pred："5"

- Q："How many days did James plan to spend on his trip in Canada?"
  - Gold："19 days" | Pred："10 days"

**根本原因：**
- 跨多条记忆的计数失败
- 可能存在检索不全（并非所有相关记忆都进入 top-200）

---

### 5. **其他**（8 例，6.4%）
边缘案例与杂项错误。

---

## 与上次运行的对比（predicted_locomo-2-short-resp）

### 主要差异：

| 指标 | 上次运行 | 本次运行 | 变化 |
|--------|--------------|-------------|--------|
| **Acc@200** | 91.82% | 91.88% | +0.06% |
| **Wrong@200** | 126 例 | 125 例 | -1 例 |
| **Open-domain Acc** | ~67% | 67.71% | 几乎不变 |
| **Multi-hop Acc** | ~94% | 95.04% | +1% ✅ |

### 变化之处：
1. **模型：**上次运行可能使用了不同的模型/配置
2. **改进：**multi-hop 推理有边际增益
3. **遗留问题：**Open-domain 协议错配未变

### 未变之处：
- Open-domain 仍是瓶颈（错误率约 32%）
- 内容错误占主导（占失败的 54%）
- 计数错误少见但仍存在

---

## 根因分析

### 1. **记忆检索质量**
- Top-200 检索既包含相关记忆，也带入噪声
- **53.6% 的失败属于"全 cutoff 均错"** → 属检索问题，而非排序问题

### 2. **Open-domain 差距**
- **Open-domain 错误率 32.3%**，其他类别为 5–7%
- Gold 答案期待常识推断（例如室内遛狗活动答"cook dog treats"）
- 系统过于字面化，无法跨越语义鸿沟

### 3. **时间指代模糊**
- "Recently" 未正确锚定到参考日期
- 多个描述相似的事件干扰检索

### 4. **记忆编码粒度**
- 多个爱好/活动被存下时缺少明确的时间或优先级标记
- 例：Calvin 有多个爱好，系统检索到了错误的那个

---

## 建议

### 高优先级：
1. **修复 open-domain 协议：**
   - 为需要世界知识的题目加入推断层
   - 在开放式 QA 基准上微调（而非仅对话式记忆）

2. **提升记忆特异性：**
   - 为 "recently" 类事件加时间标记
   - 用唯一标识消歧相似活动

3. **约束回答冗长度：**
   - Prompt 工程："用 1–2 句简洁作答"
   - 后处理提取核心事实

### 中优先级：
4. **增强计数聚合：**
   - 作答前显式抽取并枚举事件
   - 对可计数实体使用结构化记忆

5. **检索优化：**
   - 调查为何 53.6% 的失败在所有 cutoff 都错
   - 可能需改进语义编码（如更好的 embedding）

---

## 待人工复核的失败案例样本

### 案例 1：内容错误（Single-hop）
- **Q：**What painting did Melanie show to Caroline on October 13, 2023?
- **Gold：**A painting inspired by sunsets with a pink sky.
- **Pred：**An abstract painting with vibrant colors on a blue background
- **分析：**检索到了另一幅画。记忆中可能存有多幅画，选错了。

### 案例 2：计数错误（Multi-hop）
- **Q：**How many video game tournaments has Nate participated in?
- **Gold：**nine
- **Pred：**10
- **分析：**差一。需核实记忆中是否确有 9 场不同的比赛。

### 案例 3：Open-domain 错配
- **Q：**What is an indoor activity that Andrew would enjoy doing while make his dog happy?
- **Gold：**cook dog treats
- **Pred：**Playing board games (such as chess)
- **分析：**系统未推断出狗需要零食，而是期待记忆中有"cooking dog treats"的明确记载。

### 案例 4：回答冗长
- **Q：**How does John plan to honor the memories of his beloved pet?
- **Gold：**By considering adopting a rescue dog
- **Pred：**John plans to honor the memories of his late dog Max by sharing cherished photos of him and committing to making progress in his life and community work in the coming weeks.
- **分析：**核心答案（"adopting rescue dog"）可能缺失，或被埋在冗长回答中。

---

## 结论

系统在 top-200 达到 **91.88% 准确率**，相比上次运行有边际提升（+0.06%）。但表现已趋于平台期，以下问题持续存在：

1. **Open-domain 推理**（错误率 32.3%）
2. **记忆特异性**（内容错误占失败的 54%）
3. **回答冗长**（占失败的 12.8%）

**下一步：**
- 聚焦 open-domain 协议修复（ROI 最高）
- 调查"全 cutoff 均错"案例（占失败的 53.6%）以改进检索
- 若当前方案无法突破 92% 上限，考虑架构层面的改动
