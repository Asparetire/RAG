# M3 冒烟验收报告——A 档

- 生成时间：2026-11-11 22:07:08
- 题集：smoke_queries.json（vm3-smoke-v1，20 题）
- 判定规则：可回答题人工对照 gold_hint 判通过/失败；不可回答题以 refused=True 为通过；
- 验收线：通过率 ≥80%（≥16/20）；不可回答拒绝 ≥3/4；可回答误拒 ≤1（m3-runbook §1）

| # | q_id | 类型 | 语言 | 问题 | 答案（截 300 字） | 引用 | 弃答 | trace | 通过/失败 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | s01_text_zh | text | zh | Kapur 方法和 Otsu 方法分别是用来做什么的？ |  | - | 否 | 20261111220708-A-c377cc7668 | |
| 2 | s02_text_en | text | en | What is the ε-greedy implementation used for in the Q-learning driven DE algorithm? | In the Q-learning driven DE algorithm (QDEHHO), the ε-greedy implementation serves to balance exploration and exploitation when selecting DE strategies and parameters:  - **Where it is applied:** Both levels of the two-level Q-learning architecture apply an ε-greedy scheduling rule — the method-leve | [1], [7], [2] | 否 | 20261111220800-A-2164fd9cc5 | |
| 3 | s03_text_zh | text | zh | 深度学习和传统机器学习的区别是什么？ | 根据资料，深度学习（DL）与传统机器学习（ML）的区别主要体现在以下几个方面：  **1. 从属关系与模型结构** - DL 是 ML 的一个子集，其灵感来自人脑的信息处理模式，无需人工设计的规则，而是利用大量数据将给定输入映射到特定标签 [1]。 - DL 由多层算法（人工神经网络，ANN）构成，每一层对输入数据提供不同的解释 [1]；简言之，DL 是多层神经网络从海量数据中学习的 ML 子集 [2]。  **2. 特征处理方式（最核心的区别）** - 使用传统 ML 技术完成分类任务需要多个顺序步骤：预处理、特征提取、特征选择、学习和分类；且特征选择对性能影响很大，有偏差的特征选择可能导致 | [1], [2], [5], [3], [11], [8], [13] | 否 | 20261111220820-A-80497a1c1b | |
| 4 | s04_text_en | text | en | What are the differences between deep learning and traditional machine learning? | Based on the sources, the main differences between deep learning (DL) and traditional machine learning (ML) are:  1. **Relationship and architecture**: DL is a subset of ML [1], specifically the subset in which multilayered neural networks learn from vast amounts of data [3]. In neural networks, pre | [1], [3], [8], [7], [9], [6] | 否 | 20261111220851-A-a3148ff503 | |
| 5 | s05_text_zh | text | zh | 什么是贝叶斯教学（Bayesian teaching）？它如何帮助大语言模型做概率推理？ | ## 什么是贝叶斯教学（Bayesian teaching）  贝叶斯教学是一种教大语言模型近似贝叶斯推理（approximate Bayesian reasoning）的策略：具体做法是向 LLM 提供用户与“贝叶斯助手”之间交互的示例，并让 LLM 模仿这些交互 [7]。在实现上，这是一种监督微调（supervised fine-tuning）技术，用于让 LLM 模仿规范贝叶斯模型（normative Bayesian model）的预测 [6]。作为模仿对象的贝叶斯助手会维护一个反映其对用户偏好信念的概率分布，并随着用户新选择信息的到来，用贝叶斯规则更新这一分布 [7]。  ## 它如 | [7], [6], [4], [8], [9], [3] | 否 | 20261111220922-A-f86d29bbb5 | |
| 6 | s06_text_en | text | en | According to the STRATOS initiative, what is IDA (initial data analysis) and why does it matter? | ## What is IDA?  According to the STRATOS initiative (topic group TG9 on high-dimensional data), initial data analysis (IDA) is described as "an important first step in every data analysis" and is the term for all steps of data inspection and screening that occur after the analysis plan and data col | [2], [9], [4], [12], [1] | 否 | 20261111220957-A-1747f3fd77 | |
| 7 | s07_fig_zh | figure | zh | 哈里斯鹰优化算法（HHO）的各个阶段是什么样的？ | 哈里斯鹰优化算法（HHO）是一种基于种群的元启发式算法，其灵感来自哈里斯鹰的协作捕猎策略，模拟捕食者与猎物之间的动态交互 [1]。该算法主要经历三个阶段：（1）探索、（2）由猎物逃逸能量主导的转换、（3）采用多种围攻策略的开发 [1]。  **1. 探索阶段** 在这一阶段，鹰通过相对于随机个体或种群均值调整自身位置来多样化搜索，从而在随机探索与群体智能之间取得平衡 [1]。  **2. 转换阶段** 转换机制由猎物的逃逸能量驱动，该能量随迭代次数线性递减 [1]。当能量的绝对值较高时，算法倾向于继续探索；而当能量值较低时，则触发开发阶段 [1]。具体而言，逃逸能量定义为 E = 2E₀(1− | [1], [10] | 否 | 20261111221022-A-cc9b060ed2 | |
| 8 | s08_fig_en | figure | en | What are the various stages of Harris hawks optimization shown in the paper? | According to the paper, Harris Hawks Optimization (HHO) proceeds through three main stages: (1) exploration, (2) transition governed by prey escape energy, and (3) exploitation with multiple besiege strategies [1].  Details of each stage are as follows:  1. **Exploration stage**: Hawks diversify the | [1] | 否 | 20261111221043-A-5011f78e65 | |
| 9 | s09_fig_zh | figure | zh | 压力容器设计问题的示意图里包含哪些设计变量？ | 根据 Source 1，压力容器设计问题（4.4 节，F29）的示意图为 Fig. 2，展示的是一个工作压力为 3000 psi、最小容积为 750 ft³ 的压缩空气储存罐的结构 [1]。  该问题的设计变量共有四个，即 x₁、x₂、x₃、x₄，它们出现在该问题的数学模型（Eq. 18）的目标函数中 [1]。各变量的取值范围为：0.0625 ≤ x₁, x₂ ≤ 6.1875 [2]，以及 10 ≤ x₃, x₄ ≤ 200 [2]。  需要说明的是，所给 Source 中仅以 x₁–x₄ 的形式给出这些设计变量及其数学表达式和取值范围，并未在文字中具体说明每个变量在示意图中对应的物理含义（ | [1], [2] | 否 | 20261111221054-A-7483eee558 | |
| 10 | s10_fig_en | figure | en | What does the overview of the two-stage paradigm in the LLM overconfidence paper depict? | The overview (Fig. 1) of the two-stage paradigm depicts a controlled experimental setup for testing how LLMs update their confidence and decide whether to change their answers when presented with external advice [1]. Inspired by psychophysics and neuroscience studies of change of mind (CoM), it focu | [1], [5], [4] | 否 | 20261111221131-A-c9b17782f3 | |
| 11 | s11_fig_zh | figure | zh | KAN 与 MLP 的基本单元有什么区别？ | KAN 与 MLP 基本单元的区别主要体现在以下几个方面：  1. **优化对象不同**：MLP 通过训练节点之间的权重来优化模型，其激活函数是固定的；而 KAN 则通过训练激活函数来优化模型，激活函数的拟合是通过参数化为样条的一元函数实现的 [1]。  2. **激活函数的位置不同**：在 KAN 模型中，激活函数被放置在边上而不是节点上，节点主要执行简单的求和运算 [2]。  3. **参数形式与规模不同**：KAN 用样条函数取代了 MLP 中简单的权重参数，因此 KAN 通常可以使用比 MLP 小得多的计算图，所需的训练参数也远少于 MLP [2]。  4. **可学习的基函数组合** | [1], [2], [4] | 否 | 20261111221158-A-fdc6fabfa6 | |
| 12 | s12_table_zh | table | zh | 在预选择策略的对比研究中，哪种预选择策略表现最好？ | 根据对比研究的结果，**RCPS（基于关系对的分类预选择策略）** 表现最好。  具体依据如下：  1. 在三种预选择策略（RPS、CPS、RCPS）的系统性对比中，RCPS 在三种策略中取得了最高的预测准确率 [9]。  2. 在 CoDE 算法上的实验结果也表明，在 F1–F3（n = 5）和 F1–F4（n = 10）测试问题上，使用 RCPS 的 CoDE 表现优于使用 CPS 和 RPS 的版本 [5]。  3. 在与其他算法的比较中，结合 Bayes 分类的 CoDE with RCPS 取得了最佳结果 [11]，且其收敛性能也是最好的 [8]。  4. 总体而言，实验结果显示基于 | [9], [5], [11], [8] | 否 | 20261111221218-A-d3127d9564 | |
| 13 | s13_table_en | table | en | Which preselection strategy achieves the best performance in the comparison study? | **RCPS (relationship classification-based preselection)** achieves the best performance in the comparison study.  Key evidence from the sources:  - The paper's abstract states that "on two sets of test suits, RCPS outperforms the comparison preselection strategies" [10]. - In the direct comparison o | [10], [3], [6], [8], [5], [12] | 否 | 20261111221232-A-67249c11c1 | |
| 14 | s14_table_zh | table | zh | bQDEHHO 在 CEC2017 上的参数敏感性实验是怎么设置的？ | 根据 Source，bQDEHHO（论文提出的算法）在 CEC2017 上的参数敏感性实验设置如下：  **可调参数的选择** - 实验将 Q-table 更新中使用的**学习率 α 和折扣因子 γ** 作为主要可调超参数 [1]。 - 两个 Q-table 采用**各自独立的 (α, γ) 设置**进行对比 [1]。  **参数配置方案** - 如 Table 1 所示，共评估了**九组候选参数配置** [1]。  **实验平台与评估目的** - 实验在 **CEC2017 基准测试套件**上进行，用于评估不同 (α, γ) 设置对**收敛速度、最优解质量和全局搜索能力**的影响 [1]。  | [1], [3], [2] | 否 | 20261111221248-A-24f0c89f06 | |
| 15 | s15_table_en | table | en | What search criteria were used to find decision tree publications in the survey's literature search? | According to the survey, the authors defined inclusion and exclusion criteria to refine the results and guarantee both quality and relevance, such that a paper had to satisfy all inclusion criteria and none of the exclusion criteria [2]. The inclusion criteria were: (1) the paper proposes a method i | [2], [4] | 否 | 20261111221313-A-6005967936 | |
| 16 | s16_table_zh | table | zh | 描述性统计方法一览表里对位置和尺度的度量包含哪些？ | 根据文档，描述性统计方法一览表（Table 3）涵盖位置和尺度的度量、双变量度量、RLE 图和 MA 图 [2]。其中对位置和尺度的度量具体包含以下内容：  **位置的度量：** - 均值：是连续数据的标准选择 [1] - 中位数：对极端值具有稳健性 [1] - 众数：常用于分类数据 [1] - 这些度量还可以通过逐分量（即对每个变量分别）计算并汇总成向量，从而扩展到更高维度 [1]  **尺度的度量：** - 标准差：用于连续数据 [1] - 中位数绝对偏差（MAD）：作为标准差的稳健替代方法 [1] - 变异系数：通过标准差除以均值进行缩放，有助于比较在不同尺度上测量的变量 [1] | [2], [1] | 否 | 20261111221332-A-4a546a2d90 | |
| 17 | s17_unans_zh | unanswerable | zh | 2026 年最新的图像分割阈值方法是哪一种？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111221349-A-34c8ddfc9b | |
| 18 | s18_unans_en | unanswerable | en | Who won the Turing Award in 2025? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111221353-A-68951a33f7 | |
| 19 | s19_unans_zh | unanswerable | zh | 怎样用 Python 实现一个红黑树？请给出完整代码。 | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111221357-A-073c310e5a | |
| 20 | s20_unans_en | unanswerable | en | What is the price of the commercial license for the Bayesian Assistant software? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111221359-A-a84ff90088 | |

**不可回答拒绝率（自动统计）**：4/4

## 人工判定

- gold_hint 对照：见 scripts/smoke_queries.json
- 逐题证据定位：data/traces/traces-*.jsonl 按 trace 列回放

| # | q_id | gold_hint | 备注 |
|---|---|---|---|
| 1 | s01_text_zh | 13c8e91b3467 §2.1 Kapur method / §2.2 Otsu method（多级阈值分割的问题表述） | |
| 2 | s02_text_en | 5bec341c3134 §3.1.2 --greedy implementation（QDEHHO 的两级策略-参数决策） | |
| 3 | s03_text_zh | 5db85404be42 Background/Why deep learning 节 + Fig.3（深度学习与传统机器学习的区别） | |
| 4 | s04_text_en | 5db85404be42 Background/Why deep learning 节 + Fig.3 | |
| 5 | s05_text_zh | 6ebe216067e3 Results/The Bayesian Assistant/Teaching LLMs to approximate Bayesian reasoning | |
| 6 | s06_text_en | 69b72d2b0341 Background/STRATOS topic group TG9 + Results/IDA 节 | |
| 7 | s07_fig_zh | 5bec341c3134 Fig. 2 The various stages of HHO（图）+ §2.2 Harris hawks optimization | |
| 8 | s08_fig_en | 5bec341c3134 Fig. 2 The various stages of HHO（图）+ §2.2 Harris hawks optimization | |
| 9 | s09_fig_zh | 3627b932f186 Fig. 2 The schematic structure of pressure-vessel design problem（图）+ §4.4 | |
| 10 | s10_fig_en | d059e8540d5d Fig. 1 \| Overview of the two-stage paradigm（图）+ Results 首节 | |
| 11 | s11_fig_zh | f9807c0c485e Fig. 1 Comparison of MLP and KAN + Fig. 2 Infrastructure of the KAN model + Preliminaries/Kolmogorov-Arnold network | |
| 12 | s12_table_zh | 4f23718fa52e III. COMPARISON STUDY OF PRESELECTION STRATEGIES 结果表（RCPS 相关表格） | |
| 13 | s13_table_en | 4f23718fa52e III. COMPARISON STUDY OF PRESELECTION STRATEGIES 结果表（RCPS 相关表格） | |
| 14 | s14_table_zh | 5bec341c3134 §3/§4 + Fig. 4 QDEHHO parametric sensitivity on CEC2017 + 相关参数表 | |
| 15 | s15_table_en | 7335e03ac56b Fig. 2 图注（检索式 TI=(tree*) AND TS=(classif* OR regress* OR decision)）+ Inclusion/Exclusion criteria 节；原题问柱状图具体数字（数字仅在图中、无文本可检回，属出题缺陷），已修正为图注可答事实 | |
| 16 | s16_table_zh | 69b72d2b0341 Table 3 Methods for descriptive statistics: Measures for location and scale（表格） | |
| 17 | s17_unans_zh | 语料为 2024-2026 前的历史论文集合，且无'2026 最新'类比较——应拒绝 | |
| 18 | s18_unans_en | 语料无关——应拒绝 | |
| 19 | s19_unans_zh | 语料是算法应用论文，无红黑树实现代码——应拒绝 | |
| 20 | s20_unans_en | 6ebe216067e3 是研究论文，无商业化定价信息——应拒绝 | |
