# AI 开发完整工作流（Cline / Roo Code 规则片段）

> 保存为 `.clinerules/ai-workflow.md`（Roo Code 也可放 `.roo/rules/ai-workflow.md`）。

## 流程

1. **规划**：调查框架、构建与测试命令、相关模块，产出 `specs/plans/<slug>.plan.md`（验收标准、现状、方案与被否方案、文件级变更清单、分步任务、测试策略、风险、敏感代码判定、执行命令）。需求模糊时先产出 `specs/prds/<slug>.prd.md`（仅 what/who/why）。规划阶段**禁止修改源码**。
2. **确认门**：写完计划**暂停请求用户批准**。
   - 批准含 TDD 指令（“严格使用 tdd-workflow 实施”）→ 执行 TDD：先写失败测试（RED）→ 最小实现（GREEN）→ 重构 → 覆盖率 ≥80%。
   - 仅 `yes/ok` → 普通实现 + 关键路径测试。
3. **代码审查**：审查者视角查正确性、边界、并发、一致性、规范、测试有效性；分级 Blocker/Major/Minor + `文件:行`，写 `specs/reviews/<slug>.review.md`；Blocker 修复后重跑测试。
4. **安全复查（仅敏感代码）**：认证/授权/Token、外部 API/Webhook/SSRF、敏感数据(PII/支付/密钥)、上传下载、反序列化、SQL/命令拼接、依赖变更 → OWASP 逐项审查，写 `specs/reviews/<slug>.security.md`；非敏感写明跳过原因；不通过不得收尾。
5. **收尾**：修构建/lint/类型错误（禁 `@ts-ignore`/`eslint-disable`/删测试；连续 3 次失败即停并报告）→ `git diff` 与计划核对 → PR 描述经确认后创建。

禁止：确认前改代码、修改断言掩盖失败、擅自 push、敏感代码跳过安全复查。
