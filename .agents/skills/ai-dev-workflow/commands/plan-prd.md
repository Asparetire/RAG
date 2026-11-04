---
description: 需求定义（可选）——澄清 what/who/why 并产出 PRD，不涉及实现方案
argument-hint: <需求描述>
allowed-tools: Read, Grep, Glob, Write, AskUserQuestion
---

# /plan-prd — 需求定义

用户需求：$ARGUMENTS

按技能 **ai-workflow** 的 **S0 需求定义** 执行。

## 步骤

1. 一次性提出 3–5 个澄清问题并**等待回答**：谁用、什么场景、成功标准（可量化）、边界（明确不做什么）、约束（兼容性/性能/安全等级）。
2. 只回答 what / who / why。**禁止**写实现方案、选型、接口设计、改动文件清单。
3. 确定 slug（小写连字符）与产物路径（沿用项目既有目录，否则 `specs/prds/<slug>.prd.md`）。
4. 按 SKILL.md 的 PRD 模板写出文件，需求清单编号 R1..Rn，每条附可验收标准。
5. 输出：PRD 路径 + ≤10 行摘要 + 「PRD 是否可作为规划依据？」的确认问题。

## 禁止

- 在 PRD 里出现技术方案、代码片段、任务拆分。
- 回答完问题后自动进入实现规划（必须等用户确认）。
