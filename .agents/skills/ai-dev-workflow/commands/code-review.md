---
description: 通用代码审查——按工程师审查视角检查正确性、逻辑、规范与测试有效性
argument-hint: [范围，缺省为本次改动]
allowed-tools: Read, Grep, Glob, Bash, Write
---

# /code-review — 通用代码审查

范围：$ARGUMENTS（缺省：`git diff` 相对主分支 + 未跟踪的新文件）

按技能 **ai-workflow** 的 **S3 通用代码审查** 执行。

## 步骤

1. 确定范围：`git status`、`git diff --stat`、必要时 `git diff <base>...HEAD`。
2. 以**审查者视角**逐文件检查（不要为自己刚写的代码找理由）：
   - 正确性：边界、空值、错误路径、并发/异步、资源释放、异常处理是否真实有效；
   - 逻辑与设计：与 plan 一致、无隐藏副作用、无过度设计、复用了既有能力；
   - 规范：项目风格、命名、类型、日志、无调试残留、无临时代码/硬编码；
   - 测试：断言是否有效、是否覆盖 plan 用例、有无被弱化的测试。
3. 是否与 plan 变更清单一致；多余改动标出并建议回退。
4. 写 `specs/reviews/<slug>.review.md`：

```
# 代码审查：<slug>
## 结论
## 范围（文件数/行数）
## 问题
| 级别 | 文件:行 | 问题 | 建议 |
| Blocker | ... | ... | ... |
## 敏感代码判定（是/否 + 依据）
## 处理情况
```

5. 输出：Blockers n / Majors n / Minors n；**Blocker 修复后必须重跑测试**。
6. 判定敏感 → 提示下一步 `/security-scan`；非敏感 → 在 review 中写明“跳过安全复查：非敏感代码”，进入收尾。
