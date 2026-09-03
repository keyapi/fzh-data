# -*- coding: utf-8 -*-
"""扫描 Drive 现状并刷新台账「现状明细」worksheet（电子表格 + Colab 分类）。

原则：数据以台账为准；脚本无 PII 硬编码。单凭证（用户 OAuth，既能扫 Drive 又能读写台账）。
- 从 Drive 扫描所有文件被共享的账号 → 刷新「现状明细」（类别/名称/ID/属主/链接/账号/角色）；
- 「账号主清单」不动（保留人工填的 状态/备注/处理方式），只由 build_accounts_master.py 负责对账。
- 幂等：用当前 Drive 快照覆盖「现状明细」；扫描失败或结果异常时拒绝 --apply。

用法: uv run python create_permissions_ledger_sheet.py
  默认 dry-run 只打印行数；加 --apply 才写回「现状明细」。
"""
from __future__ import annotations

import sys

import gspread
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from paths import user_oauth_path

TOKEN_FILE = str(user_oauth_path())
SHEET_ID = "1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0"
SA_EMAIL = "colab-gsheets@gsheets-351101.iam.gserviceaccount.com"
SA_SUFFIX = "iam.gserviceaccount.com"
SHELL_SA = "service@automa2.iam.gserviceaccount.com"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
COLAB_MIME = "application/vnd.google.colaboratory"
LEDGER_WS = "现状明细"
LEDGER_HEADER = ["类别", "文件名称", "文件ID", "属主", "链接", "账户", "角色"]


def parse_drive_list_response(resp: requests.Response) -> list[dict]:
    resp.raise_for_status()
    return resp.json().get("files", [])


def apply_blocked_reason(*, file_count: int, new_row_count: int, existing_row_count: int | None) -> str | None:
    if file_count <= 0:
        return "Drive list returned 0 files"
    if existing_row_count and existing_row_count > 0 and new_row_count < max(1, int(existing_row_count * 0.2)):
        return f"new snapshot {new_row_count} rows << existing {existing_row_count}"
    return None


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
        r = requests.get(
            "https://www.googleapis.com/drive/v3/files", params=params,
            headers={"Authorization": f"Bearer {token}"}, timeout=60,
        )
        files = parse_drive_list_response(r)
        out.extend(files)
        page = r.json().get("nextPageToken")
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

    print(f"计划写入「现状明细」{len(rows)-1} 行（类别: 电子表格/Colab）")
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(LEDGER_WS)
    existing_n = len(ws.get_all_values())
    blocked = apply_blocked_reason(
        file_count=len(files), new_row_count=len(rows) - 1, existing_row_count=existing_n,
    )
    if blocked:
        raise SystemExit(f"refuse --apply: {blocked}")
    if not apply:
        from collections import Counter
        print("  ", Counter(r[0] for r in rows[1:]))
        print("\n>>> dry-run，未修改台账。加 --apply 执行。")
        return

    ws.update("A1", rows)
    if existing_n > len(rows):
        ws.resize(rows=len(rows))
    print(f"已刷新「现状明细」: {len(rows)-1} 行")

    try:
        sh.share(SA_EMAIL, perm_type="user", role="writer", notify=False)
    except Exception as e:
        raise SystemExit(f"share SA failed after ledger write: {e}") from e

    print(f"台账链接: {sh.url}")


if __name__ == "__main__":
    main()
