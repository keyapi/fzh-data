# -*- coding: utf-8 -*-
"""清理 Google 表权限：
1) 给所有含「前财务负责人」的表补「现任财务负责人」的 writer 权限（不发邮件）
2) 从所有表移除已确认离职账号的权限

账号从 Google Sheet 台账读（按「识别/备注」列找现/前任财务负责人，按处理方式找离职）。
默认 dry-run 只打印计划；加 --apply 才真正执行。

范围：默认用服务账号，只处理 SA 能看到的文件。不是全盘 Drive。
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
    hits = [a["account"] for a in accts if keyword in a["note"]]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise RuntimeError(f"台账「账号主清单」中找不到备注含「{keyword}」的账号，请先检查台账")
    raise RuntimeError(f"台账备注含「{keyword}」的账号不唯一: {hits}")


def should_skip_delete(email: str, perm: dict, *, add_email: str) -> bool:
    """不删 owner、现任财务、服务账号。"""
    if not email or SA_SUFFIX in email:
        return True
    if email == add_email:
        return True
    return perm.get("role") == "owner"


def phase2_may_run(*, ok_add: int, add_plan_len: int) -> bool:
    return ok_add == add_plan_len


def api(token: str, method: str, path: str, *, raise_error: bool = False, **kwargs):
    url = f"{BASE}{path}"
    for attempt in range(4):
        r = requests.request(method, url, headers={"Authorization": f"Bearer {token}"}, timeout=60, **kwargs)
        if r.status_code in (429, 500, 503) and attempt < 3:
            time.sleep(2 * (attempt + 1) + 1)
            continue
        if raise_error:
            r.raise_for_status()
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
        data = api(token, "GET", "/files", params=params, raise_error=True).json()
        files.extend(data.get("files", []))
        page = data.get("nextPageToken")
        if not page:
            break
    return files


def main() -> None:
    apply = "--apply" in sys.argv
    print("范围: 服务账号可见的电子表格（不是全盘 Drive）。全盘清理请用用户 OAuth 审计脚本另做。")
    creds = service_account.Credentials.from_service_account_file(
        service_account_path(), scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(Request())
    token = creds.token

    gc = client()
    accts = load_accounts(gc)
    add_email = _account_by_note(accts, "现任财务负责人")
    inherit_from = _account_by_note(accts, "前财务负责人")
    if add_email == inherit_from:
        raise SystemExit("现任/前财务负责人解析成同一账号，请先改台账备注")
    remove_accounts = [a for a in removed_accounts(gc) if a != add_email]

    files = fetch_all(token)
    print(f"扫描到 {len(files)} 张表（SA 可见）")
    if apply and not files:
        raise SystemExit("refuse --apply: Drive list 为空，可能是凭证/API 失败")

    file_perms: dict[str, dict[str, dict]] = {}
    for f in files:
        by_email = {}
        for p in f.get("permissions", []):
            email = p.get("emailAddress", "")
            if email and SA_SUFFIX not in email:
                by_email[email] = p
        file_perms[f["id"]] = by_email

    add_plan = []
    for f in files:
        pid, name = f["id"], f["name"]
        em = file_perms[pid]
        if inherit_from in em and add_email not in em:
            add_plan.append((pid, name))
    print(f"\n[Phase1] 给含前任财务的表补现任财务(writer, 不发邮件): {len(add_plan)} 张")

    remove_plan: list[tuple[str, str, str, str]] = []
    for f in files:
        pid, name = f["id"], f["name"]
        em = file_perms[pid]
        for acct in remove_accounts:
            if acct not in em:
                continue
            if should_skip_delete(acct, em[acct], add_email=add_email):
                print(f"  !! 跳过 {acct} on {name} (owner/现任财务/SA)")
                continue
            remove_plan.append((pid, name, acct, em[acct]["id"]))
    print(f"[Phase2] 移除离职账号权限: {len(remove_plan)} 处")
    from collections import Counter
    for acct, n in Counter(x[2] for x in remove_plan).items():
        print(f"    {acct}: {n}")

    if not apply:
        print("\n>>> dry-run 完成，未做任何修改。加 --apply 真正执行。")
        return

    ok_add = 0
    for pid, name in add_plan:
        body = {"role": "writer", "type": "user", "emailAddress": add_email}
        r = api(token, "POST", f"/files/{pid}/permissions", json=body,
                params={"supportsAllDrives": "true", "sendNotificationEmail": "false"})
        if r.status_code in (200, 201):
            ok_add += 1
            print(f"  [add] {name} -> {add_email}")
        else:
            print(f"  [add-FAIL] {name}: HTTP {r.status_code} {r.text[:120]}")
        time.sleep(0.1)

    if not phase2_may_run(ok_add=ok_add, add_plan_len=len(add_plan)):
        raise SystemExit(
            f"Phase1 未全部成功 ({ok_add}/{len(add_plan)})，已中止 Phase2 删除，避免前任财务权限被去掉后现任未补上"
        )

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

    if ok_add < len(add_plan) or ok_del < len(remove_plan):
        raise SystemExit(f"未完全成功: 补权 {ok_add}/{len(add_plan)}，移除 {ok_del}/{len(remove_plan)}")
    print(f"\n完成: 补权 {ok_add}/{len(add_plan)}，移除 {ok_del}/{len(remove_plan)}")


if __name__ == "__main__":
    main()
