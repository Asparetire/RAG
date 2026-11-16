# DocLens 论文删除与回收站（Trash）调研

> 状态：**v1.0（两项目原文/源码核实）**——2026-11-16。动机：用户需求"论文可删除，删除进垃圾桶"；本仓删除面盘点 + 业界范式核实 + 落地方案。
> 调研线：D（DocLens 删除面，全仓代码核实）+ P/O/R（业界实现）。网络备注：web_search 402 余额不足；paperless-ngx/open-webui 经 ghfast.top 镜像直抓原文与源码核实；ragflow.io 站点 JS 渲染抓不到正文（R 线标〔未核实〕）。

## 1. D 线：DocLens 删除面盘点（本仓代码核实）[D1]–[D7]

一篇论文 = **六类资产**，"删除"必须逐一处置：

| # | 资产 | 位置 | 删除时机与方式 |
|---|------|------|----------------|
| 1 | 文档元数据行 | MySQL `t_doc` | 彻底删除时 `DELETE`（FK 级联自动清 `t_chunk`，[D1] init_db.py L55） |
| 2 | 块清单 | MySQL `t_chunk` | FK `ON DELETE CASCADE` 随 t_doc 自动清 |
| 3 | 向量点位 | Qdrant `text`+`image` 两集合 | **已有现成函数** `qdrant_store.delete_doc_points(doc_id)`（M2 先删后插造的，按 payload doc_id 过滤删两集合，返回点数对账，[D2] qdrant_store.py L71） |
| 4 | BM25 索引 | 本地 pickle 全量索引 | **重建路径现成**：`load_units_from_db()`→`build_index()`→`save_index()`（_run_ingest 步骤 4 原样，约 1500 块秒级，[D3]） |
| 5 | 磁盘原件+解析产物 | `data/pdfs/{doc_id}.pdf` + `data/parsed/{doc_id}/`（doc.json/markdown/images） | 彻底删除时删（**唯一不可逆步骤**）；垃圾桶期内保留 |
| 6 | 周边引用 | `t_ctx_prefix`（chunk_id 主键，无 FK）、`t_ingest_task` 行（无 FK）、chat 引用 chip、评测数据集 | 前两者 `chunk_id LIKE '{doc_id}:%'`/`doc_id=%s` 手动清；chip 死态前端已有（M4 `cite-chip.dead`）；评测引用见 §4 边界 |

**关键实证**：
- **检索热路径全程不 JOIN t_doc**——pipeline/hybrid/assets 取块全是 `FROM t_chunk WHERE chunk_id IN (...)`（[D4]）；BM25 读取也只查 t_chunk（[D5] bm25.py L104）。⇒ **只要检索面（Qdrant 点位 + BM25 索引）不含该文档，软删的论文天然从问答消失，查询代码零改动**。
- **嵌入缓存按内容哈希**（`sha256(model+instruction+dim+content)`，[D6]）⇒ 恢复/重放索引时嵌入 API 费用为零，恢复成本只剩 BM25 重建 + Qdrant upsert（秒~分钟级）。
- **幂等补列先例**：init_db.py 已有 `ALTER TABLE t_doc ADD COLUMN category_id/user_id` 失败忽略模式（[D7]）⇒ 加 `deleted_at` 列零迁移风险。
- **API 空白确认**：papers 组现只有 upload/tasks/retry/move/title 五端点，无任何 delete（[D4] api.py）。
- 嵌入缓存 `t_embed_cache` 与文档无关联（内容寻址）⇒ **删除时绝不清缓存**（重传同内容可白嫖）。

## 2. 业界范式 [P1]–[R1]

- **paperless-ngx（文档管理标杆，回收站语义最完整，已核实官方文档原文，[P1]）**：
  - 删除 → 进 trash；**清空前"所有文件和数据库内容完整保留，可随时恢复"**（soft delete，文件不动）；
  - 保留期 `PAPERLESS_EMPTY_TRASH_DELAY` **默认 30 天**自动清；
  - 彻底删除时可配 `PAPERLESS_EMPTY_TRASH_DIR` 把**原始文件**移到外部目录兜底（库信息永久清除）；
  - 细节：重复文件检测把垃圾桶里的文档也计入；根文档删除级联其版本到垃圾桶。
- **open-webui（RAG 知识库同域，硬删派，已核实源码，[O1]）**：
  - 无回收站：删除 = 删向量集合 → 删库行 → 删物理文件（`delete_file_resource` 三连）；
  - **亮点①悬挂引用清扫**：删知识库时同步过滤所有引用它的模型配置（"Update models that reference this knowledge base"）；
  - 亮点②`ENABLE_KNOWLEDGE_FILE_RETENTION` 开关控制"从库移除时是否保留文件"。
- **RAGFlow（旗舰 RAG，〔未核实〕，[R1]）**：HTTP API 有 `DELETE /api/v1/datasets/{id}/documents`（按 ids 批删，文档+块+向量同删）——印象口径为硬删无回收站；站点 JS 渲染无法核实原文。
- **共性总结**：回收站四件套 = **软删标记 + 保留期 + 恢复 + 彻底删除**；文件永远是最后删的；"彻底删除"是不可逆边界，要把最贵的资产（原 PDF）放最后。硬删派（open-webui/RAGFlow）牺牲可恢复性换实现简单。

## 3. 方案对比与推荐

| 方案 | 机制 | 恢复成本 | 热路径风险 | 结论 |
|------|------|----------|-----------|------|
| A 纯查询期过滤 | 软删标记，索引原地保留，查询时 must_not 排除 | 零 | **高**：动 pipeline 查询过滤器；BM25 索引仍含已删文档（索引泄漏）；排除列表随删除数膨胀 | 不推荐 |
| **B 软删+检索面移除（推荐）** | `t_doc.deleted_at` 打标 + 删 Qdrant 点位 + BM25 重建；**DB 行与文件原地保留** | 低（嵌入缓存命中，重放索引分钟级） | **零**：检索代码一行不改 | ✅ paperless-ngx 同款语义 |
| C 文件回收站 | 删 DB 行+向量，文件移 `data/trash/` | 高（t_doc 已删，恢复=全量重入库+重建元数据） | 零 | 垃圾桶元数据要扫盘拼装，体验差；否 |

**推荐 B**：删除的瞬间用户预期是"从问答和列表里消失"，而非"物理销毁"——检索面移除即时达成，DB 行+文件保留是恢复的资本；paperless-ngx 实证该语义可长期维护。

## 4. 落地设计（→ runbook）

1. **库**：init_db 幂等补列 `ALTER TABLE t_doc ADD COLUMN deleted_at DATETIME NULL`（+可选 `deleted_by`）。
2. **API 五端点**（papers 组内）：
   - `DELETE /api/papers/{doc_id}` → 进垃圾桶（软删）；
   - `GET /api/papers/trash` → 垃圾桶列表（doc_id/title/n_chunks/deleted_at）；
   - `POST /api/papers/{doc_id}/restore` → 恢复（清标记+重放索引：process_doc+BM25 重建，复用 `_INGEST_LOCK` 防与入库竞争）；
   - `DELETE /api/papers/{doc_id}/purge` → 彻底删除单篇；
   - `POST /api/papers/trash/empty` → 清空垃圾桶（逐篇 purge）。
3. **paperlib 三函数**（注意顺序——先摘检索面再打标记，失败即回滚标记）：
   - `soft_delete_doc`：`_INGEST_LOCK` 内 delete_doc_points→BM25 重建→`UPDATE deleted_at=NOW()`；对 `t_ingest_task` 处于 queued/parsing/indexing 的文档拒绝删除（防与入库竞争）；
   - `restore_doc`：清标记→Qdrant upsert（嵌入缓存命中）→BM25 重建；
   - `purge_doc`：delete_doc_points（幂等重放）→`DELETE t_doc`（级联 t_chunk）→清 `t_ctx_prefix`/`t_ingest_task`（LIKE/doc_id）→**最后**删 `data/pdfs/{doc_id}.pdf` + `rmtree data/parsed/{doc_id}/`。
4. **过滤面清单**（全部加 `deleted_at IS NULL`）：list_papers、list_tree 分类计数、delete_category 的"分类下仍有论文"判断、`GET /api/docs`、上传 sha256 去重（命中垃圾桶中的同 doc_id → 409 改文案"该论文在垃圾桶中，请先恢复"）。
5. **前端**：论文卡片"删除"按钮+确认模态框（复用 4.8 modal 范式）；树头部垃圾桶入口 → 垃圾桶模态框（标题/删除时间/恢复/彻底删除/清空，2s 轮询复用任务范式可后置）；删除后对话里的旧引用 chip 自然落 `dead` 态（已有）。
6. **边界与注意**：
   - 评测：L1 题集（126 题）引用的文档被 purge 后重跑该题失败——purge 前提示"评测数据引用此论文"或仅文档注明；t_eval_result 历史数据不受影响；
   - 自动清空：MVP 只做手动"清空"；后续可仿 sweep_stale_tasks 挂启动扫描 + `TRASH_RETENTION_DAYS`（paperless 默认 30 天口径）；
   - 可选兜底：purge 时把原 PDF 移 `data/trash_files/` 而非直接删（paperless `PAPERLESS_EMPTY_TRASH_DIR` 同款），磁盘富余（458G）下建议做；
   - 双端纪律：data/ 不入库，垃圾桶状态在 DB（t_doc.deleted_at），双端通过共享 MySQL 天然一致——但文件恢复/清理只发生在执行操作的机器，需注明"文件操作在服务端容器执行"。
7. **工作量估计**：后端 1 天（3 函数+5 端点+过滤面+单测：soft/restore/purge/去重联动）+ 前端 0.5 天（删除按钮+垃圾桶模态框）+ runbook/CHANGELOG 1h。

## 5. 来源清单

| 线 | 来源 |
|---|---|
| D 线 | [D1] scripts/init_db.py（FK 级联/幂等补列）；[D2] doclens/index/qdrant_store.py（delete_doc_points/uuid5）；[D3] doclens/paperlib.py L420-425（BM25 重建三连）；[D4] doclens/serve/api.py（端点盘点）；[D5] doclens/index/bm25.py + doclens/retrieve/hybrid.py + doclens/pipeline.py（热路径只查 t_chunk）；[D6] scripts/init_db.py t_embed_cache（内容哈希缓存）；[D7] doclens/paperlib.py（分类计数/任务状态机） |
| P 线 | [P1] paperless-ngx docs/usage.md "Document Trash" 段（ghfast.top 镜像原文核实：软删保留一切/30 天默认/PAPERLESS_EMPTY_TRASH_DIR/重复检测含垃圾桶） |
| O 线 | [O1] open-webui backend/open_webui/routers/knowledge.py（ghfast.top 源码核实：delete_file_resource 三连硬删/悬挂引用清扫/ENABLE_KNOWLEDGE_FILE_RETENTION） |
| R 线 | [R1] RAGFlow HTTP API 参考（ragflow.io JS 渲染抓不到正文，删除语义〔未核实〕） |
