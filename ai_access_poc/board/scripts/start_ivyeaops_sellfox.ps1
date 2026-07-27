# Start IvyeaOps-sellfox on :8001 with Sellfox read-only PoC env.
# Uses uv-managed server\.venv (created via: uv venv + uv pip install).
# Does NOT vendor AGPL sources into fzh-data.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\start_ivyeaops_sellfox.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FzhRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$IvyRoot = Join-Path (Split-Path $FzhRoot -Parent) "IvyeaOps-sellfox"
if ($env:IVYEAOPS_ROOT) { $IvyRoot = $env:IVYEAOPS_ROOT }

$ServerDir = Join-Path $IvyRoot "server"
$VenvPy = Join-Path $ServerDir ".venv\Scripts\python.exe"
$Dist = Join-Path $IvyRoot "client\dist\index.html"

function Write-Info($m) { Write-Host "[start-ivyeaops] $m" -ForegroundColor Green }
function Write-Fail($m) { Write-Host "[start-ivyeaops] $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Dist)) {
    Write-Fail "Missing client\dist. Build first: cd $IvyRoot\client; npm run build"
}
if (-not (Test-Path $VenvPy)) {
    Write-Fail "Missing uv venv at $VenvPy. Run: cd $ServerDir; uv venv .venv; uv pip install -r requirements.txt pandas"
}
if (-not (Test-Path (Join-Path $ServerDir ".env"))) {
    Write-Fail "Missing server\.env — generate admin password via install.ps1 or docs/hands-on checklist."
}

# Load Sellfox proxy key from open_webui .env if not already set (never print value).
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
    "SELLFOX_APP_ID", "SELLFOX_APP_SECRET", "SELLFOX_CLIENT_ID", "SELLFOX_CLIENT_SECRET"
)
Import-DotEnvKeys (Join-Path $FzhRoot "SELLFOX_API\.env") @(
    "SELLFOX_PROXY_API_KEY", "SELLFOX_PROXY_BASE_URL",
    "SELLFOX_APP_ID", "SELLFOX_APP_SECRET"
)

$env:FZH_DATA_ROOT = $FzhRoot
$env:SELLFOX_READONLY_POC = "1"
$env:SELLFOX_WINDOW_MODE = "aggregate"
if (-not $env:SELLFOX_POC_SHOP_NAME) { $env:SELLFOX_POC_SHOP_NAME = "TOODDLY-Daneey-US" }

if (-not $env:SELLFOX_PROXY_API_KEY -and -not ($env:SELLFOX_APP_ID -and $env:SELLFOX_APP_SECRET)) {
    Write-Fail "No SELLFOX_PROXY_API_KEY (or AppId/Secret). Put key in ai_access_poc/open_webui/.env"
}

# Seed assistant_* (new-api) from open_webui/.env when Key present
$SeedScript = Join-Path $PSScriptRoot "seed_ivyeaops_hub_from_owui.ps1"
if (Test-Path $SeedScript) {
    try {
        Write-Info "Seeding hub_settings assistant_* from open_webui/.env ..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $SeedScript
    } catch {
        Write-Info "LLM seed skipped: $_"
    }
}

# Ensure read on / operate off without wiping assistant keys
New-Item -ItemType Directory -Force -Path (Join-Path $IvyRoot "data") | Out-Null
$Hub = Join-Path $IvyRoot "data\hub_settings.json"
& $VenvPy -c @"
import json, pathlib
p = pathlib.Path(r'''$Hub''')
data = json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
data['setup_done'] = True
data['lingxing_enabled'] = True
data['lingxing_operate_enabled'] = False
data['lingxing_operate_require_human'] = True
data['lingxing_operate_expires_at'] = ''
data['lingxing_circuit_reason'] = ''
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print('hub patched', p)
"@

$url = "http://127.0.0.1:8001"
try {
    $r = Invoke-WebRequest "$url/api/health" -TimeoutSec 2 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        Write-Info "Already running at $url"
        Start-Process $url | Out-Null
        exit 0
    }
} catch {}

Write-Info "FZH_DATA_ROOT=$FzhRoot"
Write-Info "IvyeaOps=$IvyRoot"
Write-Info "SELLFOX_READONLY_POC=1 WINDOW_MODE=aggregate shop=$($env:SELLFOX_POC_SHOP_NAME)"
Write-Info "Starting uvicorn on :8001 (uv venv python)..."

$LogsDir = Join-Path $IvyRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
$OutLog = Join-Path $LogsDir "ivyeaops.out.log"
$ErrLog = Join-Path $LogsDir "ivyeaops.err.log"

$proc = Start-Process -FilePath $VenvPy `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "info") `
    -WorkingDirectory $ServerDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

$pidFile = Join-Path $IvyRoot "data\ivyeaops.pid"
$proc.Id | Set-Content $pidFile -Encoding ascii

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest "$url/api/health" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
}
if (-not $ok) {
    Write-Fail "Health check failed. See $ErrLog"
}
Write-Info "OK $url  (login: admin / see server\.env setup docs)"
Start-Process $url | Out-Null
