<#
.SYNOPSIS
  安装 ai-dev-workflow 技能到各类 AI 编程工具目录（ASCII-only 脚本，可在任意代码页下运行）。

.DESCRIPTION
  默认把技能复制到 <Target>\skills\ai-dev-workflow（SKILL.md + commands + adapters），
  并按 -Tool 生成该工具需要的命令/规则文件。只增不改：已存在的规则文件会先备份再追加。

.PARAMETER Tool
  claude | codex | cursor | copilot | windsurf | gemini | cline | dsh | generic | all

.PARAMETER Target
  项目根目录，默认当前目录。

.PARAMETER Source
  技能源目录，默认为本脚本所在目录的上一级。

.PARAMETER DryRun
  只打印将要执行的操作。

.EXAMPLE
  .\install.ps1 -Tool all

.EXAMPLE
  .\install.ps1 -Tool claude -Target D:\Project\my-app
#>
[CmdletBinding()]
param(
  [ValidateSet('claude', 'codex', 'cursor', 'copilot', 'windsurf', 'gemini', 'cline', 'dsh', 'generic', 'all')]
  [string]$Tool = 'all',
  [string]$Target = (Get-Location).Path,
  [string]$Source = (Split-Path -Parent $PSScriptRoot),
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$Marker = '<!-- ai-dev-workflow:machine-generated -->'
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$ClaudeNote = '@skills/ai-dev-workflow/SKILL.md: any coding task follows this workflow (plan -> approval gate -> TDD or plain implement -> code-review -> security-scan -> build-fix -> pr).'
$ReadFirst = 'Before writing code, read @AI_WORKFLOW.md and follow its workflow.'

function Write-Note([string]$msg, [string]$color = 'Gray') { Write-Host $msg -ForegroundColor $color }

function Ensure-Dir([string]$p) {
  if (-not (Test-Path $p)) {
    if ($DryRun) { Write-Note "[dry] mkdir $p"; return }
    New-Item -ItemType Directory -Path $p -Force | Out-Null
  }
}

function Copy-Skill([string]$destRoot) {
  $dest = Join-Path $destRoot 'ai-dev-workflow'
  Ensure-Dir $dest
  if (-not $DryRun) {
    Copy-Item -Path (Join-Path $Source 'SKILL.md') -Destination $dest -Force
    foreach ($sub in 'commands', 'adapters') {
      $from = Join-Path $Source $sub
      if (Test-Path $from) {
        Ensure-Dir (Join-Path $dest $sub)
        Copy-Item -Path (Join-Path $from *) -Destination (Join-Path $dest $sub) -Recurse -Force
      }
    }
  }
  Write-Note "  skill  -> $dest" 'Green'
}

function Install-Commands([string]$cmdDir) {
  Ensure-Dir $cmdDir
  Get-ChildItem -Path (Join-Path $Source 'commands') -Filter *.md | ForEach-Object {
    $dst = Join-Path $cmdDir $_.Name
    if (-not $DryRun) { Copy-Item $_.FullName $dst -Force }
    Write-Note "  command -> $dst" 'Green'
  }
}

function Append-Rule([string]$file, [string[]]$lines) {
  if ($DryRun) { Write-Note "  rule   -> $file"; return }
  if (Test-Path $file) {
    $existing = [System.IO.File]::ReadAllText($file)
    if ($existing.Contains($Marker)) {
      Write-Note "  skip   -> $file (already contains workflow block)" 'DarkYellow'
      return
    }
    Copy-Item $file "$file.$RunStamp.bak"
    Write-Note "  backup -> $file.$RunStamp.bak" 'Yellow'
    [System.IO.File]::AppendAllText($file, "`r`n" + ($lines -join "`r`n") + "`r`n", $utf8)
  } else {
    Ensure-Dir (Split-Path -Parent $file)
    [System.IO.File]::WriteAllText($file, ($lines -join "`r`n") + "`r`n", $utf8)
  }
  Write-Note "  rule   -> $file" 'Green'
}

function Read-Adapter([string]$name) {
  return [System.IO.File]::ReadAllText((Join-Path $Source (Join-Path 'adapters' $name)))
}

function Install-One([string]$t) {
  Write-Note "== $t ==" 'Cyan'
  switch ($t) {
    'claude' {
      Copy-Skill (Join-Path $Target '.claude/skills')
      Install-Commands (Join-Path $Target '.claude/commands')
      Append-Rule (Join-Path $Target 'CLAUDE.md') @($Marker, $ClaudeNote)
    }
    'codex' {
      Copy-Skill (Join-Path $Target 'skills')
      Append-Rule (Join-Path $Target 'AGENTS.md') @($Marker, (Read-Adapter 'AGENTS.md.append.md'))
    }
    'cursor' {
      Copy-Skill (Join-Path $Target '.cursor/skills')
      Ensure-Dir (Join-Path $Target '.cursor/rules')
      if (-not $DryRun) {
        Copy-Item -Path (Join-Path $Source 'adapters/cursor.mdc') -Destination (Join-Path $Target '.cursor/rules/ai-dev-workflow.mdc') -Force
      }
      Write-Note "  rule   -> .cursor/rules/ai-dev-workflow.mdc" 'Green'
    }
    'copilot' {
      Copy-Skill (Join-Path $Target 'skills')
      Append-Rule (Join-Path $Target '.github/copilot-instructions.md') @($Marker, (Read-Adapter 'copilot-instructions.md'))
    }
    'windsurf' {
      Copy-Skill (Join-Path $Target 'skills')
      Append-Rule (Join-Path $Target '.windsurf/rules/ai-dev-workflow.md') @('---', 'trigger: always_on', '---', $Marker, (Read-Adapter 'windsurf-rules.md'))
    }
    'gemini' {
      Copy-Skill (Join-Path $Target 'skills')
      Append-Rule (Join-Path $Target 'GEMINI.md') @($Marker, (Read-Adapter 'GEMINI.md.append.md'))
    }
    'cline' {
      Copy-Skill (Join-Path $Target 'skills')
      Append-Rule (Join-Path $Target '.clinerules/ai-dev-workflow.md') @($Marker, (Read-Adapter 'cline-rules.md'))
    }
    'dsh' {
      Copy-Skill (Join-Path $Target 'skills')
      Write-Note "  note   -> if DSH does not scan this folder, move skills/ai-dev-workflow into the DSH skills directory or point the skills config at it." 'Yellow'
    }
    'generic' {
      Copy-Skill (Join-Path $Target 'skills')
      Append-Rule (Join-Path $Target 'AI_WORKFLOW.md') @($Marker, (Read-Adapter 'AGENTS.md.append.md'))
      Append-Rule (Join-Path $Target 'AGENTS.md') @($Marker, $ReadFirst)
    }
  }
}

if (-not (Test-Path (Join-Path $Source 'SKILL.md'))) {
  throw "SKILL.md not found under: $Source (use -Source to point at the skill folder)"
}
Write-Note "source: $Source" 'DarkGray'
Write-Note "target: $Target" 'DarkGray'
Write-Note "mode  : $(if ($DryRun) { 'dry-run' } else { 'install' })" 'DarkGray'

$targets = if ($Tool -eq 'all') { @('claude', 'codex', 'cursor', 'copilot', 'windsurf', 'gemini', 'cline', 'generic') } else { @($Tool) }
foreach ($t in $targets) { Install-One $t }
Write-Note 'done.' 'Cyan'
