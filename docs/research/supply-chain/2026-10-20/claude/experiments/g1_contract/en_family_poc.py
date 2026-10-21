#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Family SO 批量只读 PoC（E01/E02 的第一段）。

按 `Sales Order Item.item_group in (三角靠枕, 三角靠枕无扣)` + 业务日期窗口拉父单，
再逐单取明细，按行筛选 family / 非 family 同行，输出 JSONL + manifest。

不做 DN/WO/JC/SE；这是批次完整性、family manifest、逐行去向的 PoC。
所有查询只读；不写 EN。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import openpyxl

REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "EN_API" / "item_shipment_status.py").exists()),
    Path(__file__).resolve().parents[7],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import EN_API.item_shipment_status as iss  # noqa: E402

DEFAULT_GROUPS = ["三角靠枕", "三角靠枕无扣"]
FAMILY_PREFIXES = ("KS0001", "KS0248")
BOM = Path(r"D:/Work/王忠于/成本核算/EN产品BOM成本列表20261016.xlsx")
PILOT_CODES = {
    "CENCord995-DKGrey-97", "CEN003-DPBLUE-100",
    "C/Linen-Natural-100-688-wow", "C/Cord-DKBlue-100-713-wow",
    "C/Linen-Natural-194-688-wow", "C/Linen-Natural-153-688-wow",
    "C/Velvet-Grey-100-705-wow", "C/Cord-Grey-100-710-wow",
    "C/Linen-White-100-662-WOW", "TT0000671K0063721",
}


def load_family_items(path: Path = BOM) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    i_item = hdr.index("产品编号")
    items = set()
    for r in rows:
        item = str(r[i_item] or "").strip()
        if item.startswith(FAMILY_PREFIXES):
            items.add(item)
    wb.close()
    return sorted(items)


def main():
    ap = argparse.ArgumentParser(description="Family SO 批量只读 PoC")
    ap.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--groups", default=",".join(DEFAULT_GROUPS))
    ap.add_argument("--bom", default=str(BOM))
    ap.add_argument("--no-item-codes", action="store_true",
                    help="只按 item_group + pilot 客户码查询")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-sos", type=int, default=500)
    args = ap.parse_args()

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    key, secret = iss.load_credentials("prod", iss.resolve_env_files())
    if not key or not secret:
        print("✗ EN 生产凭证未配置", file=sys.stderr)
        return 2
    base = iss.ENV_URLS["prod"]

    raw_all = []
    sources = {}
    group_filter = iss.child_filter("Sales Order Item", "item_group", "in", groups)
    for label, date_field in (("group_delivery", "delivery_date"),
                              ("group_tx", "transaction_date")):
        filters = list(group_filter) + [
            [date_field, ">=", args.date_from],
            [date_field, "<=", args.date_to],
        ]
        rows = iss.paginated_get(
            "Sales Order", base, key, secret, filters, iss.SO_FIELDS,
            fallback_fields=["name", "status", "docstatus", "customer", "delivery_date",
                             "transaction_date"],
            label=f"SO({label})",
        )
        sources[label] = len(rows)
        raw_all.extend(rows)

    item_rows = 0
    if not args.no_item_codes:
        items = load_family_items(Path(args.bom))
        for chunk in iss.chunks(items, iss.IN_CHUNK):
            filters = [["Sales Order Item", "item_code", "in", chunk],
                       ["delivery_date", ">=", args.date_from],
                       ["delivery_date", "<=", args.date_to]]
            rows = iss.paginated_get(
                "Sales Order", base, key, secret, filters, iss.SO_FIELDS,
                fallback_fields=["name", "status", "docstatus", "customer",
                                 "delivery_date", "transaction_date"],
                label="SO(family item)",
            )
            item_rows += len(rows)
            raw_all.extend(rows)
    sources["item_code_rows"] = item_rows

    pilot_rows = 0
    for code in sorted(PILOT_CODES):
        rows = iss.find_sales_orders_by_customer_code(code, base, key, secret)
        pilot_rows += len(rows)
        raw_all.extend(rows)
    sources["pilot_code_rows"] = pilot_rows

    sos = iss.dedupe_by(raw_all, "name")
    if len(sos) > args.max_sos:
        sos = sos[:args.max_sos]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    family_lines = []
    non_family_lines = 0
    field_issues = []
    pilot_seen = set()
    for i, so in enumerate(sos):
        d = iss.get_single("Sales Order", so["name"], base, key, secret)
        if i + 1 < len(sos):
            time.sleep(0.15)
        if not d:
            field_issues.append({"so": so["name"], "issue": "missing_doc"})
            continue
        for line in d.get("items", []):
            item = str(line.get("item_code") or "")
            cust = str(line.get("customer_item_code") or "")
            group = str(line.get("item_group") or "")
            is_family = (item.startswith(FAMILY_PREFIXES)
                         or group in groups
                         or cust in PILOT_CODES)
            if not is_family:
                non_family_lines += 1
                continue
            if cust in PILOT_CODES:
                pilot_seen.add(cust)
            qty = float(line.get("qty") or 0)
            delivered = float(line.get("delivered_qty") or 0)
            family_lines.append({
                "run_so": so["name"],
                "so": so["name"],
                "line_id": line.get("name"),
                "so_status": d.get("status"),
                "so_docstatus": d.get("docstatus"),
                "transaction_date": d.get("transaction_date"),
                "delivery_date": d.get("delivery_date"),
                "item_code": item,
                "customer_item_code": cust,
                "item_group": group,
                "warehouse": line.get("warehouse") or d.get("set_warehouse"),
                "uom": line.get("uom"),
                "qty": qty,
                "delivered_qty": delivered,
                "open_qty": qty - delivered,
                "amended_from": d.get("amended_from"),
                "source_row": line.get("name"),
            })
    with out_path.open("w", encoding="utf-8") as f:
        for r in family_lines:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "run_id": datetime.now().strftime("%Y%m%dT%H%M%S"),
        "script_version": "en_family_poc/0.1",
        "system": base,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "groups": groups,
        "sources": sources,
        "so_headers": len(sos),
        "family_lines": len(family_lines),
        "non_family_sibling_lines": non_family_lines,
        "field_issues": field_issues,
        "pilot_codes_expected": sorted(PILOT_CODES),
        "pilot_codes_seen": sorted(pilot_seen),
        "pilot_codes_missing": sorted(PILOT_CODES - pilot_seen),
        "out": str(out_path),
        "notes": [
            "只读 SO 批量 PoC；不含 DN/WO/JC/SE。",
            "父单按 item_group 查询，行级再筛 family；非 family 同行只计数。",
            "业务日期窗口，不是 modified 增量；E02 增量另做。",
        ],
    }
    (out_path.parent / "family_poc_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: manifest[k] for k in
                      ("so_headers", "family_lines", "non_family_sibling_lines",
                       "pilot_codes_seen", "pilot_codes_missing")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
