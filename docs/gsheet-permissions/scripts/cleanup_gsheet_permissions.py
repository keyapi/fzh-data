# -*- coding: utf-8 -*-
"""清理 Google 表权限：
1) 给所有含「前财务负责人」的表补「现任财务负责人」的 writer 权限（不发邮件）
2) 从所有表移除已确认离职账号的权限

账号从 Google Sheet 台账读（按「识别/备注」列找现/前任财务负责人，按状态找离职）。
默认 dry-run 只打印计划；加 --apply 才真正执行。
"""
from __future__ import annotations

import sys
import time

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from tongtool_order_cost.tongtool_order_cost.gsheets import client, service_account_path
from sheet_ledger import load_accounts, removed_accounts

BASE = "https://www.googleapis.com/drive/v3"
SA_SUFFIX = "iam.gserviceaccount.com"


def _account_by_note(accts: list[dict], keyword: str) -> str:
    """从台账「识别/备注」列找含关键词的账号邮箱。"""
    for a in accts:
        if keyword in a["note"]:
            return a["account"]
    raise RuntimeError(f"台账「账号主清单」中找不到备注含「{keyword}」的账号，请先检查台账")


def api(token: str, method: str, path: str, **kwargs) -> dict:
    url = f"{BASE}{path}"
    for attempt in range(4):
        r = requests.request(method, url, headers={"Authorization": f"Bearer {token}"}, timeout=60, **kwargs)
        if r.status_code in (429, 500, 503) and attempt < 3:
            time.sleep(2 * (attempt + 1) + 1)
            continue
        return r
    raise RuntimeError(f"{method} {path} failed after retries")


def fetch_all(token: str) -> list[dict]:
    files: list[dict] = []
    page = None
    while True:
        params = {
            "q": "mimeType='application/vnd.google-apps.spreadsheet'",
            "fields": "nextPageToken,files(id,name,owners(emailAddress),permissions(id,emailAddress,role,type))",
            "pageSize": 1000,
            "supportsAllDrives": True,
        }
        if page:
            params["pageToken"] = page
        data = api(token, "GET", "/files", params=params).json()
        files.extend(data.get("files", []))
        page = data.get("nextPageToken")
        if not page:
            break
    return files


def main() -> None:
    apply = "--apply" in sys.argv
    creds = service_account.Credentials.from_service_account_file(
        service_account_path(), scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(Request())
    token = creds.token

    # 从台账读账号（处理方式/备注列决定现/前任财务、离职名单）
    gc = client()
    accts = load_accounts(gc)
    ADD_EMAIL = _account_by_note(accts, "现任财务负责人")    # zj
    INHERIT_FROM = _account_by_note(accts, "前财务负责人")    # zhongyu
    REMOVE_ACCOUNTS = removed_accounts(gc)

    files = fetch_all(token)
    print(f"扫描到 {len(files)} 张表")

    # 建 file_id -> {email: perm_id}
    file_perms: dict[str, dict[str, dict]] = {}
    for f in files:
        by_email = {}
        for p in f.get("permissions", []):
            email = p.get("emailAddress", "")
            if email and SA_SUFFIX not in email:
                by_email[email] = p
        file_perms[f["id"]] = by_email

    # Phase 1: 补 zj
    add_plan = []
    for f in files:
        pid, name = f["id"], f["name"]
        em = file_perms[pid]
        if INHERIT_FROM in em and ADD_EMAIL not in em:
            add_plan.append((pid, name))
    print(f"\n[Phase1] 给含 {INHERIT_FROM} 的表补 {ADD_EMAIL}(writer, 不发邮件): {len(add_plan)} 张")

    # Phase 2: 移除离职账号
    remove_plan: list[tuple[str, str, str, str]] = []  # (file_id, name, email, perm_id)
    for f in files:
        pid, name = f["id"], f["name"]
        em = file_perms[pid]
        for acct in REMOVE_ACCOUNTS:
            if acct in em:
                # 绝不删 owner / zj / 服务账号
                if em[acct].get("role") == "owner":
                    print(f"  !! 跳过 owner 账号 {acct} on {name}")
                    continue
                remove_plan.append((pid, name, acct, em[acct]["id"]))
    print(f"[Phase2] 移除离职账号权限: {len(remove_plan)} 处")
    from collections import Counter
    for acct, n in Counter(x[2] for x in remove_plan).items():
        print(f"    {acct}: {n}")

    if not apply:
        print("\n>>> dry-run 完成，未做任何修改。加 --apply 真正执行。")
        return

    # 执行 Phase 1
    ok_add = 0
    for pid, name in add_plan:
        body = {"role": "writer", "type": "user", "emailAddress": ADD_EMAIL}
        r = api(token, "POST", f"/files/{pid}/permissions", json=body,
                params={"supportsAllDrives": "true", "sendNotificationEmail": "false"})
        if r.status_code in (200, 201):
            ok_add += 1
            print(f"  [add] {name} -> {ADD_EMAIL}")
        else:
            print(f"  [add-FAIL] {name}: HTTP {r.status_code} {r.text[:120]}")
        time.sleep(0.1)

    # 执行 Phase 2
    ok_del = 0
    for pid, name, acct, perm_id in remove_plan:
        r = api(token, "DELETE", f"/files/{pid}/permissions/{perm_id}",
                params={"supportsAllDrives": "true"})
        if r.status_code in (200, 204):
            ok_del += 1
        elif r.status_code == 404:
            print(f"  [del-skip] {name}: {acct} 权限已不存在")
            ok_del += 1
        else:
            print(f"  [del-FAIL] {name} / {acct}: HTTP {r.status_code} {r.text[:120]}")
        time.sleep(0.1)

    print(f"\n完成: 补权 {ok_add}/{len(add_plan)}，移除 {ok_del}/{len(remove_plan)}")


if __name__ == "__main__":
    main()
