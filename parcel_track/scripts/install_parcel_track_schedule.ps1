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
#   - The job reads the NEWEST .xlsx in -InputDir (drop the Tongtu export there;
#     parcel_track.cli accepts a directory for --tt and picks the newest file).
#   - Output goes to parcel_track_output\ops_<YYYYMMDD>.xlsx, logs to
#     parcel_track_output\logs\parcel_track-<task>.log
#   - Needs DINGTALK_WEBHOOK / DINGTALK_SECRET / ERP_API_KEY / ERP_API_SECRET and
#     the UPS/FedEx credentials in the repo-root .env (see parcel_track/README.md).
#   - Runs as the current interactive user: the PC must be on and that user logged
#     in at trigger time; Windows Task Scheduler does not backfill missed runs.

param(
  [ValidateSet("daily", "weekly")] [string]$Task = "daily",
  [string]$AtTime = "09:07",
  [string]$DayOfWeek = "MON",
  [string]$InputDir = "parcel_track_input",
  [switch]$Remove
)

$ErrorActionPreference = "Stop"

function Write-ScheduleWrapper($repo, $taskName, $inputDir) {
  $wrapper = Join-Path $repo "parcel_track\scripts\run_parcel_track_scheduled-$taskName.cmd"
  $content = @(
    '@echo off'
    'setlocal'
    'set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"'
    'rem Keep Chinese output readable when stdout is redirected to a log file.'
    'set "PYTHONIOENCODING=utf-8"'
    'cd /d "%~dp0..\.."'
    'set "LOGDIR=%~dp0..\..\parcel_track_output\logs"'
    'if not exist "%LOGDIR%" mkdir "%LOGDIR%"'
    "uv run python -m parcel_track.cli report --tt `"$inputDir`" --notify >> `"%LOGDIR%\parcel_track-$taskName.log`" 2>&1"
  ) -join "`r`n"
  [System.IO.File]::WriteAllText($wrapper, $content + "`r`n")
  return $wrapper
}

function Register-One($repo, $taskName, $scheduleArgs, $inputDir) {
  $taskNameFull = "FZH-ParcelTrack-$taskName"
  $wrapper = Write-ScheduleWrapper $repo $taskName $inputDir
  $args = @("/Create", "/F", "/TN", $taskNameFull, "/TR", "`"$wrapper`"") + $scheduleArgs
  & schtasks $args
  if ($LASTEXITCODE -ne 0) { throw "schtasks failed for $taskNameFull" }
  $query = & schtasks /Query /TN $taskNameFull /V /FO LIST 2>&1 | Out-String
  if ($query -notmatch 'run_parcel_track_scheduled') {
    throw "Task $taskNameFull registered but Task To Run does not point at the wrapper"
  }
  Write-Host "Registered: $taskNameFull"
}

$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo "parcel_track"))) {
  throw "Run this from the fzh-data repo root (parcel_track\ not found under $repo)"
}

$taskNameFull = "FZH-ParcelTrack-$Task"

if ($Remove) {
  & schtasks /Delete /F /TN $taskNameFull 2>$null
  Write-Host "Removed (if existed): $taskNameFull"
  exit 0
}

$inputPath = Join-Path $repo $InputDir
if (-not (Test-Path $inputPath)) {
  New-Item -ItemType Directory -Path $inputPath -Force | Out-Null
  Write-Host "Created input dir: $inputPath"
}

if ($Task -eq "weekly") {
  $sched = @("/SC", "WEEKLY", "/D", $DayOfWeek, "/ST", $AtTime)
} else {
  $sched = @("/SC", "DAILY", "/ST", $AtTime)
}

Register-One $repo $Task $sched $InputDir

Write-Host ""
Write-Host "Schedule: $Task at $AtTime$(if ($Task -eq 'weekly') { " on $DayOfWeek" })"
Write-Host "Input   : $inputPath  (drop the Tongtu export here; newest .xlsx wins)"
Write-Host "Review  : schtasks /Query /TN $taskNameFull /V /FO LIST"
Write-Host "Run now : schtasks /Run /TN $taskNameFull"
Write-Host "Logs    : parcel_track_output\logs\parcel_track-$Task.log"
