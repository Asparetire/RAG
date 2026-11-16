# M6 论文删除+回收站（Trash）实现计划（runbook）

> 依据：specs/research/m6-paper-trash-survey.md v1.0（方案 B：软删+检索面移除）。slug：`m6-trash`。

## 1. 目标与验收标准（可执行验证）

- **R1 删除进垃圾桶**：`DELETE /api/papers/{doc_id}` 后——论文列表/分类树计数/`GET /api/docs` 立即不可见；问答检索不到该文档内容（Qdrant 点位摘除+BM25 重建）；`GET /api/papers/trash` 可见；`t_doc` 行与两处磁盘资产（`data/pdfs/{doc_id}.pdf`、`data/parsed/{doc_id}/`）**原样保留**。
- **R2 恢复**：`POST /api/papers/{doc_id}/restore` 后一切回到删除前状态（列表可见、检索可命中；嵌入缓存命中→零 API 费用）。
- **R3 彻底删除/清空**：`DELETE /api/papers/{doc_id}/purge`、`POST /api/papers/trash/empty` 后——DB 无行（t_doc 删除级联 t_chunk；t_ctx_prefix/t_ingest_task 手工清）、Qdrant 无点、`data/parsed/{doc_id}/` 已删；**PDF 原件移入 `data/trash_files/{doc_id}.pdf` 兜底**（paperless EMPTY_TRASH_DIR 同款，不真删）；评测历史 `t_eval_result` 不受影响。
- **R4 去重联动**：上传与垃圾桶中同 doc_id 的文件 → 409 文案"该论文在垃圾桶中，请先恢复"。
- **R5 状态守卫**：文档最新入库任务处于 queued/parsing/indexing → 拒绝删除（422"该论文正在入库，请稍后再删"）。
- **R6 前端**：论文卡片"删除"按钮（确认模态框）+ 树头部"垃圾桶"入口（模态框：标题/删除时间/恢复/彻底删除/清空，复用既有 modal 机制与 authedFetch）。

## 2. 现状调查（复用点与约束）

- **已有零件**（调研 D 线核实）：`qdrant_store.delete_doc_points(doc_id)` 两集合按 payload 删点；BM25 全量重建三连（load_units_from_db→build_index→save_index，_run_ingest 步骤 4 内联）；嵌入缓存 `t_embed_cache` 内容寻址（恢复零 API 成本）；init_db 幂等补列先例（category_id/user_id）；`t_chunk` FK 级联。
- **热路径约束**：pipeline/hybrid/assets 全部按 `chunk_id` 回表、不 JOIN t_doc ⇒ 软删无需改任何查询代码。
- **前端**：`PaperLibrary.jsx` 有成熟 modal 状态机（move/new/rename/renamePaper 四种 kind）与 `authedFetch`，删除/垃圾桶扩展为新增两种 kind + 一个数据加载函数。
- **端点现状**：papers 组仅 upload/tasks/retry/move/title，无 delete（api.py）；`GET /api/docs`（api.py L173）需加过滤。
- **鉴权**：所有新端点挂既有 `@protected` 路由（Bearer/cookie 双通道自动继承）。
- **部署约束**：Python 代码改动需重启 uvicorn（`scripts/start_server.sh`）生效；前端改动需 `npm run build` 且 dist 入库（StaticFiles 即时生效）；重启会杀进行中解析任务（启动扫描标 failed）——**执行前确认无进行中任务**。

## 3. 技术方案（关键决策 + 被否方案）

- **D1 软删列**：`t_doc` 补 `deleted_at DATETIME NULL` + `deleted_by VARCHAR(64) NULL`（幂等 ALTER）。被否：独立 t_trash 表（多一张表两处状态源，paperless 实证单列标记足够）。
- **D2 删除顺序**（失败可回退）：`_INGEST_LOCK` 内 → ① delete_doc_points ② BM25 重建 ③ `UPDATE deleted_at`。标记最后打：①② 幂等可重放，中途失败重试无害。
- **D3 恢复同步执行**：嵌入缓存命中 ⇒ 秒~分钟级；单管理员低频操作。被否：后台任务化（复用 t_ingest_task 需新增 restoring 状态，前端轮询联动，收益不成比例）。
- **D4 purge 顺序**（不可逆点最后）：delete_doc_points（幂等）→ `DELETE t_doc`（级联 t_chunk）→ 清 `t_ctx_prefix`（`chunk_id LIKE '{doc_id}:%'`）与 `t_ingest_task`（`doc_id=%s`）→ `rmtree data/parsed/{doc_id}/` → **PDF 移 `data/trash_files/` 兜底**。DB 三步一事务；文件操作放提交后（失败留孤儿文件仅记日志，不回滚 DB）。
- **D5 BM25 重建抽公共函数**：`bm25_rebuild()` 放 `doclens/index/bm25.py`，ingest/_run_ingest/soft_delete/restore 四处共用（消重复，M3 起三连代码已复制两份）。
- **D6 过滤面统一**：所有 t_doc 列表加 `deleted_at IS NULL`；**不清** `t_embed_cache`（内容寻址与文档无关）；`t_ingest_task` 软删期保留（历史可查），purge 才清。
- **D7 保留期**：MVP 仅手动"清空"；自动清空（paperless 30 天口径）留 M6+ 后续（启动扫描挂点已有）。

## 4. 变更清单（文件级）

| 文件 | 变更 | 职责 |
|---|---|---|
| `scripts/init_db.py` | 改 | 幂等补列 deleted_at/deleted_by |
| `doclens/index/bm25.py` | 改 | 新增 `bm25_rebuild()`（三连封装，原地复用 load/build/save） |
| `doclens/paperlib.py` | 改 | 新增 soft_delete_doc/list_trash/restore_doc/purge_doc；list_papers 加过滤；delete_category 计数加过滤 |
| `doclens/serve/api.py` | 改 | 5 新端点；GET /api/docs 加过滤；上传去重 409 文案（区分"在垃圾桶"）；R5 守卫 |
| `tests/test_paper_trash.py` | 新增 | 单测 ~10 条（见 §6） |
| `web/src/components/PaperLibrary.jsx` | 改 | 卡片删除按钮+del 确认模态框+trash 列表模态框（恢复/彻底删除/清空）+loadTrash |
| `web/src/styles.css` | 改 | 垃圾桶模态框列表样式（少量，复用 modal/paper-table） |
| `web/dist/**` | 重建 | `npm run build` 产物入库（交付态） |
| `specs/plans/m6-trash-runbook.md` | 本文件 | — |
| `specs/reviews/m6-trash.review.md` | S3 产出 | 代码审查 |
| `CHANGELOG.md` | 改 | 收尾条目 |

## 5. 分步任务

1. **库+BM25 封装**：init_db 补列；bm25.bm25_rebuild()；_run_ingest 步骤 4 改调共用函数。验收：pytest 全量绿。
2. **paperlib 四函数**：soft_delete_doc/list_trash/restore_doc/purge_doc + list_papers/delete_category 过滤。验收：单测 R1-R3 逻辑路径。
3. **API 端点**：5 端点+GET /api/docs 过滤+去重 409 文案+R5 守卫。验收：单测 + 本地起服务 curl 冒烟（登录→删→垃圾桶→恢复→purge）。
4. **前端**：删除按钮/确认框/垃圾桶模态框。验收：`npm run build` 成功 + 手动双端冒烟。
5. **部署验证**：push server → 容器确认无进行中任务 → `bash scripts/start_server.sh` → 容器实测全链路（含删除司尔特外的测试文档）。验收：四端点 200/404/409/422 符合预期。
6. **S3 审查+收尾**：code-review → 修复 → CHANGELOG → 双端 push（origin 视网络）。

## 6. 测试策略（普通实现，不走 TDD）

新增 `tests/test_paper_trash.py`（monkeypatch connect/qdrant/bm25，纯逻辑）：
1. soft_delete 打标+返回点数对账+文件仍在位；2. soft_delete 幂等重放（重复删除 404/无害）；3. R5 守卫拒绝进行中任务；4. restore 清标记+重放调用序；5. restore 未删除文档 → 422；6. purge 清 DB（级联+前缀清理 SQL 断言）+parsed 删除+PDF 移 trash_files；7. purge 未在垃圾桶的文档 → 422（防跳过软删直接物理删）；8. list_papers 过滤；9. list_trash 字段；10. bm25_rebuild 封装与旧三连等价。既有 212 条全量回归。

## 7. 风险与回滚

- **并发**：删除/恢复/purge 全进 `_INGEST_LOCK`（与入库互斥）；R5 守卫拒绝进行中任务。
- **误删**：确认模态框（R6）+ purge 二次确认 + PDF trash_files 兜底 + parsed 目录可由 PDF 重解析再生（代价：MinerU 分钟级）。
- **孤儿文件**：文件操作在 DB 事务后，失败仅日志（下次 purge 重试幂等清理）。
- **回滚**：功能单提交可 `git revert`；deleted_at 列残留无害（无代码引用即透明）。

## 8. 敏感代码判定

**否**——不新增认证/授权逻辑（全部挂既有 `@protected`）；无外部 API/凭据/PII；SQL 全参数化（无拼接注入面）；文件操作限定 `data/` 内且 doc_id 经 `^[0-9a-f]{12}$` 格式校验（沿用 assets.py DOC_ID_RE 守卫）。依据工作流 S4 判据逐项核对不命中 ⇒ 跳过安全专项复查，S3 通用审查中加"破坏性操作确认"审查条目。

## 9. 执行命令

- 测试（Windows 侧）：`D:\soft\anaconda\envs\doclens\python.exe -m pytest tests/ -q`
- 前端构建：`cd web && npm run build`
- 容器部署：`git push server master` → 容器 `bash /home/doclens/RAG/scripts/start_server.sh`（先确认无进行中入库任务）
- 冒烟：容器内登录 curl 五端点 + 浏览器双端实测

---
## 确认门记录（S2 开始前填写）
- 批准时间：2026-11-16 16:35（Asia/Shanghai）
- 批准指令原文："yes, 严格使用 tdd-workflow 实施（走 TDD）"
- TDD：是（RED→GREEN→重构→覆盖率，新增/改动代码覆盖率 ≥80%）

## 执行记录（S2-S5）

- **TDD 循环**：12 个循环（软删/幂等/守卫/恢复/拒绝恢复/purge/拒绝物理删/两处过滤/垃圾桶列表/bm25 编排固化/端点×4）——循环 2/3/10 在 GREEN 时已由前置循环最小实现覆盖（标记"已覆盖"，测试保留固化行为）；其余 RED→GREEN 严格推进。
- **覆盖率**（新增/改动行）：bm25.bm25_rebuild、paperlib 回收站段 L362-515、api.py 新端点 L358-398 + GET /api/docs 过滤 + 上传去重改动——**100%**（missing 项均为既有代码）。全量 231 passed。
- **部署冒烟（容器实测，2026-11-16 17:1x）**：删除→removed_points=27→清单/侧栏/Qdrant 全不可见→垃圾桶可见→恢复→**点位 27 回归**→垃圾桶空；磁盘资产完好；卡死任务 37（b056，parsing 2h+）被启动扫描标 failed 可重试；新 bundle index-CTp4u6I4.js 上线；trash 端点无鉴权 401 ✓。
- **冒烟抓真 bug 一枚**：restore 初版 force=False → doc_hash 未变被 process_doc 增量跳过（零写入）→ 恢复后点位丢失；TDD 补断言 force=True 修复复验通过（commit 9ef6fa4）。
- **部署插曲**：init_db 幂等补列先行；发现 189e/44a8 两篇的 t_doc 行与解析产物在 15:30-17:10 间被并行会话清理（非本会话操作，PDF 仍在可重入库）；git add -A 误提交并行会话的 17 个 scripts/_diag_* 脚本（已入库，保留避免破坏其工作区）。
