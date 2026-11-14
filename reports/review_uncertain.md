# 待人工裁决队列（AI 复审 uncertain）

共 16 题——请逐题在 review 行标 `收录` / `弃用(原因)`。

## 第 1 题 [table] 13c8e91b3467

**题目**：根据 Table 1（BFHS 初始参数），Bacterial Foraging (BF) 部分中取值最大的参数和 Harmony Search (HS) 部分中取值最大的参数分别是什么？各自的取值是多少？

**参考答案**：BF 部分取值最大的参数是 Number of bacterium (s)，取值为 20；HS 部分取值最大的参数是 Number of improvisations (NI)，取值为 250。

**复审意见**：题目清晰且BF部分可验证，但证据表格未给出HS部分各参数的数值，无法确认HS最大参数及取值是否为NI=250。
(confidence 0.70)

**裁决**：

---

## 第 2 题 [noise] 13c8e91b3467

**题目**：在该混合图像分割算法中，为什么引入学习自动机（Learning Automata, LA）？它在算法中起什么作用？

**参考答案**：因为软计算类算法最大的问题是容易陷入局部最优。为解决这一关键问题，论文引入LA作为控制器，在两种优化方法（细菌觅食BF与和声搜索HS）之间进行切换。

**复审意见**：证据只提到软计算方法易陷入局部最优，但未出现LA及其作为BF/HS切换控制器的细节，参考答案与证据部分吻合但无法完全判定。
(confidence 0.75)

**裁决**：

---

## 第 3 题 [table] 4f23718fa52e

**题目**：在 fes=30 时，哪个模型在 F1、F2、F3、F4 四个实例上均排名第一（rank [1]）？并分别给出该模型在这四个实例上的平均准确率。

**参考答案**：GP 模型。其在 30 fes 时于四个实例上均排名第一，平均准确率分别为：F1=0.99、F2=0.90、F3=0.76、F4=0.98。

**复审意见**：证据中仅能核实 F1、F2、F3 三个实例在 fes=30 时 GP 排名第一，F4 行及其数据未在提供的证据中出现，因此 ref_answer 中 F4=0.98 和 GP 在 F4 排名第一无法完全核实。
(confidence 0.85)

**裁决**：

---

## 第 4 题 [table] 4f23718fa52e

**题目**：在 900 fes 时，F1、F2、F3、F4 四个实例上预选择准确率排名第一（rank [1]）的模型分别是什么？哪个模型在该阶段获得第一的次数最多？

**参考答案**：F1 上排名第一的是 RCPS-GP（0.93 [1]），F2 上是 RCPS-Bayes（0.52 [1]），F3 上是 RCPS-GP（0.94 [1]），F4 上是 RPS-P-SVM（0.48 [1]）；其中 RCPS-GP 获得第一的次数最多，共 2 次。

**复审意见**：证据表格只列出了F4在30 fes的数据，缺少900 fes行，无法核对F4上RPS-P-SVM排名第一及总次数统计。
(confidence 0.70)

**裁决**：

---

## 第 5 题 [text] 5db85404be42

**题目**：作者认为已有的深度学习综述存在什么不足，因此本篇综述采用了怎样的写作思路来弥补？另外，在梳理CNN架构的发展历程时，文章选取了哪两个网络作为叙述的起点和终点？

**参考答案**：以往的深度学习综述都只涉及该领域的某一个侧面，导致对其缺乏整体性的认识；因此作者采取更全面、整体（holistic）的视角，对深度学习最重要的方面进行更系统的回顾，为读者提供一个合适的起点以形成对DL的完整理解。在CNN架构演进部分，文章从AlexNet网络开始讲起，到高分辨率网络（High-Resolution network, HR.Net）结束。

**复审意见**：第一问的不足和整体视角在证据中有支持，但ref_answer中“更系统的回顾”“为读者提供合适起点”等表述在给出的证据原文中未直接出现，且证据1截断，无法完全确认；CNN起点终点部分明确。
(confidence 0.65)

**裁决**：

---

## 第 6 题 [table] 5db85404be42

**题目**：在表中所有由 Elsevier 出版的期刊中，IF 2019 最高的是哪本期刊？其 IF 2019 与 CiteScore 分别为多少？

**参考答案**：Pattern Recognition，其 IF 2019 为 7.196，CiteScore 为 13.1，是表中 Elsevier 出版期刊中 IF 2019 最高的。

**复审意见**：证据中表格只展示了部分行的IF和出版社，无法确认Pattern Recognition就是所有Elsevier出版期刊中IF 2019最高者，需人工核对完整表格。
(confidence 0.80)

**裁决**：

---

## 第 7 题 [table] 5db85404be42

**题目**：根据 Table 2，在所有使用 ImageNet 数据集的 CNN 模型中，错误率（Error rate）最低的是哪个模型？该模型的网络深度（Depth）是多少？

**参考答案**：Inception-V4 的错误率最低，为 3.08；其网络深度为 70 层。

**复审意见**：证据中的 Table 2 数据被截断，未包含 Inception-V4 的错误率和深度，无法确认参考答案与证据一致。
(confidence 0.80)

**裁决**：

---

## 第 8 题 [table] 5db85404be42

**题目**：表中用于人体动作检测（Human action detection）的数据集有哪些？其中类别数最多的是哪个数据集，类别数是多少？

**参考答案**：用于人体动作检测的数据集有两个：UCF-101 和 Kinetics。其中类别数最多的是 Kinetics，为 400 类（UCF-101 为 101 类）。

**复审意见**：证据原文仅明确UCF-101用于人体动作检测且为101类，Kinetics的类别数及应用列未在给定证据中显示，参考答案中关于Kinetics的信息无法从证据确认。
(confidence 0.80)

**裁决**：

---

## 第 9 题 [text] 69b72d2b0341

**题目**：这篇综述所说的"高维"具体指什么？作者对被研究的观测单位（"subject"）是如何界定的？另外请举出生物医学研究中两类典型的高维数据来源。

**参考答案**：这里的"高维"指的是与每个独立观测相关联的变量数目（即 p）非常大，其取值可以从几十一直到数百万，而变量极多的情形正是该文关注的重点。作者明确将"subject"作广义理解：它泛指独立的观测单位，不仅包括人或动物受试者，还包括由其衍生的生物样本，以及其他独立的实验或观察单元。生物医学领域高维数据的典型来源有两类：一是组学数据，例如覆盖基因组、蛋白质组或代谢组的海量测量指标；二是电子健康档案数据，即为每位患者记录的大量变量。

**复审意见**：题目清晰且答案与证据大体吻合，但关于subject的具体界定在证据原文截断处未完整呈现，无法完全确认ref_answer细节是否忠实于原文。
(confidence 0.75)

**裁决**：

---

## 第 10 题 [table] 69b72d2b0341

**题目**：根据 Table 1，Examples 列中哪些方法同时出现在 IDA2 和 EDA1 两行中？

**参考答案**：PCA 和 Biplot 同时出现在 IDA2 与 EDA1 的 Examples 中。

**复审意见**：题目明确，IDA2 的 Examples 中也确实有 PCA 和 Biplot，但提供的证据原文没有 EDA1 行的 Examples 内容，无法确认 ref_answer 是否与证据一致。
(confidence 0.85)

**裁决**：

---

## 第 11 题 [noise] 6ebe216067e3

**题目**：根据片段，与 oracle teaching 相比，Bayesian teaching 具有哪些优势？

**参考答案**：Bayesian teaching 带来更高的准确率，并且在实验重复之间的变异性更小；此外，Bayesian teaching 使 LLM 更接近贝叶斯推理，Bayesian-tuned LLM 的预测与 Bayesian Assistant 约 80% 的时间一致，显著高于原始 LLM 和 oracle-tuned LLM 的预测一致率。

**复审意见**：证据原文在关键处截断，参考答案中的80%一致率及对比信息无法从当前证据片段验证，需人工核对完整原文
(confidence 0.80)

**裁决**：

---

## 第 12 题 [text] 7335e03ac56b

**题目**：为多变量决策树寻找最优线性分割时，现有启发式策略可归纳为哪三大类？请每类各举一个代表性算法，并说明最早出现的优化类算法 CART-LC 后来被研究者指出了什么不足？

**参考答案**：三大类分别是：优化技术（代表算法如 CART-LC）、线性判别分析 LDA（代表算法如 FACT、CRUISE、QUEST、GUIDE、Sparse ADTrees、Fisher's ADTree 等）、以及受几何结构启发的启发式方法（代表算法如 GDT、HHCART）。CART-LC 采用确定性的爬山算法来诱导线性分割，虽然在类结构依赖于属性线性组合的任务上具有竞争力，但后续研究者认为这种确定性做法使其容易陷入低质量的局部最优。

**复审意见**：证据中三大类及代表算法均吻合，但关于 CART-LC 不足的原文在“so”处截断，无法完整核对 ref_answer 中的“易陷入低质量局部最优”这一句。
(confidence 0.60)

**裁决**：

---

## 第 13 题 [table] d059e8540d5d

**题目**：对比表中 'Reporting on sex and gender' 与 'Reporting on race, ethnicity, or other socially relevant groupings' 两行的要求：哪一行要求作者说明相关属性是基于自我报告还是被指定（self-reporting or assigned）的，哪一行要求作者解释所用分类变量的使用原因？

**参考答案**：'Reporting on sex and gender' 行要求说明 sex 和/或 gender 是基于自我报告还是被指定的，以及所用的方法；'Reporting on race, ethnicity, or other socially relevant groupings' 行则要求作者说明其在稿件中使用的社会性分类变量并解释使用原因。

**复审意见**：Sex/gender 行的要求可由证据确认，但 race/ethnicity 行的具体内容在证据中被截断，无法核实 ref_answer 中'解释使用原因'是否与原表一致。
(confidence 0.65)

**裁决**：

---

## 第 14 题 [table] d059e8540d5d

**题目**：在 Reporting Summary 的 Life sciences study design 五项披露要点（Sample size、Data exclusions、Replication、Randomization、Blinding）中，哪几项的说明文字明确出现了 "rationale"（理由）一词？并分别说明该词出现的具体情境。

**参考答案**：共有两项：Sample size（样本量）和 Data exclusions（数据剔除）。Sample size：在未进行样本量计算的情况下，需描述样本量如何确定，并提供样本量为何足够的理由；Data exclusions：若分析中有数据被剔除，需描述剔除情况及其背后的理由，并说明剔除标准是否为预先设定。其余三项（Replication、Randomization、Blinding）的说明中均未出现 rationale 一词。

**复审意见**：题目清晰且可见证据中 Sample size 与 Data exclusions 两处含 rationale，但证据中 Randomization 行不完整且 Blinding 行缺失，无法完全核实其余三项均未出现该词，需人工确认。
(confidence 0.75)

**裁决**：

---

## 第 15 题 [table] d059e8540d5d

**题目**：在行为与社会科学研究设计的报告要点表中，哪些条目允许作者在'该情况未发生/不适用'时直接声明即可（即提供 'state so' 或 'state that no…' 的简化选项）？请列出这些条目的名称。

**参考答案**：共有三个条目提供此类简化选项：Data exclusions（若无数据被剔除，直接说明即可）、Non-participation（若无参与者退出/拒绝参与，直接说明即可）、Randomization（若参与者未被分配到实验组，直接说明即可）。其余条目如 Sampling strategy、Data collection、Timing 均要求提供具体描述，无此类选项。

**复审意见**：题目清晰且答案唯一，但证据只列出了 Data exclusions/Non-participation/Randomization 的条目名称，未给出这三行的具体填报说明，无法从证据原文完全核实“state so”简化选项是否属实。
(confidence 0.75)

**裁决**：

---

## 第 16 题 [table] f9807c0c485e

**题目**：根据表中 Fold 1 至 Fold 7 的结果，KAN 在所有数据集上取得的最高精度值是多少？该值出现在哪个数据集的第几折？

**参考答案**：最高精度为 8.1116E-01（约 0.8112），出现在 Bupa_liver 数据集的 Fold 6（第 6 折）。

**复审意见**：题目和参考回答没有明显矛盾，但证据表格只展示到 Fold 4，无法核对 Fold 5–7 中 Bupa_liver Fold 6 的 8.1116E-01 是否为最高值，需人工对照完整表格确认。
(confidence 0.75)

**裁决**：

---

