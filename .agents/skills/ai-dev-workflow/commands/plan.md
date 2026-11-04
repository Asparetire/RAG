---
description: 实现规划——调查现状并产出 plan.md，然后停在确认门等待批准
argument-hint: <需求描述>（可引用已生成的 PRD）
allowed-tools: Read, Grep, Glob, Bash, Write, AskUserQuestion
---

# /plan — 实现规划（停在确认门）

需求：$ARGUMENTS

按技能 **ai-workflow** 的 **S1 实现规划** 执行。

## 步骤

1. **先调查再写**（不得凭空猜测）：
   - 语言/框架、包管理器、构建命令、测试命令、覆盖率命令（从 package.json / pyproject.toml / Cargo.toml / Makefile / CI 配置里读）；
   - 相关已有模块与可复用点（Grep 定位入口、类型、工具函数）；
   - 既有代码风格与测试框架。
2. 用 SKILL.md 的 plan.md 模板写出文件（9 节齐全，第 8 节「敏感代码判定」必须给出是/否 + 依据）。
3. 若存在 PRD，plan 的验收标准必须逐条对应 PRD 的 R1..Rn。
4. 输出 ≤15 行摘要 + 产物路径 + 明确的批准提示：

```
计划已生成：<path>
回复其中一种继续：
- yes，严格使用 tdd-workflow 实施   ← 走 TDD
- yes                              ← 不走 TDD
```

5. **停在确认门，等待用户回复。不要开始改代码。**

收到回复后的判定（写入 plan 文末「确认门记录」）：
- 带 TDD 指令 → 走 `/tdd`；
- 仅 yes/ok → 普通实现；
- 修改意见 → 修订 plan 后**再次暂停**。
