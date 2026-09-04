# install_tongtu_schedule.ps1
# Register a Windows Task Scheduler job that runs the Tongtu auto export on a
# schedule, unattended. When the 7-day login cookie expires, --auto-login makes
# the script lazily install OCR (first time) and recognise the captcha itself,
# so no human input is needed.
#
# ASCII-only on purpose (PS 5.1 reads files without BOM as ANSI; avoid mojibake).
#
# Usage (run from the fzh-data repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -IntervalHours 12
#   powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -Task sales -IntervalHours 8
#   powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -Task both -AtTime "02:00"
#   powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -Remove
#
# Notes:
#   - Default task is "stock". Use -Task both to register stock AND sales.
#   - Either -IntervalHours (>0 => every N hours) or -AtTime ("HH:MM" => daily
#     at that local time). If both given, IntervalHours wins.
#   - The scheduled job runs as the current interactive user, so the PC must be
#     powered on and that user logged in at trigger time.
#   - Writes web_automation\scripts\run_tongtu_scheduled-<task>.cmd (ASCII, per clone).
#   - Logs append to <repo>\web_automation\logs\export-<task>.log

param(
  [ValidateSet("stock", "sales", "both")] [string]$Task = "stock",
  [int]$IntervalHours = 0,
  [string]$AtTime = "",
  [switch]$Remove
)

$ErrorActionPreference = "Stop"

function Write-ScheduleWrapper($repo, $taskName) {
  $wrapper = Join-Path $repo "web_automation\scripts\run_tongtu_scheduled-$taskName.cmd"
  $content = @(
    '@echo off'
    'setlocal'
    'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
    'cd /d "%~dp0..\.."'
    "uv run python web_automation\scripts\dispatch.py tongtu.$taskName.export -- --auto-login >> `"%~dp0..\logs\export-$taskName.log`" 2>&1"
  ) -join "`r`n"
  [System.IO.File]::WriteAllText($wrapper, $content + "`r`n")
  return $wrapper
}

function Register-One($repo, $taskName, $scheduleArgs) {
  $taskNameFull = "FZH-TongtuAutoExport-$taskName"
  $wrapper = Write-ScheduleWrapper $repo $taskName
  $tr = "`"$wrapper`""
  $args = @("/Create", "/F", "/TN", $taskNameFull, "/TR", $tr) + $scheduleArgs
  & schtasks $args
  if ($LASTEXITCODE -ne 0) { throw "schtasks failed for $taskNameFull" }
  $query = & schtasks /Query /TN $taskNameFull /V /FO LIST 2>&1 | Out-String
  if ($query -notmatch 'dispatch\.py') {
    throw "Task $taskNameFull registered but Task To Run does not contain dispatch.py"
  }
  Write-Host "Registered: $taskNameFull"
}

function Remove-Tasks($tasks) {
  foreach ($t in $tasks) {
    $tn = "FZH-TongtuAutoExport-$t"
    & schtasks /Delete /F /TN $tn 2>$null
    Write-Host "Removed (if existed): $tn"
  }
}

$repo = (Get-Location).Path
$logDir = Join-Path $repo "web_automation\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

$tasks = @()
if ($Task -eq "both") { $tasks = @("stock", "sales") } else { $tasks = @($Task) }

if ($Remove) {
  Remove-Tasks $tasks
  exit 0
}

if ($IntervalHours -gt 0) {
  $sched = @("/SC", "HOURLY", "/MO", "$IntervalHours")
} elseif ($AtTime -ne "") {
  $sched = @("/SC", "DAILY", "/ST", $AtTime)
} else {
  Write-Host "Provide -IntervalHours (every N hours) or -AtTime (HH:MM daily)."
  exit 2
}

foreach ($t in $tasks) { Register-One $repo $t $sched }

Write-Host ""
Write-Host "Done. Review with:  schtasks /Query /TN FZH-TongtuAutoExport-$($tasks[0]) /V /FO LIST"
Write-Host "Logs: $logDir"
