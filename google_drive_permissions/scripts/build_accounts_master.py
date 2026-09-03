# -*- coding: utf-8 -*-
"""对账式刷新「账号主清单」：Drive 现状 vs 台账已登记。

原则：数据以 Google Sheet 台账为准；脚本不硬编码任何邮箱（PII 治理）。
- 从 Drive 现状扫描出所有非自己/非SA的有权限账号（用户 OAuth，能看全）；
- 与台账「账号主清单」已登记账号对账：
    * 台账没有 → 追加一行 状态=待确认，只抄 Drive 里的邮箱 + 当前文件数（不写死）；
    * 台账有但 Drive 已无 → 不动（不自动删，保留人工填的状态/备注）；
    * 已有账号 → 只刷新「当前文件数」，绝不覆盖人工填的 状态/识别备注/处理方式。
- 首版"在职/离职 + 姓名备注"由人工/Agent 直接在台账填，脚本只做对账与提示。

用法: uv run python build_accounts_master.py [--apply]
  不加 --apply 只打印对账结果（模拟）；加 --apply 才写回台账。
"""
from __future__ import annotations

import sys
from collections import Counter

import gspread
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from paths import user_oauth_path

TOKEN_FILE = str(user_oauth_path())
SHEET_ID = "1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0"
MASTER_WS = "账号主清单"
SA_SUFFIX = "iam.gserviceaccount.com"
MASTER_HEADER = ["状态", "账号", "识别/备注", "处理方式", "当前文件数"]


def current_user(token: str) -> str:
    """取当前 OAuth 用户的邮箱（用于排除"自己"，不硬编码）。"""
    d = requests.get(
        "https://www.googleapis.com/drive/v3/about",
        params={"fields": "user(emailAddress)"},
        headers={"Authorization": f"Bearer {token}"}, timeout=60,
    ).json()
    return (d.get("user") or {}).get("emailAddress", "")


def list_sharer_accounts(token: str, self_acct: str) -> Counter:
    """扫描 Drive 里所有被共享账号（spreadsheet + Colab），返回 {账号: 文件数}。"""
    counts: Counter = Counter()
    for mime in ("application/vnd.google-apps.spreadsheet", "application/vnd.google.colaboratory"):
        page = None
        while True:
            params = {
                "q": f"mimeType='{mime}'",
                "fields": "nextPageToken,files(permissions(emailAddress,role,type))",
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
            for f in d.get("files", []):
                for p in f.get("permissions", []):
                    email = p.get("emailAddress", "")
                    if not email or SA_SUFFIX in email or email == self_acct:
                        continue
                    counts[email] += 1
            page = d.get("nextPageToken")
            if not page:
                break
    return counts


def main() -> None:
    apply = "--apply" in sys.argv
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=["https://www.googleapis.com/auth/drive"])
    if creds.expired or not creds.token:
        creds.refresh(Request())
    token = creds.token
    gc = gspread.authorize(creds)
    self_acct = current_user(token)
    print(f"当前用户(已排除): {self_acct}")

    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(MASTER_WS)
    existing = ws.get_all_values()[1:]  # 去掉表头

    # 台账现有账号 -> 行（保留人工填的内容）
    seen = {}
    for row in existing:
        if len(row) >= 2 and row[1]:
            seen[row[1]] = row

    # Drive 现状
    drive_counts = list_sharer_accounts(token, self_acct)
    print(f"Drive 现状有权限的账号: {len(drive_counts)}")
    if apply and not drive_counts:
        raise SystemExit("refuse --apply: Drive 扫描为空，避免把台账文件数刷成 0")

    to_add = []      # 台账没有的
    to_update = []   # 台账有的，刷新文件数
    in_drive_but_no_tai = []
    for acct, n in sorted(drive_counts.items(), key=lambda x: -x[1]):
        if acct not in seen:
            to_add.append((acct, n))
        else:
            cur = int(seen[acct][4]) if len(seen[acct]) > 4 and seen[acct][4].isdigit() else 0
            if cur != n:
                to_update.append((acct, cur, n))

    # 台账有但 Drive 已经没了权限的
    gone = [acct for acct in seen if acct not in drive_counts]

    print(f"[对账] 台账已有 {len(seen)} 个账号")
    print(f"[新增] 台账没有、Drive 有权限 -> 建议标「待确认」: {len(to_add)} 个")
    for acct, n in to_add:
        print(f"    {n:3d}  {acct}")
    print(f"[刷新] 文件数有变化: {len(to_update)} 个")
    for acct, old, new in to_update:
        print(f"    {old}->{new}  {acct}")
    print(f"[保留] 台账有但 Drive 已无权限(不自动删，人工确认): {len(gone)} 个")
    for acct in gone:
        print(f"    {acct}")

    if not apply:
        print("\n>>> dry-run，未修改台账。加 --apply 写回。")
        return

    # 写回：追加新增行；刷新文件数；绝不覆盖人工填的 状态/备注/处理方式
    rows = [MASTER_HEADER]
    for acct, row in seen.items():
        r = list(row) + [""] * (len(MASTER_HEADER) - len(row))
        drive_n = drive_counts.get(acct, 0)
        r[4] = str(drive_n)  # 只刷当前文件数
        rows.append(r)
    for acct, n in to_add:
        rows.append(["待确认", acct, "", "待定", str(n)])

    # 排序：自己/SA 置顶，然后在职 > 待确认 > 离职
    order = {"自己": 0, "SA": 1, "在职": 2, "待确认": 3, "离职": 4}
    rows[1:] = sorted(rows[1:], key=lambda r: (order.get(r[0], 9), r[1]))
    ws.update("A1", rows)
    print(f"\n已写回台账，共 {len(rows)-1} 条")


if __name__ == "__main__":
    main()
