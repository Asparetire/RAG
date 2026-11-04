# AI 开发完整工作流（GEMINI.md 片段）

> 追加到项目根 `GEMINI.md`，或放进 `.gemini/` 配置引用。

写代码类任务（新功能、修 bug、重构、测试）必须遵循：

1. **需求定义（可选）**：需求模糊时先产出 `specs/prds/<slug>.prd.md`，只讲 what/who/why。
2. **规划**：先调查项目事实，产出 `specs/plans/<slug>.plan.md`（验收标准、现状、方案、文件级变更清单、分步任务、测试策略、风险、敏感代码判定、执行命令）。此阶段**不改源码**。
3. **确认门**：写完计划**停止并等待用户批准**。批准带 TDD 指令 → 走 TDD（RED→GREEN→重构→覆盖率≥80%）；仅 `yes` → 普通实现 + 关键测试。
4. **审查**：审查者视角，Blocker/Major/Minor + `文件:行`，写入 `specs/reviews/<slug>.review.md`；Blocker 修复后重跑测试。
5. **安全复查**：敏感代码（认证/授权/Token、外部 API、敏感数据、上传下载、反序列化、注入风险、依赖变更）必须做 OWASP 逐项审查并写 `specs/reviews/<slug>.security.md`；不通过不得收尾。
6. **收尾**：修构建错误（禁 `@ts-ignore`/`eslint-disable`/删测试）、核对 diff、PR 经确认后创建。

规则：禁确认前改代码；禁改断言掩盖失败；禁擅自 push。
