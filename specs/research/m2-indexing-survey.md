# DocLens M2 索引方案·同类项目调研笔记

> 状态：**v1.0（已核实为主）**——三条调研线（分块策略 / 表格结构理解与序列化 / 多模态入库与幂等）2026-11-11 由三个研究代理并行完成；来源以**官方文档站 + GitHub 源码直抓**为主（GitHub 经 ghfast.top 加速代理读取，引注为官方仓库路径；当日 web_search 后端余额不足 HTTP 402，未依赖二手博客）。未能核实项在 §5 明确列出。
> 用途：[m2-runbook.md](../plans/m2-runbook.md) 的方案佐证与修订输入，随 G1 确认门一并过目；财报泛化包（表格 LLM 仲裁）与 M5 消融的参考。
> 约定：无标注判断为本项目自己的设计结论；带 [n] 的为已核实来源，编号见 §6。

## 0. 与项目规划的映射（本笔记如何进入 M2 runbook）

| 调研发现 | 对应决策 | 结论 |
|---|---|---|
| "同节聚合+节内超限切+标题前缀"与 RAGFlow Title Chunker / Docling HybridChunker / LlamaIndex 节解析链三大实现同构 | K1 | 印证 |
| References 过滤有 RAGFlow 版面级丢弃先例（PaperQA2 为"不滤"对照） | K1 | 印证 |
| 页眉页脚判定应加"跨页重复出现 >1 次"（RAGFlow 先例） | K1 过滤细则 | **建议修订 R1** |
| 句切边界 overlap 是主流默认（200 token / 250 字符） | K1 | 可选修订 R2（M5 消融位） |
| 标题前缀占 chunk 预算是主流实践 | K1 细则 | 维持现设计、理由记录 R3 |
| Docling 官方承认 Markdown 展平丢 span 结构 | K2 网格化重写 | 印证 |
| 序列化格式是嵌入检索方差源、对 BM25 增益弱；力气应花在"表头/字段名进文本" | K2 表格卡片 | 印证 |
| "表注+列名+行名"整卡前置无公开对应物 | K2 | 印证 + 差异化卖点 R6 |
| 无效区域剔除无公开规则集（模型化对照 = 微软 TATR） | K2 规则版 | 印证（125 表审计 = 规则归纳数据集） |
| caption 入 text 集合 + 图像向量入 image 集合 = LlamaIndex 官方多模态架构同构 | K5 | 印证 |
| 幂等四件套（doc hash 跳过 + uuid5 点 ID + 先删后插 + 指纹缓存键）有 LlamaIndex/Qdrant 官方先例 | K4/K5/§3.1 | 印证 |
| 嵌入缓存键含模型/指令/维度，严格优于 LangChain 默认 | K4 | 印证 |
| 无图注图无"默认丢弃"先例（VLM 合成 caption / 仅视觉向量两路线） | K1 caption | 印证 + 可选增强 R5 |
| 方舟 base64 体积上限未能核实 | 2.7 探针 | 待人工核实（§5） |

---

## 1. 分块策略（→ K1）

### 1.1 对比表（来源 [1]–[12]）

| 项目 | 机制 | 默认尺寸/关键参数 | 标题/语境进嵌入文本 | References |
|---|---|---|---|---|
| LlamaIndex | MarkdownNodeParser 节块 → SentenceSplitter 句切；HierarchicalNodeParser 三层 | chunk_size=1024 token、overlap=200；层级默认硬编码 [2048,512,128]、overlap=20 | 默认进：全部 metadata（含 header_path）拼入嵌入文本并占 chunk 预算 | 不滤 |
| LangChain | MarkdownHeaderTextSplitter → RecursiveCharacterTextSplitter | 4000 字符、overlap=200；分隔符 `["\n\n","\n"," ",""]`；overlap 只在节内生效 | 默认不进：strip_headers=True，标题只进 metadata（可关） | 不滤 |
| RAGFlow | 模板化 12 种 + v1.0 Title Chunker | General 目标 512 token；Paper 同节聚合、无 token 上限 | Title Chunker 把完整父标题路径写进块文本 | 版面级丢弃 reference |
| Docling | HierarchicalChunker → HybridChunker | 默认 512 token；merge_peers=True | contextualize() 把 headings 前缀计入嵌入文本并占预算 | 无特殊处理 |
| unstructured | chunk_by_title 标题分节聚合 | max_characters=500 硬上限、new_after_n_chars=500 软上限 | 不进（标题在 metadata） | 无特殊处理 |
| PaperQA2 | 按页解析后纯字符滑窗 | chunk_chars=5000、overlap=250 | 无标题前缀 | 不滤（源码无过滤逻辑） |
| Anthropic | Contextual Retrieval | chunk ≤几百 token（测算例 800）；前缀 50–100 token | 前缀拼进嵌入+BM25 | — |

### 1.2 关键事实

- **尺寸区间**：token 系集中在 512–1024，字符系 500–5000。DocLens 的 800–1600 字符（≈200–400 token）属**偏细粒度**——与"引用需精确溯源到图表/页码"的作品集定位匹配（细块 + heading 前缀补偿语境），M5 消融可作调参位，无需改。
- **同构先例 3 个**：RAGFlow v1.0 Title Chunker Hierarchy 模式（官方原文 "chunk may contain `Part 1 > Chapter 3 > Section 2` followed by the body text"）[4]；Docling HybridChunker（merge_peers 同 headings 相邻块合并 + contextualize 前缀）[7]；LlamaIndex MarkdownNodeParser+SentenceSplitter 链（header_path 元数据 + 句切 + 元数据默认进嵌入文本）[1][2]。
- **References 两种先例并存**：RAGFlow `garbage_layouts=["footer","header","reference"]` + drop=True，解析阶段直接丢弃 [6]；PaperQA2 不滤、靠检索+LLM 评分兜底 [12]。DocLens"References 不入库"与 RAGFlow 同款，站得住。
- **页眉页脚清洗**（RAGFlow 最完整）：页顶/页底 10% 区域 + **跨页重复出现 >1 次才判垃圾**（单次出现豁免）+ `__is_garbage` 正则（点线 `\.{3,}`、页码 x/y、http://、邮箱、cid 乱码）[6]；unstructured 按 Header/Footer/PageNumber 元素类目过滤 [14]。
- **Anthropic Contextual Retrieval（K7 的外部依据）**：chunk ≤几百 token；Claude 读全文+chunk 生成 **50–100 token** 语境前缀（K7 参数与其一致），拼进嵌入文本和 BM25；实测 top-20 检索失败率 5.7% → 3.7%（仅 Contextual Embeddings，**-35%**）→ 2.9%（+Contextual BM25，**-49%**）→ 1.9%（+rerank，**-67%**）[9]。M5 消融预期可直接引用该数字作参照。

### 1.3 对 K1 的修订建议

- **R1 页眉页脚判定加"跨页重复 >1 次"**：现文案"无标题归属的碎片块丢弃"可能误删单次出现的正文碎片（如短摘要框）；借 RAGFlow 的重复性判定避免误删。落点：runbook §3.1 K1 细则。
- **R2 节内句切块间 overlap（可选）**：主流默认 overlap=200 token（字符系 250）；K1 目前无重叠，存在答案落在切块边界的风险。收益=边界句召回，代价=chunk 数 +10–20%。建议 M2 先不做，记为 M5 消融位。
- **R3 标题前缀占预算之争（维持现设计）**：主流做法是前缀计入 chunk 预算（防嵌入文本超限，LlamaIndex 元数据 token 从预算扣除 [2]、Docling contextualize 超限告警 [7]）；DocLens 现设计不占预算——总长（前缀 ~100–200 字符 + 1600 正文）仍远低于方舟嵌入输入上限，两害相权维持现设计（chunk 内容统一、实现简单），理由记录在案。

## 2. 表格结构理解与检索序列化（→ K2）

### 2.1 对比表（来源 [10][11][13]–[17]）

| 项目 | 跨行列 span 处理 | 表头/列名判定 | 检索序列化 |
|---|---|---|---|
| Docling (IBM) | grid 保留 row_span/col_span；HTML/JSON/DocTags 全保留，**Markdown/LaTeX 展平为空格** | TableFormer FAST/ACCURATE 出网格；无表头语义开关 | 分块层 repeat_table_header=True（表跨块时每块前置表头）；chunk 附带 caption |
| RAGFlow | PDF 侧 deepdoc 自带 TSR 模型；Excel 不涉 span | Excel 取首行为列名 | 默认每行一 chunk："列名：值; …"键值对 + sheet 名；html4excel=12 行小 HTML 表 |
| Unstructured | 不解析 span | 无表头判定；HTML 源的 thead/th 原样进 text_as_html | Table.text + metadata.text_as_html 双轨 |
| Marker (datalab) | md/json/html 多格式输出（管线细节未核实） | 未核实 | 未核实 |
| 微软 TATR（模型对照） | spanning cell 显式检测 + GRID 对齐 | "功能分析"任务含表头角色 | 输出结构化单元格，序列化交下游 |

### 2.2 关键事实

- **Markdown 展平丢结构是官方承认的共性问题**：Docling 官方 Serialization 文档给出 span 矩阵——HTML/JSON/DocTags 全保留，Markdown/LaTeX 展平（文本只写起点格、覆盖位留空），并明确建议"依赖表格结构（如合并表头）的工作流用 export_to_html()/export_to_dict() 而非 export_to_markdown()"[10]，issue #3830 同 [11]。→ DocLens"正则丢 rowspan/colspan → 列错位"是行业共性问题，K2 网格化重写方向正确。
- **"列名前置"有行级先例**：RAGFlow Excel 入库 = 首行列名 + 每行一 chunk 输出"姓名：张三; 部门：销售部; …"键值对（或 12 行一组小 HTML 表）[13]；Docling 的近似 = repeat_table_header + caption 随块 [7]。DocLens"表格卡片（表注+列名+行名整卡前置）"是**组合已有要素的渐进创新**，无直接对应物，可放心实现并写明借鉴来源。
- **表头判定须自建**：Unstructured 对 PDF 表无表头语义判定、HTML 原样继承 [14]；MinerU 输出无 `<th>` 等价于"从 td 网格重建"，与 K2 方案一致。
- **模型化对照**：微软 TATR（PubTables-1M，约百万表真值含表头角色）用 transformer 目标检测完成结构识别+功能分析 [15]——DocLens 无 GPU 推理条件，维持规则版合理。
- **序列化格式=检索方差源**（2026 实证）：语义等价的 csv/tsv/html/markdown/ddl 在 MPNet/BGE-M3/ReasonIR/SPLADE 上产生显著不同的嵌入与检索结果；多格式质心平均优于任一单格式，**但对 BM25 类稀疏检索增益弱** [16] → 结论：别指望换格式救 BM25，力气应花在"表头/字段名/表注是否进文本"上——正是表格卡片的设计意图；表体维持 markdown 全库一致即可。
- **前沿方向记录**：Topo-RAG 主张线性化不足、表格走单元格感知 late interaction（合成语料 SEC-25 上 nDCG@10 +18.4%，注意是合成语料）[17]——列财报泛化包/后续可选，M2 不动。
- **无效区域规则集无公开资料**：Note/*/†/Total/Average/空白格密度的剔除规则在公开项目里没有现成规则集（相邻做法仅 TATR 边界框天然挡表外脚注、Unstructured 元素类目过滤两条粗粒度先例）→ **把 125 表全量人工审计当作"规则归纳数据集"运营，本身就是差异化亮点**。

### 2.3 对 K2 的结论

无需修订：网格化重写、表头拼接、manifest、表格卡片全部有依据或属合理创新。收官时把 manifest/表格卡片写成 README 与报告的卖点（R6）。

## 3. 多模态图片入库与幂等机制（→ K3/K4/K5）

### 3.1 路线对比（来源 [18]–[22]）

| 维度 | ColPali/ColQwen 整页图多向量 | caption 文本块 + 图像单向量双路（DocLens） |
|---|---|---|
| 检索质量 | ViDoRe 基准 SOTA（ICLR 2025）[18] | 依赖 caption 覆盖率，无图注图靠视觉向量兜底 |
| 向量规模 | ColPali 1030×128 维/页、ColQwen2 ~700×128 维/页 | 每图 1×2048 维 |
| 存储/索引成本 | 单页 >0.5MB（f32），插入一页 ≈4900 万次 HNSW 比较 [19] | 低一个数量级以上，普通 HNSW |
| 依赖 | 本地 GPU + colpali_engine + 多向量库 | 只需普通嵌入 API 与常规集合 |
| 开源采用 | Qdrant 官方教程生态、ViDoRe 榜单 | LlamaIndex 官方示例、kotaemon 等 |

### 3.2 关键事实

- **双路方案与 LlamaIndex 官方多模态架构同构**：文本索引入文本库、图像索引入图像库，caption 存图像节点 metadata 而不拼进图像向量 [21]——DocLens 的 text/image 两集合 + caption 进 payload 与之一致。doubao-embedding-vision 为 API 单向量模型，无本地 GPU，ColPali 路线不适用（Qdrant 官方量化其代价：每页 1030 向量、mean-pooling 压缩+重排才可扩展 [19]）。
- **无图注图的三种处理，无"默认丢弃"先例**：① VLM 合成 caption（LlamaIndex 官方示例用 GPT-4V 生成替代文本 [21]；kotaemon 同路线 [22]，二手来源）；② 只靠视觉向量（M3DocRAG 专为"证据只在图像里"设计 [20]）；③ 丢弃——未发现主流项目以此为默认。→ DocLens 127 张无图注图走"仅视觉向量"（路线②）合法；装饰图降权、VLM 合成 caption 列为后续可选增强。
- **嵌入缓存**：LlamaIndex IngestionCache（缓存变换结果，docstore 存 doc_id→hash）[23]；LangChain CacheBackedEmbeddings（ByteStore 按文本哈希缓存，**模型名不进默认键**，换模型有串缓存风险）[24]；Qdrant 增量教程（指纹=精确嵌入文本 + 模型版本入 collection metadata）[25]。→ **DocLens 键 = sha256(model+instruction+dim+content) 把模型/指令/维度全纳入，严格优于三者**，防换模型串缓存。
- **Qdrant 幂等**：官方 Points 文档确认 UUID 点 ID + upsert 同 ID 覆盖写 + 按 filter 删除 [26]；uuid5 确定性点 ID 防重复块有第三方完整先例 [27]；官方增量教程的五步对账（未变不动/变更重嵌/迁移复用/新增/删源外点）[25]。LlamaIndex 文档管理官方示例 = doc_id→hash 未变跳过/已变重处理/UPSERTS 自动更新插入，官方实测连跑两遍无重复 [28]。→ **幂等四件套与两大官方先例同构，可按原方案实施**。
- **RAGFlow 对照**：重解析会替换旧 chunk（PR #9912 佐证）[29]，但"文档未变自动跳过"无官方表述——doc 级跳过是 DocLens 的加分项。
- **图像体积**：方舟官方多模态向量化 API 文档为 JS 渲染，自动抓取仅得导航壳，**base64 字节上限与推荐分辨率未能核实**（已知事实：doubao-embedding-vision-251215、base64/URL 输入 [31][32]）；参照 OpenAI CLIP 输入 resize 224×224 [30]——大图送 API 前降采样不损质量的通识成立。

### 3.3 对 K3–K5 的修订建议

- **R4 探针升级**：2.7 全量前的图像探针从"抽 2–3 张防超限"升级为"真实切图 2–3 张 + 长边 ~1024px 降采样前后向量一致性对照"（主动降采样而非仅作回滚）。
- **R5 后续可选**：VLM 合成 caption（高价值图）、装饰图降权——列入财报泛化包/扩语料阶段候选，M2 不做。

## 4. 修订清单汇总（→ m2-runbook.md；2026-11-11 R1–R6 已全部并入，runbook 正文以"调研 R#"标注）

| # | 修订 | 落点 | 级别 |
|---|---|---|---|
| R1 | 页眉页脚判定加"跨页重复 >1 次" | runbook §3.1 K1 细则 | 建议 |
| R2 | 节内句切块间 overlap（+10–20% chunk） | runbook K1 备注，M5 消融位 | 可选 |
| R3 | 标题前缀不占预算的理由记录 | runbook §3.1 | 记录 |
| R4 | 图像探针=真实切图+长边 ~1024px 降采样对照 | runbook 2.0 前置抽查/2.7 | 建议 |
| R5 | VLM 合成 caption / 装饰图降权列入后续可选 | runbook 风险表备注 | 记录 |
| R6 | manifest+表格卡片作为作品集差异化卖点 | 收官记录（README/报告） | 记录 |

## 5. 待人工核实

1. **方舟多模态向量化 API 的 base64 字节上限/推荐分辨率**——官方文档 JS 渲染无法自动抓取正文，当日 web_search 后端亦余额不足（HTTP 402）；请人工打开 [多模态向量化 API](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api) 查"输入参数"节。不影响 M2 启动：2.7 探针（R4）本身就是实测。
2. LangChain 默认缓存键是否含模型名——需逐行核源码（低优先级；本项目缓存键自含模型字段，不受影响）。
3. kotaemon VLM 图注路线——仅有二手来源佐证（低优先级）。

## 6. 来源清单

| # | 来源 |
|---|---|
| [1] | LlamaIndex Node Parsers / Splitters 官方文档 https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/ |
| [2] | LlamaIndex sentence.py（SentenceSplitter 源码）https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/text/sentence.py |
| [3] | LangChain MarkdownHeaderTextSplitter how-to https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter |
| [4] | RAGFlow v1.0.0 dataset_configuration https://ragflow.io/docs/v1.0.0/dataset_configuration |
| [5] | RAGFlow paper.py v0.15.1 https://github.com/infiniflow/ragflow/blob/v0.15.1/rag/app/paper.py |
| [6] | RAGFlow layout_recognizer.py v0.15.1 https://github.com/infiniflow/ragflow/blob/v0.15.1/deepdoc/vision/layout_recognizer.py |
| [7] | Docling Chunking concepts https://docling-project.github.io/docling/concepts/chunking/ |
| [8] | unstructured chunk_by_title https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/chunking/title.py |
| [9] | Anthropic Contextual Retrieval https://www.anthropic.com/engineering/contextual-retrieval |
| [10] | Docling Serialization concepts https://docling-project.github.io/docling/concepts/serialization/ |
| [11] | Docling issue #3830（markdown 展平丢结构）https://github.com/docling-project/docling/issues/3830 |
| [12] | PaperQA2 settings.py https://github.com/Future-House/paper-qa/blob/main/src/paperqa/settings.py |
| [13] | RAGFlow Excel/CSV 解析源码解析（掘金）https://juejin.cn/post/7569810118169247759 |
| [14] | Unstructured document elements https://docs.unstructured.io/open-source/concepts/document-elements |
| [15] | PubTables-1M / Table Transformer https://arxiv.org/abs/2110.00061 |
| [16] | 表格序列化格式对嵌入检索的影响实证（2026）https://arxiv.org/abs/2604.24040 |
| [17] | Topo-RAG https://arxiv.org/abs/2601.10215 |
| [18] | ColPali https://arxiv.org/abs/2407.01449 |
| [19] | Qdrant PDF retrieval at scale https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/ |
| [20] | M3DocRAG https://arxiv.org/abs/2411.04952 |
| [21] | LlamaIndex GPT-4V 多模态检索官方示例 https://developers.llamaindex.ai/python/examples/multi_modal/gpt4v_multi_modal_retrieval/ |
| [22] | kotaemon https://github.com/Cinnamon/kotaemon |
| [23] | LlamaIndex IngestionCache（Redis）https://developers.llamaindex.ai/python/examples/ingestion/redis_ingestion_pipeline/ |
| [24] | LangChain CacheBackedEmbeddings https://reference.langchain.com/python/langchain-classic/embeddings/cache |
| [25] | Qdrant incremental embedding updates https://qdrant.tech/documentation/tutorials-operations/incremental-embedding-updates/ |
| [26] | Qdrant Points 管理 https://qdrant.tech/documentation/manage-data/points/ |
| [27] | OneUptime：deterministic Qdrant point IDs https://github.com/oneuptime/blog/tree/master/posts/2026-08-28-how-to-generate-deterministic-qdrant-point-ids-and-prevent-duplicate-rag-chunks |
| [28] | LlamaIndex document management pipeline https://developers.llamaindex.ai/python/examples/ingestion/document_management_pipeline/ |
| [29] | RAGFlow PR #9912（重解析替换旧 chunk）https://github.com/infiniflow/ragflow/pull/9912 |
| [30] | openai/CLIP（224×224 输入）https://github.com/openai/CLIP |
| [31] | 方舟多模态向量化 API（待人工核实参数节）https://docs.volcengine.com/docs/ark/multimodal-vectorization-api |
| [32] | 火山 LAS doubao textembedding 算子页 https://docs.volcengine.com/docs/lake-ai-service/photo-textembedding-doubao-series-models |
