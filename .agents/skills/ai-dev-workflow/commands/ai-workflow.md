---
description: 启动 AI 开发完整工作流（需求定义 → 实现规划 → 确认门 → TDD 实现 → 代码审查 → 安全复查 → 收尾）
argument-hint: <需求描述>
allowed-tools: Read, Grep, Glob, Write, Edit, Bash
---

# /ai-workflow — 完整工作流入口

用户需求：$ARGUMENTS

严格按技能 **ai-workflow**（`skills/ai-dev-workflow/SKILL.md`）执行，不要跳步。

## 当前要做的

1. 读取 `SKILL.md` 的「硬规则」「状态机与产物」「阶段细则」三节。
2. **判定起始阶段**：
   - 需求模糊 / 用户指定先写 PRD → 先做 S0（`/plan-prd`）；
   - 需求明确 → 直接 S1（`/plan`）。
3. 执行 S0/S1 的产出要求，写出文档（路径按 SKILL.md 的目录约定），**不改任何源码**。
4. 写完后**停在确认门 G1**，输出：
   - 计划摘要（≤15 行）
   - 产物路径
   - 批准提示（两种回复格式：`yes, 严格使用 tdd-workflow 实施` / `yes`）
5. 等待用户回复，**到此为止**，不要继续实现。

## 禁止

- 在确认门前创建/修改源码或测试文件。
- 自行决定走不走 TDD（必须由用户批准的指令决定）。
- 省略敏感代码判定（plan 第 8 节必填）。

若用户回复批准：按 `/plan` 之后的流程继续（TDD 或普通实现 → `/code-review` → 敏感则 `/security-scan` → `/build-fix` 按需 → `/pr`），全部结束后按 SKILL.md 的「最终汇报格式」汇报。
