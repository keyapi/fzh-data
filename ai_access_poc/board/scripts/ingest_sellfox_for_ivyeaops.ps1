# Pull Sellfox search-term → IvyeaOps data/sellfox_cache (sid-aligned).
# Uses IvyeaOps uv venv python + keys from open_webui/.env
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\ingest_sellfox_for_ivyeaops.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FzhRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$IvyRoot = if ($env:IVYEAOPS_ROOT) { $env:IVYEAOPS_ROOT } else { Join-Path (Split-Path $FzhRoot -Parent) "IvyeaOps-sellfox" }
$VenvPy = Join-Path $IvyRoot "server\.venv\Scripts\python.exe"
$Script = Join-Path $PSScriptRoot "ingest_sellfox_search_term.py"

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
if (-not $env:SELLFOX_POC_SHOP_NAME) { $env:SELLFOX_POC_SHOP_NAME = "TOODDLY-Daneey-US" }

if (-not (Test-Path $VenvPy)) { throw "Missing $VenvPy — create with uv venv + uv pip install" }

Write-Host "[ingest] shop=$($env:SELLFOX_POC_SHOP_NAME) ivy=$IvyRoot" -ForegroundColor Green
& $VenvPy $Script
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
