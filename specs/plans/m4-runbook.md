# M4 服务+UI Runbook

> **状态：实现中（2026-11-12 增补范围实现完毕，验收收官走 S3+S4 双审+tag m4）** ｜ slug：`m4-serving-ui` ｜ 依据：[主计划 §5 M4](doclens-multimodal-rag.plan.md)、[PRD FR-4.2/4.3、FR-5.1–5.4、S2](../prds/doclens-multimodal-rag.prd.md)、[m3-runbook](m3-runbook.md)（M3 产物即 M4 管线）、[m4 调研笔记](../research/m4-serving-ui-survey.md)（v1.4：R1–R12 + §1.4 契约 + §7–§11 五轮调研）、[m4-ui-mockup.html](../research/m4-ui-mockup.html)（前端布局蓝本）
> **输入观察项（2026-11-12 冒烟人工判定）**：① A 档 s01 空答案根因=max_tokens 被 reasoning 耗尽 → K7 空答案守卫（已实现）；② D 档当日 trace 被后续跑次覆盖 → 演示跑前备份纪律；③ MinerU LaTeX 数字内插空格 → 证据核验先去空白（对 M4 无代码影响，记录在案）。
> **实施进度（2026-11-12）**：4.0–4.7 全部完成并实测（SSE 事件序吻合契约/稳态 15.5s/图片附载 bug 顺手修）；4.9 登录门（argon2+JWT/session_stamp 全端吊销/限流，401 门实测）+4.10 模型反馈切换（/api/models 白名单/body.model 校验回退/done 带模型，kimi-k3 端到端实测）+4.8 论文库（8 表就绪/分类树 CRUD+环检测/dedup 409/去重守卫实测，全流程待真实新论文）——新增依赖 pwdlib/PyJWT/python-multipart 双端锁版；管理员密码随机生成入 .env 不入库。

---

## 1. 目标与验收标准（可执行验证）

| 验收项 | 验收方式 | 通过标准 |
|---|---|---|
| SSE 契约 | `tests/test_sse_contract.py`（TestClient + mock 管线） | 事件序列与 schema 断言全绿：stage(retrieve→rerank→assemble→generate) → sources 先于首 token → token×N → thinking 配对 → citations 在 finish 后 → done 收尾；error 事件字段脱敏 |
| 资产接口 | pytest + curl 冒烟 | `/api/docs/{doc_id}/pdf` 按 doc_id 回表取路径返回 PDF 流；`doc_id` 含 `../` 等恶意值 → 4xx（路径穿越守卫单测）；`/api/figure` 按 chunk_id 出图 |
| 前端手工验收清单 | 人工过目（R12，不上 JS 测试框架） | 5 项全过：①中文提问+英文提问均流式出答案；②思考状态可见（思考中→折叠面板）；③点击 [n] 引用 → PDF 打开对应页且 bbox 高亮框对齐；④不可回答题拒答话术正常展示（不卡死、不出编造答案）；⑤stage 步进条三段推进+各段耗时可见（FR-5.3） |
| bbox 对齐抽检 | 任选 2 篇第 1 页各 2 块（R7） | 高亮框与实际区域对齐（0–1 归一化 × 视口宽高换算复检通过） |
| 演示计时（S2/FR-5.2） | R6 计时协议：热启动（第二轮起计）、system prompt 限回答 ≤200 字、trace 时间戳（提交→正文首 token→流式完成→点击引用→高亮可见）+ 录屏叠加计时 | 全流程 ≤20s；超标则启用演示档降级开关（max_tokens 从紧/回答更短）复测并记录 |
| 空答案守卫 | pytest 单测（mock 生成返回空 content） | 触发一次重试（max_tokens 上调），仍空 → REFUSAL_TEXT + refused=True + trace 标记 empty_content（2026-11-12 观察项①闭环） |
| 安全五条（R10） | 单测 + 配置检视 + S4 复查 | ①路径穿越守卫（doc_id/figure 全部回表映射，realpath 包含性校验）；②uvicorn bind 127.0.0.1；③不开 CORS 中间件；④`VITE_*` 零秘密（前端仅同源 /api）；⑤SSE 事件/日志/trace 不含 key（沿 M2 纪律） |
| 交付形态（R1） | Windows `npm run build` → dist 入库 → push server → 容器 uvicorn 托管 | 浏览器经 SSH 隧道 `localhost:8000` 单进程单命令打开完整应用（FR-7.1 同构预演） |
| 回归 | `python -m pytest -q` 双端 | 170 存量 + 新增全绿；`query_cli --smoke` 不回归 |
| 里程碑 | commit（每步一个）+ `git tag m4` + push 双端 | 双端同步 |

## 2. 现状调查（2026-11-12 实测）

| 项 | 现状 | 结论 |
|---|---|---|
| M3 管线 | `doclens/retrieve`（hybrid/rerank/router）+ `doclens/generate`（context/vlm/citations/fallback）+ `query_cli.py --profile/--smoke` + `trace.py`；vlm.py 已预留 stream 参数（M3 非流式为主） | 管线成熟；M4 做"事件化编排 + SSE 编码层"，不重写管线 |
| 依赖 | fastapi==0.162.2、uvicorn[standard]==0.54.0、sse-starlette==3.7.0 已在 M0 锁版 | 服务端零新增 Python 依赖（前端依赖走 npm，另一侧） |
| 前端 | `web/` 不存在（全新）；容器无 Node（apt=10.19 不可用）【实测】；Windows Node v26.3.0 + npm 11.16.0 在位 | R1：Windows 开发+构建，容器不装 Node |
| 坐标 | t_chunk bbox 原生 0–1 归一化 [x0,y0,x1,y1]、左上原点（M1 docstring+数据探针双证）；页码 M1 schema 1 起 = react-pdf pageNumber 1 起 | 高亮=百分比定位 div，链路闭合（G4/R7） |
| 拓扑 | 容器内 uvicorn bind 127.0.0.1:8000；Windows 侧浏览器不可直连 → `ssh -N -L 8000:127.0.0.1:8000`（端口 8009 免密）或 VS Code 端口面板（R2） | 演示访问路径写死入验收 |
| 主计划过期点 | §9 `cd web && npm i -g pnpm && pnpm dev` 假设本地跑前端（修订⑥之前）；assets.py "PDF 页渲染+overlay"职责两可（G5） | R1 工具链改 Windows 路线 + R8 assets 定稿三件套；主计划补记放收官步 |
| .env.example | 无 VITE_ 变量；双端独立维护 | 前端零秘密（R10④）天然成立，保持 |

## 3. 技术方案（关键决策，R# = m4 调研修订号；C/D# = §7 高分项目对比）

| # | 决策 | 方案 | 被否方案与理由 |
|---|---|---|---|
| K0 | **API 面定稿**（R3/R4/R8/G5） | `POST /api/query`（SSE，契约 §1.4 冻结；sources 事件含 `routes` 各路命中分数字段，供 FR-5.3 并列展示）；`GET /api/docs`（文档清单，侧栏用）；`GET /api/docs/{doc_id}/pdf`（PDF 文件流，doc_id→t_doc 回表映射）；`GET /api/figure/{chunk_id}`（图片，payload.image_path 回表）。**主计划文件树的 `/api/page` 不做**（R8：浏览器端 pdf.js 渲染，无需独立 overlay 接口）；assets.py 职责=三件套（PDF 流/figure/引用数据随 SSE 下发） | 后端渲染页面图（Kotaemon 老路）：丢文本选择+占存储；用户传路径：穿越风险；独立 overlay 接口：与 sources 事件重复 |
| K1 | **事件化编排+SSE 编码层**（R3/§1.4） | `query_cli.run_query` 的编排逻辑抽为共享管线（模块级函数 + 可选 `on_event` 回调吐事件载荷 dict）：CLI 传打印回调、api.py 传 SSE 编码回调——**单一编排源，杜绝契约双侧漂移**；api.py 用 sse-starlette `EventSourceResponse` 包装 async 生成器，ping=15s；断线不续传（刷新重问）；`Cache-Control: no-cache`，该路由不加 GZip | 复制一份编排逻辑给服务端：契约漂移温床；手写 StreamingResponse：格式化/ping/断连全要自制，不划算；WebSocket：单向推送场景用不上双向通道，且 fetch-event-source 生态成熟（C/D 线佐证） |
| K2 | **前端工具链**（R1） | 开发期=Windows Node v26 跑 `npm run dev`（Vite dev server，proxy `/api`→`http://127.0.0.1:8000`，经 SSH 隧道达容器 uvicorn，热更新）；交付期=Windows `npm run build` → **dist 入库（gitignore 例外，刻意为之）** → push server → FastAPI `app.frontend("dist")` 托管。**用 npm 不用 pnpm**（Windows npm 在位零安装；npm 扁平化 node_modules，免 pnpm 的 pdfjs-dist hoist 配置） | 容器装 Node（apt 版本不可用；npmmirror 二进制为备选）：多一套工具链维护；CDN 免构建：丢工程分量；pnpm：多一层全局安装+hoist 配置，小项目无收益 |
| K3 | **前端栈**（R8/B10） | Vite + **React 19** + **react-pdf 11**（worker 同模块设置 `GlobalWorkerOptions.workerSrc=new URL(...)`；vite-plugin-static-copy 复制 cMaps/standard_fonts——本期英文语料影响小但一次配好，财报泛化包直接受益）+ **自绘 overlay**（0–1 归一化 → 百分比定位 div：`left=x0×100%; top=y0×100%; width=(x1−x0)×100%; height=(y1−y0)×100%`）+ **@microsoft/fetch-event-source** 消费 SSE（POST JSON + 流式回调；anything-llm/QAnything 直用、FastGPT 用其 fork，§7.2；备选=eventsource-parser+手写 fetch，RAGFlow/OpenWebUI 同款惯例 §8.1/8.2）。样式=**以 m4-ui-mockup.html 的 CSS 为蓝本手写**，不引 Tailwind/UI 框架 | react-pdf-highlighter 6.1（RAGFlow 同款）：实质停更+pdfjs-dist 2.16 老+React19 peer 冲突；后端转图：见 K0；Tailwind：新增依赖面，mockup 样式已够 |
| K4 | **思考流三态 UI**（R5/§3.3/§8.2 D 线佐证） | 三态照抄 ai-chatbot reasoning.tsx 成熟范式（§8.2 全逻辑实抓）：**流式态**=首条 reasoning 增量即自动展开，标题 Shimmer"思考中…"，内容限高滚动+自动滚底；**完成态**=thinking(done) 后 1s 自动折叠为"已思考 N 秒"，可再展开回看；**等待态**=stage 期尚无 reasoning 时显示 Waiting 占位（与思考态分层，§8.2 惯例）。reasoning 走**独立增量事件**（对齐 AI SDK 一等 part 惯例，见 3.1 冻结契约），绝不入对话历史、绝不混入答案正文（M3 双字段分流语义延续，token 事件只透传 delta.content） | reasoning 直接拼接进答案：M3 冒烟已实证泄漏事故；不显示思考状态：强制思考模型下演示画面卡死 10s+；把 reasoning 塞进 token 事件：前端无法区分正文与思考 |
| K5 | **引用交互**（R4/C·D 线佐证） | sources 事件先于首 token → 引用侧栏即时可点（Source N + kind 图标 + snippet + doc/page）；答案内 [n] chip 点击 → 右栏切换 PDF 视图并 scrollIntoView 对应页 → bbox 高亮框 + 短暂脉冲动画；citations 事件（finish 后）做终版校验标记——无效 n 的 chip 置灰+"降级"角标（不静默删，M3 语义延续）；snippet 同源高亮（Kotaemon 式文本匹配仅在 snippet 小文本上做，成本低不涉坐标） | 等答案出完才出引用侧栏：浪费流式等待期，且 sources 数据组装期已定（m3 调研 R11）；无 bbox 直接页级跳转：丢本项目核心差异化 |
| K6 | **检索可视化并入主前端**（FR-5.3/R9） | stage 步进条（检索→重排→生成，各段 elapsed_ms）常驻；"检索细节"可展开面板=来源卡片上并列展示各路命中分（dense_text/dense_image/bm25，来自 sources.routes 字段）+ 融合序 vs 重排序标记。开发期验收主力仍是 `query_cli --smoke` | 独立 Gradio 界面承担可视化（原 4.3）：与主前端重复建设；Perplexity 式复刻：无开源先例〔未核实〕，自绘步进条成本极低 |
| K7 | **空答案守卫+错误面**（2026-11-12 观察项①；R13 语义） | 共享管线在生成完成后检 `content.strip()`：空 → 重试一次（max_tokens 上调一档，仅此一次）→ 仍空 → REFUSAL_TEXT + refused=True + trace 标记 `empty_content`；前端拒答/错误统一展示态（error 事件 message 脱敏）；CLI 与 SSE 两路同时受益（守卫在共享管线层） | 只在 SSE 层守卫：CLI --smoke 依旧裸奔；静默重试多次：成本不可控 |
| K8 | **安全五条前置**（R10/G7） | ①文件接口一律 doc_id/chunk_id 回表映射，绝不接受用户传路径，realpath 包含性校验 + 单测；②uvicorn `--host 127.0.0.1`；③不开 CORS 中间件（dev=Vite proxy 同源、交付=同源静态托管）；④VITE_ 零秘密；⑤SSE/日志/trace 脱敏沿 M2 纪律。S4 复查在收官前强制（Web 面首开） | 安全验收留到 S4 事后补：m2 security A01 已预告"服务化时复查"，五条直接进验收 |
| K9 | **4.3 Gradio 降级为可选尾项**（R9/PRD P1 汇总） | 主推**砍单**：FR-5.3 已并入主前端（K6）、调试主力=--smoke；若工期富余，`mount_gradio_app` 挂 `/gradio` 复用共享管线（成本很低）作 P1 加分位，放收尾可选步 | 保留为必做：与主前端重复；Chainlit：已归档停维护排除 |
| K10 | **测试策略**（R12） | 后端：SSE 契约测试 1 条（TestClient+mock 管线断言事件序与 schema）+ 守卫/穿越/figure 单测 + 170 存量回归；前端：**手工验收清单 5 项**（§1），不上 JS 测试框架；契约变更=改 §1.4 + 同步双侧测试，一次一处 | JS 测试框架（vitest/testing-library）：作品集体量不值；纯手工不测契约：接口边界恰是 M3/M4 交接面，必须有自动化断言 |

### 3.1 实施细则

- **SSE 事件时序**（**冻结版=§1.4 超集**：+sources.routes 细化、+reasoning 增量事件、+stage.detail 可读名；校验依据 §8.3）：`stage{stage,detail}`（各阶段开始时发；各段耗时前端按事件到达差实时显示，权威值随 done.timing） → `sources{sources[],routes,profile}`（assemble 完成即发，先于首 token） → `stage(generate)` + `thinking{status:started}` → `reasoning{text}`×M（灰色思考流，仅前端临时态不入历史）+ `token{content}`×N + `thinking{status:done,elapsed_ms}` → `citations{cited[],invalid[]}` → `done{finish_reason,usage,timing,trace_id}`；错误任意点发 `error{code,message}`（结构化脱敏，对齐 Dify 惯例 §8.3）后关流。reasoning_content 不进 token 事件（只落 trace + 前端临时态）。
- **空心跳**：sse-starlette ping=15s（检索+重排最长 ~7s，覆盖得住）；代理缓冲坑（nginx/CF）本项目拓扑不经过，响应头仍带 `Cache-Control: no-cache`。
- **PDF 面板**：react-pdf `<Document file="/api/docs/{doc_id}/pdf">` 按需渲染页（引用跳页 scrollIntoView）；overlay 层 pointer-events:none 防挡文本选择；页码 1 起对齐（M1 schema）。
- **dist 入库纪律**：只在 Windows 侧构建（单源），容器永不 build；dist 变更随功能 commit（M6 README 写明该交付形态）。
- **演示日 checklist**（入 runbook 验收）：① 隧道预检（ssh -L 8000 存活）；② rerank 缓存预热（演示题先跑一遍）；③ trace 备份（copy data/traces → data/traces-demo-backup，观察项②）；④ 降级开关参数备好（演示档 max_tokens）。
- **多轮追问（FR-4.5）=P2 非目标**；单轮语义，每问独立。

## 4. 变更清单（文件级）

| 动作 | 文件 | 职责 |
|---|---|---|
| 修改 | `scripts/query_cli.py` | 编排逻辑抽为共享管线函数 + on_event 回调（K1）；空答案守卫接入（K7） |
| 修改 | `doclens/generate/vlm.py` | 流式生成支持（async 迭代器吐 delta.content；reasoning 分流不变）（K1/K4） |
| 新增 | `doclens/serve/__init__.py`、`doclens/serve/api.py` | FastAPI 应用：/api/query(SSE)、/api/docs、/api/docs/{doc_id}/pdf、/api/figure/{chunk_id}、app.frontend("dist")（K0/K8） |
| 新增 | `doclens/serve/assets.py` | PDF 流/figure 的回表映射与 realpath 包含性校验（K0/K8） |
| 修改 | `doclens/config.py` | serve 相关常量（bind/port/演示档参数位） |
| 新增 | `web/`（package.json、vite.config.js、index.html、src/：App/ChatPane/ThinkingPanel/SourceSidebar/PdfPane/StageBar/ScorePanel/api.js + styles.css） | 演示前端（K3–K6；布局蓝本=m4-ui-mockup.html） |
| 新增 | `web/dist/`（构建产物，gitignore 例外入库） | 交付形态（K2） |
| 新增 | `tests/test_sse_contract.py`、`tests/test_serve_assets.py` | 契约/资产/守卫单测（K7/K10） |
| 修改 | `requirements.txt`（如需 pin 新传递依赖）、`.gitignore`（dist 例外）、`CHANGELOG.md` | 工程卫生 |
| 修改 | 主计划 §9 命令与文件树注释（/api/page 删除、assets 职责、dist 交付）（收官补记） | R1/R8 落地回写 |

## 5. 分步任务（执行顺序）

| 步 | 任务 | 验收 | 依赖 |
|---|---|---|---|
| 4.0 | **共享管线事件化**：编排抽取+on_event 回调+vlm 流式+空答案守卫（K1/K7）+ 单测 | pytest 全绿（含守卫新用例）；`query_cli --smoke` 行为不回归 | 无 |
| 4.1 | **api.py + assets.py**：SSE 端点（契约实现）+ docs/pdf/figure 三资产接口 + 安全五条落码（K0/K8） | curl 冒烟出事件流；穿越单测绿 | 4.0 |
| 4.2 | **SSE 契约测试**：TestClient+mock 管线断言事件序与 schema（K10） | 契约测试绿（这一步冻结 §1.4） | 4.1 |
| 4.3 | **web 脚手架+接流**：Vite+React19 初始化、proxy、fetch-event-source 接 SSE、对话区+思考三态+引用侧栏+stage 条（K2/K4/K5 前半） | 手工清单①②⑤过；流式下首 token 即时可见（proxy 透传验证） | 4.2 |
| 4.4 | **PDF 面板+bbox 高亮**：react-pdf 集成+overlay+引用点击跳页+snippet 高亮（K5 后半） | 手工清单③过；bbox 对齐抽检（2 篇×2 块）过 | 4.3 |
| 4.5 | **检索可视化**：ScorePanel（sources.routes 并列分数+融合/重排序标记）（K6） | 手工清单⑤完整过（含分数并列） | 4.3 |
| 4.6 | **集成验收**：手工清单 5 项全过+≤20s 计时（R6 协议）+安全五条检视+降级开关实测 | §1 验收表全过 | 4.4/4.5 |
| 4.7 | **交付形态**：npm run build → dist 入库 → push server → 容器托管 → 隧道浏览器验证 + 演示日 checklist 演练 | 单命令+隧道全流程通；dist 在容器可服务 | 4.6 |
| 4.8 | **论文库（v2 方案，调研 §9）**：t_category（FastGPT 式树：自引用+ancestor_ids+环检测+层级上限）+t_ingest_task（dify 式状态机 queued/parsing/indexing/completed/error+chunk 计数+error 文本+batch 聚合号）+t_doc.category_id/可空 user_id 预埋；upload/tree/task/categories CRUD API（上传口同步校验大小/扩展名）；入库管线单篇化（mineru-kit 桥接+ingest 抽函数）；启动扫描兜底；前端：顶栏对话/论文库视图切换+分类树+论文表格（RAGFlow 式状态徽标/进度条/重试/日志）+上传+点击论文复用 PdfPane | 上传→自动入库→立即可问全链路通；树 CRUD 通；穿越/越权单测绿 | 4.6 |
| 4.9 | **登录门 L0（调研 §10）**：单管理员 argon2（pwdlib）+JWT HS256（FastAPI 官方范式）；POST /api/auth/login+get_current_user Depends 全路由一把门（/api/health、/web、登录本身除外）；所有新表预埋可空 user_id；前端登录页+token 存储+401 跳登录 | 未登录访问 /api/query→401；登录后全功能可用；弱密码/限流单测 | 4.6 |
| 4.10 | **模型反馈+切换（调研 §11）**：GET /api/models（config 白名单+vision/thinking 能力标记+当前默认）；query body 加 model 覆盖位（服务端白名单校验+非法回退默认）；选择器入输入框工具栏（ai-chatbot 范式）+cookie 持久化默认+答案 meta 显示所用模型 | 模型切换即时生效；非法模型回退单测绿；缓存按模型隔离验证 | 4.9 |
| 4.8a | （可选 P1）Gradio mount /gradio | 可用即可 | 4.6 |
| 收尾 | CHANGELOG + tag m4 + 主计划补记（§9 命令/文件树/assets 职责）+ S3 审查 + S4 安全复查（强制） | 双端同步 | 4.7 |

## 6. 测试策略（普通实现，延续 M2/M3 决策）

- 纯逻辑单测：路径映射与包含性校验、空答案守卫判定表、SSE 事件序列 schema、figure 回表；管线事件回调的载荷断言。
- 契约测试 = M3/M4 接口边界的自动化锁（mock 管线，不真调 LLM）。
- 集成走容器/隧道真实链路（uvicorn+Vite proxy+浏览器），前端以手工验收清单为准（R12）。
- 新增逻辑覆盖率 ≥80%（纯逻辑部分）；S3 代码审查+S4 安全复查收官强制（Web 面/文件服务/外部 API 代理=敏感）。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| 思考期 5–15s+ 演示冷场 | 思考三态+stage 条可见（K4/K6）；录屏脚本设计把等待期变成"讲解检索细节"时段 | 演示档降级开关（max_tokens 从紧/回答更短，R6） |
| ≤20s 超标 | R6 计时协议早暴露；rerank 缓存预热（稳态 <1s）；system prompt 限 200 字 | 演示档参数收紧复测并记录 |
| react-pdf/worker/cMaps 配置坑 | §3.5 细则照抄（B10）；4.3 首日先跑最小 <Document> 冒烟 | 退 react-pdf-highlighter 6.1 备选（记录在案） |
| Vite proxy 对 SSE 缓冲/断流 | http-proxy 透传机制（B3）；4.3 验收含"流式首 token 即时可见" | 直连 uvicorn 端口开发（隧道 8000→5173 改 8000 直访） |
| bbox 高亮对不齐（crop box/viewport 边缘） | R7 换算式+抽检兜底；百分比定位绕开原点翻转（§2.2） | 页级跳转保底（无 bbox 框仅跳页）记录降级 |
| 隧道断连/端口冲突 | 演示日 checklist（隧道预检）；VS Code 端口面板替代 ssh -L | 演示改容器内 curl+录屏兜底（极端） |
| dist 双端构建漂移 | 单源纪律（只 Windows 构建，K2） | 删 dist 重建（幂等） |
| 空答案复发（观察项①） | K7 守卫（重试一次+拒答兜底）+单测 | 无需回滚（纯增量守卫） |
| trace 被后续跑批覆盖（观察项②） | 演示日 checklist 备份纪律 | 已有 M5 归因口径兜底（trace_id 回放失败可重跑） |
| 成本 | 20 冒烟×6 档已有量级参照；M4 新增主要是开发期手工调试调用量，额度观察纪律不变（方舟控制台看余量） | 砍 K9 Gradio（P1） |

## 8. 敏感代码判定

**是（敏感）**：项目首个 Web 服务面——文件下载接口（路径穿越攻击面）+ 外部 API 代理（ARK key 全在后端进程）+ SSE 输出面（脱敏）+ 静态托管。实现完成后走 S4 安全专项复查（R10 五条前置进验收，复查验证）。

## 9. 执行命令

```bash
# —— 容器内（默认拓扑，/home/doclens/RAG）——
python -m pytest -q
uvicorn doclens.serve.api:app --host 127.0.0.1 --port 8000     # 服务（容器内直连 MySQL/Qdrant）
python scripts/query_cli.py --smoke                            # 管线回归不破

# —— Windows 开发（R1/R2 路线）——
# ① 隧道（或 VS Code 端口面板加 8000）：
ssh -N -L 8000:127.0.0.1:8000 root@10.14.50.123 -p 8009
# ② 前端 dev（热更新）：
cd web; npm install; npm run dev        # Vite proxy /api → http://127.0.0.1:8000
# ③ 浏览器：http://localhost:5173

# —— Windows 构建 + 容器托管交付（单进程单命令）——
cd web; npm run build                   # 产 web/dist（入库）
git add web/dist; git commit; git push server master
# 容器：uvicorn doclens.serve.api:app --host 127.0.0.1 --port 8000   # app.frontend("dist") 托管
# 浏览器（经 ① 隧道）：http://localhost:8000
```

---
## 确认门记录（S2 开始前填写）
- 批准时间：2026-11-12 13:33 (+08:00)
- 批准指令原文：「可以 开工吧」
- TDD：否（普通实现，延续 M2/M3 决策；质量保障走 S3 代码审查 + S4 安全复查 + 契约测试 + 手工验收清单）
- **增补批准（2026-11-12 19:30 前后）**：指令「123都做 保证质量」——三合一确认单（①论文库 v2=4.8、②登录门 L0=4.9、③模型反馈切换=4.10）全做；执行序=4.9→4.10→4.8（先立门避免返工）；B 决策点=初始 11 篇挂"未分类"；管理员密码=随机生成入 .env 不入库
