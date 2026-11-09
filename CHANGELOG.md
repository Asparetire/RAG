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
