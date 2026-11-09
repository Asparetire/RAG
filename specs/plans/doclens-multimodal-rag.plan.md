# DocLens 项目整体实现计划

> **状态：待确认（停在确认门 G1）** ｜ 阶段：S1 实现规划 ｜ slug：`doclens-multimodal-rag`
> **规划依据**：[PRD v2.0（已确认）](../prds/doclens-multimodal-rag.prd.md)、[调研笔记](../research/eval-and-retrieval-survey.md)（技术细节与来源）
> **范围**：项目整体（M0–M6 全里程碑）；批准后按里程碑逐个实施，每个里程碑完成即 git 打标签
> **修订（2026-11-05，共 5 轮）**：① 模型侧——嵌入/生成/上下文增强切火山方舟（doubao-embedding-vision-251215 单模型统一文本/图像；D3/D7/D8）；② 存储侧——Qdrant server + MySQL 服务器原生部署（无 Docker），弃 local mode + SQLite（D4/D10）；③ 拓扑——服务器仅承载存储（容器环境：无 Docker、apt 可用），本地运行应用 + git 私有远端，`.env` 指向服务器端点（D13）；④ 重排侧——D6 重写为方舟 LLM 列表式重排（flash vs pro 对比 + 视觉逐图打分），**SiliconFlow 全部移除**，PRD FR-3.2 同步修订（v2.1）——全项目只剩一把 ARK key

---

## 1. 目标与验收标准（可执行验证）

**总目标**：按 PRD v2.0 交付 DocLens P0 全部 30 条 FR，含 A–F 六档消融评测报告。

| 里程碑验收 | 验收命令/方式 | 通过标准 |
|---|---|---|
| M0 环境 | `scripts/smoke_test.py` | 六项冒烟全绿（存储连通/模型列表/文本嵌入/图像嵌入/LLM 重排/VLM） |
| M1 解析 | 质检报告 + 人工抽检 | 10 篇种子 PDF 全解析；图注绑定率 ≥90% |
| M2 索引 | `python scripts/ingest.py` 后抽查 | 10 查询 top-5 基本相关；增量重建零重复计费 |
| M3 问答 CLI | `query_cli.py --profile D` 跑 20 冒烟题 | 人工通过率 ≥80%；不可回答题拒绝生效 |
| M4 服务+UI | 浏览器完整流程演示 | 提问→流式回答→引用点击→原页高亮 ≤20s |
| M5 评测 | `run_eval.py --profiles A B C D E F` | `reports/ablation.md` 产出（含 CI、配对检验、归因） |
| M6 打磨 | 新机器克隆验证 | README 跑通（克隆 → conda 环境 → `.env` 指向服务器栈 → 构建问答）；三件套齐（架构图/指标表/成本表） |

**PRD 成功标准映射**：S1→M5；S2→M4；S3/S4→M6。

---

## 2. 现状调查（2026-11-04 实测）

| 项 | 现状 | 结论 |
|---|---|---|
| 代码 | 无（greenfield） | 全部新建 |
| 已有资产 | `specs/`（PRD v2.0 已确认、调研笔记）、`.agents/skills/ai-dev-workflow`、git 1 commit（048a994） | 规划/流程资产齐备 |
| Node | v26.3.0 ✅ | 前端工具链可用（npm 随附；pnpm 需 `npm i -g pnpm`） |
| **Python/conda** | **Anaconda @ `D:\soft\anaconda`**（conda 24.9.2，base Python 3.12.7，未入 PATH，全路径可用）；系统 `python` 仅为 Store 存根；已有 6 个环境无命名冲突；D: 剩余 150GB | 用 conda 建双环境（M0.1/0.2） |
| 模型供应商 | **火山方舟（ARK，北京区）全链路单供应商**：`doubao-embedding-vision-251215`（套餐支持，官方文档核实）、`doubao-seed-2.1-pro`（官方视觉理解文档核实）、`deepseek-v4-flash`；方舟无独立 rerank 接口 → 重排用方舟 chat 模型做 LLM 列表式重排（D6） | 一把 ARK key 全覆盖 |
| MinerU | 4.x 默认安装支持 Windows CPU（basic tier，ONNX）；要求 Python ≥3.11 | 本机可行，但速度待 M0 实测 |
| 语料 | 未下载 | M1 从 arXiv API 拉取 |

---

## 3. 技术方案（关键决策）

| # | 决策 | 选择 | 被否方案与理由 |
|---|---|---|---|
| D1 | 工具链 | **conda（已有 Anaconda @ D:\soft\anaconda，24.9.2）**：`conda create` 双环境 `doclens` / `doclens-mineru`（python=3.12，包经 pip 装并锁版本） | uv（有 conda 后不引入第二套工具链）；python.org 全局安装（污染、无环境管理） |
| D2 | MinerU 隔离 | **独立 conda 环境 `doclens-mineru` + subprocess 调其 CLI**（basic tier；conda 未入 PATH，脚本内用全路径） | 并入主环境（torch 系依赖与主环境冲突风险高） |
| D3 | 嵌入 | **`doubao-embedding-vision-251215` 单模型统一文本/图像**（火山方舟）：端点 `/api/v3/embeddings/multimodal`，Query/Corpus 分侧 instructions（官方跨模态问答模板），`dimensions` 默认 2048；优先走 Coding Plan 端点 `…/api/coding/v3`（套餐额度内，官方确认支持该模型；M0 冒烟验证该端点是否放行 multimodal 路径），不通退常规 `/api/v3` 后付费；图像单图单请求 → asyncio 并发批处理 | SiliconFlow 双模型 bge-m3 + Qwen3-VL-Embedding-8B（用户未使用过他家，供应商收敛到火山）；本地 CLIP（ViDoRe 平均仅 17.7，已核实）。**新增风险**：doubao-embedding-vision 无公开基准数 → 见风险表（M2 抽检 + instructions 调优 + M5 消融兜底） |
| D4 | 向量库 | **Qdrant server（服务器原生进程：官方静态二进制 + systemd/nohup，无 Docker）**：qdrant_client url 模式；text/image 两集合 + payload（FR-2.4） | Chroma（功能与升级路径弱）；Milvus standalone（组件重、需 Docker）；社区版 MySQL VECTOR 列（能存不能查：DISTANCE/向量索引需 MySQL AI 或 HeatWave） |
| D5 | 关键词检索 | rank-bm25 + jieba（本地，中英混合分词） | Qdrant sparse（引入向量库内 BM25 语义，调优面大） |
| D6 | 重排 | **LLM 列表式重排（纯火山）**：文本路（D 档）RRF top-50 → 单次调用（`deepseek-v4-flash`，temperature=0）输出 top-20 排序；两种重排器对比位 = flash vs `doubao-seed-2.1-pro`；多模态路（F 档）doubao-seed 视觉逐图打分（0–10）。依据：RankGPT 实测 BM25 top-100 +6~10 nDCG@10（调研 [16]） | SiliconFlow 交叉编码器（用户不使用他家，供应商收敛到一把 ARK key）；交叉编码器本地 CPU（延迟 5–20s，F 档无本地等价物） |
| D7 | 生成 | **火山 `doubao-seed-2.1-pro`**（官方图片理解示例模型）：OpenAI 兼容 `/api/v3/chat/completions`，`image_url` base64（`data:image/png;base64,…`，单图 <10MB），SSE 流式；图片 token ≈ min(宽×高÷1764, 单图上限)；降本备选 `doubao-seed-2.1-lite`（模型名集中配置可切） | SiliconFlow Qwen3-VL 系列（供应商收敛到火山）；GLM-4V/DeepSeek-VL2 |
| D8 | 上下文增强（E 档） | 火山 `deepseek-v4-flash` 为每块生成 50–100 token 前缀，**嵌入与 BM25 共用**；结果缓存 | 摘要索引（Anthropic 实测增益低）；late chunking（API 不暴露 token 级嵌入） |
| D9 | 后端/前端 | FastAPI + uvicorn（SSE）；Vite + React + pdf.js（演示页）；Gradio（调试，P1） | 全栈框架（无必要） |
| D10 | 配置与缓存 | `.env` + `config.py` 模型名集中（含火山 base_url 双端点、嵌入 instructions 模板、dimensions、MYSQL_URL/QDRANT_URL/QDRANT_API_KEY——均指向服务器）；解析缓存按 PDF sha256 落 `data/parsed/`；**MySQL 8.0+（服务器 apt 原生安装；本项目不在数据库侧做向量检索，8.0 即可）**：嵌入缓存（`hash→vector` MEDIUMBLOB，键含模型+指令+维度）+ 文档/块元数据表 + 评测结果表 | 无缓存（消融重跑成本翻倍，违背 NFR）；SQLite（用户熟悉 MySQL，评测记录 SQL 分析更顺） |
| D11 | 跨语言路由 | 查询语言检测（中文→稠密路为主，BM25 路降权旁路）；**不加查询翻译** | 翻译管道（研究证实劣于多语言嵌入） |
| D12 | 上下文组装 | 重排后 top-20 截断、最相关块首尾放置、图片 ≤5 张 | 大上下文堆料（lost-in-the-middle：50 vs 20 文档仅 +1.5%） |
| D13 | 部署拓扑 | **存储服务端化**：MySQL+Qdrant 由服务器原生承载（Linux **容器环境：无 Docker、apt 可用**——MySQL apt 安装、Qdrant 静态二进制 scp 部署，部署件在 `deploy/`）；**本地运行应用**（解析/索引/评测/服务，API 调用全由本地出口发起，服务器无需外网）+ git 私有远端（里程碑 tag 推送）；`.env` 指向服务器内网端点；PDF/解析缓存/BM25 索引留在本地 | 全栈本地（需本地常驻存储；用户指定数据上服务器） |

**架构**（数据流）：

```
【离线】PDF →(MinerU·doclens-mineru 环境)→ 统一文档模型 JSON + 图表图片
   → 文本块(含图注/表格线性化/上下文增强) --doubao-embedding-vision(text指令)--> Qdrant:text ┐
   → 图表图片 --doubao-embedding-vision(image指令)--> Qdrant:image                            ├ BM25 → 融合
【在线】中文提问 → 语言路由 → 三路召回 → RRF → LLM 重排(top-50→top-20；多模态路视觉逐图打分)
   → 上下文组装(top-20/首尾/图≤5) → doubao-seed-2.1-pro 流式生成 → 引用[ n ]→(doc,page,bbox)
   → 前端：引用点击 → pdf.js 原页渲染 + bbox 高亮
```

---

## 4. 变更清单（项目结构，文件级）

```
doclens/
├── doclens/                        # 主包
│   ├── config.py                   # D10：.env 读取、模型名集中、消融档位(A–F)定义、路径常量
│   ├── parse/
│   │   ├── schema.py               # 统一文档模型（FR-1.2）：doc_id/page/type/content/caption/bbox/image_path/heading_path
│   │   ├── mineru_parser.py        # D2：subprocess 调 doclens-mineru 环境 CLI → content list → schema；图注绑定；表格线性化（FR-1.2/1.3）
│   │   └── quality.py              # 质检报告（FR-1.4，P1）
│   ├── index/
│   │   ├── embeddings.py           # D3：火山嵌入客户端（/embeddings/multimodal，Query/Corpus 分侧指令，文本/图像同模型）+ MySQL 嵌入缓存（FR-2.1/2.2/2.5）
│   │   ├── contextual.py           # D8：块上下文前缀生成 + 缓存（FR-2.6，E 档）
│   │   ├── qdrant_store.py         # D4：url 模式接服务器 Qdrant；text/image 两集合 + payload 元数据（FR-2.4）
│   │   └── bm25.py                 # D5：BM25 索引构建与查询（FR-2.3）
│   ├── retrieve/
│   │   ├── hybrid.py               # 三路召回 + RRF(k=2,权重可配) + 图-图注联动去重（FR-3.1）
│   │   ├── rerank.py               # D6：LLM 列表式重排（flash/pro 可切换，温度 0）+ 多模态路视觉逐图打分（FR-3.2/3.5）
│   │   └── router.py               # D11：查询语言检测与路由（FR-3.4）
│   ├── generate/
│   │   ├── context.py              # D12：上下文组装（FR-4.1）
│   │   ├── vlm.py                  # D7：VLM 流式调用（doubao-seed-2.1-pro，FR-4.2）
│   │   ├── citations.py            # [n] 引用解析 → (doc,page,bbox)（FR-4.3）
│   │   └── fallback.py             # 兜底：检索分数 + 充分性双信号（FR-4.4）
│   ├── eval/
│   │   ├── dataset.py              # 评测集加载与构建工具（FR-6.1）
│   │   ├── metrics.py              # recall/MRR/nDCG/judge/引用命中（FR-6.2）
│   │   ├── stats.py                # McNemar + bootstrap CI（FR-6.3）
│   │   ├── attribution.py          # F0–F6 失败归因（FR-6.4）
│   │   └── ablation.py             # A–F 档编排（FR-3.3/6.5）
│   └── serve/
│       ├── api.py                  # FastAPI：/api/query(SSE)、/api/docs、/api/figure、/api/page（FR-5.1）
│       └── assets.py               # PDF 页渲染 + overlay 数据（FR-5.1/5.2 支撑）
├── scripts/
│   ├── smoke_test.py               # M0 冒烟（五连测）
│   ├── download_corpus.py          # arXiv 语料下载（FR：数据需求）
│   ├── ingest.py                   # 全量构建入口：解析→增强→索引（含增量）
│   ├── query_cli.py                # CLI 问答（--profile A..F）
│   └── run_eval.py                 # 一键评测（FR-6.6）
├── web/                            # React 演示前端（M4，FR-5.2/5.3）
├── data/                           # pdfs/ parsed/ cache/（本地；.gitignore）——mysql/qdrant 数据卷在服务器
├── tests/                          # 单测 + 集成（见 §6）
├── specs/                          # 已有：prds/ plans/ research/ reviews/
├── reports/                        # ablation.md、cost.md
├── .env.example                    # key 模板（不含真实 key）
├── requirements.txt + requirements-dev.txt
├── deploy/                         # D4/D13：服务器部署件（mysql 初始化 SQL / qdrant systemd unit / 部署 README）
├── .gitignore                      # data/ .env .venv* __pycache__ 等
└── README.md                       # M6 定稿（两命令/架构图/指标表/成本表）
```

---

## 5. 分步任务（按里程碑）

### M0 骨架与环境（约 0.5 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 0.0 | 服务器准备（一次性，SSH；**容器环境：无 Docker、apt 可用**）：apt 安装 MySQL（建库 + 专用账号 + bind-address）→ 部署 Qdrant 静态二进制（本地下载 → scp → nohup/systemd + API key） | 本地连通服务器两端口（MySQL 握手 + Qdrant /healthz） | 服务器 |
| 0.1 | `conda create -n doclens python=3.12 -y` → 环境内 `pip install -r requirements.txt -r requirements-dev.txt`（版本锁定） | 环境内 `pip list` 符合清单 | 无 |
| 0.2 | `conda create -n doclens-mineru python=3.12 -y` → `pip install "mineru>=4.0,<5"` → basic 模型下载（首次解析自动下载，或 `mineru-kit models download`） | 解析 1 篇样例 PDF 成功 | 无 |
| 0.3 | `config.py` + `.env.example` + `.gitignore` | 配置读取测试过 | 骨架 |
| 0.4 | `scripts/smoke_test.py`：MySQL/Qdrant 连通→模型列表→文本嵌入→图像嵌入（含 Coding Plan 端点探测，不通退 /api/v3）→LLM 重排→VLM 各一发 | 全绿 | 无 |
| 0.5 | `reports/cost.md` 成本核算表（按平台定价页，含 E 档一次性成本） | 表产出 | 无 |

### M1 解析管道（2–3 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 1.1 | `download_corpus.py`：arXiv API 拉 10 篇种子（cs.CL，图表密集启发式筛选，限速礼貌下载） | 10 篇落 `data/pdfs/` | data |
| 1.2 | `schema.py` 统一文档模型 + 单测 | 模型字段完整、序列化往返一致 | doclens/parse |
| 1.3 | `mineru_parser.py`：CLI 桥接 → content list → schema 映射；**图注绑定**（就近 + Figure/Table 前缀识别）；表格 HTML→Markdown 线性化；sha256 缓存 | 抽检绑定率 ≥90% | doclens/parse |
| 1.4 | `quality.py` 质检报告（P1，紧则砍） | 报告可审阅 | doclens/parse |

### M2 索引（1 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 2.1 | `embeddings.py`：文本/图像嵌入客户端（同模型分侧指令）+ MySQL 嵌入缓存 | 同输入二次调用零 API 费用 | doclens/index |
| 2.2 | `qdrant_store.py`：text/image 两集合 + payload（url 模式接服务器 Qdrant） | 插入/查询/元数据过滤可用 | doclens/index |
| 2.3 | `bm25.py`：索引构建（jieba+空格混合分词） | 中文/英文查询都能命中 | doclens/index |
| 2.4 | `contextual.py`（E 档）：块前缀生成 + 缓存 | 100 块生成成本与耗时入核算表 | doclens/index |
| 2.5 | `ingest.py` 全量入口（增量） | 10 篇入库；抽查 10 查询 top-5 相关 | scripts |

### M3 检索 + 生成 CLI（2 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 3.1 | `hybrid.py` 三路召回 + RRF + 去重（含单测） | 融合结果合理 | doclens/retrieve |
| 3.2 | `rerank.py`：LLM 列表式重排（flash/pro 可切换）+ 多模态路视觉打分（F 档） | D 档两重排器可对比；温度 0 输出稳定 | doclens/retrieve |
| 3.3 | `router.py` 语言检测与路由 | 中文查询走 dense 主路（单测） | doclens/retrieve |
| 3.4 | `context.py` + `vlm.py` + `citations.py` + `fallback.py` | 引用可解析；兜底可触发 | doclens/generate |
| 3.5 | `query_cli.py --profile A..F` | 20 冒烟题人工通过率 ≥80% | scripts |

### M4 服务 + UI（2–3 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 4.1 | `api.py` + `assets.py`：SSE 问答、文档/图片/PDF 页服务 | 接口冒烟过 | doclens/serve |
| 4.2 | `web/` React：对话区、引用侧栏、pdf.js 原页 + bbox 高亮 | 完整演示 ≤20s | web |
| 4.3 | Gradio 调试界面 + 检索可视化（P1） | 可用 | scripts |

### M5 评测（2–3 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 5.1 | `dataset.py`：VLM 半自动出题（三类×50 + 不可回答 15）→ 人工审核 → JSONL 定稿 | 题集版本化 | doclens/eval |
| 5.2 | `metrics.py` + `stats.py` + `attribution.py` | 金标 10 题回归通过 | doclens/eval |
| 5.3 | `ablation.py` + `run_eval.py`：A–F 跑批（结果落 MySQL 评测表） | 指标、CI、归因产出 | doclens/eval |
| 5.4 | `reports/ablation.md` 报告撰写 | 结论可复核 | reports |

### M6 打磨（1–2 天）
| 步 | 任务 | 验收 | 影响面 |
|---|---|---|---|
| 6.1 | README 定稿（部署拓扑：本地开发/服务器存储两端点说明/架构图/指标表/成本表） | 新人克隆跑通（含服务器栈前置说明） | README |
| 6.2 | 演示录屏 + 财报泛化包（P1） | 录屏产出 | data/web |

**总计**：约 10–14 个工作日（业余 2–3 周）。每里程碑完成即 `git commit + tag`。

---

## 6. 测试策略

| 层 | 对象 | 方式 |
|---|---|---|
| 单测（pytest） | `schema` 映射、RRF 融合、引用解析、指标计算、语言路由、缓存键 | 纯逻辑，无外部依赖，pytest 覆盖 |
| 集成 | 解析→索引→检索→生成端到端（固定 2–3 篇小语料） | 断言关键不变量：引用非空且可解析、图片数 ≤5、trace 落盘 |
| API 冒烟 | `/api/query` SSE 等 | httpx TestClient |
| 评测回归 | 金标 10 题固定集 | 指标可复现（防评测 harness 自身回归） |

**TDD 判定**：若批准时带 TDD 指令，TDD 范围限定纯逻辑模块（`metrics.py`、`hybrid.py` 的 RRF、`citations.py`），API 粘合层按关键路径测试处理（外部服务无法先写失败测试）。若普通实现，则每模块至少关键路径测试 1 条，新增逻辑覆盖率建议 ≥80%。

---

## 7. 风险与回滚

| 风险 | 概率 | 缓解 | 回滚 |
|---|---|---|---|
| MinerU Win/CPU 安装失败或过慢 | 中 | M0 首日实测；flash tier 预筛；公开论文可远程 tier | 退 docling，改动面仅 `mineru_parser.py` |
| LLM 重排在线延迟（+2~5s/查询） | 中 | RRF 先截 top-50、单次调用、flash 模型；演示走流式并行 | 砍重排档位（RRF 直出 top-20，改动面 rerank.py 开关） |
| LLM 重排复现性（温度 0 非绝对确定） | 低 | temperature=0 + 记录模型版本；配对统计容忍小方差 | — |
| Coding Plan 端点不放行 /embeddings/multimodal | 低 | M0 首日冒烟实测 | 退常规 /api/v3 后付费（模型不变，嵌入单价低） |
| doubao-embedding-vision 检索质量未验证（无公开基准数） | 中 | M2 入库后 10 查询抽检；优先调 instructions/dimensions/模型版本（官方强调 instructions 决定效果）；M5 消融用数据说话 | 质量确凿不达标时以评测数据重议供应商（数据决策） |
| 环境问题 | 已消除 | 已有 conda（D:\soft\anaconda，base 3.12.7，D: 剩 150GB）；双环境隔离 | — |
| 服务器为容器环境（无 Docker、apt 可用） | 已纳入设计 | MySQL apt 原生安装；Qdrant 静态二进制 scp 部署；API 调用全由本地发起 | — |
| 服务器不可达（网络/宕机） | 低 | 进程守护（systemd unit 或管理员侧自启）；恢复后本地 `.env` 直连即用 | 退 Qdrant local mode + SQLite（连接层已封装隔离，改动面小） |
| 成本超支 | 低 | 嵌入缓存；评测分批跑；E 档前缀生成前先小样定价 | 砍 E/F 档保 A–D 主线 |
| 时间超支 | 中 | 里程碑独立验收；P1 随时可砍 | 保 P0 闭环 |
| 评测集质量 | 中 | 人工审核 + BM25 剔伪题 + F0 监控（>5% 先修题集） | — |

**回滚策略**：每里程碑 git tag（`m0`…`m6`）并推送私有远端，任何一步出问题回退到上一标签；本地解析产物/缓存在 `data/`（gitignore）；服务器栈数据用 mysqldump + Qdrant snapshot 定期备份。

---

## 8. 敏感代码判定

**是（敏感）**。依据：① 外部 API 调用（火山方舟全链路）；② API key 管理（.env：ARK_API_KEY、MYSQL_URL、QDRANT_API_KEY）；③ 服务器承载存储服务（端口暴露面）。
实现完成后必须走 S4 安全专项复查，重点：
- `.env` 在 `.gitignore` 中且仓库历史无 key；`.env.example` 不含真实值
- 服务器无公网出口、仅内网可达（无公网暴露面）：Qdrant 开 API key；MySQL 专用最小权限账号（非 root）；同网段多人共用时加 SSH 隧道
- 凭据不入仓库、不入日志、不入错误信息
- key/PII 不入日志、不入 trace、不入错误信息
- 依赖审计（`pip-audit`）
- 前端不暴露 key（API 全部经后端代理转发）

---

## 9. 执行命令

```bash
# ── M0 环境（一次性）──
# ① 服务器（SSH，容器环境无 Docker）：apt 装 MySQL（建库/专用账号/bind-address）→ scp Qdrant 静态二进制 → 起进程（nohup/systemd）+ API key；内网直连
# ② 本地（conda 在 D:\soft\anaconda 未入 PATH，用 Anaconda Prompt / conda activate，或全路径 condabin\conda.bat）：
#    .env：ARK_API_KEY（火山）+ ARK_BASE_URL（优先 https://ark.cn-beijing.volces.com/api/coding/v3）+ MYSQL_URL + QDRANT_URL/QDRANT_API_KEY（均指向服务器）
conda create -n doclens python=3.12 -y
conda activate doclens
pip install -r requirements.txt -r requirements-dev.txt
conda create -n doclens-mineru python=3.12 -y
conda activate doclens-mineru
pip install "mineru>=4.0,<5"
# MinerU 模型（basic tier；首次解析自动下载，或手动）：
mineru-kit models download --tier basic
conda activate doclens
python scripts/smoke_test.py                                   # 冒烟（五连测）

# ── 构建 / 问答 / 评测（doclens 环境内）──
python scripts/download_corpus.py --seed 10
python scripts/ingest.py                    # 解析→增强→索引（增量；内部经 subprocess 调 doclens-mineru 的 CLI）
python scripts/query_cli.py --profile D "成绩对比图里哪个考试超过了人类？"
python scripts/run_eval.py --profiles A B C D E F

# ── 测试 ──
pytest --cov=doclens --cov-report=term-missing

# ── 服务 / 前端 ──
uvicorn doclens.serve.api:app --reload      # 后端
cd web && npm i -g pnpm && pnpm install && pnpm dev   # 前端（或直接用 npm）
```

---

## 确认门记录（S2 开始前填写）

- 批准时间：
- 批准指令原文：
- TDD：是 / 否
