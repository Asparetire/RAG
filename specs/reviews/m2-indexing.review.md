# 代码审查：m2-indexing（M2 索引里程碑）

> **审查者**：S3 通用代码审查（ai-dev-workflow，独立审查视角，只审不改）
> **日期**：2026-11-11 16:15（北京时间）
> **范围**：M2 新增/修改 21 个文件，约 2985 行——
> `doclens/parse/table_struct.py`、`doclens/parse/mineru_parser.py`、
> `doclens/index/{chunker,db,embeddings,qdrant_store,bm25,contextual}.py`、
> `scripts/{init_db,rebuild_docs,ingest,search_probe,quality_report}.py`、
> `tests/test_{table_struct,chunker,db,embeddings,qdrant_store,bm25,contextual,parser_mapping}.py`。
> **计划依据**：[specs/plans/m2-runbook.md](../plans/m2-runbook.md)（K1–K7 决策 + §3.1 实施细则，先读后核对）。
> **审查快照**：HEAD = f609378（S4 修复批，审查期间并行落地并已提交）+ 工作区残留 rebuild_docs.py sys.path 自举；全部文件按最终版本核对（mtime 快照确认无遗漏）；64 用例本机实跑全绿。

## 结论

**Blocker 0 ｜ Major 2 ｜ Minor 13 ｜ Nit 17**。整体质量良好：与 runbook K1–K7 及 §3.1 细则逐项对齐，已知三连修（外键顺序/信号量懒绑定/429 降并发）验证完整，无硬编码密钥/路径，无调试残留。两个 Major 均为错误路径/契约缺陷（MySQL 写入原子性、ctx 缓存跳过不比对 model），改动量小，建议在 2.8 容器增量幂等验收前顺手修复。

## 已知修复验证（任务清单第 5 项）

| 修复项 | 验证结果 |
|---|---|
| 外键顺序（t_doc 先写） | ✅ 完整。init_db.py:26-55 DDL 顺序 t_doc→t_chunk（FK 指向已建父表）；ingest.py:76-93 运行时先 upsert t_doc 再删插 t_chunk。**但原子性问题见 Major-1**（t_doc 已提交、t_chunk 失败 → 增量跳过） |
| 事件循环懒绑定 | ✅ 完整。embeddings.py:122-127 `_semaphore()` 每次取 `get_running_loop()` 比对 `_loop`，跨 `asyncio.run` 复用 client 安全（ingest.py:138 正是每篇一次 `asyncio.run` + 全程复用 client 的场景）。残留：依赖 asyncio 原语私有 `_loop` 属性（Nit-8） |
| 429 降并发 | ✅ 完整。embeddings.py:29-33 `CONCURRENCY=2`（注释注明实测 4 触发账号级 429）、`RETRIES=6` 指数退避 60s 封顶；重试 `asyncio.sleep` 在信号量**外**（占位不放大）。同类残留排查：contextual.py 的 LLM 调用**无任何重试**且批内一错全丢（Minor-11）；其余模块无外呼 |
| （追加）S4 修复批 f609378 | ✅ 审查期间落地并复核：S4-01 db.py:34-35 密码脱敏 + test_db.py:31-39 单测实跑通过；S4-03 ingest.py:42-47 `_image_file` 越界守卫 + 116-123 缺失跳过；S4-04 bm25.py:85-87 pickle 信任边界。同类残留：db.py 正则非锚定（Minor-12）、被跳过图像单元仍写 t_chunk（Nit-3） |

## 与 runbook 一致性核对（逐项）

| 项 | 核对结果 |
|---|---|
| K1 切块 | ✅ 核对通过。同 heading_path 相邻聚合、超 1600 句切（`.?!`+空白+句首字符，chunker.py:28）、单句硬切带空格回退（:54-68）、宁短勿跨节、跨节不合并、无 overlap；标题只作 `" / ".join` 前缀不计预算（:133-147，有单测）；References/Bibliography 过滤（:150）；页眉页脚=无归属+<300 字符+跨页重复 ≥2（:117-128，与 §3.1">1 次才删"一致，有单测）；表格 1 chunk、caption/image 双路（:161-170） |
| K2 表格 v2 | ✅ 核对通过。四步管线齐：html.parser 网格化+rowspan/colspan 复制补全（table_struct.py:92-116）、无效区域分级标记（空白/分隔丢弃、脚注/合计移尾部，:160-196）、清洗后判定列名拼接"一级/二级"+行名列（:201-239）、manifest 含 columns/row_labels/excluded+理由+去向；rebuild_docs.py 从缓存 raw JSON 重建 doc.json+manifest，不重跑 MinerU；markdown 降级路径与"(Continued)"续表均有真实夹具单测。缺陷见 Minor-5/6/7 |
| K3 嵌入 | ✅ 核对通过。单条请求（embeddings.py:142 `input:[item]`）、并发信号量（降 2 有实测依据，代码注释引 runbook 风险表第 1 条）、指数退避重试、文本/图像双 instruction（CORPUS_TEXT/IMAGE_INSTRUCTION）、图像 base64 单图单请求 |
| K4 缓存 | ✅ 核对通过。键 = sha256(model+instruction+dim+content) 四要素 + `\x00` 分隔防拼接歧义（:40-46，有单测验证逐字段敏感性）；MEDIUMBLOB float32 小端（vec_to_bytes/bytes_to_vec 往返有单测）；先查缓存再调 API；ON DUPLICATE 幂等。与 runbook 完全一致 |
| K5 Qdrant | ✅ 核对通过。两集合（doclens_text/doclens_image）、点 ID=uuid5(chunk_id)（:31-33，有确定性单测）、payload 字段与 §3.1 一致（text 不含正文/bbox → 回表）、A/B 档 kind 过滤（:25-28，"A"=["text"]、"B"=text+table+caption，有单测）、delete-by-filter 先删后插（:67-78）、分批 200 upsert |
| K6 BM25 | ✅ 核对通过。jieba.lcut+小写（:26-28）、pickle 分词语料+jsonl 元数据落 data/bm25/、重建式增量从 t_chunk 加载（:94-116）、image 单元不进索引（build_index 过滤，有单测）、空索引/空查询防御 |
| K7 E 档 | ✅ 核对通过。ctx_model=deepseek-v4-flash（config.py:50）、50–100 token 中文前缀提示词（temperature=0、max_tokens=200）、t_ctx_prefix 幂等 upsert、分层抽样按占比（有单测）。100 块试产已实测入 cost.md（269.7s/0 失败）。缺陷见 Major-2/Nit-10 |
| §3.1 数据链路 | ✅ 核对通过。t_chunk 覆盖全部四类单元、chunk_id=`{doc_id}:{序号:04d}`、content_hash 字段落库、两集合同 uuid5、Qdrant payload 不含正文/bbox、search_probe._lookup_contents 按 chunk_id 回表取正文（M3/M4 共用路径的先例已通） |
| §3.1 增量语义 | ✅ 核对通过。t_doc.doc_hash=doc.json 全文 sha256、未变整篇跳过（零 API 零写入）、变化 doc 按 doc_id 先删后插（Qdrant delete-by-filter + t_chunk 删行）、BM25 收尾全量重建、`--force` 忽略跳过（缓存仍生效）、收尾汇总输出 API 次数/缓存命中/两集合点数（2.8 验收证据齐备） |
| §3.1 实现注意 | ⚠️ 基本通过。PyMySQL 同步调用均经 `asyncio.to_thread`/executor 包裹（embeddings/contextual）；漏网一处：ingest.py:133 回退分支 `p.read_bytes()` 直接阻塞事件循环（Minor-9） |
| §6 测试策略 | ⚠️ 大体达标。每模块 ≥1 关键路径单测、缓存键/聚合/过滤/网格化均有真实夹具或强断言；缺口：合计行排除无直接断言、generate_prefixes 缓存语义零用例（详见"测试审查"节） |
| §4 变更清单 | ⚠️ 实际文件与清单基本一致；两处漏记：`scripts/rebuild_docs.py`（2.0 重建入口）不在 §4 表中；`scripts/probe_queries.json`（2.7 查询清单，§1/§5 有提及）——收官补记即可（Nit-17） |

## 问题清单

### Major（2 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| M-1 | ingest.py:76-93（`_write_chunks`） | **MySQL 写入无事务原子性**。db.connect() 固定 autocommit=True，三步（t_doc upsert → t_chunk DELETE → executemany INSERT）逐条即提交：若 INSERT 中途失败（content 超 TEXT 上限/连接断开/数据异常），t_doc 已带**新 doc_hash** 而 t_chunk 处于删空/半插状态 → 下次增量运行 hash 相同被**静默跳过**，该文档永久缺失于 BM25 与回表，且 Qdrant 可能残留旧点——直接击穿 2.8"增量幂等"验收的机制保障 | 用显式事务包裹三步：进入函数先 `conn.begin()`（PyMySQL 在 autocommit 下可手动开事务）或对该写入使用 autocommit=False 连接，三步完成后统一 `conn.commit()`；异常时 rollback，保持旧 doc_hash 与旧 chunk 行一致 |
| M-2 | contextual.py:54-68、96（`_prefix_get_existing` + `todo` 过滤） | **缓存跳过不比对 model，与自身 docstring 契约不符**。docstring（:89）承诺"已有缓存且 model 相同的块跳过"，但 SELECT 只查 chunk_id 不带 model 条件；t_ctx_prefix 主键是 chunk_id，换 ctx_model（如 M5 换模型）后旧前缀被永久复用且永不再生，E 档消融数据被静默污染（K4 嵌入缓存把 model 纳入键，此处却漏了——同图案的双重标准） | 查询改为 `SELECT chunk_id FROM t_ctx_prefix WHERE chunk_id IN (...) AND model=%s`，传入 `settings.ctx_model`；顺带把返回值口径改齐（当前只返回新生成条目，已缓存的不在返回 dict 里，docstring 说"返回 chunk_id→prefix"有歧义，Nit-10） |

### Minor（13 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| m-1 | mineru_parser.py:112-126 | `_table_to_markdown` 死代码：表格分支已改走 table_struct.transform_table，全仓无调用方（v1 线性化被 K2 取代） | 删除；其中"HTML 去标签"逻辑在 m-6 的降级路径还能复用，可移入 table_struct |
| m-2 | mineru_parser.py:173-185 | `build_doc` 连续两个字符串字面量：第一个是真 docstring，第二个是冗余表达式（M1 收官补写说明时的残留），`help()`/文档工具只认第一个 | 合并为一个 docstring |
| m-3 | mineru_parser.py:238-245 | 表格块 `transform_table` 返回空 text 时 `continue` 发生在 `collect.append` 之前 → 该表从 tables_manifest.json 完全消失，125 表全量人工审计存在盲区 | 判空前先 append manifest（空表自带 degraded 记录），或在此分支补一条 `{type:"dropped_empty"}` 清单项 |
| m-4 | chunker.py:29、150 | `_REFERENCE_RE = ^(references|bibliography|参考文献)\b` 不匹配编号型标题（"4. References"/"5 References"）——恰是 K1 要防的"引用条目污染 BM25"场景从编号标题漏进 | 正则放开可选编号前缀：`^\s*(?:\d+[.:：]?\s*)?(references|bibliography|参考文献)\b`；补一条编号标题单测 |
| m-5 | table_struct.py:216-226、279-293、379 | **表头行未按 drop_cols 过滤**：`_build_body` 表头分支输出全宽 `header_cols`，数据行却剔除 `drop_cols`，出现整列空白列时表头与数据行**列数错位**（markdown 语义错行）；:379 汇总行 tail 传 `drop_cols=set()` 同样与主体不对齐 | `_join_header` 后对 `header_cols` 按 `drop_cols` 同步过滤（保留列号对齐），汇总行 tail 也传实际 `drop_cols` |
| m-6 | table_struct.py:335-341 | 网格化失败降级时 `fallback = _flat_text(raw)`：对 HTML 源表（content 本身是 HTML 串）会把 `<table><tr>...` 原始标签整段塞进 chunk | 降级路径先判 source：html 源先去标签取纯文本（可复用 m-1 的线性化逻辑），markdown 源保持现状 |
| m-7 | table_struct.py:261-270 | `_flat_text` 列表分支用 `"".join` 连接分段，markdown 表各行走管道会**粘连成一行**。当前 11 篇 structured_content 的 content 均为 str（实测路径不触发），属防御分支缺陷 | 改 `"\n".join(...)` 并跳过空段 |
| m-8 | chunker.py:108、169 + ingest.py:110-123 | 无 caption **且**无 image_path 的 image 单元仍被 emit：t_chunk 有行（content 空串）、Qdrant 无点——M1 质检"空图"列全空（现网 329 图全有 image_path），但 ingest 对缺失文件只跳过嵌入不删行，§1 验收口径"Qdrant 点数与 chunk 统计一致"在该边角被打破 | chunker emit 前对 `kind=="image" and not content and not image_path` 直接 return；或 ingest 跳过时同步从 `_chunk_rows` 剔除并对账打印 |
| m-9 | ingest.py:133 | 降采样走了 `asyncio.to_thread`，回退分支 `p.read_bytes()` 却直接在事件循环上阻塞读（§3.1"避免阻塞事件循环"自家纪律的漏网；329 图 × 每次数百 KB） | `small = ...; blobs.append(small if small is not None else await asyncio.to_thread(p.read_bytes))` |
| m-10 | embeddings.py:169-180 | 批内任一请求最终失败：`return_exceptions=True` 收集后在循环里 raise，**已成功兄弟请求的向量不落缓存**——429 长退避场景下整批重跑重付费 | raise 前先把成功 rows `await asyncio.to_thread(_cache_put_many, rows_ok)` |
| m-11 | contextual.py:106（`generate_prefixes`） | `asyncio.gather` 无 `return_exceptions=True` 且 `_gen_one` 无重试：一条 LLM 调用失败 → 整批前缀全丢（cost.md 实测 269.7s/100 块，M5 全量约 70 分钟，一次瞬时 429 就全白跑）；与 embeddings 模块的容错策略不一致 | 逐条 try/except 收集失败清单（跳过不落库、日志汇总），加至少一次指数退避重试（对齐 K3 策略） |
| m-12 | db.py:17-19、32 | `_URL_RE.match` 非锚定：尾随垃圾被静默接受，且 db 名在首个非 `\w` 字符处截断（`.../doclens-bad` → database="doclens"，**静默连错库**；query 参数同理被吞） | 改 `re.fullmatch`（或 pattern 尾加 `\Z`），docstring 注明不支持 query 参数；补 1 条"库名带连字符应报错"单测 |
| m-13 | test_table_struct.py:138 | 断言空转/取错段：`assert "| --- |" not in content.split("\n\n")[1] if "\n\n" in content else True`——content 无 `\n\n` 时恒 True；有 `\n\n` 时 `[1]` 是 tail 而非 body，检查对象错误，伪代码表"无表头即无分隔行"的真实意图未被验证 | 改为直接 `assert "| --- |" not in content` |

### Nit（17 条）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| n-1 | ingest.py:6 | 模块 docstring 流程写"t_chunk 先删后插 → t_doc upsert"，实际实现是 t_doc 先写（外键要求，107c690 修复后未同步注释） | 更正 docstring |
| n-2 | ingest.py:97 | `process_doc` docstring 返回键 `{..., n_units, ...}` 过时，实际键为 n_text/n_img/downsampled/written | 更新 |
| n-3 | ingest.py:110-123 | 被跳过的图像单元（越界/文件缺失）仍进入 `_chunk_rows` 写库，仅打印警告 | 跳过时同步从 chunks 剔除，或汇总处给出 t_chunk/Qdrant 对账差值说明 |
| n-4 | embeddings.py:29-33 | CONCURRENCY=2 偏离 runbook K3"并发 4"，依据只在代码注释 | 收官时 runbook 风险表/§2 补记一行 |
| n-5 | embeddings.py:166 | `api_calls` 统计口径为"发起数"（含失败重试的每轮），2.8 汇总口径宜注明 | 注释注明口径或改为成功数+失败数两键 |
| n-6 | embeddings.py:181 | `cached.get(k) or fetched[k]` 以真值判断兜底，向量恰为空列表时会 KeyError | 改 `cached[k] if k in cached else fetched[k]` |
| n-7 | embeddings.py:205 | data URL MIME 硬编码 `image/jpeg`，非 JPEG 输入 MIME 失真（现语料全 .jpg，暂无实害） | 按扩展名/魔数选择，或统一转 JPEG 后嵌入 |
| n-8 | embeddings.py:125 | 懒绑定依赖 asyncio 原语私有属性 `_loop`（3.10+ 行为可用，属私有 API） | 显式存 `self._sem_loop` 记录归属循环 |
| n-9 | db.py:46-52 | `connect()` 未设 connect_timeout，库不可达时线程挂 OS 级超时 | 加 `connect_timeout=10`（可被 overrides 覆盖） |
| n-10 | contextual.py:87-110 | 模块无 CLI 入口，100 块试产经临时路径执行（cost.md 有实测记录但不可复现）；返回值口径见 M-2 | 补 `scripts/ctx_trial.py`（或 REPL 片段入 specs），并修 docstring |
| n-11 | bm25.py:23 | META_JSONL 注释声称含 `page` 字段，ingest.py:183 实际只传 chunk_id/doc_id/kind | 注释对齐实际字段 |
| n-12 | init_db.py:44 | `t_chunk.content TEXT`（64KB）对表格卡片+markdown 偏紧（实测 max≈7KB，余量 8 倍），与 M-1 叠加会触发半写 | 换 MEDIUMTEXT，或注释写明上限护栏与超限处理 |
| n-13 | search_probe.py:21 | probe_queries.json 实际在 `scripts/`，runbook §1 写 `data/`（docstring 已自述偏差待补记） | 收官补记 runbook |
| n-14 | quality_report.py:153-207 | `_table_audit` 输出路径固定 REPORTS_DIR（不受 `--out` 控制）、未 mkdir；审计报告只有列名/行名/排除项，缺 chunk 正文预览列，人工过目需另开 doc.json | 支持 `--out`；每表附卡片首行预览 |
| n-15 | qdrant_store.py:57-60、111-119 | `create_payload_index` 裸 `except Exception: pass`（连接错误也会被吞）；`search_tier` 未知 tier 静默等价 B 档 | except 收窄为 qdrant_client 异常并记日志；未知 tier raise ValueError |
| n-16 | test_parser_mapping.py:89-91 | 文件中部 `import re as _re` 与模块级 `_CAPTION_OK` 定义（E402） | 移到文件顶部 |
| n-17 | specs/plans/m2-runbook.md §4 | 变更清单漏记 `scripts/rebuild_docs.py`（2.0 重建入口，实际新增并已提交）；`scripts/probe_queries.json` 同 | 收官补记（chunker.py 的补记说明已在 §4 自注） |

## 测试审查（任务清单第 4 项）

**总况**：8 个测试文件、**64 用例全绿**（本机 doclens 环境 16:12 实跑，含 S4-01 新单测；`python -m pytest -q` → 64 passed in 3.65s）。

| 文件 | 断言质量 | plan 用例覆盖 |
|---|---|---|
| test_chunker.py | 强：精确内容比对（前缀拼接/不占预算）、硬切上限、跨节断组、页眉页脚三态、幂等重跑全等 | ✅ K1 全覆盖；缺编号 References 用例（对应 m-4） |
| test_table_struct.py | 强：真实难表夹具（两级表头拼接逐列断言、markdown 降级、伪代码表、续表、form 表、降级防御） | ⚠️ 缺**合计行（Average/Total）排除**与分组带的直接断言——runbook §6 点名"Average 合计行"夹具，目前只有 raw footnotes 路径被测（`_TOTAL_RE` 分支零覆盖）；另有 m-13 空转断言 |
| test_db.py | 强：含 S4-01 脱敏断言（secret 不入消息 + `***` 占位） | ✅ |
| test_embeddings.py | 中：缓存键四要素敏感性、向量往返、双格式解析扎实；`_embed_batch` 编排（顺序保证/缓存命中统计/失败不落缓存）无用例——后两者恰与 m-10 相关 | ✅ plan §6 所列"缓存键"达标 |
| test_qdrant_store.py | 薄（2 用例：uuid5 确定性 + TIER_KINDS 映射）但符合 §6"集成走容器真实调用"约定，点数幂等留给 2.8 | ✅（按约定） |
| test_bm25.py | 强：中英混合命中、落盘往返（monkeypatch 路径干净）、重建式增量语义、空防御 | ✅ |
| test_contextual.py | 中：抽样三态（占比/全取/剔除 image+空）与提示词装配扎实；**`generate_prefixes` 缓存跳过语义零用例**——Major-2 正落在无人看管处 | ⚠️ |
| test_parser_mapping.py | 强：真实样例夹具、v2 表格映射（collect/manifest 断言）、缓存命中不调 MinerU（monkeypatch 抛错守卫）、就近图注绑定 | ✅ |

## 敏感代码判定

**是（敏感）**——与 runbook §8 一致：外部 API（方舟嵌入/LLM）+ 凭据（ARK_API_KEY、MYSQL_URL 密码）。S4 安全专项复查**已随实施并行完成**（f609378：S4-01 密码脱敏、S4-02 边界取证、S4-03 路径越界守卫、S4-04 pickle 纪律），本审查复核其修复完整性如上表。S3 视角补充确认：无硬编码密钥/路径（.env 双端隔离、`.env`/`data/` gitignore 实测生效：`git check-ignore` 命中）；错误信息不含凭据（m-12 修复后 db.py 报错走脱敏分支）；SQL 全部参数化（bm25/search_probe/embeddings/contextual 的 IN 占位拼接均为 `%s` 占位符，无注入面）。

## 处理情况

- 本审查为 S3 只读审查，**未改动任何源码/测试**；产物即本报告。
- 审查期间实施线并行落地了 S4 修复批（f609378）与 2.7 三连修（107c690），所有结论均按最终版本（mtime 快照 + HEAD f609378 + 工作区 rebuild_docs.py 自举补丁）核对；64 用例在最终版本上实跑全绿。
- **Blocker 0**：无需阻塞收尾。建议：M-1 在 2.8 增量幂等验收前修复（改动 3 行级）；M-2 在 M5 复用 t_ctx_prefix 前修复（改动 2 行级）；Minor/Nit 可随收官批量处理或开 backlog。
- 复测命令（双端）：`python -m pytest -q`（本机 doclens env / 容器 doclens 环境）。
