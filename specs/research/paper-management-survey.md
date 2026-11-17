# DocLens 论文批量入库与论文管理完善调研

> 状态：**v1.0（本仓代码核实 + 两竞品源码/文档核实）**——2026-11-17。动机：用户需求"① 论文支持批量入库；② 论文管理功能完善，失败了的论文怎么处理"。本调研 = 批量入库实现范式 + 管理面（重点失败处理）缺口盘点与落地清单。
> 网络备注：web_search 402 余额不足（同 2026-11-16）；raw.githubusercontent.com 被网络策略拦截；paperless-ngx 官方文档（main 分支 markdown 源）与 RAGFlow SDK 源码经 ghfast.top 镜像直抓核实；open-webui 删除面沿用 2026-11-16 已核实事实 [O1]，其批量上传行为〔未核实〕。

## 1. D 线：DocLens 上传/任务/管理面盘点（本仓代码核实）[D1]–[D9]

- **[D1] 单篇上传链路**（api.py:245-286）：读内存 → validate_upload（文件名/大小）→ sha256 → t_doc 重复/垃圾桶检查（409 两种文案）→ 落 `data/pdfs_inbox/` → create_task（状态"排队中"）→ daemon 线程跑 `_run_ingest`（paperlib.py:532）。
- **[D2] 任务状态机**：排队中 → parsing(0.05) → 0.4(解析完成) → indexing(0.5) → completed；error 独立终态。逐文件独立任务行（t_ingest_task）。**batch_id 字段与按批查询已就绪**（paperlib.py:327 get_tasks_by_batch；qasper-batch 先例为脚本批量建行），但入口只有单文件。
- **[D3] 并发即串行**：`_INGEST_LOCK` 全局锁（paperlib.py:36,547）——任意来源的入库（上传/重试/批处理）在锁上自然排队；**并发提交 N 个文件 = N 个线程堆在锁上**（线程堆积但解析不并发）。
- **[D4] 失败可见性缺口（重大）**：`list_active_tasks` 仅查 `queued/parsing/indexing`（paperlib.py:319）——**error 任务不出现在前端"进行中"区**，任务失败瞬间即从 UI 消失；而前端 TaskStatusMeta 已有完整 error 徽标渲染（PaperLibrary.jsx:12,79-82，title 提示 + 前 40 字错误）——**设计-实现脱节**；前端全文件无重试按钮（`/api/papers/tasks/{id}/retry` 端点 api.py:293-328 是孤岛）。
- **[D5] inbox 无生命周期管理**：`pdfs_inbox` 全后端仅 api.py:276 一处写入，无任何删除/移动——**成败皆永久堆积**（昨日 b056 的 inbox 文件实证仍在）。
- **[D6] 孤儿解析进程**：uvicorn 重启杀等待线程 → mineru subprocess 失去 1800s 超时看护 → 永久孤儿（2026-11-16 实证：4 进程 8h 零产出、单进程 1200% CPU，详见 CHANGELOG 2026-11-16 孤儿化条目）。
- **[D7] 重试端点限制**：要求 doc_id 已生成 + canonical PDF 存在（api.py:308-323）——校验阶段就失败（未生成 doc_id）的任务不可重试，只能重传。
- **[D8] 失败原因可读性**：error 字段存原始异常文本（如 "MinerU 重试后仍失败：...timed out after 1800 seconds"）——对新手不可读，无"建议错峰重试/检查文件/恢复垃圾桶"类行动引导。
- **[D9] 任务行只增不减**：t_ingest_task 无保留期清理（当前 38 行，速率低但无上限机制）。

## 2. 业界范式 [P]/[R]/[O]

- **paperless-ngx（文档管理标杆，官方文档 usage.md + api.md 核实，[P1][P2]）**：
  - **消费即清**：consume 目录里的文件消费成功后即被移走入库结构——"expected that files in the consumption directory will no longer exist (there) after being consumed"（[P1] usage.md The consumption directory）⇒ 对照 [D5] 缺口。
  - **上传=异步任务**：`POST /api/documents/post_document/` 立即返回**消费任务 UUID**，`/api/tasks/?task_id={uuid}` 查状态（成功后含 document id）——与 DocLens task_id 轮询同范式 ✓。
  - **任务体系一等公民**：`/api/tasks/` 分页 + `/api/tasks/summary/`、`/api/tasks/status_counts/`、`/api/tasks/active/` 聚合端点 + **`/api/tasks/acknowledge/`**（确认/消除失败任务）+ `POST /api/tasks/run/` 派发（[P2] api.md v6/v10 changelog）。
  - **失败文档处理**：任务失败在 UI（File Tasks）可见含错误信息；已入库文档可经 bulk_edit **`reprocess`** 重跑。
  - **重复文件两种模式**（[P1] Duplicate documents）：默认**不拒绝**（照收 + 警告 + 详情页 Duplicates 标签页）；可选 `PAPERLESS_CONSUMER_DELETE_DUPLICATES=true` 改为拒绝——重复文件删除、任务失败并链接已有文档。
  - **并行消费靠 Celery 任务队列**（独立进程/机器，[P1] Architecture）。
- **RAGFlow（旗舰 RAG，SDK 源码核实，[R1]）**：
  - **批量上传原生支持**：`upload_documents(document_list)` 一个 multipart 请求带 N 个 file 字段（dataset.py upload_documents）；
  - **上传与解析解耦**：上传只建文档，`async_parse_documents(document_ids)` 对选中文档显式触发解析，`async_cancel_parse_documents` **可取消**；
  - **逐文档状态机**：ingestion_status ∈ COMPLETED/FAILED/STOPPED + progress + chunk_count/token_count，SDK 自带轮询至终态（_get_documents_status）。
- **open-webui**：删除面 2026-11-16 已核实（[O1]，硬删 + 悬挂引用清扫）；批量上传行为〔未核实〕。
- **共性总结**：① 上传快返回 + 任务立即可见（DocLens 已有 ✓）；② **失败是一等公民**——失败任务长期可见 + 错误信息 + 确认/重试入口（DocLens 缺 ✗✗）；③ 解析临时目录"消费即清"（缺 ✗）；④ 批量 = 一个请求 N 个 file 字段（RAGFlow 同款）；⑤ 重任务用真任务队列（Celery）——单机单进程场景 DocLens 的 daemon 线程+锁是合理降级，但必须补"重启孤儿清理"。

## 3. 方案对比与推荐（批量入库）

- **方案 A：改造现有 `/api/papers/upload` 为 List[UploadFile]**——被否：破坏 m6-trash 有意设计的单文件 409 垃圾桶引导语义及其测试（回归面 > 收益）。
- **方案 B（推荐）：新增 `POST /api/papers/upload-batch`**——一个请求 N 个 file 字段（RAGFlow 同款）；批内**串行** worker 线程顺序 `_run_ingest`（`_INGEST_LOCK` 保证跨批串行）；逐文件失败隔离（skipped_duplicate/skipped_trash/skipped_invalid/queued 四态结果）；批内去重 + 跨库去重"跳过并提示"（对照 [P1] 两种模式选宽容跳过式——RAG 语义下重复文档无增量价值且省嵌入费用）；上限 20 文件/批。详见 specs/plans/paper-batch-upload.plan.md（确认门待批准）。
- **方案 C：inbox 目录扫描消费（paperless consume 目录模式）**——被否：引入目录扫描/防重复杂度，HTTP 端点已够单机场景。

## 4. 论文管理完善清单（失败处理为核心，按优先级）

| # | 项 | 改动量 | 说明 |
|---|----|--------|------|
| R1 | **失败任务可见性** | 小（SQL 一行 + 无前端改动） | list_active_tasks 纳入 error（[D4]）；前端 error 徽标渲染已就绪直接生效。收益最大 |
| R2 | **失败重试按钮** | 小（前端） | 接既有 `/retry` 端点（[D4] 孤岛）；仅对 error 且 doc_id 非空任务显示（[D7] 校验失败类不可重试的置灰引导"请重新上传"） |
| R3 | **失败原因可读化** | 小（展示层） | 错误文案映射表：超时→"解析超时（机器繁忙），建议错峰重试"；垃圾桶→"先恢复再传"；解析失败→原始异常保留 error 字段，展示层翻译 |
| R4 | **inbox 清理** | 小 | 入库成功后删除对应 inbox 文件（对照 [P1] 消费即清）；失败保留供排查；启动扫描顺带清理超期（如 7 天）孤儿 inbox 文件 |
| R5 | 孤儿解析进程清理 | 中 | 启动扫描扩展：按 cmdline 工作目录归属（data/parsed/<doc_id>/）且仅清理"对应任务已终态"的进程；防误伤并行会话手工解析 |
| R6 | 任务行保留期 | 小 | 终态任务行保留 N 天定期清（[D9]） |
| R7 | 批量重试 | 暂缓 | R2 逐个重试已够用；批级"全部重试"待批量入库落地后视需求 |
| — | 分布式任务队列（Celery） | 非目标 | 单机单进程 daemon 线程+锁是合理降级；L1 多用户再议（与 n-6 分布式锁记池呼应） |

## 5. 与既有计划的关系

- 批量入库实现计划：specs/plans/paper-batch-upload.plan.md（确认门待批准）——§3 推荐方案 B 即该计划技术方案。
- **建议**：R1–R4 与批量入库**同批实现**（四项都是小改动：SQL 一行 / 前端按钮 / 文案映射 / unlink+启动扫描扩展），一次交付"批量入库 + 失败可管理"完整体验；R5/R6 独立记池择期。
