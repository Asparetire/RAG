#!/usr/bin/env bash
# 将 ai-dev-workflow 技能安装到各类 AI 编程工具目录。
#
# 用法： ./install.sh [claude|codex|cursor|copilot|windsurf|gemini|cline|dsh|generic|all]
#        TARGET=/path/to/project ./install.sh all
#        SOURCE=/path/to/skill ./install.sh claude
#
# 只增不改：已存在的规则文件会先备份再追加（已有标记的会跳过）。源目录默认是本脚本所在目录的上一级。
set -euo pipefail

TOOL="${1:-all}"
TARGET="${TARGET:-$(pwd)}"
SOURCE="${SOURCE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MARKER='<!-- ai-dev-workflow:machine-generated -->'
STAMP="$(date +%Y%m%d-%H%M%S)"
say() { printf '%s\n' "$*"; }
ok()  { printf '  \033[32m%s\033[0m\n' "$*"; }

[ -f "$SOURCE/SKILL.md" ] || { echo "找不到 SKILL.md：$SOURCE"; exit 1; }
say "源：$SOURCE"
say "目标：$TARGET"

copy_skill() { # $1 = 目标 skills 目录
  mkdir -p "$1/ai-dev-workflow"
  cp -f "$SOURCE/SKILL.md" "$1/ai-dev-workflow/"
  for sub in commands adapters; do
    [ -d "$SOURCE/$sub" ] && cp -r "$SOURCE/$sub" "$1/ai-dev-workflow/" || true
  done
  ok "skill  -> $1/ai-dev-workflow"
}

copy_commands() {
  mkdir -p "$1"
  for f in "$SOURCE"/commands/*.md; do
    cp -f "$f" "$1/"
    ok "command -> $1/$(basename "$f")"
  done
}

append_rule() { # $1 = 文件, $2 = 内容
  local file="$1" body="$2"
  if [ -f "$file" ]; then
    if grep -qF "$MARKER" "$file" 2>/dev/null; then
      say "  skip   -> $file (already contains workflow block)"; return 0
    fi
    cp "$file" "$file.$STAMP.bak"; say "  backup -> $file.$STAMP.bak"
  fi
  mkdir -p "$(dirname "$file")"
  printf '\n%s\n%s\n' "$MARKER" "$body" >> "$file"
  ok "rule   -> $file"
}

install_one() {
  local t="$1" body
  say "== $t =="
  case "$t" in
    claude)
      copy_skill "$TARGET/.claude/skills"
      copy_commands "$TARGET/.claude/commands"
      append_rule "$TARGET/CLAUDE.md" '@skills/ai-dev-workflow/SKILL.md 写代码任务按此工作流执行（plan → 确认门 → TDD/普通实现 → code-review → security-scan → build-fix → pr）。'
      ;;
    codex)
      copy_skill "$TARGET/skills"
      append_rule "$TARGET/AGENTS.md" "$(cat "$SOURCE/adapters/AGENTS.md.append.md")"
      ;;
    cursor)
      copy_skill "$TARGET/.cursor/skills"
      mkdir -p "$TARGET/.cursor/rules"
      cp -f "$SOURCE/adapters/cursor.mdc" "$TARGET/.cursor/rules/ai-dev-workflow.mdc"
      ok "rule   -> .cursor/rules/ai-dev-workflow.mdc"
      ;;
    copilot)
      copy_skill "$TARGET/skills"
      append_rule "$TARGET/.github/copilot-instructions.md" "$(cat "$SOURCE/adapters/copilot-instructions.md")"
      ;;
    windsurf)
      copy_skill "$TARGET/skills"
      body="$(printf -- '---\ntrigger: always_on\n---\n'; cat "$SOURCE/adapters/windsurf-rules.md")"
      append_rule "$TARGET/.windsurf/rules/ai-dev-workflow.md" "$body"
      ;;
    gemini)
      copy_skill "$TARGET/skills"
      append_rule "$TARGET/GEMINI.md" "$(cat "$SOURCE/adapters/GEMINI.md.append.md")"
      ;;
    cline)
      copy_skill "$TARGET/skills"
      append_rule "$TARGET/.clinerules/ai-dev-workflow.md" "$(cat "$SOURCE/adapters/cline-rules.md")"
      ;;
    dsh)
      copy_skill "$TARGET/skills"
      ok "说明：若技能目录未被 DSH 扫描，请把 skills/ai-dev-workflow 移到 DSH 技能目录，或用 skills 工具/目录配置指向它。"
      ;;
    generic)
      copy_skill "$TARGET/skills"
      append_rule "$TARGET/AI_WORKFLOW.md" "$(cat "$SOURCE/adapters/AGENTS.md.append.md")"
      append_rule "$TARGET/AGENTS.md" '写代码前先读 @AI_WORKFLOW.md 并按其流程执行。'
      ;;
    *)
      echo "未知工具：$t"; exit 2
      ;;
  esac
}

if [ "$TOOL" = "all" ]; then
  set -- claude codex cursor copilot windsurf gemini cline generic
else
  set -- "$TOOL"
fi
for t in "$@"; do install_one "$t"; done
say '完成。'
