# -*- coding: utf-8 -*-
"""用用户级凭证(kyzh2022)全量盘点 Drive 权限：
电子表格 + Colab notebook 每个文件的共享账号 → 扁平 ledger CSV + 汇总。

离职账号标记列表从 Google Sheet 台账读（不在脚本里硬编码邮箱 PII）。
"""
from __future__ import annotations

import csv
from collections import defaultdict

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from tongtool_order_cost.tongtool_order_cost.gsheets import client
from sheet_ledger import removed_accounts

TOKEN_FILE = r"D:\Work\赛狐\Cursor\secrets\gsheets-user-oauth.json"
OUT_CSV = "drive_permission_ledger.csv"
COLAB_LEDGER_CSV = "colab_permission_ledger.csv"

SA_SUFFIX = "iam.gserviceaccount.com"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
COLAB_MIME = "application/vnd.google.colaboratory"


def listfiles(token: str, q: str) -> list[dict]:
    out: list[dict] = []
    page = None
    while True:
        params = {
            "q": q,
            "fields": "nextPageToken,files(id,name,mimeType,owners(emailAddress),permissions(id,emailAddress,role,type))",
            "pageSize": 1000,
            "supportsAllDrives": True,
        }
        if page:
            params["pageToken"] = page
        r = requests.get(
            "https://www.googleapis.com/drive/v3/files", params=params,
            headers={"Authorization": f"Bearer {token}"}, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("files", []))
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def main() -> None:
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    if creds.expired or not creds.token:
        creds.refresh(Request())
    token = creds.token

    removed = removed_accounts(client())  # 离职账号列表，从台账读

    files = listfiles(token, "mimeType='application/vnd.google-apps.spreadsheet'") + listfiles(
        token, "mimeType='application/vnd.google.colaboratory'"
    )
    print(f"全量文件: {len(files)}")

    ledger_rows = []
    colab_rows = []
    acct_files: dict[str, set[str]] = defaultdict(set)  # acct -> set of file ids
    removed_left: dict[str, int] = defaultdict(int)     # acct -> count still present

    for f in files:
        fid, name, mime = f["id"], f["name"], f["mimeType"]
        owner = (f.get("owners") or [{}])[0].get("emailAddress", "")
        url = f"https://docs.google.com/spreadsheets/d/{fid}/" if mime == SHEET_MIME else f"https://colab.research.google.com/drive/{fid}"
        for p in f.get("permissions", []):
            email = p.get("emailAddress", "")
            if not email or SA_SUFFIX in email:
                continue
            role = p.get("role", "")
            acct_files[email].add(fid)
            if email in removed:
                removed_left[email] += 1
            ledger_rows.append({
                "file_name": name, "file_id": fid, "mime": mime, "owner": owner, "url": url,
                "account": email, "role": role,
            })
            if mime == COLAB_MIME and email != owner:
                colab_rows.append({"notebook": name, "notebook_id": fid, "owner": owner, "account": email, "role": role})

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file_name", "file_id", "mime", "owner", "url", "account", "role"])
        w.writeheader()
        w.writerows(ledger_rows)
    with open(COLAB_LEDGER_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["notebook", "notebook_id", "owner", "account", "role"])
        w.writeheader()
        w.writerows(colab_rows)

    print("\n===== 账号 → 文件数（按文件数降序） =====")
    for acct, ids in sorted(acct_files.items(), key=lambda x: -len(x[1])):
        mark = " [已离职]" if acct in removed else ""
        print(f"{acct:38s} {len(ids):4d}  {mark}")

    print("\n===== 离职账号仍残留的文件数（全量 Drive） =====")
    non_zero = {a: n for a, n in removed_left.items() if n}
    if non_zero:
        for a, n in sorted(non_zero.items(), key=lambda x: -x[1]):
            print(f"  {a}: {n} 个文件")
    else:
        print("  (无残留，全部已清)")

    print(f"\n明细已保存: {OUT_CSV}\nColab 明细: {COLAB_LEDGER_CSV}")


if __name__ == "__main__":
    main()
