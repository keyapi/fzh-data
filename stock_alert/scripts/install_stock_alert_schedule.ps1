# install_stock_alert_schedule.ps1
# Register Windows Task Scheduler jobs that run the Tongtool stock jobs unattended
# and push summaries to a DingTalk group robot:
#   - FZH-StockAlert-daily  : low stock detail + "newly low" Excel  (default 09:23)
#   - FZH-StockInbound-daily: intraday purchase inbound, direct Tongtool API
#                             (default 10:00, 14:00, 17:00)
#
# ASCII-only on purpose (PS 5.1 reads files without BOM as ANSI; avoid mojibake).
#
# Usage (run from the fzh-data repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -AtTime "09:23" -InboundTimes "10:00,14:00,17:00"
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -SkipInbound
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -Remove
#
# Notes:
#   - Needs TONGTOOL_ERP2_PRIMARY_KEY/SECRET in tongtool_api\.env and
#     DINGTALK_WEBHOOK_STOCK / DINGTALK_SECRET_STOCK in the repo-root .env.
#   - Intraday inbound calls /openapi/tongtool/stocksChangeDetailQuery directly
#     (EN stock_change only syncs once daily ~05:53, too stale for 10/14/17).
#   - Tongtool ERP2 is rate limited to 5 calls/minute merchant-wide; the jobs
#     throttle product-name lookups (13s). Do not shorten the interval.
#   - Uses the ScheduledTasks cmdlets, NOT `schtasks /TR`: the repo path usually
#     contains a space, and schtasks stores /TR unquoted -> the task would try to
#     run "D:\Claude" and fail with ERROR_FILE_NOT_FOUND (-2147024894).
#   - Runs as the current interactive user: the PC must be on and that user logged
#     in; StartWhenAvailable requests a delayed run after a missed trigger.

param(
  [string]$AtTime = "09:23",
  [string]$InboundTimes = "10:00,14:00,17:00",
  [string]$Warehouses = "",
  [double]$Threshold = 5,
  [switch]$SkipInbound,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$taskNameFull = "FZH-StockAlert-daily"
$inboundTaskFull = "FZH-StockInbound-daily"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $taskNameFull -Confirm:$false -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $inboundTaskFull -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed (if existed): $taskNameFull, $inboundTaskFull"
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

function Write-InboundWrapper($repo, $warehouses) {
  $wrapper = Join-Path $repo "stock_alert\scripts\run_stock_inbound_scheduled.cmd"
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
    "uv run python stock_alert\scripts\run_stock_inbound.py --today --source tongtool$whFlag >> `"%LOGDIR%\stock_inbound-daily.log`" 2>&1"
  ) -join "`r`n"
  [System.IO.File]::WriteAllText($wrapper, $content + "`r`n")
  return $wrapper
}

function Register-RepoTask($taskName, $wrapper, $times) {
  $action = New-ScheduledTaskAction -Execute $wrapper
  $triggers = @()
  foreach ($time in $times) {
    $triggers += New-ScheduledTaskTrigger -Daily -At $time.Trim()
  }
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
  # Robustness: the PC may be asleep / not ready at the trigger time. Run ASAP after a
  # missed start (StartWhenAvailable), allow a wake timer (WakeToRun), and do not skip on
  # battery (matters for laptops; harmless on desktops). Without these, a single missed
  # run silently loses that day's report.
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Principal $principal -Settings $settings -Force | Out-Null

  $registered = (Get-ScheduledTask -TaskName $taskName).Actions[0].Execute
  if ($registered -ne $wrapper) {
    throw "Task $taskName registered but runs '$registered' instead of '$wrapper'"
  }
}

$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo "stock_alert"))) {
  throw "Run this from the fzh-data repo root (stock_alert\ not found under $repo)"
}

$wrapper = Write-ScheduleWrapper $repo $Warehouses $Threshold
Register-RepoTask $taskNameFull $wrapper @($AtTime)
Write-Host "Registered: $taskNameFull"
Write-Host "Schedule : daily at $AtTime"
Write-Host "Wrapper  : $wrapper"
Write-Host "Logs     : stock_alert_output\logs\stock_alert-daily.log"

if (-not $SkipInbound) {
  $inboundWrapper = Write-InboundWrapper $repo $Warehouses
  $inboundTimesList = $InboundTimes.Split(",")
  Register-RepoTask $inboundTaskFull $inboundWrapper $inboundTimesList
  Write-Host "Registered: $inboundTaskFull"
  Write-Host "Schedule : daily at $InboundTimes (direct Tongtool API)"
  Write-Host "Wrapper  : $inboundWrapper"
  Write-Host "Logs     : stock_alert_output\logs\stock_inbound-daily.log"
}

Write-Host ""
Write-Host "Review   : Get-ScheduledTask -TaskName $taskNameFull | Select-Object -ExpandProperty Actions"
Write-Host "Run now  : Start-ScheduledTask -TaskName $taskNameFull"
if (-not $SkipInbound) {
  Write-Host "Run now  : Start-ScheduledTask -TaskName $inboundTaskFull"
}
