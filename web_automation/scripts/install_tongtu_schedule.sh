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

# Build minute/hour fields.
MIN=0; HOUR=""
if [ "$EVERY" -gt 0 ]; then
  HOUR="*/$EVERY"
elif [ -n "$AT" ]; then
  # expects HH:MM
  HOUR="${AT%%:*}"
  MIN="${AT##*:}"
else
  echo "Provide --every N (hours) or --at HH:MM (daily)." >&2
  exit 2
fi

cron_line() {
  local t="$1"
  # minute hour dom month dow command ; the trailing comment is the marker we
  # grep to replace on re-register / remove.
  printf '%s %s * * * cd %s && uv run python web_automation/scripts/dispatch.py tongtu.%s.export -- --auto-login >> %s/export-%s.log 2>&1  # FZH-TongtuAutoExport-%s\n' \
    "$MIN" "$HOUR" "$REPO" "$t" "$LOGDIR" "$t" "$t"
}

reg_one() {
  local t="$1" marker="FZH-TongtuAutoExport-$t"
  local line; line="$(cron_line "$t")"
  # Remove any prior line carrying this marker, then append the new one.
  crontab -l 2>/dev/null | grep -v "# $marker" | crontab -
  ( crontab -l 2>/dev/null; printf '%s' "$line" ) | crontab -
  echo "Registered crontab for $marker"
}

remove_all() {
  for t in "${TASKS[@]}"; do
    crontab -l 2>/dev/null | grep -v "# FZH-TongtuAutoExport-$t" | crontab -
    echo "Removed (if existed): FZH-TongtuAutoExport-$t"
  done
}

if [ "$REMOVE" -eq 1 ]; then remove_all; exit 0; fi

for t in "${TASKS[@]}"; do reg_one "$t"; done
echo ""
echo "Verify with:  crontab -l | grep FZH-Tongtu"
echo "Logs: $LOGDIR"
