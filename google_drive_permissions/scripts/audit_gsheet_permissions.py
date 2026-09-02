# -*- coding: utf-8 -*-
"""只读盘点：扫描服务账号可访问的全部 Google 表，列出每个账号在哪些表有权限。

用 Drive API files.list 一次性返回全部表的权限（免逐表调用），快很多。
重点关注的账号列表从 Google Sheet 台账读（不在脚本里硬编码邮箱 PII）。
"""
from __future__ import annotations

import csv
from collections import defaultdict

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from tongtool_order_cost.tongtool_order_cost.gsheets import client, service_account_path
from sheet_ledger import kept_accounts, load_accounts

SA_SUFFIX = "iam.gserviceaccount.com"
OUT_CSV = "gsheet_permission_audit.csv"


def fetch_all_files(token: str) -> list[dict]:
    files: list[dict] = []
    url = "https://www.googleapis.com/drive/v3/files"
    page = None
    while True:
        params = {
            "q": "mimeType='application/vnd.google-apps.spreadsheet'",
            "fields": "nextPageToken,files(id,name,owners(emailAddress),permissions(emailAddress,role,type))",
            "pageSize": 1000,
            "supportsAllDrives": True,
        }
        if page:
            params["pageToken"] = page
        r = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        r.raise_for_status()
        data = r.json()
        files.extend(data.get("files", []))
        page = data.get("nextPageToken")
        if not page:
            break
    return files


def main() -> None:
    creds = service_account.Credentials.from_service_account_file(
        service_account_path(), scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(Request())
    files = fetch_all_files(creds.token)
    print(f"服务账号可访问的电子表格总数: {len(files)}")

    # 重点关注的账号：在职保留 + 离职（从台账读，处理方式列决定）
    gc = client()
    watch = kept_accounts(gc) + [a["account"] for a in load_accounts(gc) if a["status"] == "离职"]

    rows = []
    account_counts: dict[str, dict] = defaultdict(lambda: {"sheets": 0, "roles": set()})

    for f in files:
        name, sid = f.get("name", ""), f.get("id", "")
        owner = (f.get("owners") or [{}])[0].get("emailAddress", "")
        present = {}
        for p in f.get("permissions", []):
            email = p.get("emailAddress", "")
            if not email or SA_SUFFIX in email:
                continue
            role = p.get("role", "")
            present[email] = role
            account_counts[email]["sheets"] += 1
            account_counts[email]["roles"].add(role)

        row = {"name": name, "id": sid, "url": f"https://docs.google.com/spreadsheets/d/{sid}/", "owner": owner}
        for a in watch:
            row[a] = present.get(a, "")
        others = [f"{e}({r})" for e, r in present.items() if e not in watch]
        row["other_accounts"] = "; ".join(sorted(others))
        rows.append(row)

    rows.sort(key=lambda r: (r["owner"], r["name"]))
    fieldnames = ["name", "id", "url", "owner"] + watch + ["other_accounts"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print("\n===== 每个账号出现在多少张表（含角色）=====")
    for email in sorted(account_counts, key=lambda e: -account_counts[e]["sheets"]):
        c = account_counts[email]
        print(f"{email:38s} {c['sheets']:3d} 张表  角色: {sorted(c['roles'])}")

    def sheets_of(email: str) -> list[str]:
        return [r["name"] for r in rows if r.get(email)]

    for watch_email in [a for a in watch if a]:
        names = sheets_of(watch_email)
        if names:
            print(f"\n含 {watch_email} 的表 ({len(names)}):")
            for n in names:
                print(f"  - {n}")

    print(f"\n调查表已保存: {OUT_CSV}")


if __name__ == "__main__":
    main()
