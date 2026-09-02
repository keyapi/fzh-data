# -*- coding: utf-8 -*-
"""综合收集：
1) 全部 Colab notebook + 是否已有SA + 是否已有同事writer
2) 8 张公开链接表(anyone)的当前状态
3) 4 个离职属主文件的当前状态
"""
from __future__ import annotations

import csv
import requests
from collections import defaultdict
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

TOKEN_FILE = r"D:\Work\赛狐\Cursor\secrets\gsheets-user-oauth.json"
SA_EMAIL = "colab-gsheets@gsheets-351101.iam.gserviceaccount.com"
BASE = "https://www.googleapis.com/drive/v3"


def listfiles(token, mime, fields):
    out = []
    page = None
    while True:
        params = {"q": f"mimeType='{mime}'", "fields": fields, "pageSize": 1000, "supportsAllDrives": True}
        if page:
            params["pageToken"] = page
        d = requests.get(f"{BASE}/files", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=60).json()
        out.extend(d.get("files", []))
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def grep_colab(name, files):
    for f in files:
        if f["name"].lower() == name.lower():
            return f
    return None


def main():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    if creds.expired or not creds.token:
        creds.refresh(Request())
    token = creds.token

    # 全部 Colab
    colabs = listfiles(token, "application/vnd.google.colaboratory",
                       "nextPageToken,files(id,name,owners(emailAddress),permissions(id,emailAddress,role,type))")
    print(f"===== 全部 Colab: {len(colabs)} 个 =====\n")
    print("--- 无 SA 且无同事 writer（纯个人/测试, 未加 SA 的这批）---")
    no_sa_no_col = []
    for f in colabs:
        perms = f.get("permissions", [])
        has_sa = any(p.get("emailAddress") == SA_EMAIL for p in perms)
        col_emails = [p.get("emailAddress") for p in perms
                      if p.get("emailAddress") and p.get("emailAddress") != f.get("owners", [{}])[0].get("emailAddress") and "gserviceaccount.com" not in p.get("emailAddress")]
        if not has_sa and not col_emails:
            no_sa_no_col.append(f)
    # 按名字分组统计(有些同名)
    byname = defaultdict(list)
    for f in no_sa_no_col:
        byname[f["name"]].append(f["id"])
    for name in sorted(byname):
        print(f"  {name}")
    print(f"\n无SA且无同事的: {len(no_sa_no_col)} 个")

    print("\n--- 无 SA 但有同事权限（可能遗漏的）---")
    for f in colabs:
        perms = f.get("permissions", [])
        has_sa = any(p.get("emailAddress") == SA_EMAIL for p in perms)
        col_emails = [p.get("emailAddress") for p in perms
                      if p.get("emailAddress") and p.get("emailAddress") != f.get("owners", [{}])[0].get("emailAddress") and "gserviceaccount.com" not in p.get("emailAddress")]
        if not has_sa and col_emails:
            print(f"  {f['name']}  <- 同事: {col_emails}")

    # 8 张公开链接表(anyone)
    print("\n===== 公开链接表(anyone) =====")
    sheets = listfiles(token, "application/vnd.google-apps.spreadsheet",
                       "nextPageToken,files(id,name,owners(emailAddress),permissions(id,emailAddress,role,type,domain))")
    for f in sheets:
        anyone = [p for p in f.get("permissions", []) if p.get("type") == "anyone"]
        if anyone:
            for p in anyone:
                print(f"  [{p.get('role')}] {f['name']}\n      id={f['id']}\n      url=https://docs.google.com/spreadsheets/d/{f['id']}/")


if __name__ == "__main__":
    main()
