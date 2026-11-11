# DocLens M3 检索+生成·同类项目调研笔记

> 状态：**v1.0（研究代理核实为主）**——三条调研线（混合检索与融合 / LLM 列表式重排 / 带据生成与 CLI）2026-11-11 由三个研究代理并行完成；当日 web_search 后端 HTTP 402 不可用，全部结论改经 web_fetch 直抓**官方文档站 + GitHub 官方仓库源码 + arXiv 原文**（raw 文件经 ghfast.top 代理；github.com 主站被本地网络策略阻断）。标注约定：〔已核实〕=代理亲自抓到原文；〔二手〕=工程共识无原文；〔未核实〕=抓不到、不作实施依据。关键决策数字建议抽查原文后作为最终依据。
> 用途：[m3-runbook](../plans/m3-runbook.md)（**待立项**）的方案佐证与修订输入，随 G1 确认门一并过目；财报泛化包与 M5 消融的参考。与 [eval-and-retrieval-survey](eval-and-retrieval-survey.md)（2026-11-04 方法级调研）互补——那份回答"**选什么方法**"，本笔记回答"**实现时同类项目踩过什么坑、怎么解**"。
> 约定：无标注判断为本项目自己的设计结论；带 [n] 的为已核实来源，编号见 §7。

## 0. 与项目规划的映射（本笔记如何进入 M3 runbook）

| 调研发现 | 对应决策 | 结论 |
|---|---|---|
| Qdrant 服务端 RRF 仅限单集合内（prefetch 挂单集合），DocLens 三路异构（Qdrant×2 + 本地 BM25）→ 客户端融合别无选择 | 3.1 hybrid.py | 印证路线 + 实现位置定稿（R1） |
| 每路召回量官方示例=20/路→融合 10（Qdrant）【1】；RRF k 三档并存：Qdrant 默认 k=2、原论文/Elastic/LlamaIndex k=60 | 3.1 参数 | 建议修订 R1（k=2 维持、k=60 对照位） |
| 图-图注联动去重**无块级先例**，主流（M3DocRAG/VisRAG）以"页"为检索单元天然合并图文【4】【5】 | 3.1 去重 | 建议修订 R2（"证据组"归并=页级聚合的块级等价物） |
| rank_bm25 分词完全由调用方负责、索引/查询两侧不一致=静默劣化【6】 | 3.1 BM25 | 建议修订 R3（tokenize 单例两侧共用 + 配对拍单测） |
| rank_bm25 无内置过滤，但 `get_batch_scores(query, doc_ids)` 子集打分可承担 kind 过滤【6】 | 3.1/3.5 kind 过滤 | 建议修订 R3（免建多份 BM25 索引） |
| 两后端各写一份 kind 过滤易口径漂移（消融结论失真） | 3.1/3.5 | 建议修订 R4（TIER_KINDS 单源映射 + 单测防线） |
| 查询向量缓存无强先例但与入库缓存同构 | 3.5 | 建议修订 R5（复用 t_embed_cache） |
| dense/BM25/融合分数均不可跨查询比较【1】【2】，"判官替代分数阈值"有论文先例（CRAG【8】/Self-RAG【9】） | 3.4 fallback | 印证已定双信号 + 建议修订 R6（不做全局分数阈值） |
| RankGPT 官方源码三级解析链（清洗→去重→越界过滤+缺失补尾）= 列表式重排解析的标准兜底【11】 | 3.2 rerank.py | 建议修订 R7（原样移植 + 四类单测） |
| 重排实践数字：窗口 20、每篇截 300 词（源码）【11】；Anthropic 150→20【13】；级联省钱（大模型只重排小模型 top-30）【12】 | 3.2 预算 | 建议修订 R8（输入截 30 保 D6 骨架；pro 档级联） |
| GLM-5.3-FLASH **强制思考不可关闭**（官方文档）【21】，方舟 doubao-seed thinking 参数〔未核实〕【37】 | 3.2/3.4 思考适配 | 建议修订 R9（按"必有 reasoning_content"设计） |
| temperature=0 不保证确定性（实证）【19】 | 3.2/M5 | 建议修订 R10（重排结果缓存 + 每配置 ≥3 次重复） |
| ALCE 引用解析语义：正则漏 [1,2]、越界引用=整句显式判 0【27】；LlamaIndex "Source N:" 块头 + prompt 三要素【26】 | 3.4 citations | 建议修订 R11（编号机制 + 后处理语义） |
| 多模态引用节点：文本块与图片**同 Source 交错**（非图片堆尾）【26】 | 3.4 context | 建议修订 R12（图文交错 + 选图规则） |
| 大模型上下文不充分时倾向硬答而非弃答【31】【32】；selective generation +2~10% | 3.4 fallback | 印证已定双信号 + 建议修订 R13（调参顺序：先压误拒） |
| "问题语言决定作答语言"是多语评测既定范式（MKQA）【33】 | 3.4 | 建议修订 R14（system prompt 语言跟随） |
| ALCE 配置范式：命名配置文件 + 一条命令复现【28】；Langfuse/promptfoo 为成熟可观测/评测先例【35】【36】 | 3.5 query_cli.py | 建议修订 R15/R16（trace JSONL + --smoke 报告）；R18 记录（工具不引入） |
| VisRAG：单图兼容方案=逐页打分+检索分加权【5】 | 3.2 F 档 | 记录 R17（逐图点式打分起步） |

---

## 1. 混合检索与融合（→ 3.1 hybrid.py / 3.3 router.py）

### 1.1 融合参数与实现路线

- **坑**：Qdrant 服务端 RRF（prefetch + fusion）**只能在单 collection 内做**——各路 prefetch 挂在同一集合查询下、用命名向量区分；DocLens 是双集合 + 本地 BM25 的三路异构，服务端融合天然不适用【1】。官方明确坑：offset 只作用于主查询，"**prefetch 的 limit 必须 ≥ 主查询 limit+offset，否则可能得到空结果**"【1】。融合后的 score 只是排名合成值、**不再是相似度**（Elastic 明示各路分数量纲互不相关）【2】——融合层之上再套 score_threshold 语义不可靠。
- **主流**：Qdrant 官方混合检索示例=每路 prefetch limit 20 → 融合后 limit 10【1】；Elastic `rank_window_size` 默认=最终 size，官方明言"窗口越大相关性越好但更慢"【2】。**RRF 的 k 三档并存**：Qdrant 服务端默认 k=2（权重 w 默认 1，公式 score=Σ1/(k+(rank+1)/w−1)）【1】；LlamaIndex 客户端实现硬编码 k=60 并注明出自原论文【3】；Elastic `rank_constant` 默认 60、文档称"RRF 免调参"【2】。另有一个实现陷阱：LlamaIndex QueryFusionRetriever **默认 mode 是 SIMPLE（加权分数和）而非 RRF，必须显式指定**【3】——自研时直接写 RRF 无此坑。
- **落地**：客户端自实现 RRF 定稿（别无选择）；每路召回 30 起步（调参位 20–50；Qdrant 示例的"融合 10"是无重排直答场景，我们融合池按 D6 骨架保 top-50 交重排）；k=2 维持已定约束（恰为 Qdrant 默认），k=60 留 M5 对照位；两条官方坑（prefetch limit、融合分语义）写进模块注释与单测。

### 1.1b 融合方案可选面（2026-11-11 立项问答补充）

| 方案 | 原理 | 谁在用（已核实来源） | 对 DocLens 的适配 |
|---|---|---|---|
| **RRF（排名融合）** | score=Σ1/(k+rank)，只看名次不看分数 | Qdrant（k=2 默认）【1】、Elastic（rank_constant=60）【2】、LlamaIndex（k=60）【3】 | ✅ **主线（已定）**——对分数质量与量纲免疫 |
| 加权 RRF | 每路乘权重 w_r：1/(k+rank/w) | Qdrant 官方支持【1】、LangChain EnsembleRetriever〔二手〕 | ✅ 作权重实验位（重点：图像路 w） |
| 凸组合（分数归一加权） | 每路分数 min-max 归一到 [0,1] 后加权（Weaviate 的 alpha，示例默认 0.5；融合方法本身可切换）【39】 | Weaviate【39】 | ⚠️ 要求分数可信且可比——BM25 无上界、图像路跨模态 cosine 区分度未验证（M2 风险表既知），先天吃亏 |
| DBSF（分布归一融合） | 按每路分数的均值/标准差做 z-score 归一再求和 | Qdrant 官方第二选项【1】；LlamaIndex DIST_BASED 同族 | 🔶 M5 消融位（分数系首选代表） |
| 相对分数融合 | score ÷ 本路最高分后加权 | LlamaIndex 默认 SIMPLE 模式【3】 | 🔶 与 DBSF 二选一进消融即可 |
| 配额/门控式 | 每路固定配额，或按查询特征开关某路 | ——（D11 路由的"BM25 旁路"就是门控特例） | ✅ 已在用；配额制不值当单独实现 |
| 学习型融合（LTR） | 训练融合权重/模型 | 工业界搜索系统 | ❌ 无标注数据无 GPU；"智能排序"职责已交给重排层（D6） |

- **关键判断**：融合层在我们的架构里是**候选池生成器**而非终审——D 档起有 LLM 重排承担精排（Anthropic：重排使失败率 5.7%→1.9%【13】），融合方案的差异会被重排抹平；**方案差异真正暴露的地方是无重排档（A/B/C）**，那里融合就是最终排序——这正是 M5 消融要跑对照组的原因。
- **M5 对照组建议**（全在无重排档跑才有意义）：RRF vs DBSF；k=2 vs k=60；图像路权重 1.0 vs 0.5（防弱图像路挤占 text/table 名额）。
- **实现建议**：hybrid.py 把"融合器"抽象成纯函数（输入=各路 (chunk_id, rank, score)，输出=融合序列），RRF/加权 RRF/DBSF 各是一个函数体——M5 加消融档零改动，成本几乎为零。

### 1.2 图与图注联动去重

- **坑**：同一图表，caption 文本块（text 集合）与图像块（image 集合）是同一证据的两面，两路同中会双计、挤占 top-k 名额。
- **主流**：**块级多路去重无公开先例**〔未核实〕；主流做法是"改粒度"而非"去重"——M3DocRAG 三段式=ColPali 按页建索引→检索 top-K 页→VLM 作答，图文天然同页合并；其实测"证据含图时图文 RAG 差距最大、给更多页普遍提升"【4】；VisRAG 同样"以页为检索与生成的基本单元"【5】。
- **落地**：**证据组归并**——RRF 之后、重排之前，按 (doc_id, page) 或 figure 组（caption 的 payload 带 image_path/bbox、image 的 payload 带 caption，M2 已具备）归并命中：组内取最优名次做代表、组成员保留供引用。这是 M3DocRAG 页级聚合在块级 schema 上的等价物；"不去重只靠重排"留作 M5 消融档。

### 1.3 BM25 工程细则

- **坑（源码级）**：rank_bm25 BM25Okapi 默认 k1=1.5、b=0.75、epsilon=0.25；**负 IDF 词**（出现于超过半数文档）被压到 epsilon·avg_idf 地板——~1500 块小语料上高频词地板效应更明显【6】。`get_scores` 输入是"已分词 token 列表"，**分词完全由调用方负责，索引侧/查询侧分词不一致=静默劣化**【6】。无内置过滤检索，但提供 `get_batch_scores(query, doc_ids)` 子集打分【6】。jieba 对中英混排/大小写/连字符的行为无权威文档〔未核实〕——最大风险是两侧用了不同切分模式（cut vs cut_for_search）或漏 lower()。
- **落地**：tokenize 做成单例函数（jieba 默认模式 + lower）**索引与查询两侧共用**，配"中英混合/专有名词/数字"配对拍单测；默认 k1/b 不调，调参位只动 b（0.4–0.75）；zh 查询按已定约束降权/旁路（3.3 router）。

### 1.4 消融档位过滤与查询缓存

- **坑**：A–F 六档在 Qdrant 与 BM25 两个后端各写一份 kind 过滤，极易口径漂移（如 A 档一边含 caption 一边不含）→ 消融结论失真；Qdrant 过滤要性能需建 payload 索引【7】。
- **落地**：**单一事实源映射**——模块内唯一 `TIER_KINDS={A:{text}, B:{text,table,caption}, …}`，Qdrant filter 构造器（Filter(must=[FieldCondition+MatchValue/MatchAny])【7】）与 BM25 侧都由它生成；BM25 用全量索引 + `get_batch_scores` 按允许 kind 的 chunk 子集打分（1513 块 O(N) 无压力，免多份 pickle）；**防线单测**：固定查询下断言两后端返回 chunk 的 kind ⊆ TIER_KINDS[tier]。
- **查询嵌入缓存**：同一批查询跨六档重跑，查询向量复用 `t_embed_cache` 同一张表（键=sha256(model+instruction+dim+content) 天然覆盖查询侧——Query/Corpus 分侧指令已体现在键里），六档评测嵌入调用降为 1 次；role 列（ingest|query）为可选审计增强。

### 1.5 检索分数与兜底阈值

- **坑**：dense cosine 与 BM25 分数都只在同一查询内可比，**跨查询全局阈值必错**；融合分更是纯排名合成【1】【2】。
- **主流**：放弃分数阈值、把"库中是否有答案"交给下游判官有论文背书——CRAG 用轻量检索评估器给取回文档评置信度再触发动作【8】；Self-RAG 用反思 token 按需检索/自评【9】。
- **落地**：检索层只稳定输出 top-k，**不做全局分数阈值兜底**（已定双信号=检索分数观测 + judge，见 §3.5）；top1–top2 分差、命中 kind 分布仅作日志观测不进决策。

---

## 2. LLM 列表式重排（→ 3.2 rerank.py）

### 2.1 输出解析与兜底（RankGPT 三级链，源码级依据）

- **坑**：模型输出排列时常漏元素、重复元素、夹带解释文字、只输出 top-N 前缀。
- **主流**（sunnweiwei/RankGPT `rank_gpt.py`，源码全文已抓【11】）：三级解析链——① `clean_response` 把所有非数字字符替换成空格再按整数切分（天然滤掉解释文字）；② `remove_duplicate` 保留首次出现去重；③ `receive_permutation` 过滤越界 ID 后把缺失候选**按原顺序补到尾部**。最坏情况（输出全废）自动退化为原顺序——**解析链本身就是兜底**。提示词同时明令 "Only response the ranking results, do not say any word or explain"。
- **落地**：三级链原样移植（与模型无关）；单测覆盖空串/重复/越界/夹带文字四类。

### 2.2 位置偏差与温度 0 非确定性

- **位置偏差**：列表中段/尾部的相关文档更难被提到顶部（DebiasFirst 实证"位于输入末尾的 passage 更难进入 top"【15】；Lost in the Middle 的 U 形【14】）。缓解：滑窗从尾向头滑+重叠窗（RankGPT 原生【12】）、PRP 单向判定（延迟优化 61.36s→0.37s/查询【18】）、采样边际化集成（TS-SetRank，BRIGHT +15~25%【17】）；"随机洗牌×多次取平均"未找到强公开证据〔未核实〕。
- **温度 0**：**不保证确定性**——实证 temp=0 显著优于 temp=1 但仍大量任务零重复输出【19】；RankGPT 官方固定 temperature=0【11】。
- **落地**：候选 ≤30 单次调用时"输入顺序=RRF 顺序"是混杂变量，"候选洗牌后重排"对照留 M5 定案；M5 每配置 ≥3 次重复报均值+极差；方舟 `seed` 参数对本项目两模型是否生效需实测〔未核实〕。

### 2.3 思考型模型做重排（GLM 强制思考）

- **官方事实**（智谱文档，原文已抓）：**GLM-5.3 / GLM-5.3-FLASH 等新系列默认开启 Thinking 且"强制思考不能关闭"**——`thinking:{"type":"disabled"}` 仅对旧系（GLM-4.6/5.2/5.1/5/4.7）有效【21】；官方《延迟优化》实践页：降首字延迟首要手段=减少/关闭思考+减少输入+要求直接作答，长前缀建议用上下文缓存【22】。方舟 doubao-seed 系 thinking 参数（已知形态 `{"type":"enabled|disabled|auto"}`）官方原文未抓到〔未核实，落地前以方舟控制台文档复核〕【37】。
- **落地**：**flash 档按"思考关不掉"设计**——max_tokens 从紧、解析只认 content、TTFT/思考耗时入 trace；pro 档（doubao-seed-2-1-pro）保留 thinking 开关做延迟/质量消融（待 R-核实项 1）；系统提示词固定前缀以吃上下文缓存。
- **与 NFR 的张力（立项时校准）**：NFR"生成首 token <5s"在强制思考模型下大概率守不住（M0 实测 doubao-seed-2.1-pro 全流 10.76s；E 档试产出现过单次 132s 长思考）——建议 M3 runbook 把指标口径改为"正文首 token（思考结束后）"并实测记录，或在 NFR 表加注。

### 2.4 候选数量、截断、级联与失败降级

- **实践数字**：RankGPT 窗口 20/步长 10 处理 top-100，**每篇截 300 词**（源码 max_length=300）【11】【12】；Anthropic contextual retrieval：150→重排→20（top-20 检索失败率 5.7%→1.9%）【13】；档位差距：gpt-4 53.68 vs gpt-3.5 49.37（BEIR nDCG@10 均值）【10】；Qwen3-Reranker 0.6B/4B/8B=65.8/69.8/69.0（MTEB-R），小档明显弱【24】；级联省钱：gpt-4 只重排 gpt-3.5 已排好的 top-30（论文脚注）【12】。
- **坑**：塞太多→中段被忽略（与 2.2 位置偏差叠加）、超时；候选文本过长→截断丢信息。
- **落地**：D6 骨架（RRF top-50 → 重排 → top-20）保持，**重排输入截 30**（50 直进单次调用有超长+中段忽略风险——RankGPT 窗口 20 的立论）；候选文本截 300 词等价量自测微调；**pro 档级联法**：只重排 flash 档 top-10/15 控预算；**失败降级**：HTTP 超时 4–6s + 1 次重试 → 失败回 RRF 序并打降级标记（RankGPT 源码自带 30s 超时+重试+解析回退的雏形【11】），降级率列入 M3 验收指标。

### 2.5 结构化输出之争

- **已核实**：格式约束越严、推理任务掉分越多（Let Me Speak Freely）【20】；RankGPT 全程自由文本+鲁棒解析、无 JSON【11】；GLM 官方支持 `response_format:{"type":"json_object"}`【23】。
- **落地**：主方案=自由文本 `[1] > [2]` + 三级解析链；JSON 模式仅作 M5 一组消融。

### 2.6 F 档多模态重排先例

- **已核实**：VisRAG v1 管线无独立重排段（Ret+Gen）：单图 VLM 用"页面横向拼接成一张图"或多图直喂 top-k，生成性能随检索页数增加；单图兼容方案=**逐页打分+检索分加权选择**【5】。Qwen3-Reranker 为 query-doc 成对 cross-encoder、instruction-aware【24】。VisRAG v2 重排细节、M3DocRAG 分辨率消融（1024→2048）、Qwen3-VL-Reranker 托管情况均〔未核实〕【25】。
- **落地**：**逐图打分（0–2 分）点式起步**（可控、可缓存、失败可跳过），再试一次 4–6 图列表式对比；分辨率沿用 M1 图块原图，放大实验留 M5。

---

## 3. 带据生成（→ 3.4 context.py / vlm.py / citations.py / fallback.py）

### 3.1 [n] 引用稳定输出与后处理

- **坑**：引用幻觉（编造 n）、格式漂移（[1,2]/[1][2]/[1-3]）、引用粒度过粗。
- **主流**：LlamaIndex CitationQueryEngine——每块开头标 "**Source N:**"；prompt 三要素（仅依据所给源作答/每答至少一引/仅显式引用时才标）+ 一句 few-shot 展示句内内联 [2]…[1]；检索块重切 512 字符作引用粒度【26】。ALCE `eval.py`：宽松正则 `re.findall(r"\[\d+", sent)`——**[1,2] 只会取到 1**（需自行兼容逗号/区间写法）；**越界引用=整句判 0（显式拒绝而非静默删）**；NLI 模型逐句核"句子是否被所引文档蕴含"出 citation recall/precision【27】。ALCE 论文编号勘误：**arXiv 2305.14627**（2305.14295 是物理论文）【28】。
- **落地**：采纳"块头 Source N: 编号 + 三要素 prompt + 句内内联 [n]"（DocLens 块 800–1600 字符，不必学 512 重切）；后处理按 ALCE 语义——正则提取全部 [n]（兼容 [1,2]），**无效 n 整句降级标记并落 trace，不静默删**；NLI 事后核对记为 M5 增强。

### 3.2 流式与引用的配合

- **坑**：[n] 跨 SSE chunk 截断；引用侧栏需要完整清单。
- **主流**：LlamaIndex 引擎 streaming 默认 False——官方对"引用+流式"持保守态【26】；kotaemon=答案+引用块完成后一次性呈现【34】；增量缓冲"遇 [ 暂停、遇 ] 释放"系通用工程做法〔二手〕。
- **落地**：双轨——M3 CLI 非流式先跑通；M4 SSE 正文透传 content，**引用清单在 finish_reason=stop 后对完整文本一次性解析**（不逐 token 解析引用）；流式内联高亮（3 字符缓冲）记为 M4 待办。

### 3.3 多模态上下文组装

- **主流**：LlamaIndex 多模态引用节点=每个 Source 一个节点，"Source N:" 文本标签 + 该源文本块 + 图片块**同节点交错**（非图片堆尾）【26】；M3DocRAG：检索页数↑→性能↑，证据涉图片时文本 RAG 差距尤其大【4】【25】；生成侧图片位置/分辨率/数量上限论文未专测〔未核实〕；原图+caption 同送无实证〔未核实〕。
- **落地**：**图文按 Source 交错、图片紧跟其 caption 且同编号**（[n]→文档/页/坐标溯源天然成立）；选图=融合分 top5 + 与已选文本块去重（同区域优先原图、caption 文本保留）；分辨率原图直送（GLM-5.3-Flash 1M 窗口【30】）；组装档位 top-20 内加 top-12 对照并落 trace（lost-in-the-middle 首尾优先之上的细化）。

### 3.4 思考型模型的生成侧处理

- **官方事实**（智谱文档，原文已抓）：流式 SSE 中 `choices[0].delta.content`（正文增量）与 `delta.reasoning_content`（思考增量）**分离字段**，finish_reason 与 usage 仅末 chunk【29】；GLM-5.3-Flash 默认 Thinking 且强制不可关【21】。
- **落地**：客户端**双字段分流**——reasoning_content 只落 trace（思考 token 数、思考耗时），绝不混入答案正文；usage 取末 chunk（非流式取 message）；CLI 非流式等待即可，M4 把"思考中"当状态展示（TTFT 后移，见 §2.3 与 NFR 张力）。

### 3.5 无依据兜底与阈值调参顺序

- **已核实**：大模型在上下文不充分时**倾向硬答而非弃答**（Sufficient Context；其 selective generation 使"有回答时的正确率"+2~10%）【31】；RGB：negative rejection 是 RAG 四能力最弱之一——**单靠 prompt 写"没有就承认"不可靠**【32】；CRAG=轻量评估器门控【8】；生成后 NLI self-check 最准但最贵【27】。
- **落地**：已定双信号（检索观测 + judge）与上述先例同构，维持；**调参顺序**：阈值从松到紧在 20 冒烟题上扫描（记录拒答/误拒矩阵），**先压误拒 ≤5% 再提拒答率**（拒答率好提、误拒难压）；prompt 内"无依据就明确声明"保留作第三道兜底，不作主机制。

### 3.6 答案语言跟随

- **主流**：MKQA 10k 题×26 语言对齐——"问题语言决定作答语言"是多语评测既定范式【33】；生成侧专门论文未找到〔未核实〕；prompt 显式指定输出语言属工程共识〔二手〕。
- **落地**：system prompt 明确"用与问题相同的语言作答，专有名词/术语可保留英文"；router 的语言检测字段入 trace，供 M5 归因 F5 时查"语言跟随失败"。

---

## 4. CLI、trace 与验收工作流（→ 3.5 query_cli.py）

### 4.1 消融配置管理

- **主流**：ALCE 范式——命名规范配置文件（`{模型}_{检索器}_{方法}.yaml`）+ `run.py --config` 一条命令复现、CLI 参数可覆盖【28】；dataclass/registry、Hydra 属通用范式〔二手〕。
- **落地**：profile = **dataclass registry**（六档共享字段+档位覆写，复用 config.py），CLI 只留 --profile/--question；配置不得散落 env 判断。

### 4.2 trace 与 F0–F6 归因对齐

- **落地（自研设计，M2 search_probe 先例延续）**：trace 按"主事件+子事件"落本地 JSONL：query → 各路检索（chunk_id+分数+排名）→ 融合前后序 → 重排前后序 → 最终上下文清单 → LLM 原始输出（**reasoning/content 分列**）→ 分段耗时+token 用量——字段与失败归因 F0–F6 一一对应（F2 召回缺失=各路命中不含 gold；F3 融合错排=融合前后序；F4 重排伤害=重排前后序；F5 生成失败=上下文含 gold 仍错；F6 兜底误触发=弃答判定记录）。

### 4.3 冒烟验收报告

- **主流**：promptfoo `eval`→`view` 本地 web 报告（题目×配置并排矩阵、可进 CI）【36】；"人工填通过/失败"列的现成工具未找到〔未核实〕——普遍做法=自动报告+人工批注列。
- **落地**：自建轻量版——`query_cli.py --smoke` 跑 20 题×当前 profile，产 Markdown 报告（题目|答案|[n] 引用|各路 top 命中并排|是否弃答 + 表尾人工"通过/失败"列）；每行嵌 trace id，失败题可回放。Langfuse/promptfoo 不引入（JS 栈重），记为 M5 备选【35】【36】。

---

## 5. 修订清单汇总（→ m3-runbook；立项经 G1 确认后并入）

| # | 修订 | 落点 | 级别 |
|---|---|---|---|
| R1 | 每路召回 30 起步（调参位 20–50）、客户端自实现 RRF 定稿、k=2 维持 + k=60 对照位；prefetch limit 坑与"融合分无相似度含义"写进注释/单测 | runbook K-检索 | 建议 |
| R2 | 图-图注联动去重=证据组归并（RRF 后、重排前；按 doc+page/figure 组，组内最优名次代表、成员留引用）；"不去重"留消融档 | runbook K-检索 | 建议 |
| R3 | BM25：tokenize 单例两侧共用+配对拍单测；默认 k1/b 不调（b 调参位 0.4–0.75）；kind 过滤走 get_batch_scores 子集打分；负 IDF 地板效应记录 | runbook K-检索 | 建议 |
| R4 | TIER_KINDS 单源映射 + "两后端 kind ⊆ 映射"防线单测 | runbook K-检索/CLI | 建议 |
| R5 | 查询向量复用 t_embed_cache（键天然覆盖 Query 指令侧）；role 列可选 | runbook K-CLI | 建议 |
| R6 | 不做全局分数阈值兜底；检索层只出 top-k，分数仅日志观测 | runbook K-兜底 | 建议 |
| R7 | 重排解析照抄 RankGPT 三级链（清洗→去重→越界过滤+缺失补尾）+ 四类单测 | runbook K-重排 | 建议 |
| R8 | 重排预算：输入截 30（D6 骨架 top-50→top-20 保持）、每篇截 300 词、temp=0；pro 档级联（只重排 flash top-10/15）；超时 4–6s+1 重试→回 RRF 序+降级标记，降级率入验收 | runbook K-重排 | 建议 |
| R9 | 思考模型适配：glm-5.3-flash 强制思考不可关（官方），代码按"必有 reasoning_content"设计、解析只认 content、max_tokens 从紧、TTFT/思考耗时入 trace；NFR"首 token<5s"口径立项时校准 | runbook K-生成 + NFR 校准 | 建议 |
| R10 | 重排结果缓存（query, 候选指纹, 模型档, 参数）沿用缓存表模式；M5 每配置 ≥3 次重复报均值+极差 | runbook K-重排/M5 | 建议 |
| R11 | 引用：Source N 块头 + prompt 三要素 + few-shot；后处理兼容 [1,2]、无效 n 整句降级标记落 trace（不静默删）；NLI 核对留 M5 | runbook K-生成 | 建议 |
| R12 | 上下文组装：图文按 Source 交错、图片紧跟 caption 同编号；选图=融合分 top5+去重；top-12 对照档落 trace | runbook K-生成 | 建议 |
| R13 | 兜底阈值调参顺序：先压误拒 ≤5% 再提拒答率（20 冒烟题扫拒答/误拒矩阵）；prompt 兜底为第三道 | runbook K-兜底 | 建议 |
| R14 | 答案语言跟随问题语言（system prompt 明确，专有名词可留英文）；语言检测字段入 trace | runbook K-生成 | 建议 |
| R15 | trace=主事件+子事件 JSONL（各路命中、融合/重排前后序、最终上下文、reasoning/content 分列、分段耗时+token），字段对齐 F0–F6 | runbook K-CLI | 建议 |
| R16 | `query_cli.py --smoke`：20 题自动产 Markdown 验收报告（答案/引用/命中并排+人工通过列+trace id 可回放） | runbook 3.5 | 建议 |
| R17 | F 档多模态重排：逐图 0–2 分点式起步、4–6 图列表式对比留实验；分辨率沿用 M1 | runbook F 档备注 | 记录 |
| R18 | Langfuse/promptfoo 不引入 M3（JS 栈重），JSONL trace + Markdown 报告自建；两者作 M5 备选 | runbook 备注 | 记录 |

## 6. 待人工核实

1. **方舟 doubao-seed 系 thinking 参数**（enabled/disabled/auto 形态与生效范围）——pro 档重排/生成的延迟消融前必须核实；入口 [方舟深度思考](https://docs.volcengine.com/docs/ark/deep-thinking)（页面存在、正文 JS 渲染未抓到）【37】。不影响 M3 开工：flash 档按"思考不可关"设计不依赖此项。
2. **方舟 `seed` 参数**对 glm-5.3-flash / doubao-seed-2-1-pro 是否生效（M5 复现性实验用）〔未核实〕。
3. **生成侧图片数量上限/分辨率对 VLM 读图的影响**——M3DocRAG 分辨率消融与 VisRAG v2 重排细节未抓到原文；M3 沿用"原图直送+top5"，M5 记对照〔未核实〕【25】【5】。
4. **jieba 中英混排/连字符边界行为**——无权威文档，以配对拍单测自证代之〔未核实〕。
5. F 档参考：Qwen3-VL-Reranker 托管与效果（方舟无托管 reranker，LLM 打分是既定路线；此项仅记录）〔未核实〕【24】。

## 7. 来源清单

| # | 来源 | 用途 |
|---|---|---|
| [1] | [Qdrant Hybrid Queries](https://qdrant.tech/documentation/search/hybrid-queries/) | RRF 公式 k=2/w=1、prefetch 20→10、offset/limit 坑、单集合限制 |
| [2] | [Elastic RRF](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) | rank_constant=60、rank_window_size、免调参、分数不可比 |
| [3] | [LlamaIndex fusion_retriever.py](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/retrievers/fusion_retriever.py) | 客户端 RRF k=60、weights、hash 去重、默认 SIMPLE 坑 |
| [4] | [M3DocRAG 项目页](https://m3docrag.github.io) | 页级三段式、证据模态结论 |
| [5] | [VisRAG](https://arxiv.org/abs/2410.10594) | 页为基本单元、逐页打分+加权、页面拼接 |
| [6] | [rank_bm25 源码](https://github.com/dorianbrown/rank_bm25) | 默认 k1/b/epsilon、负 IDF 地板、调用方分词、get_batch_scores |
| [7] | [Qdrant Filtering](https://qdrant.tech/documentation/search/filtering/) | must/MatchAny 语法、payload 索引建议 |
| [8] | [CRAG](https://arxiv.org/abs/2401.15884) | 检索评估器判官替代分数阈值 |
| [9] | [Self-RAG](https://arxiv.org/abs/2310.11511) | 反思 token 按需检索自评 |
| [10] | [RankGPT](https://arxiv.org/abs/2304.09542) | 重排增益 +6~+10 nDCG@10、档位差距 |
| [11] | [RankGPT rank_gpt.py](https://github.com/sunnweiwei/RankGPT) | 三级解析链、300 词、temp=0、超时重试（源码级） |
| [12] | [RankGPT HTML v3](https://arxiv.org/html/2304.09542v3) | 滑窗 back-to-first、级联省钱脚注 |
| [13] | [Anthropic Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval) | 150→20、失败率 5.7%→1.9% |
| [14] | [Lost in the Middle](https://arxiv.org/abs/2307.03172) | 位置 U 形 |
| [15] | [DebiasFirst](https://arxiv.org/abs/2604.03642) | 末位劣势实证 |
| [16] | [InvariRank](https://arxiv.org/abs/2608.03091) | 重排输出一致性框架（RecSys 2026） |
| [17] | [TS-SetRank](https://arxiv.org/abs/2511.01208) | 采样集成 +15~25% |
| [18] | [PRP](https://arxiv.org/abs/2511.07555) | 单向判定延迟优化 61.36s→0.37s |
| [19] | [温度 0 非确定性](https://arxiv.org/abs/2308.02828) | temp=0 仍大量任务零重复输出 |
| [20] | [Let Me Speak Freely](https://arxiv.org/abs/2408.02442) | 格式约束损害推理 |
| [21] | [GLM 思考模式（官方）](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode) | GLM-5.3-FLASH 强制思考不能关闭 |
| [22] | [GLM 延迟优化（官方）](https://docs.bigmodel.cn/cn/best-practice/latency-optimization) | 降首字延迟官方实践 |
| [23] | [GLM 结构化输出（官方）](https://docs.bigmodel.cn/cn/guide/capabilities/struct-output) | json_object 模式 |
| [24] | [Qwen3 Embedding 博客](https://qwenlm.github.io/blog/qwen3-embedding/) | Qwen3-Reranker 0.6B/4B/8B 分数、instruction-aware |
| [25] | [M3DocRAG](https://arxiv.org/abs/2411.04952) | 检索页数↑性能↑、拼接低分辨率劣于多模态检索 |
| [26] | [LlamaIndex citation_query_engine.py](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/query_engine/citation_query_engine.py) | Source N 块头、三要素 prompt、512 重切、图文交错、streaming 默认 False（源码级） |
| [27] | [ALCE eval.py](https://github.com/princeton-nlp/ALCE/blob/main/eval.py) | 正则漏 [1,2]、越界整句判 0、NLI 核对（源码级） |
| [28] | [ALCE README](https://github.com/princeton-nlp/ALCE) | 论文正名 arXiv 2305.14627、配置范式 |
| [29] | [GLM 流式消息（官方）](https://docs.bigmodel.cn/cn/guide/capabilities/streaming) | delta.content / delta.reasoning_content 分离、usage 末 chunk |
| [30] | [GLM-5.3-Flash 模型页（官方）](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash) | 1M 窗口、多模态 |
| [31] | [Sufficient Context](https://arxiv.org/abs/2411.06037) | 不充分时倾向硬答、selective generation +2~10% |
| [32] | [RGB](https://arxiv.org/abs/2309.01431) | negative rejection 最弱、prompt 兜底不可靠 |
| [33] | [MKQA](https://arxiv.org/abs/2007.15207) | 问题语言决定作答语言 |
| [34] | [kotaemon](https://github.com/Cinnamon/kotaemon) | 答案+引用块一次性呈现先例 |
| [35] | [Langfuse](https://github.com/langfuse/langfuse) | trace 平台先例（M5 备选） |
| [36] | [promptfoo](https://github.com/promptfoo/promptfoo) | 评测矩阵报告先例（M5 备选） |
| [37] | [方舟深度思考](https://docs.volcengine.com/docs/ark/deep-thinking) | doubao thinking 参数（JS 渲染未抓到，待人工核实） |
| [38] | [Anthropic Citations](https://docs.claude.com/en/docs/build-with-claude/citations) | 服务端引用 API（重定向断裂未核实，仅记录） |
| [39] | [Weaviate Hybrid Search](https://docs.weaviate.io/weaviate/search/hybrid) | alpha 相对权重 + 融合方法可切换（2026-11-11 主代理补充核实，方法名清单未抓全） |
