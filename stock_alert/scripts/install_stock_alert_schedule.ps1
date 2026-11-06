# install_stock_alert_schedule.ps1
# Register a Windows Task Scheduler job that runs the Tongtool low-stock scan
# unattended and pushes a summary to a DingTalk group robot.
#
# ASCII-only on purpose (PS 5.1 reads files without BOM as ANSI; avoid mojibake).
#
# Usage (run from the fzh-data repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -AtTime "09:23" -Threshold 5
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -Remove
#
# Notes:
#   - Needs TONGTOOL_ERP2_PRIMARY_KEY/SECRET in tongtool_api\.env and
#     DINGTALK_WEBHOOK_STOCK / DINGTALK_SECRET_STOCK in the repo-root .env.
#   - Tongtool ERP2 is rate limited to 5 calls/minute merchant-wide; the job
#     pages warehouse-by-warehouse with a built-in throttle. Do not shorten the
#     interval.
#   - Uses the ScheduledTasks cmdlets, NOT `schtasks /TR`: the repo path usually
#     contains a space, and schtasks stores /TR unquoted -> the task would try to
#     run "D:\Claude" and fail with ERROR_FILE_NOT_FOUND (-2147024894).
#   - Runs as the current interactive user: the PC must be on and that user logged
#     in at trigger time; Windows Task Scheduler does not backfill missed runs.

param(
  [string]$AtTime = "09:23",
  [string]$Warehouses = "",
  [double]$Threshold = 5,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$taskNameFull = "FZH-StockAlert-daily"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $taskNameFull -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed (if existed): $taskNameFull"
  exit 0
}

function Write-ScheduleWrapper($repo, $warehouses, $threshold) {
  $wrapper = Join-Path $repo "stock_alert\scripts\run_stock_alert_scheduled.cmd"
  $whFlag = if ($warehouses) { " --warehouses `"$warehouses`"" } else { "" }
  $content = @(
    '@echo off'
    'setlocal'
    'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
    'rem Keep Chinese output readable when stdout is redirected to a log file.'
    'set "PYTHONIOENCODING=utf-8"'
    'cd /d "%~dp0..\.."'
    'set "LOGDIR=%~dp0..\..\stock_alert_output\logs"'
    'if not exist "%LOGDIR%" mkdir "%LOGDIR%"'
    "uv run python stock_alert\scripts\run_stock_alert.py --threshold $threshold$whFlag >> `"%LOGDIR%\stock_alert-daily.log`" 2>&1"
  ) -join "`r`n"
  [System.IO.File]::WriteAllText($wrapper, $content + "`r`n")
  return $wrapper
}

$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo "stock_alert"))) {
  throw "Run this from the fzh-data repo root (stock_alert\ not found under $repo)"
}

$wrapper = Write-ScheduleWrapper $repo $Warehouses $Threshold

$action = New-ScheduledTaskAction -Execute $wrapper
$trigger = New-ScheduledTaskTrigger -Daily -At $AtTime
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $taskNameFull -Action $action -Trigger $trigger `
  -Principal $principal -Force | Out-Null

$registered = (Get-ScheduledTask -TaskName $taskNameFull).Actions[0].Execute
if ($registered -ne $wrapper) {
  throw "Task $taskNameFull registered but runs '$registered' instead of '$wrapper'"
}

Write-Host "Registered: $taskNameFull"
Write-Host "Schedule : daily at $AtTime"
Write-Host "Wrapper  : $wrapper"
Write-Host "Review   : Get-ScheduledTask -TaskName $taskNameFull | Select-Object -ExpandProperty Actions"
Write-Host "Run now  : Start-ScheduledTask -TaskName $taskNameFull"
Write-Host "Logs     : stock_alert_output\logs\stock_alert-daily.log"
