# One-time setup: IvyeaOps-sellfox with uv (FZH)
# Prefer uv over global pip. Does not vendor AGPL into fzh-data.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\setup_ivyeaops_uv.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FzhRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$IvyRoot = if ($env:IVYEAOPS_ROOT) { $env:IVYEAOPS_ROOT } else { Join-Path (Split-Path $FzhRoot -Parent) "IvyeaOps-sellfox" }
$ServerDir = Join-Path $IvyRoot "server"
$ClientDir = Join-Path $IvyRoot "client"

function Write-Info($m) { Write-Host "[setup-uv] $m" -ForegroundColor Green }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv not found. Install: https://docs.astral.sh/uv/  or irm https://astral.sh/uv/install.ps1 | iex"
}

$env:UV_INDEX_URL = if ($env:UV_INDEX_URL) { $env:UV_INDEX_URL } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
$env:npm_config_registry = if ($env:npm_config_registry) { $env:npm_config_registry } else { "https://registry.npmmirror.com" }

Write-Info "IvyeaOps=$IvyRoot"
Set-Location $ServerDir
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Info "uv venv .venv"
    uv venv .venv
}
Write-Info "uv pip install requirements + pandas"
uv pip install -r requirements.txt pandas

if (-not (Test-Path (Join-Path $ServerDir ".env"))) {
    Write-Info "Generating server\.env (admin password printed once)..."
    $py = ".\.venv\Scripts\python.exe"
    $secret = & $py -c "import secrets; print(secrets.token_urlsafe(32))"
    $pw = & $py -c "import secrets; print(secrets.token_urlsafe(9))"
    $hash = & $py -c "import bcrypt,sys; print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt()).decode())" $pw
    @"
IVYEA_OPS_HOST=127.0.0.1
IVYEA_OPS_PORT=8001
IVYEA_OPS_DEV=0
IVYEA_OPS_SECRET=$secret
IVYEA_OPS_USER=admin
IVYEA_OPS_PASSWORD_HASH=$hash
IVYEA_OPS_ALLOWED_ORIGINS=http://127.0.0.1:8001
"@ | Set-Content -Path ".env" -Encoding utf8
    Write-Host "  admin password: $pw" -ForegroundColor Yellow
    Write-Host "  username: admin — change after first login" -ForegroundColor Yellow
} else {
    Write-Info "server\.env exists — skip"
}

New-Item -ItemType Directory -Force -Path (Join-Path $IvyRoot "data"), (Join-Path $IvyRoot "logs") | Out-Null

if (-not (Test-Path (Join-Path $ClientDir "dist\index.html"))) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node 18+ required to build client"
    }
    Write-Info "npm install + build client"
    Set-Location $ClientDir
    $env:NODE_ENV = "development"
    npm install --no-audit --no-fund
    npm run build
    if (-not (Test-Path "dist\index.html")) { throw "client build failed" }
} else {
    Write-Info "client\dist present — skip build"
}

Write-Info "Done. Next: start_ivyeaops_sellfox.ps1 then ingest_sellfox_for_ivyeaops.ps1"
