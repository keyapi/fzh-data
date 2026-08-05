#!/usr/bin/env bash
# One-command Portal start (bash). Prerequisite: open_webui compose up.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OWUI="$(cd "$ROOT/../open_webui" && pwd)"

if ! docker network inspect open_webui_public >/dev/null 2>&1; then
  echo "[portal] open_webui_public missing — starting shell PoC first…"
  (cd "$OWUI" && docker compose up -d)
fi

cd "$ROOT"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[portal] created .env from .env.example"
fi
if [[ ! -f ../board/out/candidates.json ]]; then
  echo "[portal] board/out missing — using fixtures/board_out"
  export BOARD_OUT_HOST=./fixtures/board_out
fi
docker compose up -d --build
echo "[portal] ready → http://127.0.0.1:${PORTAL_PORT:-8088}/"
echo "[portal] e2e: uv run python scripts/e2e_verify.py"
