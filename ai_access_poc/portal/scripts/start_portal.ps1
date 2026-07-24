# One-command Portal start (PowerShell). Prerequisite: open_webui compose up.
# Do NOT use Start-Job for web services (Lesson 58).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Owui = Join-Path (Split-Path -Parent $Root) "open_webui"

$net = docker network inspect open_webui_public 2>$null
if (-not $net) {
  Write-Host "[portal] open_webui_public missing — starting shell PoC first…"
  Push-Location $Owui
  docker compose up -d
  Pop-Location
}

Set-Location $Root
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "[portal] created .env from .env.example"
}

$boardOut = Join-Path (Split-Path -Parent $Root) "board\out"
if (-not (Test-Path (Join-Path $boardOut "candidates.json"))) {
  Write-Host "[portal] board/out missing — using fixtures/board_out"
  $env:BOARD_OUT_HOST = "./fixtures/board_out"
}

docker compose up -d --build
$port = if ($env:PORTAL_PORT) { $env:PORTAL_PORT } else { "8088" }
Write-Host "[portal] ready → http://127.0.0.1:$port/"
Write-Host "[portal] e2e: uv run python scripts/e2e_verify.py"
