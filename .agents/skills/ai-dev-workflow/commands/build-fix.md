---
description: 修复构建/类型检查/lint 错误——按需执行
argument-hint: [错误输出或命令]
allowed-tools: Read, Edit, Bash, Grep, Glob
---

# /build-fix — 修构建错误

输入：$ARGUMENTS（缺省：运行项目构建命令）

按技能 **ai-workflow** 的 **S5 收尾 · /build-fix** 执行。

## 步骤

1. 从项目配置取构建命令（`npm run build`、`tsc --noEmit`、`cargo check`、`go build ./...`、`mvn -q compile` 等），原样运行并保存完整错误。
2. 按错误类别修，**一次只修一类**最小问题：
   - 类型错误 → 补类型/收窄联合，不 `as any` / `# type: ignore` 掩盖；
   - 未定义符号 → 补 import 或改调用点；
   - lint → 按项目规则修，不擅自全局禁用；
   - 依赖/版本 → 读错误定位，必要时装缺失依赖并说明。
3. 每修一批立即重跑构建；全绿后**再跑全量测试**。
4. 连续 3 次修复仍失败 → 停止，报告：错误原文、已尝试方案、疑似根因、需要用户决策的点。

## 禁止

- 用 `@ts-ignore`、`eslint-disable`、删除测试、放宽 tsconfig 来“通过”。
- 顺带重构或改计划外文件（如确有必要，先说明）。
