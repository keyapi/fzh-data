#!/usr/bin/env python3
"""
重置某个用户「今天」的订阅额度：作废当前订阅 + 按同一套餐新建。

等价于后台「用户管理 → 更多 → 订阅管理 → 作废 → 新增订阅」，但一条命令完成。
全部走 new-api 官方管理接口，不直接改表，避免复制业务逻辑（下次重置时间等）。

用法:
    python3 reset-user-quota.py --user 高琪              # 按当前套餐重置
    python3 reset-user-quota.py --user 7 --plan 3        # 换成 Daily-50 重置
    python3 reset-user-quota.py --user 高琪 --dry-run     # 只看会做什么
    python3 reset-user-quota.py --init-token             # 首次：生成本脚本用的管理令牌

凭证：脚本读 /opt/new-api/.secrets.env 的 NEW_API_ADMIN_TOKEN（root 的 access_token），
不打印、不落日志。令牌等同于 root 权限，文件权限应保持 600。
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

SECRETS_FILE = "/opt/new-api/.secrets.env"
BASE_URL = os.getenv("NEW_API_BASE", "http://127.0.0.1:3000").rstrip("/")
ROOT_USER_ID = 1
TOKEN_KEY = "NEW_API_ADMIN_TOKEN"


# ── 凭证与数据库 ────────────────────────────────────────────────────

def _read_secrets() -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.isfile(SECRETS_FILE):
        return out
    for line in open(SECRETS_FILE, encoding="utf-8").read().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip("'")
    return out


def _set_secret(key: str, value: str) -> None:
    lines = []
    if os.path.isfile(SECRETS_FILE):
        lines = open(SECRETS_FILE, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    with open(SECRETS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(SECRETS_FILE, 0o600)


def _mysql(sql: str) -> str:
    pwd = _read_secrets().get("MYSQL_ROOT_PASSWORD", "")
    if not pwd:
        sys.exit("[FAIL] 缺少 MYSQL_ROOT_PASSWORD（/opt/new-api/.secrets.env）")
    proc = subprocess.run(
        ["docker", "exec", "-e", f"MYSQL_PWD={pwd}", "-i", "new-api-mysql",
         "mysql", "-uroot", "--default-character-set=utf8mb4", "new_api", "-N", "-B", "-e", sql],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        sys.exit(f"[FAIL] MySQL: {proc.stderr.strip()}")
    return proc.stdout.strip()


def resolve_user(arg: str) -> tuple[int, str, int]:
    """接受用户名或数字 ID，返回 (id, username, status)。"""
    if arg.isdigit():
        where = f"id = {int(arg)}"
    else:
        where = "username = '" + arg.replace("\\", "\\\\").replace("'", "''") + "'"
    rows = _mysql(f"SELECT id, username, status FROM users WHERE {where};")
    if not rows:
        sys.exit(f"[FAIL] 找不到用户: {arg}")
    uid, name, status = rows.splitlines()[0].split("\t")
    return int(uid), name, int(status)


def init_token() -> int:
    """为 root 生成一个 access_token 并写入 .secrets.env（幂等）。"""
    existing = _read_secrets().get(TOKEN_KEY, "")
    if existing:
        row = _mysql(f"SELECT id FROM users WHERE id = {ROOT_USER_ID} AND access_token = '{existing}';")
        if row:
            print("[OK] 管理令牌已存在且有效")
            return 0
    token = secrets.token_hex(16)
    _mysql(f"UPDATE users SET access_token = '{token}' WHERE id = {ROOT_USER_ID};")
    _set_secret(TOKEN_KEY, token)
    print("[OK] 已为 root 生成管理令牌并写入 .secrets.env（600）")
    return 0


# ── new-api 管理接口 ────────────────────────────────────────────────

def api(method: str, path: str, body: dict | None = None) -> dict:
    token = _read_secrets().get(TOKEN_KEY, "")
    if not token:
        sys.exit("[FAIL] 缺少 NEW_API_ADMIN_TOKEN，先运行: python3 reset-user-quota.py --init-token")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, method=method)
    req.add_header("Authorization", token)
    req.add_header("New-Api-User", str(ROOT_USER_ID))
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"[FAIL] HTTP {e.code} {path}: {e.read().decode()[:200]}")
    if not payload.get("success"):
        sys.exit(f"[FAIL] {path}: {payload.get('message')}")
    return payload.get("data")


def active_subscriptions(user_id: int) -> list[dict]:
    data = api("GET", f"/api/subscription/admin/users/{user_id}/subscriptions") or []
    # 接口返回的是 [{"subscription": {...}, "plan": {...}}]，这里只取订阅本体
    subs = [item.get("subscription", item) for item in data]
    return [s for s in subs if s.get("status") == "active"]


# ── 主流程 ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="重置用户今日订阅额度（作废 + 按套餐新建）")
    ap.add_argument("--user", help="用户名或用户 ID")
    ap.add_argument("--plan", type=int, help="新建用的套餐 ID（默认沿用当前套餐）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要执行的动作")
    ap.add_argument("--init-token", action="store_true", help="为 root 生成管理令牌后退出")
    args = ap.parse_args()

    if args.init_token:
        return init_token()
    if not args.user:
        ap.error("--user 必填")

    uid, name, status = resolve_user(args.user)
    if status != 1:
        print(f"[WARN] 用户 {name}(id={uid}) 当前 status={status}（非启用），额度重置对它没有实际意义")

    subs = active_subscriptions(uid)
    plan_id = args.plan or (subs[0].get("plan_id") if subs else None)
    if not plan_id:
        sys.exit(f"[FAIL] 用户 {name} 没有生效订阅，也没有给 --plan，无从重置")

    print(f"用户: {name} (id={uid})")
    for s in subs:
        print(f"  当前订阅 id={s.get('id')} plan={s.get('plan_id')} "
              f"已用={s.get('amount_used')}/{s.get('amount_total')}")

    if args.dry_run:
        for s in subs:
            print(f"[DRY] 作废订阅 id={s.get('id')}")
        print(f"[DRY] 按 plan_id={plan_id} 新建订阅")
        return 0

    for s in subs:
        api("POST", f"/api/subscription/admin/user_subscriptions/{s.get('id')}/invalidate")
        print(f"[OK] 已作废订阅 id={s.get('id')}")

    api("POST", f"/api/subscription/admin/users/{uid}/subscriptions", {"plan_id": plan_id})
    print(f"[OK] 已按 plan_id={plan_id} 新建订阅")

    fresh = active_subscriptions(uid)
    if not fresh:
        print("[FAIL] 新建后查不到生效订阅，请到后台确认")
        return 2
    for s in fresh:
        print(f"  新建订阅 id={s.get('id')} 已用={s.get('amount_used')}/{s.get('amount_total')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
