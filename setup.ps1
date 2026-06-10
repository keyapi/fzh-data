# setup.ps1 - fzh-data dev environment init
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1
# What it does:
#   1. Create CLAUDE.md symlink pointing to AGENTS.md
#   2. Link .agents/skills/* into ~/.claude/skills/
#   3. Link superpowers skills into ~/.claude/skills/ (if installed)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeSkills = "$env:USERPROFILE\.claude\skills"

Write-Host "=== fzh-data dev environment init ===" -ForegroundColor Cyan
Write-Host ""

# helper: create directory junction (no admin required)
function New-SafeJunction {
    param([string]$Path, [string]$Target)
    if (Test-Path $Path) {
        Write-Host "  [SKIP] already exists: $Path" -ForegroundColor Gray
        return
    }
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    try {
        cmd /c "mklink /J `"$Path`" `"$Target`"" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] $Path" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] $Path (junction failed)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  [FAIL] $Path : $_" -ForegroundColor Red
    }
}

# helper: create file symlink or copy fallback
function New-SafeSymlink {
    param([string]$Path, [string]$Target)
    if (Test-Path $Path) {
        Write-Host "  [SKIP] already exists: $Path" -ForegroundColor Gray
        return
    }
    try {
        New-Item -ItemType SymbolicLink -Path $Path -Target $Target -Force | Out-Null
        Write-Host "  [OK] $Path -> $Target" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] symlink failed, fallback to copy: $Path" -ForegroundColor Yellow
        Copy-Item $Target $Path
        Write-Host "  [OK] (copy) $Path" -ForegroundColor Green
    }
}

# ---- Step 1: CLAUDE.md -> AGENTS.md ----

Write-Host "Step 1: CLAUDE.md symlink" -ForegroundColor Yellow
$ClaudeMd = Join-Path $ScriptDir "CLAUDE.md"
$AgentsMd = Join-Path $ScriptDir "AGENTS.md"

if (Test-Path $ClaudeMd) {
    $item = Get-Item $ClaudeMd -ErrorAction SilentlyContinue
    if ($item.LinkType -eq "SymbolicLink" -and (Split-Path $item.Target -Leaf) -eq "AGENTS.md") {
        Write-Host "  [SKIP] CLAUDE.md already linked to AGENTS.md" -ForegroundColor Gray
    } else {
        Write-Host "  [INFO] Recreating CLAUDE.md as symlink..." -ForegroundColor Yellow
        Remove-Item $ClaudeMd -Force
        New-SafeSymlink -Path $ClaudeMd -Target $AgentsMd
    }
} else {
    New-SafeSymlink -Path $ClaudeMd -Target $AgentsMd
}
Write-Host ""

# ---- Step 2: .agents/skills/ -> ~/.claude/skills/ ----

Write-Host "Step 2: Link project skills to Claude Desktop" -ForegroundColor Yellow
$ProjectSkills = Join-Path $ScriptDir ".agents\skills"

if (-not (Test-Path $ClaudeSkills)) {
    New-Item -ItemType Directory -Path $ClaudeSkills -Force | Out-Null
}

Get-ChildItem $ProjectSkills -Directory | ForEach-Object {
    $linkPath = Join-Path $ClaudeSkills $_.Name
    New-SafeJunction -Path $linkPath -Target $_.FullName
}
Write-Host ""

# ---- Step 3: superpowers skills (if installed) ----

Write-Host "Step 3: Link superpowers skills (if installed)" -ForegroundColor Yellow
$spSkills = "$env:USERPROFILE\.claude\superpowers\skills"
if (Test-Path $spSkills) {
    Get-ChildItem $spSkills -Directory | ForEach-Object {
        $linkPath = Join-Path $ClaudeSkills $_.Name
        New-SafeJunction -Path $linkPath -Target $_.FullName
    }
} else {
    Write-Host "  [INFO] superpowers not installed, skip." -ForegroundColor Gray
    Write-Host "  Install guide: docs/superpowers-install.md" -ForegroundColor Gray
}
Write-Host ""

# ---- Done ----

Write-Host "=== Init complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verify:" -ForegroundColor White
Write-Host "  git status"
Write-Host "  ls ~/.claude/skills"
Write-Host "  Restart Claude Desktop, then try /brainstorming"
