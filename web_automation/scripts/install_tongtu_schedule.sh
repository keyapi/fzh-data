#!/usr/bin/env bash
# install_tongtu_schedule.sh
# Register a crontab job that runs the Tongtu auto export on a schedule, unattended.
# When the 7-day login cookie expires, --auto-login makes the script lazily install
# OCR (first time) and recognise the captcha itself.
#
# ASCII-only on purpose (portable, no BOM). Linux / macOS.
#
# Usage (run from the fzh-data repo root):
#   ./web_automation/scripts/install_tongtu_schedule.sh --task stock  --every 12      # every 12 hours
#   ./web_automation/scripts/install_tongtu_schedule.sh --task sales  --at 02:00      # daily 02:00
#   ./web_automation/scripts/install_tongtu_schedule.sh --task both   --every 8
#   ./web_automation/scripts/install_tongtu_schedule.sh --remove
#
# Notes:
#   - Default task is stock.
#   - Either --every N (hours) or --at HH:MM (daily). If both, --every wins.
#   - The PC must be on and the user logged in; cron only fires while the box runs.
#   - Logs append to <repo>/web_automation/logs/export-<task>.log

set -euo pipefail

TASK="stock"
EVERY=0
AT=""
REMOVE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --task)  TASK="$2"; shift 2 ;;
    --every) EVERY="$2"; shift 2 ;;
    --at)    AT="$2"; shift 2 ;;
    --remove) REMOVE=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$TASK" in
  stock|sales|both) ;;
  *) echo "--task must be stock|sales|both" >&2; exit 2 ;;
esac

REPO="$(pwd)"
LOGDIR="$REPO/web_automation/logs"
mkdir -p "$LOGDIR"

TASKS=()
if [ "$TASK" = "both" ]; then TASKS=(stock sales); else TASKS=("$TASK"); fi

resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return
    fi
  done
  echo "uv not found in PATH or ~/.local/bin / ~/.cargo/bin" >&2
  exit 2
}

UV_BIN="$(resolve_uv)"
REPO_Q=$(printf '%q' "$REPO")
LOGDIR_Q=$(printf '%q' "$LOGDIR")
UV_Q=$(printf '%q' "$UV_BIN")
PATH_PREFIX_Q=$(printf '%q' "$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin")

# Build minute/hour fields.
MIN=0; HOUR=""
if [ "$EVERY" -gt 0 ]; then
  HOUR="*/$EVERY"
elif [ -n "$AT" ]; then
  HOUR="${AT%%:*}"
  MIN="${AT##*:}"
else
  echo "Provide --every N (hours) or --at HH:MM (daily)." >&2
  exit 2
fi

cron_line() {
  local t="$1"
  local marker="FZH-TongtuAutoExport-$t"
  # shellcheck disable=SC2059
  printf '%s %s * * * PATH=%s cd %s && %s run python web_automation/scripts/dispatch.py tongtu.%s.export -- --auto-login >> %s/export-%s.log 2>&1 # %s\n' \
    "$MIN" "$HOUR" "$PATH_PREFIX_Q" "$REPO_Q" "$UV_Q" "$t" "$LOGDIR_Q" "$t" "$marker"
}

reg_one() {
  local t="$1" marker="FZH-TongtuAutoExport-$t"
  local line
  line="$(cron_line "$t")"
  { crontab -l 2>/dev/null || true; printf '%s' "$line"; } | crontab -
  if ! crontab -l | grep -F "# $marker" >/dev/null; then
    echo "Failed to register crontab for $marker" >&2
    exit 1
  fi
  echo "Registered crontab for $marker"
}

remove_all() {
  for t in "${TASKS[@]}"; do
    local marker="FZH-TongtuAutoExport-$t"
    local current
    current="$(crontab -l 2>/dev/null || true)"
    if [ -z "$current" ]; then
      echo "Removed (if existed): $marker"
      continue
    fi
    printf '%s\n' "$current" | grep -vF "# $marker" | crontab -
    echo "Removed (if existed): $marker"
  done
}

if [ "$REMOVE" -eq 1 ]; then remove_all; exit 0; fi

for t in "${TASKS[@]}"; do reg_one "$t"; done
echo ""
echo "Verify with:  crontab -l | grep FZH-Tongtu"
echo "Logs: $LOGDIR"
