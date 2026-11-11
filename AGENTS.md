# AGENTS.md

本文件供 AI 编码助手在本仓库工作时自动读取。

## 用户沟通约定（最高优先级）

- **「下一步」锚点（每次收工时更新）**：本节末尾的 `Next Action:` 行是新会话的交接锚点——新对话读到这里就知道从哪继续，无需用户复述背景。
- 用户是**技术新手**：不要假设已掌握 Linux / SQL / Python 生态的常识，术语第一次出现用一句话解释。
- 每一步操作都说明四件事：**这条命令在做什么 → 为什么需要 → 预期看到什么输出 → 怎样算成功**。
- 命令整块给出、可直接复制粘贴；占位符（如 `<密码>`）要说明替换成什么、从哪来。
- 出错时：先安抚（容器环境踩坑很正常），再按顺序给定位步骤（先看哪个输出/日志），最后给修复命令。
- 全程中文交流。
- **收工口令**：用户说"收工/记录进度"时，执行三件事——① 更新下方 Next Action；② 补 CHANGELOG.md；③ commit + push。
- 用户已确认：成本/定价**不做精确核算**（M2 批量嵌入前看一眼方舟控制台额度余量即可）；成本表只记录耗时与额度观察。

Next Action: **M2 已收官（2026-11-11 tag m2，S3/S4 双审通过）——下一站 M3 检索+生成 CLI（runbook 待立项）**。遗留三件事：①125 表全量人工审计（用户过目 reports/table_audit_m2.md，不阻塞 M3）；②S3 Minor 清单排 M3 首项（specs/reviews/m2-indexing.review.md：表头 drop_cols 过滤、编号型 References 标题漏过滤、contextual 单块失败重试等）；③容器连 GitHub 不通期间为 scp 同步（容器侧 /home/doclens/RAG working tree 有未提交改动，网络恢复后须 pull 对齐——注意容器侧 fetch/checkout 后再清点）。用户已拍板：解析维持 CPU（GPU 探针实验入待办池）；表格 v2 升级为结构理解管线·规则版（区分列名/行名、剔除无效区域、manifest 输出、125 表全量人工审计；LLM/VLM 仲裁留财报泛化包），并入 M2 开工首项（2.0，纯后处理从缓存重建、不重跑 MinerU）。M2 核心方案：K1 切块=节内聚合 800–1600 字符（heading 前缀随行）+References/碎片过滤、K3 嵌入=单条+asyncio 并发 4、K4 缓存先行（MySQL t_embed_cache）、K5 Qdrant 两集合+kind 过滤实现 A/B 档、K6 BM25=jieba、K7 E 档前缀 M2 只试产 100 块。预估规模 ~2450 次嵌入调用。批准后顺序 2.0 表格v2 → 2.1 chunker → 2.2 建表 → 2.3–2.6 四模块 → 2.7 ingest → 2.8 实测验收（增量幂等+10 查询抽查）→ tag m2。注意：M2 涉及外部 API+凭据，实现后走 S4 安全复查；`/home` 持久卷管理员确认仍在等。2026-11-11 评审修订已并入 runbook（新增 §3.1 实施细则：幂等写入=doc 级跳过+uuid5 点 ID+先删后插、t_chunk 回表补 FR-2.4 坐标与正文、表格卡片、K1 内容过滤、风险表+3、§4 编号修正）；同日完成同类项目调研（specs/research/m2-indexing-survey.md：分块/表格/多模态三线，K1/K2/K4/K5 主线获官方先例印证，R1–R6 小修订已并入 runbook（正文标注调研 R#）），以上均随 G1 一并批准。

## 项目速查（随进展更新）

- **项目**：DocLens 多模态 RAG（求职作品集）。规划文档在 `specs/`：PRD v2.1、plan（5 轮修订）、M0 runbook 为现行执行依据。
- **模型**：火山方舟单供应商，全链路一把 `ARK_API_KEY`（Coding Plan 支持第三方模型：glm-5.3-flash / kimi-k3 / deepseek-v4.1-flash 等，见[官方列表](https://docs.volcengine.com/docs/ark/coding-plan-personal-get-started?lang=zh)）；SiliconFlow 已于 v2.1 移除，勿再引入。**主力 VLM 已换代**（2026-11-10 用户决策）：`GEN_MODEL=glm-5.3-flash`（原生多模态、thinking 型模型——正式代码须处理 reasoning_content 与 content 的分离）；`RERANK_MODEL_PRO=doubao-seed-2-1-pro` 保留为消融对比位。
- **拓扑（2026-11-09 变更：采用 VS Code Remote-SSH 远程开发）**：应用代码与 Python 环境在服务器容器内运行。SSH `root@10.14.50.123` **直达工作容器**（容器主机名 `404dd5d73a82`），无需 docker exec / Dev Containers 附加模式；连接参数以 Tabby / VS Code ssh config 里验证过的为准（密码只存本地，不写入本文件）。PyCharm 2024.1 因与容器内 conda 26.x 不兼容（`lateinit property envs_dirs` 崩溃，官方 2025.3 才修复）已搁置。容器内 `127.0.0.1` 直连 MySQL/Qdrant，不再依赖本地 SSH 隧道。最终交付仍需在 Windows 11 上按 README 克隆跑通（FR-7.1），代码保持跨平台（pathlib、不写死系统路径）。
- **数据库**：`doclens` 库已建（utf8mb4），应用账号 `hifen37`（密码只存本地 `.env`，绝不入库、不写入本文件）。
- **版本管理（2026-11-09 起）**：远程仓库 `https://github.com/Asparetire/RAG`（master 分支）为唯一同步中转站，Windows `D:\Project\RAG` ↔ 容器 `/home/doclens/RAG` 双端走 git。纪律：commit message 用"类型: 一句话"格式（feat/fix/docs/chore/env）；重要变更同步追加 `CHANGELOG.md` 条目（仓库根目录）；开工 pull、收工 push；同一文件不两头同时改。`.env` 与 `data/` 被 gitignore 挡住，绝不入库。
- **环境细节（2026-11-10，2026-11-11 勘误存储约定）**：容器内 pip 默认源已切清华镜像（`/root/.config/pip/pip.conf`），pypi.org 直连不可达（pip-audit 走 OSV 源在本机跑）；`.env` 双端独立维护（不入库）——**勘误（S4-02 实证 + 2026-11-11 本机体检确认）：Windows 侧写 `10.14.50.123` 不可达（3306/6333 未对外发布），本机场景必须走 SSH 隧道后写 `127.0.0.1`（本机 13306→3306、16333→6333，或 VS Code 端口面板），容器内场景保持 `127.0.0.1:3306/6333` 直连**；MinerU 模型落容器 `/root/.mineru/models/`（2.0 GB，2026-11-10 实测修正；原记 `/root/.cache` 有误），容器重建需重装重下（关联持久卷待办）。
- **git 双端同步（2026-11-11 升级）**：Windows 侧已加 `server` 远端（`ssh://root@10.14.50.123:8009/home/doclens/RAG`）+ 容器已配 `receive.denyCurrentBranch=updateInstead`——**`git push server master` 一条命令即同步容器工作区**（M2 遗留③ 的 scp 同步方式作废）；GitHub `origin` 照常 push 作公开备份。SSH 端口 8009（ssh config 已配）、密钥免密。
- **进度（2026-11-09）**：服务器 MySQL 已建库 ✅（doclens / hifen37）；Qdrant 已部署并验活 ✅（/home/doclens/qdrant）；一键脚本 /home/doclens/start-services.sh（2026-11-10 核查：此前 ✅ 记录有误、脚本从未落盘，重建版已交用户执行；Qdrant 本体在 /home/doclens/qdrant 完好）；本地 doclens conda 环境已装 ✅；容器内 miniconda 已装 ✅（conda 26.3.2）；容器内 doclens conda 环境已建 ✅（/opt/conda/envs/doclens）；VS Code Remote-SSH 直连容器已打通 ✅；项目代码已迁入容器 ✅（/home/doclens/RAG，scp 整包含 .git）；git 双端流程已建 ✅（S0 基线 02d447c 已提交并推送 GitHub）；CHANGELOG.md 已建立 ✅；M0 收官 ✅（tag m0，六连测全绿）；M1 收官 ✅（tag m1，11 篇解析+图注绑定，22 单测）。**M2 收官 ✅（2026-11-11 tag m2）**：表格 v2 结构理解管线（125 表 manifest+审计报告）+ chunker（1513 单元）+ 五张表 + 嵌入缓存（二次零 API 实测）+ Qdrant uuid5 幂等 + BM25 + E 档 100 块试产 + ingest 全量入库（Qdrant 1184+329 点）+ 增量幂等（重跑 0 API/2.6s）+ 10 查询抽查双路命中；S3 审查（Blocker 0/Major 2 已修）+ S4 安全复查（通过，3306/6333 外部不可达取证）；pytest 双端 65 passed。待办：125 表人工审计（用户）；AGENTS"Windows .env 写 10.14.50.123"约定实际不可达（M3 前勘误）；requirements 版本锁定+pip-audit；S3 Minor 排 M3。进行中：M3 检索+生成 CLI（待立项）。
