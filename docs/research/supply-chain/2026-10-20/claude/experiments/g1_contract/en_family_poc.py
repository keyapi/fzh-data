#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Family SO 批量只读 PoC（E01/E02 第一段，修正日期/角色/截断/partial）。

- 日期口径显式：默认 delivery_date，可切 transaction_date；所有来源共用同一口径。
- family 角色：KS / PK# / ND# / group / customer；无法裁定记 pending，不直接算非 family。
- 来源 stats：候选行数、页数、终止依据；候选/选中/截断/详情失败逐层对平。
- 只读 EN；输出 JSONL + manifest。不含 DN/WO/JC/SE。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_family_manifest(path: Path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    i_item = hdr.index("产品编号")
    i_code = hdr.index("客户物料号")
    items: set[str] = set()
    codes: set[str] = set()
    for r in rows:
        item = str(r[i_item] or "").strip()
        code = str(r[i_code] or "").strip()
        if not item.startswith(FAMILY_PREFIXES):
            continue
        items.add(item)
        if code and "已删除" not in code:
            codes.add(code)
    wb.close()
    variants = set()
    for item in items:
        variants.update({item, f"PK#{item}", f"ND#{item}"})
    manifest = {
        "version": "family_manifest/20261016",
        "ks_items": sorted(items),
        "customer_codes": sorted(codes),
        "query_item_codes": sorted(variants),
        "roles": {"KS": "finished/leaf", "PK#": "packaging/cover candidate",
                  "ND#": "historical/other candidate"},
    }
    blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest["sha256"] = sha256_bytes(blob)
    return manifest


def normalize_item(item: str) -> tuple[str, str]:
    for prefix, role in (("PK#", "PK"), ("ND#", "ND")):
        if item.startswith(prefix):
            return item[len(prefix):], role
    return item, "KS"


def classify_line(item: str, group: str, cust: str, groups: list[str],
                  family_items: set[str], family_codes: set[str]) -> tuple[str, str]:
    base, role = normalize_item(item)
    if base.startswith(FAMILY_PREFIXES) or base in family_items:
        return "family", role
    if group in groups:
        return "family", "group"
    if cust in family_codes:
        return "family", "customer"
    if item.startswith(("PK#", "ND#")):
        return "pending", "unknown_prefix"
    return "out_of_scope", "other"


def paged_so(filters: list, base_url: str, key: str, secret: str,
             label: str, page_size: int = 100):
    rows, start, pages, complete = [], 0, 0, False
    fields = iss.SO_FIELDS
    fallback = ["name", "status", "docstatus", "customer", "delivery_date",
                "transaction_date"]
    while pages < 200:
        status, body = iss.api_get_status(
            iss._build_url("Sales Order", filters, fields, start, page_size, "name asc"),
            base_url, key, secret,
        )
        if status == 417:
            fields = fallback
            status, body = iss.api_get_status(
                iss._build_url("Sales Order", filters, fields, start, page_size, "name asc"),
                base_url, key, secret,
            )
        if status != 200:
            raise iss.QueryError(f"{label}: HTTP {status} {str(body)[:140]}")
        pages += 1
        data = body.get("data", []) or []
        if not data:
            complete = True
            break
        rows.extend(data)
        if len(data) < page_size:
            complete = True
            break
        start += len(data)
    return rows, {"rows": len(rows), "pages": pages, "complete": complete,
                  "termination": "empty" if not data else ("short_page" if complete else "max_pages")}


def main():
    ap = argparse.ArgumentParser(description="Family SO 批量只读 PoC")
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--date-basis", choices=("delivery", "transaction"), default="delivery")
    ap.add_argument("--groups", default=",".join(DEFAULT_GROUPS))
    ap.add_argument("--bom", default=str(BOM))
    ap.add_argument("--no-item-codes", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-sos", type=int, default=500)
    args = ap.parse_args()

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    date_field = "delivery_date" if args.date_basis == "delivery" else "transaction_date"
    family = load_family_manifest(Path(args.bom))
    family_items = set(family["ks_items"])
    family_codes = set(family["customer_codes"])

    key, secret = iss.load_credentials("prod", iss.resolve_env_files())
    if not key or not secret:
        print("✗ EN 生产凭证未配置", file=sys.stderr)
        return 2
    base = iss.ENV_URLS["prod"]

    source_stats = {}
    matched_sources: dict[str, set[str]] = defaultdict(set)
    raw_all = []

    group_filter = iss.child_filter("Sales Order Item", "item_group", "in", groups)
    rows, stats = paged_so(group_filter + [[date_field, ">=", args.date_from],
                                           [date_field, "<=", args.date_to]],
                           base, key, secret, "SO(group)")
    source_stats["group"] = stats
    raw_all.extend((r, "group") for r in rows)

    if not args.no_item_codes:
        item_rows = 0
        item_pages = 0
        item_complete = True
        for chunk in iss.chunks(family["query_item_codes"], iss.IN_CHUNK):
            rows, stats = paged_so(
                [["Sales Order Item", "item_code", "in", chunk],
                 [date_field, ">=", args.date_from],
                 [date_field, "<=", args.date_to]],
                base, key, secret, f"SO(item {chunk[0]}…)",
            )
            item_rows += stats["rows"]
            item_pages += stats["pages"]
            item_complete = item_complete and stats["complete"]
            raw_all.extend((r, "item_code") for r in rows)
        source_stats["item_code"] = {"rows": item_rows, "pages": item_pages,
                                     "complete": item_complete,
                                     "termination": "sum_of_chunks"}

    pilot_rows = 0
    pilot_pages = 0
    pilot_complete = True
    for code in sorted(PILOT_CODES):
        rows, stats = paged_so(
            [["Sales Order Item", "customer_item_code", "like", f"%{code}%"],
             [date_field, ">=", args.date_from],
             [date_field, "<=", args.date_to]],
            base, key, secret, f"SO(pilot {code})",
        )
        pilot_rows += stats["rows"]
        pilot_pages += stats["pages"]
        pilot_complete = pilot_complete and stats["complete"]
        raw_all.extend((r, "pilot") for r in rows)
    source_stats["pilot"] = {"rows": pilot_rows, "pages": pilot_pages,
                             "complete": pilot_complete, "termination": "sum_of_codes"}

    by_name = {}
    for row, src in raw_all:
        name = row.get("name")
        if not name:
            continue
        by_name.setdefault(name, row)
        matched_sources[name].add(src)
    candidate_sos = len(by_name)
    selected = sorted(by_name.values(), key=lambda r: r.get("name") or "")
    truncated = candidate_sos > args.max_sos
    selected = selected[:args.max_sos]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    counts = defaultdict(int)
    detail_failed = []
    pilot_seen = set()
    with out_path.open("w", encoding="utf-8") as f:
        for i, so in enumerate(selected):
            d = iss.get_single("Sales Order", so["name"], base, key, secret)
            if i + 1 < len(selected):
                time.sleep(0.15)
            if not d:
                detail_failed.append(so["name"])
                continue
            srcs = sorted(matched_sources.get(so["name"], []))
            for line in d.get("items", []):
                item = str(line.get("item_code") or "")
                cust = str(line.get("customer_item_code") or "")
                group = str(line.get("item_group") or "")
                disposition, role = classify_line(item, group, cust, groups,
                                                  family_items, family_codes)
                counts[disposition] += 1
                counts[f"role:{role}"] += 1
                if disposition != "family":
                    continue
                if cust in PILOT_CODES:
                    pilot_seen.add(cust)
                qty = float(line.get("qty") or 0)
                delivered = float(line.get("delivered_qty") or 0)
                f.write(json.dumps({
                    "run_id": run_id,
                    "so": so["name"],
                    "line_id": line.get("name"),
                    "so_status": d.get("status"),
                    "so_docstatus": d.get("docstatus"),
                    "transaction_date": d.get("transaction_date"),
                    "delivery_date": d.get("delivery_date"),
                    "item_code": item,
                    "customer_item_code": cust,
                    "item_group": group,
                    "family_role": role,
                    "matched_sources": srcs,
                    "warehouse": line.get("warehouse") or d.get("set_warehouse"),
                    "uom": line.get("uom"),
                    "qty": qty,
                    "delivered_qty": delivered,
                    "open_qty": qty - delivered,
                    "amended_from": d.get("amended_from"),
                }, ensure_ascii=False) + "\n")

    status = "complete"
    reasons = []
    if truncated:
        status = "partial"
        reasons.append("max_sos_truncated")
    if detail_failed:
        status = "partial"
        reasons.append("detail_failed")
    if any(not s.get("complete") for s in source_stats.values()):
        status = "partial"
        reasons.append("source_incomplete")
    manifest = {
        "run_id": run_id,
        "script_sha256": sha256_file(Path(__file__)),
        "family_manifest_version": family["version"],
        "family_manifest_sha256": family["sha256"],
        "family_manifest_counts": {
            "ks_items": len(family["ks_items"]),
            "customer_codes": len(family["customer_codes"]),
            "query_item_codes": len(family["query_item_codes"]),
        },
        "date_basis": date_field,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "groups": groups,
        "sources": source_stats,
        "candidate_sos": candidate_sos,
        "selected_sos": len(selected),
        "truncated": truncated,
        "max_sos": args.max_sos,
        "detail_failed": detail_failed,
        "line_dispositions": {k: v for k, v in counts.items() if not k.startswith("role:")},
        "line_roles": {k[5:]: v for k, v in counts.items() if k.startswith("role:")},
        "pilot_expected": sorted(PILOT_CODES),
        "pilot_seen": sorted(pilot_seen),
        "pilot_missing": sorted(PILOT_CODES - pilot_seen),
        "status": status,
        "status_reasons": reasons,
        "out": str(out_path),
        "out_sha256": sha256_file(out_path),
        "notes": [
            "只读 SO 批量 PoC；不含 DN/WO/JC/SE。",
            "所有来源共用同一日期口径；delivery 与 transaction 不混算。",
            "family 角色含 KS/PK#/ND#/group/customer；无法裁定记 pending。",
            "候选→选中→详情失败→逐行处置逐层记录。",
        ],
    }
    (out_path.parent / "family_poc_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: manifest[k] for k in
                      ("status", "candidate_sos", "selected_sos", "line_dispositions",
                       "pilot_missing")}, ensure_ascii=False))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
