# AI 开发完整工作流（ai-dev-workflow）技能

把一张「AI 开发完整工作流」流程图，落成**可安装、可跨工具使用**的编码技能：

```
需求定义(可选) → 实现规划 → 【确认门】 → TDD 实现 → 通用代码审查 → 敏感?(安全复查) → 收尾(build-fix / PR)
```

- 作者原图：Mr.7y · 参考图见 [workflow-diagram.jpg](workflow-diagram.jpg)
- 核心规范：[SKILL.md](SKILL.md)（唯一权威，其他文件都是它的入口或适配）

## 目录结构

| 文件 | 作用 |
|---|---|
| [SKILL.md](SKILL.md) | 技能主文件：硬规则、状态机、各阶段细则、产物模板、工具接入表、反模式 |
| [commands/](commands/) | 与流程图命令一一对应的命令文件（Claude Code 等支持斜杠命令的工具直接可用） |
| [adapters/](adapters/) | 给 Codex/AGENTS.md、Cursor、Copilot、Windsurf、Gemini CLI、Cline 的规则片段 |
| [scripts/install.ps1](scripts/install.ps1) | Windows 一键安装（ASCII-only，任意代码页可运行） |
| [scripts/install.sh](scripts/install.sh) | macOS / Linux 一键安装 |
| [package.json](package.json) | 可选的 npm 元数据 |

命令清单：`/ai-workflow`、`/plan-prd`、`/plan`、`/plan-canvas`、`tdd-workflow`、`/code-review`、`/security-scan`、`/build-fix`、`/pr`。

## 核心设计（与流程图一致的关键规则）

1. **确认门**：计划写完必须停下等批准，批准前不改任何源码。
2. **TDD 由批准指令决定**：批准时带「严格使用 tdd-workflow 实施」→ RED→GREEN→重构→覆盖率≥80%；只回 `yes` → 不走 TDD。
3. **可视化确认顺序**：先发 TDD 指令，再点 `Approve plan`。
4. **敏感代码强制安全复查**：认证 / 授权 / API / PII / 密钥 / 上传下载 / 反序列化 / 注入面 / 依赖变更；非敏感则书面写明跳过原因。
5. **产物落盘**：`specs/prds|plans|reviews/`（项目已有 `.claude/prds`、`docs/` 等约定时沿用）。
6. **收尾**：`/build-fix` 按需修构建（禁止 `@ts-ignore`/`eslint-disable`/删测试掩盖），`/pr` 经确认后创建。

## 安装

### Windows

> 若 PowerShell 报「cannot be loaded / 未数字签名」（默认执行策略是 `RemoteSigned`，从 Git 下载的脚本会带「来自互联网」标记），先解除标记：
> `Unblock-File .\scripts\install.ps1`；或改用 `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Tool all`。

```powershell
# 安装全部工具到当前目录（项目根）
.\skills\ai-dev-workflow\scripts\install.ps1 -Tool all

# 只装某一工具，指定项目目录
.\skills\ai-dev-workflow\scripts\install.ps1 -Tool claude -Target D:\Project\my-app

# 只预览，不落盘
.\skills\ai-dev-workflow\scripts\install.ps1 -Tool all -DryRun
```

### macOS / Linux

```bash
./skills/ai-dev-workflow/scripts/install.sh all
TARGET=~/code/my-app ./skills/ai-dev-workflow/scripts/install.sh claude
```

脚本行为：复制 `SKILL.md + commands + adapters` 到目标的 `skills/ai-dev-workflow`（或对应工具目录），然后**追加**规则文件（已存在且未被本脚本写过时先备份为 `*.bak`，已有标记则跳过）。

### 各工具安装结果

| `-Tool` | 生成位置 | 生效方式 |
|---|---|---|
| `claude` | `.claude/skills/ai-dev-workflow/`、`.claude/commands/*.md`、`CLAUDE.md` 追加一行 | 直接 `/plan`、`/code-review` 等 |
| `codex` | `skills/ai-dev-workflow/`、`AGENTS.md` 追加流程 | Codex 读 AGENTS.md |
| `cursor` | `.cursor/rules/ai-dev-workflow.mdc`（alwaysApply）、`.cursor/skills/ai-dev-workflow/` | 规则常驻，任意对话生效 |
| `copilot` | `.github/copilot-instructions.md` 追加 | Copilot Chat 读取 |
| `windsurf` | `.windsurf/rules/ai-dev-workflow.md`（always_on） | 规则常驻 |
| `gemini` | `GEMINI.md` 追加 | Gemini CLI 启动读取 |
| `cline` | `.clinerules/ai-dev-workflow.md` | Cline / Roo 规则 |
| `dsh` | `skills/ai-dev-workflow/`（DeepSeek Harness） | 视为技能目录，触发时加载 |
| `generic` | `skills/ai-dev-workflow/`、`AI_WORKFLOW.md`、`AGENTS.md` 一行指引 | 任意 Agent |

> 用户级安装：Claude Code 可把技能目录放到 `~/.claude/skills/`；DSH 用户可放到其技能目录，或用其工具/目录配置指向本目录。

## 使用方式

```
你：/ai-workflow 实现用户登录的短信验证码登录
AI：调查项目 → 写 specs/plans/user-login-otp.plan.md → 停在确认门
你：yes，严格使用 tdd-workflow 实施        ← 走 TDD
AI：RED(失败) → GREEN → 重构 → 覆盖率 85% → /code-review → 敏感(认证) → /security-scan
    → /build-fix(按需) → 生成 PR 描述 → 询问后开 PR → 输出汇总
```

不要 TDD 时只回 `yes` 即可。

## 接入自定义工具

任意能读规则/系统提示的工具，接入两步：

1. 把 `SKILL.md` 全文（或 `adapters/AGENTS.md.append.md` 精简版）放进其规则文件 / 系统提示；
2. 在该规则文件再加一行：`写代码前先读 skills/ai-dev-workflow/SKILL.md 并按其流程执行。`

## 扩展方向（可选，按需再补）

- 把 specs/ 加入 .gitignore 或改到 docs/（按团队约定）。
- 在 CI 里加一档：PR 必须附 specs/reviews/*.review.md 与安全结论才算通过。
- 多人协同时，plan 的「确认门记录」可改为审批面板/PR 评论的审批链接。
