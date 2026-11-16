# DocLens M6 打磨·README 呈现与泛化包调研

> 状态：**v1.0（README 原文级核实）**——2026-11-16。动机：M6 两件事（6.1 README 定稿：新人两条命令跑通；6.2 演示录屏+财报泛化包）的业界惯例与实施细节调研。
> 调研线：M（README 结构，5 项目原文核实）+ N（demo 呈现/录制工具/中文财报难点/泛化方法学）。网络备注：web_search 402；README 原文经 ghfast.top，arxiv/obsproject/playwright.dev 直抓。

## 1. M 线：README 结构与部署文档（5 项目）[M1]–[M7]

- **章节骨架**（高星实际顺序）：logo+一句话 → badges → **demo gif/截图首屏** → 可折叠 TOC → What is X → Get Started → Key Features → System Architecture → 部署（多方式分节）→ 配置 → FAQ → License。
- **quick start 惯例**：命令块+"打开 http://localhost:PORT"+默认账号引导（MaxKB 默认密码直接写 README；FastGPT 两条命令+root/1234）；Prerequisites 单列。
- **架构图**：5 样本均**不用 mermaid**——静态 png 放 docs/images 是主流。
- **环境变量**：.env.example 为真源+README 内联 3-5 个关键项表格，详解下沉。
- **demo 呈现**：全部首屏；gif 为主；**大资产不入主仓库**（AnythingLLM 挂 Release assets、open-webui 挂自家 CDN）——四项目一致实证。

## 2. N 线：demo 录制/中文财报/泛化方法学 [N1]–[N12]

- **demo 形式三派**：RAGFlow 双 GIF 置顶（资产独立 docs 仓库）/lobe-chat 用 user-attachments mp4 内联渲染（GitHub 免费、README 直播）/ai-chatbot 仅静态图+在线 demo 链接。均无 YouTube/bilibili 链接惯例。
- **录制工具（免费+Windows）**：OBS Studio（全场景 mp4）+ **Playwright `video:'on'`**（浏览器场景脚本化稳定录像+action 高亮）+ ScreenToGif（剪 README 首屏 GIF）。
- **中文财报难点（MinerU/OmniDocBench 官方口径）**：跨页表格合并、复杂版面、阅读顺序；表格属性含合并单元格/三线表/无边框；OmniDocBench 10 类文档**含 research_report（研报/财报）**；MinerU 2.5-Pro Table TEDS 93.42——复杂表仍是相对短板。
- **财报预检清单**（OmniDocBench 维度）：①有无文本层（扫描件险）②表格边框类型③跨页表与合并单元格④双栏/竖排/旋转⑤水印。
- **泛化方法学**：**BEIR 零样本设定**（构建域≠评测域，NeurIPS 2021 D&B）——DocLens 可声明"调优仅基于学术论文语料，财报包构建期不可见，属零样本跨域评测"；解析指标可借 OmniDocBench 口径命名（文本编辑距离/表格 TEDS）。

## 3. 对 DocLens M6 的建议（→ runbook）

- **README 章节**：logo+badges → **首屏截图四宫格**（登录门/流式对话+引用 bbox/评测看板）→ 可折叠 TOC → 架构图（docs/images/architecture.png，双端拓扑）→ **两条命令**（①git clone ②bash scripts/start_server.sh，中间 10 秒 cp .env.example+填 ARK_API_KEY）→ Windows 开发模式 subsection（隧道口诀）→ .env 双列表 → **评测小表**（A→C→D 消融+BEIR，链接 ablation.md）→ FAQ 3-5 条 → License。
- **demo**：60–90s **user-attachments mp4 内联**（README 直播、不占仓库）+ 15–20s GIF 备用首屏；分镜：论文库/上传(0-15s)→流式回答+思考三态(15-40s)→**点引用→PDF bbox 高亮（黄金位 40-60s）**→多模态题(60-70s)→评测看板(70-90s)。
- **录制管线**：OBS 录全流程 mp4 + Playwright video:'on' 兜底 + ScreenToGif 剪首屏 GIF。
- **财报包验收标准**：3–5 篇 A 股年报覆盖不同版式（横/竖/跨页/合并单元格表）；每篇 ≥10 题含表格数字题；通过线=解析层（Markdown 表格抽查可读+跨页表合并正确）+问答层（可答且引用 bbox 点中）+**零样本口径声明**（财报域降幅如实报告）。

## 4. 来源清单

| 线 | 来源 |
|---|---|
| M 线 | [M1] ragflow README（骨架/Docker-Source 二分/架构图 jpg）；[M2] anything-llm README（部署矩阵/.env 生成/Release gif）；[M3] open-webui README（pip 两命令/内联 -e 表/docs 分层）；[M4] FastGPT README（中文骨架/两条命令/默认账号/四宫格）；[M5] MaxKB README（一条 docker run/对比表/四宫格）；[M6] Best-README-Template（编号步骤/Prerequisites）；[M7] ungh 元信息 |
| N 线 | [N1] ragflow README（双 GIF/独立 docs 仓库）；[N2] open-webui README（CDN gif）；[N3] lobehub README（user-attachments mp4 内联）；[N4] ai-chatbot README（静态图+demo 链接）；[N5] MinerU README_zh（4.2 三难点/四档解析）；[N6] OmniDocBench README（10 类型含 research_report/表格维度/TEDS/v1.6 嵌套表）；[N7] BEIR arxiv 2104.08663（零样本跨域）；[N8] playwright.dev videos；[N9] obsproject.com；[N10] ScreenToGif README；[N11][N12] 年报比对文与 GitHub 限额〔未核实〕 |
