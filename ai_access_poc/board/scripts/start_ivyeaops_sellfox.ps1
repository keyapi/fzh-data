# Start IvyeaOps-sellfox on :8001 with Sellfox read-only PoC env.
# Uses uv-managed server\.venv. Does NOT vendor AGPL into fzh-data.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\start_ivyeaops_sellfox.ps1
#   ... -OpenBrowser          # optional: open system Chrome/Edge
# Agent / E2E: omit -OpenBrowser; use Cursor built-in browser only.

param(
    [switch]$OpenBrowser
)

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
if (-not $env:SELLFOX_POC_SHOP_NAME) { $env:SELLFOX_POC_SHOP_NAME = "BJRYECLTD-US" }

if (-not $env:SELLFOX_PROXY_API_KEY -and -not ($env:SELLFOX_APP_ID -and $env:SELLFOX_APP_SECRET)) {
    Write-Fail "No SELLFOX_PROXY_API_KEY (or AppId/Secret). Put key in ai_access_poc/open_webui/.env"
}

$SeedScript = Join-Path $PSScriptRoot "seed_ivyeaops_hub_from_owui.ps1"
if (Test-Path $SeedScript) {
    try {
        Write-Info "Seeding hub_settings assistant_* from open_webui/.env ..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $SeedScript
    } catch {
        Write-Info "LLM seed skipped: $_"
    }
}

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
function Open-SystemBrowserIfRequested {
    if ($OpenBrowser) {
        Write-Info "Opening system browser (-OpenBrowser)"
        Start-Process $url | Out-Null
    } else {
        Write-Info "Skip system browser (Cursor built-in E2E). Pass -OpenBrowser if needed."
    }
}

try {
    $r = Invoke-WebRequest "$url/api/health" -TimeoutSec 2 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        Write-Info "Already running at $url"
        Open-SystemBrowserIfRequested
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

# Pass PoC env explicitly into child (avoids missing SELLFOX_* after Start-Process)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $VenvPy
$psi.Arguments = "-m uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level info"
$psi.WorkingDirectory = $ServerDir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
# Copy current process env, then force PoC keys
$psi.EnvironmentVariables["FZH_DATA_ROOT"] = $FzhRoot
$psi.EnvironmentVariables["SELLFOX_READONLY_POC"] = "1"
$psi.EnvironmentVariables["SELLFOX_WINDOW_MODE"] = "aggregate"
$psi.EnvironmentVariables["SELLFOX_POC_SHOP_NAME"] = $env:SELLFOX_POC_SHOP_NAME
foreach ($k in @("SELLFOX_PROXY_API_KEY","SELLFOX_PROXY_BASE_URL","SELLFOX_APP_ID","SELLFOX_APP_SECRET","SELLFOX_CLIENT_ID","SELLFOX_CLIENT_SECRET")) {
    $v = [Environment]::GetEnvironmentVariable($k, "Process")
    if (-not [string]::IsNullOrWhiteSpace($v)) { $psi.EnvironmentVariables[$k] = $v }
}
$psi.EnvironmentVariables["VIRTUAL_ENV"] = (Join-Path $ServerDir ".venv")

$proc = [System.Diagnostics.Process]::Start($psi)
# Fire-and-forget log pumps (best-effort; health check is the gate)
Start-Job -ScriptBlock {
    param($p, $out, $err)
    $p.StandardOutput.ReadToEnd() | Set-Content -Path $out -Encoding UTF8
    $p.StandardError.ReadToEnd() | Set-Content -Path $err -Encoding UTF8
} -ArgumentList $proc, $OutLog, $ErrLog | Out-Null

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
Write-Info "OK $url  pid=$($proc.Id)  (login: admin / see server\.env setup docs)"
Open-SystemBrowserIfRequested
