# install_parcel_track_schedule.ps1
# Register a Windows Task Scheduler job that runs the parcel_track ops report
# unattended and pushes the resulting Excel to a DingTalk group.
#
# ASCII-only on purpose (PS 5.1 reads files without BOM as ANSI; avoid mojibake).
#
# Usage (run from the fzh-data repo root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -Task weekly -DayOfWeek MON -AtTime "09:07"
#   powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -Remove
#
# Notes:
#   - By default the job FETCHES the data itself (Tongtu "order detail statistics",
#     last 7 days ending YESTERDAY - Tongtu rejects a range ending today), unzips it
#     into -InputDir, then runs the report. Pass -SkipFetch to keep dropping the
#     export in by hand instead.
#   - Output goes to parcel_track_output\ops_<start>_<end>.xlsx, logs to
#     parcel_track_output\logs\parcel_track-<task>.log
#   - Needs DINGTALK_WEBHOOK / DINGTALK_SECRET / ERP_API_KEY / ERP_API_SECRET and
#     the UPS/FedEx credentials in the repo-root .env (see parcel_track/README.md).
#   - Uses the ScheduledTasks cmdlets, NOT `schtasks /TR`: the repo path usually
#     contains a space, and schtasks stores /TR unquoted -> the task would try to run
#     "D:\Claude" and fail with ERROR_FILE_NOT_FOUND (-2147024894).
#   - Runs as the current interactive user: the PC must be on and that user logged
#     in at trigger time; Windows Task Scheduler does not backfill missed runs.

param(
  [ValidateSet("daily", "weekly")] [string]$Task = "daily",
  [string]$AtTime = "09:07",
  [string]$DayOfWeek = "MON",
  [string]$InputDir = "parcel_track_input",
  [switch]$SkipFetch,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"

function Write-ScheduleWrapper($repo, $taskName, $inputDir, $skipFetch) {
  $wrapper = Join-Path $repo "parcel_track\scripts\run_parcel_track_scheduled-$taskName.cmd"
  $fetchFlag = if ($skipFetch) { " --skip-fetch" } else { "" }
  $content = @(
    '@echo off'
    'setlocal'
    'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
    'rem Keep Chinese output readable when stdout is redirected to a log file.'
    'set "PYTHONIOENCODING=utf-8"'
    'rem Bundled chromium cannot start headed on this machine; use the installed Chrome.'
    'rem See web_automation/docs/reference/browser-launch.md'
    'set "WEB_AUTOMATION_BROWSER_CHANNEL=chrome"'
    'cd /d "%~dp0..\.."'
    'set "LOGDIR=%~dp0..\..\parcel_track_output\logs"'
    'if not exist "%LOGDIR%" mkdir "%LOGDIR%"'
    "uv run python parcel_track\scripts\daily_fetch_and_report.py --notify$fetchFlag --input-dir `"$inputDir`" >> `"%LOGDIR%\parcel_track-$taskName.log`" 2>&1"
  ) -join "`r`n"
  [System.IO.File]::WriteAllText($wrapper, $content + "`r`n")
  return $wrapper
}

function Register-One($repo, $taskName, $inputDir, $skipFetch, $atTime, $dayOfWeek) {
  $taskNameFull = "FZH-ParcelTrack-$taskName"
  $wrapper = Write-ScheduleWrapper $repo $taskName $inputDir $skipFetch

  # NOTE: do NOT use `schtasks /TR "<path>"` here. The repo usually lives under a path
  # with a space ("D:\Claude Demo\..."), and schtasks stores the value unquoted, so the
  # task ends up trying to run "D:\Claude" -> ERROR_FILE_NOT_FOUND (-2147024894).
  # The ScheduledTasks cmdlets take the executable as a plain string, no shell parsing.
  $action = New-ScheduledTaskAction -Execute $wrapper
  if ($taskName -eq "weekly") {
    $days = [System.DayOfWeek]::$(_Expand-DayOfWeek $dayOfWeek)
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $atTime
  } else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $atTime
  }
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

  Register-ScheduledTask -TaskName $taskNameFull -Action $action -Trigger $trigger `
    -Principal $principal -Force | Out-Null

  $registered = (Get-ScheduledTask -TaskName $taskNameFull).Actions[0].Execute
  if ($registered -ne $wrapper) {
    throw "Task $taskNameFull registered but runs '$registered' instead of '$wrapper'"
  }
  Write-Host "Registered: $taskNameFull"
}

function _Expand-DayOfWeek($code) {
  $map = @{ MON = "Monday"; TUE = "Tuesday"; WED = "Wednesday"; THU = "Thursday";
            FRI = "Friday"; SAT = "Saturday"; SUN = "Sunday" }
  $key = $code.Trim().ToUpper()
  if ($map.ContainsKey($key)) { return $map[$key] }
  return $code
}

$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo "parcel_track"))) {
  throw "Run this from the fzh-data repo root (parcel_track\ not found under $repo)"
}

$taskNameFull = "FZH-ParcelTrack-$Task"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $taskNameFull -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed (if existed): $taskNameFull"
  exit 0
}

$inputPath = Join-Path $repo $InputDir
if (-not (Test-Path $inputPath)) {
  New-Item -ItemType Directory -Path $inputPath -Force | Out-Null
  Write-Host "Created input dir: $inputPath"
}

Register-One $repo $Task $InputDir $SkipFetch.IsPresent $AtTime $DayOfWeek

Write-Host ""
Write-Host "Schedule: $Task at $AtTime$(if ($Task -eq 'weekly') { " on $DayOfWeek" })"
if ($SkipFetch) {
  Write-Host "Input   : $inputPath  (drop the Tongtu export here by hand; newest .xlsx wins)"
} else {
  Write-Host "Input   : $inputPath  (fetched automatically: last 7 days, ending YESTERDAY)"
  Write-Host "          Tongtu rejects a ship-date range ending today, so the job never uses today."
}
Write-Host "Review  : Get-ScheduledTask -TaskName $taskNameFull | Select-Object -ExpandProperty Actions"
Write-Host "Run now : Start-ScheduledTask -TaskName $taskNameFull"
Write-Host "Logs    : parcel_track_output\logs\parcel_track-$Task.log"
