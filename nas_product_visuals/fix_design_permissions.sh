#!/bin/bash
# 在"设计稿"文件夹中添加 DENY ACE 移除"视觉需求（读取）"权限
# 两阶段: 启动扫描 + inotify 实时监控
#
# DSM 计划任务 (开机触发, root):
#   flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh'
#
# 测试: BASE_PATH=/volume1/技术部, 生产: /volume1/产品信息

BASE_PATH="/volume1/技术部"
INOTIFY="/usr/local/bin/inotifywait"
TARGET_GROUP="视觉需求（读取）"
TARGET_DIR="设计稿"
SYNOACL="/usr/syno/bin/synoacltool"
LOG_TAG="[fix-design-perms]"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG $*"; }

# ── 核心: 为设计稿目录添加 DENY ACE ──
# 关键: 直接 pipe synoacltool → grep -F, 不经过 echo (POSIX locale 会破坏 UTF-8)
fix_one() {
    local dir="$1"
    [[ -d "$dir" ]] || return 0

    # 等待 BTRFS ACL 沉降 (删除重建后旧 ACL 异步恢复)
    sleep 2

    # 已有 deny → 跳过
    if $SYNOACL -get "$dir" 2>/dev/null | grep -F "视觉需求" | grep -q "deny"; then
        return 0
    fi

    # 无此组 → 跳过
    if ! $SYNOACL -get "$dir" 2>/dev/null | grep -qF "视觉需求"; then
        return 0
    fi

    # 添加全权限拒绝
    if $SYNOACL -add "$dir" "group:${TARGET_GROUP}:deny:rwxpdDaARWcCo:fd--" >/dev/null 2>&1; then
        log "fixed: $dir"
    else
        log "FAILED: $dir"
    fi
}

# ── Phase 1: 启动扫描 ──
run_scan() {
    log "Phase 1: scanning..."
    local count=0
    while IFS= read -r -d '' dir; do
        fix_one "$dir" && ((count++))
    done < <(find "$BASE_PATH" -type d -name "$TARGET_DIR" \
        ! -path "*/@eaDir/*" ! -path "*/#recycle/*" -print0 2>/dev/null)
    log "Phase 1 done: $count dirs processed"
}

# ── Phase 2: inotify 监控 ──
run_monitor() {
    if [[ ! -x "$INOTIFY" ]]; then
        log "ERROR: inotifywait not found at $INOTIFY"
        exit 1
    fi
    echo 65536 > /proc/sys/fs/inotify/max_user_watches 2>/dev/null || true

    log "Phase 2: monitoring on $BASE_PATH"
    while true; do
        "$INOTIFY" -q -m -r \
            -e create -e moved_to \
            --format '%w%f' \
            --exclude '(@eaDir|#recycle)' \
            "$BASE_PATH" 2>/dev/null | while read -r new_path; do
            [[ -d "$new_path" ]] || continue
            [[ "$(basename "$new_path")" == "$TARGET_DIR" ]] || continue
            fix_one "$new_path"
        done
        log "inotifywait exited, restart in 5s..."
        sleep 5
        # 补漏扫描
        find "$BASE_PATH" -type d -name "$TARGET_DIR" \
            ! -path "*/@eaDir/*" ! -path "*/#recycle/*" \
            -print0 2>/dev/null | while IFS= read -r -d '' dir; do
            fix_one "$dir"
        done
    done
}

log "=== starting ==="
run_scan
run_monitor
