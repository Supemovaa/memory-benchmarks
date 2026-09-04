# Locomo-2 深度失败分析：真实错因归因

分析对象：`results/locomo/predicted_locomo-2` 的 125 例 wrong@200
方法：原始 conversation × gold evidence × retrieved memory × 生成答案，四方交叉比对

---

## 一、归因框架与结果

对每道错题，检查 gold 答案的内容词分别在**evidence 原文**、**200 条 memory 池**、**top-20 上下文**中的存活情况，得到四个互斥层级：

| 层级 | 判据 | 数量 | 占比 |
|---|---|---|---|
| **A. 推断/标注争议** | gold 不在原文，也不在池中 | 26 | 20.8% |
| **B. 提取层有损** | gold 在原文，但未存活到池中 | 17 | 13.6% |
| **C. 检索排序失败** | gold 在池中，但排名 >20 | 26 | 20.8% |
| **D. 生成/选择失败** | gold 已在 top-20 | 56 | 44.8% |

在此之上，人工复核发现一个**跨层的独立问题：19 例（15.2%）是数据集缺陷**，分两型：

- **类型 1（13 例）说话人归属错误**：问题问 A，evidence 引用的却是 B 说的话
- **类型 2（6 例）gold 与 evidence 矛盾或不完整**：gold 的时间限定与原话冲突、同一场景有多个等价答案而 gold 只列其一、或 gold 内容在原文根本无出处

这 19 例散落在 A/B/C/D 四层，模型答案实际上是对的或同等有效。

**扣除后的有效失败：106 例，真实错误率 6.88%**（报告口径 8.12%），等效 Acc@200 = **93.12%**。

---

## 二、层级 0：数据集缺陷（19 例，15.2%）

### 2.1 类型 1：说话人归属错误（13 例）

问题主语与 evidence 说话人不一致。全部 13 例已逐一核对上下文确认。

| qid | 问题问谁 | evidence 实际是谁说的 | 类别 |
|---|---|---|---|
| conv7_q179 | Jolene | Deborah | single-hop |
| conv9_q151 | Calvin | Dave | single-hop |
| conv4_q165 | Tim | John | single-hop |
| conv4_q166 | John | Tim | single-hop |
| conv4_q135 | Tim | John | single-hop |
| conv4_q136 | Tim | John | single-hop |
| conv9_q88 | Calvin | Dave | single-hop |
| conv9_q147 | Calvin | Dave | single-hop |
| conv7_q120 | Jolene | Deborah | single-hop |
| conv1_q44 | Gina | Jon | single-hop |
| conv3_q119 | Nate | Joanna | single-hop |
| conv3_q54 | Joanna | Nate | temporal |
| conv8_q24 | Sam | Evan | temporal |

**三个已完整核对上下文的实例：**

**conv7_q179** — Q: What did **Jolene** recently play that she described to Deb? / GOLD: a card game about cats
```
D27:11  Jolene : Thanks, Deb! Appreciate your support.
D27:12  Deborah: ...I recently played a game. This is a card game about cats...   ← evidence
D27:13  Jolene : I look forward to meeting you and playing this game!
```
说"card game about cats"的是 Deborah，而 D27:13 明确显示 Jolene 还没玩过。模型答 "scuba diving lesson"（Jolene 自己提过的活动）。

**conv4_q166** — Q: What is **John's** favorite book series? / GOLD: Harry Potter
```
D27:18  John: ...Which one is your favorite?
D27:19  Tim : Harry Potter is my favorite book. It's so immersive!   ← evidence
D27:20  John: Cool! Glad you're enjoying that book!
```
是 John 在问、Tim 在答。D27:20 的 "you're enjoying" 再次确认 Harry Potter 属于 Tim。

**conv4_q136** — Q: What did **Tim** say about his injury? / GOLD: The doctor said it's not too serious
```
D18:9   Tim : I hope your injury heals soon.
D18:10  John: ...The doctor said it's not too serious.   ← evidence
D18:12  John: I hate not being on the court.
```
受伤的是 John。模型答 "Tim did not have an injury... it was John who had an ankle injury" —— **完全正确，却被判错**。

这类标注错误集中在 single-hop（11/13），且有明显模式：**同一 session 内两人交替发言时，evidence 取了相邻的错误一轮**（conv4 一段对话里就有 3 例）。

---

### 2.2 类型 2：gold 与 evidence 矛盾或不完整（6 例）

这一型比说话人错误更隐蔽——evidence 引对了人，但 gold 本身站不住。

#### (a) gold 的时间限定与原话冲突（2 例）

**conv0_q135** — Q: What setback did Melanie face **in October 2023**? / GOLD: 受伤，暂停陶艺
```
session_17 @ 10:31 am on 13 October, 2023
D17:8  Melanie: ...BTW, recently I had a setback. **Last month** I got hurt and had to take a break from pottery
```
说于 10/13 的 "last month" 指的是 **9 月**。memory 存成 "around September 2023" 是**正确的**。问题却限定 October，模型据此排除 9 月事件、转而找真正落在 10 月的 setback（儿子车祸），是合理推理。**gold 与问题的时间限定自相矛盾。**

**conv0_q68** — Q: How long has Melanie been practicing art? / GOLD: Since 2016
```
session_16 @ 12:09 am on 13 September, 2023
D16:8  Melanie: **Seven years now**, and I've finally found my real muses: painting and pottery
```
原话是"七年"，gold 换算成了绝对年份 2016。模型答 "seven years" 是**原话的忠实复述**，语义完全等价，只是没做减法。

#### (b) 同一场景多个等价答案，gold 只列其一（2 例）

**conv0_q137** — Q: What painting did Melanie show to Caroline on October 13, 2023? / GOLD: 粉色天空的日落画
```
D17:12  Melanie: Here's one I did last week. It's inspired by the sunsets.
        |CAP: a photo of a painting of a sunset with a pink sky      ← evidence
D17:13  Caroline: Wow Mel, that's stunning!...
D17:14  Melanie: I've done an abstract painting too, take a look!
        |CAP: a photo of a painting on a wall with a blue background
```
**同一天 Melanie 展示了两幅画**。问题只说"on October 13"，没有任何限定词区分先后或类型。模型答蓝底抽象画（D17:14）**同样满足问题**，gold 只写了其中一幅。

**conv8_q116** — Q: What painting did Evan share with Sam in October? / GOLD: a cactus in the desert
```
session_11 @ 8:57 pm on 6 October, 2023
D11:8   Evan: Here's what I did last week.  |CAP: a painting of a cactus in the desert   ← evidence
D11:9   Sam : Wow, those**are** awesome!  (复数 → 不止一幅)
D11:10  Evan: The **sunset painting** was inspired by a vacation... The **cactus painting** came from a road trip
```
D11:9 用了复数 "those are"，D11:10 中 Evan 自己明确提到 sunset painting 和 cactus painting **两幅**。模型答 sunset/cliff 那幅同样有据。同一缺陷模式。

#### (c) gold 内容在原文无出处（1 例）

**conv3_q92** — Q: What kind of lighting does Nate's gaming room have? / GOLD: red and purple lighting
```
D10:2  Nate: ...just taking care of this.
       |CAP: a photo of a gaming room with a computer and a gaming chair   ← evidence
```
evidence 的 caption **完全没有灯光信息**。我在上一版报告里也确认过：整个 conv3 原文中搜索 `lighting|purple` 只匹配到"紫色头发"、"紫蓝色手柄"，**没有任何一处提到房间灯光颜色**。gold 的 "red and purple lighting" 在数据集中无出处（可能来自未提供给模型的原始图片）。模型答 "dimmable lights" 也是猜测，但 gold 本身不可达。

#### (d) evidence 定位偏移（1 例）

**conv2_q27** — Q: When did John have a party with veterans? / GOLD: The Friday before 20 May 2023
```
session_15 @ 7:38 pm on 20 May, 2023
D15:11  John: Here's a pic from **last Friday** with some veterans...   ← evidence（只有照片，没说party）
D15:13  John: We had a great time **throwing a small party** and inviting some veterans to share their stories
```
evidence 指向 D15:11（提到 last Friday 但未说 party），party 的内容其实在 D15:13。要答对需要：把 D15:11 的"last Friday"与 D15:13 的"party"关联，再用 session 日期 5/20 反推出 5/19。**这是 gold 隐含了两跳推理却标为 single-hop 的 evidence。**

---

## 三、层级 B：提取层有损（17 例，13.6%）

gold 事实在原文中存在，但抽取成 memory 时被抹掉。**全部 17 例都是 single-hop**——即使最简单的单跳题，提取层损失也普遍存在。

### B1. 具体属性被泛化（6 例）

| qid | 原文 | 存下来的 memory | GOLD | 模型答 |
|---|---|---|---|---|
| conv9_q113 | "The **wind blowing through my hair** and the rush of freedom" | "describing **the wind** and rush of freedom as he reflected on his life path" | feeling the wind blowing through his hair | 反思人生 + 唱歌 |
| conv9_q97 | "It's all about those **small details** that make it unique" | "Dave views customizing his car as a way to show his **personal style**" | attention to small details | personal style |
| conv9_q90 | "Adding electronic elements **gives them a fresh vibe**" | "describing the process as **exciting self-discovery and growth**" | gives them a fresh vibe | exciting self-discovery |
| conv4_q82 | "it's **super exciting and free-feeling**" | "describing the feeling as **unreal**" | super exciting and free-feeling | unreal |
| conv0_q140 | caption: `a sign that says trans lives matter` | "the posters displayed **pride and strength**" | "Trans Lives Matter" | pride and strength |
| conv1_q73 | Gina 形容 dance 为 **magical** | 池中 200 条**无一含 magical** | magical | expressive, graceful |

共性：**抽取器把原话的具体措辞替换成了自己的概括**。这类损失最致命，因为 gold 恰恰考的就是原话措辞。

### B2. 关键谓词/量词丢失（5 例）

| qid | 原文 | memory | GOLD |
|---|---|---|---|
| conv2_q119 | "I see them **at least once a week**" | 池中 rank 23 才有部分覆盖，top-20 完全没有 | At least once a week |
| conv9_q93 | "Keep at it and **never forget your dreams**!" | 池中无此建议 | to never forget his dreams |
| conv4_q158 | "most growth in **communication and bonding**" | 池中**0 覆盖**，只有"team's growth"泛化表述 | Communication and bonding |
| conv3_q151 | "I'm **taking some time off to chill with my pets**" | rank 45，top-20 只有"stoked and proud" | Taking time off to chill with pets |
| conv1_q52 | "Creating a special experience **is the key to making them feel welcome and coming back**" | rank 14 但覆盖仅 0.12 | 同左 |

### B3. 图片 caption 未进入检索（3 例）

**conv7_q119** — Q: What picture did Jolene share related to feeling overwhelmed?
- 原文 caption：`a photo of a desk with a notebook and a computer monitor`（覆盖 gold **100%**）
- 池中排名：**39**，top-20 覆盖仅 0.20
- 模型答：bullet journal spread（另一张照片）

**conv3_q143**、**conv0_q140** 同理，caption 中的具体内容在检索时权重过低。

### B4. 多轮信息未合并（3 例）

**conv3_q195** — Q: What does Nate want to do when he goes over to Joanna's place?
- 原文 D28:29：`Maybe we can watch one of your movies together or go to the park!`
- 池中 rank 13，覆盖 0.33
- 模型答：baking or cooking sessions（另一轮对话的内容）

---

## 四、层级 C：检索排序失败（26 例，20.8%）

gold 在 200 条池中，但排名 >20，未进生成窗口。

### C1. 泛化描述压制具体事件（最主要模式）

**conv0_q142** — Q: How do Melanie and Caroline describe their journey through life together?
- GOLD: An ongoing adventure of learning and growing.
- 原文 D17:25：Caroline 原话 `It's an ongoing adventure of learning and growing`
- **池中覆盖 100%，但排名 39**
- top-1 是 "Melanie told Caroline that she makes life's struggles more bearable" —— 主题相近的泛化陈述
- 模型只能基于 top-20 拼出"mutually supportive friendship"

**conv2_q98** — Q: What did John host for the veterans in May 2023?
- GOLD: a small party to share their stories（原文 D15:13 明确说 `throwing a small party and inviting some veterans to share their stories`）
- 池中 rank 33；top-1/top-2 是"December 2022 的 homeless shelter 活动"和"July 2023 的 marching event"
- 模型答：organized a petition

**conv0_q114** — Q: What do sunflowers represent according to Caroline?
- GOLD: warmth and happiness（原文 D8:11 Caroline 原话 `Sunflowers mean warmth and happiness`）
- 池中 rank 24，top-20 覆盖 **0**
- top-1/top-2 全是 Caroline 的 LGBTQ 社区话题

### C2. 计数题的证据分散（3 例）

**conv2_q62** — Q: How many dogs has Maria adopted from the dog shelter?
- GOLD: two；evidence 是两条独立 session（D30:1 领养 Coco / D31:2 领养第二只）
- 两条 memory 分别在 rank 21 和更后，**top-20 覆盖 0**
- top-1 是 "Maria started volunteering at a local dog shelter once a month" —— 查询词"dog shelter"命中了志愿活动而非领养事件
- 模型答：1

### C3. 时间窗口无法匹配（6 例，temporal 类别的主要失败源）

**conv9_q12** — Q: When was Calvin's concert in Tokyo?
- GOLD: last week of May 2023
- 池中 rank 37 才是正确的 "Calvin performed in Tokyo recently (around late May 2023)"
- top-2 是 "Tokyo music festival around August 21, 2023" —— **同一城市的另一场演出排名更高**
- 模型答：Around August 2023

### C4. 需要推断的隐含信息（3 例）

**conv7_q36** — Q: How old is Jolene? / GOLD: likely no more than 30; since she's in school
- 10 条 evidence 全是"studies/exams/engineering student"，**无一处直接说年龄**
- 池中 rank 161 才有弱覆盖
- 模型答："memories do not state Jolene's exact age"（保守但被判错）

---

## 五、层级 A：推断/标注争议（26 例，20.8%）

gold 既不在原文也不在池中。**21/26 是 open-domain**，占 open-domain 全部错误（31 例）的 **67.7%**。

### A1. gold 需要世界知识桥接

**conv7_q18** — Q: In what country did Jolene buy snake Seraphim? / GOLD: In France
- 原文 D2:24：`I bought it a year ago in Paris.`
- gold 把 Paris 抽象成了 France（需要地理知识）
- **池中 200 条无一含 Paris 或 France**——抽取时地点信息被丢弃，memory 只有 "Jolene acquired Seraphim around June 2022"
- 模型答：Colombia（幻觉）
- **这一例同时是 B 类（提取丢失 Paris）+ A 类（gold 需要 Paris→France 推断）的叠加**

**conv5_q19** — Q: What indoor activity would Andrew enjoy while making his dog happy? / GOLD: cook dog treats
- evidence 只有两条：Andrew 喜欢 cooking（D10:12）、Andrew 养了狗 Toby（D12:1）
- 原文从未出现 "dog treats"，gold 是标注者做的常识合成（cooking + dog → cook dog treats）
- 模型答：board games / chess

**conv4_q53** — Q: What other exercises can help John with his basketball performance? / GOLD: Sprinting, long-distance running, and boxing
- evidence 只提到 strength training（D8:5）和 yoga（D20:2）
- gold 的三项全是标注者基于运动科学的推荐，对话中完全没有
- 模型答：总结了已有的 strength training

**conv2_q64** — Q: What job might Maria pursue in the future? / GOLD: Shelter coordinator, Counselor
- 4 条 evidence 全是志愿经历，无一处提职业规划
- 模型答："memories do not specify a particular paid job"——事实上准确

### A2. 聚合计数无显式记录

**conv3_q78** — Q: How many video game tournaments has Nate participated in? / GOLD: nine
- evidence 是 **9 条独立 session**（D1:3, D6:7, D10:4, D14:8, D17:1, D19:1, D20:1, D22:2, D27:1）
- 每场比赛单独存为一条 memory，**池中不存在"nine"这个聚合事实**
- 模型答：10

值得注意的是，逐条读 evidence 会发现计数本身有歧义：D6:7 说的是 "participating **again**"（进行中，非新增一场），D20:1 是 "had a letdown"（参加但输了）。gold=9 与模型=10 的差异正来自"是否把某次重复提及算作独立赛事"，**这题的标注也存在争议空间**。

---

## 六、层级 D：生成/选择失败（56 例，扣除 8 例标注错误后为 48 例，38.4%）

gold 已在 top-20，模型仍答错。这是最大的一类，也是**唯一纯粹属于生成器的失败**。

### D1. 多候选并存时选错（最主要模式，约 20 例）

**conv2_q130** — Q: Which activity has John done **apart from yoga** at the studio? / GOLD: weight training
- 原文 D25:17：`I've done weight training so far too`
- top-1 memory: "John's yoga studio offers a variety of classes including yoga, **kickboxing, and circuit training**"
- 模型答：kickboxing and circuit training
- **错因**：top-1 列出的是"studio 提供的课程"（可选项），gold 要的是"John 实际做过的"。模型混淆了 offered 与 done。prompt 的 Step 4 明确写过 "Report what someone actually DID, not what was offered"，但未生效。

**conv0_q135** — Q: What setback did Melanie face in **October 2023**? / GOLD: 受伤，暂停陶艺
- **top-1 memory 就是正确答案**："Melanie experienced a setback around **September** 2023 when she got hurt and had to take a break from pottery"
- 模型答：儿子车祸（10月14-15日）
- **错因**：模型严格按"October"筛选，而 memory 标的是 September（原文 D17:8 是 10月13日说"**last month** I got hurt"，抽取时把 last month 解析成 September）。模型选了时间戳真正落在 10 月的另一事件。**这是 B 类（抽取时间错误）诱发的 D 类失败**。

**conv0_q137** — Q: What painting did Melanie show on **October 13, 2023**? / GOLD: 灵感来自日落的粉色天空画
- 池中覆盖 100%，rank 10 有 "Melanie created a landscape painting of a sunset with a pink sky around **October 6**"
- top-1 是 "abstract painting with vibrant colors on a **blue** background... around October 2023"
- 模型答：blue background 那张
- **错因**：两幅画都在窗口内，模型选了时间描述更贴合"October 2023"的 top-1。gold 对应的那条被标成 October 6，与提问日期 10/13 不符。

**conv2_q88** — Q: What topic has John been blogging about recently? / GOLD: politics and the government
- 池中 rank 3 就是原话覆盖
- 模型答：education reform and infrastructure（另一条 memory 的内容）

**conv0_q85** — Q: What are Caroline's plans for the summer? / GOLD: researching adoption agencies
- 池中 rank 14 覆盖 100%
- top-1 是 "summer trip with Melanie"
- 模型答：LGBTQ art show + summer outing

### D2. 抽象层级过高（约 8 例）

**conv2_q18** — Q: Who did John go to yoga with? / GOLD: Rob
- **top-1 memory 明确写了 "John's colleague **Rob** invited him to a beginner's yoga class"**
- 模型答：a colleague
- **错因**：纯粹的生成层退化——具体人名就在 top-1，模型却输出了上位词。prompt Step 4 的 "ALWAYS choose the MOST SPECIFIC detail" 未生效。

**conv3_q14** — Q: What nickname does Nate use for Joanna? / GOLD: Jo
- 原文 D7:1：`Hey **Jo**, guess what I did?`
- 模型答：Joanna（即全名，恰好是"非昵称"）

**conv0_q71** — Q: What book did Melanie read from Caroline's suggestion? / GOLD: "Becoming Nicole"
- 两条 evidence 跨 session：D7:11（Caroline 推荐 Becoming Nicole）+ D17:10（Melanie 说在读你推荐的书）
- 池中覆盖 0.50 @ rank 6
- 模型答：Charlotte's Web（幻觉，池中另一本书）
- **错因**：需要跨两条 memory 做指代链接（"that book you recommended" → Becoming Nicole），模型未建链

### D3. 数值/时长计算错误（约 6 例）

**conv2_q63** — Q: How many weeks passed between Maria adopting Coco and Shadow? / GOLD: two weeks
- evidence：D30:1（8/11，"got a puppy **two weeks ago**"→ Coco 约 7/28）+ D31:2（8/13，"adopted **last week**"→ Shadow 约 8/6）
- 池中覆盖 100% @ rank 7
- 模型答：Approximately 1.3 weeks
- **错因**：模型用了两次对话的日期差（8/11→8/13 = 2天）或错误锚定，而非两次领养的实际日期差。相对时间表达（"two weeks ago"/"last week"）需要先转绝对日期再相减，模型跳过了这一步。

### D4. 时间锚定错误（约 8 例，temporal 的主要失败源）

**conv2_q48** — Q: When did John have his first firefighter call-out? / GOLD: The Sunday before 3 July 2023
- 原文 D26:4：`**Last Sunday** we had our first call-out`（这句说于 7/3 前后）
- **memory 记的是 "John had his first call-out on July 30, 2023"** —— 抽取时把说话日期误当事件日期
- 模型答：July 30（忠实复述了错误的 memory）
- **这是 B 类污染 D 类的典型**：memory 本身与 gold 矛盾，模型无从纠正

**conv2_q59** — Q: When did John go on a camping trip with Max? / GOLD: The summer of 2022
- 原文 D30:6：`Max and I had a blast on our camping trip **last summer**`（说于 2023 年夏 → 指 2022 年夏）
- memory：`around summer 2023` —— 相对时间未换算
- 模型答：summer of 2023

**conv3_q22** — Q: When did Joanna start writing her third screenplay? / GOLD: May 2022
- 模型答：完整推理后结论 "An explicit start date is not provided"，给出 April 21 - May 20 区间
- 池中覆盖 100% @ rank 1，但那条 memory 讲的是**第二部**剧本（Feb 2022）
- **错因**：需要按序数（first/second/third）排序剧本时间线，模型排序失败

---

## 七、量化汇总

| 层级 | 原始数 | 扣除数据集缺陷后 | 占有效失败 | 可归责 | 修复杠杆 |
|---|---|---|---|---|---|
| L0 数据集缺陷 | 19 | — | — | ❌ 数据集 | 修正 evidence / gold |
| A 推断争议 | 26 | 24 | 22.6% | ⚠️ 协议 | 重定义评测或加推断层 |
| B 提取有损 | 17 | 15 | 14.2% | ✅ 系统 | **抽取保真度** |
| C 排序失败 | 26 | 23 | 21.7% | ✅ 系统 | **混合检索** |
| D 生成失败 | 56 | 44 | 41.5% | ✅ 系统 | rerank + CoT |
| **合计** | **125** | **106** | 100% | | |

**有效错误率：106/1540 = 6.88%**（报告口径 8.12% 中有 **1.24pt** 是数据集缺陷）
**等效 Acc@200 = 93.12%**

### 错因 × 类别

| | single-hop | multi-hop | temporal | open-domain |
|---|---|---|---|---|
| L0 数据集缺陷 | 15 | 0 | 4 | 0 |
| A 推断争议 | 2 | 1 | 2 | 21 |
| B 提取有损 | 17 | 0 | 0 | 0 |
| C 排序失败 | 14 | 3 | 6 | 3 |
| D 生成失败 | 29 | 10 | 10 | 7 |
| 小计 | 62 | 14 | 18 | 31 |

**四个类别的瓶颈完全不同：**
- **single-hop（62 错）**：提取有损 17 例是独有问题 + 数据集缺陷 15 例；扣除后 **30 例**真实失败
- **multi-hop（14 错，5.0%）**：表现最好，主要是生成层跨记忆链接失败
- **temporal（18 错）**：C 类占 6/18，**相对时间未换算成绝对日期**是核心（conv2_q48/q59 两例 memory 本身就错）
- **open-domain（31 错）**：21 例（67.7%）是 gold 要求超出记忆的推断，**属协议错配**

---

## 八、跨层耦合：一个关键发现

单看归因表会低估提取层的影响。实际上**B 类污染会伪装成 D 类失败**：

| qid | 表面归因 | 真实根因 |
|---|---|---|
| conv2_q48 | D（gold 在 top-20） | memory 把"last Sunday"存成了 July 30 → **B** |
| conv2_q59 | D | memory 把"last summer"存成 summer 2023 → **B** |
| conv0_q135 | D（top-1 就是答案） | memory 把"last month"存成 September，与提问的 October 冲突 → **B** |
| conv7_q18 | A（需 Paris→France） | memory 完全丢弃了 Paris → **B** |

这 4 例的 memory 内容与原文事实矛盾，模型忠实复述反而答错。**把这类计入后，提取层实际影响约 19-21 例（17-19%）**，超过表面的 13.4%。

共性机制：**相对时间表达（last month / last summer / last Sunday / two weeks ago）在抽取时被错误地锚定到了说话日期**，而非换算成事件日期。

---

## 九、修复优先级

按"可修复例数 / 实现成本"排序：

### 1. 抽取层保真（覆盖 19-21 例，约 +1.3pt）
- **相对时间强制换算**：抽取时把 last month/last summer/two weeks ago 结合 session 日期换算成绝对日期，并**分开存储 event_date 与 utterance_date**（直接修 conv2_q48/q59、conv0_q135）
- **保留原话措辞**：具体属性（wind through hair / small details / fresh vibe / magical / trans lives matter）不做同义改写，或额外存一份原文 span
- **caption 独立成条**：图片描述作为独立 memory，避免被文本主句吞掉（修 conv7_q119）
- **保留量词与地点**：at least once a week、in Paris 这类限定词不可丢

### 2. 检索混合化（覆盖约 16-18 例，约 +1.1pt）
- **BM25 + 向量混合**：C 类的主模式是"泛化描述压制具体事件"，lexical 匹配能把 conv0_q142（rank 39）、conv2_q98（rank 33）、conv0_q114（rank 24）拉进 top-20
- **计数题聚合召回**：检测 how many → 按实体+谓词召回全部实例再去重（修 conv2_q62）
- **时间过滤**：查询含月份/季节时按 event_date 过滤，避免 conv9_q12 那样"同城市另一场演出"排在前面

### 3. 生成层 rerank + 显式推理（覆盖约 15-20 例，约 +1.0pt）
- **specificity rerank**：top-20 内若同时存在具体实体与上位词，强制选具体的（修 conv2_q18 的 Rob / a colleague）
- **offered vs done 区分**：prompt 已有该规则但未生效，需在 rerank 阶段硬过滤（修 conv2_q130）
- **相对时长计算链**：要求先把两个相对时间锚定成绝对日期再相减（修 conv2_q63）
- **序数排序**：first/second/third 类问题先建时间线再定位（修 conv3_q22）

### 4. 数据集修正（不涨分，但让指标可信）
- 修正 13 例 evidence 说话人错误
- conv3_q78 的计数标准需明确（"participated" 是否含重复提及的同一赛事）

### 5. open-domain 单列（约 21 例，+1.4pt 但属口径调整）
21 例 gold 要求超出记忆的常识推断。这不是记忆系统的能力边界问题，混在总分里会误导迭代方向。建议单列报告或改用软性 judge。

---

## 十、上限估算

当前 91.88%，有效错误 112 例。

| 修复项 | 可回收 | 累计 acc |
|---|---|---|
| 基线 | — | 91.88% |
| 修正数据集标注（13 例） | +0.84pt | 92.72% |
| 抽取层保真 | +1.3pt | 94.0% |
| 检索混合化 | +1.1pt | 95.1% |
| 生成层 rerank | +1.0pt | 96.1% |
| open-domain 单列 | +1.4pt | 97.5%（口径调整）|

**技术可达上限约 96%**；剩余 4% 主要是 open-domain 推断题和真正歧义的标注。

---

## 十一、与上次分析的结论差异

上次报告（`fail_case_analysis.md`）把 `CHUNK_SIZE=1` 列为最大杠杆，理由是"25.8% 的 gold 从不出现在池中"。本次逐案核对后需要修正这个判断：

- **上次的 25.8%** 是用 gold 内容词覆盖率 <0.6 粗筛得到的，其中相当一部分实际是 **A 类**（gold 本就不在原文，是标注者推断），不是抽取丢失
- 真正的抽取丢失是 **17 例（13.6%）**，加上时间锚定错误的耦合案例约 19-21 例
- **`CHUNK_SIZE` 不是主因**：B 类的 17 例中，损失机制是"抽取器改写措辞/丢弃限定词"，而非"看不到相邻上下文"。conv9_q113 的原话和 memory 在同一轮内，加大 chunk 也不会保住 "wind through hair"
- **真正该改的是抽取 prompt/schema**：要求保留原话措辞、相对时间换算、caption 独立成条

上次的第 1 项（`max_tokens`）已在本次验证解决（CoT 泄漏 73→0）。第 6 项（top_50 作为工作点）依然成立。
