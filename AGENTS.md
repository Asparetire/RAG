# AGENTS.md

本文件供 AI 编码助手在本仓库工作时自动读取。

## 用户沟通约定（最高优先级）

- 用户是**技术新手**：不要假设已掌握 Linux / SQL / Python 生态的常识，术语第一次出现用一句话解释。
- 每一步操作都说明四件事：**这条命令在做什么 → 为什么需要 → 预期看到什么输出 → 怎样算成功**。
- 命令整块给出、可直接复制粘贴；占位符（如 `<密码>`）要说明替换成什么、从哪来。
- 出错时：先安抚（容器环境踩坑很正常），再按顺序给定位步骤（先看哪个输出/日志），最后给修复命令。
- 全程中文交流。

## 项目速查（随进展更新）

- **项目**：DocLens 多模态 RAG（求职作品集）。规划文档在 `specs/`：PRD v2.1、plan（5 轮修订）、M0 runbook 为现行执行依据。
- **模型**：火山方舟单供应商，全链路一把 `ARK_API_KEY`；SiliconFlow 已于 v2.1 移除，勿再引入。
- **拓扑（2026-11-09 变更：采用 VS Code Remote-SSH 远程开发）**：应用代码与 Python 环境在服务器容器内运行。SSH `root@10.14.50.123` **直达工作容器**（容器主机名 `404dd5d73a82`），无需 docker exec / Dev Containers 附加模式；连接参数以 Tabby / VS Code ssh config 里验证过的为准（密码只存本地，不写入本文件）。PyCharm 2024.1 因与容器内 conda 26.x 不兼容（`lateinit property envs_dirs` 崩溃，官方 2025.3 才修复）已搁置。容器内 `127.0.0.1` 直连 MySQL/Qdrant，不再依赖本地 SSH 隧道。最终交付仍需在 Windows 11 上按 README 克隆跑通（FR-7.1），代码保持跨平台（pathlib、不写死系统路径）。
- **数据库**：`doclens` 库已建（utf8mb4），应用账号 `hifen37`（密码只存本地 `.env`，绝不入库、不写入本文件）。
- **版本管理（2026-11-09 起）**：远程仓库 `https://github.com/Asparetire/RAG`（master 分支）为唯一同步中转站，Windows `D:\Project\RAG` ↔ 容器 `/home/doclens/RAG` 双端走 git。纪律：commit message 用"类型: 一句话"格式（feat/fix/docs/chore/env）；重要变更同步追加 `CHANGELOG.md` 条目（仓库根目录）；开工 pull、收工 push；同一文件不两头同时改。`.env` 与 `data/` 被 gitignore 挡住，绝不入库。
- **环境细节（2026-11-10）**：容器内 pip 默认源已切清华镜像（`/root/.config/pip/pip.conf`），pypi.org 直连不可达；`.env` 双端独立维护（不入库）——容器侧 `MYSQL_URL`/`QDRANT_URL` 写 `127.0.0.1`，Windows 侧写 `10.14.50.123`；MinerU 模型落容器 `/root/.cache`，容器重建需重装重下（关联持久卷待办）。
- **进度（2026-11-09）**：服务器 MySQL 已建库 ✅（doclens / hifen37）；Qdrant 已部署并验活 ✅（/home/doclens/qdrant）；一键脚本 /home/doclens/start-services.sh ✅；本地 doclens conda 环境已装 ✅；容器内 miniconda 已装 ✅（conda 26.3.2）；容器内 doclens conda 环境已建 ✅（/opt/conda/envs/doclens）；VS Code Remote-SSH 直连容器已打通 ✅；项目代码已迁入容器 ✅（/home/doclens/RAG，scp 整包含 .git）；git 双端流程已建 ✅（S0 基线 02d447c 已提交并推送 GitHub）；CHANGELOG.md 已建立 ✅；容器端 git 对齐 ✅（working tree clean，HEAD=02d447c，GitHub 公开仓库拉取免认证）；容器内 doclens-mineru 环境已建 ✅（2026-11-10，python 3.12 + mineru 4.x，样例 PDF 解析验收通过）。进行中：M0 0.3 配置骨架（config.py + tests/test_config.py）。待办：smoke_test.py 六连测、ARK_EMBED_BASE_URL 探测回填、成本核算表 reports/cost.md、specs 环境约束修订（PRD §8 / plan 修订⑥）、管理员确认 /home 是否持久卷。
