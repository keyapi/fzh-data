#!/usr/bin/env python3
"""
Periodic offboarding check — verify DingTalk employee status via App Token.

Runs daily (cron). Uses app-level access token (client_credentials) to query
DingTalk API for each OAuth-linked user's active status. Disables new-api
accounts for employees no longer in the organization.

Requires: qyapi_get_member permission

Usage:
    python3 offboarding-check.py
"""

import json
import subprocess
import sys
import urllib.request

APP_KEY = "dingb0z8d4yzrl3mjqkr"
APP_SECRET = "QWD8XTsjEDs-KVaXev1OoM13Y71ILCzVQqaKgWeyLJbl_cUedu4S9kolIPkSrbK7"

MYSQL_CMD = [
    "docker", "exec", "-i", "new-api-mysql",
    "mysql", "-uroot", "-pnew-api-root-pwd",
    "new_api", "-N", "-B",
]


def run_mysql(query: str) -> str:
    proc = subprocess.run(
        MYSQL_CMD + ["-e", query],
        capture_output=True, text=True, timeout=30,
    )
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
    result = api_post("https://api.dingtalk.com/v1.0/oauth2/accessToken", {
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "grantType": "client_credentials",
    })
    token = result.get("accessToken")
    if not token:
        raise RuntimeError(f"Failed to get app token: {result}")
    return token


def check_user_active(union_id: str, app_token: str) -> bool | None:
    """
    Check if a DingTalk user is still active in the org.
    Returns True if active, False if not, None if user not found.
    """
    # Step 1: unionId → userId
    result = api_post(
        f"https://oapi.dingtalk.com/topapi/user/getbyunionid?access_token={app_token}",
        {"unionid": union_id},
    )
    if result.get("errcode") != 0:
        print(f"  [WARN] getbyunionid failed for {union_id[:16]}...: {result.get('errmsg')}")
        return None

    userid = result["result"]["userid"]

    # Step 2: userId → user detail (includes active status)
    result = api_post(
        f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={app_token}",
        {"userid": userid},
    )
    if result.get("errcode") != 0:
        print(f"  [WARN] user/get failed for {userid}: {result.get('errmsg')}")
        return None

    return result["result"].get("active", False)


def main():
    # Get all DingTalk OAuth users from new-api
    output = run_mysql("""
        SELECT u.id, u.username, u.status, b.provider_user_id
        FROM users u
        JOIN user_oauth_bindings b ON u.id = b.user_id
        WHERE b.provider_id = 1 AND u.status = 1
    """)
    if not output:
        print("[OK] No active DingTalk OAuth users to check")
        return

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

    print(f"Checking {len(users)} DingTalk user(s)...")

    try:
        app_token = get_app_token()
    except Exception as e:
        print(f"[FATAL] Cannot get app token: {e}")
        sys.exit(1)

    disabled = 0
    for user in users:
        uid = user["id"]
        username = user["username"]
        union_id = user["union_id"]

        active = check_user_active(union_id, app_token)
        if active is None:
            print(f"  [SKIP] {username} — API lookup failed")
        elif active:
            print(f"  [OK] {username} — active")
        else:
            run_mysql(f"UPDATE users SET status = 2 WHERE id = {uid} AND status = 1")
            print(f"  [OFFBOARD] {username} (id={uid}) — departed, disabled")
            disabled += 1

    print(f"Done. Disabled: {disabled}")


if __name__ == "__main__":
    main()
