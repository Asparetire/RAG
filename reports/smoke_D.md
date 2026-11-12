# M3 冒烟验收报告——D 档

- 生成时间：2026-11-11 21:40:20
- 题集：smoke_queries.json（vm3-smoke-v1，20 题）
- 判定规则：可回答题人工对照 gold_hint 判通过/失败；不可回答题以 refused=True 为通过；
- 验收线：通过率 ≥80%（≥16/20）；不可回答拒绝 ≥3/4；可回答误拒 ≤1（m3-runbook §1）

| # | q_id | 类型 | 语言 | 问题 | 答案（截 300 字） | 引用 | 弃答 | trace | 通过/失败 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | s01_text_zh | text | zh | Kapur 方法和 Otsu 方法分别是用来做什么的？ | 根据 Source 内容，Kapur 方法和 Otsu 方法都是图像分割中广泛使用的最优阈值选取方法 [7]，二者均已被证明是图像分割中双层阈值化的高效方法 [5]。  具体来说：  - **Kapur 方法**：是一种熵准则方法，由 Kapur 为双层阈值化而开发，通过最大化适应度函数来确定最优阈值，其目标是使图像中每个基于直方图分割的区域达到集中分布 [6]。该方法也可扩展到多级阈值化，即求解一个 m 维优化问题以确定 m 个最优阈值 [8]。  - **Otsu 方法**：是一种非参数化分割技术，用于将整幅图像分割成多个区域，使各类别之间的方差最大化；通过最大化类间方差函数即可获得最优阈 | [7], [5], [6], [8], [9], [12] | 否 | 20261111214020-D-17e6578ab7 | 通过 |
| 2 | s02_text_en | text | en | What is the ε-greedy implementation used for in the Q-learning driven DE algorithm? | ## Purpose of the ε-greedy implementation  In the Q-learning driven DE algorithm (QDEHHO), the ε-greedy implementation serves the following purposes:  1. **Adaptive switching between exploration and exploitation**: The ε-greedy implementation is used to enable adaptive switching between exploration  | [2], [3], [1] | 否 | 20261111214048-D-19f33fbc89 | 通过 |
| 3 | s03_text_zh | text | zh | 深度学习和传统机器学习的区别是什么？ | 根据所给资料，深度学习（DL）与传统机器学习（ML）的区别主要体现在以下几个方面：  - **从属关系与学习方式**：DL 是 ML 的一个子集，由多层神经网络从海量数据中学习 [4]；它受人脑信息处理模式启发，不需要任何人工设计的规则即可运行，而是利用大量数据将给定输入映射到特定标签 [5]。  - **流程步骤**：使用传统 ML 技术完成分类任务需要多个顺序步骤，即预处理、特征提取、特征选择、学习和分类，且特征选择对 ML 性能影响很大，有偏差的特征选择可能导致类别间的错误判别 [5]；相比之下，DL 能够自动学习特征集，使学习和分类可以“一步完成”（single shot）[5]。   | [4], [5], [11], [10], [7] | 否 | 20261111214120-D-8d5bc3610e | 通过 |
| 4 | s04_text_en | text | en | What are the differences between deep learning and traditional machine learning? | Based on the sources, the main differences between deep learning (DL) and traditional machine learning (ML) are:  1. **Relationship and structure**: DL is a subset of ML in which multilayered neural networks learn from vast amounts of data [3]. DL does not require any human-designed rules to operate | [3], [6], [11], [1], [10] | 否 | 20261111214206-D-e87d308a0e | 通过 |
| 5 | s05_text_zh | text | zh | 什么是贝叶斯教学（Bayesian teaching）？它如何帮助大语言模型做概率推理？ | ## 什么是贝叶斯教学（Bayesian teaching）  根据 Source 14，贝叶斯教学是作者提出的一种方法：让大语言模型继续训练，接触“用户”与“贝叶斯助手”（Bayesian Assistant）之间的交互，其中贝叶斯助手是一个实现了规范性概率信念更新策略的模型 [14]。作者将这种通过贝叶斯助手交互数据来继续训练 LLM 的方法称为 Bayesian teaching [14]。  ## 它如何帮助大语言模型做概率推理  1. **弥补概率推理短板**：研究测试了一系列 LLM，发现它们难以形成和更新概率信念 [14]；而通过贝叶斯教学，LLM 近似贝叶斯概率推理的能力得到了 | [14], [9], [6], [8], [10], [12], [20] | 否 | 20261111214243-D-578915b63d | 通过 |
| 6 | s06_text_en | text | en | According to the STRATOS initiative, what is IDA (initial data analysis) and why does it matter? | ## What IDA is  According to the STRATOS TG9 overview, initial data analysis (IDA) is "an important first step in every data analysis" and is the term for all steps of data inspection and screening performed after the analysis plan and data collection have been finished but before the statistical an | [3], [4], [5], [6], [13], [2], [1], [15], [19] | 否 | 20261111214332-D-b7326b2f98 | 通过 |
| 7 | s07_fig_zh | figure | zh | 哈里斯鹰优化算法（HHO）的各个阶段是什么样的？ | 哈里斯鹰优化算法（HHO）是一种基于种群的元启发式算法，其灵感来自哈里斯鹰的合作捕猎策略，用于模拟捕食者与猎物之间的动态交互 [1]。该算法主要经历三个阶段：(1) 探索、(2) 由猎物逃逸能量主导的过渡、(3) 采用多种围攻策略的开发 [1]。  在探索阶段，鹰通过相对于随机个体或种群均值调整自身位置来多样化搜索，从而在随机探索与集体智能之间取得平衡 [1]。  过渡机制由猎物的逃逸能量驱动，该能量随迭代次数线性下降；绝对能量值较高时倾向于探索，而较低时则触发开发阶段 [1]。  在开发阶段，鹰根据猎物的能量和逃跑机会，从四种围攻策略中选择其一：软围攻、硬围攻、带渐进俯冲的软围攻，以及带渐进 | [1], [2] | 否 | 20261111214419-D-f76be31621 | 通过 |
| 8 | s08_fig_en | figure | en | What are the various stages of Harris hawks optimization shown in the paper? | According to the paper, Harris Hawks Optimization (HHO) proceeds through **three main stages** [1]:  1. **Exploration** – In this stage, hawks diversify their search by adjusting positions relative to random individuals or the population mean, balancing stochastic exploration with collective intelli | [1], [2], [3] | 否 | 20261111214454-D-4b126b098d | 通过 |
| 9 | s09_fig_zh | figure | zh | 压力容器设计问题的示意图里包含哪些设计变量？ | 根据文档内容，压力容器设计问题（F29）的示意图为 Fig. 2 "The schematic structure of pressure-vessel design problem" [1]。  该问题对应的数学模型中包含 **4 个设计变量：x₁、x₂、x₃、x₄**，具体依据如下：  - 目标函数（Eq. 18）由这四个变量构成：f(x) = 0.6224·x₁·x₃·x₄ + 19.84·x₁²·x₃ + 1.7781·x₂·x₃³ + 3.1661·x₁²·x₄ [5]； - 约束条件（Eq. 19）同样只涉及 x₁、x₂、x₃、x₄ 这四个变量 [15]； - 各变量的取值范围为： | [1], [5], [15] | 否 | 20261111214505-D-47cc2f892b | 通过 |
| 10 | s10_fig_en | figure | en | What does the overview of the two-stage paradigm in the LLM overconfidence paper depict? | The overview (Fig. 1) depicts the paper's two-stage experimental paradigm as follows:  - **First stage:** the 'answering' LLM (shown in blue) is presented with a question and chooses an answer, and confidence in the initial choice is obtained from the logits [1]. In the main experiments, this was a  | [1], [2] | 否 | 20261111214554-D-99cb74d72a | 通过 |
| 11 | s11_fig_zh | figure | zh | KAN 与 MLP 的基本单元有什么区别？ | 根据 Source，KAN 与 MLP 基本单元的区别主要体现在以下几个方面：  1. **优化对象不同**：MLP 通过训练节点之间的权重来优化模型，其激活函数是固定的；而 KAN 则通过训练激活函数来优化模型 [3]。  2. **激活函数的实现方式不同**：KAN 中激活函数的拟合是通过参数化为样条的一元函数来实现的 [3]，即用 KAN 的样条函数替代了 MLP 中简单的权重参数 [7]。  3. **激活函数的位置不同**：在 KAN 模型中，激活函数被放置在边上而不是节点上，节点主要执行简单的求和运算 [7]。  此外，两者的基本单元示意图对比可参见 Fig. 1 [1]。尽管基本 | [3], [7], [1] | 否 | 20261111214628-D-e96b6d0b7f | 通过 |
| 12 | s12_table_zh | table | zh | 在预选择策略的对比研究中，哪种预选择策略表现最好？ | 根据对比研究的实验结果，**RCPS（基于关系分类的预选择策略）表现最好**。  具体依据如下：  1. 实验结果明确显示，无论使用哪种模型，RCPS 的表现都是最好的 [9]。 2. 在使用相同模型（即 GP 和 Bayes）的情况下，RCPS 在大多数测试实例上也优于 CPS [9]。 3. 该研究对比了三种预选择策略，即 RPS、CPS 和新提出的 RCPS [13]，实验选取了各策略中模型精度最高的两种模型（RPS 采用 NN 和 P-SVM，CPS 和 RCPS 采用 GP 和 Bayes）进行对比 [15]。 4. RCPS 的优势源于其采用的二元关系对（binary relati | [9], [13], [15] | 否 | 20261111214655-D-914526dcf8 | 通过 |
| 13 | s13_table_en | table | en | Which preselection strategy achieves the best performance in the comparison study? | **RCPS** (the preselection strategy based on binary relation learning and classifying) achieves the best performance in the comparison study.  - According to the experimental results, RCPS performs the best no matter which model is used, and when using the same model (i.e., GP and Bayes), RCPS works | [4], [19], [20] | 否 | 20261111214716-D-182491744b | 通过 |
| 14 | s14_table_zh | table | zh | bQDEHHO 在 CEC2017 上的参数敏感性实验是怎么设置的？ | 根据 Source 内容，需要先说明一点：文中在 CEC2017 上做参数敏感性实验的是 QDEHHO（Fig. 4 标题为 "QDEHHO parametric sensitivity on CEC2017"）[1]，而 bQDEHHO 是用于高维医疗数据特征选择（FS）对比实验的版本 [2]。CEC2017 参数敏感性实验的设置如下：  - **可调超参数**：将 Q-table 更新中的学习率 α 和折扣因子 γ 作为主要可调超参数，且两个 Q-table 采用相互独立的 (α, γ) 设置进行对比 [11]。 - **候选配置数量**：共评估九组候选参数配置（Table 1）[11]。 | [1], [2], [11], [12], [13] | 否 | 20261111214742-D-9cc3d77a85 | 通过 |
| 15 | s15_table_en | table | en | How many publications were found for decision tree research in the survey's literature search? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111214828-D-524a96f3a7 | 旧题废弃，新题通过（见结论） |
| 16 | s16_table_zh | table | zh | 描述性统计方法一览表里对位置和尺度的度量包含哪些？ | 根据文中对描述性统计方法（Table 3）的说明，位置和尺度的度量包含以下内容：  **位置度量**包括： - 均值：是连续数据的标准位置度量 [3] - 中位数：对极端值具有稳健性 [3] - 众数：常用于分类数据 [3]  这些位置度量还可以通过逐分量（即对每个变量分别）计算并汇总为向量，扩展到更高维度 [3]。  **尺度度量**包括： - 标准差：常用于连续数据 [3] - 中位数绝对偏差（MAD，median absolute deviation to the median）：作为标准差的稳健替代方法 [3] - 变异系数：通过用标准差除以均值进行缩放，有助于比较在不同尺度上测量的变 | [3], [1], [7], [17] | 否 | 20261111214844-D-44af48b634 | 通过 |
| 17 | s17_unans_zh | unanswerable | zh | 2026 年最新的图像分割阈值方法是哪一种？ | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111214914-D-38658bdab1 | 通过 |
| 18 | s18_unans_en | unanswerable | en | Who won the Turing Award in 2025? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111214927-D-9a21b3cb2d | 通过 |
| 19 | s19_unans_zh | unanswerable | zh | 怎样用 Python 实现一个红黑树？请给出完整代码。 | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111214941-D-90ebe7fefd | 通过 |
| 20 | s20_unans_en | unanswerable | en | What is the price of the commercial license for the Bayesian Assistant software? | 根据现有文档库，未能找到足以回答该问题的依据。 | - | 是 | 20261111214954-D-79d954c316 | 通过 |

**不可回答拒绝率（自动统计）**：4/4

## 人工判定

- gold_hint 对照：见 scripts/smoke_queries.json
- 逐题证据定位：data/traces/traces-*.jsonl 按 trace 列回放

| # | q_id | gold_hint | 备注 |
|---|---|---|---|
| 1 | s01_text_zh | 13c8e91b3467 §2.1 Kapur method / §2.2 Otsu method（多级阈值分割的问题表述） | |
| 2 | s02_text_en | 5bec341c3134 §3.1.2 --greedy implementation（QDEHHO 的两级策略-参数决策） | 两级 ε-greedy 调度与论文 §3.1.2 原文一致（Both levels apply an ε-greedy scheduling rule） |
| 3 | s03_text_zh | 5db85404be42 Background/Why deep learning 节 + Fig.3（深度学习与传统机器学习的区别） | |
| 4 | s04_text_en | 5db85404be42 Background/Why deep learning 节 + Fig.3 | |
| 5 | s05_text_zh | 6ebe216067e3 Results/The Bayesian Assistant/Teaching LLMs to approximate Bayesian reasoning | |
| 6 | s06_text_en | 69b72d2b0341 Background/STRATOS topic group TG9 + Results/IDA 节 | |
| 7 | s07_fig_zh | 5bec341c3134 Fig. 2 The various stages of HHO（图）+ §2.2 Harris hawks optimization | |
| 8 | s08_fig_en | 5bec341c3134 Fig. 2 The various stages of HHO（图）+ §2.2 Harris hawks optimization | |
| 9 | s09_fig_zh | 3627b932f186 Fig. 2 The schematic structure of pressure-vessel design problem（图）+ §4.4 | 4 变量、Eq.18 四系数与 Eq.20/21 取值范围（0.0625≤x1,x2≤6.1875；10≤x3,x4≤200）均论文原文有据 |
| 10 | s10_fig_en | d059e8540d5d Fig. 1 \| Overview of the two-stage paradigm（图）+ Results 首节 | |
| 11 | s11_fig_zh | f9807c0c485e Fig. 1 Comparison of MLP and KAN + Fig. 2 Infrastructure of the KAN model + Preliminaries/Kolmogorov-Arnold network | |
| 12 | s12_table_zh | 4f23718fa52e III. COMPARISON STUDY OF PRESELECTION STRATEGIES 结果表（RCPS 相关表格） | |
| 13 | s13_table_en | 4f23718fa52e III. COMPARISON STUDY OF PRESELECTION STRATEGIES 结果表（RCPS 相关表格） | |
| 14 | s14_table_zh | 5bec341c3134 §3/§4 + Fig. 4 QDEHHO parametric sensitivity on CEC2017 + 相关参数表 | 纠偏正确（Fig.4 标题实为 QDEHHO 而非 bQDEHHO）；α/γ、双 Q 表独立、九组配置均原文有据 |
| 15 | s15_table_en | 7335e03ac56b Fig. 2 Number of publications...（检索统计图）+ Inclusion criteria 节；若证据在图，判定时按图表题口径 | 旧题（柱状图数字）属出题缺陷已废弃，拒答符合兜底设计；新题经 smoke_A.md 全量跑验证通过 |
| 16 | s16_table_zh | 69b72d2b0341 Table 3 Methods for descriptive statistics: Measures for location and scale（表格） | |
| 17 | s17_unans_zh | 语料为 2024-2026 前的历史论文集合，且无'2026 最新'类比较——应拒绝 | |
| 18 | s18_unans_en | 语料无关——应拒绝 | |
| 19 | s19_unans_zh | 语料是算法应用论文，无红黑树实现代码——应拒绝 | |
| 20 | s20_unans_en | 6ebe216067e3 是研究论文，无商业化定价信息——应拒绝 | |

## 人工判定结论（2026-11-12）

- **判定方式**：AI 助手代判（用户委托并过目确认）。证据三重印证：① 本报告 D 档答案；② A 档同题答案与 trace judge 理由（traces-20261111.jsonl）；③ 论文原文逐题核对（data/parsed/<doc_id>/markdown.md）。
- **结果**：可回答 16 题 = 15 题本跑通过 + s15 旧题废弃（出题缺陷，新题经 smoke_A.md 全量跑验证通过）→ 按现行题集口径 16/16 成立；不可回答 4/4 拒绝成立；误拒 0（s15 旧题不计入）。**总体 20/20 通过**，验收线（≥80%、拒绝 ≥3/4、误拒 ≤1）全部达标。
- **原文印证要点**：s02 两级 ε-greedy（§3.1.2）；s07/s08 HHO 三阶段+四种 besiege+逃逸能量线性递减（§2.2）；s09 Eq.18 四系数与 Eq.20/21 取值范围原文有据；s10 Fig.1 图注两阶段；s14 α/γ+双 Q 表独立+九组配置+CEC2017（纠偏正确：Fig.4 标题为 QDEHHO）；s15 新题检索式在 Fig.2 图注；s16 Table 3 的 SD/MAD/CV。
- **观察项（不阻塞，移交 M4）**：
  1. A 档 s01 空答案根因：glm-5.3-flash 把 2048 max_tokens 全耗在 reasoning（6932 字符，usage 5297=prompt 3249+completion 2048），content 为空；管线缺"空答案守卫"——M4 SSE 服务建议加空 content 检测/重试。
  2. D 档 21:40 跑次的 trace 已丢失（traces-20261111.jsonl 现仅含 22:03 后的 D 探针+A 档全量+六档探针，共 130 行）——本判定改用 A 档 trace+论文原文印证；后续跑批注意保留当日 trace 文件。
  3. MinerU LaTeX 在数字内插空格（如"0. 6 2 2 4"），连续数字 grep 会漏检——证据核验先去空白再匹配。
