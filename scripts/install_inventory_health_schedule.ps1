# install_inventory_health_schedule.ps1
# Register a Windows Task Scheduler job that runs the daily Tongtool inventory
# health check (browser export + API backup artifacts, offline parity).
#
# Usage (run from the MAIN fzh-data checkout, not a worktree):
#   powershell -ExecutionPolicy Bypass -File scripts\install_inventory_health_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_inventory_health_schedule.ps1 -AtTime "07:17"
#   powershell -ExecutionPolicy Bypass -File scripts\install_inventory_health_schedule.ps1 -Remove
#
# The task runs as the current interactive user: the PC must be on and that
# user logged in.  Logs go to D:\Work\fzh-inventory\health\health-scheduled.log
# (D:\Work\fzh-inventory is an ASCII junction to the stock backup root).

param(
  [string]$AtTime = "07:17",
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "FZH-TongtuInventoryHealth"

function Remove-Task {
  & schtasks /Delete /F /TN $TaskName 2>$null
  Write-Host "Removed (if existed): $TaskName"
}

if ($Remove) {
  Remove-Task
  exit 0
}

$repo = (Get-Location).Path
if ($repo -match '\\\.claude\\worktrees\\') {
  Write-Host "Run this from the MAIN checkout, not a worktree: $repo"
  exit 2
}

$scriptPath = Join-Path $repo "scripts\inventory_daily_health.py"
if (-not (Test-Path $scriptPath)) {
  Write-Host "Missing: $scriptPath"
  exit 2
}

$healthDir = "D:\Work\fzh-inventory\health"
if (-not (Test-Path $healthDir)) {
  New-Item -ItemType Directory -Path $healthDir -Force | Out-Null
}

$wrapper = Join-Path $repo "scripts\run_inventory_health_scheduled.cmd"
$log = Join-Path $healthDir "health-scheduled.log"
$content = @(
  '@echo off'
  'setlocal'
  'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
  'cd /d "%~dp0.."'
  "uv run python scripts\inventory_daily_health.py >> `"$log`" 2>&1"
) -join "`r`n"
[System.IO.File]::WriteAllText($wrapper, $content + "`r`n")

if ($AtTime -notmatch '^\d{2}:\d{2}$') {
  Write-Host "AtTime must be HH:MM"
  exit 2
}

$tr = "`"$wrapper`""
& schtasks /Create /F /TN $TaskName /TR $tr /SC DAILY /ST $AtTime
if ($LASTEXITCODE -ne 0) { throw "schtasks failed for $TaskName" }

$query = & schtasks /Query /TN $TaskName /V /FO LIST 2>&1 | Out-String
if ($query -notmatch 'inventory_daily_health|run_inventory_health_scheduled') {
  throw "Task $TaskName registered but Task To Run does not point at the health wrapper"
}

Write-Host "Registered: $TaskName at $AtTime (daily)"
Write-Host "Wrapper:    $wrapper"
Write-Host "Log:        $log"
