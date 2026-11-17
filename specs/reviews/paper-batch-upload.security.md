# S4 安全专项复查：论文批量上传路径（paper-batch-upload）

- **日期**：2026-11-17
- **范围**：`git diff HEAD -- doclens/` + `web/src/components/PaperLibrary.jsx`（对照既有单篇端点）
- **依据**：ai-workflow S4（敏感代码判定：文件上传 ⇒ 命中，强制安全专项复查）；OWASP Top 10 + 本项目技术栈（FastAPI/Starlette multipart、pymysql/MySQL、Qdrant、MinerU subprocess、React SPA、单管理员 argon2+JWT）
- **审查对象**：
  - `doclens/serve/api.py` — `api_papers_upload_batch`（新增，:308-378）对照 `api_papers_upload`（既有，:265-306）；`_run_batch_worker`（:67-76）
  - `doclens/paperlib.py` — `validate_upload`（:743-751）、`_cleanup_inbox_file`（:650-663）、`sweep_old_inbox_files`（:666-682）、`list_active_tasks`（:312-330）、`_run_ingest`（:538-638）
  - `web/src/components/PaperLibrary.jsx` — 上传分流（:135-168）、`multiple` 选择（:335）、轮询条件（:127-128）、失败展示/重试（:190-208, :355-373）
- **纪律**：只审查未修改任何源码/测试文件（本报告文件除外）。

---

## 结论

**有条件通过（需修复项）** — 2 项 Medium 修复后方可收尾；3 项 Low 建议记池或顺手修；无 Critical/High。

无 SQL 注入、无路径穿越、无鉴权缺口、无算力放大（串行 worker 设计正确）；需修的两项均为「批量路径相对既有口径的退化/放大」：异常文本原样回显（M-1）与先整读后校验（M-2）。

---

## 重点复查项结论

### 1. 批量放大 DoS（20 × 100MB）——部分通过，见 M-2 / L-2

**已核，通过（设计面）**：
- 批内**串行单 worker 线程**（api.py:67-76、:375-377），批内逐个 `_run_ingest`；`_INGEST_LOCK` 跨批互斥（paperlib.py:553）——无线程数放大、无并发解析算力放大（2026-11-16 孤儿进程事故不复发）。测试 `test_batch_upload_serial_worker` / `test_run_batch_worker_serial_order` 覆盖。
- 批内 RAM **无累计**：`contents = f.file.read()` 每轮重绑定（api.py:338），前一文件字节随引用释放；`staged` 仅存 `(task_id, dest)` 路径。峰值 ≈ 单文件全长（而非 20×100MB 同时驻留）。
- 文件数上限 20 在 handler 首行生效（api.py:320-322），先于任何读取/落盘/建任务。

**需修复（M-2，Medium）**：单文件**先整读、后校验**——`f.file.read()`（api.py:338；既有单篇同款 :274）把整个 part 读入 RAM 之后才调 `validate_upload` 的 100MB 上限（:339）。任何一个 >100MB 的 part（如 8GB"PDF"）都会先被全量读进内存再拒绝：峰值 RAM = 文件全长，可 MemoryError/OOM 击杀整个服务（连带击杀在途入库任务）。新增 `multiple` 多选使"误选一个超大文件"的概率上升，故从既有隐患升格为本轮需修项。修复见修复清单 F2。

**需修复（L-2，Low）**：无请求体总量门槛——Starlette multipart 解析在 handler 之前已把整个 body spool 到磁盘临时文件（默认 max_files/max_fields=1000，仅 spool 无拒绝），uvicorn/Starlette 无默认 body 上限，仓库内无 nginx `client_max_body_size`（deploy.md 未配置反代）。20 文件上限在 2GB body 全部落盘后才 422；并发数批请求 → 临时盘放大。单管理员 LAN 场景实际风险有限，故 Low。修复见 F3。

**Info（备忘）**：上传侧无请求超时（同步 handler 走 anyio 线程池，uvicorn 默认无 body 超时）——LAN 单管理员可接受，不修；`conn = connect()`（api.py:332）横跨 20 文件的慢 IO 读取持有 DB 连接——量级可接受，备忘；批内文件名+时间戳构造 dest，同秒同内容文件靠 `seen` 集合与跨库去重兜住，无覆盖竞态新增。

### 2. 文件名注入 / 路径穿越——穿越已核通过；净化不足见 L-1

**已核，通过（穿越面）**：
- `dest = inbox / f"{doc_id}_{int(time.time())}_{safe_name}"`（api.py:364）：前缀 `doc_id` 是 sha256 前 12 位 hex（:343）、`ts` 为 int，**唯一用户可控段是 `safe_name`**，而 `safe_name = fname.replace("/", "_").replace("\\", "_")`（:363）把两类分隔符全部替换——`../`、`..\..`、绝对路径 `C:\evil\x.pdf`、URL 编码形态最终都退化为**无分隔符的单段文件名**，dest 恒为 `pdfs_inbox` 直下一个普通文件，无法指向上级目录。
- 纯 `..`/`...` 残留：拼在前缀后成为 `{docid}_{ts}_..` 整体文件名，不构成穿越（Linux 上合法文件名；Windows 上 `Path` 拼接后仍是完整名）。
- inbox 目录本身固定为 `DATA_DIR / "pdfs_inbox"`（:327-328），无用户输入参与目录构造。

**需修复（L-1，Low）**：`safe_name` 仅去分隔符，缺三件事：
1. **无长度上限**：超长 fname → dest 超过 Windows `MAX_PATH` 260 → `write_bytes` OSError；或 fname>255 → `t_ingest_task.filename VARCHAR(255)`（init_db.py:136）在严格模式下 DataError——两者的异常文本正是 M-1 回显泄露的触发源。前端 `multiple` 选择任意来源文件，超长名并不罕见。
2. **无控制字符处理**：Linux 上 `\n` 是合法文件名字符 → inbox 落盘含 `\n` 的文件名并入库 `filename` 列（React 渲染转义、无 XSS，JSON 响应合法转义——仅污染/排查困难）；`\x00` → OSError（进 M-1 回显）。
3. **无 Unicode 处理**：RTL 覆盖符（U+202E）在任务区把显示名倒序（显示欺骗；存储与交付无害——入库前有 `%PDF-` 魔数校验 corpus_intake.py:29,48，交付以 `application/pdf` inline）。同形字符仅视觉混淆。

修复见 F4（`_safe_basename` 帮助函数，单篇端点同步受益）。**注意：上述三点在既有单篇端点同样存在（api.py:298-303），批量未引入新类别，但批量 UI 使触发概率上升。**

### 3. 落盘安全（inbox 写 / _cleanup_inbox_file / sweep）——已核，通过

**已核，通过**：
- inbox 写（api.py:327-328, :365）：目录固定、`mkdir(parents=True, exist_ok=True)`、文件名见第 2 项（无穿越）。
- `_cleanup_inbox_file`（paperlib.py:650-663）：`p.resolve().parent == (DATA_DIR / "pdfs_inbox").resolve()` 是**包含性判断**——若 pdf_path 是指向 canonical（`data/pdfs/`）或其他目录的符号链接，`resolve()` 解析到真实目标后 parent 判断不匹配 → 不删；即使构造出 resolve 后仍落在 inbox 的符号链接，`p.unlink()` 删除的是**目录项（链接本身）而非目标文件**（unlink 语义不跟随符号链接，POSIX/Windows 一致）——canonical 不可经此路径误删。失败任务保留 inbox 供排查（:634-638 不清），语义与 `sweep_old_inbox_files` 7 天兜底闭环。测试 `test_cleanup_inbox_file_only_inbox` 直接覆盖"canonical 绝不误删"。
- TOCTOU（resolve 判断与 unlink 之间被换文件）：攻击者需具备**本地文件系统写权限**才能在窗口内换入路径——单管理员容器部署下超出威胁模型；且如上所述，即便换入符号链接，unlink 删链接不删目标，损害上限是"删掉 inbox 里一个文件"。可接受。
- `sweep_old_inbox_files`（:666-682）：仅遍历 inbox 目录、逐文件 try/except OSError 不中断；启动期执行（api.py:234-241）失败不阻塞启动。备忘（Info）：理论上排队 >7 天任务的 inbox 原件会被 sweep（当前 `_INGEST_LOCK` 串行下排队 7 天不可达），备注即可。

### 4. 鉴权继承——已核，通过

**已核，通过**：
- 批量端点 `@protected.post("/api/papers/upload-batch")`（api.py:308）挂在 `protected` 路由，该路由 `dependencies=[Depends(auth.get_current_user)]`（api.py:94）——与全部 `/api/papers/*`、`/api/docs`、`/api/query` 同一把门；无旁路注册（`app.include_router(protected)` 一处，:221）。
- `get_current_user`（auth.py:126-137）：Bearer/cookie 双通道，token 缺失/无效一律 401（decode_token 不区分原因，auth.py:115-123）；session_stamp=HMAC(jwt_secret, 密码派生) 改密即全端吊销（auth.py:39-48）。
- 空凭据 fail-fast（api.py:88-92）；`auth_enabled=False` 仅测试注入路径（api.py:82-83）。
- 登录限流/假哈希（auth.py:142-152）不受本 diff 影响。

### 5. 信息泄露——需修复（M-1）；其余已核通过

**需修复（M-1，Medium）**：批量端点逐文件异常**原样回显到 HTTP 响应**：
`except Exception as exc: results.append({..., "detail": f"处理失败：{str(exc)[:140]}"})`（api.py:370-372）。

- 泄露向量（均可由合法管理员请求触发，多为误操作触发）：
  - `write_bytes` OSError 消息含**完整服务器文件系统路径**（dest 内嵌 `DATA_DIR` 绝对路径，如 `D:\Project\RAG\data\pdfs_inbox\...` 或容器路径）——超长名/非法字符（含 `\x00`）即触发；
  - `create_task` 的 pymysql `DataError (1406, "Data too long for column 'filename' ...")`——泄露表/列/schema 信息；
  - DB 不可达时 `OperationalError` 泄露 host/port。
- **口径退化**：本项目已有统一脱敏约定——任务侧 error 落库经 `sanitize_error(exc)[:500]`（paperlib.py:634-638）、SSE error 事件同口径（api.py:60-64）、单篇端点异常直接冒泡为 FastAPI 通用 500（无回显）。批量端点是唯一把原始 `str(exc)` 写进响应体的路径。
- 修复见 F1。注意 `sanitize_error` 现仅打码 `sk-*` 与 `api_key=`（sanitize.py:14-15），不含路径规则——修复时建议顺手在 sanitize.py 补一条绝对路径打码（见 F1 附注）。

**已核，通过（其余泄露面）**：
- `validate_upload` 返回固定中文文案（paperlib.py:743-751）——无内部细节；
- `skipped_trash`/`skipped_duplicate` detail 仅含 doc_id（hex，api.py:356, :360）；
- 任务 error 字段落库前 `sanitize_error + [:500]`（paperlib.py:634-638）——24h 窗口回显到 UI 的错误文本已脱敏；前端 `friendlyError`/`title` 仅展示该已脱敏文本（PaperLibrary.jsx:190-208, :360）；
- 日志：uvicorn.error 仅记计数与异常 stacktrace（api.py:230-241, :486-487——stacktrace 只进服务端日志不进响应，可接受）；无 filename/凭据入日志；
- 前端回显 `t.filename`（入库原始名）：React JSX 文本/属性插值自动转义——无 XSS（含 `\n`、RTL 字符仅显示层观感问题，见 L-1）。

### 6. SQL 注入——已核，通过

**已核，通过**：本 diff 触及的全部 SQL 逐条核对：
- api.py:350 `SELECT deleted_at FROM t_doc WHERE doc_id=%s`（参数为服务端计算的 sha256 hex）；
- paperlib.py:277-280 `create_task` INSERT 全参数化；
- paperlib.py:322-325 `list_active_tasks` 静态字符串（含新增 `OR (status='error' AND updated_at > NOW() - INTERVAL 1 DAY)`）——无任何拼接；
- paperlib.py:305 `update_task` 动态 SET：列名来自**代码内固定白名单元组**（:292-297），值全参数化；
- paperlib.py:337-340 `get_tasks_by_batch` 参数化。
无一处字符串拼接用户输入。 ✔

### 7. DoS 二阶（error 行进 list_active_tasks 24h 窗口）——已核，通过；防御性上限见 L-3

**已核，通过**：
- **轮询不被 error 行驱动**：前端轮询条件已同步改为仅非终态 `hasActive = activeTasks.some(t => t.status==='queued'||'parsing'||'indexing')`（PaperLibrary.jsx:127-128）——error/completed 行常驻任务区但**不会造成无限轮询**；全部终态后 2.5s 轮询停表，tree 仅在手动操作时刷新。
- **响应体膨胀有界**：error 文本 ≤500 字符（paperlib.py:638）、filename ≤255（VARCHAR 硬限）、窗口 SQL 自愈（`updated_at > NOW() - INTERVAL 1 DAY`，paperlib.py:325）+ inbox 7 天 sweep。
- **放大路径不存在**：制造 error 行需先通过 `validate_upload`（≥10KB 且写盘）+ 一次上传 POST；重试仅限有 doc_id（canonical 存在）的任务（api.py:400-415）——无免上传的行数放大器；认证门后无匿名攻击面。
- 残余（L-3，Low）：24h 窗口内 error 行数无 `LIMIT`，脚本化自堆（管理员自身）可把 `/api/papers/tree` 响应推到数十 MB 量级——无外部攻击者路径，故 Low。修复见 F5。

---

## S4 标准检查表（逐条结论）

| # | 检查项 | 结论 |
|---|---|---|
| 1 | 注入（SQL/命令/模板/日志） | **已核，通过**（第 6 项；MinerU 调用为既有 subprocess 封装，本 diff 未触碰） |
| 2 | 鉴权与越权（IDOR/默认拒绝） | **已核，通过**（第 4 项；单管理员无横向越权面；batch_id/task_id 均在门内） |
| 3 | 认证流程（token 生命周期/限速/重放） | **已核，通过**（7d 有效期+session_stamp 吊销+登录限流+假哈希，auth.py 不在本 diff 改动面） |
| 4 | 凭据管理 | **已核，通过**（本 diff 无凭据触碰；ARK key/MySQL 密码仍走 .env，异常文本经 sanitize 打码 key 形态——但见 M-1 的非凭据类泄露） |
| 5 | 数据保护（传输/存储/日志脱敏/错误信息） | **需修复**（M-1：批量端点异常原样回显）；日志面通过 |
| 6 | Web 面（CORS/CSRF/Cookie） | **已核，通过**（无 CORS 中间件=同源；cookie `httponly+samesite=lax` api.py:106-108 → 跨站 POST 不带 cookie，批量端点与既有端点同口径无 CSRF 缺口。备忘：无 `Secure` 标记——127.0.0.1/LAN 部署既有口径，非本 diff 引入，不修） |
| 7 | 文件与反序列化（穿越/白名单/大小限制） | **穿越通过、落盘通过**；**大小限制需修复**（M-2 先读后验、L-2 无 body 总量门槛）；扩展名白名单 + 下游 `%PDF-` 魔数双校验通过 |
| 8 | 依赖与供应链 | **不适用**（本 diff 零新增第三方依赖；uuid/hashlib/threading/pathlib 均标准库） |
| 9 | 第三方调用（超时/重试/证书） | **已核，通过/不适用**（本 diff 未改 MinerU/ARK 调用；`connect` 有 connect_timeout=10s，db.py:57） |

---

## 修复清单

### F1（M-1，必须）批量端点异常 detail 改走统一脱敏
- **位置**：`doclens/serve/api.py:370-372`
- **改法**：
  ```python
  except Exception as exc:  # 单文件异常隔离（不拖垮整批）
      from doclens.serve.sanitize import sanitize_error
      results.append({"filename": fname, "action": "skipped_invalid",
                      "detail": f"处理失败：{sanitize_error(exc)[:140]}"})
  ```
- **附注（建议顺手）**：`doclens/serve/sanitize.py:14-15` 现仅打码 key 形态，建议补一条绝对路径打码（Windows 盘符路径与 Unix 绝对路径 → `…<path>…`），使"错误含路径"这一类在同一口径下整体收敛——单测 `sanitize` 各形态补断言。

### F2（M-2，必须）先验大小、后整读
- **位置**：`doclens/serve/api.py:338-342`（批量）；既有单篇 `doclens/serve/api.py:274-277` 同步修（同款隐患）
- **改法**（`UploadFile.file` 是 SpooledTemporaryFile，可 seek）：
  ```python
  f.file.seek(0, 2)
  size = f.file.tell()
  f.file.seek(0)
  err = paperlib.validate_upload(fname, size)
  if err:
      results.append({"filename": fname, "action": "skipped_invalid", "detail": err})
      continue
  contents = f.file.read(size + 1)   # +1 兜底：并发追加导致超限时显式拒绝
  if len(contents) > paperlib.UPLOAD_MAX_BYTES:
      results.append({"filename": fname, "action": "skipped_invalid",
                      "detail": "文件超过 100MB 上限"})
      continue
  ```
- **验收**：构造 >100MB 的假 part（测试可 monkeypatch 小阈值），断言 4xx/跳过且**服务端未整读**（内存不随文件大小线性增长——至少断言读取发生在校验之后：打桩记录调用顺序）。

### F3（L-3 合并处理，建议）请求体总量门槛
- **位置**：`doclens/serve/api.py`（create_app 内加一层 Content-Length 预检 ASGI/中间件）或 `docs/deploy.md`（反代 `client_max_body_size 2200m`）
- **改法**：入口处 `content-length > (MAX_BATCH_FILES+2) * (UPLOAD_MAX_BYTES + 10MB)` 直接 413；无反代部署时以中间件实现（现无 BaseHTTPMiddleware 依赖——注意沿用裸 ASGI 包装风格，避免缓冲流式响应）。
- **验收**：伪造超大 Content-Length 的请求返回 413 且 handler 未进入。

### F4（L-1，建议）文件名净化帮助函数
- **位置**：`doclens/paperlib.py`（新增 `_safe_basename`）；`doclens/serve/api.py:363`（批量）与 `:298`（单篇）同改；`create_task` 入库名（api.py:366/:303）用净化后名字
- **改法**：
  ```python
  def _safe_basename(name: str, max_len: int = 120) -> str:
      import unicodedata
      s = unicodedata.normalize("NFC", name or "")
      s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cc", "Cf"))
      s = s.replace("/", "_").replace("\\", "_")
      stem, _, ext = s.rpartition(".") if s.endswith(".pdf") else (s, "", "")
      ...
      # 截断保留 .pdf 后缀；空结果回退 "paper.pdf"
  ```
- **验收**：超长名/含 `\n` `\x00` /U+202E/纯 `..` 的用例落盘成功且任务区显示不异常；`VARCHAR(255)` 不再溢出。

### F5（L-3，建议）error 行 defensive LIMIT
- **位置**：`doclens/paperlib.py:322-325`
- **改法**：查询尾追加 `ORDER BY id LIMIT 200`（或 error 分支单独 LIMIT）；前端"已隐藏更早失败任务"文案可选。
- **验收**：现有 `test_list_active_tasks_includes_error` 断言 SQL 文本同步更新。

---

## 复测建议

1. F1/F2/F4 修复后：`pytest tests/test_paper_batch.py tests/test_sanitize.py`（按实际文件名）+ 全量 `pytest`（当前基线 196 passed），并补 4 个安全负向用例：异常回显脱敏断言（含长名触发 DataError 场景）、超限文件不整读、超长/控制字符/RTL 文件名落盘与回显、`_safe_basename` 单测。
2. 复查复测结果追加至本文件「复测结果」节后再进入 S5 收尾。

## 复测结果

（2026-11-17 回填，全部修复验证通过）

| 项 | 修复 | 验证 |
|----|------|------|
| M-1 | `sanitize_error` 补 Unix/Windows 绝对路径打码规则（serve/sanitize.py）；批量端点逐文件 detail 改走 `sanitize_error(exc)[:140]`（api.py 批量端点 except 分支） | 新增 `test_batch_upload_error_detail_sanitized`（detail 不含 /home/doclens、不含 RAG）+ `test_sanitize_error_masks_absolute_paths`（Unix/Windows 两形态 + 无路径文案不受影响）通过 |
| M-2 | 新增 `paperlib.read_upload_capped()`：seek(0,2) 取 size → validate_upload(size) → `read(UPLOAD_MAX_BYTES+1)` 超限显式拒绝；单篇与批量两端点均接线（单篇顺带闭环 M4-02 记池项） | 新增 `test_read_upload_capped_oversize_not_read_entirely`（谎报 150MB size 被 size 预检拒绝、零整读）通过 |
| L-1 | 新增 `paperlib._safe_basename()`：NFC + 删 Cc/Cf + 分隔符剔除 + UTF-8 字节截断（预留 .pdf 后缀 4 字节）；单篇/批量两端点接线（dest 与 create_task 均用净化名） | 新增 `test_safe_basename_sanitizes_malicious_names`（../、反斜杠、\n、U+202E、300 汉字超长、空名回退）通过 |
| L-2 | docs/deploy.md §3 补反代 `client_max_body_size`（≤2200MB）部署要求 | 文档变更（无代码断言） |
| L-3 | `list_active_tasks` 改 `ORDER BY id DESC LIMIT 200` + 回正序展示 | `test_list_active_tasks_includes_error` 同步断言通过 |

复测：全量 `pytest` **251 passed**（基线 239 + 批量功能/安全用例新增）；前端 `npm run build` 成功。结论升级：**通过**。
