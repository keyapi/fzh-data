# Phase2: entities + Targeting/Campaign + asin_profit → IvyeaOps sellfox_cache
#
# OPTIONAL warm-up / boil-the-lake tool. Product path is on-demand:
# Browse / Optimizer miss·force → fetch_dataset → sellfox_ingest.ensure_dataset.
# You do NOT need to run this before colleagues use 数据浏览 / 优化建议.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\ingest_sellfox_phase2.ps1
# Optional:
#   $env:SELLFOX_POC_SHOP_NAME = "BJRYECLTD-US"
#   $env:SELLFOX_POC_DAYS = "30"
#   $env:SELLFOX_POC_SKIP_REPORTS = "1"   # entities (+profit) only
#   $env:SELLFOX_POC_SKIP_PROFIT = "1"

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FzhRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$IvyRoot = if ($env:IVYEAOPS_ROOT) { $env:IVYEAOPS_ROOT } else { Join-Path (Split-Path $FzhRoot -Parent) "IvyeaOps-sellfox" }
$VenvPy = Join-Path $IvyRoot "server\.venv\Scripts\python.exe"
$Script = Join-Path $PSScriptRoot "ingest_sellfox_phase2.py"

function Import-DotEnvKeys([string]$path, [string[]]$keys) {
    if (-not (Test-Path $path)) { return }
    Get-Content $path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $k, $v = $_ -split '=', 2
        $k = $k.Trim(); $v = $v.Trim().Trim('"').Trim("'")
        if ($keys -contains $k -and -not [string]::IsNullOrWhiteSpace($v)) {
            if (-not [Environment]::GetEnvironmentVariable($k)) {
                [Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
}

Import-DotEnvKeys (Join-Path $FzhRoot "ai_access_poc\open_webui\.env") @(
    "SELLFOX_PROXY_API_KEY", "SELLFOX_PROXY_BASE_URL",
    "SELLFOX_APP_ID", "SELLFOX_APP_SECRET"
)

$env:FZH_DATA_ROOT = $FzhRoot
$env:IVYEAOPS_ROOT = $IvyRoot
$env:SELLFOX_READONLY_POC = "1"
$env:SELLFOX_WINDOW_MODE = "aggregate"
if (-not $env:SELLFOX_POC_SHOP_NAME) { $env:SELLFOX_POC_SHOP_NAME = "BJRYECLTD-US" }
if (-not $env:SELLFOX_POC_DAYS) { $env:SELLFOX_POC_DAYS = "30" }

if (-not (Test-Path $VenvPy)) { throw "Missing $VenvPy — create with uv venv + uv pip install" }

Write-Host "[phase2-ingest] shop=$($env:SELLFOX_POC_SHOP_NAME) days=$($env:SELLFOX_POC_DAYS) ivy=$IvyRoot" -ForegroundColor Green
& $VenvPy $Script
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
