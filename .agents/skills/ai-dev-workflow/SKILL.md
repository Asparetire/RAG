---
name: ai-dev-workflow
description: Use when writing or changing code for a feature, bug fix, refactor, or tests, or when the user asks for a full workflow / plan-first / TDD / code review / security scan routine; runs requirement def -> plan -> approval gate -> TDD or plain implement -> code review -> security review when sensitive -> build fix and PR. Also tells how to install this skill into Claude Code, Codex, Cursor, Copilot, Windsurf, Gemini CLI, Cline, and DeepSeek Harness.
---

# AI 开发完整工作流（Code Workflow）

> 依据「AI 开发完整工作流」流程图落地：需求定义 → 实现规划 → 可视化确认（可选）→ TDD 实现 → 代码审查 → 安全专项复查（按需）→ 收尾（build-fix / PR）。
> 本文件是唯一的规范来源；`/ai-workflow` 命令与各工具适配脚本只是本文件的入口。

## 适用范围

当用户提出以下任一诉求时使用本技能：

- 开发新功能 / 修复缺陷 / 重构 / 编写测试；
- 说「按工作流来」「走完整流程」「写代码流程」；
- 输入 `/ai-workflow <任务描述>`。

不适用：纯问答、纯解释代码、只跑一下命令。

---

## 硬规则（先读这段，违反即视为未按流程执行）

1. **不碰代码的规划阶段**：需求定义、实现规划阶段只产出文档，**不许改动任何源码/测试文件**。
2. **确认门**：实现规划写完后**停在确认门**等待用户批准，不得自动开始实现。
3. **TDD 依赖显式指令**：用户批准时若**带了 TDD 指令**才走 RED→GREEN→重构→覆盖率；只回 `yes`/`proved`/`ok` 等而不带指令 → **不走 TDD**，按普通实现（先写最小可用代码 + 关键测试）。
4. **敏感代码必须安全复查**：涉及认证 / 授权 / 支付 / 外部 API 调用 / 敏感数据（PII、密钥、token）时，跳过代码审查后的普通路径，强制走安全专项复查。
5. **每步有产物**：文档落到 `specs/` 下（见目录约定），并在结束时汇报产物路径与摘要，不要只口头说“做完了”。
6. **默认不执行破坏性操作**：不擅自 `git push`、不 `git reset --hard`、不删用户文件；开 PR 必须经用户确认。
7. **明确失败时如实报告**：测试/构建失败不许“顺手”改测试或注释断言来掩盖，除非用户在计划里批准。

---

## 状态机与产物

```
S0 需求定义(可选) → S1 实现规划 → [确认门 G1]
  ↗ (带 TDD 指令)        ↘ (不带指令：普通实现)
S2 TDD 实现 ─────────────────────────┐
   RED→GREEN→重构→覆盖率              │
                                    ▼
                         S3 通用代码审查
                                    │
                        ┌───────────┴───────────┐
                    普通代码                  敏感代码
                 (跳过安全复查)          S4 安全专项复查
                        └───────────┬───────────┘
                                    ▼
                     S5 收尾：/build-fix [按需] → /pr 开 PR
```

| 阶段 | 命令名（与图一致） | 产物 | 是否必须 |
|---|---|---|---|
| S0 需求定义 | `/plan-prd` | `specs/prds/<slug>.prd.md` | 可选（需求模糊时） |
| S1 实现规划 | `/plan` | `specs/plans/<slug>.plan.md` | 必须 |
| G1 确认门 | 用户在对话中批准（+/plan-canvas 可视化批准） | 批准记录写入 plan 文末 | 必须 |
| S2 TDD 实现 | 技能 `tdd-workflow`（非命令，需手动指定） | 代码 + 测试 + 覆盖率数据 | 条件：用户带 TDD 指令 |
| S3 通用代码审查 | `/code-review` | `specs/reviews/<slug>.review.md` | 必须 |
| S4 安全专项复查 | `/security-scan` | `specs/reviews/<slug>.security.md` | 仅敏感代码 |
| S5 收尾 | `/build-fix`、`/pr` | 修复提交 / PR 链接 | 按需 / 必须汇报 |

**slug 规则**：任务名小写 + 连字符，如 `user-login-otp`。

**目录约定**：若项目已有约定（`.claude/prds`、`.claude/plans`、`docs/`）则**沿用项目既有目录**；否则用 `specs/{prds,plans,reviews}/`。路径必须在 plan 中写明，一旦确定不再更换。

---

## 阶段细则

### S0 需求定义（可选）

**触发**：需求目标不清、验收标准不可量化、或用户明确要求先写 PRD。

1. 用 3–5 个问题澄清（一次性问完，不要挤牙膏）：谁用、什么场景、成功标准、边界/不做什么、约束（兼容性、性能、安全等级）。
2. **只回答 what/who/why，不碰 how**（不写实现方案、不选型、不设计接口）。
3. 产出 `prd.md`，结构：

```markdown
# <功能名> PRD
## 背景与目标
## 用户与场景
## 需求清单（R1..Rn，每条附可验收标准）
## 非目标（明确不做）
## 约束与风险
## 待确认问题
```

4. 向用户确认 PRD 是否可作为规划依据（一次明确提问，问完即停）。

### S1 实现规划

1. 先探测项目事实（不要凭猜）：语言/框架、包管理器、构建与测试命令、目录结构、既有代码风格、相关已有模块。
2. 产出 `plan.md`，**必须包含**：

```markdown
# <功能名> 实现计划
## 1. 目标与验收标准（可执行验证）
## 2. 现状调查（代码位置、复用点、约束）
## 3. 技术方案（关键决策 + 被否方案 + 理由）
## 4. 变更清单（文件级：新增/修改/删除，含职责）
## 5. 分步任务（每步：做什么、验收方式、预计影响面）
## 6. 测试策略（单测/集成/边界，TDD 用例列表，若走 TDD）
## 7. 风险与回滚
## 8. 敏感代码判定（是/否 + 依据）
## 9. 执行命令（构建、测试、覆盖率）
---
## 确认门记录（S2 开始前填写）
- 批准时间：
- 批准指令原文：
- TDD：是 / 否
```

3. **停在确认门**：输出计划摘要（≤15 行）+ 文档路径 + 一句明确的批准提示：

> 「计划已生成：`specs/plans/<slug>.plan.md`。确认后可回复：
> `yes, 严格使用 tdd-workflow 实施`（走 TDD）
> 或 `yes`（不走 TDD，按普通实现）」

4. 等用户回复，**不要继续改代码**。

5. 收到批准后判定：

| 用户回复形态 | 判定 |
|---|---|
| `yes / ok / 批准` + 提到 TDD、`tdd-workflow`、先写测试 | **走 TDD**，写入确认门记录 |
| 仅 `yes / proved / ok / 可以` | 不走 TDD，普通实现 |
| 修改意见 | 回到 S1 修订计划，**再次暂停**等批准 |

### S1.5 可视化确认（可选，`/plan-canvas`）

- 仅当工具支持浏览器内计划审阅（如 plan-canvas / 人工审批面板）时使用。
- 产物：在浏览器/计划面板中打开 `plan.md` 供审阅；用户在面板点 **Approve plan** 完成批准（无面板时跳过本阶段）。
- **顺序要求（重要）**：先在侧栏/对话发送 TDD 指令，**再**点 Approve plan；否则批准不会携带 TDD 指令，将按普通实现执行。
- 若工具无可视化面板：跳过本阶段，直接用对话批准。

### S2 测试驱动实现（技能 `tdd-workflow`，手动指定）

仅在确认门判定「走 TDD」时执行，严格四段式：

1. **RED**：先为计划中的第 N 条用例写测试 → 运行 → **必须看到失败**，记录失败输出；不得写实现后再补测试。
2. **GREEN**：写让测试通过的最小实现，不提前加需求外功能。
3. **重构**：测试保持全绿的前提下消除重复、拆分函数、统一命名；每轮重构后跑全量测试。
4. **覆盖率**：跑覆盖率，**新增/改动代码行覆盖率 ≥ 80%**；缺口要么补测试，要么在 plan 中书面说明豁免理由。

约束：
- 一次只推进一个用例循环，循环间可短汇报（一行）。
- 测试失败**不许**改断言/跳过测试来“过关”；如需调整断言，向用户说明原因。
- 环境无法写测试（例如无测试框架）时：先补最小测试设施，这本身作为 plan 一步。

### S2' 普通实现（不带 TDD 指令）

- 按 plan 分步实现，每步结束跑既有测试；新增逻辑至少补关键路径测试。
- 其余同 S2 的约束（不改断言掩盖失败、覆盖率建议 ≥80% 用于新增代码）。

### S3 通用代码审查（`/code-review`）

以**审查者视角**逐文件核对（尽量独立于实现上下文，必要时用子代理/新会话审查）：

- 正确性：边界、空值、错误路径、并发/异步、资源释放。
- 逻辑与设计：与 plan 一致、无隐藏副作用、无过度设计、复用既有能力。
- 规范：项目风格、命名、类型、日志、异常策略、无调试残留。
- 测试：断言是否真有效、是否覆盖 plan 的用例。
- 结论分级：`Blocker / Major / Minor / Nit`，每条给出文件:行号 + 修复建议。

产出 `review.md`（结论 + 问题清单 + 处理情况）。**Blocker 必须修复后重跑测试**。

### 敏感代码判定 → S4 安全专项复查（`/security-scan`）

判定为**敏感**（任一命中）：

- 认证、授权、会话、JWT/OAuth、密码、多因素；
- 外部 API / Webhook / 第三方 SDK 调用、网络出口、SSRF 风险点；
- 敏感数据：PII、联系方式、证件、定位、支付、密钥、token、凭据、审计日志；
- 文件上传/下载、反序列化、SQL/命令拼接、模板渲染、权限相关配置；
- 依赖新增或升级、加密与哈希。

非敏感 → 跳过 S4，直接收尾（在 `review.md` 中写明“跳过安全复查：非敏感代码”）。

敏感 → 按 OWASP Top 10 与本项目技术栈逐项复查：
- 输入校验/输出编码、注入、鉴权失效、越权（横向/纵向）、IDOR；
- 认证流程（重放、限速、token 生命周期、存储位置）；
- 密钥与凭据是否硬编码/入日志/入仓库、.env 与环境隔离；
- 日志脱敏、错误信息不泄露内部细节；
- 传输与存储加密、TLS 校验、CORS/CSRF、Cookie 属性；
- 依赖漏洞（可跑 `npm audit` / `pip-audit` / `cargo audit` 等，命令取自项目）。

产出 `security.md`，结论：`通过 / 有条件通过（需修复项）/ 不通过`。**不通过不得进入收尾。**

### S5 收尾

1. `/build-fix`（按需）：构建/类型检查/lint 失败时，定位并修复；修复后重跑构建 + 测试。连续修复 3 次仍失败 → 停下来报告现象与已尝试方案。
2. 变更自检：`git status` / `git diff --stat` 核对改动文件是否与 plan 的变更清单一致，有无误改。
3. `/pr`：生成 PR 描述（目标、方案、测试与覆盖率、审查结论、安全结论、风险与回滚），**询问用户确认后**再创建 PR（有 `gh` 才用 `gh pr create`，否则输出可复制的 PR 文本）。
4. 最终汇报格式：

```
✅ 工作流完成：<slug>
- PRD: specs/prds/<slug>.prd.md（若跳过写明）
- 计划: specs/plans/<slug>.plan.md（TDD: 是/否）
- 审查: specs/reviews/<slug>.review.md（Blocker 0 / Major n）
- 安全: 敏感 / 非敏感（结论）
- 测试: x passed, 覆盖率 y%
- 变更: n 文件 (+a/-b)
- PR: <链接> 或 未创建
```

---

## 常用触发话术（供用户/上层代理使用）

| 想做什么 | 说 |
|---|---|
| 完整流程 | `/ai-workflow 实现 <需求>` |
| 只做需求 | `/plan-prd <需求>` |
| 只做计划 | `/plan <需求>` |
| 批准并走 TDD | `yes，请严格使用 tdd-workflow 技能实施` |
| 批准但不走 TDD | `yes` |
| 只审查 | `/code-review` |
| 只安全扫描 | `/security-scan` |
| 修构建 | `/build-fix` |
| 开 PR | `/pr` |

---

## 各工具接入对照

| 工具 | 接入方式 | 命令目录 |
|---|---|---|
| Claude Code | 技能放 `.claude/skills/ai-workflow/`；命令放 `.claude/commands/` | `.claude/commands/*.md` |
| Codex CLI / AGENTS.md 系 | 把 `SKILL.md` 内容并入 `AGENTS.md`（或用 `adapters/AGENTS.md.append.md`） | 无命令层，用触发话术 |
| Cursor | `.cursor/rules/ai-workflow.mdc`（alwaysApply 规则） | 规则文件 |
| GitHub Copilot | `.github/copilot-instructions.md` | — |
| Windsurf | `.windsurf/rules/ai-workflow.md` | — |
| Gemini CLI | `GEMINI.md` | — |
| Cline / Roo Code | `.clinerules/ai-workflow.md` | — |
| 通用（任意 Agent） | 项目根 `AI_WORKFLOW.md` + 在规则文件中加一行“写代码前先读 AI_WORKFLOW.md” | — |
| DeepSeek Harness (DSH) | 技能目录 `<skills 路径>/ai-workflow/SKILL.md` | `commands/` 作为话术参考 |

安装脚本：`scripts/install.ps1`（Windows）/ `scripts/install.sh`（macOS/Linux），见其 `-h` 输出。

---

## 反模式（禁止）

- 计划没批准就开始改代码；
- 用户只回 `yes` 却擅自走 TDD（或反之，带了 TDD 指令却跳过 TDD）；
- 可视化确认时先点 Approve、后发指令；
- 用“改测试/删断言/加 try-catch 吞错”让流程变绿；
- 敏感代码跳过安全复查；
- 审查只写“看起来没问题”，不给文件行号；
- 把调试打印、临时开关、mock 数据留在提交里。

---

## 资源索引

- 命令细则：commands/（ai-workflow、plan-prd、plan、plan-canvas、tdd-workflow、code-review、security-scan、build-fix、pr）
- 各工具规则片段：dapters/`n- 安装脚本：scripts/install.ps1（Windows）、scripts/install.sh（macOS/Linux）
- 安装说明与目录结构：README.md`n- 原始流程图：workflow-diagram.jpg`n