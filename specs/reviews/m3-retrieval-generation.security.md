# M3 检索+生成模块 安全专项复查（S4 /security-scan）

- **审查者**：S4 安全专项复查代理（ai-dev-workflow 技能规范 · OWASP Top 10 视角，DeepSeek Harness / glm-5.3-flash）
- **日期**：2026-11-11
- **范围**（m3-runbook 判定敏感面：外部 API + 凭据 + 新增落盘面）：
  - `scripts/query_cli.py`（端到端编排：读 .env、连 MySQL/Qdrant/方舟、写 trace/reports）
  - `doclens/trace.py`（**新增落盘面**：trace 脱敏纪律）
  - `doclens/retrieve/`：rerank.py（t_rerank_cache + LLM + 降级 fail_reason）、hybrid.py（回表 SQL + payload 解析）、router.py（纯函数，附带核过）
  - `doclens/generate/`：vlm.py、fallback.py（judge）、context.py、citations.py（LLM 调用与 prompt 注入面）
  - `doclens/config.py`（Profile 注册表）、`scripts/init_db.py`（t_rerank_cache DDL）
  - 0.1 清障批改动的 M2 文件：`doclens/index/db.py`（m-12 复核）、embeddings.py（m-10/n-5/n-6）、qdrant_store.py（n-15）、bm25.py（n-11）、contextual.py（m-11）、`scripts/ingest.py`（m-9）、rebuild_docs.py、parse/table_struct.py、parse/mineru_parser.py
  - 依赖：requirements-lock.txt（新增）、requirements.txt
- **复查方式**：只读审查，未改动任何源码/测试；逐文件通读 + 全仓 grep（凭据/pickle/eval/subprocess/verify=False/.env 写入/execute 参数化）+ `git diff m2..HEAD` 全量核对变更面 + **本机实证两处**（openai 依赖链 importlib.metadata；db.py 脱敏正则 4 形态）。沿用 M2 复查（specs/reviews/m2-indexing.security.md）的取证口径，其结论只引用不重取。

---

## 结论：通过（附加固建议，无必修项）

- **Critical：0　High：0　Medium：0　Low：2　Info：3（另 1 项非安全健壮性顺带记录）**
- Low ×2：S4-10（db.py 脱敏正则残留缺口——无 `@` 截断形态密码仍入异常消息，本机实证）、S4-11（`_load_image_blob` 读侧无路径越界校验——纵深防御缺口）
- 均不阻塞 M3 收官；建议 S4-10/S4-11 排 M3 收尾或 M4 首项，S4-15（一行守卫）可 M3 内顺手修。
- M2 既有结论边界全部复核成立：m-12 fullmatch 修复有效、ingest 写侧越界校验仍在、M3 零新增 pickle、零 .env 写入、3306/6333 外部不可达结论继续引用（S4-02，未重新取证）。

---

## 复查清单逐项结论（任务清单 7 项）

| # | 检查项 | 结论 | 说明 |
|---|---|---|---|
| 1 | 密钥与凭据 | **通过（带 S4-10 记录）** | 无硬编码（grep 全仓；config.py:81-99 仅模型名/端点默认值，非敏感；.env.example 全占位符）。M3 三处 LLM 客户端（rerank.py:240、vlm.py:101、fallback.py:101）api_key 仅进 SDK 参数，不入日志/print/异常构造。**异常路径取证**：① rerank 降级 fail_reason（rerank.py:320）= 异常类型名 + `str(exc)`——openai SDK 异常文本为状态码+响应体/连接错误描述，不回显 Authorization header（M2 清单 #5 同口径）；② hybrid 回表异常 = pymysql 错误码+消息（无密码）；③ query_cli 无 try/except 吞错，traceback 直出终端——pymysql/openai 异常文本均不含凭据。grep 证实 print 无凭据；**M3 零 .env 写入**（全仓唯一写 .env 仍为 M0 smoke_test.py:134-148 既有例外，M2 S4-09 已标注）。db.py m-12 复核见下文与 S4-10 |
| 2 | trace 落盘面 | **通过** | trace.py 只写调用方传入的结构化数据，模块自身无 settings 依赖（防回归断言在 tests/test_trace.py:50-56：源码含 "settings" 即失败）。query_cli 六类事件（meta/routes/fused/rerank/context/llm_fallback，query_cli.py:181-232）逐字段核过：无 key/密码/连接串/Qdrant URL；.env 值中仅**模型名**（非敏感，gen.model / rerank_out.model）入 trace；问题原文与答案入库属预期（m3-runbook §3.1 设计，F0–F6 归因需要）；rerank fail_reason 与 judge reason 为 LLM/异常文本，当前无凭据（S4-13 防御性建议）。落盘 `data/traces/` 被 .gitignore `data/` 覆盖不入库。**SQL 全参数化（三处+一）**：rerank._cache_get/_cache_put（rerank.py:193-197/220-225，`%s`+元组）、query_cli._fetch_members（:53-57，500 分批纯占位符）、query_cli ctx_prefixes（:143-146，占位符——注意空列表占位符失配崩溃，见 S4-15）、hybrid.fetch_chunk_meta（:161，`_FETCH_SQL.format(ph=ph)` 值走参数元组） |
| 3 | 提示注入 | **通过（S4-12 评估）** | 用户问题与检索文档内容拼进 LLM 提示词共三处（重排/judge/生成）；本项目无写操作、无工具调用、输出仅经 citations 纯正则解析——最大后果 = 答案被操纵 / 拒答被绕过 / 重排序被操纵，不可达代码执行与凭据窃取。评级 Info，后果边界与缓解建议见 S4-12 |
| 4 | pickle/反序列化 | **通过** | M3 新增代码零 pickle（grep 证实全仓唯一 pickle = bm25.py:73/86，M2 既有；`git diff m2..HEAD` 对 bm25.py 仅 META_JSONL 注释变更 n-11，pickle 逻辑未动）——沿用 M2 S4-04 结论（信任边界纪律已写入 load_index docstring）。M3 全部 JSON 解析走 json.loads（rerank cache ranking、context._maybe_json_list、hybrid heading_path），无其他反序列化面 |
| 5 | 依赖 | **通过（备注）** | requirements-lock.txt 新增（容器 pip freeze 全量锁定，FR-7.2）。**httpx2 恢复声明核实（本机 importlib.metadata 实证）**：openai（本机 3.46.0）Requires 含 `httpx2<3,>=2.12.0`；httpx2 2.16.0 Requires 含 `httpcore2==2.16.0`（exact 钉扎）；httpcore2 2.16.0 需 `h11>=0.16`、`truststore>=0.10`——lock（httpx2==2.16.0 / httpcore2==2.16.0 / h11==0.16.0 / truststore==0.10.5）**全满足，lock 注释声明属实**。备注：本机 openai 3.46.0 与 lock 3.48.0 存在 minor 漂移（lock 以容器为准，requirements.txt 头注既定口径）；pip-audit 仍建议在容器内跑（M2 A06 待办延续，本机 pypi 直连不可达未重跑） |
| 6 | 文件路径 | **通过（带 S4-11 纵深防御建议）** | `_load_image_blob`（query_cli.py:68-78）路径拼接无越界校验：相对路径在 PROJ_ROOT 与 data/ 两个基准目录间试探、绝对路径原样放行、`..` 不校验。image_path 来自 t_chunk / Qdrant payload——均为 M2 ingest 受控写入（**写侧加固仍在**：ingest.py:42-45 `_image_file` resolve + `is_relative_to` + 缺失跳过，:122 调用点未回退）。威胁主体需 DB/Qdrant 写权限，攻击面小；但写读两侧校验不对称，读出的 bytes 还会编码 data URL 送外部方舟 API（本地文件外带面）——评 Low，见 S4-11 |
| 7 | report 文件写入 | **通过（带 S4-14 Info）** | `--smoke` 写 `reports/smoke_{profile}{'_pro'}.md`（query_cli.py:259）——profile 经 argparse `choices=list(PROFILES)` 白名单约束（A–F），`_pro` 为字面量，**无用户可控路径**；写目录固定 PROJ_ROOT/reports。内容含冒烟问题原文+答案截 300 字+trace id，已随 git 提交（m2..HEAD 显示 reports/smoke_A.md、smoke_D.md 新增）——非凭据，但延伸 M2 S4-07 的公开仓库语料信息暴露面，见 S4-14 |

### OWASP Top 10 对照（security-scan 9 项检查）

| OWASP | 结论 | 依据 |
|---|---|---|
| A01 越权/访问控制 | 不适用 | 无 Web 面/多租户；M4 服务化时复查（CLI 单操作者） |
| A02 加密失败 | 沿用 M2 S4-02 | Qdrant 明文 HTTP 边界已取证确认（引用，未重取）；M3 出站 LLM 调用走 `ark_base_url`（https，来自 .env），TLS 校验默认开启，全仓无 `verify=False`/`trust_env`（grep 证实） |
| A03 注入 | 通过 | SQL 全参数化（清单 #2 五处 execute 逐一核对）；命令注入零新增（subprocess 仍仅 mineru_parser 一处，M3 未触碰）；prompt 注入见 S4-12（Info） |
| A05 安全配置错误 | 通过 | .env.example 全占位符；qdrant api_key 为空时 `api_key=None`（qdrant_store.py:39，M2 既有）——依赖网络边界，与 S4-02 合并 |
| A06 依赖/供应链 | 通过（备注） | lock 文件建立且 httpx2 链条核实一致（清单 #5）；本机↔lock 版本漂移已备注；pip-audit 容器内待跑 |
| A07 认证失效 | 不适用 | 无用户认证面 |
| A08 数据完整性失败 | 通过 | M3 零新增反序列化面（清单 #4）；t_rerank_cache 写入参数化 + 幂等 ON DUPLICATE KEY |
| A09 日志与监控失效 | 通过（带 S4-10 记录） | M3 新增链路异常消息卫生良好（fail_reason 仅异常文本、无凭据）；db.py 残留无 `@` 形态缺口见 S4-10（Low） |
| A10 SSRF | 通过 | 出站 URL 全部仅来自 settings/.env（ark_base_url×3、ark_embed_base_url×1、qdrant_url×1、mysql_url）；用户问题/检索内容**不参与任何 URL 构造**；图片仅以 data URL 上行至方舟（目的端仍为 .env 配置的 base_url） |

---

## 发现清单

### S4-10（Low·加固）db.py 脱敏正则对"无 @ 的截断形态"失效——密码仍可入异常消息（m-12 复核附带发现）
- **位置**：`doclens/index/db.py:36-37`（脱敏分支 `re.sub(r"(://[^:@/]+:)[^@]*@", r"\1***@", raw)`）
- **m-12 复核结论（任务指定项）**：`_URL_RE.fullmatch(raw)` 锚定匹配已生效（db.py:34；单测 tests/test_db.py:31-39 覆盖连字符库名/query 参数/尾随垃圾三形态拒绝）；脱敏分支保留且对**含 @ 的**解析失败形态有效（query 参数、缺库名、缺端口等常见误配均含 `@host` 段，能正确打码）；S4-01 单测（test_db.py:42-50）在。
- **残留缺口（本机实证）**：正则要求密码段后必须出现 `@` 才打码——URL 若被截断成"只有 `user:pwd`、后面什么都没有"的形态，脱敏不生效：
  ```
  mysql+pymysql://u:SECRET@h:3306/  → 'mysql+pymysql://u:***@h:3306/'   leak: False ✅
  mysql+pymysql://u:SECRET          → 'mysql+pymysql://u:SECRET'          leak: True  ❌
  mysql+pymysql://u:SECRET:         → 'mysql+pymysql://u:SECRET:'         leak: True  ❌
  mysql+pymysql://u:SECRET@         → 'mysql+pymysql://u:***@'            leak: False ✅
  ```
- **风险**：.env 手工编辑误删后半段（该形态恰是"复制粘贴截半行"的典型事故）时，DBConfigError 携带明文密码直达终端 traceback；本项目协作习惯（AGENTS）恰是终端输出常被粘贴进对话/文档（CWE-209 / OWASP A09，违反 runbook §8"密码不入错误信息"）。触发条件较苛刻（评 Low），且现有单测恰好只覆盖含 @ 形态，防不住该缺口。
- **修复建议**：去掉对尾部 `@` 的要求——`re.sub(r"(://[^:@/]+:)[^@]*", r"\1***", raw)`。取证推演：含密码形态整体打码；无密码形态（`://user@host`）因 user 后无 `:` 不匹配、原样保留；无 user 形态（`://127.0.0.1:3306/db`）会过度打码端口/库名——失败路径上过度打码属可接受的 fail-safe 方向。
- **复测方式**：补单测——`parse_mysql_url("mysql+pymysql://u:SECRET")` 断言异常消息含 `***` 且不含 `SECRET`（与既有 test_parse_error_message_masked_password 并列）。

### S4-11（Low·纵深防御）_load_image_blob 读侧无路径越界校验（与 ingest 写侧校验不对称）
- **位置**：`scripts/query_cli.py:68-78`
- **现状**：`Path(image_path)` 后仅判断是否绝对路径（绝对路径**原样放行**读取，:73-74）；相对路径在 `PROJ_ROOT / image_path` 与 `data/ / image_path` 间试探，`..` 段不校验、不 resolve、无包含关系断言。对照写侧：ingest.py:42-45 `_image_file`（resolve + `is_relative_to(doc_dir)` + 缺失跳过）在本轮 diff 中确认未被回退。
- **威胁链**：image_path ← t_chunk.image_path / Qdrant image payload ← 均为 M2 ingest 受控写入（当前干净）；一旦 DB/Qdrant 被篡改（本地攻击者、误操作手工修数、未来新增写入方），`..` 或绝对路径即可驱动读取任意本地文件，且读出的 bytes 会经 `_data_url`（vlm.py:62-65）编码后**上行到外部方舟 API**——本地文件外带面（与 M2 S4-03 风险描述同源）。
- **风险**：当前信任边界（单机单操作者、自产数据）成立，实际攻击路径不存在；属纵深防御缺口——写侧挡住的值理论上不会入库，但读侧裸奔违背"入口校验"惯例。评 Low。
- **修复建议**：复用 ingest._image_file 同款逻辑——`(PROJ_ROOT / image_path).resolve()` 后断言 `is_relative_to(PROJ_ROOT.resolve())` 且原值为相对路径；校验失败返回 None（与现有缺失容错同路径）并在 trace 记一条。
- **复测方式**：夹具 `../x.png` / `C:\secret.png` / 绝对路径三种输入 → 返回 None、不发起该图调用。

### S4-12（Info）提示注入暴露面评估（问题与检索内容双拼接；后果边界=答案操纵，无执行面）
- **位置**（三处拼接面）：① rerank.py:157（`f"Query: {question}"` + 候选正文前 300 词）；② context.py:169-172（`f"问题：{ctx.question}"` + Source 正文，经 vlm.py:98 与 fallback.py:98 复用）；③ fallback.py:99（judge 提示词 + 含问题行的全文 context）。
- **注入源**：用户问题（CLI 操作者自输入，自注入自，威胁有限）+ 检索文档内容（t_chunk ← M2 MinerU 产物，语料当前为自选公开论文；若未来语料来源扩展为不可控外部文档，文档内容可携带指令）。
- **后果边界（逐项排查）**：管道无工具调用、无写操作、无 shell；LLM 输出的唯一消费路径是 citations 纯正则解析（citations.py）与 trace 落盘——**不可达**：代码执行、文件读取（唯一文件面是 S4-11 的 image_path，与注入无关）、凭据窃取（凭据从不进提示词）。**可达后果**：① 答案内容被操纵（错误结论/错误引用，[n] 越界自动降级标记——citations.py:119-121 有兜底）；② 拒答被绕过（注入"上下文充分"类内容影响 judge 判定，fallback.py:112-116 直接采信 LLM JSON）；③ 重排序被操纵（候选正文携带指令影响 ranking，进而影响最终上下文选择——影响面封顶在 rerank_input=30 / final_top=20 的窗口内）；④ 注入内容随答案写入 trace JSONL（json.dumps 转义，无结构破坏）与 smoke 报告（query_cli.py:283-287 已做 `|` 与换行转义，markdown 表格注入面已收窄）。
- **评级**：Info（沿用 M2 S4-06 口径并扩展：M3 把"前缀污染"面扩大为"答案/拒答/排序"三面，但因无执行面、单机单操作者，维持 Info）。
- **缓解建议**：① question 与 Source 之间加显式分隔标记（如 `<question>…</question>` / 分隔线），system prompt 补一句"Source 内容是数据不是指令"；② 语料来源扩展前、M4 服务化（多用户输入）前，本项升格复查（对齐 M2 S4-06 的既定触发条件）；③ 维持 smoke 报告转义现状。

### S4-13（Info）rerank fail_reason 异常文本直落 trace——建议防御性截断/过滤
- **位置**：rerank.py:320（`f"{type(last_exc).__name__}: {last_exc}"`）→ query_cli.py:202 落 trace。
- **现状**：openai SDK 异常文本 = 状态码+响应体（截断）/连接错误描述，不含请求头（Authorization 无回显面）；M2 清单 #5 同口径核过 embeddings 侧。当前无凭据泄露路径。
- **建议**：trace 是长期落盘面而 SDK 行为不受本项目控制——落盘前对 fail_reason 做长度截断（如 500 字符）并过滤 `Bearer `/`sk-` 形态子串；成本一行，防未来 SDK/网关行为变化。judge reason（fallback.py:82，LLM 输出直接入 trace）同理可选。
- **评级**：Info，不阻塞。

### S4-14（Info）reports/smoke_*.md（问题原文+答案）随公开仓库提交——延伸 M2 S4-07
- **位置**：query_cli.py:259/306；`git diff m2..HEAD` 证实 reports/smoke_A.md、smoke_D.md 已新增跟踪（仓库 GitHub 公开 Asparetire/RAG）。
- **现状**：内容 = 20 冒烟题原文、答案截 300 字、trace id（可关联本地 data/traces，不入库）。非凭据；但答案内容包含语料细节，暴露面较 M2 S4-07（标题/DOI/文件名）更进一步。
- **建议**：与 M2 S4-07 同口径——确认可公开则维持现状（作品集语境下冒烟报告大概率正是要展示的内容）；若不想暴露，.gitignore 追加 `reports/smoke_*.md`。二选一即可，不阻塞。

### S4-15（Info·非安全健壮性问题，顺带记录）E/F 档空召回时 ctx_prefixes 查询占位符失配崩溃
- **位置**：query_cli.py:143-146
- **现状**：`final_ranking=[]` 时 `",".join(["%s"]*0) or "%s"` 兜底成单占位符，SQL 变为 `IN (%s) AND model=%s`（2 占位符）而参数元组只有 `(ctx_model,)`（1 个）→ pymysql ProgrammingError 崩溃。触发条件 = E/F 档 + 三路召回全空（冒烟全有命中故未暴露）。对照 `_fetch_members` 对空 ids 已有早退（:45-46），该查询缺同款守卫。报错路径无凭据，属自伤型健壮性问题，非攻击面。
- **建议**：查询前加 `if not final_ranking: ctx_prefixes = {}` 早退（一行）；复测：A 档题在 E 档空召回夹具下正常拒答不崩。

---

## M2 S4 结论边界对照（引用不重取）

| M2 结论 | M3 复核结果 | 状态 |
|---|---|---|
| **S4-01** db.py 异常消息密码脱敏 | m-12 fullmatch 修复有效（锚定+三形态拒绝单测在，tests/test_db.py:31-39）；脱敏分支保留（db.py:36-37）且含 @ 形态正确打码；**发现无 @ 截断形态残留缺口 → S4-10（Low）** | 修复有效，留尾巴 |
| **S4-02** 3306/6333 外部不可达（M2 取证：容器 /proc/net/tcp 绑定 docker 桥接接口 + Windows→10.14.50.123 双端口 TcpTestSucceeded=False） | **直接引用，未重新取证**。M3 未新增任何监听面——五类外部客户端全部为出站连接（Qdrant 检索、方舟 rerank/judge/生成/嵌入），Qdrant/MySQL 仍按 .env 指向 127.0.0.1（隧道/容器内网） | **结论继续成立** |
| S4-03 image_path 越界（ingest 写侧） | 写侧加固仍在（ingest.py:42-45 `resolve`+`is_relative_to`，:122 调用点未回退）；M3 **新增读侧** `_load_image_blob` 未校验 → S4-11（Low，纵深防御） | 写侧维持，读侧新面 |
| S4-04 BM25 pickle 信任边界 | M3 零新增 pickle；bm25.py 本轮仅注释变更（n-11），docstring 纪律声明在 | 沿用 |
| S4-05 zip 解包 / S4-08 rebuild_docs 参数拼接 | M3 未触碰（rebuild_docs.py 仅加 sys.path 自举 3 行）；维持 Info 原判 | 沿用 |
| S4-06 contextual prompt 拼接面 | M3 扩展为三处 LLM 拼接面（重排/judge/生成）→ S4-12（Info） | 面扩大，级不变 |
| S4-07 reports/ 公开仓库语料暴露 | M3 新增 smoke 报告入库 → S4-14（Info） | 面扩大，级不变 |
| S4-09 smoke_test .env 回填例外 | M3 全部新增代码零 .env 写入（grep 证实）；例外维持 M0 原样 | 维持 |

---

## 通过项正面清单（无需动作）

1. **trace 脱敏纪律成立**：trace.py 无 settings 依赖（源码断言防回归），六类事件逐字段核过无凭据；落盘面在 gitignore 内；trace 不能炸主链路（`_jsonable` 全类型兜底）设计使异常路径也不会绕过脱敏。
2. **SQL 全参数化**：M3 全部 5 处 execute（rerank 读写缓存、query_cli 回表与 ctx 前缀、hybrid 回表）占位符构造正确、值走参数元组；init_db.py DDL 为静态字面量；t_rerank_cache 无触发器/存储过程面。
3. **LLM 客户端卫生**：三处客户端 api_key 仅进 SDK 参数；client 即建即关/AsyncOpenAI 常规用法；无 header 级日志；max_tokens/timeout 全部显式上限（资源耗尽面收敛）。
4. **降级路径不放大异常**：rerank 失败回 RRF 序+degraded 标记、judge 失败默认放行（均不重抛异常），错误文本收敛进 trace 单字段。
5. **citations 解析纯函数**：纯正则+纯数据结构，`_RANGE_SPAN_CAP=50` 对异常大区间有防御；无 eval/exec。
6. **smoke 报告写入**：文件名白名单+固定目录+目录已存在才写（mkdir parents=True），无路径可控面；表格转义已做。
7. **M2 加固零回退**：ingest._image_file、qdrant_store n-15（吞异常收窄+告警）、search_tier 未知档报错、contextual 失败隔离（只打印 chunk_id 不打印异常文本）——本轮 diff 逐一确认。

---

## 放行条件与建议排期

| 项 | 处置 | 建议 |
|---|---|---|
| S4-10 db.py 无 @ 形态脱敏缺口 | Low·加固 | M3 收尾或 M4 首项：改一行正则 + 补一个无 @ 形态单测（复测方式见发现项） |
| S4-11 _load_image_blob 越界校验 | Low·纵深防御 | M3 收尾或 M4 首项：复用 _image_file 同款校验；改动前不阻塞 |
| S4-12 提示注入 | Info | M4 服务化/语料扩展时升格复查；当前可选加分隔标记 |
| S4-13 fail_reason 截断 | Info | 可选一行加固 |
| S4-14 smoke 报告公开性 | Info | 用户二选一确认即可 |
| S4-15 空召回占位符失配 | Info·健壮性 | **建议 M3 内顺手修**（一行守卫）——非安全项 |
| M2 S4-02 边界确认 | 已闭环 | 引用 M2 取证结论，3306/6333 外部不可达继续成立 |

- 本次复查**未改动任何源码/测试**，仅新增本报告文件。
- 结论按 ai-dev-workflow S4 规范：**通过**（无 Medium 及以上发现；Low/Info 建议项不阻塞 S5 收尾）。
