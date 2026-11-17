# 论文批量入库 实现计划

> slug：`paper-batch-upload` ｜ 日期：2026-11-17 ｜ 状态：待确认门批准

## 1. 目标与验收标准（可执行验证）

- **目标**：论文库上传区支持一次选择多个 PDF，批量提交入库；逐文件独立任务/进度/失败隔离，重复与无效文件跳过不拖垮整批。
- **验收标准**：
  1. 选 3 个文件（1 新 PDF + 1 与库内重复 + 1 非 PDF）上传 → 200；1 个入队解析、重复提示跳过、非 PDF 提示跳过；任务区出现 1 个进行中任务且轮询到完成；
  2. 同一批内选两个相同文件 → 第二个被跳过（批内去重），不产生两个同 doc_id 任务；
  3. 单文件上传行为与现在完全一致（409 垃圾桶引导语义保留，既有测试不改仍绿）；
  4. 单批 >20 个文件 → 422；
  5. 全量 pytest 通过（基线 239 + 新增）。

## 2. 现状调查（代码位置、复用点、约束）

- 单篇上传：`doclens/serve/api.py:245-286`（校验→sha256→垃圾桶/重复 409→落 inbox→create_task→daemon 线程跑 `_run_ingest`）。
- 任务状态机：`doclens/paperlib.py:271`（create_task，状态"排队中"起）、`_run_ingest`（paperlib.py:532，`_INGEST_LOCK` 全局串行化——**解析天然串行，批内无需另建队列**）、`get_tasks_by_batch`（batch_id 查询已就绪）。
- `batch_id` 概念已存在（qasper-batch 先例；schema 就绪），仅缺多文件入口。
- 前端：`web/src/components/PaperLibrary.jsx:92-157`（单文件 state/上传函数）、`:289-300`（input 无 multiple）；进行中任务区（activeTasks 轮询 2.5s）已能逐任务显示进度，无需改。
- 校验：`paperlib.validate_upload(filename, size)`（paperlib.py:699）；PDF 魔数校验在 `_run_ingest` 内 `validate_pdf`。
- 既有测试：`tests/test_paper_trash.py:363`（单文件 409 语义测试——保持不动即回归护栏）。

## 3. 技术方案（关键决策 + 被否方案 + 理由）

- **决策 1：新增 `POST /api/papers/upload-batch`（多文件端点），单文件端点原样保留。**
  被否：改造原端点为 List 参数——会破坏 m6-trash 有意设计的单文件 409 垃圾桶引导语义与其测试（回归面>收益）。
- **决策 2：批内串行解析**。批请求只起 **1 个** daemon 线程顺序迭代 `_run_ingest`（每任务独立行/独立错误隔离）；`_INGEST_LOCK` 天然保证跨批串行。被否：每文件一线程并行——N 个 MinerU 抢 CPU/评分线程堆积（2026-11-16 孤儿进程事故的直接教训：并发解析是算力放大器）。
- **决策 3：逐文件处理、单文件粒度失败隔离**。循环内逐个：读文件→validate_upload→sha256→t_doc 重复/垃圾桶检查→批内去重（seen set）→落 inbox→create_task；任何一步失败只标记该文件（action=skipped_*），不中断整批。
- **决策 4：批量上限**。单批 ≤20 个文件（`MAX_BATCH_FILES`），防任务列表/线程滥用；单文件大小沿用 validate_upload 既有上限；逐文件读入内存（峰值=单文件上限，不随批放大）。
- **响应契约**：`{"batch_id", "results": [{"filename", "doc_id", "action", "detail", "task_id"?}]}`，action ∈ `queued | skipped_duplicate | skipped_trash | skipped_invalid`。200 + 逐文件结果（全部无效时 results 也返回，action=skipped_invalid 逐条说明，前端可读）。
- **前端**：input 加 `multiple`；选 1 个文件走既有单文件路径（零回归），≥2 个走批量端点；上传消息汇总"N 入队 / M 重复跳过 / K 无效跳过"+逐条明细；进行中任务区复用既有轮询展示。

## 4. 变更清单（文件级）

| 文件 | 变更 | 职责 |
|---|---|---|
| `doclens/serve/api.py` | 新增 `POST /api/papers/upload-batch` 端点（约 +60 行） | 多文件循环处理 + 批线程编排 |
| `doclens/paperlib.py` | 新增 `MAX_BATCH_FILES` 常量与 `stage_inbox_file(filename, contents)` 助手（落 inbox + 返回 doc_id/dest，供批量端点复用；单篇端点不动） | 抽取可测的落盘/去重前置件 |
| `tests/test_paper_batch.py` | 新增（约 5-6 条用例） | 见 §6 |
| `web/src/components/PaperLibrary.jsx` | multiple input + pendingFiles 数组 + doUpload 分流 + 汇总消息 | 批量上传 UX |

## 5. 分步任务

1. **paperlib 助手 + 常量**：`stage_inbox_file`（sha256、重复/垃圾桶查询、inbox 落盘；重复时抛/返回标记）→ 验收：单测（FakeConn）通过。
2. **批量端点**：`upload-batch`（≤20 上限、逐文件隔离、单线程串行编排）→ 验收：API 单测通过 + 全量回归。
3. **前端分流**：multiple 选择 + 双路径上传 + 汇总消息 → 验收：`npm run build` 成功 + 手动冒烟（3 文件场景）。
4. **收尾**：全量 pytest + CHANGELOG + 双端 push。

## 6. 测试策略

- FakeConn/TestClient 范式（同 test_paper_trash），monkeypatch `db_mod.connect`、`pl.validate_upload`、`pl._run_ingest`、`threading.Thread`（记录目标不真跑）。
- 用例列表：① 新+重复+非 PDF 三文件 → 逐文件 action 断言；② 批内同文件去重；③ >20 文件 422；④ 垃圾桶内重复 → skipped_trash 带恢复引导文案；⑤ 全部无效 → 200 且 results 全 skipped_invalid；⑥ 单文件端点回归（既有测试不改）。
- 手工冒烟：真实 3 PDF（含 1 重复）走 UI 验证任务区轮询与问答可用。

## 7. 风险与回滚

- 风险：批量大文件内存（逐文件读入，峰值=单文件上限，可控）；长批占用 _INGEST_LOCK 数小时（CPU 解析单篇即小时级——看板逐任务可见，用户可自行判断批量规模；文档提示"大批量建议分多次/错峰"）。
- 回滚：新端点独立，前端分流开关式——回滚=前端退回单文件路径，一行改动；服务端新端点无状态可直接摘除。

## 8. 敏感代码判定

**是**——文件上传路径（大小/类型校验、文件名净化、落盘、批上限放大滥用面）。按流程实现后走 S4 安全专项复查（重点：批量放大 DoS、文件名注入、inbox 落盘路径、鉴权继承）。

## 9. 执行命令

- 测试：`D:\soft\anaconda\envs\doclens\python.exe -m pytest tests/ -q`
- 前端构建：`cd web && npm run build`
- 双端同步：`git push origin master && git push server master`

---
## 确认门记录（S2 开始前填写）

- 批准时间：
- 批准指令原文：
- TDD：
