# M3 冒烟验收报告——D 档

- 生成时间：2026-11-11 21:06:35
- 题集：smoke_queries.json（vm3-smoke-v1，20 题）
- 判定规则：可回答题人工对照 gold_hint 判通过/失败；不可回答题以 refused=True 为通过；
- 验收线：通过率 ≥80%（≥16/20）；不可回答拒绝 ≥3/4；可回答误拒 ≤1（m3-runbook §1）

| # | q_id | 类型 | 语言 | 问题 | 答案（截 300 字） | 引用 | 弃答 | trace | 通过/失败 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | s01_text_zh | text | zh | Kapur 方法和 Otsu 方法分别是用来做什么的？ | 根据 Source 内容，Kapur 方法和 Otsu 方法都是用于**图像分割中的阈值分割**的方法，具体如下：  1. **双层阈值分割**：Kapur 和 Otsu 方法已被证明是图像分割中双层阈值分割的高效方法 [1]。  2. **可扩展至多级阈值分割**：这两种方法都可以很容易地扩展到多级阈值分割问题，但由于计算时间随阈值数量呈指数增长，在确定最优阈值方面效率较低 [2]；当扩展到多级阈值分割时，计算时间会随阈值数量呈指数增长，从而限制了多级阈值分割的应用 [1]。  3. **作为确定最优阈值的准则（目标函数）**：Otsu 和 Kapur 属于非参数方法，基于给定的准则以最优方 | [1], [2], [4], [8] | 否 | 20261111210635-D-17e6578ab7 | |
| 2 | s02_text_en | text | en | What is the ε-greedy implementation used for in the Q-learning driven DE algorithm? | In the Q-learning driven DE algorithm (QDEHHO), the ε-greedy implementation serves the following purposes:  1. **Scheduling strategy and parameter selection**: Both levels of the two-level Q-learning architecture apply an ε-greedy scheduling rule — the method-level Q-table uses it to select among fo | [1], [10] | 否 | 20261111210657-D-19f33fbc89 | |
| 3 | s03_text_zh | text | zh | 深度学习和传统机器学习的区别是什么？ | 根据所给文献，深度学习（DL）与传统机器学习（ML）的区别主要体现在以下几个方面：  1. **从属关系**：深度学习是机器学习的一个子集，其灵感来源于人脑的信息处理模式 [2]。  2. **特征处理方式（最核心的区别）**：使用传统 ML 技术完成分类任务需要多个顺序步骤，即预处理、特征提取、特征选择、学习和分类，且特征选择对 ML 技术的性能影响很大，有偏差的特征选择可能导致类别之间的错误判别 [2]；相反，DL 能够针对多种任务自动化地学习特征集，使学习和分类可以“一步完成”（single shot）[2]。传统 ML 算法的有效性高度依赖于输入数据表示的完整性，因此多年来特征工程（从 | [2], [5], [11], [15], [1] | 否 | 20261111210727-D-8d5bc3610e | |
| 4 | s04_text_en | text | en | What are the differences between deep learning and traditional machine learning? | Based on the sources, the main differences between deep learning (DL) and traditional machine learning (ML) are:  1. **Relationship and architecture**: DL is a subset of ML, inspired by the information processing patterns of the human brain, and is designed using numerous layers of algorithms (artif | [3], [12], [6], [9], [1], [10] | 否 | 20261111210810-D-e87d308a0e | |
| 5 | s05_text_zh | text | zh | 什么是贝叶斯教学（Bayesian teaching）？它如何帮助大语言模型做概率推理？ | ## 什么是贝叶斯教学（Bayesian teaching）  贝叶斯教学是论文《Bayesian teaching enables probabilistic reasoning in large language models》中提出的一种方法，其核心是一种监督微调（supervised fine-tuning）技术，用来教大语言模型模仿“规范性贝叶斯模型”（normative Bayesian model）的预测 [9]。其理论依据是：贝叶斯推断框架给出了智能体在接收新信息时更新信念的最优方式 [7]。  具体做法上，以航班推荐任务为例——该任务要求助手在多轮交互中从用户的选择中推断其偏 | [9], [7], [6], [2], [10], [4], [14] | 否 | 20261111210847-D-578915b63d | |
| 6 | s06_text_en | text | en | According to the STRATOS initiative, what is IDA (initial data analysis) and why does it matter? | ## What is IDA?  According to the STRATOS initiative, initial data analysis (IDA) is an important first step in every data analysis, and it can be particularly challenging in high-dimensional data (HDD) settings [2]. IDA is a term for all steps of data inspection and screening that take place after  | [2], [16], [5], [1], [10], [7] | 否 | 20261111210939-D-b7326b2f98 | |
| 7 | s07_fig_zh | figure | zh | 哈里斯鹰优化算法（HHO）的各个阶段是什么样的？ | 哈里斯鹰优化算法（HHO）是一种基于种群的元启发式算法，其灵感来自哈里斯鹰的合作捕猎策略，模拟捕食者与猎物之间的动态交互 [1]。  该算法主要经历三个阶段：(1) 探索，(2) 由猎物逃逸能量主导的过渡，(3) 采用多种围攻策略的开发 [1]。  **探索阶段**：鹰通过相对随机个体或种群均值来调整自身位置，从而使搜索多样化，在随机探索与集体智能之间取得平衡 [1]。  **过渡机制**：由猎物的逃逸能量驱动，该能量随迭代次数线性下降；当能量绝对值较高时鼓励探索，而较低时则触发开发阶段 [1]。  **开发阶段**：鹰根据猎物的能量和逃脱机会，采用四种围攻战术之一——软围攻、硬围攻、带渐进俯 | [1], [18] | 否 | 20261111211015-D-f76be31621 | |
| 8 | s08_fig_en | figure | en | What are the various stages of Harris hawks optimization shown in the paper? | According to the paper, Harris Hawks Optimization (HHO) proceeds through **three main stages** [1]:  1. **Exploration** – In this stage, hawks diversify their search by adjusting positions relative to random individuals or the population mean, balancing stochastic exploration with collective intelli | [1] | 否 | 20261111211056-D-4b126b098d | |
| 9 | s09_fig_zh | figure | zh | 压力容器设计问题的示意图里包含哪些设计变量？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211119-D-47cc2f892b | |
| 10 | s10_fig_en | figure | en | What does the overview of the two-stage paradigm in the LLM overconfidence paper depict? | The overview (Fig. 1) depicts the two-stage paradigm, a controlled experimental design developed to test how LLMs update their confidence and decide whether to change their answers when presented with external advice [2]. In the first stage (panel a), the 'answering' LLM (shown in blue) chooses an a | [2], [1] | 否 | 20261111211133-D-99cb74d72a | |
| 11 | s11_fig_zh | figure | zh | KAN 与 MLP 的基本单元有什么区别？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211207-D-e96b6d0b7f | |
| 12 | s12_table_zh | table | zh | 在预选择策略的对比研究中，哪种预选择策略表现最好？ | 在三种预选择策略（RPS、CPS、RCPS）的对比研究中，**RCPS（基于关系对的分类预选择策略）表现最好**。  具体依据如下：  - 实验结果表明，在 LZG 测试集上，CoDE with RCPS 的表现优于 CoDE with CPS 和 CoDE with RPS [7]。 - 在 YLL 测试集的统计结果中，RCPS-Bayes 的平均排名为 1.42，RCPS-Ada 为 2.12，均明显优于 RPS 和 CPS 的各种模型组合 [20]。 - 文章结论部分明确指出，对比结果显示 RCPS 在三种策略中取得了最高的预测准确率 [14]。 - 此外，研究还发现基于二元关系数据的分 | [7], [20], [14], [12] | 否 | 20261111211222-D-914526dcf8 | |
| 13 | s13_table_en | table | en | Which preselection strategy achieves the best performance in the comparison study? | **RCPS (relationship classification-based preselection)** achieves the best performance in the comparison study.  Supporting evidence from the sources:  - The paper's abstract states that "on two sets of test suits, RCPS outperforms the comparison preselection strategies" [10]. - In the direct compa | [10], [5], [6], [9], [7] | 否 | 20261111211253-D-182491744b | |
| 14 | s14_table_zh | table | zh | bQDEHHO 在 CEC2017 上的参数敏感性实验是怎么设置的？ | 根据文档，该参数敏感性实验（论文 4.2.1 节）的设置如下：  - **可调参数的选择**：实验将 Q-table 更新中使用的学习率 α 和折扣因子 γ 作为主要可调超参数 [3]。 - **参数组合方式**：两个 Q-table 采用相互独立的 (α, γ) 设置进行对比 [3]。 - **配置数量**：如 Table 1 所示，共评估了九组候选参数配置，对应结果表中的 Group_1 至 Group_9 [3][5]。 - **测试平台与考察目标**：实验在 CEC2017 基准测试套件上进行，用于评估不同 (α, γ) 设置对收敛速度、最优解质量和全局搜索能力的影响 [3]。 - * | [3], [5], [6], [8], [9], [1], [12] | 否 | 20261111211327-D-9cc3d77a85 | |
| 15 | s15_table_en | table | en | How many publications were found for decision tree research in the survey's literature search? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211414-D-524a96f3a7 | |
| 16 | s16_table_zh | table | zh | 描述性统计方法一览表里对位置和尺度的度量包含哪些？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211428-D-44af48b634 | |
| 17 | s17_unans_zh | unanswerable | zh | 2026 年最新的图像分割阈值方法是哪一种？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211443-D-38658bdab1 | |
| 18 | s18_unans_en | unanswerable | en | Who won the Turing Award in 2025? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211502-D-9a21b3cb2d | |
| 19 | s19_unans_zh | unanswerable | zh | 怎样用 Python 实现一个红黑树？请给出完整代码。 | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211516-D-90ebe7fefd | |
| 20 | s20_unans_en | unanswerable | en | What is the price of the commercial license for the Bayesian Assistant software? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111211530-D-79d954c316 | |

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
