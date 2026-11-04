---
description: 在浏览器/计划面板中可视化审阅 plan.md 并完成批准（可选步骤）
argument-hint: <plan 文件路径，缺省为最新 specs/plans/*.plan.md>
allowed-tools: Read, Glob, Bash
---

# /plan-canvas — 可视化确认

目标计划：$ARGUMENTS（缺省时取 `specs/plans/` 下最新的 `*.plan.md`）

按技能 **ai-workflow** 的 **S1.5 可视化确认** 执行。

## 步骤

1. 找到 plan 文件并在浏览器中打开：
   - 若工具自带计划审阅面板（plan-canvas / 人工审批面板 / 预览视图），使用它；
   - 否则生成一份可直接浏览的 HTML（保留 plan 全文 + 目录锚点 + 风险与敏感判定高亮），用系统默认浏览器打开。
2. 提示用户在面板中审阅；可在面板上直接改计划，改完请用户保存回写 plan 文件。
3. **提醒顺序**：
   > 若要走 TDD，请**先在侧栏/对话发送指令**：`请严格使用 tdd-workflow（技能）实施`，**再**点击 `Approve plan`。先批后发指令会导致按普通实现执行。
4. 用户点击 `Approve plan` 后：把批准记录（时间、指令原文、TDD 是/否）写入 plan 文末「确认门记录」，然后进入 S2。

## 禁止

- 未收到批准指令就进入实现。
