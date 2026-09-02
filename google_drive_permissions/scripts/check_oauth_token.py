# -*- coding: utf-8 -*-
"""检查用户级 OAuth 凭证(refresh token)当前可否刷新及过期风险。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

TOKEN_FILE = r"D:\Work\赛狐\Cursor\secrets\gsheets-user-oauth.json"


def main() -> None:
    with open(TOKEN_FILE, encoding="utf-8") as fh:
        raw = json.load(fh)
    print("credential 文件内容(隐藏 secret):")
    print("  type          :", raw.get("type"))
    print("  client_id     :", raw.get("client_id"))
    print("  scopes        :", raw.get("scopes"))
    print("  refresh_token :", ("(存在)" if raw.get("refresh_token") else "(缺失!)"))
    print("  文件修改时间   :", datetime.fromtimestamp(__import__("os").path.getmtime(TOKEN_FILE)).strftime("%Y-%m-%d %H:%M:%S"))

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    print("\n刷新前: token存在 =", bool(creds.token), "| 过期 =", creds.expired)

    if creds.expired or not creds.token:
        try:
            creds.refresh(Request())
            print("刷新后: 成功取得新 access token =", bool(creds.token))
            print("刷新后 expiry:", datetime.fromtimestamp(creds.expiry.timestamp()).isoformat() if creds.expiry else "?")
        except Exception as e:
            print("刷新失败:", type(e).__name__, e)
            return
    else:
        print("仍有效，无需刷新")

    # 用 token 拉一个轻量接口验证身份
    import requests
    r = requests.get(
        "https://www.googleapis.com/drive/v3/about",
        params={"fields": "user(emailAddress,displayName)"},
        headers={"Authorization": f"Bearer {creds.token}"}, timeout=30,
    )
    print("\nDrive about 接口:", r.status_code)
    if r.ok:
        print("  user:", r.json().get("user"))


if __name__ == "__main__":
    main()
