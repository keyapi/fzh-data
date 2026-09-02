# -*- coding: utf-8 -*-
"""用户级 OAuth 一次性授权：在浏览器完成本人的 Google 账号授权后，
把 refresh token 存到 D:\\Work\\赛狐\\Cursor\\secrets\\gsheets-user-oauth.json。
用法: uv run python auth_gsheets_user.py <client_secret.json路径>
"""
from __future__ import annotations

import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRET = sys.argv[1]
OUT = r"D:\Work\赛狐\Cursor\secrets\gsheets-user-oauth.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
print(">>> 浏览器已打开，请用你自己的 Google 账号登录并点「允许 Allow」。等待授权...", flush=True)
creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)

data = {
    "type": "authorized_user",
    "client_id": creds.client_id,
    "client_secret": creds.client_secret,
    "refresh_token": creds.refresh_token,
    "scopes": list(creds.scopes),
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
print(f"SAVED token -> {OUT}", flush=True)
