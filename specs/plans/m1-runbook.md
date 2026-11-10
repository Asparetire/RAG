# M1 解析管道 Runbook

> **状态：已批准（G1 通过 2026-11-10 15:05，进入 S2 实施）** ｜ slug：`m1-parse-pipeline` ｜ 依据：[主计划 §5 M1](doclens-multimodal-rag.plan.md)、[PRD FR-1.1~1.4](../prds/doclens-multimodal-rag.prd.md)、[M0 runbook](m0-runbook.md)（环境事实）
> **用户决策（2026-11-10）**：① 语料 = **自选领域论文**（用户收集 PDF，弃用主计划 1.1 的 arXiv 自动下载）；② MinerU 安装耗时 = **未记录**（用户无法回忆，如实记入成本表）；③ 实现方式 = **普通实现**（不走 TDD，每模块配关键路径单测）

---

## 1. 目标与验收标准（可执行验证）

| 验收项 | 验收方式 | 通过标准 |
|---|---|---|
| 语料入库 | `data/pdfs/` + `data/corpus_manifest.json` | 收料论文全部过校验（非空、可打开、`%PDF` 文件头；当前 11 篇，含 1 篇错投待用户定夺） |
| 统一文档模型 | `pytest tests/test_schema.py` | 四类块字段完整；JSON 序列化往返一致 |
| 解析器 | 全部入库论文（当前 11 篇）容器内实测 | 全部成功产出 schema JSON 落 `data/parsed/`；单篇耗时回填成本表 |
| 图注绑定率 | `quality.py` 报告 + 人工抽检 | 抽检 ≥90%（PRD FR-1.3） |
| 单测回归 | `pytest`（双端） | 全绿 |
| 里程碑 | commit（每步一个）+ `git tag m1` + push | GitHub 双端同步 |

## 2. 现状调查（2026-11-10 实测）

| 项 | 现状 | 结论 |
|---|---|---|
| git | 双端同在 409c19a，工作区干净 | 可开工 |
| 执行拓扑 | Windows 免密 SSH 直达容器（主机名 404dd5d73a82） | 代码在 Windows 写、容器内跑；AI 远程执行，用户不切终端 |
| MinerU | `mineru-kit` 4.1.7 @ `/opt/conda/envs/doclens-mineru/bin/`；模型 `/root/.mineru/models/`（2.0 GB = onnx 819M + GGUF 1.2G）；M0 样例解析产物预期在容器 `data/test/`（开工时核实） | CLI 桥接可用；AGENTS.md 旧记录（`/root/.cache`）已修正 |
| 配置 | `config.py` 已有 `PARSED_DIR = data/parsed`、`DATA_DIR` | 路径常量就绪，不需改 config |
| 依赖 | httpx / pillow 等已锁 | 不新增依赖、不动 requirements.txt |
| 语料 | 用户自选，已收 12 篇（文字版/未加密/文件头全过）。元数据核验发现 **1 篇错投**：文件名 Binary Relation Learning，内容实为高光谱遥感论文（DOI 10.1109/TGRS.2014.2350983，Murphy et al.）；真身已在（TEVC 10.1109/TEVC.2020.2986348，Hao Hao / Aimin Zhou 等） | 实际语料 11 篇；错投 1 篇待用户确认删除；1.1 改型为"人工收料 + 校验入库" |

## 3. 技术方案（关键点）

- **1.1 改型说明**：主计划 `download_corpus.py`（arXiv API 下载）因语料决策改为 `scripts/corpus_intake.py`——校验（PDF 文件头/大小/可打开）→ 按 sha256 定 doc_id → 复制为 `data/pdfs/<doc_id>.pdf` → 产出 `data/corpus_manifest.json`（doc_id/原文件名/sha256/大小）。下载动作由用户在 Windows 侧完成，AI 经 SSH/scp 搬入容器。
- **解析桥接（1.3 核心）**：`subprocess` 调 `/opt/conda/envs/doclens-mineru/bin/mineru-kit parse <pdf> -o <临时目录>`（4.1.7 参数以实测 `--help` 为准），读回 content list JSON；设超时与失败重试一次；CLI 输出目录按 PDF sha256 隔离。
- **schema 映射（1.2）**：`Block`（type: text/title/table/image；page；bbox；content；caption；image_path；heading_path）+ `DoclensDoc`（doc_id、sha256、blocks）+ JSON 序列化往返。
- **图注绑定**：就近原则（图块与相邻 text 块）+ `Figure N` / `Table N` / `图 N` / `表 N` 前缀识别；绑定结果写入 `caption` 字段。
- **表格线性化**：HTML → Markdown（保留行列结构，供 B 档文本入库）。
- **缓存（FR-1.1 增量）**：`data/parsed/<sha256>/`（raw content list + doc.json + images/）；已存在则跳过解析。
- **重复论文处理（两层去重，2026-11-10 用户追问后入设计）**：① 文件级（intake 时）——PDF sha256 拦字节级重复，改名副本也命中；② 论文级（解析后）——提取 DOI + 归一化标题与清单比对，同文不同源判重：manifest 标 `duplicate_of`，M2 只索引 canonical 份，文件删除与否由用户决定。本层顺带发现"文件名与内容不符"的错投文件（收料时已实测发现一例，见 §2）。
- **映射单测夹具**：把容器内 M0 样例的真实 content list JSON 摘取代表片段存 `tests/fixtures/`（入库跟踪），映射/绑定/线性化测试不真调 MinerU。

## 4. 变更清单（文件级）

| 动作 | 文件 | 职责 |
|---|---|---|
| 新增 | `doclens/parse/schema.py` | 统一文档模型（1.2） |
| 新增 | `doclens/parse/mineru_parser.py` | CLI 桥接 + 映射 + 绑定 + 线性化 + 缓存（1.3） |
| 新增 | `doclens/parse/quality.py` | 质检报告（1.4，P1 紧则砍） |
| 新增 | `scripts/corpus_intake.py` | 语料校验 + 指纹 + 清单（1.1 改型） |
| 新增 | `tests/test_schema.py`、`tests/test_parser_mapping.py`、`tests/fixtures/content_list_sample.json` | 单测与夹具 |
| 修改 | `reports/cost.md` | 三记录回填（模型体积已补 2.0 GB；单篇耗时 M1.3 实测后回填） |
| 修改 | `CHANGELOG.md`、`AGENTS.md` | 进度与锚点更新 |

## 5. 分步任务（执行顺序 1.2 → 1.0 → 1.3 → 1.4）

| 步 | 任务 | 验收 | 谁做 |
|---|---|---|---|
| 1.2 | schema.py + 单测 | pytest 绿 | AI |
| 1.0 | 用户收论文进 `data/pdfs_inbox/`（已收 12 篇，核验发现 1 篇错投待删）→ AI 去重校验、scp 上容器、出清单 | 11 篇过校验 + manifest 产出（预留 DOI/标题回填位） | 用户 + AI |
| 1.3 | mineru_parser.py + 单测 → 容器内 11 篇实测（逐篇计时） | 全解析成功；绑定率抽检 ≥90%；耗时回填成本表 | AI |
| 1.4 | quality.py 质检报告 | 报告可审阅（时间紧则砍，不影响 m1 标签） | AI |
| 收尾 | CHANGELOG + commit + tag m1 + push；specs 环境约束修订（PRD §8 / plan 修订⑥，随收官 commit 一并做）；AGENTS.md Next Action 指向 M2 | GitHub 同步 | AI |

## 6. 测试策略（普通实现）

- 每模块关键路径单测 ≥1 条；新增逻辑覆盖率目标 ≥80%（纯逻辑部分）。
- `test_schema.py`：构造样例 → 序列化 → 反序列化 → 断言相等。
- `test_parser_mapping.py`：固定夹具测映射（四类块）、图注绑定（就近 + 前缀）、表格线性化、sha256 缓存键。
- 集成验收走容器内真实解析（外部工具，不进单测）。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| 用户论文图表过少 → 绑定率失真 | 收料标准前置（图表密集） | 换论文 |
| MinerU CPU 解析慢（10 篇或数十分钟） | 逐篇跑 + 缓存增量 + 后台执行 | 接受耗时并记录 |
| content list 结构与预期不符 | 开工先人工核对 M0 真实产物再写映射 | 只动映射层 |
| 扫描件混入 | intake 基础校验 + 1.4 质检兜底 | 用户换文字版 |

## 8. 敏感代码判定

**非敏感**：无外部 API 调用（MinerU 为本地 CLI）、无凭据读写、纯本地文件处理。跳过 S4 安全复查（scp 搬运是人工操作非代码）。

## 9. 执行命令

```bash
# 单测（Windows 侧用 D:\soft\anaconda\envs\doclens\python.exe -m pytest；容器侧 conda activate doclens）
pytest

# 容器内实测解析（AI 经 SSH 执行，计时逐篇记录）
/opt/conda/envs/doclens-mineru/bin/mineru-kit parse data/pdfs/<doc_id>.pdf -o /tmp/m1_out/
```

---
## 确认门记录（S2 开始前填写）

- 批准时间：2026-11-10 15:05（+08:00）
- 批准指令原文：「yes 可以删」（同时确认删除错投遥感文件；语料定格 11 篇）
- TDD：否（用户 2026-11-10 预先选定"普通实现"）
