# AI 开发完整工作流（AGENTS.md 片段）

> 工具无关的可移植版本，可直接追加到项目根的 `AGENTS.md` / `AI_WORKFLOW.md`。
> 完整细则见 `skills/ai-dev-workflow/SKILL.md`。

## 何时启用

写代码类任务（新功能、修 bug、重构、补测试）默认按本流程；纯问答/只跑命令不启用。

## 流程

1. **需求定义（可选，`/plan-prd`）**：需求模糊时先澄清，产出 `specs/prds/<slug>.prd.md`，**只答 what/who/why，不碰 how**。
2. **实现规划（`/plan`）**：先调查项目事实，产出 `specs/plans/<slug>.plan.md`，必须含：验收标准、现状、方案与被否方案、文件级变更清单、分步任务、测试策略、风险、**敏感代码判定**、执行命令。
3. **确认门**：写完计划**停下等批准**，不得自行开始实现。
   - 用户回 `yes` + TDD 指令（如“严格使用 tdd-workflow 实施”）→ 走 TDD；
   - 用户只回 `yes / proved / ok` → 不走 TDD（普通实现 + 关键测试）。
   - 有可视化计划面板时：**先发 TDD 指令，再点 Approve plan**。
4. **TDD 实现（仅带指令时）**：RED（先写测试并看到失败）→ GREEN（最小实现）→ 重构（保持全绿）→ 覆盖率 ≥80%（缺口须书面豁免）。不许改断言/跳过测试过关。
5. **通用代码审查（`/code-review`）**：审查者视角查正确性、边界、并发、设计一致性、规范、测试有效性；结论分 Blocker/Major/Minor，附 `文件:行`；写 `specs/reviews/<slug>.review.md`。Blocker 修复后重跑测试。
6. **敏感代码判定 → 安全专项复查（`/security-scan`，仅敏感触发）**：
   敏感 = 认证/授权/会话/JWT、外部 API/Webhook/SSRF、敏感数据（PII/支付/密钥/token）、文件上传下载、反序列化、SQL/命令拼接、依赖新增升级。
   逐项过 OWASP：注入、越权/IDOR、认证流程、凭据管理、数据保护与日志脱敏、CORS/CSRF/Cookie、路径穿越、依赖审计、第三方调用。结论 通过/有条件通过/不通过；不通过不得收尾。
   非敏感 → 跳过，并在 review 中写明“跳过安全复查：非敏感代码”。
7. **收尾**：`/build-fix`（构建/类型/lint 失败时按需修复，禁 `@ts-ignore`/`eslint-disable`/删测试通过，连续 3 次失败即停并报告）→ 核对改动与计划清单一致 → `/pr`（生成 PR 描述，询问确认后创建）。

## 硬规则

- 确认门前只产出文档，不改源码。
- TDD 与否由用户批准指令决定，不得自作主张。
- 敏感代码必须安全复查。
- 不擅自 `git push` / `reset --hard` / 删用户文件。
- 结束时汇报产物路径 + 摘要（PRD/计划/审查/安全/测试覆盖率/变更统计/PR）。

## 触发话术

`/ai-workflow <需求>` · `/plan-prd` · `/plan` · `/plan-canvas` · `tdd-workflow` · `/code-review` · `/security-scan` · `/build-fix` · `/pr`
