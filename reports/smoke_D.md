# M3 冒烟验收报告——D 档

- 生成时间：2026-11-11 21:17:32
- 题集：smoke_queries.json（vm3-smoke-v1，20 题）
- 判定规则：可回答题人工对照 gold_hint 判通过/失败；不可回答题以 refused=True 为通过；
- 验收线：通过率 ≥80%（≥16/20）；不可回答拒绝 ≥3/4；可回答误拒 ≤1（m3-runbook §1）

| # | q_id | 类型 | 语言 | 问题 | 答案（截 300 字） | 引用 | 弃答 | trace | 通过/失败 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | s01_text_zh | text | zh | Kapur 方法和 Otsu 方法分别是用来做什么的？ | 根据 Source 内容，Kapur 方法和 Otsu 方法的用途如下：  - Kapur 方法和 Otsu 方法已被证明是图像分割中双层级阈值化的有效方法 [3]。 - 它们属于非参数方法，基于给定的准则以最优方式确定阈值，比参数化方法更稳健、更准确 [9]。 - 这两种方法可以较容易地扩展到多层级阈值化问题，但计算时间会随阈值数量的增加呈指数增长，从而限制了多层级阈值化的应用 [3][9]。 - 在实际应用中，可以通过 Kapur 和 Otsu 函数来逼近图像的直方图，即计算各函数参数的最优值 [15]。 - 其中 Kapur 熵利用直方图的全局客观属性，由于其通用性，该准则可用于分割目的 | [3], [9], [15], [18] | 否 | 20261111211732-D-17e6578ab7 | |
| 2 | s02_text_en | text | en | What is the ε-greedy implementation used for in the Q-learning driven DE algorithm? | In the Q-learning driven DE algorithm (QDEHHO), the ε-greedy implementation serves the following purposes:  1. **Adaptive selection of strategies and parameters**: It is applied at both levels of the two-level Q-learning architecture — the method-level Q-table (which evaluates four candidate mutatio | [1], [10] | 否 | 20261111211800-D-19f33fbc89 | |
| 3 | s03_text_zh | text | zh | 深度学习和传统机器学习的区别是什么？ | 深度学习（DL）是机器学习（ML）的一个子集，其灵感来自人脑的信息处理模式 [2]。两者的核心区别在于特征处理方式：使用传统 ML 技术完成分类任务需要多个顺序步骤，即预处理（pre-processing）、特征提取（feature extraction）、明智的特征选择（wise feature selection）、学习和分类，而且特征选择对 ML 技术的性能影响很大，有偏差的特征选择可能导致类别之间的错误判别 [2]。相比之下，DL 能够针对多种任务自动学习特征集，使学习和分类可以“一步到位”（single shot）地完成 [2]。传统 ML 的有效性高度依赖于输入数据表示的完整性，因 | [2], [5], [11], [15], [1] | 否 | 20261111211827-D-8d5bc3610e | |
| 4 | s04_text_en | text | en | What are the differences between deep learning and traditional machine learning? | According to the sources, deep learning (DL) is actually a subset of machine learning (ML), but the two differ in several key ways [3]:  1. **Feature handling / feature engineering**: Achieving a classification task with conventional ML requires several sequential steps—pre-processing, feature extra | [3], [9], [6], [1], [12], [10] | 否 | 20261111211904-D-e87d308a0e | |
| 5 | s05_text_zh | text | zh | 什么是贝叶斯教学（Bayesian teaching）？它如何帮助大语言模型做概率推理？ | ## 什么是贝叶斯教学（Bayesian teaching）  贝叶斯教学是一种通过监督微调（supervised fine-tuning）让大语言模型模仿“规范性贝叶斯模型”（normative Bayesian model）预测的方法 [9]。具体而言，研究者在用户与一个“贝叶斯助手”（Bayesian Assistant）的交互数据上对 LLM 进行微调，而该贝叶斯助手代表了关于用户偏好更新信念的规范性方式 [6]。  ## 它如何帮助大语言模型做概率推理  - **弥补差距**：研究首先发现，LLM 在信念更新方面远未达到贝叶斯框架所设定的标准 [7]。 - **提升与贝叶斯模型的一致 | [9], [6], [7], [2], [10], [4] | 否 | 20261111211948-D-578915b63d | |
| 6 | s06_text_en | text | en | According to the STRATOS initiative, what is IDA (initial data analysis) and why does it matter? | According to the STRATOS initiative, initial data analysis (IDA) is an important first step in every data analysis, and it can be particularly challenging in high-dimensional data (HDD) settings [2]. IDA is a term for all steps of data inspection and screening that take place after the analysis plan | [2], [16], [5], [1], [10] | 否 | 20261111212035-D-b7326b2f98 | |
| 7 | s07_fig_zh | figure | zh | 哈里斯鹰优化算法（HHO）的各个阶段是什么样的？ | 哈里斯鹰优化算法（HHO）是一种基于种群的元启发式算法，其灵感来自哈里斯鹰的合作捕猎策略，模拟捕食者与猎物之间的动态交互 [1]。该算法经历三个主要阶段：(1) 探索、(2) 由猎物逃逸能量主导的过渡、(3) 包含多种围攻策略的开发 [1]。  在探索阶段，鹰通过相对于随机个体或种群均值调整自身位置来多样化搜索，从而在随机探索与集体智能之间取得平衡 [1]。  过渡机制由猎物的逃逸能量驱动，该能量随迭代次数线性下降；较高的绝对能量值会鼓励探索，而较低的值则触发开发阶段 [1]。  在开发阶段，鹰根据猎物的能量和逃脱机会，从四种围攻战术中选择其一：软围攻、硬围攻、带渐进俯冲的软围攻，以及带渐进俯 | [1] | 否 | 20261111212105-D-f76be31621 | |
| 8 | s08_fig_en | figure | en | What are the various stages of Harris hawks optimization shown in the paper? | According to the paper, Harris Hawks Optimization (HHO) proceeds through **three main stages**: (1) exploration, (2) transition governed by prey escape energy, and (3) exploitation with multiple besiege strategies [1].  Details of each stage:  1. **Exploration stage**: Hawks diversify their search b | [1], [2] | 否 | 20261111212146-D-4b126b098d | |
| 9 | s09_fig_zh | figure | zh | 压力容器设计问题的示意图里包含哪些设计变量？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212205-D-47cc2f892b | |
| 10 | s10_fig_en | figure | en | What does the overview of the two-stage paradigm in the LLM overconfidence paper depict? | The overview (Fig. 1) depicts the paper's controlled experimental paradigm, termed the two-stage paradigm, which was developed to test how LLMs update their confidence and decide whether to change their answers when presented with external advice [2].  Specifically, it shows:  - **First stage (panel | [2], [1] | 否 | 20261111212254-D-99cb74d72a | |
| 11 | s11_fig_zh | figure | zh | KAN 与 MLP 的基本单元有什么区别？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212328-D-e96b6d0b7f | |
| 12 | s12_table_zh | table | zh | 在预选择策略的对比研究中，哪种预选择策略表现最好？ | 在三种预选择策略（RPS、CPS、RCPS）的对比研究中，**RCPS（基于关系对的分类预选择策略）表现最好**。  具体依据如下：  1. 离线实验的对比结果表明，RCPS 在三种策略中取得了最高的预测准确率 [14]。 2. 在将三种策略集成到 CoDE 算法的实验中，在 F1–F3（n=5）和 F1–F4（n=10）测试问题上，CoDE with RCPS 的表现优于 CoDE with CPS 和 CoDE with RPS [7]。 3. 在 YLL 测试集的统计结果中，RCPS-Bayes 的平均排名为 1.42，是所有六种方法中排名最好的（RCPS-Ada 为 2.12，也优于  | [14], [7], [20], [12] | 否 | 20261111212342-D-914526dcf8 | |
| 13 | s13_table_en | table | en | Which preselection strategy achieves the best performance in the comparison study? | **RCPS (relationship classification-based preselection)** achieves the best performance in the comparison study.  - The paper's abstract states that the experimental results suggest that on two sets of test suites, RCPS outperforms the comparison preselection strategies [10]. - In the direct compari | [10], [5], [6], [9] | 否 | 20261111212410-D-182491744b | |
| 14 | s14_table_zh | table | zh | bQDEHHO 在 CEC2017 上的参数敏感性实验是怎么设置的？ | 根据 Source 中的描述，该参数敏感性实验的设置如下：  - **可调参数的选择**：实验将 Q-table 更新中使用的学习率 α 和折扣因子 γ 作为主要可调超参数 [3]。 - **参数组合方式**：两个 Q-table 采用相互独立的 (α, γ) 设置进行对比 [3]。 - **配置数量**：如 Table 1 所示，共评估了九组候选参数配置，结果表中对应 Group_1 至 Group_9 [3][5]。 - **测试平台与考察指标**：实验在 CEC2017 基准测试套件上进行，用于评估不同 (α, γ) 设置对收敛速度、最优解质量和全局搜索能力的影响 [3]。 - **结果 | [3], [5], [1], [6], [8], [9] | 否 | 20261111212437-D-9cc3d77a85 | |
| 15 | s15_table_en | table | en | How many publications were found for decision tree research in the survey's literature search? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212522-D-524a96f3a7 | |
| 16 | s16_table_zh | table | zh | 描述性统计方法一览表里对位置和尺度的度量包含哪些？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212536-D-44af48b634 | |
| 17 | s17_unans_zh | unanswerable | zh | 2026 年最新的图像分割阈值方法是哪一种？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212552-D-38658bdab1 | |
| 18 | s18_unans_en | unanswerable | en | Who won the Turing Award in 2025? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212606-D-9a21b3cb2d | |
| 19 | s19_unans_zh | unanswerable | zh | 怎样用 Python 实现一个红黑树？请给出完整代码。 | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212620-D-90ebe7fefd | |
| 20 | s20_unans_en | unanswerable | en | What is the price of the commercial license for the Bayesian Assistant software? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111212633-D-79d954c316 | |

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
| 15 | s15_table_en | 7335e03ac56b Fig. 2 Number of publications...（检索统计图）+ Inclusion criteria 节；若证据在图，判定时按图表题口径 | |
| 16 | s16_table_zh | 69b72d2b0341 Table 3 Methods for descriptive statistics: Measures for location and scale（表格） | |
| 17 | s17_unans_zh | 语料为 2024-2026 前的历史论文集合，且无'2026 最新'类比较——应拒绝 | |
| 18 | s18_unans_en | 语料无关——应拒绝 | |
| 19 | s19_unans_zh | 语料是算法应用论文，无红黑树实现代码——应拒绝 | |
| 20 | s20_unans_en | 6ebe216067e3 是研究论文，无商业化定价信息——应拒绝 | |
