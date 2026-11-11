# M2 索引 Runbook

> **状态：待确认（停在确认门 G1）** ｜ slug：`m2-indexing` ｜ 依据：[主计划 §5 M2](doclens-multimodal-rag.plan.md)、[PRD FR-2.1~2.6](../prds/doclens-multimodal-rag.prd.md)、[m1-runbook](m1-runbook.md)（M1 产物即 M2 原料）
> **用户决策（2026-11-11）**：① 解析维持 **CPU 方案**（GPU 探针实验入待办池，将来批量扩语料再做）；② 表格多级表头处理（表格 v2）**并入 M2 开工首项**；③ 实现方式默认延续**普通实现**（不走 TDD）；④ 表格 v2 升级为**结构理解管线（规则版）**——区分列名/行名、剔除无效区域、输出 manifest、125 表全量人工审计；LLM/VLM 仲裁留待财报泛化包（2026-11-11 评审选档）
> **评审修订（2026-11-11，随 G1 一并确认）**：§4 步骤编号修正、幂等写入机制、t_chunk 回表（补 FR-2.4 坐标与正文取回）、K1 内容过滤与切块细则、表格卡片、风险表补充——详见 §3.1 及各节标注；同类项目调研（[m2-indexing-survey](../research/m2-indexing-survey.md)）印证主线方案，R1–R6 小修订已并入（正文标注"调研 R#"）

---

## 1. 目标与验收标准（可执行验证）

| 验收项 | 验收方式 | 通过标准 |
|---|---|---|
| 全量入库 | `python scripts/ingest.py`（容器内） | 11 篇全部入库：Qdrant 两集合点数与 chunk 统计一致；BM25 索引含全部文本单元；MySQL 元数据齐（chunk_id 回表可取 content/bbox/heading_path） |
| 增量幂等 | 重跑 `ingest.py` | **零 API 调用**（doc 级跳过 + 嵌入缓存双保险，以 ingest 收尾汇总输出为证）、点数不变、无重复 |
| 检索抽检 | `scripts/search_probe.py` 跑 10 条中文查询（英文语料；查询清单版本化存 `data/probe_queries.json`） | top-5 基本相关（人工判定，主计划 M2 验收线；表格召回一般不算失败，见 §7 风险表） |
| 表格 v2（结构理解） | manifest + 质检报告刷新 + **125 表全量人工过目（约 1h）** | 列名/行名判定正确（无效内容零混入）；两级表头拼接语义保留（`一级/二级`）；排除清单零误伤数据行 |
| E 档试产 | contextual 100 块试跑（text/table/caption 分层抽样） | 耗时与量级记录进 cost.md |
| 里程碑 | commit（每步一个）+ `git tag m2` + push | 双端同步 |

## 2. 现状调查（2026-11-11 实测）

| 项 | 现状 | 结论 |
|---|---|---|
| M1 原料 | 11 篇 `data/parsed/<doc_id>/`（doc.json + 原始 JSON + images/）；manifest 含 title/doi，11 个 DOI 唯一 | 原料齐备，直接开工 |
| MySQL | 空库（无表） | 2.2 建 5 张表 |
| Qdrant | 空集合（HTTP 明文 + API key，容器内网直连可接受；warning 已知） | 2.4 建两集合 |
| 嵌入端点 | `ARK_EMBED_BASE_URL=coding/v3` 已验证放行 multimodal（M0 决策①）；config 有三段官方 instructions 模板；M0 冒烟单条文本/图像嵌入均 2048 维通过 | 客户端有既定路径 |
| 依赖 | httpx/PyMySQL/qdrant-client/rank-bm25/jieba/numpy/pillow 均已装 | 不新增依赖（表格网格化用标准库 `html.parser`） |
| GPU | 4×RTX 4090D 直通可见，但推理库为 CPU 版；用户拍板维持 CPU | 仅记录，不行动 |
| 语料规模预估 | 3838 块 → 约 2000 文本 chunk（含 ~200 caption 文本块）+ 125 表 + 329 图 ≈ **2450 次嵌入调用**（References 过滤后约 -10–15%）；329 图构成待 2.0 核对（公式截图占比） | 量级可控 |

## 3. 技术方案（关键决策）

| # | 决策 | 方案 | 被否方案与理由 |
|---|---|---|---|
| K1 | **切块粒度**（M2 首要决策） | **节内聚合**：同 `heading_path` 的连续 text 块合并成 800–1600 字符 chunk（约 300–500 token；目标区间非硬限——短节独立成块，宁短勿跨节）；超限按句切分（单句超限硬切）；标题块不单独入库（作 heading 前缀，不计入字符预算）；跨节不合并。**内容过滤**：References/Bibliography 节不入库；页眉页脚/碎片块按重复性判定丢弃——无标题归属且跨页重复出现 >1 次才删，单次出现保留（RAGFlow 先例，防误删正文，调研 R1）。表格 = 1 chunk（表格卡片 + 清洗后 markdown，见 K2）；图片 = caption 文本 chunk（kind=caption）。细则见 §3.1 | Block 直接入库：双栏论文碎片块太多（"Article"/"Received:..."），检回即噪声；整节巨块：超过嵌入输入上限且稀释语义；不过滤 References：引用条目 BM25 高频误召回，污染检索体验 |
| K2 | 表格 v2 = **结构理解管线**（规则版） | 新增 `doclens/parse/table_struct.py`，四步：① `html.parser` 网格化——rowspan/colspan 复制补全对齐网格（v1 正则丢属性，实为重写）；② **无效区域规则标记**——空白格 / 分隔行 / 脚注行（Note、注：、\*、† 前缀）/ 合计行（Total、Average、Mean、合计、小计、总计）/ 全宽说明行 / 分组带；③ **清洗后的网格**上判定（先扫地再认门牌）——列名 = 顶部连续表头行逐列拼接（`一级/二级`），行名列 = 首列非数字 + 高唯一度；判定从保守，宁漏拼不错拼；④ 每表输出 **manifest**（columns / row_labels / excluded+理由+去向）随 doc.json 落盘。**排除分级**：空白/分隔丢弃；表注/合计行不当结构、但保留至 chunk 尾部。从缓存 raw JSON 重建 doc.json（不重跑 MinerU） | LLM/VLM 仲裁：留待财报泛化包（中文表格噪声更杂，届时做规则 vs LLM 对比位），M2 英文表 125 张规则可覆盖且可全量人工审计；保留 HTML 原文进 Block：raw 已落盘可回溯，模型层不冗余 |
| K3 | 嵌入 | 单条请求 + asyncio 并发（并发 4，指数退避重试 3 次）；文本用 `CORPUS_TEXT_INSTRUCTION`，图像用 `CORPUS_IMAGE_INSTRUCTION` + base64（单图单请求，D3 既定） | 批量接口：coding/v3 multimodal 未验证 batch，探针再议 |
| K4 | 嵌入缓存 | MySQL `t_embed_cache`：键 = sha256(model+instruction+dim+content)，MEDIUMBLOB 存向量（float32→bytes）。先查缓存再调 API——增量与消融重跑都省钱 | 文件缓存：SQL 便于 M5 评测时按键统计 |
| K5 | Qdrant | 两集合：`doclens_text`（2048, cosine, payload: doc_id/chunk_id/kind/page/heading_path）、`doclens_image`（payload: doc_id/image_path/page/caption/bbox）。**点 ID = uuid5(chunk_id)，upsert 幂等**。A 档与 B 档差异用 kind 过滤实现（A=text，B=text+table+caption），不建多余集合；text 集合的正文/bbox 不进 payload，走 t_chunk 回表（§3.1） | 每档一集合：维护翻倍，payload 过滤足够 |
| K6 | BM25 | rank-bm25 + jieba（`jieba.lcut` 中英通吃，小写化）；索引落 `data/bm25/`（**pickle 存分词语料** + chunk 元数据 jsonl）；增量 = 从 t_chunk 加载语料重建 BM25Okapi（对象不可 extend，IDF 随语料重算） | Qdrant sparse：调优面大（D5 既定） |
| K7 | E 档前缀 | `contextual.py` 生成 50–100 token 前缀（ctx_model=deepseek-v4-flash）存 `t_ctx_prefix`；**M2 只做模块+100 块试产**（text/table/caption 分层抽样），全量向量在 M5 按需生成（嵌入缓存兜底） | M2 全量生成：2000 次额外调用，M5 才用得上 |

### 3.1 实施细则（2026-11-11 评审补充，随 G1 一并确认）

- **切块细则**：句边界 = 句末标点（.?!）+ 空白；heading 前缀 = `" / ".join(heading_path)` + 换行接正文，不计入 800–1600 预算（主流做法前缀占预算以防嵌入超限；本项目前缀 ~100–200 字符 + 正文 1600 仍远低于方舟嵌入输入上限，维持现设计、理由记录——调研 R3）；页眉页脚判定 = 无标题归属**且**跨页重复出现 >1 次才删，单次出现保留（RAGFlow 先例，防误删正文——调研 R1）；节内句切块间**不加 overlap**（主流默认 200 token，代价 chunk 数 +10–20%，记为 M5 消融位——调研 R2）；公式块（M1 映射 equation→text）随正文聚合，LaTeX 串不做特殊处理；caption 文本块天然短，不适用聚合。
- **表格卡片**：表格 chunk 文本 =【表注】+【列】列名清单 +【行】行名清单的单行卡片（无表注/行名的表自动省略对应段）+ 清洗后 markdown 主体 + 尾部保留的表注/合计行——密集自然语言同时喂饱嵌入与 BM25，机制化改善表格检索。
- **无图注图**：仅图像向量入 image 集合（M3DocRAG 先例；调研未发现"默认丢弃"先例）；VLM 合成 caption（高价值图）与装饰图降权列为财报泛化包/扩语料阶段可选——调研 R5。
- **数据链路（补 FR-2.4 坐标与正文取回）**：`t_chunk` 为单一事实源，覆盖全部索引单元（text/table/caption/image；image 单元 content 记 caption 可空、另存 image_path），字段 content/bbox/kind/page/heading_path/content_hash；两集合点 ID 均为 uuid5(chunk_id)；Qdrant/BM25 命中后按 chunk_id 回表取正文与坐标（M3 生成、M4 高亮共用此路径）；chunk_id = `{doc_id}:{doc 内序号}`。
- **增量语义**：`t_doc` 存 doc.json 全文 hash——未变文档整篇跳过（零 API + 零写入，2.8 幂等验收的机制保障）；变化文档按 doc_id 先删后插（Qdrant delete-by-filter + t_chunk 删行），BM25 从 t_chunk 全量重建（~2000 块分词秒级）。`--force` = 忽略 doc 级跳过强制重建（嵌入缓存仍生效，不重复计费）。
- **实现注意**：PyMySQL 为同步库，asyncio 并发中 DB 读写走 `asyncio.to_thread` 或统一串行，避免阻塞事件循环；全量嵌入前看一眼方舟控制台额度余量（用户既定纪律）。

## 4. 变更清单（文件级）

| 动作 | 文件 | 职责 |
|---|---|---|
| 修改 | `doclens/parse/mineru_parser.py` | 表格 v2：接入 table_struct 管线，manifest 随 doc.json 落盘（2.0） |
| 新增 | `doclens/parse/table_struct.py` | K2 结构理解管线：网格化 / 无效区域标记 / 列名行名判定 / manifest（2.0） |
| 新增 | `doclens/index/chunker.py` | K1 节内聚合 + 内容过滤（2.1；主计划未列此文件，随收官补记） |
| 新增 | `doclens/index/embeddings.py` | 嵌入客户端 + MySQL 缓存（2.3） |
| 新增 | `doclens/index/qdrant_store.py` | 集合管理 / 上传 / uuid5 点 ID / 过滤查询（2.4） |
| 新增 | `doclens/index/bm25.py` | BM25 构建 / 加载 / 重建式增量（2.5） |
| 新增 | `doclens/index/contextual.py` | E 档前缀生成 + 缓存（2.6） |
| 新增 | `scripts/init_db.py` | 5 张表幂等创建（2.2） |
| 新增 | `scripts/ingest.py` | 全量/增量编排入口：doc 级跳过 / 先删后插 + 收尾汇总（2.7） |
| 新增 | `scripts/search_probe.py` | 10 查询抽查工具（2.7；查询清单版本化存 `data/probe_queries.json`，M5 可复用对照；M3 被 hybrid 取代） |
| 修改 | `scripts/quality_report.py` | 表格 manifest 审计汇总（2.0） |
| 新增 | `tests/test_table_struct.py`、`tests/test_chunker.py` 等 | 每模块关键路径单测（表格夹具取真实难表） |
| 修改 | `reports/cost.md`、`CHANGELOG.md`、`AGENTS.md` | 记录 |

MySQL 五张表：`t_doc`（文档元数据 + doc.json 全文 hash，增量跳过依据）、`t_chunk`（块全量字段：content/bbox/kind/page/heading_path/content_hash/image_path——检索回表单一事实源）、`t_embed_cache`（嵌入缓存）、`t_ctx_prefix`（E 档前缀）、`t_eval_result`（M5 评测，先建结构）。

## 5. 分步任务（执行顺序）

| 步 | 任务 | 验收 | 依赖 |
|---|---|---|---|
| 2.0 | **前置抽查** raw JSON（`<th>` 有无 / 表格截图路径 / 跨页表是否被切成两块 / 329 图构成）→ table_struct 管线 + manifest + 缓存重建 11 篇 + 质检刷新 + **125 表全量人工审计** | 列名/行名正确、无效内容零混入、排除零误伤（单测夹具用真实难表 + 全量过目） | 无 |
| 2.1 | chunker.py（聚合 + References/碎片过滤）+ 单测 | 聚合数/尺寸分布合理；heading 前缀正确；过滤规则生效 | 2.0 |
| 2.2 | init_db.py 容器建表 | SHOW TABLES 5 张齐 | 无 |
| 2.3 | embeddings.py + 缓存 + 单测 | 同输入二次调用零 API 费（缓存命中日志） | 2.2 |
| 2.4 | qdrant_store.py（uuid5 点 ID + doc 级先删后插）+ 单测 | 建集合/上传/过滤查询可用；同 doc 重跑点数不变 | 无 |
| 2.5 | bm25.py + 单测 | 中英混合查询命中 | 无 |
| 2.6 | contextual.py + 100 块试产（分层抽样） | 成本入 cost.md | 2.2 |
| 2.7 | ingest.py + search_probe.py（doc 级跳过/重建 + 收尾汇总输出）；全量嵌入前跑图像探针：2–3 张真实切图 + 长边 ~1024px 降采样前后向量一致性对照（调研 R4） | 全量跑通；汇总输出 API 次数/缓存命中/点数；探针结果入 cost.md | 2.1–2.5 |
| 2.8 | 实测验收：全量 → 增量幂等 → 10 查询抽查 | 见 §1 | 2.7 |
| 收尾 | CHANGELOG + tag m2 + 主计划补记（chunker.py/table_struct.py 入文件树、工期 1→2 天）+ Next Action；README/收官报告写入"表格 manifest+卡片=差异化卖点"（调研 R6） | 双端同步 | 2.8 |

## 6. 测试策略（普通实现）

- 每模块关键路径单测 ≥1 条；缓存键、chunk 聚合与内容过滤、表格网格化/无效区域标记/表头行名判定/manifest 生成为纯逻辑重点。
- 表格夹具取真实难表：多级表头、Note 脚注、Average 合计行、分组带各 1–2 张。
- 集成验收走容器真实调用（嵌入 API/Qdrant/MySQL 不进单测）。
- 新增逻辑覆盖率目标 ≥80%（纯逻辑部分）。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| coding/v3 并发限制/限流 | 先 10 条探针；并发 4 起步可调；退避重试 | 降并发或串行 |
| 超长 chunk 超嵌入输入上限 | K1 上限 1600 字符兜底 | 调阈值 |
| 嵌入质量不达预期（无公开基准） | 10 查询抽检早暴露；调 instructions/维度 | M5 消融兜底（主计划风险表既定） |
| 重复计费 | 缓存先行 + doc 级跳过 + 增量幂等验收 | — |
| Qdrant/MySQL 数据损坏 | 重建成本低（缓存令重嵌入近零），snapshot 兜底 | 重建 |
| 真实切图体积/分辨率超 API 上限 | M0 冒烟用的是合成小图；2.7 全量前跑真实切图探针：2–3 张 + 长边 ~1024px 降采样对照（调研 R4） | pillow 降采样重试 |
| 表格线性化检索天然偏弱 | 表格卡片前置（表注+列名+行名）；抽检表格召回一般≠失败，M5 B 档对比才是判定时刻 | 调卡片构成/instructions |
| MinerU 表格结构识别错误（无边框/跨页表） | 2.0 抽查专挑最难表；K2 判定从保守（宁漏拼不错拼） | 人工修正 manifest |

## 8. 敏感代码判定

**是（敏感）**：外部 API 调用（方舟嵌入）+ 凭据使用（ARK_API_KEY、MySQL 密码）。实现完成后走 S4 安全复查：key/密码不入日志不入错误信息、`.env` 不入库、Qdrant 明文 HTTP+key 的内网边界确认。

## 9. 执行命令

```bash
# 容器内（doclens 环境）
python scripts/init_db.py
python scripts/ingest.py            # 全量；重跑即增量（doc 级跳过）
python scripts/ingest.py --force    # 忽略 doc 级跳过、全部重建（嵌入缓存仍生效，不重复计费）
python scripts/search_probe.py      # 10 查询抽查（清单：data/probe_queries.json）
pytest                              # 双端
```

---
## 确认门记录（S3 实施开始前填写）

- 批准时间：2026-11-11 14:54（北京时间）
- 批准指令原文：开始M2的发开工作 保证工作质量
- TDD：否（延续 M1 普通实现）
