# AI 开发完整工作流（Copilot 指令片段）

> 追加到 `.github/copilot-instructions.md`，或放到 `.github/instructions/ai-workflow.instructions.md`（带 `applyTo: "**"` 头）。

任何**写代码**任务（新功能、修 bug、重构、补测试）按以下流程；纯问答不启用。

1. **规划先行，不碰代码**：先调查项目（框架/构建命令/测试命令/相关模块），产出 `specs/plans/<slug>.plan.md`（验收标准、现状、方案与被否方案、文件级变更清单、分步任务、测试策略、风险、**敏感代码判定**、执行命令）。需求模糊时先产出 `specs/prds/<slug>.prd.md`（只答 what/who/why）。
2. **确认门**：计划写完必须**停下等用户批准**，不得自动开始实现。
   - 用户批准并带 TDD 指令（如「严格使用 tdd-workflow 实施」）→ 走 TDD；
   - 仅回复 `yes/ok` → 不走 TDD，按计划实现，关键路径补测试。
3. **TDD**（仅带指令）：RED（先写测试并确认失败）→ GREEN（最小实现）→ 重构（全绿）→ 覆盖率 ≥80%。禁止为过关修改/跳过断言。
4. **代码审查**：以审查者视角检查正确性、边界、并发、设计一致性、规范、测试有效性；问题分级 Blocker/Major/Minor 并标 `文件:行`，写入 `specs/reviews/<slug>.review.md`；Blocker 修复后重跑测试。
5. **安全复查（仅敏感代码）**：认证/授权/会话/Token、外部 API/Webhook、敏感数据(PII/支付/密钥)、上传下载、反序列化、SQL/命令拼接、依赖变更 → 按 OWASP 逐项审查并写 `specs/reviews/<slug>.security.md`；非敏感须写明跳过原因；不通过不得收尾。
6. **收尾**：先修构建/lint/类型错误（禁 `@ts-ignore`、`eslint-disable`、删测试）；核对 diff 与计划一致；PR 描述须经用户确认后才创建。

命令话术：`/ai-workflow`、`/plan-prd`、`/plan`、`tdd-workflow`、`/code-review`、`/security-scan`、`/build-fix`、`/pr`。
