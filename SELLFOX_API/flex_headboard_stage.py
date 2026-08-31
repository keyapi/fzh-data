# -*- coding: utf-8 -*-
"""灵活拼接床头板分阶段创建：登记表 → EN/赛狐快照 → 合成通途SKU → 阶段记录。

登记表里只有 KS0453-OMR-60x30x20-WHITEMEDIUMGRAY 一个变体，
数量 3/4/5/6，通途SKU 全部为“无捆绑SKU”。
"""
from __future__ import annotations

import json

import soft_wall_stage as sws

sws.configure("灵活拼接床头板")

SUPPORT_PREFIXES = (
    "ND#",
    "PK#",
    "SXBZ",
    "PLBZ",
    "USNJ",
    "USTX",
    "ZLMB#",
    "套件#",
)


def build_plan_rows(*, full: bool = False) -> list[dict]:
    snapshot = json.loads(sws.latest_snapshot().read_text(encoding="utf-8"))
    items = [
        item
        for item in snapshot.get("en_items") or []
        if str(item.get("item_group") or "") == sws.KEYWORD
        and item.get("variant_of")
        and not str(item.get("item_code") or "").startswith(SUPPORT_PREFIXES)
    ]
    sellfox = snapshot.get("sellfox_by_sku") or {}
    rows: dict[str, dict] = {}
    for index, asin, shop, sku, name, qty in sws.read_register_rows():
        if not name or sws.KEYWORD not in name:
            continue
        try:
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        if len(items) != 1:
            continue
        item = items[0]
        refs = [
            str(c.get("ref_code") or "")
            for c in (item.get("customer_items") or [])
            if c.get("ref_code")
        ]
        if not refs:
            continue
        base_ref = refs[0]
        full_sku = f"{base_ref}-{item['item_code']}-{qty_int}pcs"
        row = rows.setdefault(
            full_sku,
            {
                "阶段": "测试",
                "通途SKU": full_sku,
                "数量": qty_int,
                "底层EN物料": item["item_code"],
                "赛狐底层SKU": item["item_code"],
                "赛狐底层ID": str((sellfox.get(item["item_code"]) or {}).get("id") or ""),
                "底层赛狐存在": "是" if sellfox.get(item["item_code"]) else "否",
                "物料名称": name,
                "ASIN": [],
                "店铺": [],
                "预计TJ#": "",
                "EN套件名称": "",
                "阶段状态": "待创建",
                "EN结果": "",
                "客户物料号结果": "",
                "赛狐结果": "",
                "完成时间": "",
                "备注": "直接基码",
            },
        )
        row["ASIN"].append(asin)
        row["店铺"].append(shop)
    for row in rows.values():
        row["ASIN"] = " | ".join(sorted(set(row["ASIN"])))
        row["店铺"] = " | ".join(sorted(set(row["店铺"])))
    return list(rows.values())


sws.build_plan_rows = build_plan_rows

if __name__ == "__main__":
    raise SystemExit(sws.main())
