# -*- coding: utf-8 -*-
"""Build a change-only Channel Account plan from Sheet rows + EN dump."""
from __future__ import annotations

from channel_account_sync.names import SKIP_CREATE, parse_aliases, reject_amazon_euro, sheet_to_en_name
from channel_account_sync.owners import collapsed_segments, en_last_owner, month_columns, needed_for_existing


def sheet_records(header: list[str], rows: list[list]) -> tuple[list[dict], list[str]]:
    month_cols = month_columns(header)
    recs = []
    for i, vals in enumerate(rows[1:] if rows else [], start=2):
        rec = {header[j]: (vals[j] if j < len(vals) else "") for j in range(len(header))}
        rec["_sheet_row"] = i
        if not (rec.get("渠道账号") or "").strip():
            continue
        recs.append(rec)
    return recs, month_cols


def alias_gaps(rec: dict, en_acc: dict, en_name: str) -> list[str]:
    wanted = parse_aliases(en_name, rec.get("渠道账号别名") or "")
    sheet_name = rec["渠道账号"].strip()
    if sheet_name != en_name and sheet_name not in wanted:
        wanted.append(sheet_name)
    have = {(a.get("account_alias") or "").strip() for a in (en_acc.get("aliases") or [])}
    return [a for a in wanted if a not in have]


def build_plan(sheet: dict, en: dict) -> dict:
    recs, month_cols = sheet_records(sheet["header"], sheet.get("rows") or [])
    en_by = {a["name"]: a for a in en.get("accounts") or []}
    insert_existing = []
    new_accounts = []
    skip = []
    forbidden = []
    aliases = []
    for rec in recs:
        sheet_name = rec["渠道账号"].strip()
        channel = (rec.get("渠道") or "").strip()
        if sheet_name in SKIP_CREATE:
            skip.append({"sheet": sheet_name, "reason": "skip_create"})
            continue
        en_name = sheet_to_en_name(sheet_name)
        err = reject_amazon_euro(en_name, channel, en_name[-3:] if en_name.endswith("EUR") else en_name[-2:])
        if err:
            forbidden.append({"sheet": sheet_name, "en_name": en_name, "reason": err})
            continue
        segs = collapsed_segments(rec, month_cols)
        en_acc = en_by.get(en_name)
        if not en_acc:
            new_accounts.append(
                {
                    "sheet": sheet_name,
                    "en_name": en_name,
                    "channel": channel,
                    "group": rec.get("运营分组"),
                    "aliases": rec.get("渠道账号别名"),
                    "owners": segs,
                    "sheet_row": rec["_sheet_row"],
                }
            )
            continue
        missing = alias_gaps(rec, en_acc, en_name)
        if missing:
            aliases.append({"account": en_name, "add": missing})
        en_from, en_user = en_last_owner(en_acc)
        needed = needed_for_existing(segs, en_from, en_user)
        if needed:
            insert_existing.append(
                {
                    "account": en_name,
                    "group": rec.get("运营分组"),
                    "en_from": en_from,
                    "en_user": en_user,
                    "needed": needed,
                    "sheet_row": rec["_sheet_row"],
                }
            )
    return {
        "n_sheet": len(recs),
        "n_en": len(en_by),
        "n_existing_need_insert": len(insert_existing),
        "n_owner_rows_existing": sum(len(x["needed"]) for x in insert_existing),
        "n_new_accounts": len(new_accounts),
        "n_owner_rows_new": sum(len(x["owners"]) for x in new_accounts),
        "n_alias_gaps": len(aliases),
        "new_accounts": new_accounts,
        "insert_existing": insert_existing,
        "alias_gaps": aliases,
        "skip": skip,
        "forbidden": forbidden,
    }
