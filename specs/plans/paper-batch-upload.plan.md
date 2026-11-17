# 论文批量入库 + 失败处理四件套 实现计划

> slug：`paper-batch-upload` ｜ 日期：2026-11-17 ｜ 状态：已批准（范围扩大：并入调研 R1–R4）
> 调研依据：[specs/research/paper-management-survey.md](../research/paper-management-survey.md)（D 线缺口实锤 + paperless-ngx/RAGFlow 范式核实）

## 1. 目标与验收标准（可执行验证）

- **目标**：① 论文库上传区支持一次选择多个 PDF 批量入库（逐文件失败隔离）；② 失败论文可管理——失败可见（R1）、可重试（R2）、原因可读（R3）、inbox 有生命周期（R4）。
- **验收标准**：
  1. 选 3 个文件（1 新 PDF + 1 与库内重复 + 1 非 PDF）上传 → 200；1 个入队解析、重复提示跳过、非 PDF 提示跳过；任务区出现 1 个进行中任务且轮询到完成；
  2. 同一批内选两个相同文件 → 第二个被跳过（批内去重），不产生两个同 doc_id 任务；
  3. 单文件上传行为与现在完全一致（409 垃圾桶引导语义保留，既有测试不改仍绿）；
  4. 单批 >20 个文件 → 422；
  5. **R1**：任务失败后前端任务区仍能看到该任务（error 徽标 + 摘要），且 error 行不驱动轮询（终态）；
  6. **R2**：失败任务行有"重试"按钮（doc_id 非空时），点击后新任务入队；doc_id 为空的失败任务提示"请重新上传"；
  7. **R3**：失败原因展示层翻译成人话（超时/重启中断/垃圾桶/解析失败各有行动引导），原始异常保留在悬浮提示；
  8. **R4**：入库成功后对应 inbox 文件被删除（canonical 不受影响）；启动扫描清理 >7 天孤儿 inbox 文件；
  9. 全量 pytest 通过（基线 239 + 新增）。

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
| `doclens/serve/api.py` | 新增 `POST /api/papers/upload-batch` 端点（约 +60 行）；启动扫描块追加孤儿 inbox 清理调用 | 多文件循环处理 + 批线程编排 |
| `doclens/paperlib.py` | `MAX_BATCH_FILES` 常量、`_cleanup_inbox_file()` 助手（R4）、`sweep_old_inbox_files()`（R4）、`list_active_tasks` 纳入 error（R1）、`read_upload_capped()`（S4 M-2）、`_safe_basename()`（S4 L-1）——批量端点内联 staging（S3 M-5 备案：未抽 stage_inbox_file 助手，循环体即 staging 逻辑） | 批量前置件 + 失败可见性 + inbox 生命周期 |
| `tests/test_paper_batch.py` | 新增（约 8 条用例） | 见 §6 |
| `web/src/components/PaperLibrary.jsx` | multiple input + pendingFiles 数组 + doUpload 分流 + 汇总消息；任务区标题/轮询条件调整（R1）；重试按钮（R2）；失败原因翻译（R3） | 批量上传 UX + 失败可管理 |

## 5. 分步任务

1. **R1 失败可见性**：list_active_tasks SQL 纳入 error（含 24h 内 error 行）→ 前端任务区标题改"入库任务"、轮询条件改为仅非终态 → 验收：单测 + 手动构造失败任务可见。
2. **paperlib 助手**：_cleanup_inbox_file / sweep_old_inbox_files / MAX_BATCH_FILES / read_upload_capped / _safe_basename → 验收：单测通过。（原计划的 stage_inbox_file 未单独抽取——staging 逻辑内联在批量端点循环中，S3 M-5 备案）
3. **批量端点**：upload-batch（≤20 上限、逐文件隔离、单线程串行编排）→ 验收：API 单测通过 + 全量回归。
4. **R2+R3 前端**：重试按钮 + 失败原因翻译 → 验收：build 成功 + 手动冒烟。
5. **R4**：_run_ingest 两个成功路径接 _cleanup_inbox_file；api.py 启动扫描加 sweep_old_inbox_files → 验收：单测 + 冒烟后 inbox 不堆积。
6. **收尾**：全量 pytest + npm build + CHANGELOG + 双端 push。

## 6. 测试策略

- FakeConn/TestClient 范式（同 test_paper_trash），monkeypatch `db_mod.connect`、`pl.validate_upload`、`pl._run_ingest`、`threading.Thread`（记录目标不真跑）。
- 用例列表：① 新+重复+垃圾桶重复+非 PDF 四文件 → 逐文件 action 断言；② 批内同文件去重；③ >20 文件 422；④ list_active_tasks SQL 含 error（R1）；⑤ sweep_old_inbox_files 清老留新（R4）；⑥ _cleanup_inbox_file 仅删 inbox 内文件、canonical 不动（R4）；⑦ 单文件端点回归（既有测试不改）。
- 手工冒烟：真实 3 PDF（含 1 重复）走 UI 验证任务区轮询与问答可用。

## 7. 风险与回滚

- 风险：批量大文件内存（逐文件读入，峰值=单文件上限，可控）；长批占用 _INGEST_LOCK 数小时（CPU 解析单篇即小时级——看板逐任务可见，文档提示"大批量建议分多次/错峰"）；R1 纳入 error 后轮询永动（前端轮询条件改为仅非终态，已列验收 5）。
- 回滚：新端点独立，前端分流开关式——回滚=前端退回单文件路径，一行改动；服务端新端点无状态可直接摘除；R1-R4 均为独立小改动可单独回退。

## 8. 敏感代码判定

**是**——文件上传路径（大小/类型校验、文件名净化、落盘、批上限放大滥用面）。按流程实现后走 S4 安全专项复查（重点：批量放大 DoS、文件名注入、inbox 落盘路径、鉴权继承）。

## 9. 执行命令

- 测试：`D:\soft\anaconda\envs\doclens\python.exe -m pytest tests/ -q`
- 前端构建：`cd web && npm run build`
- 双端同步：`git push origin master && git push server master`

---
## 确认门记录（S2 开始前填写）

- 批准时间：2026-11-17 11:09
- 批准指令原文：用户在实施范围选项中选择"批量入库 + 失败四件套（推荐）"（批量入库 + R1 失败可见性 + R2 重试按钮 + R3 失败原因可读化 + R4 inbox 清理）；此前指示"先调研一下这个功能的实现都要怎么做"——调研产物 specs/research/paper-management-survey.md。
- TDD：否（用户批准未带 TDD 指令——按普通实现，关键路径测试照补）
