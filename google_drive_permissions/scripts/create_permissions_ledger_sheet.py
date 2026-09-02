# -*- coding: utf-8 -*-
"""扫描 Drive 现状并刷新台账「现状明细」worksheet（电子表格 + Colab 分类）。

原则：数据以台账为准；脚本无 PII 硬编码。单凭证（用户 OAuth，既能扫 Drive 又能读写台账）。
- 从 Drive 扫描所有文件被共享的账号 → 刷新「现状明细」（类别/名称/ID/属主/链接/账号/角色）；
- 「账号主清单」不动（保留人工填的 状态/备注/处理方式），只由 build_accounts_master.py 负责对账。
- 幂等：清空「现状明细」后重写为当前 Drive 现状快照。

用法: uv run python create_permissions_ledger_sheet.py
  默认 dry-run 只打印行数；加 --apply 才真正清空重写「现状明细」。
"""
from __future__ import annotations

import sys

import gspread
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

TOKEN_FILE = r"D:\Work\赛狐\Cursor\secrets\gsheets-user-oauth.json"
SHEET_ID = "1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0"
SA_EMAIL = "colab-gsheets@gsheets-351101.iam.gserviceaccount.com"
SA_SUFFIX = "iam.gserviceaccount.com"
SHELL_SA = "service@automa2.iam.gserviceaccount.com"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
COLAB_MIME = "application/vnd.google.colaboratory"
LEDGER_WS = "现状明细"
LEDGER_HEADER = ["类别", "文件名称", "文件ID", "属主", "链接", "账户", "角色"]


def list_files(token: str, mime: str) -> list[dict]:
    out = []
    page = None
    while True:
        params = {
            "q": f"mimeType='{mime}'",
            "fields": "nextPageToken,files(id,name,mimeType,owners(emailAddress),permissions(emailAddress,role,type))",
            "pageSize": 1000,
            "supportsAllDrives": True,
        }
        if page:
            params["pageToken"] = page
        d = requests.get(
            "https://www.googleapis.com/drive/v3/files", params=params,
            headers={"Authorization": f"Bearer {token}"}, timeout=60,
        ).json()
        out.extend(d.get("files", []))
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def main() -> None:
    apply = "--apply" in sys.argv
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    if creds.expired or not creds.token:
        creds.refresh(Request())
    token = creds.token
    gc = gspread.authorize(creds)

    files = list_files(token, SHEET_MIME) + list_files(token, COLAB_MIME)
    print(f"Drive 文件总数: {len(files)}")

    rows = [LEDGER_HEADER]
    for f in files:
        fid, name, mime = f["id"], f["name"], f["mimeType"]
        owner = (f.get("owners") or [{}])[0].get("emailAddress", "")
        url = f"https://docs.google.com/spreadsheets/d/{fid}/" if mime == SHEET_MIME else f"https://colab.research.google.com/drive/{fid}"
        cat = "电子表格" if mime == SHEET_MIME else "Colab"
        for p in f.get("permissions", []):
            email = p.get("emailAddress", "")
            if not email or SA_SUFFIX in email or email in (SA_EMAIL, SHELL_SA):
                continue
            rows.append([cat, name, fid, owner, url, email, p.get("role", "")])

    print(f"[dry-run] 将写入「现状明细」{len(rows)-1} 行（类别: 电子表格/Colab）")
    if not apply:
        from collections import Counter
        print("  ", Counter(r[0] for r in rows[1:]))
        print("\n>>> dry-run，未修改台账。加 --apply 执行。")
        return

    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(LEDGER_WS)
    ws.clear()
    ws.update("A1", rows)
    print(f"已刷新「现状明细」: {len(rows)-1} 行")

    # 确保 SA 仍在台账（作为 editor 以便后续脚本读）
    try:
        sh.share(SA_EMAIL, perm_type="user", role="writer", notify=False)
    except Exception as e:
        print("share SA:", e)

    print(f"台账链接: {sh.url}")


if __name__ == "__main__":
    main()
