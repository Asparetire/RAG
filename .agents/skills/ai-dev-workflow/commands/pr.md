---
description: 收尾——核对改动、生成 PR 描述并在确认后开 PR
argument-hint: [目标分支]
allowed-tools: Read, Bash, Grep, Glob
---

# /pr — 开 PR

目标分支：$ARGUMENTS（缺省：仓库默认分支）

按技能 **ai-workflow** 的 **S5 收尾 · /pr** 执行。

## 步骤

1. 自检：`git status` / `git diff --stat`，核对改动文件是否与 plan.md 第 4 节变更清单一致；多改/漏改要说明。确认无调试残留、无密钥、无临时文件。
2. 读取审查与安全结论（`specs/reviews/`）与测试覆盖率。
3. 生成 PR 文本：

```markdown
## 目标
## 方案（关键决策）
## 变更
## 测试
- 用例：n passed / n failed
- 覆盖率：新增代码 x%
## 审查
- 通用审查：Blocker 0 / Major n（已处理 n）
- 安全复查：<含义项结论> / 不适用（非敏感代码）
## 风险与回滚
## 关联
PRD / plan / review 文档路径
```

4. **先展示文本并询问用户确认**（是否开 PR、目标分支、是否 draft）。
5. 确认后：有 `gh` → `gh pr create --title ... --body-file <临时文件>`；否则推送分支（若用户同意）并输出可复制的 PR 文本与 compare 链接。
6. 汇报 PR 链接或“未创建（用户未确认/无 gh）”。

## 禁止

- 未经确认直接 `push` 或建 PR。
- 跳过漏改/多改的说明。
