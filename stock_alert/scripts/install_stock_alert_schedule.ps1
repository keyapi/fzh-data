# install_stock_alert_schedule.ps1
# Register Windows Task Scheduler jobs for stock alerts:
#   - FZH-StockAlert-Poland : Poland low-stock alert          (default 14:00)
#   - FZH-StockAlert-US     : 美中 + 美东 low-stock alert     (default 20:00)
#   - FZH-StockInbound-daily: today's purchase inbound, one card (default 14:00)
#
# Low-stock cards only list warehouses that actually have NEW low-stock SKUs;
# no new -> no push. Inbound card only lists warehouses with real inbound;
# none -> no push.
#
# ASCII-only on purpose (PS 5.1 reads files without BOM as ANSI; avoid mojibake).
# Region -> warehouse mapping lives in Python (run_stock_alert_region.py), not
# in this script, so Chinese warehouse names never go through cmd.exe.
#
# Usage (run from the fzh-data repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -PolandAtTime "14:00" -UsAtTime "20:00" -InboundAtTime "14:00"
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -SkipInbound
#   powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -Remove
#
# Notes:
#   - Needs TONGTOOL_ERP2_PRIMARY_KEY/SECRET in tongtool_api\.env and
#     DINGTALK_WEBHOOK_STOCK / DINGTALK_SECRET_STOCK in the repo-root .env.
#   - Inbound calls /openapi/tongtool/stocksChangeDetailQuery directly
#     (EN stock_change only syncs once daily ~05:53, too stale for intraday).
#   - Tongtool ERP2 is rate limited to 5 calls/minute merchant-wide; the jobs
#     throttle product-name lookups (13s). Do not shorten the interval.
#   - Runs as the current interactive user; StartWhenAvailable catches up after
#     a missed trigger, and WakeToRun asks Windows to wake the PC. To make the
#     jobs run while the screen is off, also keep the PC from sleeping on AC
#     (powercfg /change standby-timeout-ac 0).

param(
  [string]$PolandAtTime = "14:00",
  [string]$UsAtTime = "20:00",
  [string]$InboundAtTime = "14:00",
  [switch]$SkipInbound,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
$polandTask = "FZH-StockAlert-Poland"
$usTask = "FZH-StockAlert-US"
$inboundTask = "FZH-StockInbound-daily"
$legacyTask = "FZH-StockAlert-daily"

if ($Remove) {
  foreach ($name in @($polandTask, $usTask, $inboundTask, $legacyTask)) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  }
  Write-Host "Removed (if existed): $polandTask, $usTask, $inboundTask, $legacyTask"
  exit 0
}

function Write-Wrapper($repo, $fileName, $pythonArgs, $logName) {
  $wrapper = Join-Path $repo "stock_alert\scripts\$fileName"
  $content = @(
    '@echo off'
    'setlocal'
    'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
    'rem Keep Chinese output readable when stdout is redirected to a log file.'
    'set "PYTHONIOENCODING=utf-8"'
    'cd /d "%~dp0..\.."'
    'set "LOGDIR=%~dp0..\..\stock_alert_output\logs"'
    'if not exist "%LOGDIR%" mkdir "%LOGDIR%"'
    "uv run python $pythonArgs >> `"%LOGDIR%\$logName`" 2>&1"
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

# Replace the previous single 09:23 task.
Unregister-ScheduledTask -TaskName $legacyTask -Confirm:$false -ErrorAction SilentlyContinue

$polandWrapper = Write-Wrapper $repo "run_stock_alert_poland_scheduled.cmd" `
  "stock_alert\scripts\run_stock_alert_region.py --region poland" "stock_alert_poland-daily.log"
Register-RepoTask $polandTask $polandWrapper @($PolandAtTime)
Write-Host "Registered: $polandTask"
Write-Host "Schedule : daily at $PolandAtTime (Poland only)"
Write-Host "Logs     : stock_alert_output\logs\stock_alert_poland-daily.log"

$usWrapper = Write-Wrapper $repo "run_stock_alert_us_scheduled.cmd" `
  "stock_alert\scripts\run_stock_alert_region.py --region us" "stock_alert_us-daily.log"
Register-RepoTask $usTask $usWrapper @($UsAtTime)
Write-Host "Registered: $usTask"
Write-Host "Schedule : daily at $UsAtTime (美中 + 美东)"
Write-Host "Logs     : stock_alert_output\logs\stock_alert_us-daily.log"

if (-not $SkipInbound) {
  $inboundWrapper = Write-Wrapper $repo "run_stock_inbound_scheduled.cmd" `
    "stock_alert\scripts\run_stock_inbound.py --today --source tongtool" "stock_inbound-daily.log"
  Register-RepoTask $inboundTask $inboundWrapper @($InboundAtTime)
  Write-Host "Registered: $inboundTask"
  Write-Host "Schedule : daily at $InboundAtTime (one merged card)"
  Write-Host "Logs     : stock_alert_output\logs\stock_inbound-daily.log"
}

Write-Host ""
Write-Host "Review   : Get-ScheduledTask -TaskName $polandTask,$usTask | Select-Object TaskName,State"
Write-Host "Run now  : Start-ScheduledTask -TaskName $polandTask"
Write-Host "Run now  : Start-ScheduledTask -TaskName $usTask"
if (-not $SkipInbound) {
  Write-Host "Run now  : Start-ScheduledTask -TaskName $inboundTask"
}
