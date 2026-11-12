# DocLens M4 服务+UI·规划审查与同类项目调研笔记

> 状态：**v1.2（已核实为主）**——2026-11-11 立稿（v1.0：P/G/R 审查+A/B 两线调研）；**2026-11-12 增补 §7 高分项目横评（C 线）、§8 交互与协议深挖（D 线）、§9 论文库调研（E/F 线）**。审查结论为本会话实测核实（SSH 探针/源码/数据）；A/B/C/D/E/F 六条调研线由研究代理并行完成，web_search 全程 HTTP 402 不可用，全部经 ghfast.top/ungh.cc 代理直抓官方文档与源码核实；未能核实项在 §5 列明。
> 用途：主计划 M4 节（`doclens-multimodal-rag.plan.md` §5 M4）的问题审查 + [m4-runbook](../plans/)（**待立项**）的方案佐证与修订输入，随 G1 确认门一并过目。
> **配套演示**：[m4-ui-mockup.html](m4-ui-mockup.html)——单文件交互原型（无后端、无构建，浏览器直接打开）：演示 §1.4 契约的完整时序（阶段条 → sources 先于首 token → 思考折叠面板 → 流式正文+可点击引用 → bbox 百分比高亮 → citations/done），含图表题/表格题/不可回答题三个剧本（bbox 抄自真实 doc.json 探针值）；M4 runbook 立项时可直接作前端布局蓝本。
> 与 [m3-retrieval-generation-survey](m3-retrieval-generation-survey.md) 强关联：M4 的 SSE 契约直接消费 M3 调研 R9（思考流）/R11（引用编号语义）/R15（trace 字段），本文不重复引用其原文，只标"m3 调研 R#"。
> 约定：标注【实测】= 本会话亲自验证（SSH 探针/读源码/读数据）；带 [n] 的为调研代理核实来源（编号见 §6）。

## 0. 与项目规划的映射（本笔记如何进入 M4 runbook）

| 审查/调研发现 | 对应规划位 | 结论 |
|---|---|---|
| 容器无 Node/npm/pnpm【实测】，主计划 §9 的 `pnpm install && pnpm dev` 在现行拓扑不可执行 | D9 / §9 执行命令 | **硬伤 P1**，修订 R1 |
| MySQL/Qdrant 端口外部不可达（m2 S4 取证）→ 同理 uvicorn/Vite 端口 Windows 浏览器不可达，演示必须走 SSH 端口转发 | D13 修订⑥ / M4 runbook | **硬伤 P2**，修订 R2 |
| M4 全部压在 M3 管线上，而 retrieve/generate 包目前为空壳【实测】 | M3/M4 时序 | **硬伤 P3**，修订 R11 |
| /api/query 的 SSE 事件契约主计划未定义 | 4.1 | **缺口 G1**，修订 R3/R4 + §1.4 契约提案 |
| glm-5.3-flash 强制思考不可关（m3 调研已核实），前端需"思考中"状态 | 4.2 | **缺口 G2**，修订 R5 |
| ≤20s 验收无计时口径，且强制思考使首 token 延迟预算失真 | S2/FR-5.2/NFR | **缺口 G3**，修订 R6 |
| bbox 坐标系约定与高亮换算未写（已核实 0–1 归一化、左上原点【实测】） | 4.2 / FR-1.2 | **缺口 G4**，修订 R7 |
| assets.py "PDF 页渲染"职责两可 | 4.1 | **缺口 G5**，修订 R8 |
| Gradio(P1) 与 M3 CLI/--smoke、FR-5.3 定位重叠；Chainlit 已归档停维护【B 线核实】 | 4.3 | **缺口 G6**，修订 R9 |
| FastAPI 官方内置 `app.frontend(dist)` SPA 托管；react-pdf 11 要求构建 Node≥22.13【B 线核实】 | 交付形态/工具链 | 印证 R1 交付形态 |
| M4 是首个 Web 面，安全验收只有一句"前端不暴露 key" | §8 / 4.1 | **缺口 G7**，修订 R10 |
| 前端/契约测试策略空白 | §6 | **缺口 G8**，修订 R12 |
| 同类项目引用高亮：**仅 RAGFlow 做到 bbox 级**（react-pdf-highlighter 钉 6.1）；Kotaemon 无坐标靠文本匹配；Onyx/Verba/AnythingLLM/OpenWebUI 止步文档卡片【A 线核实】 | 4.2 选型 | §2 已回填——印证 bbox 路线差异化 + R8 选型 |
| SSE/前端工程细节（事件惯例/Vite proxy/pdfjs worker/Chainlit） | 4.1/4.2 | §3 已回填 |

## 1. M4 规划审查——问题清单（2026-11-11 实测核实）

### 1.1 硬伤（有实测证据，立项前必须解决）

**P1：前端工具链假设过时（拓扑变更遗留）。**
主计划 D9/§9 写于"本地运行应用"时代（修订⑥之前），M4 执行命令 `cd web && npm i -g pnpm && pnpm install && pnpm dev` 隐含"前端工具链在应用运行机上"。但修订⑥后应用（含 M4 的前后端）都跑在容器里，而**容器内 node/npm/pnpm 全部 command not found**【实测 SSH】。可用事实：
- apt 候选 nodejs = 10.19.0【实测】，远低于 Vite 要求（≥18/20），apt 路线不可行；
- 容器网络：`registry.npmjs.org` 与 `registry.npmmirror.com` 均 HTTP 200 直通【实测】（GitHub 不通不影响 npm 源）；npmmirror 的 node 二进制镜像可达（302）；
- Windows 侧 Node v26.3.0 + npm 11.16.0 仍在【实测】，与主计划 §2 记载一致；
- 容器 /home 余量 518G【实测】，node_modules 无压力。

三条候选路线（对比详见 §3.4）：A）容器装官方 Node 二进制（npmmirror 镜像下载解包，不走 GitHub）；B）Windows 侧开发与构建 `web/dist` → git 同步 → FastAPI 托管——免容器 Node，且与 M6/FR-7.1 的 Win11 克隆验证天然同构；C）免构建 CDN 方案（不推荐）。**定稿建议（R1）=B 路线为主**：开发期 Windows Node 跑 Vite dev（API 经 SSH 隧道到容器，热更新——高亮对齐类视觉迭代省大量往返），交付期 Windows 构建 dist → FastAPI `app.frontend("dist")` 托管——单进程单命令，贴合 S3"两条命令跑通"；容器不装 Node，npmmirror Node 22+ 二进制为备选。

**P2：演示访问路径未写（演示当天最容易翻车的点）。**
m2 S4 已取证 3306/6333 外部不可达——同理，容器内 uvicorn/Vite 监听的端口，Windows 浏览器也**不能直连**。可行路径只有两条：VS Code Remote-SSH 的自动端口转发（已打通 Remote-SSH，转发是内建能力），或 `ssh -L 8000:127.0.0.1:8000` 手动隧道【SSH 连通性实测可用】。M4 runbook 必须把"后端 bind 127.0.0.1 + 转发方式 + 浏览器访问 http://localhost:8000"写成验收步骤，并顺带完成 AGENTS 里挂着的".env 写 10.14.50.123 不可达"勘误的表述统一（M4 后端在容器内跑，.env 全部 127.0.0.1，主计划 §9 注释里的旧说法不要再扩散）。

**P3：依赖时序——M4 的两个验收步全部压在一个还没开工的里程碑上。**
`doclens/retrieve` 与 `doclens/generate` 目前是空壳【实测】，M3 runbook 未立项。M4 的 /api/query 没有可包的管线、web/ 没有可显示的引用。结论：**M4 立项排在 M3 收官之后**（顺序本来就是 M3→M4，这里只是提醒：M4 runbook 里不许出现"先做 UI 用假数据"之类的安排——要 mock 就只 mock /api/query 一个边界，且以 §1.4 契约为准，避免契约双侧漂移）。

### 1.2 缺口（规划未覆盖、runbook 立项时补）

- **G1 SSE 事件契约未定义**：主计划只写"/api/query(SSE)"一个词。事件 schema、引用映射何时下发、错误与降级如何表达，全部空白。而这恰是 M3（管线）与 M4（前端）的接口边界，不先冻结就会出现"前端按猜的 schema 写完、M3 出不来"的返工。→ §1.4 给出契约提案（对齐 m3 调研 R11/R15），修订 R3/R4。
- **G2 thinking 流展示未规划**：glm-5.3-flash 强制思考不可关（m3 调研已核实官方文档），流式时 reasoning_content 与 content 分离、usage 只在末 chunk（m3 调研已核实）。思考期实测可长达 5–15s（m3 调研记录：M0 实测 doubao 全流 10.76s、E 档曾现 132s 长思考），前端若无"思考中"可见状态，演示时就是画面卡死 10 秒。→ 修订 R5。
- **G3 ≤20s 验收无计时口径**：S2/FR-5.2 只写"完整演示流程 ≤20s"，没定义从哪个时刻到哪个时刻、冷启动还是热启动、回答多长。强制思考模型下"生成首 token<5s"大概率守不住（m3 调研 R9 已建议 M3 校准该口径），M4 的 20s 预算必须重新分解并实测校准。→ 修订 R6（预算分解见该条）。
- **G4 bbox 高亮换算约定未写**：已核实【实测】——MinerU 4.1.7 的 structured_content.json 中 bbox **原生即 0–1 归一化** `[x0,y0,x1,y1]`（`mineru_parser.py` 模块 docstring 实测记录在案），M1 原样入库 doc.json/t_chunk；同页多块 y 随阅读顺序递增 → **左上原点、y 向下为正**。前端换算就是 `left=x0×W, top=y0×H, width=(x1−x0)×W, height=(y1−y0)×H`（W/H=渲染视口像素），无需再乘页宽页高 pt 值。runbook 把该约定写成显式规则，并加一条验收："任选 2 篇第 1 页各 2 块，高亮框与实际区域对齐抽检"（防 crop box/viewport 边缘差异）。→ 修订 R7。（另【A 线核实】：MinerU master 的 content_list 协议已改 0-1000 整数框——本项目锁定 4.1.7 的 0-1 浮点口径，**升级 MinerU 时必须复检此处**；MinerU page_idx 0 起 vs M1 schema 1 起页码【实测】，前端组件 pageNumber 1 起可直接对齐。）
- **G5 assets.py 职责两可**："PDF 页渲染 + overlay 数据"（主计划 §4 文件树注释）可读成"后端渲染页面图"，与 D9 的 pdf.js 浏览器端渲染矛盾。应明确后端只供三样：① PDF 原文件流（`/api/docs/{doc_id}/pdf`，文件路径从 t_doc/解析缓存映射，绝不接受用户传路径）；② figure 图片（`/api/figure`，按 doc_id+序号或 chunk_id 寻址）；③ 引用与 bbox 数据随 SSE 事件下发（G1 的 sources/citations 事件），**不需要独立 overlay 接口**。→ 修订 R8。
- **G6 4.3 Gradio(P1) 定位重叠**：M3 调研 R16 已定 `query_cli.py --smoke` 产 Markdown 验收报告——开发期调试工具已有着落；FR-5.3 检索可视化(P1)建议并入 4.2 主前端（stage 进度条 + 各路命中分数面板），这恰是面试演示的加分项；Gradio 与这两者重叠，建议砍掉或降为"有余力再做"（若保留：`mount_gradio_app` 挂 /gradio 复用同一管线，成本很低，见 §3.6；Chainlit 已归档停维护、从候选排除【B 线核实】）。→ 修订 R9。
- **G7 M4 安全验收细则未前置**：主计划 §8 只有一句"前端不暴露 key"；m2 security review A01 也预告"服务化时复查"。M4 是全项目首个 Web 面，五条最低验收应直接写进 runbook（不等 S4 事后补）：① PDF/图片接口路径穿越守卫——按 doc_id 从库里映射文件，拒绝一切用户传入路径，realpath 包含性校验；② 默认 bind 127.0.0.1；③ 不开 CORS 中间件（Vite proxy / 同源静态托管）；④ `VITE_*` 环境变量零秘密（key 只在后端进程）；⑤ SSE 事件与日志不含 key（沿用 M2 S4 纪律）。→ 修订 R10。
- **G8 前端/契约测试策略空白**：§6 只有"httpx TestClient 打 /api/query"。建议补：一条 SSE 契约测试（断言事件序列与 schema）；前端不上 JS 测试框架（作品集体量不值），用手工验收清单（中英提问、流式、引用点击、不可回答题拒答展示、思考状态展示）代替。→ 修订 R12。

### 1.3 修订建议汇总（→ m4-runbook；立项经 G1 确认后并入）

| # | 修订 | 落点 | 级别 |
|---|---|---|---|
| R1 | 前端工具链路线定稿：开发期=Windows Node 跑 Vite dev（API 经 SSH 隧道到容器 uvicorn，热更新）；交付=Windows 构建 dist → git 同步 → FastAPI `app.frontend("dist")` 托管（官方内置 SPA fallback，单命令启动）；容器不装 Node 为主推（备选=npmmirror Node 22+ 二进制；react-pdf 11 要求构建 Node≥22.13，apt 路线排除） | runbook 4.2 前置 + §9 命令修订 | **必要** |
| R2 | 演示访问路径写死：bind 127.0.0.1 + VS Code 端口转发（或 ssh -L），"浏览器 localhost:8000 打开"入验收步骤 | runbook 4.1/4.2 验收 | **必要** |
| R3 | SSE 事件契约冻结（stage/token/sources/citations/done/error，schema 见 §1.4），作为 M3/M4 接口边界，双侧以此实现并各配契约测试 | runbook 4.1 + 交接 M3 | **必要** |
| R4 | sources 事件在上下文组装完成即发（Source N 编号组装期已定，m3 调研 R11）——引用侧栏流式期间即可点击；citations 终版在 finish 后发（实际被引 n + 无效 n 降级标记，不静默删） | runbook 4.1/4.2 | 建议 |
| R5 | thinking 状态 UI：reasoning_content 只进 trace 与"思考中"状态条，绝不混入答案正文；折叠面板样式从主流 UI 惯例（§3） | runbook 4.2 | 建议 |
| R6 | ≤20s 计时协议：热启动（第二轮起计）、system prompt 限回答 ≤200 字、计时取 trace 时间戳（提交→正文首 token→流式完成→点击引用→高亮可见）+ 录屏叠加计时；预算重分解=检索 ~2s + 重排 2–5s + 思考 5–15s（状态可见）+ 流式 5–10s + 点击高亮 1–2s，实测校准；超 20s 的降级开关=演示档 max_tokens 从紧/回答更短 | runbook 验收 + NFR 校准 | **必要** |
| R7 | bbox 约定显式化：0–1 归一化、左上原点、换算公式 + "2 篇×第 1 页×2 块对齐抽检"验收 | runbook 4.2 验收 | 建议 |
| R8 | assets.py 职责定稿三件套（PDF 文件流/figure 图片/引用数据随 SSE 下发），不做服务端页面渲染（Kotaemon 老路，§2.3）；渲染库选型 G1 拍板：**react-pdf 11 + 自绘 overlay（主推）** vs react-pdf-highlighter 6.1（RAGFlow 同款备选，实质停更）——理由见 §2.3；worker/cMaps 配置按 §3.5 | runbook 4.1/4.2 | **必要** |
| R9 | 4.3 Gradio 砍单或降级（若保留：`mount_gradio_app` 挂 /gradio；Chainlit 已停维护排除）；FR-5.3 检索可视化并入 4.2（stage 进度 + 分数面板） | runbook 4.3 | 建议 |
| R10 | 安全验收五条前置（路径穿越守卫/bind 127.0.0.1/无 CORS/VITE_ 零秘密/日志脱敏） | runbook 验收 + §8 细化 | **必要** |
| R11 | M4 立项时序=M3 收官后；若要提前开工 UI，只许 mock /api/query 一个边界且以 §1.4 契约为准 | runbook 依赖声明 | 建议 |
| R12 | 测试补位：SSE 契约测试 1 条 + 前端手工验收清单（5 项），不上 JS 测试框架 | runbook 测试策略 | 建议 |

## 1.4 /api/query SSE 事件契约（提案——M3/M4 接口边界，立项时冻结）

```
event: stage      data: {"stage":"retrieve"|"rerank"|"assemble"|"generate","detail":...}
event: sources    data: {"sources":[{"n":1,"doc_id":"...","page":3,"bbox":[...],"kind":"text|table|caption|image",
                          "chunk_id":"...","snippet":"...","image_path":null|"..."}], "profile":"D"}
event: token      data: {"content":"..."}            # 只透传 delta.content；reasoning_content 不进此事件
event: thinking   data: {"status":"started"|"done","elapsed_ms":...}   # 思考状态（R5）
event: citations  data: {"cited":[1,3],"invalid":[7],"elapsed_ms":...} # finish 后：实际被引 n + 无效 n 降级标记（m3 调研 R11）
event: done       data: {"finish_reason":"stop","usage":{...},"timing":{...},"trace_id":"..."}
event: error      data: {"code":"...","message":"...（脱敏）"}
```

- 时序：`stage(retrieve)` → `stage(rerank)` → `stage(assemble)` + **`sources`（一次发全，编号即 Source N，m3 调研 R11）** → `stage(generate)` + `thinking(started)` → `token`×N + `thinking(done)` → `citations` → `done`。错误在任何点可发生，发 `error` 后关流。
- `sources` 先于首 token 的意义：引用侧栏在流式期间即可点击跳转（改善 G3 的 20s 预算与演示体验）；`citations` 只是终版过滤/排序信息。
- 心跳：空闲 >15s 发 SSE 注释行（`:` 开头）防代理断连；客户端断线不重连续传（演示场景，刷新重问即可）。
- 与 M3 的分工：M3 管线以生成器/回调形式吐上述事件载荷，/api/query 只是 SSE 编码层；trace JSONL（m3 调研 R15）在 M3 侧落盘，done 事件只带 trace_id。

## 2. 同类项目：引用溯源与 PDF 高亮（调研线 A——已返回，来源 [A1]–[A6]）

> 调研代理注：web_search 全程 HTTP 402；github.com/raw 主站被本机 DNS 拦截，经 ghfast.top/ungh.cc 代理直抓源码与官方文档核实。

### 2.1 对比表（来源 [A1]–[A3]）

| 项目 | 引用定位机制 | 坐标存储 | 页面渲染 | 前端栈 |
|---|---|---|---|---|
| RAGFlow | chunk.positions → 前端定位高亮（**调研项目中唯一 bbox 级**） | [[页号,x1,y1,x2,y2]] 5 元组（API 文档未写明单位/顺序） | 浏览器 pdf.js（react-pdf-highlighter@^6.1.0） | React18+Vite+Tailwind/Radix |
| Kotaemon | **无 bbox**：LLM 引文 → 字符串匹配（LCS 比率 >0.5）→ textLayer span 高亮 + 跳页 | 无坐标，仅页码+短语 | pdf.js 预构建 viewer（iframe） | Gradio(ktem)+原生 JS |
| Onyx | [n]→document_id 文档级；悬停源卡片，点击开预览 | 无坐标、无页级 | 文档预览，无 bbox 高亮 | Next.js/React |
| Verba/AnythingLLM/OpenWebUI | 引用止于文档/片段卡片 | 无 | 无原文页 bbox 高亮（未源码核实） | — |

### 2.2 关键事实（源码级）

- **bbox 级高亮是稀有特性，DocLens 路线对齐头部**：对比项目里只有 RAGFlow 真正做"引用→原文 bbox 高亮" [A1]；Kotaemon 用文本匹配替代坐标（引文→chunk 文本 find_text→textLayer span 包裹）[A2]；Onyx 编号只到 document_id [A3]。→ M2 的 t_chunk bbox 投入直接兑现为 RAGFlow 级展示形态；且比 Kotaemon 的字符串匹配稳——图/表证据无文本可匹配，恰是本项目核心题型。
- **react-pdf-highlighter 现状**：main=v8-rc，**实质停更**（最后 push 2024-11-22，npm 最新 8.0.0-rc.0/2024-09）；RAGFlow 钉 6.1.0（连带 pdfjs-dist 2.16）。ScaledPosition 模型=页面归一化 0-1 boundingRect ⇄ viewport 换算 + scrollTo 跳页 [A4]。
- **pdf.js 坐标系**：PDF 原点左下、y 向上，CSS 像素经 viewport transform 翻转；`PixelsPerInch.PDF_TO_CSS_UNITS=96/72` [A4]。→ DocLens 的 0-1 归一化坐标用**百分比定位**可绕开原点翻转问题（G4 换算式 + R7 对齐抽检兜底）。
- **MinerU 版本漂移警告**：master 的 content_list 协议已把 bbox 改为 **0-1000 整数框**（normalize_bbox 注释 `int(v*1000)`），middle 协议仍 0-1 浮点；官方文档未明文原点方向 [A5]。→ 本项目锁定 4.1.7 的 0-1 浮点口径（parser docstring 实测记录 + G4 数据探针双证）；**升级 MinerU 时必须复检**。
- **Range 请求**：pdf.js 无 206 时自动整文件下载（可 disableRange）；Starlette StaticFiles 全文无 Range 逻辑（FileResponse 不做 206）[A6]。→ 11 篇小 PDF 全量下载无实际影响；Range 列可选优化，非阻塞。
- **页码基准**：MinerU page_idx 0 起；M1 schema 已统一 1 起页码【实测 doc.json】；react-pdf / react-pdf-highlighter 的 pageNumber 均 1 起——可直接对齐。

### 2.3 对 4.2 的选型结论（→ R8，G1 确认门拍板）

- **主推：react-pdf（wojtekmaj）+ 自绘 overlay**。理由：① DocLens bbox 已 0-1 归一化 → 高亮=百分比定位 div（`left:x0*100%; top:y0*100%…`），自绘成本约十行，不需要 react-pdf-highlighter 的 textLayer 注入机制（那是为"文本锚定高亮"设计的，本项目锚定的是图表/段落 bbox）；② 维护中、pdf.js 现代（B 线已核实 worker/cMaps/React19 配置）；③ 引用跳页=页面容器 scrollIntoView，平凡实现。
- **备选：react-pdf-highlighter 6.1.x（RAGFlow 同款）**——若想要现成 scrollTo/弹注/文本锚定；代价=实质停更 + pdfjs-dist 2.16 老 + 与 React 19 peer 依赖冲突风险（RAGFlow 自身钉 React 18）。
- **不做后端转图（Kotaemon 老路）**：丢文本选择、占存储；11 篇语料浏览器端 pdf.js 足够【与 R8/G5 一致】。
- 引用数据结构：主推路线用 §1.4 sources 事件的简化结构（{n,doc_id,page,bbox,kind,snippet}）；选备选库则对齐其 IHighlight{content,position{pageNumber,boundingRect,rects}}。

## 3. 工程实现：SSE/前端工具链/思考流（调研线 B——已返回，来源 [B1]–[B12]）

> 调研代理注：web_search 全程 HTTP 402 未用上；github.com/raw 主站被本机 DNS 拦截，经 ghfast.top 前缀代理抓取成功（与 m2/m3 调研同款网络环境）。下列 [B#] 均指原始地址。

### 3.1 SSE 服务端（→ 4.1 api.py）

- sse-starlette `EventSourceResponse` 接 async 生成器（yield {event,data,id,retry}），**ping 默认 15s**（检索+重排最长 ~7s，覆盖得住），`request.is_disconnected()` 断连检测 [B1]；FastAPI 官方已建 SSE 教程页 [B2]（正文抓取超时，标题/导航两处核实存在）。
- **代理缓冲坑**：nginx 默认缓冲 ~16KB 才 flush（需 `X-Accel-Buffering: no`）、Cloudflare ~100KB [B1]；本项目开发期 Vite proxy（http-proxy-3 透传）与直连 FastAPI 无此层，但响应头仍应带 `Cache-Control: no-cache`，且该路由不加 GZip（uvicorn 默认不压缩）。
- 落地：用 sse-starlette（M0 已锁版本，容器实测就位）；手写 StreamingResponse 须自实现格式化/ping/断连，不划算。断线**不做服务端续传**——单次问答流语义上重连=重新提问，前端出错提示重发即可。

### 3.2 前端消费 SSE（→ 4.2 web/）

- EventSource 只支持 GET、无 body、无自定义 header [B4]；问答必须 POST JSON → **@microsoft/fetch-event-source**（POST+headers+onerror 自控重试+Page Visibility）[B4]；fetch+ReadableStream 手写分帧为备选。
- Vite dev：`server.proxy {'/api': {target:'http://127.0.0.1:8000', changeOrigin:true}}`，代理透传流式响应（官方无 SSE 专节）[B3]。

### 3.3 思考流渲染惯例（→ R5）

- z.ai 官方流式：`delta.content` 与 `delta.reasoning_content` 并列、finish_reason/usage 仅末 chunk [B5]；glm-5.3-flash 官方页：**thinking.type 仅支持 enabled**（强制思考获第二个官方口径印证）、原生多模态、1M 上下文 [B6]。
- 开源惯例（已核实）：Gradio Chatbot 以 metadata 渲染**可折叠思考面板**、`reasoning_tags` 自动抽取折叠 [B7]——"思考中灰字实时流式 → 正文首 token 后折叠为'已思考'面板 → reasoning 不入对话历史"是现成范式，前端照此实现即可。

### 3.4 容器无 Node 的路线对比（→ R1 定稿）

- 【实测补充】本容器 apt nodejs 候选=10.19.0（Ubuntu focal 系），比代理核到的 Debian bookworm 18.20.4 还老——apt 路线彻底排除；Node 18 已 EOL、Vite 7 需 Node 20.19+ [B8]。
- npmmirror 官方支持 npm registry 配置 + node 二进制镜像 `/mirrors/node`（配合 n 的 `N_NODE_MIRROR` 可离线装）[B8]；容器内两镜像可达【实测 HTTP 200/302】。
- **FastAPI 官方已内置静态前端托管**：`app.frontend(directory="dist")`——API 路由优先，`fallback="auto"` 即 SPA history fallback [B9]；交付形态一行代码。
- **react-pdf 11 要求 React≥19 且构建 Node≥22.13** [B10]——若走容器内构建，容器 Node 必须 22+（npmmirror 二进制可装）；Windows 侧 v26 无此约束。
- **落地建议（R1）**：开发期=**Windows Node 跑 Vite dev**（API 经 SSH 隧道指到容器 uvicorn），享受热更新——高亮对齐这类视觉迭代必多次往返，"改一行→git 双端同步→重建→刷新"的开发环不可接受；交付/演示=**Windows 构建 dist → git 同步 → FastAPI `app.frontend` 托管**（单进程单命令，与 M6/FR-7.1 的 Win11 克隆验证同构）；容器不装 Node 为主推，npmmirror Node 22+ 为备选。CDN+htmx 免构建方案放弃（丢工程分量，作品集不建议）[B8]。

### 3.5 pdf.js / react-pdf 集成细则（→ R8）

- worker 正确姿势：`pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()`，**必须在渲染 <Document> 的同一模块设置**（否则默认值可能覆盖）；pnpm 需 `.npmrc` 加 `public-hoist-pattern[]=pdfjs-dist` [B10]。
- **中文 PDF 必须带 cMaps**（vite-plugin-static-copy 复制 `pdfjs-dist/cmaps` → `options.cMapUrl:'/cmaps/'`）——本期英文 arXiv 影响小，**财报泛化包必做**；standard_fonts 与 JBIG2/JPEG2000 wasm 目录同理 [B10]。
- 高亮=在 <Page> 上叠绝对定位 overlay div，按 viewport scale 换算坐标 [B10]——与 §1.2 G4 的 0–1 归一化约定拼接（`left=x0×W, top=y0×H…`），链路闭合。

### 3.6 调试界面与阶段进度（→ R9）

- **Chainlit 已归档、官方声明停维护**（无 bug fix/安全更新）[B11]——从候选中排除；Gradio 活跃（当前 6.31），ChatInterface 流式 + ChatMessage metadata 折叠步骤卡 + `mount_gradio_app` 挂进 FastAPI [B7][B12]。
- 落地：4.3 若保留 Gradio，走 `mount_gradio_app` 挂 `/gradio` 复用同一管线（成本很低）；开发期验收主力仍是 M3 的 `query_cli --smoke`（m3 调研 R16）。演示阶段进度 = §1.4 的 `event:stage` 驱动前端三段步进条（检索→重排→生成，附各段耗时），自绘成本极低；Perplexity 式步骤条无开源直接复刻先例〔未核实〕。

## 7. 高分项目横评补充（C 线，2026-11-12——M4 立项加做，12 项目全量实抓）

> 动机：G1 立项前对"服务+UI"形态做一轮高分 GitHub 项目横评，验证 R1–R12 选型、找可借鉴交互。星标均经 ungh.cc 实抓（截至 2026-11-12）；ai-chatbot 已更名 vercel/chatbot。D 线（交互与协议深挖）见 §8。

### 7.1 对比矩阵（星标实抓 [C1]；其余实抓见 [C2]–[C18]）

| 项目(星标) | 前端栈 | 流式协议 | 引用形态 | 思考流 | 阶段提示 | PDF 预览 |
|---|---|---|---|---|---|---|
| dify 161.0k | Next.js | SSE（ssePost 解析 data: 行，实抓） | 来源卡片/文档级〔昨日口径〕 | reasoning_chunk 独立事件（实抓） | node_started/finished+agent_log 事件（实抓） | react-pdf-highlighter 依赖〔用途未核实〕 |
| open-webui 158.4k | Svelte5+Vite | SSE(eventsource-parser)+socket.io 并存 | 编号+来源卡片+CitationModal（组件实抓） | 〔未核实〕 | StatusHistory/StatusItem 组件（实抓） | pdfjs-dist+FilePreview（实抓） |
| ragflow 94.0k | React18+Vite+AntD | SSE（eventsource-parser 实抓） | **bbox 页级高亮**（昨日复核；react-pdf-highlighter 依赖实抓） | 〔未核实〕 | 〔未核实〕 | react-pdf-highlighter 内嵌（实抓） |
| anything-llm 68.2k | React18+Vite | SSE（@microsoft/fetch-event-source 实抓） | 编号+来源侧栏（Citation/SourcesSidebar 组件实抓） | thinking 动画+ReasoningEffort（实抓） | thinking 动画（实抓） | 〔未核实〕 |
| private-gpt 57.6k | 自带 Workbench UI（演示用） | messages API streaming（README 实抓；SSE〔未核实〕） | citations（README 实抓；粒度未核实） | 〔未核实〕 | 〔未核实〕 | 〔未核实〕 |
| onyx 33.3k | Next16+React19 | 〔未核实〕 | 文档级〔昨日口径〕 | 〔未核实〕 | 〔未核实〕 | pdfjs-dist+react-pdf（实抓） |
| FastGPT 30.0k | Next.js+Chakra | SSE（@fortaine/fetch-event-source 实抓） | 编号+引用列表（官方文档 quoteList.mdx 实抓） | 〔未核实〕 | 〔未核实〕 | 〔未核实〕 |
| kotaemon 25.9k | Gradio | Gradio 内建流 | 引用+相关性评分+**浏览器内 PDF 高亮**（README 实抓；文本匹配级=昨日口径） | 〔未核实〕 | 低相关告警（README 实抓） | 内置 PDF_JS 查看器（README 实抓） |
| MaxKB 23.1k | Vue3+Element Plus | 〔未核实〕（依赖无 SSE 库） | 段落级〔昨日口径〕 | 〔未核实〕 | 〔未核实〕 | pdfjs-dist（实抓） |
| ai-chatbot 21.0k | Next16+React19 | AI SDK 数据流（SSE 基）+resumable-stream 续流（实抓） | 无（非 RAG） | message-reasoning.tsx+ai-elements/reasoning.tsx 折叠组件（实抓） | shimmer/spinner（实抓） | 文档 artifact 预览（实抓） |
| QAnything 14.2k | Vue3+Vite+AntDVue | SSE（fetch-event-source 实抓） | 引用弹窗（ChatSourceDialog 实抓） | 〔未核实〕 | 〔未核实〕 | Source/PdfView.vue+@vue-office/pdf（实抓） |
| Verba 7.7k | Next14+daisyUI | 〔未核实〕 | 来源卡片〔昨日口径〕 | 〔未核实〕 | 〔未核实〕 | react-pdf/renderer 为"生成"非"预览"（实抓） |

### 7.2 共性规律（→ 对 R1–R12 的校验结论）

1. **SSE 一统（7/12 实抓到 SSE 依赖）**：RAGFlow/Dify/OpenWebUI/AnythingLLM/FastGPT/QAnything/ai-chatbot 全走 SSE 系；WebSocket 仅 open-webui 与 dify 作附属实时通道——**R3 的 FastAPI SSE 选型是主流正解**。
2. **引用交互天花板普遍在文档级**：多数止步"编号+来源卡片"；页级高亮仅 kotaemon（文本匹配）与 RAGFlow（bbox）——**bbox 级仍是稀缺差异点（2/12），DocLens 路线对齐头部且差异化成立**（印证 §2.1/R8）。
3. **思考流折叠成标配**：dify 独立 reasoning_chunk 事件、ai-chatbot reasoning 折叠组件、anything-llm thinking 动画——**R5 双字段分流+折叠面板方向与业界一致**。
4. **阶段可视化=轻事件流**：dify node 事件、open-webui StatusHistory、anything-llm 动画，无一用重型进度系统——**K6 用 stage 事件驱动步进条的成本判断成立**。
5. **pdfjs 系预览是标配（7/12）但 ≠ 引用定位**：打通"点击引用→原页 bbox"的仅 RAGFlow/kotaemon 两家——预览易、溯源难，M4 验收把 bbox 对齐抽检（R7）设为硬项是对的。
6. **@microsoft/fetch-event-source 是 SSE 消费事实标准**（anything-llm/QAnything 直用，FastGPT 用其 fork @fortaine）——K3 选型有充分先例。

### 7.3 对 DocLens M4 的可借鉴点（→ runbook K 决策佐证）

- **dify**：SSE 事件词汇表最完整（message/agent_thought/reasoning_chunk/node_started/agent_log…），"一个 SSE 端点+type 分流"的事件契约设计最值得参照——§1.4 的 stage/token/thinking 分事件与之同构。
- **open-webui**：Citations+CitationModal 即引用 UI 最小集；StatusHistory 证明"阶段状态=事件数组渲染"足够轻。反差：socket.io 全家桶对单人作品集过重，不采。
- **anything-llm**：独立 SourcesSidebar+SourceDetailView 的来源侧栏交互可抄；生成期 thinking 动画占位成本低效果好。
- **ragflow**：唯一 bbox 级先例，react-pdf-highlighter+pdf.js 路线证明单人可维护；引用[n]→预览页内定位联动抄其交互（库本身仍不采，见 R8）。
- **ai-chatbot**：ai-elements/reasoning 折叠思考面板、resumable-stream 断线续流——前者佐证 K4 三态，后者 M4 不采（单次问答流语义，刷新重问即可，R3 已定）。
- **QAnything**：结构最像 M4 目标（SSE+引用弹窗→PDF 预览链路完整）但 2026-09 起停更——只抄交互不依赖。
- **private-gpt**：已转型 API 层、UI 降级为演示——启示：**服务与 UI 解耦，README/API 契约先行**（M4 的契约测试 K10 与此同旨）。
- **kotaemon**：引用+相关性评分小字值得抄（→ K5 侧栏卡片附融合分）；已停更（pushedAt 2026-07）。

### 7.4 来源清单（C 线，2026-11-12 实抓）

| # | 来源 |
|---|---|
| [C1] | ungh.cc/repos/{12 项目} JSON——星标数与默认分支（全部实抓） |
| [C2] | ghfast.top/…/ragflow/main/web/package.json——React18+Vite、eventsource-parser、react-pdf-highlighter |
| [C3] | ghfast.top/…/dify/main/web/package.json——Next、socket.io-client、react-pdf-highlighter |
| [C4] | ghfast.top/…/dify/main/web/service/base.ts——ssePost/handleStream 解析 data: 行；reasoning_chunk/node_* 事件 |
| [C5] | ghfast.top/…/open-webui/main/package.json——Svelte5、socket.io-client、eventsource-parser、pdfjs-dist |
| [C6] | ungh open-webui main 文件清单+正则提取——Citations.svelte/CitationModal/CitationsModal/StatusHistory |
| [C7] | ghfast.top/…/anything-llm/master/frontend/package.json——React+Vite、fetch-event-source |
| [C8] | ungh anything-llm master 文件清单+正则提取——Citation/SourcesSidebar/SourceDetailView/thinking-animation.webm |
| [C9] | ghfast.top/…/FastGPT/main/projects/app/package.json——Next、fetch-event-source |
| [C10] | ungh FastGPT main 文件清单——document/content/guide/chat/quoteList.mdx |
| [C11] | ghfast.top/…/MaxKB/v2/ui/package.json——Vue3+Element Plus+pdfjs-dist、无 SSE 库 |
| [C12] | ghfast.top/…/QAnything/qanything-v2/front_end/package.json+ungh 文件清单——Vue3、fetch-event-source、Source/PdfView.vue、ChatSourceDialog.vue |
| [C13] | ghfast.top/…/onyx/main/web/package.json——Next16、pdfjs-dist、react-pdf |
| [C14] | ghfast.top/…/kotaemon/main/README.md——Gradio；in-browser PDF viewer with highlights；PDF_JS 可选 |
| [C15] | ghfast.top/…/private-gpt/main/README.md——API 层定位、Workbench UI、messages API streaming、retrieval with citations |
| [C16] | ghfast.top/…/vercel/chatbot/main/package.json+ungh main 文件清单——ai v7、resumable-stream、message-reasoning.tsx、ai-elements/reasoning.tsx |
| [C17] | ghfast.top/…/Verba/main/frontend/package.json——Next14、react-pdf/renderer |
| [C18] | ghfast.top/…/dify/main/README.md——产品定位 |

> 失败路径注记：ungh 单文件端点 302→raw.githubusercontent.com（本机 DNS 拦截+工具不跟随跨域重定向），原始文件一律走 ghfast.top；open-webui package.json 首次 ghfast 429 限流重试成功；Onyx/MaxKB/Verba 流式细节、各项目思考流具体渲染未逐文件取证者均标〔未核实〕。

## 8. 交互与协议深挖（D 线，2026-11-12——三题全部当日实抓核实）

### 8.1 RAGFlow 引用交互与 v1.0 现状 [D1][D2]

- main=v1.0.0（2026-11-06 GA：Go 全量重写 + 全新 Agentic Chat，取代原 Low/Medium/High/Ultra 思考档；聊天历史存 prompt/token 用量/执行时间；消息列表虚拟化 #21790）。
- web 依赖实抓：`react-pdf-highlighter ^6.1.0`、`eventsource-parser ^1.1.2`、zustand、react-resizable-panels、react-markdown、Vite。
- 组件级交互流〔未核实〕（v1.0 主权重写致旧路径失效、目录树 API 截断）；依赖佐证的典型流：回答内引用标记 → Dialog/侧栏打开 PDF 预览 → react-pdf-highlighter 按 positions（页码+矩形数组）bbox 高亮 → 文档级来源聚合——与 runbook K5 同型。
- 可借鉴：①eventsource-parser 手工解析 fetch 流（不用原生 EventSource，兼容 POST+鉴权头）；②positions 数据形态可直接参考；③引用/用量/耗时随消息持久化回显。

### 8.2 思考面板三态实现惯例 [D3]–[D9][D11]

**vercel/ai-chatbot `ai-elements/reasoning.tsx`（全逻辑实抓）**：
- 三态：流式自动展开（`defaultOpen ?? isStreaming`）→ 结束 1s 后自动折叠（AUTO_CLOSE_DELAY=1000，可再展开）→ 历史态标题 "Thought for N seconds"（duration=ceil(ms/1000) 前端计时）。
- 触发器：思考中=Shimmer "Thinking..."；内容区限高 200px 滚动+流式自动滚底+暗色小字；**纯等待期（尚无任何 part）显示 "Waiting..."——与思考态分层**。
- 协议：reasoning 是独立消息 part（state:"streaming"），多 part 合并渲染。
- OpenWebUI：reasoning 以 `<details type="reasoning" done duration>` 块嵌在 content 里流式输出，marked 扩展解析（rAF 节流重解析）；复制/编辑时剥离。三态渲染细节〔未核实〕。
- AI SDK 官方：reasoning-start/delta/end 为一等 part，与 text 平级。
- → runbook K4 落地：默认态（无 reasoning）不渲染+stage 期 Waiting 占位；流式态首条 reasoning 即自动展开+Shimmer+限高滚底；完成态 1s 自动折叠"已思考 N 秒"可回看；**reasoning 走独立增量事件**（一等 part 惯例）。

### 8.3 SSE 事件对照与契约校验 [D11]–[D16]

| 维度 | Dify | FastGPT | AI SDK |
|---|---|---|---|
| 载体 | data 行 JSON 内 event 字段 | SSE event 字段+类型化 data | data 行 JSON 内 type 字段 |
| 文本 | message/agent_message 增量 | answer（OpenAI chunk 形态） | text-start/delta/end |
| 思考 | agent_thought（legacy agent） | 复用 answer，data 带 reasoning_content | reasoning-start/delta/end |
| 来源/引用 | 无专用流事件，message_end 汇总 | flowResponses 尾部一次发全 | source-url/document 整条 part |
| 结束 | message_end(+workflow_finished) | answerStop(finish_reason)→data:[DONE] | finish part→data:[DONE] |
| 错误 | error 事件（status/code/message） | error 事件 | error part |
| 心跳 | ping 首帧+约 10s（event:ping 无 data） | 〔未核实〕 | ping keep-alive |

**对 §1.4 草案的三条校验**：
1. **一致**：token≈text-delta/answer 增量；thinking 独立事件有 AI SDK 一等 part 先例（FastGPT 复用 answer 为另一派，不采）；error 三家必有且结构化（对齐 Dify 的 code/message，脱敏）；done≈message_end/finish，挂 usage/finish_reason 的惯例我们 §1.4 已具备。
2. **采纳**：①reasoning 增量补独立事件（§1.4 只有 thinking 状态事件、缺思考文本通道，而 R5 意图是流式灰字——runbook 3.1 冻结为 §1.4 超集）；②stage 附可读名 detail（步骤级先例：FastGPT flowNodeStatus、AI SDK start-step/finish-step），各段耗时前端按事件到达差实时显示、权威值随 done.timing；③心跳已有（sse-starlette ping=15s，Dify 10s 同量级）。
3. **sources/citations 拆分正确**：成熟项目均不逐 token 发引用——FastGPT 尾部一次发全、Dify 挂 message_end、AI SDK source part 整条非增量；我们 sources 先行（侧栏即时可点）+citations 生成完发终版，与三家兼容且体验更优。

### 8.4 来源清单（D 线，2026-11-12 实抓；GitHub 原始文件均经 ghfast.top 代理）

| # | 来源 |
|---|---|
| [D1] | ragflow main web/package.json（react-pdf-highlighter/eventsource-parser 等） |
| [D2] | ungh ragflow releases/latest（v1.0.0 GA 2026-11-06） |
| [D3]–[D7] | open-webui main：ResponseMessage.svelte / ContentRenderer.svelte / marked citation-extension.ts / extension.ts / Markdown.svelte |
| [D8][D9] | vercel/chatbot main：components/ai-elements/reasoning.tsx / components/chat/message.tsx |
| [D10] | vercel/chatbot main：components/chat/data-stream-handler.tsx |
| [D11] | ai-sdk.dev/docs/ai-sdk-ui/stream-protocol（reasoning-start/delta/end 一等 part） |
| [D12][D13] | dify-docs main：api-reference/guides/streaming.mdx / chat.mdx |
| [D14]–[D16] | FastGPT main：packages/global/core/workflow/runtime/{constants,sse}.ts、projects/app/src/pages/api/v1/chat/completions.ts |

> 失败路径：ungh 文件端点 302→raw.githubusercontent（DNS 拦截不可跟）、jsdelivr 报包超 50MB、sourcegraph 403、RAGFlow 组件路径探测 404（v1.0 重写）——message_end 的 metadata 细节、OpenWebUI 思考三态渲染细节、RAGFlow 组件级引用流程标〔未核实〕，未编造。

## 9. 论文库调研（E/F 线，2026-11-12——「上传入库+树状分类」需求专项）

> 动机：新增论文库功能（UI 上传 PDF→后台入库→立即可检索；树状分类目录）立项前，对 dify(161k★)/ragflow(94k★)/open-webui(158k★)/FastGPT(30k★)/MaxKB(23k★)/anything-llm(68k★) 的**上传管线**与**知识库组织 UI** 做源码级横评。RAGFlow 1.0（2026-11-06 GA）后端重写为 Go+NATS，经典 Python 架构证据取 v0.27.2 tag。

### 9.1 E 线：上传与入库管线 [E1]–[E15]

- **上传接口**：五家全部 multipart 直传，"先落盘建记录、同步返回、再异步解析"。dify 另有 `GET /files/upload` 把大小/批量上限下发前端预检；MaxKB 限 100MB；大小/扩展名校验放上传口同步 4xx，解析失败放任务侧。
- **任务模型**：dify=celery+Redis（beat 扫描 stalled 恢复）；ragflow v0.27=独立 task_executor 消费 Redis Stream 消费组（未 ack 自动重投）；FastGPT=Mongo 行即队列（lockTime 抢锁+retryCount 3 次+TTL）；MaxKB=celery+celery_once 防重入；**open-webui=FastAPI BackgroundTasks 进程内后台——五家唯一不用外部队列，与 DocLens 体量同款**。进度反馈全部前端轮询查库（open-webui 另有 1s 查库 SSE 端点），无一家用 WS。
- **状态机**：dify 最细（waiting→parsing→cleaning→splitting→indexing→completed/error，轮询按 batch 返回 completed_segments/total_segments+error 文本+各阶段时间戳）；ragflow=progress∈[0,1]+progress_msg 逐条（-1 即失败，支持取消）；open-webui=pending→processing→completed/failed。
- **解析架构**：解析器注册表+统一流程（ragflow FACTORY 十余种解析器同签名；**MinerU 是 ragflow 内置 PDF 解析器且超时可配**——佐证 mineru-kit 桥接复用）；最耗时=解析（OCR/版面）与 LLM 增强，故全部异步化。
- **校验结论**：①"任务状态落库+轮询"成立；②采纳 batch 聚合号（一次轮询覆盖本次上传全部文档）+状态对齐 dify 粒度（queued/parsing/indexing/completed/error+chunk 计数+error 文本）；③进程内后台的"重启丢任务"用**启动扫描**兜底（超阈值的 processing 任务标 failed），不引 celery；④上传校验与解析解耦。

### 9.2 F 线：知识库组织与树状 UI [F1]–[F15]

- **数据模型**：真树自引用 2/5——**FastGPT 最佳先例**（分类与库同表 type 区分 folder/dataset，parentId+**ancestorIds 物化路径**加速子树查询+可配置 maxFolderDepth）；open-webui（folder 表 parent_id 无外键，移动做环检测+"不能移入自身/子树"，折叠状态持久化）。平铺 3/5——AnythingLLM workspaces（slug 唯一）、Dify datasets（无分组字段，靠标签）、RAGFlow 卡片流。
- **组织形态**：**顶层清一色平铺**（卡片流/表格+搜索筛选），树只出现在下钻层——FastGPT 点文件夹换 URL 逐层下钻+面包屑+文件夹侧卡（改名/移动/批量）；open-webui 对话文件夹树在侧栏（可折叠、展开状态入库）。移动交互用弹窗/按钮而非拖拽（FastGPT）。
- **状态 UI（RAGFlow 范式最完整）**：文档页表格列=复选框批量/名称/上传时间/启用开关/chunk 数/解析器/状态/操作；状态七态枚举，RUNNING 显示进度条+百分比且可点开解析日志弹窗，FAIL/DONE 给重解析按钮（弹确认框），RUNNING 可取消（整行置灰遮罩）。
- **上传交互**：**入口在容器内部**——open-webui 知识库详情页整页拖拽+按钮（本地/URL/文本/整目录），上传目标=当前浏览目录（**无需弹窗选分类**）；上传项在列表顶部显示 uploading→processing 状态机+toast。
- **校验结论**：①t_category 自引用树成立（FastGPT 先例：加 ancestor_ids 冗余+环检测+层级上限常量）；②顶层用平铺列表、树管导航——**"分类树侧栏+主区论文列表+面包屑"是合理落位**；③状态字段=status 枚举+progress+error 文本，UI 照 RAGFlow 范式（徽标+进度条+重试+日志）；④上传入口放"当前分类上下文"，不弹窗选分类；⑤点击论文复用 PDF 面板合理（条目就地查看是共识）。

### 9.3 来源清单（E/F 线，2026-11-12 实抓；GitHub 原文均经 ghfast.top 代理，RAGFlow 另经 Gitee 镜像）

| 线 | 来源 |
|---|---|
| E 线 | [E1–E5] ungh 仓库元信息；[E6] dify api/tasks/document_indexing_task.py；[E7] dify api/controllers/console/files.py；[E8] dify api/controllers/service_api/dataset/document.py（create-by-file/batch/状态机原文）；[E9] ragflow rag/svr/task_executor.py@v0.27.2（Redis Stream/FACTORY/进度/心跳自愈/80min 超时）；[E10] MaxKB apps/dataset/serializers/document_serializers.py；[E11][E12] FastGPT dataset training/collection schema.ts；[E13] open-webui backend/open_webui/routers/files.py（BackgroundTasks/状态字段/SSE 状态端点）；[E14] open-webui routers/knowledge.py（pending 中断重试）；[E15] dify api/extensions/ext_celery.py（beat sweep） |
| F 线 | [F1][F2] open-webui models/folders.py+routers/folders.py（parent_id/环检测/展开持久化）；[F3][F4] anything-llm prisma schema+workspace.js（平铺/slug）；[F5][F6] dify datasets 列表页两版（卡片网格/enable_knowledge_fs）；[F7] dify api/models/dataset.py（无分组字段/状态机）；[F8] FastGPT dataset/schema.ts（parentId+ancestorIds+type+maxFolderDepth）；[F9][F10] open-webui Knowledge.svelte+KnowledgeBase.svelte（列表徽标/库内目录树/上传状态机）；[F11] ragflow datasets 列表页；[F12]–[F14] ragflow use-dataset-table-columns/parsing-status-cell/reparse-dialog+process-log-modal（七态+进度条+取消/重解析）；[F15] FastGPT dataset/list/index.tsx（下钻/面包屑/文件夹侧卡/批量移动） |

> 〔未核实〕FastGPT 队列消费器循环、AnythingLLM 前端侧栏形态、Dify/RAGFlow 上传控件视觉形态、message_end metadata 细节等——均不影响结论。

## 5. 待人工核实

1. A/B 两线均已回填（2026-11-11）。
2. 未能核实项〔不作实施依据〕——A 线：RAGFlow positions 坐标单位/顺序与前端组件路径（main 分支重构 + 文档未写明，本项目不依赖该格式）；Verba/AnythingLLM/OpenWebUI 仅特性级未源码核实；MinerU bbox 原点方向官方文档未明文（R7 对齐抽检即最终验证）。B 线：FastAPI SSE 教程正文与内置 EventSourceResponse 引入版本号（页面超时）；Starlette StreamingResponse 文档正文；NodeSource 可达性（已按网络限制推断不采用）；Vite proxy 对 SSE 的官方专门说明（无专节，仅 http-proxy-3 透传机制）；LobeChat/Open WebUI 的 reasoning 渲染细节（文档 404/源码未抓，Gradio 官方惯例已足佐证）；裸 pdfjs-dist `?url` 官方文档（react-pdf 已封装，够用）；火山方舟侧 reasoning_content 专页（docs.z.ai 已覆盖 GLM 系字段语义）。
3. bbox「左上原点」依据同页阅读顺序递增推断【实测 11 篇之一】+ MinerU 惯例；R7 的对齐抽检即为最终验证，不额外阻塞。
4. VS Code 端口转发在本机已可用（Remote-SSH 已打通）；ssh -L 手动隧道已实测连通——二选一即可，无需额外核实。

## 6. 来源清单

**B 线（工程实现，调研代理 2026-11-11 fetch 核实；github 经 ghfast.top 代理读取）**

| # | 来源 |
|---|---|
| [B1] | sse-starlette README https://github.com/sysid/sse-starlette （EventSourceResponse/ping=15s/断连检测/代理缓冲坑） |
| [B2] | FastAPI SSE 教程 https://fastapi.tiangolo.com/tutorial/server-sent-events/ （页面存在两处核实、正文超时） |
| [B3] | Vite server.proxy https://vite.dev/config/server-options.html |
| [B4] | @microsoft/fetch-event-source https://github.com/Azure/fetch-event-source |
| [B5] | z.ai 流式消息（官方） https://docs.z.ai/guides/capabilities/streaming （delta.content/reasoning_content 分离、usage 末 chunk） |
| [B6] | glm-5.3-flash 模型页（官方） https://docs.z.ai/guides/vlm/glm-5.3-flash （多模态/1M 窗口/thinking 仅 enabled） |
| [B7] | Gradio Chatbot（metadata 折叠思考面板/reasoning_tags） https://gradio.app/docs/gradio/chatbot |
| [B8] | npmmirror https://npmmirror.com/ ＋ n 的 N_NODE_MIRROR https://github.com/tj/n ＋ Debian nodejs 版本 https://packages.debian.org/bookworm/nodejs |
| [B9] | FastAPI app.frontend（dist/SPA fallback） https://fastapi.tiangolo.com/tutorial/frontend/ |
| [B10] | react-pdf（worker 同模块设置/cMaps/pnpm hoist/React19+Node22.13） https://github.com/wojtekmaj/react-pdf |
| [B11] | Chainlit 归档声明 https://docs.chainlit.io/get-started/project-status |
| [B12] | Gradio 活跃版本与 mount_gradio_app/流式支持（同 [B7] 文档域，6.31） |

**A 线（同类项目引用溯源与 PDF 高亮，调研代理 2026-11-11 fetch 核实）**

| # | 来源 |
|---|---|
| [A1] | RAGFlow web/package.json（react-pdf-highlighter@^6.1.0）https://github.com/infiniflow/ragflow/blob/main/web/package.json ；HTTP API reference（chunk positions）https://github.com/infiniflow/ragflow/blob/main/docs/references/http_api_reference.md |
| [A2] | Kotaemon pdf_viewer.js / citation_qa.py（文本匹配高亮，零坐标）https://github.com/Cinnamon/kotaemon/blob/main/libs/ktem/ktem/assets/js/pdf_viewer.js |
| [A3] | Onyx citations 特性文档（编号→document_id，无页级定位）https://github.com/onyx-dot-app/onyx （.agents/feature-map/components/citations.md @6bac4e01） |
| [A4] | react-pdf-highlighter（v8-rc 停更/ScaledPosition/scrollTo）https://github.com/agentcooper/react-pdf-highlighter ；pdf.js display_utils（PDF_TO_CSS_UNITS/viewport）https://github.com/mozilla/pdf.js |
| [A5] | MinerU content_list normalize_bbox（0-1000 整数框）与 structured-content 文档 https://github.com/opendatalab/MinerU |
| [A6] | pdf.js fetch_stream（Range 回退整文件）https://github.com/mozilla/pdf.js ；Starlette staticfiles（无 Range/206）https://github.com/encode/starlette |
