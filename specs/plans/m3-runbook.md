# M3 检索+生成 Runbook

> **状态：待确认（停在确认门 G1）** ｜ slug：`m3-retrieval-generation` ｜ 依据：[主计划 §5 M3](doclens-multimodal-rag.plan.md)、[PRD FR-3/FR-4/NFR](../prds/doclens-multimodal-rag.prd.md)、[m2-runbook](m2-runbook.md)（M2 产物即 M3 原料）、[m3 调研笔记](../research/m3-retrieval-generation-survey.md)（R1–R19，工程实践级）、[检索方法调研](../research/eval-and-retrieval-survey.md)（方法级已定约束）
> **体检输入（2026-11-11 本机环境体检，6/6 全通）**：① Windows GBK 编码坑（✅❌ 打印崩溃，PYTHONUTF8=1 已验证）；② qdrant-client 1.20.0 vs 服务器 1.15.4 版本偏移；③ glm-5.3-flash 强制思考、reasoning_content 泄漏活证据；④ .env 双端漂移实锤（QDRANT_API_KEY 已同步修复）；⑤ httpx2 冗余包——全部并入 §2/§3/§5
> **用户决策（待 G1 确认）**：实现方式默认延续普通实现（M2 决策④同款）

---

## 1. 目标与验收标准（可执行验证）

| 验收项 | 验收方式 | 通过标准 |
|---|---|---|
| S3 清障批 | `python -m pytest -q` + review 复核记录 | 全绿（65 存量 + 新增用例）；[m2 review](../reviews/m2-indexing.review.md) Minor 13 条全修并有复核记录 |
| 工程卫生 | requirements 锁定文件 + `pip-audit` + 勘误文件 diff | 锁定入库；qdrant-client 钉 `~=1.15.4`；httpx2 移除；AGENTS/.env.example 勘误完成 |
| 六档开关 | `query_cli.py --profile A..F` 各跑 1 题 | 六档全部跑通；A 档结果不含 caption/image 命中（kind 过滤生效）；D 档重排生效（融合序 ≠ 最终序） |
| 20 冒烟题 | `--smoke` 产 Markdown 报告 + 人工填"通过/失败"列 | 通过率 ≥80%（≥16/20）；不可回答题拒绝 ≥3/4；可回答题误拒 ≤1（R13 口径：先压误拒） |
| 跨语言通路 | 冒烟题含中英对照 3 对 | 中文查询能命中英文语料并输出 [n] 引用（M3 只验通路；recall 差距 ≤5pp 的全量验收在 M5 FR-3.4） |
| trace 落盘 | 抽 1 条 `data/traces/*.jsonl` 人工核对 | 字段齐：各路命中(chunk_id+分数+排名)、融合/重排前后序、最终上下文、reasoning/content 分列、分段耗时+token（F0–F6 归因够用） |
| 性能实测 | `reports/cost.md` 回填 | 检索 P95（目标 <2s）与**正文**首 token（思考后，目标 <5s）实测记录；超限不阻塞但须记录并触发 NFR 修订提案（调研 R9 口径校准） |
| 里程碑 | commit（每步一个）+ `git tag m3` + push | 双端同步 |

## 2. 现状调查（2026-11-11 实测）

| 项 | 现状 | 结论 |
|---|---|---|
| M2 产物 | 1513 单元入库（text 857/caption 202/table 125/image 329）；Qdrant `doclens_text` 1184 点 + `doclens_image` 329 点；BM25 pickle；`t_chunk` 单一事实源；E 档前缀 100 块试产（全量留 M5） | 原料齐备，直接开工 |
| 检索通路先例 | `search_probe.py` 已通 uuid5 点查 + t_chunk 回表取正文（M3/M4 共用路径）；`bm25.py` 查询已有；`qdrant_store.search_tier` 支持 kind 过滤 | 三路召回全部有既有构件，hybrid.py 是"编排层"非"重写层" |
| 模型 | GEN=glm-5.3-flash（**强制思考不可关**，官方文档+冒烟实测双证）；RERANK flash/pro 双档在 .env；ctx=deepseek-v4-flash（judge 默认同款） | K2/K5 按"必有 reasoning_content"设计 |
| 拓扑 | 容器内直连=默认（M2 既定）；**本机隧道场景 2026-11-11 体检 6/6 全通**（13306→MySQL、16333→Qdrant，SSH 8009 免密） | 双场景写入 §9 执行命令；AGENTS"Windows .env 写 10.14.50.123"勘误入 0.2 |
| 依赖 | qdrant server 1.15.4 vs 本机 client 1.20.0（告警级偏移）；httpx2 冗余；requirements 未锁定 | 0.2 钉版+清理+pip-audit |
| git 双端 | 本机 `scripts/rebuild_docs.py` 自举补丁未提交；容器侧同款未提交改动（GitHub 不通期 scp 同步遗留，M2 遗留③） | 0.0 对齐，先于一切 |
| 冒烟题集 | 不存在（M2 的 probe_queries.json 只有 10 条检索抽查题） | 0.2 出 20 题（含不可回答 4 道、中英对照 3 对），版本化 `scripts/smoke_queries.json` |
| 125 表人工审计 | 待用户过目 `reports/table_audit_m2.md` | 不阻塞 M3 |

## 3. 技术方案（关键决策，R# = 调研笔记修订号）

| # | 决策 | 方案 | 被否方案与理由 |
|---|---|---|---|
| K0 | **S3 清障批（M3 首项）** | 0.1 一次修完 [m2 review](../reviews/m2-indexing.review.md) **Minor 13 条**（m-1 死代码 / m-2 docstring / m-3 manifest 盲区 / m-4 编号型 References / m-5 表头 drop_cols 列错位 / m-6 降级 HTML 未去标签 / m-7 粘连 / m-8 空 image 单元 / m-9 事件循环阻塞 / m-10 批内失败不落缓存 / m-11 contextual 单块失败全批丢 / m-12 URL 正则非锚定 / m-13 空转断言）+ 指定 Nit（n-9 connect_timeout、n-15 异常收窄、n-1/n-2/n-4/n-5/n-6/n-11/n-13/n-17 补记类）；其余 Nit 记 backlog | 分散拖到 M5：Minor 里 m-4/m-5 直接影响检索质量与消融口径，m-10/m-11 影响重跑成本，先清后建 |
| K1 | **hybrid.py 三路召回+融合**（R1/R2/R3/R4/R19） | 三路各取 **30**（调参位 20–50）→ **客户端 RRF**（k=2 默认=Qdrant 服务端同款，k=60 留对照位）→ **证据组去重**（RRF 后、重排前：按 (doc_id,page)+figure 组归并，组内最优名次做代表、组成员保留供引用）→ 融合池 top-50 交重排。**融合器=可插拔纯函数**（rrf / weighted_rrf / dbsf 三实现，M5 加消融档零改动）。**TIER_KINDS 单源映射**：Qdrant filter 与 BM25 侧同源生成，防线单测断言两后端 kind ⊆ 映射。BM25 kind 过滤=`get_batch_scores` 子集打分（1513 块 O(N) 免多份索引）。**tokenize 单例**（jieba cut+lower）索引/查询两侧共用+配对拍单测。模块注释写明两条官方坑：Qdrant prefetch limit≥主查询 limit+offset、融合分无相似度语义 | 服务端 RRF：仅限单集合，三路异构不适用【调研 S1】；分数归一加权作主线：BM25 无上界+图像路跨模态分数区分度未验证，先天吃亏（凸组合/DBSF 留 M5 消融） |
| K2 | **rerank.py LLM 列表式重排**（R7/R8/R9/R10） | 输入=融合池 top-50 **截 30**；每候选截 300 词等价量（表格卡片实测微调）；单次调用输出 top-20（D6 骨架保持）；temperature=0；**三级解析链照抄 RankGPT**（非数字清洗→去重→越界过滤+缺失按原序补尾）+四类单测（空串/重复/越界/夹带文字）；自由文本 `[1] > [2]` 不用 JSON 模式。**flash 档按"强制思考不可关"设计**：解析只认 content、max_tokens 从紧 512 起步实测调；**pro 档级联**（只重排 flash top-10/15 控预算）；**失败降级**=超时 5s+1 次重试→回 RRF 序+degraded 标记入 trace，降级率入验收；**结果缓存 `t_rerank_cache`**（键=sha256(query+候选指纹+model+params)） | 50 候选直进单次调用：超长+中段被忽略（RankGPT 窗口 20 的立论）；JSON 模式：格式约束损害推理【20】；pro 档全量重排：延迟预算爆 |
| K3 | **router.py 语言路由**（D11+R14） | 中文字符占比 ≥0.3 判 zh（纯函数）；zh→**BM25 旁路**（降权 0.5 档留 M5 FR-3.4 调参）；语言字段入 trace；不加查询翻译 | 查询翻译：研究证实劣于多语言嵌入（eval 调研已核） |
| K4 | **context.py 上下文组装**（R12+D12） | 重排 top-20 内组装、首尾优先；每块开头 **Source N:** 编号；**图文按 Source 交错**、图片紧跟其 caption 且同编号；选图=融合分 top5+与已选文本块去重（同区域优先原图、caption 文本保留）；分辨率原图直送；top-12 对照档作参数位（M5） | 图片堆尾：LlamaIndex 多模态引用先例是同 Source 交错【26】；学 512 字符重切引用粒度：本项目块 800–1600 已够细 |
| K5 | **vlm.py 生成**（R9/R14） | glm-5.3-flash；**双字段分流**：reasoning_content 只落 trace（思考 token 数/耗时），绝不进答案；usage 取末 chunk；TTFT/思考耗时埋点；系统提示词固定前缀吃上下文缓存；system prompt 明确"用与问题相同语言作答，专有名词/术语可保留英文"；M3 非流式为主，流式接口预留 M4（SSE 只透传 content） | 向 5.3 系发 thinking:disabled：官方明示无效【21】；把思考当答案兜底（冒烟脚本现状）：实测已泄漏思考文本 |
| K6 | **citations.py 引用**（R11） | 正则兼容 `[n]`/`[n,m]`/`[n][m]`/`[n-m]`（ALCE 原版漏 [1,2] 的坑避开）；**无效 n=所在句降级标记落 trace（不静默删、不重写答案）**；[n]→(doc,page,bbox) 经 t_chunk 回表（复用 search_probe._lookup_contents 路径）；流式下引用清单=stop 后对完整文本一次解析（M4） | 静默删无效引用：掩盖引用幻觉，评测失真；NLI 逐句核对：留 M5 增强（每句一次模型调用太贵） |
| K7 | **fallback.py 无依据兜底**（R6/R13） | 双信号：① judge 上下文充分性判定（默认 ctx_model，可配；Sufficient Context 先例 93% 准确）+② 检索观测（log-only，**不设全局分数阈值**——分数不可跨查询比较）；调参纪律=20 冒烟题**先压误拒 ≤1/16 再提拒答**（拒答/误拒矩阵入报告）；prompt"无依据明确声明"保留为第三道，不作主机制；弃答输出=固定话术+空引用+trace 标记 | prompt 单兜底：RGB 实证负例拒绝最弱；全局分数阈值：dense/BM25/融合分均不可比【1】【2】 |
| K8 | **query_cli.py + trace.py**（R15/R16/R19） | profile=**dataclass registry**（config.py：六档共享字段+档位覆写，含召回旋钮：路线开关/每路 top-k/路权重/融合器选择）；`--smoke` 产 Markdown 报告（题目\|答案\|[n] 引用\|各路 top 命中\|是否弃答+表尾人工"通过/失败"列），每行嵌 trace_id 可回放；trace=主事件+子事件 **JSONL** 落 `data/traces/`（gitignore），schema 见 §3.1；**Windows 入口 `sys.stdout.reconfigure(encoding="utf-8")`**（体检①，双端免环境变量，conftest.py 同款） | Langfuse/promptfoo 引入：JS 栈重，M5 备选【35】【36】；配置散落 env 判断：消融口径漂移温床 |
| K9 | **工程卫生**（体检②④⑤） | requirements 全量钉版（**qdrant-client 钉 `~=1.15.4`** 对齐服务器；移除 httpx2）+ `pip-audit`；AGENTS 拓扑行勘误（Windows 场景=SSH 隧道 127.0.0.1:13306/16333 或 VS Code 端口面板）+ .env.example 同步注释；`search_probe.py` 保留作 M5 对照工具（抽查职责被 hybrid 取代但文件不删） | 升级服务器 Qdrant：另行提案，不搭车；放任版本偏移：client/server 行为差异是隐性消融变量 |

### 3.1 实施细则

- **召回量与管道序**：每路 top-30 → RRF 融合 → 证据组归并 → 融合池 top-50（D6 骨架）→ 重排输入截 30 → 输出 top-20 → 组装（top-20 内首尾优先+图 ≤5）。
- **证据组归并**：key=(doc_id, page)；figure 组=caption 块 payload.image_path ↔ image 点关联（M2 payload 已具备）；组代表=组内最高融合分；组成员 chunk_id 列表入 trace 与上下文（引用可指组内任一成员）。"不去重只靠重排"留 M5 消融档。
- **重排候选文本格式**：`[i] (doc_id,page,kind) heading_path / 正文前 300 词`；提示词沿用 RankGPT 措辞"只输出编号序列，形如 [2,1,...]，不要解释"。
- **trace JSONL schema**（一行一查询）：
  `{query_id, ts, profile, question, lang, routes:{dense_text|dense_image|bm25:[{chunk_id,score,rank}]}, fused:[...], fused_dedup:[...], rerank:{input, output, degraded, latency_ms, usage}, context:[{chunk_id, source_n, kind}], llm:{reasoning_chars, reasoning_tokens, content, tokens, ttft_ms, total_ms}, fallback:{judge_score, refused, reason}}`
- **弃答话术**：「根据现有文档库，未能找到足以回答该问题的依据。」
- **20 冒烟题构成**：可回答 16（纯文本 6 / 图表 5 / 表格 5，其中中英对照 3 对）+ 不可回答 4；VLM 辅助出题+人工审核，版本化 `scripts/smoke_queries.json`（probe_queries.json 先例：验收资产入库不入 data/）。
- **judge 提示词**：判定"所给上下文是否足以回答问题"输出 sufficient/insufficient+理由一句（落 trace）；阈值即 sufficient 判定本身，从松到紧迭代靠提示词措辞与判定模型档位。

## 4. 变更清单（文件级）

| 动作 | 文件 | 职责 |
|---|---|---|
| 修改 | `doclens/parse/mineru_parser.py`、`doclens/parse/table_struct.py`、`doclens/index/chunker.py`、`doclens/index/embeddings.py`、`doclens/index/contextual.py`、`doclens/index/qdrant_store.py`、`doclens/db.py`、`scripts/ingest.py` | S3 清障批（K0 明细见 §3 K0） |
| 修改 | `doclens/index/bm25.py` | tokenize 单例暴露共用（K1） |
| 修改 | `doclens/config.py` | TIER_KINDS、profile dataclass registry（含召回旋钮）、t_rerank_cache 常量（K1/K8） |
| 修改 | `scripts/init_db.py` | 幂等新增 `t_rerank_cache`（第 6 张表） |
| 新增 | `doclens/retrieve/`（hybrid.py、rerank.py、router.py）、`doclens/generate/`（context.py、vlm.py、citations.py、fallback.py） | 主计划 3.1–3.4 |
| 新增 | `doclens/trace.py` | JSONL trace writer（K8；主计划未列，收官补记） |
| 新增 | `scripts/query_cli.py`、`scripts/smoke_queries.json` | 主计划 3.5 + 冒烟题集 |
| 新增 | `tests/test_hybrid.py`、`test_rerank.py`、`test_router.py`、`test_citations.py`、`test_fallback.py`、`test_context.py` 等 | §6 用例 |
| 修改 | `requirements.txt`、`AGENTS.md`、`.env.example`、`reports/cost.md`、`CHANGELOG.md` | K9/勘误/记录 |

## 5. 分步任务（执行顺序）

| 步 | 任务 | 验收 | 依赖 |
|---|---|---|---|
| 0.0 | **双端 git 对齐**：本机 rebuild_docs.py 自举补丁检视→commit→push；容器侧 fetch/checkout 清点（GitHub 仍不通则 scp 对齐）——M2 遗留③闭环 | 双端 `git log` 一致、working tree 干净 | 无 |
| 0.1 | **S3 清障批**：K0 明细 13 Minor + 指定 Nit + 新增单测（编号 References/合计行排除/缓存跳过语义/m-13 断言修复） | pytest 全绿（65+新增） | 0.0 |
| 0.2 | **工程卫生+冒烟题**：requirements 钉版+去 httpx2+pip-audit；AGENTS/.env.example 勘误；20 题出题版本化 | 锁定入库、audit 无高危、smoke_queries.json 入库 | 0.0 |
| 3.1 | hybrid.py（三路+RRF+证据组去重+TIER_KINDS+tokenize 单例）+ 单测 | 纯函数单测绿；真实查询三路命中且回表可取正文 | 0.1 |
| 3.2 | rerank.py（解析链+截断+双档+降级+t_rerank_cache）+ 单测 | 三级解析四类单测绿；D 档实测重排生效，延迟/降级率入 cost.md | 3.1 |
| 3.3 | router.py（语言检测+BM25 旁路）+ 单测 | zh/en/混合三态正确 | 无（可与 3.2 并行） |
| 3.4 | 生成四件套（context/vlm/citations/fallback）+ 单测 | 引用解析四类+降级标记单测绿；组装顺序断言绿；reasoning 不入答案 | 3.1 |
| 3.5 | trace.py + query_cli.py + --smoke；集成验收：六档各跑通 → 20 题冒烟人工填列 → 性能实测入 cost.md | §1 验收表全过 | 3.2/3.3/3.4 |
| 收尾 | CHANGELOG + tag m3 + 主计划补记（trace.py 入文件树、search_probe 退役说明、工期 2→2.5–3 天）+ Next Action + 清障批复核记录 | 双端同步 | 3.5 |

## 6. 测试策略（普通实现，延续 M2 决策）

- 纯逻辑单测重点：RRF/加权 RRF/DBSF 纯函数（k、权重敏感性）、证据组归并、三级解析四类、引用正则四类+无效降级、语言检测三态、fallback 判定表、组装顺序（图文交错/首尾/图 ≤5）、TIER_KINDS 双后端一致性、BM25 tokenize 配对拍、重排缓存键。
- 集成走容器/隧道真实调用（Qdrant/BM25/LLM/VLM 不进单测）；新增逻辑覆盖率 ≥80%（纯逻辑部分）。
- 冒烟题人工验收走 `--smoke` 报告（答案/引用/命中并排+人工列），不裸跑终端肉眼比对。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| 重排延迟超预算（强制思考模型） | 输入截 30+max_tokens 从紧+TTFT 埋点早暴露 | 降级回 RRF 序（degraded 标记既定）；pro 档级联 |
| 重排输出不稳（temp=0 非确定+思考干扰） | 三级解析链兜底+降级率入验收 | 解析失败自动回 RRF 序 |
| 误拒率压不到 ≤1/16 | 阈值从松扫起+judge 提示词迭代+judge 可换 pro 档 | 兜底降级为仅 prompt 第三道（记录在案，M5 重试） |
| 引用格式漂移/引用幻觉 | 正则兼容四类+无效 n 降级标记落 trace | 极端情况退化为"答案不带内联 [n]、引用列表整体附后"（记录） |
| 中英对照通路不达标 | M3 只验通路（命中+出引用）；≤5pp 全量验收在 M5 | BM25 降权档 M5 调参 |
| qdrant client/server 行为差异 | 0.2 钉 `~=1.15.4` | 服务器升级另行提案 |
| GitHub 仍不通 | 0.0 scp 对齐预案 | 同 M2 遗留③处理方式 |
| Windows GBK 编码再现 | 入口 reconfigure（K8） | 环境变量 PYTHONUTF8=1 兜底（已验证） |
| 成本 | 冒烟 20 题×六档≈120 次检索+40–80 次 LLM 调用，量级可控；额度观察纪律不变（方舟控制台看余量） | 砍 F 档（P1） |

## 8. 敏感代码判定

**是（敏感）**：外部 API 调用面扩大（重排 LLM/judge/VLM + 查询侧嵌入）+ 凭据使用（ARK_API_KEY、QDRANT_API_KEY、MYSQL_URL 密码）+ **新增 trace 落盘面**（key/密码/.env 值绝不入 trace；问题原文与答案入库属预期）。实现完成后走 S4 安全复查。

## 9. 执行命令

```bash
# —— 容器内（默认拓扑，/home/doclens/RAG）——
python -m pytest -q
python scripts/init_db.py                          # 幂等；0.2 后新增 t_rerank_cache
python scripts/query_cli.py --profile D --question "问题"
python scripts/query_cli.py --smoke                # 20 题 × 当前档
python scripts/query_cli.py --profile A --smoke    # 指定档跑全套

# —— 本机（可选场景，先挂隧道再跑；2026-11-11 体检 6/6）——
# ssh -N -L 13306:127.0.0.1:3306 -L 16333:127.0.0.1:6333 root@10.14.50.123   # 端口 8009，免密；或 VS Code 端口面板加 3306/6333
# $env:PYTHONUTF8='1'; $env:MYSQL_URL='...@127.0.0.1:13306/doclens'; $env:QDRANT_URL='http://127.0.0.1:16333'
```

---
## 确认门记录（S2 开始前填写）
- 批准时间：2026-11-11 19:51 (+08:00)
- 批准指令原文：「开始吧 完成M3 保证质量」
- TDD：否（普通实现，延续 M2 决策④；质量保障走 S3 代码审查 + S4 安全复查 + 集成验收）
