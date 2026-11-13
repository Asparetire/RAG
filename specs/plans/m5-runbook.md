# M5 评测 Runbook

> **状态：待批准（G1 确认门）** ｜ slug：`m5-evaluation` ｜ 依据：[主计划 §5 M5](doclens-multimodal-rag.plan.md)、[PRD FR-3.4/FR-6.x、S2](../prds/doclens-multimodal-rag.prd.md)、[m4-runbook](m4-runbook.md)（M4 产物=评测对象与消融新维度）、[m5-eval-survey](../research/m5-eval-survey.md)（v1.0：QASPER/BEIR/RGB 基准调研 + RAGAS/ALCE/ir-measures 指标口径 + judge 校准，[K]/[L] 来源编号）
> **用户已批准的三项范围**（2026-11-13）：①QASPER 外部基准纳入；②BEIR 检索旁测纳入；③负面维度题（噪声/反事实）并入自建集。
> **输入观察项**：①S4-11 图片读侧越界（S4 报告建议 M5 首项顺手修）；②M3 图片路径 bug 已修——C 档消融口径备注（此前图文输入静默失效）；③J-1 重排降级率口径随 D 档；④NFR"正文首 token"口径提案随本 runbook 一并确认。

---

## 1. 目标与验收标准（可执行验证）

| 验收项 | 验收方式 | 通过标准 |
|---|---|---|
| 自建题集 v1.0 | `data/eval/dataset_v1.jsonl` 版本化 + 分层统计报告 | ~185 题（可回答 150+不可答 15+负面 20）；题型/论文/语言/难度四维覆盖达标；BM25 伪题率 ≤5%；人审通过 |
| QASPER 外部基准 | `data/eval/qasper_subset.jsonl` + 论文入库记录 | 60–100 题分层抽样（多段文本/图表/不可答≈8:1.5:1）；对应论文 PDF 全部入库可问 |
| BEIR 检索旁测 | `scripts/eval_beir.py` 跑 SciFact+NFCorpus | nDCG@10 产出并与 BEIR 公开基线表对比（对标记录入报告） |
| 指标实现正确性 | 指标单测（固定排序→已知指标值）+ **金标 10 题回归** | 指标单测全绿；金标 10 题两次跑批指标完全一致（harness 无漂移） |
| 六档消融跑批 | `run_eval.py --suite main`：A–F × 自建题集 | 每档×每题结果落 t_eval_result；断点续跑验证（杀进程重跑不重复计费） |
| 扩展消融 | D 档 × gen_model 三模型（抽样 50 题） | glm/kimi/deepseek 对比数据入表 |
| 消融报告 | `reports/ablation.md` | 总表（六档×指标×bootstrap 95% CI）+分题型+归因分布 F0–F6+每模块一句话结论；数字可复核 |
| judge 校准 | 抽样 50 题人工对齐报告 | judge 与人工一致率 ≥80%（MT-Bench 参考线）；未达标则调 prompt 重校 |
| 回归 | `python -m pytest -q` 双端 | 196 存量+新增全绿；`--smoke` 不回归 |
| 里程碑 | commit（每步）+ `git tag m5` + push 双端 | 双端同步 |

## 2. 现状调查（2026-11-13）

| 项 | 现状 | 结论 |
|---|---|---|
| 题集 | 仅 20 道冒烟题（m3-smoke-v1，含 gold_hint/中英对照 3 对/不可答 4）；正式评测集未建 | 5.1 首建；冒烟题 origin=smoke 并入 |
| 出题原料 | 11 篇 parsed 产物齐（markdown/structured_content/doc.json）+ 论文库分类（M4） | VLM 出题原料充足 |
| 评测表 | t_eval_result 已建（M2 先建结构） | 直接用 |
| 归因原料 | trace JSONL 按 F0–F6 设计（M3），M4 增 model/empty_content 字段 | attribution 直接消费 |
| 指标资产 | 引用解析器（citations.py 四类兼容）、t_rerank_cache、--profile 机制 | metrics 聚焦新增计算 |
| QASPER | 官方页 403/HF 不可达〔预研记录〕；数据获取路径需 5.0 实测（备选：val 集+镜像/直链） | 5.0 首项确认 |
| BEIR | zip 直链可达（预研核实）；SciFact+NFCorpus 规模已知 | 半天接入 |
| judge | ctx_model=deepseek-v4-flash（便宜），与生成模型天然分离 | 校准纪律按调研 §2.4 |
| 敏感面 | S4-11 图片读侧越界（pipeline._load_image_blob 绝对路径放行） | 5.0 顺手修 |

## 3. 技术方案（关键决策；[K]/[L]=m5-eval-survey 来源编号）

| # | 决策 | 方案 | 被否方案与理由 |
|---|---|---|---|
| K1 | **题集 schema 与分层** | JSONL：q_id（分层编码）/type/lang/question/ref_answer/gold[{doc_id,page,chunk_id}]/answerable/difficulty(direct\|synthesis)/pair_of/origin/gold_hint。~185 题=可回答 150（文本 50/图表 50/表格 50）+不可答 15+负面 20（噪声 10/反事实 10，RGB 维度 [K8]）。分层保证：11 篇每篇 ≥8、中英对照 ~15 对、每类 direct/synthesis 两档 | 不分层：结论无法按维度拆解（PRD 要求分题型报告）；只测"答案对不对"不测检索：归因无从谈起 |
| K2 | **出题管线**（dataset.py） | VLM 读 parsed 产物按题型模板出候选（每篇每类 6–8）；自动预筛：相似去重+ref_answer 关键句在 gold chunk 原文包含性校验；**BM25 伪题检测**（gold 检索分远超第二名=字面重叠题→重写）；不可答=反事实构造（改数字/年份/拼凑/不存在概念）；**s15 教训写入出题 prompt**（禁止出"答案只在图内数字"的题） | 纯人工出题：165 题工作量不可行；纯 VLM 无闸：质量不可控 |
| K3 | **人审分批** | 先出 1 篇 ~15 题试审批（校准出题质量+审核标准）→ 用户过目 → 放量到全量 → 逐题审核报告（题目/ref_answer/gold 原文并排 markdown）→ 定稿 v1.0 | 一次性全量出题：质量偏了返工 165 题 |
| K4 | **QASPER 接入** | 5.0 实测获取路径（官方/HF/镜像备选）；优先 test 集按论文分层抽样 60–100（多段文本/图表/不可答≈8:1.5:1），test 答案不公开则退 val（1,005 题）；arXiv 抓对应论文 PDF→走 4.8 论文库入库管线→题目映射；**评测口径=官方 Answer-F1（多参考取 max）+Evidence-F1** [K1] | 自编学术题：无外部效度；整集 1,451 题：成本不可行 |
| K5 | **指标自实现**（metrics.py） | 检索：recall@k（**TREC 分母声明**）+Success@k+nDCG@10（**log2 公式注明**）+MRR+RAGAS context_precision（AP 口径）；生成：**Answer-F1**+**faithfulness 自实现**（答案拆原子陈述→逐条 NLI vs 被引 chunk 拼接，ctx_model verdict 0/1）+answer relevancy（反向 3 问嵌入余弦）；**引用：ALCE 口径 recall（被支持句占比）+precision（必要性检验）**；中文切句自备（正则+句号规则，NLTK 是英文规则 [L6]） | 引 RAGAS/DeepEval 框架：依赖重+黑盒，四指标结构极简自实现可控（调研 §2.1 [L1]–[L4]）；nDCG 不注明公式：横向比较失真 |
| K6 | **judge 校准** | judge=ctx_model（deepseek，与生成模型分离防自偏好）；二值 verdict+reason（可审计可算 kappa）；**抽样 50 题人工对齐，目标 ≥80%**（MT-Bench 参考线 [L9]）；位置交换鲁棒性抽检 | judge=生成模型自己：自偏好污染；不校准直接用：数字不可信 |
| K7 | **统计** | 配对二元（可答/拒答对错）→McNemar；连续指标→bootstrap 95% CI（按题重采样 1000 次）[L10][L11]；全部对比报 p 值+CI | 单点比较不报显著性：评审批评点（Dror 协议） |
| K8 | **跑批架构**（ablation.py+run_eval.py） | 幂等断点续跑：结果键=(q_id, profile, model) 落 t_eval_result，重跑跳过已完成（杀进程重跑不重复计费）；套件：main=A–F×自建题集；qasper=D 档×QASPER 子集；gen_model=D 档×50 题抽样×三模型；跑前额度预检+降级率随 D 档记录（J-1） | 一次性全跑：中途失败全废；无额度预检：跑一半破产 |
| K9 | **归因**（attribution.py） | 消费 trace JSONL 定位首个失败环节：F0 出题错（gold 未命中但 ref_answer 支持）/F1 解析缺失/F2 召回缺失（gold chunk 不在融合池）/F3 融合错排/F4 重排伤害（融合池有→重排后丢）/F5 生成失败/F6 兜底误触发 | 逐题人肉归因：165×6 不可行 |
| K10 | **报告结构** | reports/ablation.md：总表（六档×指标×CI）→分题型→QASPER/BEIR 外部基准节→归因分布→gen_model 对比→每模块一句话结论 | 只堆数字无叙事：面试讲不出 |
| K11 | **S4-11 顺手修** | pipeline._load_image_blob 绝对路径放行改为包含性校验（S4 报告建议 M5 首项） | 带病进评测 |

## 4. 变更清单（文件级）

| 动作 | 文件 | 职责 |
|---|---|---|
| 修改 | doclens/pipeline.py | S4-11 图片路径包含性校验（K11） |
| 新增 | doclens/eval/__init__.py、dataset.py（K2 出题管线）、metrics.py（K5）、stats.py（K7）、attribution.py（K9）、ablation.py（K8 跑批） | 评测模块 |
| 新增 | scripts/run_eval.py、scripts/eval_qasper.py、scripts/eval_beir.py、scripts/eval_review_report.py | 入口：一键跑批/QASPER 接入/BEIR 旁测/人审报告生成 |
| 新增 | data/eval/dataset_v1.jsonl、qasper_subset.jsonl（版本化；data/ gitignore 需加例外——沿 smoke_queries.json 先例） | 题集资产 |
| 修改 | scripts/init_db.py | t_eval_result 补列（如 model 维度——若现有列不够） |
| 新增 | tests/test_metrics.py、test_stats.py、test_dataset.py | 指标固定用例/出题预筛逻辑 |
| 修改 | requirements.txt（beir 或直接解析 zip——K4 落地定） | 依赖 |
| 新增 | reports/ablation.md、reports/eval_review_*.md（人审报告） | 产出 |
| 修改 | CHANGELOG.md、AGENTS.md（收官） | 记录 |

## 5. 分步任务（执行顺序）

| 步 | 任务 | 验收 | 依赖 |
|---|---|---|---|
| 5.0 | **前置**：QASPER 获取路径实测（官方/镜像/直链）+S4-11 图片越界顺手修+额度预检 | 数据文件可下载；修复单测绿 | 无 |
| 5.1 | **出题管线+试审批**：dataset.py（K2）+1 篇 ~15 题试审报告 | 试审批产出；BM25 伪题检测生效 | 5.0 |
| 5.2 | **试审反馈→放量出题**：全量候选→预筛→`data/eval/dataset_v1.jsonl`+人审报告 | 你过目定稿 v1.0（~185 题） | 5.1 |
| 5.3 | **QASPER 接入**：数据下载+论文抓取（arXiv）→ 论文库管线入库+题目映射+子集 jsonl | 对应论文可问答；映射无歧义 | 5.0 |
| 5.4 | **BEIR 旁测接入**：SciFact+NFCorpus 下载+检索器挂接 | nDCG@10 产出 | 无（可与 5.1–5.3 并行） |
| 5.5 | **指标三件套**：metrics.py（K5）+stats.py（K7）+attribution.py（K9）+单测 | 指标单测绿；金标 10 题回归一致 | 5.2 |
| 5.6 | **跑批**：main 套件（A–F×185）+QASPER（D 档）+gen_model（抽样 50）+断点续跑实测 | t_eval_result 全量；断点续跑验证 | 5.3/5.5 |
| 5.7 | **报告**：reports/ablation.md（K10）+judge 校准报告 | 数字可复核；叙事完整 | 5.6 |
| 收尾 | S3+S4 双审（评测面轻量）+CHANGELOG+tag m5+主计划补记+AGENTS 翻页 | 双端同步 | 5.7 |

## 6. 测试策略（普通实现）

- 指标计算：**固定小用例**（手工构造排序与相关等级→断言指标值到小数点后 4 位）——全项目测试密度最高处；F1/faithfulness/citation 口径各配边界用例（空引用/越界/多引用必要性）。
- 出题管线：预筛逻辑（去重/包含性/BM25 伪题判定）纯函数单测。
- 归因：构造 mini trace 场景断言 F 判定。
- 集成：金标 10 题回归（评测 harness 自身防漂移）+QASPER 小样端到端。
- LLM judge 不进单测；跑批走容器真实链路。

## 7. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| VLM 出题质量差（平凡/争议题） | 1 篇试审批先校准（K3）+BM25 伪题检测+人审兜底 | 试审不达标→改 prompt 重出该篇 |
| 人审时间不可控（165 题） | 分批（试审→放量）+审核报告并排展示降低单题耗时 | 全量未审完→先跑已审子集（≥100 题即有统计意义，CI 记录） |
| QASPER 数据拿不到（403/HF 不可达） | 5.0 多路径实测（官方 zip/HF 镜像/镜像站）；仍不可得→外部基准降级为 BEIR 单层（检索旁测保留） | L2 缺位不阻塞 L1/L3（三层可独立交付） |
| 跑批成本 | 缓存复用（嵌入/重排）+额度预检+gen_model 抽样 50 题 | 砍 gen_model 消融与 QASPER 规模（60 题） |
| 归因失准 | trace F0–F6 字段 M3 已备；attribution 用金标 10 题回归验证 | 归因分布仅作参考不进结论 |
| 指标口径争议 | 全部口径注明出处（ir-measures/RAGAS/ALCE）；公式写进报告 | 公式切换留参数位（dcg log2/exp-log2） |
| 跑批中断 | 断点续跑幂等（K8） | 无需回滚 |
| 成本/额度 | 额度预检入 5.0；方舟控制台观察纪律 | 砍 F 档（P1 惯例） |

## 8. 敏感代码判定

**低敏感（S3 常规+S4 简查）**：评测面不新增对外攻击面（跑批不对外、judge 用既有 key 纪律）；QASPER 论文经 4.8 论文库入库走既有穿越守卫。data/eval 题集入库注意 gitignore 例外配置（沿 smoke_queries.json 先例）。

## 9. 执行命令

```bash
# —— 容器内（默认拓扑）——
python -m pytest -q
python scripts/run_eval.py --suite main            # A–F × 自建题集（断点续跑）
python scripts/run_eval.py --suite qasper          # D 档 × QASPER 子集
python scripts/run_eval.py --suite gen_model       # D 档 × 三模型 × 50 题
python scripts/eval_beir.py                        # BEIR 检索旁测
python scripts/eval_review_report.py               # 人审报告生成

# —— 本机（可选）——
# 隧道 13306/16333/8000 同 M4（见 AGENTS.md）
```

---
## 确认门记录（S2 开始前填写）
- 批准时间：
- 批准指令原文：
- TDD：否（普通实现；metrics 纯逻辑以固定用例单测保证，是否升级 TDD 由批准指令决定）
