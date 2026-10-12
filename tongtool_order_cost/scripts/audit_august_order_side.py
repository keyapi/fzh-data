#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8 月原始订单 → EN Tongtool Order 只读数量与关系对账。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from tongtool_order_cost import gsheets
from tongtool_order_cost.order_side_input import (
    ErpnextOrderClient,
    group_order_documents,
    normalize_order_document,
    order_base,
    tiktok_platform_body,
)


def main_repo_root() -> Path:
    common_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], text=True, encoding="utf-8"
    ).strip()
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = Path.cwd() / common_path
    return common_path.resolve().parent


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def retry(operation, attempts: int = 8):
    for attempt in range(attempts):
        try:
            return operation()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 20))


def read_raw_order_ids(spreadsheet: str, worksheet: str) -> tuple[int, list[str]]:
    gc = retry(gsheets.client)
    sheet = retry(lambda: gc.open(spreadsheet))
    ws = retry(lambda: sheet.worksheet(worksheet))
    headers = retry(lambda: ws.row_values(1))
    if "订单号" not in headers:
        raise ValueError(f"原始表缺少列: 订单号；现有列数={len(headers)}")
    column = headers.index("订单号") + 1
    values = retry(lambda: ws.col_values(column))
    order_ids = [str(value).strip() for value in values[1:] if str(value).strip()]
    return max(len(values) - 1, 0), order_ids


def prefix(order_id: str) -> str:
    base = order_base(order_id)
    for index, char in enumerate(base):
        if char.isdigit():
            return base[:index].rstrip("-_")
    return base


def build_report(raw_rows: int, raw_order_ids: list[str], rows) -> dict[str, Any]:
    counts = Counter(raw_order_ids)
    unique_ids = list(dict.fromkeys(raw_order_ids))
    by_id = {row.order_id: row for row in rows}
    missing = [order_id for order_id in unique_ids if order_id not in by_id]
    duplicate_ids = {order_id: count for order_id, count in counts.items() if count > 1}

    bodies: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        body = tiktok_platform_body(row.order_id)
        if body:
            bodies[body].append(row.order_id)
    cross_prefix = []
    for body, order_ids in bodies.items():
        distinct = sorted(set(order_ids))
        if len({prefix(order_id) for order_id in distinct}) > 1:
            cross_prefix.append({"platform_order_body": body, "order_ids": distinct})

    return {
        "source": {
            "spreadsheet": "通途订单202608",
            "worksheet": "2026年8月订单",
            "raw_rows_read": raw_rows,
            "nonblank_order_rows": len(raw_order_ids),
            "unique_order_ids": len(unique_ids),
            "duplicate_order_rows": len(raw_order_ids) - len(unique_ids),
            "duplicate_order_ids": duplicate_ids,
        },
        "reconciliation": {
            "requested_unique": len(unique_ids),
            "fetched": len(rows),
            "missing": len(missing),
            "failed": 0,
            "empty_shell": sum(row.status == "empty_shell" for row in rows),
            "supplementary": sum(row.is_supplementary for row in rows),
            "no_cover": sum(row.piece_rule == "无皮壳·待复核" for row in rows),
            "confirmed_child_only": sum(
                row.is_child and row.original_order_exists is False for row in rows
            ),
            "parent_exists": sum(row.original_order_exists is True for row in rows),
            "parent_unknown": sum(
                row.is_child and row.original_order_exists is None for row in rows
            ),
            "mixed_shipping_methods": sum(len(row.shipping_methods) > 1 for row in rows),
            "cross_prefix_candidate_groups": len(cross_prefix),
        },
        "missing_order_ids": missing,
        "cross_prefix_candidates": cross_prefix,
        "orders": [asdict(row) for row in rows],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spreadsheet", default="通途订单202608")
    parser.add_argument("--worksheet", default="2026年8月订单")
    parser.add_argument("--output", default=str(MODULE_ROOT / "out" / "august_order_side_audit.json"))
    args = parser.parse_args(argv)

    repo = main_repo_root()
    os.environ.setdefault(
        "GSPREAD_SERVICE_ACCOUNT_FILE",
        str(repo / "secrets" / "gsheets-service-account.json"),
    )
    env = parse_env(repo / "EN_API" / ".env")
    api_key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY") or ""
    api_secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET") or ""
    if not api_key or not api_secret:
        raise SystemExit("EN_API/.env 缺少生产 ERPNext API 凭证")

    raw_rows, raw_order_ids = read_raw_order_ids(args.spreadsheet, args.worksheet)
    unique_ids = list(dict.fromkeys(raw_order_ids))
    base_ids = list(
        dict.fromkeys(
            order_base(order_id)
            for order_id in unique_ids
            if order_base(order_id) != order_id
        )
    )
    requested_ids = list(dict.fromkeys([*unique_ids, *base_ids]))

    client = ErpnextOrderClient(
        env.get("ERP_URL") or "https://erpnext.vilavi.cn",
        api_key,
        api_secret,
    )
    parents = client.list_orders_by_ids(requested_ids)
    fetched_ids = [str(parent.get("name") or "") for parent in parents]
    children = client.list_order_items_by_order_ids(fetched_ids)
    documents = group_order_documents(parents, children)
    normalized = [normalize_order_document(document) for document in documents]

    all_by_id = {row.order_id: row for row in normalized}
    rows = []
    for order_id in unique_ids:
        row = all_by_id.get(order_id)
        if row is None:
            continue
        if row.is_child:
            exists = row.base_order_id in all_by_id
            row = row.__class__(
                **{
                    **asdict(row),
                    "original_order_exists": exists,
                    "status": "child_only" if not exists and row.status == "ok" else row.status,
                    "items": row.items,
                }
            )
        rows.append(row)

    report = build_report(raw_rows, raw_order_ids, rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    source = report["source"]
    reconciliation = report["reconciliation"]
    print(json.dumps(source, ensure_ascii=False, indent=2))
    print(json.dumps(reconciliation, ensure_ascii=False, indent=2))
    print(f"报告: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
