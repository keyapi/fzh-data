"""Read-only order, SKU, package and persisted-cost coverage checks.

Input and detail outputs contain business identifiers and must stay outside git.
No accounting decisions or historical cost recomputation are made here.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from sellfox_settlement.validation_paths import private_output


def validate_input(rows, required, label):
    if not isinstance(rows, list):
        raise ValueError(f"{label}: expected a JSON array")
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"{label} row {position}: expected an object")
        missing = required - row.keys()
        if missing:
            raise ValueError(f"{label} row {position}: missing columns {', '.join(sorted(missing))}")


def base_order_id(value):
    return re.sub(r"_\d+$", "", str(value or "").strip())


def normalize_sku(value):
    """Treat Unicode spaces as the same SKU character. Amazon exports sometimes use NBSP."""
    return "".join(" " if unicodedata.category(ch) == "Zs" else ch for ch in str(value or "")).strip()


def match_transaction(row, orders):
    oid = str(row.get("order_id") or "").strip()
    sku = normalize_sku(row.get("sku"))
    candidates = [o for o in orders if base_order_id(o.get("platform_order_id")) == oid]
    account = row.get("account")
    if account:
        candidates = [o for o in candidates if o.get("sale_account") == account]
    result = {"status": "order_unmatched", "order_count": len(candidates), "item_count": 0, "package_count": 0}
    if not candidates:
        return result
    if len({o.get("sale_account") for o in candidates}) > 1:
        return {**result, "status": "ambiguous_account"}
    exact = [o for o in candidates if o.get("platform_order_id") == oid]
    split = [o for o in candidates if o.get("platform_order_id") != oid]
    if exact and split:
        return {**result, "status": "ambiguous_parent_child"}
    items = [i for o in candidates for i in o.get("order_items", []) if normalize_sku(i.get("platform_sku")) == sku and sku]
    if not items:
        return {**result, "status": "sku_unmatched" if sku else "sku_missing"}
    selected = [o for o in candidates if any(normalize_sku(i.get("platform_sku")) == sku for i in o.get("order_items", []))]
    en_fulfillment = {"FBA" if o.get("order_type") == "FBA" else "FBM" for o in selected if o.get("order_type") in {"FBA", "FBM", "自发货"}}
    if row.get("fulfillment") in {"FBA", "FBM"} and en_fulfillment and en_fulfillment != {row["fulfillment"]}:
        return {**result, "status": "fulfillment_conflict"}
    packages = {p.get("package") for o in selected for p in o.get("packages", []) if p.get("package")}
    return {**result, "status": "matched", "order_count": len(selected), "item_count": len(items), "package_count": len(packages),
            "en_order_types": sorted({o.get("order_type") or "unknown" for o in selected}),
            "erp_item_count": sum(bool(i.get("erp_item_code")) for i in items),
            "product_cost_positive_count": sum(float(i.get("sx_shipping_cost") or 0) > 0 for i in items),
            "first_freight_positive_count": sum(float(i.get("first_freight") or 0) > 0 for i in items),
            "tail_source_counts": dict(Counter(i.get("last_leg_fee_sources") or "empty" for i in items)),
            "en_order_names": [o["name"] for o in selected]}


def summarize_coverage(rows, orders, supplemental_orders=None, account_by_file=None):
    account_by_file = account_by_file or {}
    order_index = {}
    for order in orders:
        order_index.setdefault(base_order_id(order.get("platform_order_id")), []).append(order)
    extra_index = {}
    for order in {o["name"]: o for o in [*orders, *(supplemental_orders or [])]}.values():
        extra_index.setdefault(base_order_id(order.get("platform_order_id")), []).append(order)
    details = []
    statuses = Counter()
    supplemental = Counter()
    fulfillment = {}
    unique = set()
    for row in rows:
        eligible = row.get("type") in {"Order", "Refund"} and bool(row.get("order_id"))
        scoped = row
        if account_by_file and not row.get("account"):
            scoped = {**row, "account": account_by_file.get(Path(str(row.get("source_file") or "")).name)}
        result = match_transaction(scoped, order_index.get(row.get("order_id"), [])) if eligible else {"status": "excluded_non_order_or_missing_id"}
        if row.get("type") in {"Refund_Retrocharge", "Chargeback Refund"} and row.get("order_id"):
            extra = match_transaction(row, extra_index[row["order_id"]]) if row["order_id"] in extra_index else {"status": "not_in_primary_snapshot"}
            supplemental[extra["status"]] += 1
            result["supplemental_link_probe"] = extra
        details.append({"source_file": row.get("source_file"), "source_line": row.get("source_line"), "order_id": row.get("order_id"), "sku": row.get("sku"), "type": row.get("type"), "fulfillment": row.get("fulfillment"), **result})
        statuses[result["status"]] += 1
        if eligible:
            group = row.get("fulfillment") or "unknown"
            fulfillment.setdefault(group, Counter())[result["status"]] += 1
            unique.add((row.get("source_file"), row.get("order_id"), row.get("sku")))
    excluded = statuses.get("excluded_non_order_or_missing_id", 0)
    return {"input_rows": len(rows), "eligible_rows": len(rows)-excluded, "excluded_rows": excluded,
            "statuses": dict(statuses), "fulfillment": {k: dict(v) for k, v in fulfillment.items()},
            "supplemental_link_statuses": dict(supplemental),
            "unique_source_order_sku_pairs": len(unique), "en_candidate_orders": len(orders)}, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--supplemental-orders", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.output_dir = private_output(args.output_dir)
    except ValueError as exc:
        parser.error(str(exc))
    rows = json.loads(args.transactions.read_text(encoding="utf-8"))
    orders = json.loads(args.orders.read_text(encoding="utf-8"))
    validate_input(rows, {"type", "order_id", "sku", "fulfillment", "source_file", "source_line"}, "transactions")
    validate_input(orders, {"name", "platform_order_id", "order_items", "packages"}, "orders")
    supplemental_orders = json.loads(args.supplemental_orders.read_text(encoding="utf-8")) if args.supplemental_orders else []
    validate_input(supplemental_orders, {"name", "platform_order_id", "order_items", "packages"}, "supplemental orders")
    report, details = summarize_coverage(rows, orders, supplemental_orders)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "cost_coverage_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "cost_coverage_details.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
