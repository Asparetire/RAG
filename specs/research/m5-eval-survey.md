# DocLens M5 评测·公开基准与指标方法学调研

> 状态：**v1.0（源码/论文级核实）**——2026-11-12。动机：用户要求评测"不能玩具、要专业量化"——调研公开基准数据集与业界评测框架口径，把 M5 从"自测自语"升级为**三层混合**：自建域内题集（归因）+ 公开学术基准子集（外部效度）+ 业界标准指标口径（横向可比）。
> 调研线：K（公开基准数据集，双子代理之一）+ L（评测框架方法学）。网络备注：web_search 全程 402；arxiv.org/ir-measur.es/docs.ragas.io 可直抓，github raw 经 ghfast.top，HF 在本环境不可达（数据集 id 未直核）。

## 1. K 线：公开基准数据集（按契合度）

### 1.1 QASPER——契合度最高（主外部基准候选）[K1][K2]
- NLP 论文全文 QA：5,049 题/1,585 篇 arXiv 论文（LaTeX 解析全文+Semantic Scholar 爬取图表）；test 1,451 题按论文切分。
- 出题者只读标题+摘要、答题者读全文——**题目天然"需要读全文才能答"**，无伪题问题。
- 答案四型：抽取 51.8%/抽象 24.2%/是否 13.9%/**不可答 10.2%**；证据型：文本 81.6%/**图表 11.6%**/无证据 12.8%；55.5% 需跨多段证据。
- 指标：Answer-F1（SQuAD span-F1，多参考取 max）+ Evidence-F1；人类下界 60.9/71.6。**原论文基线因多模态困难直接剔除 13% 图表证据题——正是 DocLens 的发挥空间**。
- 工程：test 集按论文取题+arXiv 抓 PDF（LaTeX 源对 MinerU 友好）+paper id 映射+复用官方 F1 口径——**约 1–2 天**。
- 〔未核实〕官方页 allenai.org/data/qasper 本环境 403；HF allenai/qasper 不可达；数据许可需落地时确认。

### 1.2 BEIR/MTEB——检索层旁测 [K3][K4][K5]
- BEIR 18 数据集零样本检索套件（zip 直链/pip 可装）；学术子集：SciFact 300 查询/5K 语料、NFCorpus 323/3.6K；主指标 nDCG@10。
- corpus 是摘要/段落**非 PDF 全文**——不能整集喂入，但可挂官方 corpus+qrels 跑自家检索器（dense/BM25/重排）**对标公开榜**——零解析成本、零 LLM 成本、可复现。

### 1.3 其他
- **MultiHop-RAG**：2,556 题证据跨 2–4 文档（英文新闻库，非论文）——只借"跨文档合成"难度分层思想 [K6][K7]。
- **RGB**：RAG 诊断四测试床（噪声鲁棒/负拒绝/信息整合/反事实鲁棒，AAAI 2024）——**负面维度设计直接借鉴**（对应自建不可答/反事实题）[K8]。
- **CRUD-RAG**：中文，语料不匹配；借 RAGQuestEval 思想 [K9][K10]。
- **DocVQA/ChartQA/PlotQA**：单页图像 VQA 无检索环节——不作主基准 [K11][K12][K13][K14]。
- **FlashRAG**（WWW 2025）：38 基准/16 方法权威索引，含 QASPER——业界选型佐证 [K15]。

## 2. L 线：指标口径与方法学（全部源码/论文级核实）

### 2.1 RAGAS 四指标——可零依赖自实现（每指标 1–2 次 LLM+算术）[L1]–[L5]
- **faithfulness**：答案→LLM 拆原子陈述→逐条 NLI 判"能否从被引上下文推出"→可推出/总数。无需参考答案。
- **answer relevancy**：LLM 从答案反向生成 3 个问题→与原问题嵌入余弦均值；全回避式判 0。
- **context precision**：逐检索块判"对得出答案是否有用"→**AP 口径**（前缀命中率均值，非 nDCG）。
- **context recall**：参考答案逐句判"能否归因到检索上下文"→可归因/总数。需参考答案。
- 纯规则/ID 变体存在；版本更名有迁移指南。

### 2.2 ALCE 引用评测 [L6][L7]
- **citation recall**：答案按句切分，该句全部 [n] 文档拼接为 passage，NLI 判蕴含→被支持句占比。
- **citation precision**：多引用且联合被支持的句做**必要性检验**——逐引用单独判，去掉后仍蕴含=过度引用(0)——Σ必要/总引用。
- 对齐：DocLens 的被引 chunk=ALCE 的 doc（标题+正文）逐条套用；中文切句需自备（NLTK 是英文规则）。

### 2.3 检索指标权威口径（ir-measures/pytrec_eval）[L8]
- **recall@k 分母=全部相关数（不截断到 k）**；"top-k 命中与否"叫 **Success@k**——常见混用，M5 须显式声明。
- **nDCG@10**：pytrec_eval 默认 dcg='log2'（Σrel/log₂(i+1)），gdeval 用 exp-log² 变体——**报告须注明公式**；原始出处 Järvelin & Kekäläinen TOIS 2002。
- **MRR**：首个相关文档位次倒数（可带 cutoff）。

### 2.4 judge 校准 [L9][L11][L13]
- MT-Bench：GPT-4 级 judge 与人工一致率 >80%（≈人与人）；三类偏差（位置/冗长/自偏好）及缓解（交换候选顺序）。
- ARES：轻量 judge+数百条人工标注+PPI 置信区间——校准范式。
- 惯例：二值 verdict+reason（可审计、可算 kappa）；**judge 与被评模型分离**。

### 2.5 统计检验 [L10][L11]
- Dror et al.（ACL 2018）：成对二元→McNemar；连续分数→配对 t/bootstrap；不报显著性的单点比较是评审批评点。
- DocLens 已计划的 McNemar+bootstrap（按题重采样 1000 次/95% CI）与惯例吻合。

## 3. 修订后 M5 方案（三层混合）

| 层 | 内容 | 规模 | 测什么 | 成本 |
|---|---|---|---|---|
| L1 自建域内题集 | 原 165 题方案+RGB 负面维度（噪声/反事实 20 题） | ~185 题 | 端到端表现+分题型+归因 F0–F6 | 出题 LLM+人审 |
| L2 公开基准子集 | **QASPER test/val 子集**（多段文本/图表证据/不可答≈8:1.5:1 分层抽样）+ **BEIR SciFact+NFCorpus 检索旁测** | QASPER 60–100 题；BEIR ~600 查询 | 外部效度：Answer-F1/Evidence-F1/拒答准确率；检索层 nDCG@10 对标公开榜 | 论文抓取+解析 1–2 天工程 |
| L3 指标口径升级 | 检索：recall（TREC 分母声明）+Success@k+nDCG@10（注明公式）+MRR+RAGAS context_precision；生成：Answer-F1+**RAGAS faithfulness（自实现）**+answer relevancy+**ALCE 引用 recall/precision**；拒答：准确率+误拒率；统计：McNemar+bootstrap 95% CI | 全指标 | 与业界对话、横向可比 | NLI/relevancy 用 ctx_model（deepseek-v4-flash，便宜） |

- judge 校准纪律：judge（ctx_model）与生成模型分离、二值 verdict+reason、抽样 50 题人工对齐（目标 >80% 一致率）。
- 成本量级：QASPER 100 题×(1 生成+~10 judge/NLI) ≈ 1100 次 LLM 调用（ctx_model 计费便宜）+自建题集出题一次性成本。跑批前方舟额度预检。
- 工程增量：QASPER 接入 1–2 天；faithfulness/引用评测自实现 1 天；其余复用 M3/M4 资产（--profile/trace/契约测试经验）。

## 4. 来源清单

| 线 | 来源 |
|---|---|
| K 线 | [K1][K2] arxiv 2105.03011（QASPER 论文+HTML 全文：规模/类型占比/F1 口径/人类下界/13% 图表题弃权）；[K3][K4] arxiv 2104.08663+beir-cellar/beir README（18 数据集/直链/学术子集表）；[K5][K12][K13][K15] export.arxiv.org（MTEB 2210.07316/ChartQA 2203.10244/PlotQA 1909.00997/FlashRAG 2405.13576）；[K6][K7] arxiv 2401.15391+MultiHop-RAG repo；[K8] arxiv 2309.01431（RGB）；[K9][K10] arxiv 2401.17043+CRUD_RAG repo；[K11][K14] DocVQA 2007.00398（注意常见流传编号 2007.00387 系错误）/MP-DocVQA 2212.05935 |
| L 线 | [L1]–[L4] ragas main 四指标源码（_faithfulness/_context_precision/_context_recall/_answer_relevance.py，经 ghfast 抓 raw）；[L5] docs.ragas.io 指标页；[L6] Princeton-nlp/ALCE eval.py（AutoAIS/citation rec/prec 算法）；[L7] ALCE 仓库结构；[L8] ir-measur.es measures 页（R/Success/RR/nDCG 定义 NOTE+公式参数+Järvelin 引用）；[L9] arxiv 2306.05685（MT-Bench）；[L10] aclanthology P18-1128（Dror 显著性协议）；[L11] arxiv 2311.09476（ARES）；[L12] arxiv 2408.08067（RAGChecker）；[L13] trulens.org RAG Triad；[L14] confident-ai/deepeval |

> 〔未核实〕QASPER 许可与 HF 数据卡（本环境 HF 不可达）、FastGPT 全文细节、BEIR 各子集许可、MT-Bench 之外的 judge 校准文献。正确 arXiv 号备忘：DocVQA=2007.00398、ChartQA=2203.10244（流传的错误编号勿引用）。
