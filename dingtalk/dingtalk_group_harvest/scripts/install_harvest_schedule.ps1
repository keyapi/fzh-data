# install_harvest_schedule.ps1
# Register Windows Task Scheduler jobs for DingTalk group harvest.
#
# ASCII-only on purpose (PS 5.1 reads files without BOM as ANSI; avoid mojibake).
#
# Usage (run from the fzh-data repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File dingtalk\dingtalk_group_harvest\scripts\install_harvest_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File dingtalk\dingtalk_group_harvest\scripts\install_harvest_schedule.ps1 -DailyAt "08:10" -WeeklyAt "08:40"
#   powershell -ExecutionPolicy Bypass -File dingtalk\dingtalk_group_harvest\scripts\install_harvest_schedule.ps1 -Remove
#
# Notes:
#   - Daily job: harvest messages/files. Weekly job (Monday): build digests.
#   - Jobs run as the current interactive user; the PC must be on and logged in.
#   - DWS login must be valid. `dws auth status` auto-refreshes while the
#     refresh token is valid; after it expires, run `dws auth login` manually.
#   - Logs append to <Root>\logs\daily.log and weekly.log.

param(
  [string]$DailyAt = "08:10",
  [string]$WeeklyAt = "08:40",
  [string]$Root = "",
  [switch]$Remove
)

$ErrorActionPreference = "Stop"

$repo = (Get-Location).Path
if ($Root -eq "") { $Root = Join-Path $env:USERPROFILE "dingtalk_harvest" }
$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Write-Wrapper($name, $pythonArgs, $logName) {
  $wrapper = Join-Path $repo "dingtalk\dingtalk_group_harvest\scripts\run_harvest_$name.cmd"
  $content = @(
    '@echo off'
    'setlocal'
    'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
    "set `"DINGTALK_HARVEST_ROOT=$Root`""
    "cd /d `"$repo`""
    "uv run python -m dingtalk.dingtalk_group_harvest.cli $pythonArgs >> `"$logDir\$logName`" 2>&1"
  ) -join "`r`n"
  [System.IO.File]::WriteAllText($wrapper, $content + "`r`n")
  return $wrapper
}

function Register-One($taskName, $wrapper, $scheduleArgs) {
  $tr = "`"$wrapper`""
  $args = @("/Create", "/F", "/TN", $taskName, "/TR", $tr) + $scheduleArgs
  & schtasks $args
  if ($LASTEXITCODE -ne 0) { throw "schtasks failed for $taskName" }
  $query = & schtasks /Query /TN $taskName /V /FO LIST 2>&1 | Out-String
  if ($query -notmatch 'dingtalk_group_harvest') {
    throw "Task $taskName registered but Task To Run does not contain dingtalk_group_harvest"
  }
  Write-Host "Registered: $taskName"
}

$dailyTask = "FZH-DingtalkHarvest-Daily"
$weeklyTask = "FZH-DingtalkHarvest-Weekly"

if ($Remove) {
  & schtasks /Delete /F /TN $dailyTask 2>$null
  & schtasks /Delete /F /TN $weeklyTask 2>$null
  Write-Host "Removed (if existed): $dailyTask, $weeklyTask"
  exit 0
}

$dailyWrapper = Write-Wrapper "daily" "harvest" "daily.log"
$weeklyWrapper = Write-Wrapper "weekly" "digest" "weekly.log"

Register-One $dailyTask $dailyWrapper @("/SC", "DAILY", "/ST", $DailyAt)
Register-One $weeklyTask $weeklyWrapper @("/SC", "WEEKLY", "/D", "MON", "/ST", $WeeklyAt)

Write-Host ""
Write-Host "Done. Review with:"
Write-Host "  schtasks /Query /TN $dailyTask /V /FO LIST"
Write-Host "  schtasks /Query /TN $weeklyTask /V /FO LIST"
Write-Host "Logs: $logDir"
Write-Host "Archive: $Root"
