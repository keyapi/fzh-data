#!/usr/bin/env bash
# GitHub SSH 被阻断时临时走 HTTPS，推完自动把 origin 切回去。
# 用法: ./git_push_https.sh [仓库路径] [传给 git push 的参数...]
# 例:   ./git_push_https.sh ~/frappe-bench/apps/key_test --dry-run
set -euo pipefail

repo="$PWD"
args=()
if [ $# -gt 0 ] && [ -d "$1" ]; then
  repo="$1"; shift
fi
if [ $# -gt 0 ]; then args=("$@"); fi

cd "$repo"
orig="$(git remote get-url origin)"
case "$orig" in
  git@github.com:*)       https="https://github.com/${orig#git@github.com:}" ;;
  ssh://git@github.com/*) https="https://github.com/${orig#ssh://git@github.com/}" ;;
  https://*)              echo "origin 已是 HTTPS，直接推送" >&2; exec git push ${args[@]+"${args[@]}"} ;;
  *) echo "无法识别 origin: $orig" >&2; exit 2 ;;
esac

git remote set-url origin "$https"
trap 'git remote set-url origin "$orig"; echo "已恢复 origin → $orig"' EXIT
git push ${args[@]+"${args[@]}"}
