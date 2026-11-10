# CHANGELOG（项目变更日志）

> 约定：每次重要变更（环境/部署、新功能、修复、文档结构）都要在这里追加一条记录，写清"干了什么"；日常小改动只在 commit message 里说清即可。本文件与代码一起提交，随仓库同步到两端。

## 记录格式

```
### 日期｜类型：一句话标题
- 要点 1
- 要点 2
```

类型取值：`env`（环境/部署）、`feat`（新功能）、`fix`（修复 Bug）、`docs`（文档）、`chore`（杂项）。

---

## 2026-11-09｜env：远程开发工作流搭建完成

- 拓扑变更：弃用 PyCharm SSH 远程（2024.1 与容器内 conda 26.x 不兼容，报 `lateinit property envs_dirs` 崩溃，官方 2025.3 才修复），改用 VS Code Remote-SSH 直连容器（`root@10.14.50.123` → 容器 `404dd5d73a82`）。
- 容器内环境就绪：Miniconda（conda 26.3.2）、doclens conda 环境（/opt/conda/envs/doclens）已建。
- 项目代码迁入容器 `/home/doclens/RAG`（scp 整包，含 .git）。
- 建立 GitHub 远程仓库 `Asparetire/RAG` 作为 Windows ↔ 容器双端同步的中转站，确立纪律：开工 pull、收工 push、同一文件不两头同时改。
- 新增本 CHANGELOG；`.gitignore` 追加排除 `.agents/`（AI 助手本地目录）。
- 修复 Windows 端 `.git` 目录的文件夹权限缺陷（此前 git 写入被拒；原权限已备份，恢复脚本在 `.agents/acl-recovery/`）。
- 容器端 git 对齐完成：`working tree clean`，HEAD=02d447c，双端同步流程首次跑通。

## 2026-11-10｜env：容器内 MinerU 解析环境搭建完成

- 创建容器 conda 环境 `doclens-mineru`（python=3.12），安装 `mineru>=4.0,<5`（M0 runbook §0.2）。
- 容器网络限制：pypi.org 直连不可达（Errno 101 Network is unreachable），已把 pip 默认源切换为清华镜像（写入 `/root/.config/pip/pip.conf`，一劳永逸）。
- 样例 PDF（s41467-025-67998-6，Nature Communications 论文）解析跑通，`data/test/` 产出结构化 Markdown，用户验收通过。
- 成本三记录（安装耗时 / 模型体积 / 单篇解析耗时）暂缺，待 0.5 成本表环节补录。
- 位置备注：MinerU 模型与 pip 包分别落在容器 `/root/.cache` 与 `/opt/conda/envs`——容器若重建需重装重下（关联待办：管理员确认持久卷）。

## 2026-11-10｜feat：M0 0.3 配置骨架 + 0.4 冒烟六连测脚本入库

- 新增 `doclens/config.py`（plan D10）：pydantic-settings 读 `.env`、模型名集中、消融阶梯 A–F 常量（PRD §7.1）、路径常量（pathlib 跨平台）、嵌入 Query/Corpus 分侧 instructions 模板（runbook §0.4）。
- 新增 `tests/test_config.py`：4 条配置测试（模型配置 / 存储地址 / 路径常量 / 档位齐全），验收 `pytest tests/test_config.py`。
- 新增 `scripts/smoke_test.py`（runbook §0.4）：六连测（MySQL/Qdrant 连通、文本/图像嵌入、LLM 重排、VLM 流式），每项打印耗时供成本表；含 `ARK_EMBED_BASE_URL` 探测（coding/v3 → api/v3 顺序）与自动回填 `.env`（M0 决策点①）。
- 分工：代码由 AI 助手在 Windows 侧编写推送，容器侧 pull 后执行 pytest 与冒烟。
- 修复：容器内 pytest 报 `ModuleNotFoundError: No module named 'doclens'`——新增 `pytest.ini`（`pythonpath = .` 把仓库根加入测试导入路径，`testpaths = tests`）。

## 2026-11-10｜env：M0 冒烟六连测全绿（6/6），决策点①完成

- **0.3 配置骨架验收通过**：容器内 `pytest tests/test_config.py` 4 passed（pytest.ini 修复后导入路径正常）。
- **0.4 冒烟六连测 6/6 全绿**：MySQL/Qdrant 连通、文本/图像嵌入（均 2048 维）、LLM 重排（flash 列表式）、VLM 流式生成——每项耗时已记录供成本表。
- **决策点①结论**：嵌入端点 `coding/v3` 放行 multimodal 路径，`ARK_EMBED_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3` 自动回填容器 `.env`（Coding Plan 额度覆盖嵌入，无需退 api/v3 付费通道）。
- 修复：方舟 multimodal 嵌入响应的 `data` 为**字典**（`{"embedding": [...]}`）而非 OpenAI 风格数组——smoke_test 改为双格式兼容解析。
- 修复：Qdrant 401——以正在运行的进程（11-05 启动）环境变量为准，把真实密钥同步回容器 `.env`，连通验证通过。
- 重建 `/home/doclens/start-services.sh`（幂等启动 + API key 从 `.env` 读取），MySQL 8.0.42 / Qdrant 验活通过。
- SSH 免密打通：Windows ed25519 公钥装入容器 `authorized_keys`，自动化运维不再依赖密码。
- 待补：成本表三记录（MinerU 安装耗时/模型体积/单篇解析耗时）与方舟定价页数字，凑齐后产出 reports/cost.md 并打 tag 收官。


