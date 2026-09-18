# -*- coding: utf-8 -*-
"""Read-only dump of Google Sheet 渠道账号 + EN Channel Account docs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from channel_account_sync.rest import get_all, get_doc, session

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "out"
SHEET_ID = "1nbMO-wf-Oj7HIuYlPOtrC7F8QtsEPDE80BmXo8G6O3Y"
TARGET_GID = 763421711


def fetch_sheet() -> dict:
    sys.path.insert(0, str(REPO_ROOT / "tongtool_order_cost"))
    from tongtool_order_cost.gsheets import client

    gc = client()
    sh = gc.open_by_key(SHEET_ID)
    worksheets = [{"title": ws.title, "id": ws.id} for ws in sh.worksheets()]
    target = None
    for ws in sh.worksheets():
        if ws.id == TARGET_GID:
            target = ws
            break
    if target is None:
        for ws in sh.worksheets():
            if "渠道账号" in ws.title and "20260521" in ws.title:
                target = ws
                break
    if target is None:
        raise SystemExit("SHEET_TAB_NOT_FOUND")
    rows = target.get_all_values()
    return {
        "spreadsheet_title": sh.title,
        "spreadsheet_id": SHEET_ID,
        "worksheets": worksheets,
        "target_title": target.title,
        "target_gid": target.id,
        "header": rows[0] if rows else [],
        "n_rows": len(rows),
        "rows": rows,
    }


def fetch_en() -> dict:
    s, url = session()
    names = [r["name"] for r in get_all(s, url, "Channel Account", ["name"])]
    accounts = []
    errors = []
    for name in names:
        r = get_doc(s, url, "Channel Account", name)
        if r.status_code != 200:
            errors.append({"name": name, "status": r.status_code, "body": r.text[:400]})
            continue
        doc = r.json()["data"]
        accounts.append(
            {
                "name": doc.get("name"),
                "channel": doc.get("channel"),
                "account_code": doc.get("account_code"),
                "allow_empty_account_code": doc.get("allow_empty_account_code"),
                "channel_region": doc.get("channel_region"),
                "status": doc.get("status"),
                "aliases": [
                    {"account_alias": a.get("account_alias"), "idx": a.get("idx")}
                    for a in (doc.get("channel_account_alias") or [])
                ],
                "owners": [
                    {
                        "user": o.get("user"),
                        "from_date": o.get("from_date"),
                        "to_date": o.get("to_date"),
                        "is_active": o.get("is_active"),
                        "role_in_account": o.get("role_in_account"),
                        "branch": o.get("branch"),
                    }
                    for o in (doc.get("owners") or [])
                ],
            }
        )
    channels = get_all(
        s,
        url,
        "Sales Channel",
        ["name", "channel_name", "channel_code", "supported_regions", "is_active", "region_type"],
    )
    return {
        "url": url,
        "n_accounts": len(accounts),
        "n_channels": len(channels),
        "errors": errors,
        "accounts": accounts,
        "channels": channels,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-only", action="store_true")
    parser.add_argument("--en-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.en_only:
        sheet = fetch_sheet()
        (OUT / "channel_account_gsheet.json").write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("sheet", sheet["spreadsheet_title"], sheet["target_title"], "rows", sheet["n_rows"])
    if not args.sheet_only:
        en = fetch_en()
        (OUT / "channel_account_en.json").write_text(
            json.dumps(en, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("en accounts", en["n_accounts"], "channels", en["n_channels"], "errors", len(en["errors"]))


if __name__ == "__main__":
    main()
