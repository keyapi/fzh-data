#!/usr/bin/env python3
"""
Auto-bind Daily-20 subscription plan to new DingTalk OAuth users.

Runs as a cron job (every minute). Queries MySQL for users who:
  1. Have a DingTalk OAuth binding (user_oauth_bindings table)
  2. Do NOT have any active subscription (user_subscriptions table)
Then binds them to the "Daily-20" plan (plan_id=2).

Idempotent — running multiple times won't double-bind.

Usage:
    python3 auto-bind-subscription.py
"""

import secrets
import string
import subprocess
import sys
import time
from datetime import datetime, timedelta

PLAN_ID = 2
DAILY_QUOTA = 1370000  # ~20 RMB worth of quota

MYSQL_CMD = [
    "docker", "exec", "-i", "new-api-mysql",
    "mysql", "-uroot", "-pnew-api-root-pwd",
    "new_api", "-N", "-B",
]


def run_mysql(query: str) -> str:
    """Run a MySQL query via docker exec and return stdout."""
    proc = subprocess.run(
        MYSQL_CMD + ["-e", query],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        print(f"[ERROR] MySQL query failed: {proc.stderr}", file=sys.stderr)
        sys.exit(1)
    return proc.stdout.strip()


def find_unbound_users() -> list[int]:
    """Return user IDs with DingTalk OAuth but no active subscription."""
    output = run_mysql("""
        SELECT u.id
        FROM users u
        INNER JOIN user_oauth_bindings b
            ON u.id = b.user_id
        LEFT JOIN user_subscriptions s
            ON u.id = s.user_id AND s.status = 'active'
        WHERE s.id IS NULL
    """)
    if not output:
        return []
    return [int(line) for line in output.split("\n") if line.strip()]


def bind_subscription(user_id: int) -> bool:
    """Create an active Daily-20 subscription for the given user. Returns True on success."""
    now = int(time.time())
    # next_reset = midnight tomorrow in server local time (Asia/Shanghai)
    # Same logic as new-api's calcNextResetTime for "daily" period
    local_now = datetime.now()
    tomorrow_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    next_reset = int(tomorrow_midnight.timestamp())
    end_time = now + 365 * 24 * 3600  # 12 months

    sql = f"""
        INSERT INTO user_subscriptions
            (user_id, plan_id, amount_total, amount_used,
             start_time, end_time, status, source,
             last_reset_time, next_reset_time,
             allow_wallet_overflow, created_at, updated_at)
        VALUES
            ({user_id}, {PLAN_ID}, {DAILY_QUOTA}, 0,
             {now}, {end_time}, 'active', 'admin',
             {now}, {next_reset},
             0, {now}, {now})
    """
    try:
        run_mysql(sql)
        return True
    except SystemExit:
        return False


def find_tokenless_users() -> list[int]:
    """Return user IDs with DingTalk OAuth but no token."""
    output = run_mysql("""
        SELECT u.id
        FROM users u
        INNER JOIN user_oauth_bindings b ON u.id = b.user_id
        LEFT JOIN tokens t ON u.id = t.user_id
        WHERE t.id IS NULL
    """)
    if not output:
        return []
    return [int(line) for line in output.split("\n") if line.strip()]


def create_default_token(user_id: int) -> bool:
    """Create a default API token for the given user."""
    key = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(48))
    now = int(time.time())
    sql = f"""
        INSERT INTO tokens
            (user_id, `key`, name, status, remain_quota, unlimited_quota,
             created_time, expired_time)
        VALUES
            ({user_id}, '{key}', 'Default', 1, 0, 1, {now}, -1)
    """
    try:
        run_mysql(sql)
        return True
    except SystemExit:
        return False


def main():
    # 1. Auto-bind subscription
    users = find_unbound_users()
    for uid in users:
        if bind_subscription(uid):
            print(f"[OK] Bound Daily-20 to user_id={uid}")
        else:
            print(f"[FAIL] Failed to bind user_id={uid}", file=sys.stderr)

    # 2. Auto-create default token
    tokenless = find_tokenless_users()
    for uid in tokenless:
        if create_default_token(uid):
            print(f"[OK] Created default token for user_id={uid}")
        else:
            print(f"[FAIL] Failed to create token for user_id={uid}", file=sys.stderr)


if __name__ == "__main__":
    main()
