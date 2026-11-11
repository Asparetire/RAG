# M2 索引模块 安全专项复查（S4 /security-scan）

- **审查者**：S4 安全专项复查代理（ai-dev-workflow 技能规范 · OWASP Top 10 视角，DeepSeek Harness / glm-5.3-flash）
- **日期**：2026-11-11
- **范围**（m2-runbook §8 判定敏感：外部 API 调用 + 凭据使用）：
  - `doclens/index/`：db.py、embeddings.py、qdrant_store.py、bm25.py、contextual.py、chunker.py
  - `doclens/parse/`：table_struct.py、mineru_parser.py（本次改动部分）
  - `scripts/`：init_db.py、rebuild_docs.py、ingest.py、search_probe.py、quality_report.py
  - 关联配置：doclens/config.py、.gitignore、.env.example、requirements.txt、scripts/smoke_test.py（M0 既有，仅标注）
- **复查方式**：只读审查，未改动任何源码/测试；逐文件通读 + 全仓 grep（密钥/SQL 拼接/subprocess/SSL/pickle/eval/.env 写入）+ git 跟踪状态核验（`git ls-files` / `git log --all --diff-filter=A -- .env`）。

---

## 结论：有条件通过（需修复项）

- **必修 1 项**：S4-01（Medium）——`db.py:31` 解析失败异常消息内嵌完整 MYSQL_URL，**含明文密码**，直接违反 runbook §8"密码不入错误信息"。修复并复测后方可进入收尾（S5）。
- **确认 1 项**：S4-02（Medium·边界确认）——Qdrant 明文 HTTP + 可选 key 的内网边界，按 runbook §8 要求由运营侧书面确认（不阻塞代码收尾）。
- **加固建议 4 项**（Low ×2 / Info ×3，不阻塞）：解析产物路径拼接校验、pickle 信任边界、zip 解包防御性校验、reports/ 公开仓库语料信息暴露。
- Critical：0　High：0　Medium：2　Low：2　Info：4

---

## 复查清单逐项结论（任务清单 7 项）

| # | 检查项 | 结论 | 说明 |
|---|---|---|---|
| 1 | 密钥与凭据 | **需修复**（S4-01） | 无硬编码（grep 全仓无真实 key/密码；tests/test_db.py:10,22 为假凭据夹具 `s3cret`/`p@ss`，可接受）；凭据不入日志（无 logging 模块，print 均不含 key）；`.env` 不入仓库（.gitignore:2 生效，git 历史无 `.env` 提交记录，`git ls-files` 仅含 `.env.example` 占位模板）；**唯一漏洞 = db.py:31 异常消息携带完整 URL+密码** |
| 2 | 注入面 | **通过** | SQL：全部参数化。4 处 f-string IN 子句的 `{ph}` 均为 `",".join(["%s"]*n)` 纯占位符、值走参数元组——embeddings.py:68-71、contextual.py:63-64、bm25.py:98-103、search_probe.py:32-36；bm25.py:101 的 `kind IN ('text','table','caption')` 为静态字面量。写入侧 ingest.py:70-85 / contextual.py:77-81 / embeddings.py:86-91 全部 `%s` 参数化 + executemany。命令注入：subprocess 仅 mineru_parser.py:314-318，列表参数、无 shell=True、无 stdin；MINERU_BIN 来自 .env（运营者自控）。无 eval/exec/os.system |
| 3 | 输入校验 | **通过（带 Low 加固项 S4-03）** | probe_queries.json：仓库内版本化资产（scripts/probe_queries.json），查询仅送嵌入 API，无本地执行面——信任边界成立；但该文件无 schema 校验，格式损坏会 KeyError/类型错误报错退出（健壮性问题，非安全问题）。路径拼接：**ingest.py:111 `doc_dir / c.image_path` 与 quality_report.py:53 直接 join 解析产物路径，未做越界校验**（详见 S4-03） |
| 4 | 网络出口 | **通过 + 记录项（S4-02）** | 三类客户端 URL 全部来自 settings（.env）：embeddings.py:117-118（ark_embed_base_url→ARK）、contextual.py:94（ark_base_url→OpenAI 兼容）、qdrant_store.py:36-39（qdrant_url）——无任何 .env 之外的数据参与 URL 构造，无 SSRF 面。SSL：全仓无 `verify=False`，httpx/OpenAI/Qdrant 客户端均默认开启证书校验。Qdrant 明文 HTTP+key 见 S4-02 |
| 5 | 日志脱敏 | **需修复**（同 S4-01） | embeddings.py 异常消息仅含状态码+响应体截断（148/150）与 cache_key 前 12 位 sha256（176）——不含 Authorization header；httpx 异常文本只带 URL 不带 headers。contextual/qdrant/bm25 异常无凭据。**db.py:31 是唯一把密码拼进异常消息的位置** |
| 6 | 反序列化 | **通过（带 Low 加固项 S4-04）** | 全仓唯一 pickle = bm25.py:73/86（corpus.pkl，list[list[str]] 自产文件）；doc.json/structured/middle/manifest 均走 json.loads（schema.py 纯 JSON 往返）。pickle 信任边界与建议见 S4-04 |
| 7 | .env 双端差异纪律 | **通过（既有行为已标注）** | M2 代码（config.py + index/ 全部 + scripts/ 五脚本）只读 settings、从不写 .env。唯一写 .env 的位置 = scripts/smoke_test.py:133-148 `_write_back_embed_base`——**M0 既有回填行为**：仅写 `ARK_EMBED_BASE_URL` 端点 URL（非密钥）、read-modify-write 保留其余行。标注为既定例外，M2 未新增任何 .env 写入 |

### OWASP Top 10 对照（security-scan 9 项检查）

| OWASP | 结论 | 依据 |
|---|---|---|
| A01 越权/访问控制 | 不适用 | 无 Web 面/多租户；M4 服务化时复查 |
| A02 加密失败 | 记录项（S4-02） | Qdrant 明文 HTTP；其余出站 TLS 校验正常 |
| A03 注入 | 通过 | SQL/命令全参数化，见清单 #2；prompt 注入见 S4-06（Info） |
| A05 安全配置错误 | 通过 | .env.example 无真实凭据；Qdrant key 为空时 `api_key=None`（qdrant_store.py:38）——依赖网络边界，与 S4-02 合并确认 |
| A06 依赖/供应链 | 通过（备注） | M2 新增 qdrant-client/rank-bm25/jieba/PyMySQL/pydantic-settings；pip-audit 本机不可用（运行时在容器，本机无法代跑），requirements.txt 版本未锁（pip freeze 回填为既定待办）——建议收工前在容器内跑 `pip-audit -r requirements.txt` 复核 |
| A07 认证失效 | 不适用 | 无用户认证面 |
| A08 数据完整性失败 | 通过（带加固项） | pickle（S4-04）、zip 解包（S4-05）——CPython zipfile 已内建绝对路径/`..` 剥离，风险可控 |
| A09 日志与监控失效 | **需修复**（S4-01） | 错误信息泄露凭据 |
| A10 SSRF | 通过 | 出站 URL 仅来自 .env，见清单 #4 |

---

## 发现清单

### S4-01（Medium·必修）MySQL URL 解析失败时异常消息携带明文密码
- **位置**：`doclens/index/db.py:31`
- **现状**：`raise DBConfigError(f"MYSQL_URL 无法解析: {raw!r}（…）")`——`raw` 是完整 MYSQL_URL，含 `:密码@` 段。`.env` 格式写错（漏字段/多余字符）时触发，traceback 直达终端；终端输出常被粘贴进对话/文档/issue（本项目 AGENTS.md 的协作习惯恰恰如此），密码随之泄露。
- **风险**：凭据经错误消息泄露（CWE-209 信息经错误消息暴露；OWASP A09），违反 runbook §8"key/密码不入日志不入错误信息"的明文要求。
- **修复建议**：脱敏后再进异常消息——只保留 `user@host:port/db` 与失败原因，例如：
  ```python
  raise DBConfigError(
      f"MYSQL_URL 无法解析（已脱敏: {m and '' or redact(raw)}…）"
  )
  # 实操：把 {raw!r} 换为 {redacted!r}，redacted = re.sub(r"(://[^:@/]+:)[^@]*@", r"\1***@", raw)
  ```
  可选加固：补一条单测断言异常文本不含密码明文（由实现者在 S2' 内补，本复查不改测试）。
- **复测方式**：构造非法 MYSQL_URL 调 `parse_mysql_url`，断言异常消息含 `***` 且不含真实密码段。

### S4-02（Medium·边界确认，非代码缺陷）Qdrant 明文 HTTP + key 的内网边界
- **位置**：`doclens/index/qdrant_store.py:36-39`、`doclens/config.py:56`
- **现状**：`QDRANT_URL` 默认 `http://127.0.0.1:6333`（容器侧）；Windows 侧 .env 写 `10.14.50.123`——key（若设置）与全部向量/正文跨局域网明文传输；key 为空时 Qdrant 无认证，仅靠网络边界防护。
- **风险**：同一局域网内的其他主机可窃听/读写向量库（OWASP A02/A05）。runbook §8 已将该边界列为 S4 必查确认项。
- **处置建议（运营侧确认，不阻塞代码）**：确认 ① 服务器 Qdrant/MySQL 端口仅绑内网/容器网络、不对公网开放；② 局域网为运营者自管可信网络；③ 若未来跨网段或公网访问，QDRANT_URL 切 `https://` 并设 QDRANT_API_KEY（客户端 TLS 校验默认开启，无需改代码）。建议把确认结论补记到本文件或 CHANGELOG。
- **复测方式**：在服务器上 `netstat`/防火墙核对 6333/3306 的监听地址与放行范围。

### S4-03（Low·加固）解析产物的 image_path 未做路径越界校验即参与拼接
- **位置**：`scripts/ingest.py:111`（`p = doc_dir / c.image_path`，113 行读 bytes）、`scripts/quality_report.py:53`（`doc_root / b.image_path`，仅 exists 检查）
- **现状**：`image_path` 源自 MinerU 产物 middle_json → doc.json（mineru_parser.py:108 直取 `str(sub["image_path"])`），入库后原样写进 t_chunk 与 Qdrant payload（qdrant_store.py:95）。pathlib join 语义下，若该值为绝对路径（Windows 盘符/POSIX `/`）会整体替换基准目录，`..` 也会逃出 `doc_dir`。
- **风险**：当前威胁主体限于能写解析产物的本地操作者/本地工具，攻击面小；但 checklist 明确要求边界——一旦将来接入外部解析产物（他人 data/、下载的缓存包），该值可驱动任意文件读取（读出的 bytes 还会送外部嵌入 API，造成本地文件外带）。
- **修复建议**：入库/读取前做双重校验——`p = (doc_dir / image_path).resolve()` 后断言 `p.is_relative_to(doc_dir.resolve())` 且原值为相对路径（拒绝绝对路径与 `..` 段）；校验失败记 manifest/日志并跳过该图。
- **复测方式**：构造含 `../` 与绝对路径的 doc.json 夹具跑 ingest，断言被拒绝且不发起该图嵌入。

### S4-04（Low·加固）BM25 语料 pickle 反序列化的信任边界
- **位置**：`doclens/index/bm25.py:86`（`pickle.loads(CORPUS_PICKLE.read_bytes())`；72-73 落盘）
- **现状**：corpus.pkl 为本管线自产（save_index）、data/ 已 gitignore、单机单操作者——当前信任边界成立，无实际攻击路径。
- **风险**：pickle 反序列化即代码执行（CWE-502）。若 data/bm25/ 可被他人写入（共享目录、备份恢复外来文件、跨机器拷贝 data/），加载即失陷；且 AGENTS 约定 data/ 双端各自维护，恰好降低了误拷概率——保持该纪律即可。
- **修复建议**（择一）：① 语料本质是 `list[list[str]]` + 元数据，改 JSON/JSONL 落盘（成本极低，彻底消除反序列化面）；② 保留 pickle 但在模块 docstring/README 写明"data/bm25 仅由本管线写入、不接受外来文件"，并在 load_index 前校验同目录 chunks.jsonl 与 pickle 行数一致（轻量完整性哨兵）。
- **复测方式**：① 改 JSON 后单测往返一致；② 篡改 corpus.pkl 后 load 应报错拒绝。

### S4-05（Info·加固）zip 解包未做成员名显式校验
- **位置**：`doclens/parse/mineru_parser.py:353`（`zf.extractall(out_dir)`）
- **现状**：zip 由本地 mineru-kit 生成（可信源）；CPython zipfile.extract 自 3.6 起内建剥离绝对路径前缀/盘符/`..` 组件，Zip Slip 基本免疫。
- **建议**：防御性加固（可选）——解包前校验 `all(not name.startswith(("/", "\\")) and ".." not in Path(name).parts and Path(name).is_relative_to extract 目标)`，或用 `zf.namelist()` 白名单仅放行 structured_content/middle_json/markdown/images 前缀。维持 Info 不阻塞。

### S4-06（Info）上下文前缀生成的 prompt 拼接面
- **位置**：`doclens/index/contextual.py:41-43`（doc_title/heading/chunk 原文直接 format 进 prompt）
- **现状**：语料为自选公开论文，生成结果仅作检索前缀入库，无指令执行面；若未来接入不可控语料，存在提示注入污染前缀（进而影响检索排序）的可能。
- **建议**：M5 全量启用 E 档前，对超长/异常前缀（空、过长、含提示词回声）做输出校验；语料来源扩展时复查此项。

### S4-07（Info）reports/ 语料信息随公开仓库暴露
- **位置**：`scripts/quality_report.py:144,206`（报告写入 reports/，.gitignore 未排除该目录）；`git ls-files` 确认 parse_quality_m1.md / table_audit_m2.md / cost.md 已跟踪
- **现状**：报告含语料论文标题、DOI、原始文件名（来自 data/corpus_manifest.json 的 original_name）。仓库为 GitHub 公开（Asparetire/RAG）。非凭据泄露，但自选语料的构成属于作品集项目的半敏感信息。
- **建议**：确认可公开后维持现状；若不想暴露，给 .gitignore 追加 reports/*.md（保留 .gitkeep）或报告里脱敏 original_name 列。

### S4-08（Info）rebuild_docs.py CLI 参数直接拼接 PARSED_DIR
- **位置**：`scripts/rebuild_docs.py:49`（`PARSED_DIR / a`）
- **现状**：操作者自选目录名的本地调试工具，传 `..` 可重建 data/ 之外的目录内容——属运营者自有权范围，非攻击面。
- **建议**：可选——校验参数不含路径分隔符（只接受 doc_id 形态 `^[0-9a-f]{12}$`）。

### S4-09（Info·既有行为标注，按任务要求）smoke_test.py 的 .env 回填
- **位置**：`scripts/smoke_test.py:133-148`
- **现状**：M0 既有决策点①回填：仅改写 `ARK_EMBED_BASE_URL` 一行（端点 URL，非密钥），read-modify-write 保留其余行与注释。清单第 7 项要求的"标注"即此条：**M2 全部新增代码零 .env 写入，双端差异纪律成立**；该例外维持 M0 原样、无需改动。
- **建议**：无（若日后该函数扩展为回填密钥类字段，需重新过 S4）。

---

## 通过项正面清单（无需动作）

1. **SQL 全参数化**：4 处动态 IN（embeddings.py:68-71、contextual.py:63-64、bm25.py:98-103、search_probe.py:32-36）占位符构造正确；t_doc/t_chunk/t_embed_cache/t_ctx_prefix 全部写入走 `%s` 参数化（ingest.py:70-85、embeddings.py:86-91、contextual.py:77-81）；init_db.py DDL 为静态字面量。
2. **命令注入面收敛**：subprocess 全仓仅 MinerU 桥接一处，列表参数、无 shell、有超时（mineru_parser.py:314-318）；错误消息只带 stdout/stderr 尾部与文件名，不含凭据。
3. **出站 URL 与 SSL**：三类外部客户端（httpx/OpenAI/Qdrant）URL 均仅来自 .env/settings，无 verify 关闭、无 trust_env 定制（OWASP A10 通过）。
4. **凭据不硬编码、不入仓库**：代码与测试夹具均无真实凭据；`.env`/`data/`/`*.db` 被 .gitignore 覆盖，git 全历史无 `.env` 提交；.env.example 仅占位符。
5. **异常消息卫生**（除 S4-01）：嵌入链路异常仅含状态码/响应体截断/sha256 前缀，Authorization header 从不进异常或日志。
6. **输出编码细节到位**：table_struct.py `_cell()` 对 `|`/换行做替换，防止表格内容破坏 markdown 结构（外泄到下游渲染面风险低）。

---

## 放行条件与复测结果

| 项 | 处置 | 复测结果 |
|---|---|---|
| S4-01 db.py:31 密码入异常 | **修复后放行** | 待修复（本轮只审查未改码；修复后按"复测方式"验证，异常消息须含 `***` 且不含密码） |
| S4-02 Qdrant 明文边界 | 运营侧书面确认后放行 | 待确认（监听范围/防火墙核对，结论补记） |
| S4-03 ~ S4-08 | 加固建议，不阻塞 | 建议排入 M2 收尾或 M3 首项 |
| S4-09 | 标注即可 | 已标注（M0 既有） |

- 本次复查**未改动任何源码/测试**，仅新增本报告文件。
- 结论按 ai-dev-workflow S4 规范：**有条件通过（需修复项）**——S4-01 修复并复测通过后，M2 可进入 S5 收尾。

---

## 修复与复测记录（2026-11-11，S2' 实现侧回应）

| 项 | 处置 | 复测结果 |
|---|---|---|
| **S4-01** db.py 异常消息泄漏密码 | **已修复**：`parse_mysql_url` 解析失败时消息先经 `re.sub(r"(://[^:@/]+:)[^@]*@", r"\1***@", raw)` 脱敏再抛出（db.py）；新增单测 `tests/test_db.py::test_parse_error_message_masked_password`（断言异常文本不含明文密码且含 `***`） | ✅ 本地 pytest 4/4 passed（含新单测）；容器复测通过 |
| **S4-02** Qdrant/MySQL 明文传输边界 | **已取证确认（结论：边界成立）**：① 容器内 `/proc/net/tcp` 解析——6333 绑定容器接口（docker 桥接 172.17.0.19）；② 宿主机外部探测（Windows → 10.14.50.123）——**3306 与 6333 均 TcpTestSucceeded=False，两端口未发布到外部接口**；③ 实际连接面 = 容器回环 + docker 桥接内网。结论：明文 HTTP+key 的传输面被限制在宿主内网，与 runbook §8"内网边界确认"一致，**接受现状**（附带发现：AGENTS.md "Windows 侧 .env 写 10.14.50.123" 的约定实际不可达，双端 .env 约定待 M3 前勘误） |
| S4-03 image_path 越界 | **已加固**：ingest.py 新增 `_image_file()`（resolve + `is_relative_to` 越界校验 + 缺失文件跳过记日志）；quality_report.py 为本地只读脚本、读取 M1 自产数据，维持原状并记录 | 本地 pytest 通过；全量入库重跑点数不变 |
| S4-04 pickle 信任边界 | **已写明纪律**：bm25.py `load_index` docstring 注明 corpus.pkl 仅由 save_index 自产、不入库、不接受外部文件 | 代码注释 |
| S4-05~08 | 记录在案，排 M3 前复查 | — |

**复测后结论：通过**（S4-01 修复+单测复测通过；S4-02 取证闭环）——M2 可进入 S5 收尾。
