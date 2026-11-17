# S3 通用代码审查：论文批量入库 + 失败处理四件套（paper-batch-upload）

> 日期：2026-11-17 ｜ 审查人：S3 审查代理（独立会话，未参与实现）
> 范围：未提交改动 `git diff HEAD -- doclens/ web/src/ tests/`（4 个功能文件 + **并行 S4 修复批**在其上的增量）
> 依据：specs/plans/paper-batch-upload.plan.md ＋ specs/research/paper-management-survey.md ＋ specs/reviews/paper-batch-upload.security.md（S4，并行会话产物）
> 方法：diff 全量比对 ＋ 现行文件逐行读 ＋ pytest 实测 3 轮；行号以 2026-11-17 11:45 工作区为准（S4 修复批在审查窗口内多次落码，本报告基于其收敛后的最终状态）

## 结论

**Blocker 0 / Major 0 / Minor 5 / Nit 5 —— 审查通过，可进入收尾**（Minor 建议本轮顺手修或记池，均无阻断性）。

实测：全量 pytest **251 passed**（基线 239 ＋ 功能新增 8 ＋ S4 负向 3 ＋ sanitize 路径打码 1）；`tests/test_paper_batch.py` 11/11 绿。

---

## 1. 审查范围

| 文件 | 本次功能改动 | 状态 |
|---|---|---|
| `doclens/serve/api.py` | `POST /api/papers/upload-batch`（:309-382）＋ `_run_batch_worker`（:67-76）＋ 启动扫描块 sweep_old_inbox_files（:234-241） | 已审 |
| `doclens/paperlib.py` | `MAX_BATCH_FILES`（:35）、`list_active_tasks` 纳入 24h error＋LIMIT 200（R1，:313-334）、`_run_ingest` 两成功路径接清理（:591、:637）、`_cleanup_inbox_file`（:654-667）、`sweep_old_inbox_files`（:670-686） | 已审 |
| `web/src/components/PaperLibrary.jsx` | multiple/pendingFiles/doUpload 分流（:94、:135-170）、轮询条件非终态（R1，:126-133）、重试按钮（R2，:172-187、:368-376）、friendlyError（R3，:190-199、:360） | 已审 |
| `tests/test_paper_batch.py` | 8 条功能用例（新增文件） | 已审 |
| （S4 增量）`doclens/serve/sanitize.py`、`read_upload_capped`/`_safe_basename`、两端点接线、`docs/deploy.md`、`tests/test_serve_assets.py` | S4 修复批 F1/F2/F4/F5 及配套 | 已复核（§6） |

范围外仅提及不展开：`specs/plans/paper-batch-upload.plan.md`（文档）、`web/dist/*`（构建产物；构建时间 11:28:48 晚于 jsx 最后修改 11:26:40，产物新鲜）。

## 2. 与 plan/调研一致性核对

| plan 条目 | 实现落点 | 判定 |
|---|---|---|
| 验收 1：混合三文件 200＋逐文件 action | 端点逐文件循环（api.py:337-371）＋ `test_batch_upload_mixed_actions`（test:104） | ✓（UI 手工冒烟待执行，plan §6 已列） |
| 验收 2：批内去重 | `seen` set 仅在跨库查重通过后 add（api.py:364）→ 命中即 `skipped_duplicate`（:346-350） | ✓（test:130） |
| 验收 3：单文件行为一致、409 语义保留 | 单篇端点保留；S4 批重构其内部实现（先验后读/文件名净化），409 垃圾桶文案与回归用例原样通过（§4） | ✓ |
| 验收 4：>20 → 422 | api.py:320-323，上限取 `paperlib.MAX_BATCH_FILES`（paperlib.py:35） | ✓（test:145） |
| 验收 5（R1）：error 可见且不驱动轮询 | SQL 纳入 24h error（paperlib.py:327-329）；前端 `hasActive` 仅非终态（jsx:126-128）；标题改"入库任务"（jsx:351） | ✓（test:186） |
| 验收 6（R2）：重试按钮/置灰引导 | `doc_id` 条件渲染重试（jsx:368-373）；空 doc_id →"无法自动重试，请重新上传"（jsx:374-376），与调研 [D7] 约束一致 | ✓ |
| 验收 7（R3）：失败原因翻译 | `friendlyError`（jsx:190-199）＋原始异常留 title（jsx:358） | ✓（误分类风险见 N-1） |
| 验收 8（R4）：消费即清＋启动清理 | 两个成功路径接 `_cleanup_inbox_file`（paperlib.py:591、:637）；canonical 守卫（:660-667）；启动 sweep（api.py:234-241） | ✓（test:304、:326） |
| 验收 9：全量 pytest | 实测 251 passed | ✓ |
| 决策 2：整批 1 线程串行 | `_run_batch_worker`（api.py:67-76）＋响应前单线程启动（:379-381）；跨批互斥由 `_INGEST_LOCK` 承担 | ✓（test:156、:174） |
| 决策 3：单文件粒度失败隔离 | 逐文件 try/except（api.py:339-376） | ✓（残余缺口见 M-1/M-2） |
| 决策 4：≤20 上限＋逐文件读内存 | 循环内逐文件读（api.py:341），峰值=单文件上限 | ✓（body 总量面由 S4 L-2 以 deploy.md 反代指引落地） |
| plan §4/§5 承诺 `stage_inbox_file()` 助手 | **未实现**（staging 内联于端点） | ✗ 文档漂移 → **M-5** |

响应契约（plan §3）：`{batch_id, results:[{filename, doc_id?, action, detail, task_id?}]}`、action 四态——实现一致（api.py:341-371）；全部无效时仍 200＋逐条 skipped_invalid ✓。

## 3. 问题清单

### M-1（Minor）批 worker 循环无兜底——error 落库路径再失败会中断批内后续
- 位置：doclens/serve/api.py:67-76（`_run_batch_worker`）；逃逸点 paperlib.py:638-642（`_run_ingest` 的 except 兜底里 `update_task` 落 error，若此时 DB 故障则异常穿出）
- 现象：常规失败（解析/校验/嵌入）确实隔离（`_run_ingest` 兜底落 error，docstring 的声明成立）；但兜底路径自身抛异常（DB 抖动）会击穿 worker 循环 → 批内剩余任务永久滞留 queued，前端 `hasActive` 恒真轮询永转，直至下次重启被 sweep_stale_tasks（>1h）标 error。单文件路径同病（线程静默死亡），批量化放大了影响面。
- 修复建议（约 5 行）：循环体包 `try: paperlib._run_ingest(...) except Exception: logging.exception(...)` 后 continue；可选：对滞留任务补一次 `update_task(task_id, status="error", error="批处理中断")`。

### M-2（Minor）`seen.add` 先于建任务＋落盘后建任务失败无清理——孤儿文件＋误导性去重提示
- 位置：doclens/serve/api.py:364（seen.add）→ :366-367（dest.write_bytes）→ :368（create_task）
- 现象：`create_task` 抛异常（DB 抖动）时，inbox 文件已落盘但无人消费（留到 7 天 sweep），且 doc_id 已进 `seen` → 批内后续同内容文件被误报"本批内已有相同内容文件"（实际第一个根本没入队）。
- 修复建议（约 3 行）：① `seen.add(doc_id)` 挪到 `create_task` 成功之后；② except 分支里对"已落盘未入队"的 dest 补 `dest.unlink(missing_ok=True)`（dest 提为循环级变量再判断）。

### M-3（Minor）`_safe_basename` 未覆盖 Windows 保留字符——Windows 交付下落盘失败且文案不可读
- 位置：doclens/paperlib.py:786-788（仅滤 Cc/Cf 控制字符与 `/\` 分隔符）
- 现象：`<>:"|?*` 未替换。项目最终交付含 Windows 11（AGENTS.md FR-7.1），文件名如 `报告: v2.pdf` 在 Windows 落盘 `write_bytes` 抛 OSError（WinError 123）；S4 修复后 detail 经 sanitize_error 只剩"处理失败：[Errno 22] Invalid argument: '<path>'"——不泄露但新手不可读，且该文件被静默跳过。Linux（现行容器）无此问题；单篇端点同样受益于补齐（api.py:298 同款净化）。
- 修复建议：`_safe_basename` 字符过滤补 `ch in '<>:"|?*'` → 替换为 `_`（保留字符是落盘卫生，与既有 Cc/Cf 过滤同层）。

### M-4（Minor）批量相关测试落盘真实 DATA_DIR——测试污染＋测试期真删真实 inbox 老文件
- 位置：tests/test_paper_batch.py:104-127、:130-142、:156-171（端点用例向**真实** `data/pdfs_inbox` 落盘且无清理，每次跑测试各留 1/1/2 个孤儿文件）；:304-323、:326-348（R4 两测直接在真实 `data/pdfs_inbox`、`data/pdfs` 建删文件）；另 `_client()` → create_app 启动扫描真跑 `sweep_old_inbox_files`（api.py:236）——**跑测试即删除真实 inbox 中 >7 天文件**（2026-11-23 起 b056 遗留文件会被测试清掉）
- 影响：`data/` 为 gitignore 运行时目录、sweep 本就是下次启动要做的事，故仅 Minor；但测试不该有消费真实数据的副作用。
- 修复建议：`_patch_common` 里 `monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path/"data")` ＋ `monkeypatch.setattr(pl, "DATA_DIR", tmp_path/"data")`（api.py 与 paperlib 各自绑定的 DATA_DIR 都要打桩，端点用例即全封闭）；R4 两测同法替换 `from doclens.config import DATA_DIR` 的真目录引用（`_cleanup_inbox_file`/`sweep_old_inbox_files` 读模块全局，可 patch）；隔离后 sweep 用例 `assert n >= 1`（:342）可收紧为 `== 1`。

### M-5（Minor）plan 承诺的 `stage_inbox_file()` 助手未实现——文档与实现漂移
- 位置：specs/plans/paper-batch-upload.plan.md:44（§4 变更清单）、:51（§5 步骤 2）
- 现象：plan 两处仍列 `stage_inbox_file()` 助手，实际 staging 内联在端点（api.py:363-368）；plan §4/§5 其余部分（R1-R4 扩展）已同步更新，唯独此项未改。
- 修复建议：改 plan 两处为"staging 内联于端点（与 S4 F2/F4 净化链路同址，免多一层参数传递）"，或后续真抽助手——二选一，保持审查基准自洽。

### N-1（Nit）friendlyError 裸 `api` 子串过宽
- 位置：web/src/components/PaperLibrary.jsx:197（`/嵌入|embedding|ARK|API key|api/i`）
- 现象：任何含 "api" 子串的异常文本（如 "rapid"、含 api 的 URL 片段）都被误译为"模型服务调用失败"。R3 是展示层、原始异常在 title 可见，故仅 Nit。
- 修复建议：收窄为 `\bAPI\b|api[-_ ]?key|ARK` 等带边界的模式。

### N-2（Nit）错误徽标 30 字截断削掉行动引导尾字
- 位置：web/src/components/PaperLibrary.jsx:360（`friendlyError(t.error).slice(0, 30)`）
- 现象：固定文案"文档解析失败：文件可能损坏/加密或为扫描件，检查后重试或换文件"共 31 字，截断到 30 丢尾字，行动引导受损（R3 的目的即引导）。
- 修复建议：放宽到 50–60 或不截（badge 已有 title 兜底原始异常）。

### N-3（Nit）上传成功后 pendingFiles 不清空——重复点击＝整批重传
- 位置：web/src/components/PaperLibrary.jsx:337（onChange）、:342-344（按钮）；doUpload 成功分支不清 state
- 现象：批量上传成功后文件仍选中，再点按钮整批重传 → 全部 skipped_duplicate（无实害但有噪音）；旧单文件行为相同（一致性说明，非回归）。
- 修复建议：成功分支 `setPendingFiles([])` 并重置 input value（`e.target.value=''` 需在 onChange 里配合，或用 key 重挂）。

### N-4（Nit）`fname` 净化调用在逐文件 try 之外
- 位置：doclens/serve/api.py:338（`fname = paperlib._safe_basename(...)` 在 `try:`（:339）之前）
- 现象：`_safe_basename` 为纯字符串操作几乎不可能抛，但按"单文件异常隔离"的严格边界应纳入 try——若未来净化逻辑变复杂（如引入 IO），会击穿整批隔离变 500。
- 修复建议：挪进 try 内（except 分支已有 fname 兜底文案路径），或加注释声明其为 total function。

### N-5（Nit）R1 用例未断言 24h 窗口与 LIMIT——防回归面不完整
- 位置：tests/test_paper_batch.py:214-215（仅断言 `status IN (...)` 与 `status='error'` 两个片段）
- 现象：若有人删掉 `AND updated_at > NOW() - INTERVAL 1 DAY`（paperlib.py:328）或 `LIMIT 200`（:329），测试仍绿——error 行将永驻任务区或响应体失控，正是 R1 评审时点名的两个风险点。
- 修复建议：补 `"INTERVAL 1 DAY" in captured["sql"]` 与 `"LIMIT 200" in captured["sql"]` 两个断言。

## 4. 硬性确认项：与既有回归的语义相容

1. **`tests/test_paper_trash.py` 未被改动**：不在 git status 修改列表（mtime 2026-11-16 17:44:07，早于功能开工），`test_api_upload_dedupe_trash_message`（:363-372）逐字原样，随全量 251 passed 通过——**单文件 409 垃圾桶引导语义未破坏**（实证）。
2. **单文件端点对外语义保持**：S4 批重构了其内部实现（先验后读/文件名净化/create_task 传净化名），但 409 双文案、doc_id 口径、响应结构不变——回归用例原样通过即语义未变的证据。
3. **`tests/test_paper_batch.py` 8 条功能用例全数保留且通过**（文件现 348 行：原 8 条位于前部未动，S4 追加 3 条负向用例插入 R4 节之前）：`test_paper_batch.py` 11/11 绿。

## 5. 测试有效性评估

- **断言真实有效**（非恒真）：逐文件 action 按文件名精确断言＋响应键集合断言（test:120-127）；批内去重断言**有序**完整 action 序列（test:142）；worker 打桩断言 `target is api_mod._run_batch_worker`——若实现退化为"每文件一线程"，last 记录的 target 将是 `_run_ingest` 而使断言失败，能证伪并发回归（test:167）；worker 顺序经模块函数直测（test:181）；R4 两测走真实文件系统双分支（删/留/误删 canonical）。
- **打桩姿势**：`monkeypatch.setattr("threading.Thread", _NoThread)` 全局替换经实测与 TestClient 兼容（anyio 门户线程创建不受影响，11/11 绿）；`validate_upload` 简化桩的差异（放开 10KB 下限）已在 docstring 声明（test:36-40）——透明。
- **弱点**：R1 用例仅 SQL 文本断言且缺窗口/LIMIT 断言（→ N-5）；sweep 用例 `n >= 1` 弱断言（共享真实目录下合理，M-4 隔离后可收紧）；R2/R3 前端逻辑无自动化测试（plan §5 步骤 4 仅要求 build＋手工冒烟，属计划内取舍）。

## 6. 并行 S4 修复批复核（按父级指示纳入范围）

S4 报告结论"有条件通过（2 Medium＋3 Low）"，其修复批在本审查窗口内落地并收敛，逐项复核：

| 修复项 | 落点 | S3 复核 |
|---|---|---|
| F1（M-1）detail 统一脱敏 | api.py:372-376 经 `sanitize_error(exc)[:140]`；sanitize.py:20-21 补 Unix/Windows 绝对路径打码 | ✓ 负向用例 `test_batch_upload_error_detail_sanitized`（test:282-297）＋ `test_sanitize_error_masks_absolute_paths`（test_serve_assets.py:77-84）绿；打码先于 [:300] 截断，顺序正确 |
| F2（M-2）先验大小后整读 | `read_upload_capped`（paperlib.py:758-775）：seek/tell 预检 → 拒则零读；`read(cap+1)`＋:773-774 兜底防 size 谎报 | ✓ 两端点均接线（api.py:275、:341） |
| F4（L-1）文件名净化 | `_safe_basename`（paperlib.py:778-796）：NFC＋Cc/Cf 过滤＋分隔符剔除＋UTF-8 字节截断（had_pdf 时预留 4 字节，:792） | ✓（Windows 保留字符缺口遗留 → M-3） |
| F5（L-3）error 行 LIMIT 200 | paperlib.py:329 `ORDER BY id DESC LIMIT 200`＋:332 Python `reversed` 回正序 | ✓ 语义保持（最新 200 条、升序展示）；R1 用例仍绿 |
| F3（L-2）请求体总量门槛 | docs/deploy.md 反代 `client_max_body_size`（≤2200MB）指引 | ✓ Low 定级下以文档路线落地合理；应用层 422 在 spool 后生效的事实已在 deploy.md 如实写明 |

**审查窗口内的红→绿过程记录**（供 security.md"复测结果"回填参考）：11:36 实测全量曾 2 failed——① 旧版 `LyingStub` 把谎报 `tell` 放在 UploadFile 外层而 `read_upload_capped` 读的是 `.file` 真身（测试桩形状错）；② `_safe_basename` 截断后补 `.pdf` 致总长 202 > max_bytes=200（契约自违）。11:41 会话自修（`_LyingFile` 归位 `.file`；`limit = max_bytes - (4 if had_pdf else 0)`）后全绿。两处修法均与本报告建议一致，最终状态不复计缺陷。
**观察（不计缺陷）**：sanitize.py Windows 路径正则字符类含空格（:21），可能把路径后跟随的普通文字一并吞进 `<path>`（如"D:\x\a.pdf 附注"）——过度打码方向安全，纯展示损失，S4 可自行斟酌收紧。

## 7. 正面确认（复核过、无问题的点）

- **启动扫描顺序安全**：sweep_stale_tasks（api.py:228）先于 sweep_old_inbox_files（:236）——滞留 >1h 的活跃任务先标 error，7 天清理窗口不可能命中仍被引用的 inbox 文件（"误删在途文件"不成立）。
- **dest 命名碰撞无害**：`{doc_id}_{ts}_{name}` 同秒同名碰撞仅发生在"内容相同"时，覆盖写幂等；路径穿越由分隔符剔除闭合（S4 已核）。
- **资源释放**：batch 端点 conn `finally` 关闭（api.py:377-378）；UploadFile 流由 FastAPI 0.162.2（requirements.txt:17，≥0.103 自动关闭语义）统一关闭，列表参数同覆盖。
- **并发模型**：整批 1 个 daemon 线程串行 `_run_ingest`；跨批及与软删/恢复/彻底删除的互斥经 `_INGEST_LOCK`（paperlib.py:553 等）；锁粒度=单任务（未跨整批持锁），不放大 2026-11-16 孤儿进程事故面。
- **R1 24h 窗口有 Schema 支撑**：`t_ingest_task.updated_at NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`（scripts/init_db.py:146），create_task 不显式写该列安全。
- **规范面**：中文注释＋依据标注（[P1]/[D4]/[R1]/日期/事故引用）与仓内风格一致；命名一致（`MAX_BATCH_FILES`/`_cleanup_inbox_file`/`sweep_old_inbox_files`）；无 print/console.log 调试残留；前端 `STATUS_META`（jsx:7-13）与 `link-btn` 样式（styles.css:251）引用均存在。

## 8. 遗留与收尾建议

1. **验收 1 的 UI 手工冒烟**（真实 3 PDF 含 1 重复，走任务区轮询＋问答）待人工执行——plan §6 已列，代码审查无法替代。
2. **收尾步未做**：CHANGELOG 条目与双端 push（plan §5 步骤 6；git status 尚无 CHANGELOG 改动）。
3. 修复优先级建议：M-1/M-2 各约 5 行建议本轮顺手修（批量端点是本次交付核心，隔离承诺值得闭环）；M-3 随 Windows 交付前修；M-4 记池（下轮测试卫生批）；M-5 改 plan 文档即可。
4. S4 报告"复测结果（待修复后回填）"可回填：251 passed ＋ 本报告 §6 复核记录。

---
*审查方法自检：只读审查，未修改任何源码/测试文件（本报告为唯一产出）；所有行号基于收审时工作区快照，S4 批后续再落码需重新对行。*

---

## 9. 处置记录（2026-11-17，审查意见回填）

| 项 | 处置 | 验证 |
|----|------|------|
| M-1 | `_run_batch_worker` 循环体逐任务 try/except + 日志 + 继续（api.py） | 全量回归含 worker 顺序用例 |
| M-2 | `seen.add` 移至 create_task 成功后；except 分支 unlink 孤儿 dest；fname 净化移入 try（N-4 一并） | 混合用例 + 批内去重用例通过 |
| M-3 | `_safe_basename` 过滤集补 Windows 保留字符 `<>:"|?*`（paperlib.py） | `test_safe_basename_sanitizes_malicious_names` 通过 |
| M-4 | 批量测试 DATA_DIR 重定向 tmp_path（api_mod/pl 两处）；R4 两测同步改 tmp_path；评测启动扫描 connect 打桩（消 10s 真连库）；**另加固**：inbox 启动清理加 `settings.web_static` 门——pytest/开发环境的 create_app 不再触碰真实 inbox（防"跑测试删真实数据"） | 全量 251 passed；真实 inbox 零触碰 |
| M-5 | plan §4/§5 两处 stage_inbox_file 漂移修正（改为内联 staging 备案） | 文档核对 |
| N-1 | friendlyError 裸 `api` 子串收紧为 `\bARK\b|API key` | 代码核对 |
| N-2 | error 徽标 slice(0,30)→slice(0,60) | 代码核对 |
| N-3 | 上传成功后清空 pendingFiles + input.value（失败路径保留选择） | 代码核对 |
| N-5 | R1 用例补断言 INTERVAL 1 DAY 与 LIMIT 200（后者即 S4 L-3） | `test_list_active_tasks_includes_error` 通过 |
| 观察 | sanitize Windows 正则含空格字符类过度打码 → 收紧为 `[\w.\-]+` 段（方向仍安全） | sanitize 路径测试通过 |

复测：全量 pytest **251 passed**；`npm run build` 成功。Minor 5 全修、Nit 5 修 4（N-4 与 M-2 合并处置）。
