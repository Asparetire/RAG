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

Next Action: **M2 已开工——G1 已批准（2026-11-11 14:54，指令"开始M2的发开工作 保证工作质量"，普通实现走 S2'）**。runbook 在 `specs/plans/m2-runbook.md`（终稿），当前步：2.0 表格 v2。用户已拍板：解析维持 CPU（GPU 探针实验入待办池）；表格 v2 升级为结构理解管线·规则版（区分列名/行名、剔除无效区域、manifest 输出、125 表全量人工审计；LLM/VLM 仲裁留财报泛化包），并入 M2 开工首项（2.0，纯后处理从缓存重建、不重跑 MinerU）。M2 核心方案：K1 切块=节内聚合 800–1600 字符（heading 前缀随行）+References/碎片过滤、K3 嵌入=单条+asyncio 并发 4、K4 缓存先行（MySQL t_embed_cache）、K5 Qdrant 两集合+kind 过滤实现 A/B 档、K6 BM25=jieba、K7 E 档前缀 M2 只试产 100 块。预估规模 ~2450 次嵌入调用。批准后顺序 2.0 表格v2 → 2.1 chunker → 2.2 建表 → 2.3–2.6 四模块 → 2.7 ingest → 2.8 实测验收（增量幂等+10 查询抽查）→ tag m2。注意：M2 涉及外部 API+凭据，实现后走 S4 安全复查；`/home` 持久卷管理员确认仍在等。2026-11-11 评审修订已并入 runbook（新增 §3.1 实施细则：幂等写入=doc 级跳过+uuid5 点 ID+先删后插、t_chunk 回表补 FR-2.4 坐标与正文、表格卡片、K1 内容过滤、风险表+3、§4 编号修正）；同日完成同类项目调研（specs/research/m2-indexing-survey.md：分块/表格/多模态三线，K1/K2/K4/K5 主线获官方先例印证，R1–R6 小修订已并入 runbook（正文标注调研 R#）），以上均随 G1 一并批准。

## 项目速查（随进展更新）

- **项目**：DocLens 多模态 RAG（求职作品集）。规划文档在 `specs/`：PRD v2.1、plan（5 轮修订）、M0 runbook 为现行执行依据。
- **模型**：火山方舟单供应商，全链路一把 `ARK_API_KEY`（Coding Plan 支持第三方模型：glm-5.3-flash / kimi-k3 / deepseek-v4.1-flash 等，见[官方列表](https://docs.volcengine.com/docs/ark/coding-plan-personal-get-started?lang=zh)）；SiliconFlow 已于 v2.1 移除，勿再引入。**主力 VLM 已换代**（2026-11-10 用户决策）：`GEN_MODEL=glm-5.3-flash`（原生多模态、thinking 型模型——正式代码须处理 reasoning_content 与 content 的分离）；`RERANK_MODEL_PRO=doubao-seed-2-1-pro` 保留为消融对比位。
- **拓扑（2026-11-09 变更：采用 VS Code Remote-SSH 远程开发）**：应用代码与 Python 环境在服务器容器内运行。SSH `root@10.14.50.123` **直达工作容器**（容器主机名 `404dd5d73a82`），无需 docker exec / Dev Containers 附加模式；连接参数以 Tabby / VS Code ssh config 里验证过的为准（密码只存本地，不写入本文件）。PyCharm 2024.1 因与容器内 conda 26.x 不兼容（`lateinit property envs_dirs` 崩溃，官方 2025.3 才修复）已搁置。容器内 `127.0.0.1` 直连 MySQL/Qdrant，不再依赖本地 SSH 隧道。最终交付仍需在 Windows 11 上按 README 克隆跑通（FR-7.1），代码保持跨平台（pathlib、不写死系统路径）。
- **数据库**：`doclens` 库已建（utf8mb4），应用账号 `hifen37`（密码只存本地 `.env`，绝不入库、不写入本文件）。
- **版本管理（2026-11-09 起）**：远程仓库 `https://github.com/Asparetire/RAG`（master 分支）为唯一同步中转站，Windows `D:\Project\RAG` ↔ 容器 `/home/doclens/RAG` 双端走 git。纪律：commit message 用"类型: 一句话"格式（feat/fix/docs/chore/env）；重要变更同步追加 `CHANGELOG.md` 条目（仓库根目录）；开工 pull、收工 push；同一文件不两头同时改。`.env` 与 `data/` 被 gitignore 挡住，绝不入库。
- **环境细节（2026-11-10）**：容器内 pip 默认源已切清华镜像（`/root/.config/pip/pip.conf`），pypi.org 直连不可达；`.env` 双端独立维护（不入库）——容器侧 `MYSQL_URL`/`QDRANT_URL` 写 `127.0.0.1`，Windows 侧写 `10.14.50.123`；MinerU 模型落容器 `/root/.mineru/models/`（2.0 GB，2026-11-10 实测修正；原记 `/root/.cache` 有误），容器重建需重装重下（关联持久卷待办）。
- **进度（2026-11-09）**：服务器 MySQL 已建库 ✅（doclens / hifen37）；Qdrant 已部署并验活 ✅（/home/doclens/qdrant）；一键脚本 /home/doclens/start-services.sh（2026-11-10 核查：此前 ✅ 记录有误、脚本从未落盘，重建版已交用户执行；Qdrant 本体在 /home/doclens/qdrant 完好）；本地 doclens conda 环境已装 ✅；容器内 miniconda 已装 ✅（conda 26.3.2）；容器内 doclens conda 环境已建 ✅（/opt/conda/envs/doclens）；VS Code Remote-SSH 直连容器已打通 ✅；项目代码已迁入容器 ✅（/home/doclens/RAG，scp 整包含 .git）；git 双端流程已建 ✅（S0 基线 02d447c 已提交并推送 GitHub）；CHANGELOG.md 已建立 ✅；容器端 git 对齐 ✅（working tree clean，HEAD=02d447c，GitHub 公开仓库拉取免认证）；容器内 doclens-mineru 环境已建 ✅（2026-11-10，python 3.12 + mineru 4.x，样例 PDF 解析验收通过）；M0 0.3 配置骨架 ✅（pytest 4 passed）；M0 0.4 冒烟六连测 ✅（6/6 全绿，2026-11-10）；决策点① ✅（ARK_EMBED_BASE_URL=coding/v3 放行 multimodal 并回填容器 .env）；一键脚本 ✅（2026-11-10 重建：幂等 + 密钥从 .env 读取；此前 ✅ 记录有误）；SSH 免密 ✅（Windows ed25519 公钥入容器）。M0 0.5 成本核算表 ✅（框架版；三记录已补二：模型体积 2.0GB 实测、安装耗时=未记录，单篇耗时随 M1 1.3 回填）。进行中：M1 解析管道。M1 决策三连 ✅（2026-11-10：语料=自选领域论文 / MinerU 安装耗时=未记录 / 普通实现）；M1 runbook ✅（G1 批准）；M1 收官 ✅（2026-11-10 tag m1：1.2 schema + 1.0 corpus_intake 11 篇入库 + 1.3 mineru_parser 两阶段图注绑定 + 1.4 质检报告；22 单测全绿；有编号图表单元覆盖 100%，逐块 61.4% 为参考口径——127 个无图注图为附录小图/装饰图，属正常）。待办：管理员确认 /home 是否持久卷；GPU 探针实验（待办池：4×4090D 直通可见但推理库为 CPU 版，将来批量扩语料再启用）。进行中：M2 索引（G1 已批准 2026-11-11 14:54，普通实现；S2' 实施中——首步 2.0 表格 v2 前置抽查；解析原料在容器 /home/doclens/RAG/data/parsed/ 11 篇齐备，Windows 侧经 SSH 直连操作容器）。
