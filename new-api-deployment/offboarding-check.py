#!/usr/bin/env python3
"""
Periodic offboarding check — verify DingTalk employee status via App Token.

Runs daily (cron). Uses app-level access token (client_credentials) to query
DingTalk API for each OAuth-linked user's active status. Disables new-api
accounts for employees no longer in the organization.

Requires: qyapi_get_member permission

Usage:
    python3 offboarding-check.py
    python3 offboarding-check.py --dry-run              # 只记不封（仍写 audit；不改 users/proxy/identity_map）
    python3 offboarding-check.py --union-id <unionId>    # 只看某一个人（含已封用户）
    python3 offboarding-check.py --force                 # 跳过「全员 60121」熔断
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# 凭证不硬编码：从环境变量或 /opt/new-api/.secrets.env 读取
SECRETS_FILE = Path("/opt/new-api/.secrets.env")

# getbyunionid: 该 unionId 在当前企业通讯录范围内查不到对应员工（已移出组织）
ERRCODE_USER_NOT_FOUND = 60121
# 一次跑批里「全部都是 60121」且人数达到此阈值 → 更像 token/通讯录权限故障，熔断不封
MASS_DEPART_MIN = 3


def _secret(key: str) -> str:
    v = os.environ.get(key, "").strip()
    if v:
        return v
    if SECRETS_FILE.is_file():
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return ""


def _mysql_pwd() -> str:
    pwd = _secret("MYSQL_ROOT_PASSWORD")
    if not pwd:
        raise RuntimeError("MYSQL_ROOT_PASSWORD 未配置：请设环境变量或写 /opt/new-api/.secrets.env")
    return pwd


def _proxy_db_path() -> str:
    return _secret("PROXY_DB_PATH") or "/data/sellfox-proxy/sellfox-proxy.db"


def run_mysql(query: str) -> str:
    cmd = [
        "docker", "exec", "-e", f"MYSQL_PWD={_mysql_pwd()}",
        "-i", "new-api-mysql",
        "mysql", "-uroot", "new_api", "-N", "-B",
        "-e", query,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"MySQL error: {proc.stderr}")
    return proc.stdout.strip()


def api_post(url: str, body: dict) -> dict:
    """POST JSON to an API endpoint, return parsed response."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_app_token() -> str:
    """Obtain app-level access token via client_credentials."""
    app_key = _secret("DINGTALK_APP_KEY")
    app_secret = _secret("DINGTALK_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("DINGTALK_APP_KEY / DINGTALK_APP_SECRET 未配置")
    result = api_post("https://api.dingtalk.com/v1.0/oauth2/accessToken", {
        "appKey": app_key,
        "appSecret": app_secret,
        "grantType": "client_credentials",
    })
    token = result.get("accessToken")
    if not token:
        raise RuntimeError(f"Failed to get app token: {result}")
    return token


def _esc(value) -> str:
    """Escape a value for inline MySQL SQL (docker exec 无参数绑定)."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


# ── Schema (幂等，跑一次自动建) ───────────────────────────────────────

DDL_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS dingtalk_identity_map (
      union_id         VARCHAR(128) PRIMARY KEY,
      dingtalk_user_id VARCHAR(128) NOT NULL,
      display_name     VARCHAR(255),
      last_verified_ts INT NOT NULL,
      created_at       INT NOT NULL,
      KEY idx_dtmap_userid (dingtalk_user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS offboarding_audit (
      id INT AUTO_INCREMENT PRIMARY KEY,
      ts INT NOT NULL,
      channel ENUM('stream','daily','dryrun','manual') NOT NULL,
      union_id VARCHAR(128),
      new_api_user_id INT,
      username VARCHAR(128),
      dingtalk_user_id VARCHAR(128),
      proxy_keys_disabled INT NOT NULL DEFAULT 0,
      result VARCHAR(32) NOT NULL
    )
    """,
]


def ensure_schema():
    for ddl in DDL_TABLES:
        run_mysql(ddl.strip())


def resolve_provider_id() -> int:
    """Resolve dingtalk custom OAuth provider id by slug. Fail loudly if absent."""
    out = run_mysql("SELECT id FROM custom_oauth_providers WHERE slug='dingtalk'")
    rows = [line for line in out.split("\n") if line.strip()] if out else []
    if not rows:
        raise RuntimeError("custom_oauth_providers 中找不到 slug='dingtalk' 的 provider，无法继续")
    return int(rows[0].strip())


def upsert_identity_map(union_id: str, userid: str, display_name: str | None):
    now = int(time.time())
    run_mysql(
        "INSERT INTO dingtalk_identity_map "
        "(union_id, dingtalk_user_id, display_name, last_verified_ts, created_at) "
        f"VALUES ({_esc(union_id)}, {_esc(userid)}, {_esc(display_name)}, {now}, {now}) "
        "ON DUPLICATE KEY UPDATE dingtalk_user_id=VALUES(dingtalk_user_id), "
        "display_name=VALUES(display_name), last_verified_ts=VALUES(last_verified_ts)"
    )


def delete_identity_map(union_id: str):
    run_mysql(f"DELETE FROM dingtalk_identity_map WHERE union_id = {_esc(union_id)}")


def insert_audit(channel: str, result: str, *, union_id=None, new_api_user_id=None,
                 username=None, dingtalk_user_id=None, proxy_keys_disabled: int = 0):
    run_mysql(
        "INSERT INTO offboarding_audit "
        "(ts, channel, union_id, new_api_user_id, username, dingtalk_user_id, "
        " proxy_keys_disabled, result) "
        f"VALUES ({int(time.time())}, {_esc(channel)}, {_esc(union_id)}, "
        f"{'NULL' if new_api_user_id is None else int(new_api_user_id)}, "
        f"{_esc(username)}, {_esc(dingtalk_user_id)}, {int(proxy_keys_disabled)}, {_esc(result)})"
    )


# ── 就业状态判定 ──────────────────────────────────────────────────────

def classify_employment(union_id: str, app_token: str) -> tuple[str, str | None, str]:
    """
    判定一个 unionId 对应员工的组织状态。

    返回 (state, userid, reason)：
      state 取值：
        "DEPARTED" — getbyunionid 返回 60121（未找到对应员工，已移出组织）→ 应封号
        "OK"       — 员工仍在组织内（getbyunionid 成功）→ 不封号，并刷新 identity_map
        "RETRY"    — 系统繁忙 / 其它错误 → 本次跳过，等下一轮；绝不含糊禁用
    注意：不以 user/get 的 active 字段作为封号依据（active=false 只表示未激活钉钉，
    不代表离职）；也未依赖未在官方文档确认的 user/get status(在职/离职) 字段。
    """
    try:
        result = api_post(
            f"https://oapi.dingtalk.com/topapi/user/getbyunionid?access_token={app_token}",
            {"unionid": union_id},
        )
    except Exception as e:
        return "RETRY", None, f"getbyunionid network error: {e}"
    try:
        errcode = int(result.get("errcode"))
    except (TypeError, ValueError):
        return "RETRY", None, f"getbyunionid bad errcode={result.get('errcode')!r}"
    if errcode == ERRCODE_USER_NOT_FOUND:
        return "DEPARTED", None, "getbyunionid 60121 (not in org)"
    if errcode != 0:
        return "RETRY", None, f"getbyunionid errcode={errcode} {result.get('errmsg')}"
    userid = (result.get("result") or {}).get("userid")
    if not userid:
        return "RETRY", None, "getbyunionid ok but no userid"
    return "OK", userid, ""


# ── Proxy key 禁用 ────────────────────────────────────────────────────

def disable_proxy_keys(union_id: str) -> int:
    """Disable all active proxy API keys for a departed DingTalk user.
    Returns the number of keys disabled. Raises if proxy DB unreachable.
    """
    db_path = _proxy_db_path()
    if not os.path.exists(db_path):
        raise RuntimeError(f"proxy DB not found: {db_path}")
    db = sqlite3.connect(db_path)
    try:
        cur = db.execute(
            "UPDATE api_keys SET is_active = 0 "
            "WHERE dingtalk_union_id = ? AND is_active = 1",
            (union_id,),
        )
        count = cur.rowcount
        db.commit()
        return count
    finally:
        db.close()


# ── 主流程 ────────────────────────────────────────────────────────────

def should_abort_mass_depart(departed_count: int, classified_count: int) -> bool:
    """全员 60121 且人数足够多 → 更像钉钉权限/token 故障，不要一次封光。"""
    return classified_count >= MASS_DEPART_MIN and departed_count == classified_count


def fetch_bound_users(provider_id: int, union_id_filter: str | None) -> list[dict]:
    """查询钉钉 OAuth 绑定的 new-api 用户。

    默认：status=1（待判定）以及 status=2 但仍留在 identity_map 的人
    （proxy 上次没关成功，必须重试）。带 --union-id 时不限 status。
    """
    if union_id_filter:
        query = (
            "SELECT u.id, u.username, u.status, b.provider_user_id "
            "FROM users u JOIN user_oauth_bindings b ON u.id = b.user_id "
            f"WHERE b.provider_id = {provider_id} "
            f"AND b.provider_user_id = {_esc(union_id_filter)}"
        )
    else:
        query = (
            "SELECT u.id, u.username, u.status, b.provider_user_id "
            "FROM users u JOIN user_oauth_bindings b ON u.id = b.user_id "
            f"WHERE b.provider_id = {provider_id} AND ("
            "u.status = 1 OR ("
            "u.status = 2 AND EXISTS ("
            "SELECT 1 FROM dingtalk_identity_map m "
            "WHERE m.union_id = b.provider_user_id)))"
        )
    output = run_mysql(query)
    if not output:
        return []
    users = []
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        users.append({
            "id": int(parts[0]),
            "username": parts[1],
            "status": int(parts[2]),
            "union_id": parts[3],
        })
    return users


def _retry_proxy_only(user: dict, channel: str, dry_run: bool) -> str:
    """new-api 已是 status=2，只补关 proxy。成功才删 identity_map。"""
    uid = user["id"]
    username = user["username"]
    union_id = user["union_id"]
    if dry_run:
        insert_audit("dryrun", "proxy_pending", union_id=union_id, new_api_user_id=uid,
                     username=username)
        print(f"  [DRYRUN] {username} (id={uid}) — would retry proxy keys")
        return "proxy_pending"
    try:
        proxy_count = disable_proxy_keys(union_id)
    except Exception as e:
        print(f"  [WARN] 禁用 proxy key 失败（new-api 已封，下次重试）: {e}")
        insert_audit(channel, "proxy_pending", union_id=union_id, new_api_user_id=uid,
                     username=username)
        return "proxy_pending"
    insert_audit(channel, "disabled", union_id=union_id, new_api_user_id=uid,
                 username=username, proxy_keys_disabled=proxy_count)
    delete_identity_map(union_id)
    print(f"  [PROXY-RETRY] {username} (id={uid}) — proxy keys disabled={proxy_count}")
    return "disabled"


def _disable_departed(user: dict, userid: str | None, channel: str, dry_run: bool) -> str:
    """封 new-api；proxy 失败则保留 identity_map 供次日重试。"""
    uid = user["id"]
    username = user["username"]
    union_id = user["union_id"]
    if dry_run:
        insert_audit("dryrun", "departed", union_id=union_id, new_api_user_id=uid,
                     username=username, dingtalk_user_id=userid)
        print(f"  [DRYRUN] {username} (id={uid}) — would disable (departed)")
        return "departed"

    run_mysql(f"UPDATE users SET status = 2 WHERE id = {uid} AND status = 1")
    print(f"  [OFFBOARD] {username} (id={uid}) — departed, disabled")
    try:
        proxy_count = disable_proxy_keys(union_id)
    except Exception as e:
        print(f"  [WARN] 禁用 proxy key 失败（new-api 已封，下次重试）: {e}")
        insert_audit(channel, "proxy_pending", union_id=union_id, new_api_user_id=uid,
                     username=username, dingtalk_user_id=userid)
        return "proxy_pending"
    insert_audit(channel, "disabled", union_id=union_id, new_api_user_id=uid,
                 username=username, dingtalk_user_id=userid,
                 proxy_keys_disabled=proxy_count)
    delete_identity_map(union_id)
    return "disabled"


def main():
    parser = argparse.ArgumentParser(description="离职兜底检查（每日 cron）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只记不封（仍写 audit；不改 users/proxy/identity_map）")
    parser.add_argument("--union-id", default=None,
                        help="只检查指定 unionId 的绑定用户（含已封用户）")
    parser.add_argument("--force", action="store_true",
                        help="跳过全员 60121 熔断（确认是真批量离职时再用）")
    args = parser.parse_args()

    channel = "dryrun" if args.dry_run else "daily"

    # 预检只要 schema / provider / 钉钉 token。proxy sqlite 挂了仍先封 new-api。
    try:
        ensure_schema()
        provider_id = resolve_provider_id()
        app_token = get_app_token()
    except Exception as e:
        print(f"[FATAL] 预检失败，本次不执行封号: {e}", file=sys.stderr)
        sys.exit(2)

    users = fetch_bound_users(provider_id, args.union_id)
    if not users:
        insert_audit(channel, "ok")
        suffix = f" unionId={args.union_id}" if args.union_id else ""
        print(f"[OK] No active DingTalk OAuth users to check{suffix}")
        return

    print(f"Checking {len(users)} DingTalk user(s)...")

    to_classify = [u for u in users if u["status"] != 2]
    classified: list[tuple[dict, str, str | None, str]] = []
    for user in to_classify:
        try:
            state, userid, reason = classify_employment(user["union_id"], app_token)
        except Exception as e:
            state, userid, reason = "RETRY", None, f"classify error: {e}"
        classified.append((user, state, userid, reason))

    departed_n = sum(1 for _, state, __, ___ in classified if state == "DEPARTED")
    if (
        not args.force
        and not args.union_id
        and should_abort_mass_depart(departed_n, len(classified))
    ):
        print(
            f"[FATAL] 全员 {departed_n}/{len(classified)} 均为 60121，疑似钉钉权限/token 故障，"
            "本次不封号。确认是真批量离职后加 --force。",
            file=sys.stderr,
        )
        insert_audit(channel, "abort")
        sys.exit(2)

    disabled_total = 0
    proxy_failed = False

    for user in users:
        if user["status"] == 2:
            result = _retry_proxy_only(user, channel, args.dry_run)
            if result == "proxy_pending" and not args.dry_run:
                proxy_failed = True
            elif result == "disabled":
                disabled_total += 1
            continue

        match = next((c for c in classified if c[0] is user), None)
        if match is None:
            continue
        _, state, userid, reason = match
        username = user["username"]
        union_id = user["union_id"]
        uid = user["id"]

        if state == "RETRY":
            print(f"  [SKIP] {username} — {reason}")
            insert_audit(channel, "skip", union_id=union_id, new_api_user_id=uid,
                         username=username)
            continue

        if state == "OK":
            if userid and not args.dry_run:
                upsert_identity_map(union_id, userid, username)
            print(f"  [OK] {username} — active")
            continue

        result = _disable_departed(user, userid, channel, args.dry_run)
        if result == "proxy_pending":
            proxy_failed = True
            disabled_total += 1
        else:
            disabled_total += 1

    insert_audit(channel, "ok", proxy_keys_disabled=disabled_total)
    print(f"Done. Disabled: {disabled_total}")
    if proxy_failed:
        sys.exit(2)

if __name__ == "__main__":
    main()
