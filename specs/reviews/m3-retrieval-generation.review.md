# 代码审查：m3-retrieval-generation（M3 检索+生成里程碑）

> **审查者**：S3 通用代码审查（独立审查代理，只审不改）
> **日期**：2026-11-11 22:30（北京时间）
> **范围**：M3 新增/改动约 2000 行——`doclens/retrieve/{hybrid,rerank,router}.py`、`doclens/generate/{context,vlm,citations,fallback,__init__}.py`、`doclens/trace.py`、`doclens/config.py`（Profile 注册表）、`scripts/{query_cli,init_db}.py`、0.1 清障批（5739279）抽查、对应 9 个测试文件。
> **计划依据**：[specs/plans/m3-runbook.md](../plans/m3-runbook.md)（K0–K9 + §3.1 实施细则，先读后核对）、[specs/research/m3-retrieval-generation-survey.md](../research/m3-retrieval-generation-survey.md)（R1–R19）、[m2 review](m2-indexing.review.md)（0.1 清障对照）。
> **审查快照**：HEAD = ecd3082，工作区干净；`python -m pytest -q` → **169 passed in 8.10s**（本机 doclens 环境实跑，PYTHONUTF8=1）。

## 结论

**Blocker 1 ｜ Major 2 ｜ Minor 8 ｜ Nit 12**。模块级代码质量整体优秀：hybrid/rerank/router/context/citations/fallback 与 K1–K7 及 R1–R19 逐项对齐，纯函数设计、手算级单测、异常路径完备、SQL 全参数化、无调试残留、无硬编码密钥路径。**但编排层（query_cli）存在一个 Blocker：1bf4229 的"组员就地展开"重构把重排输出彻底丢掉了——D/E/F 档的 LLM 重排（实测 11.2s/次的成本）对最终上下文零影响**，且与"重排疑似恒降级"（Major-1）互相掩盖，冒烟报告未察觉。该 Bug 恰好落在零测试覆盖的编排函数里（三次连续 hotfix 均无单测）。建议：**修复 Blocker 后方可进入 S4 安全复查与 M3 收官**；Major-1 需先查容器 trace 的 degraded 率定案。

## Blocker（1 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| B-1 | scripts/query_cli.py:120-133（`answer_question` 重排分支） | **重排输出被完全弃用，D/E/F 档重排对最终上下文零影响**。1bf4229 之前是 `final_ranking = rerank_out.ranking`（git show 证实）；重构后 `ranking = rerank_out.ranking`（:120）成为死变量，`final_ranking` 改由遍历 `rr.pool[:profile.final_top]`（**融合去重序**）+组员就地展开构建。后果：① K1 管道序"重排输入 30→输出 20→组装"被拦腰截断，重排只出现在 trace 里；② D 档验收"重排生效（融合序 ≠ 最终序）"仅被去重/展开的顺序差**虚假满足**；③ M5 消融若基于现状，D 档重排贡献恒为 0（还白付 11.2s/次延迟与 token 费）；④ 降级回 RRF 序与重排成功在最终序上不可区分，degraded 标记失去意义。直接诱因：为拿 `h.group_members` 需要 Hit 对象，实现者贪便遍历了 pool 而非 ranking | 用 `hit_by_id = {h.chunk_id: h for h in rr.pool}` 把 rerank 序映射回 Hit：`window = [hit_by_id[c] for c in rerank_out.ranking if c in hit_by_id][:profile.final_top]`，再按现有展开逻辑（代表后跟组员、seen 去重、展开后交 assemble 按 final_top 截断）；末尾恢复 101f0d1 的保底——融合池 top-20 中 ranking 未覆盖块补到尾部（degraded 时 ranking=输入序=pool[:30] 序，行为自动退化正确）。同时删除死变量 `ranking`/`members_map`（:103-104、:120），**并给"组员展开+截断"抽成纯函数补单测**——三次 hotfix（2b7ac96/101f0d1/1bf4229）全部落在这个无测试的函数里，B-1 正是这么漏掉的 |

## 已知修复验证（0.1 清障批 5739279 抽查 4 处）

| 修复项 | 验证结果 |
|---|---|
| m-4 编号型 References | ✅ 完整。chunker.py:31 `_REFERENCE_RE` 放开可选编号前缀 `^\s*(?:\d+[.:：]?\s*)?(references\|bibliography\|参考文献)\b` + IGNORECASE，:154 按 heading_path 逐级匹配；test_chunker 新增用例 |
| m-5 表头 drop_cols 错位 | ✅ 完整。table_struct.py:377 表头按 drop_cols 同步剔除、:408 汇总行传实际 drop_cols，与主体行宽对齐（原 :379 `set()` 已修） |
| m-10 批内失败不落缓存 | ✅ 完整。embeddings.py:174-188 `return_exceptions=True` 收集后先 `rows` 落缓存（:185）再 raise，注释引 m-10 |
| m-11 contextual 单块失败全批丢 | ✅ 完整。contextual.py:109-136 单块重试 3 次、退避在信号量外、失败清单汇总打印、返回只含成功条目——与 K3 容错策略对齐 |
| （附带）n-9/n-15/n-12/m-6/m-7 | ✅ db.py:55 connect_timeout=10；qdrant_store.py:60-64,118-120 异常收窄+未知 tier raise；t_chunk MEDIUMTEXT（init_db.py:46）；m-6 降级 HTML 去标签 `_html_to_markdown`（table_struct.py:277-295）落位复用 m-1 逻辑 |

## 与 runbook 一致性核对（逐项）

| 项 | 核对结果 |
|---|---|
| K1 三路+融合 | ✅ 模块内完整。每路 30（profile.per_route_top）、客户端 RRF k=2（weighted_rrf 按 Qdrant 官方公式 1/(k+rank/w)、DBSF z-score+std=0 贡献 0）、证据组并查集归并（(doc,page) 页组 + figure 跨页组，代表=最高分保原位、成员按融合序入 group_members）、池 50 截断；两条 R1 官方坑写进模块注释；BM25 后过滤+回表 to_thread。**⚠️ 编排层破坏管道序见 B-1** |
| K2 重排 | ✅ 解析链三级照抄 RankGPT 语义（清洗/去重/越界过滤+补尾）、自由文本无 JSON、temp=0、max_tokens 256（893b94c 实测调优）、失败降级回 RRF 序+degraded、t_rerank_cache 键=sha256(model+max_tokens+候选指纹+question)。**⚠️ 两处偏差：timeout 5s 与实测延迟矛盾（Major-1）；pro"级联"名不副实（Minor m-7）** |
| K3 路由 | ✅ 完整。zh 占比 ≥0.3（边界恰等有单测）、zh→0.0 整路旁路（连检索都不发起，routes 无键供 trace 区分）、0.5 降权位留 M5、语言入 trace、未知 lang 宁多召回 |
| K4 组装 | ⚠️ 部分对齐。Source N 编号/图文同 Source/图 ≤5 先到先得/E 档前缀 ✅；**"首尾优先"未实现**（ranking 原序装载，docstring 自declared 留 M5，runbook 未补记，m-8）；**image 先于 caption 时组不成对**（Major-2） |
| K5 生成 | ✅ 双字段分流（reasoning 只进 trace 统计，流式/非流式都只认 content）、usage 末 chunk、TTFT=正文首 token 口径、系统提示词固定前缀+语言跟随、不向 5.3 系发 thinking:disabled。⚠️ AsyncOpenAI 未 close（m-1） |
| K6 引用 | ✅ 完整。`[n]`/`[n,m]`/`[n][m]`/`[n-m]` 四类+中文逗号+en-dash、区间展开带 50 上限防炸、无效 n 整句降级落 trace 不删不重写、[n]→(doc,page,bbox) 映射、句切保护小数 |
| K7 兜底 | ✅ 完整。judge 失败/解析失败/None 全部放行（judge_ok 标记）、检索分数不进决策只落 trace、REFUSAL_TEXT 与 runbook §3.1 逐字一致、judge 提示词含表格文本化指引（7ca4673）。⚠️ prompt 第三道"无依据明确声明"条款缺失（m-3） |
| K8 CLI+trace | ✅ Profile dataclass 注册表（六档共享旋钮+档位覆写，防线单测锁语义）、`--smoke` Markdown 报告（嵌入 trace_id 可回放、人工列留空）、JSONL 子事件流落 data/traces/、入口 stdout reconfigure。⚠️ trace 字段与 §3.1 schema 有出入（m-4）；F 档 multimodal_rerank 空转（m-2）；--smoke 无逐题隔离（m-6） |
| K9 工程卫生 | ✅ requirements 全量钉版（qdrant-client 1.15.1 附 Py<3.12 事实依据）、AGENTS/.env.example 勘误（a43e320）、smoke_queries.json 版本化入库（20 题=6/5/5/4+中英对照 3 对）、cost.md M3 实测回填。⚠️ runbook K9 行文未同步（n-12） |
| §3.1 细则 | ⚠️ 大体对齐。重排候选格式 `[i] (doc_id,page,kind) heading / 前300词` ✅；judge 提示词 ✅；弃答话术逐字 ✅；trace schema 字段出入见 m-4；**管道序"输出 20→组装 20"被 B-1 破坏** |

## 问题清单

### Major（2 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| J-1 | rerank.py:269（`timeout: float = 5.0`）+ query_cli.py:119（调用未传参）+ reports/cost.md §5b | **重排超时预算与强制思考模型的实测延迟矛盾，D 档 30 候选场景疑似每次都走降级**。cost.md 实测"重排（D 档，flash，30 候选）11.2s"——与降级路径总时长 5s（超时）+1s（退避）+5s（重试）≈11s 高度吻合；对比成功样本"1 query+5 候选 2.70s"。若属实：D 档冒烟全程 ranking=RRF 输入序、`degraded=true`+`fail_reason=APITimeoutError` 已在 trace 里但**三轮冒烟报告与 cost.md 均未提"降级"**（grep 无命中），降级率入验收（K2）的口径失真；且与 B-1 叠加后"重排无效"被完全掩盖 | ① 先查容器 `data/traces/*.jsonl` 的 `rerank.degraded/fail_reason/latency_ms` 定案；② 若恒降级：timeout 提到 12–15s（或按 R8 级联缩输入至 15）二选一，重跑 D 档验证重排真实生效；③ cost.md §5b 补降级率字段（K2 验收项）；④ 顺带核对 max_tokens=256 下思考+输出是否触顶（thinking ~430 token + 输出 ~120 token，256 上限可能截断排序输出导致解析链吞尾） |
| J-2 | context.py:106-151（`_companion` + 认领逻辑） | **image 先于 caption 时"同 Source 交错"失效**：`_companion` 只在处理 caption 时向前找未被认领的 image（:109 `other in taken` 跳过），image 块先出现则自成 Source 并认领原图；随后 caption 到达时 companion=None → **同一图占两个 Source、caption 文本在两个 Source 里重复**，挤占 final_top=20 名额，[n] 引用可指到重复 Source。重排/融合序不保证 caption 在前（rerank 可任意输出），真实可触发；test_context.py 只测了 caption-先序，恰好漏掉该分支 | 处理 image 块时向后查找其 caption（top 内同 image_path 且 kind=caption）一并吸收（caption 文本并入该 Source、caption chunk_id 记入 taken），或 caption 到达时若 image 已被认领则跳过生成重复 Source（保留首个、文本去重）。补一条 image-先序单测 |

### Minor（8 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| m-1 | vlm.py:101、fallback.py:101 | `AsyncOpenAI(...)` 每次调用即建即用，**从不 close**（rerank.py:240-252 的同步 client 有 try/finally close，两处异步没有）。`--smoke` 20 题 × 2 client = 40 个未关闭的 httpx.AsyncClient 连接池挂在共用事件循环上，GC 前 socket 悬挂 + ResourceWarning；M4 服务化按请求复用该写法会稳定泄漏 | `try: ... finally: await client.close()`（AsyncOpenAI.close 为协程），或在 CLI/服务层持有一个进程级共享 client 注入 |
| m-2 | config.py:67-68 + query_cli.py（全文无 `multimodal_rerank` 读取） | **F 档 multimodal_rerank=True 是空转旗标**：`--profile F` 与 E 输出全等（无逐图打分、无 4-6 图列表式对比，R17 落地项零实现）。收官验收"六档全部跑通"对 F 的判定标准悬空——跑通了一个与 E 无差异的档位，消融阶梯 F-E 差值恒 0 | M3 收官前二选一：① 按 R17 最小实现逐图 0–2 分点式打分（rerank.py 已有缓存/降级骨架可复用）；② 显式声明 F 档 M3=占位（profile desc 或 --help 注明"P1 未接入"），并记 runbook——防止 M5 消融把 F 档数据当真 |
| m-3 | vlm.py:38-43（SYSTEM_PROMPT） | **K7 第三道防线"无依据明确声明"未进系统提示词**。fallback.py:7 与 citations.py:13 的 docstring 都引用"prompt '无依据明确声明' + self_check"，但 SYSTEM_PROMPT 只有"只依据 Source/每句引用/语言跟随"三要素——judge 放行但证据实际不足时，模型在"每句必须引用"压力下只会硬编一个 [n]（RGB 实证的引用幻觉路径） | SYSTEM_PROMPT 追加第四要素："若所给 Source 不含回答依据，直接声明依据不足，不得编造"——与 judge 双保险，改动一行 |
| m-4 | query_cli.py:195-232（trace 落盘）对照 runbook §3.1 schema | **trace 字段与 schema 有出入**：`fallback.judge_score` 缺（现为 judge_ok/judge_reason）；`rerank.input`（重排输入序，F4 归因需要）缺——fused 事件里有 pool 全序可部分代偿，但严格对不上；`llm.reasoning_tokens` 缺（vlm.py 只记 chars，未读 usage.completion_tokens_details.reasoning_tokens）；`llm.content/tokens` 被改名为 `answer/usage_tokens`（消费方按 schema 解析会 miss）；judge 自身耗时未记（timings 只有 retrieve/rerank/generate） | 按 schema 补齐字段名或反向修订 runbook §3.1（二选一，收官前定稿）：加 `judge_score`（=sufficient bool）、`rerank.input=inp 序`、`reasoning_tokens`（读 usage 明细）、judge_ms；M4/M5 的归因脚本以修订后的 schema 为准 |
| m-5 | query_cli.py:140-149、164-168；hybrid.py:438-439 | **事件循环同步阻塞三处（m-9 纪律漏网）**：① E 档 t_ctx_prefix 查询直连 PyMySQL 未包 to_thread（同函数里 `_fetch_members` 却包了，自相矛盾）；② `_load_image_blob` 的 `p.read_bytes()`（图 ≤5、每个数百 KB）在循环上直读；③ BM25 `load_index()`（pickle 反序列化）+`idx.search()`（O(N) 打分）同步直调——模块 docstring 只豁免了 qdrant（"毫秒级直调"），BM25 未声明 | ①② 按既有纪律包 `asyncio.to_thread`（① 顺手抽成 `_fetch_ctx_prefixes` 辅助函数）；③ load/search 包 to_thread 或在 docstring 补豁免依据（索引 ~MB 级、实测毫秒），三处口径统一 |
| m-6 | query_cli.py:276-287（`_run_smoke`） | **--smoke 无逐题失败隔离**：任一题抛错（生成超时 120s/网络抖动/API 5xx 都会从 `answer_question` 穿透）→ `run_until_complete` 上抛 → finally 关循环 → **已跑完的 N 题结果全部丢弃，报告文件根本不落盘**。20 题 × 多次 LLM 调用跑批，一次瞬时故障毁掉整轮验收；与 m-11"单块失败不拖垮全批"的项目精神相悖 | 逐题 `try/except Exception`：失败题在报告行写 `ERROR: {类型}`、trace 照记、继续下一题；汇总区加"异常题数"。收敛后单题仍可 `--question` 复跑 |
| m-7 | query_cli.py:116-118 + rerank.py:348-352 | **pro"级联"名不副实（K2/R8 偏差）**：K2 定义"pro 档级联=只重排 flash 已排 top-10/15 控预算"；实现是 tier=pro 时对**融合池 top-30**（cascade_input 传入的是 RRF 序 cand_map.values()，flash 根本没跑）直接重排——cascade_input docstring 说"取 flash 已排序列表前 top 个"，与调用不符；预算也未控（30 候选进 pro 比级联贵一倍） | 按 K2 实现：先 flash 重排 30 → `cascade_input(flash_out, top=15)` → pro 重排前 15 → 拼接 flash 15 之后序；或改名 `--rerank-pro` 为"pro 直排 top-30 对比位"并把 runbook/cascade_input docstring 对齐，不留两套口径 |
| m-8 | context.py:17-20、97-156 对照 runbook K4/§3.1 | **K4"首尾优先"未实现**：runbook §3.1 写"组装（top-20 内首尾优先+图 ≤5）"，实现为 ranking 原序装载——docstring 自declared"精排版留 M5 消融"，属未报备的方案简化（与 m-2 同类：验收口径需要明示） | runbook §3.1 补记一行"M3 实装=ranking 原序，首尾优先装载留 M5 消融位（context.py docstring 已声明）"；或直接实现（奇偶填头尾，改动限于展示序循环） |

### Nit（12 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| n-1 | query_cli.py:103-104 | `members_map` 构造后无任何引用（死代码，重排分支元数据实际走 `_fetch_members`） | 删除；`ranking` 死变量随 B-1 一并清理 |
| n-2 | rerank.py:54 对照 hybrid.py:79 | `Candidate.page: int` 标注与 Hit.page 的 `int \| None` 不符，query_cli 直接透传（image/caption 回表 page 理论可为 NULL） | 标注改 `int \| None`（build_prompt 已用 f-string 容忍 None） |
| n-3 | query_cli.py:143-146 | `final_ranking` 为空时 `ph or "%s"` 与 `(*final_ranking, model)` 参数数不匹配（2 占位符 1 参数）→ ProgrammingError。仅在空库/空池退化场景触发 | 空列表直接跳过查询（ctx_prefixes={}） |
| n-4 | query_cli.py:116 | `--rerank-pro` 对无重排档（A/B/C）静默忽略，用户无感知 | argparse 校验组合并报错，或 help 注明"仅 D+ 档生效" |
| n-5 | tests/test_trace.py:41-47 | `query_id` 含秒级时间戳，`a == b` 断言跨秒边界（极慢 CI）会 flake | 注入时间参数或 monkeypatch datetime，消除真实时钟依赖 |
| n-6 | hybrid.py:417-419 | 全路关闭的退化 profile 下 `qvec is None` 仍会先调嵌入（浪费一次 API）——正常档无影响 | 把嵌入调用移进"至少一路开启"分支 |
| n-7 | trace.py:47-52 对照 runbook §3.1"一行一查询" | 实现为"一行一子事件"（meta/routes/fused/… 分行）——设计合理（崩溃安全，docstring 已论证）但与 runbook 字面口径不一致 | runbook §3.1 补记"M3 实装=主事件+子事件流，query_id 串联"（trace.py docstring 已自述） |
| n-8 | hybrid.py:25-27、425 | 档位映射 `text_kinds=={"text"}→A 否则→B` 是隐式约束：未来出现 ("text","table") 之类集合时 Qdrant 过滤=B（含 caption）而 BM25 后过滤=该集合，两后端口径漂移——恰是 R4 要防的 | 未知集合直接 raise（或断言 text_kinds ∈ {("text",), ("text","table","caption"), None}），注释已自认约束但未设防 |
| n-9 | rerank.py:206 | `_cache_get` 的 `json.loads(row[2])` 无容错：缓存行 JSON 损坏（手工改库/半写）会异常穿透炸掉整次查询而非降级 | try/except ValueError → 返回 None（当未命中，重排重跑） |
| n-10 | trace.py:41-43 | `import hashlib` 在函数体内（模块顶部未 import） | 移到模块顶部，与全仓风格一致 |
| n-11 | context.py:174-177 | `to_prompt_parts` 把图片 part 统一追加在全部文本之后，image part 不携带"所属 Source N"标注——图文配对只靠隐式顺序，VLM 引用图证据时缺锚点 | 每个 image part 前插一行文本 `（附图：Source N 原图）`，或按 Source 交错拼接 parts |
| n-12 | m3-runbook.md:48（K9） | runbook 仍写"qdrant-client 钉 ~=1.15.4；移除 httpx2"，事实已两度修正（1.15.1，bbbb911；httpx2 恢复，78c1c12——openai 3.48 真实依赖） | 收官补记 K9 事实修正，防后续按 runbook 复原错误版本 |

## 测试审查

**总况**：9 个 M3 测试文件、**96 用例**（hybrid 25 / rerank 21 / citations 12 / fallback 11 / router 10 / context 7 / vlm 4 / trace 4 / config_profiles 2），全仓 **169 passed**（8.10s，本机实跑）。隔离纪律严格执行：Qdrant/BM25/嵌入/DB/LLM 全部注入桩或 monkeypatch，`_BoomEmbed`/`_BoomMeta` 哨兵类反证"不该走的路径没走"，无真库真 API 依赖。

| 文件 | 用例 | 断言质量 | plan 用例覆盖 |
|---|---|---|---|
| test_hybrid.py | 25 | **强**：RRF/weighted/DBSF 手算期望值逐分核对（approx）、k/权重敏感性、并查集归并五态（同页/跨页传递/组隔离/代表非首见/未知元数据不合并）、A/B kind 过滤下发、BM25 旁路与 0.5 降权、回表 SQL 参数化断言（占位符数==参数数）、自建 client close/注入不 close | ✅ K1 全覆盖，R4 防线（两后端 kind⊆映射）实测成立 |
| test_rerank.py | 21 | **强**：解析链四类+前缀+全废+负号、缓存键 7 维敏感性（含候选序与 300 词截断口径）、缓存命中不调 LLM/未命中写库/`use_cache=False` 零 IO、降级三径（重试 1 次/不可重试不重试/解析全废）、缓存键期望值与签名同源（005df4f 防魔法数漂移） | ✅ K2/R7/R8/R10 达标；缺"重排成功→最终序消费"端到端断言（B-1 正好无人看守） |
| test_router.py | 10 | 强：三态+0.3 恰等边界+空串/纯标点+旁路/正常/未知 lang | ✅ K3 |
| test_citations.py | 12 | 强：四类格式+ALCE `[1,2]` 坑专项+区间/中文逗号+越界降级保句+小数不切句+映射双保险 | ✅ K6 |
| test_fallback.py | 11 | 强：judge 裸 JSON/围栏/坏 JSON/异常/非 bool 五态全放行向、force_refuse、self_check 四态、REFUSAL_TEXT 逐字锁定 | ✅ K7/R13 |
| test_context.py | 7 | 中强：编号连续/truncated、caption-先序交错、限额保文本、E 档前缀、JSON 列容错；**缺 image-先序用例（J-2 落点）** | ⚠️ K4 部分覆盖 |
| test_vlm.py | 4 | 中：流式分流（含"迟到的思考"乱序分片）+usage 末 chunk+TTFT 正文口径+调用参数断言+data URL/png/缺图跳过；非流式分支 covered | ✅ K5/R9 核心达标 |
| test_trace.py | 4 | 中：JSONL 落盘/未知类型不炸/query_id 分组；脱敏断言是**源码检查**（"settings" not in src）——偏弱但配合人工核对 payload 清单成立；query_id 有秒边界 flake（n-5） | ⚠️ K8 部分 |
| test_config_profiles.py | 2 | 强（防线性质）：A–F 阶梯增量逐档锁定+共享旋钮防漂移 | ✅ K8/PRD §7.1 |

**关键缺口**：`query_cli.answer_question` 编排逻辑**零测试**——组员展开/截断/补齐（B-1、J-2 的下游）连续三次 hotfix 全在此函数且全靠容器冒烟肉眼验证。建议随 B-1 修复把"窗口+组员展开+补齐"抽成纯函数（输入=pool Hits+ranking，输出=final_ranking），补 4 条单测：正常重排序、degraded 回退、代表带组员展开、窗口外补齐。

## 敏感代码判定

**是（敏感）**——与 runbook §8 一致：外部 API 调用面扩大（重排 LLM/judge/VLM/查询侧嵌入）+ 凭据（ARK_API_KEY、QDRANT_API_KEY、MYSQL_URL 密码）+ trace 落盘面。S3 视角补充确认（S4 前置核查）：

- **无硬编码密钥/路径**：模型名/URL 全走 settings（.env）；query_cli 路径由 `__file__` 派生；config.py 注释中的本机示例路径仅文档性质。
- **trace 脱敏** ✅：trace.py 不 import settings（test_trace 源码级断言 + 人工核对 query_cli 全部 payload——仅 question/answer/排名/分数/耗时/模型名，属 runbook §8 预期入库内容）；无 key/密码/.env 值落盘路径；data/traces/ 在 gitignore 内。
- **SQL 全参数化** ✅：hybrid/query_cli 的 IN 子句均为 `%s` 占位符拼接（值走参数），rerank/embeddings/bm25/contextual 缓存读写同款；init_db 纯 DDL 无值。
- **错误信息不含凭据** ✅：db.py 脱敏正则（m-12 修复后 fullmatch+`***` 占位）复用至今；rerank fail_reason 只含异常类名与消息（OpenAI SDK 消息不含 key）。
- **遗留关注（移交 S4）**：m-1 未关闭的 AsyncOpenAI（连接悬挂属资源卫生而非泄密）；`.env` 双端隔离照旧（S4-02 已取证）。

## 处理情况

- 本审查为 S3 只读审查，**未改动任何源码/测试**；产物即本报告。
- 全部结论按 HEAD = ecd3082 核对；169 用例本机实跑全绿；B-1 的"重构前后对比"以 `git show 1bf4229` 为证。
- **结论：修复 B-1（约 10 行 + 抽函数补测）并定案 J-1（查 trace 降级率）后，可进入 S4 安全复查与 M3 收官**。J-2/m-1~m-8 建议随 B-1 同批处理（均为小改动）；Nit 可随收官批量补记或入 backlog。
- 复测命令：`$env:PYTHONUTF8='1'; & "D:\soft\anaconda\envs\doclens\python.exe" -m pytest -q`（容器侧 doclens 环境同款）。
