# -*- coding: utf-8 -*-
"""Read-only lookup for 软包墙围 EN items and Sellfox commodities.

Usage:
    uv run --project .. python soft_wall_lookup.py [--out snapshot.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from client import SellfoxClient, SellfoxConfig

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / "EN_API" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    return values


def en_session(env: dict[str, str]) -> tuple[str, requests.Session]:
    base = env.get("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/")
    key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY")
    secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET")
    if not key or not secret:
        raise SystemExit("EN API 凭证缺失")
    session = requests.Session()
    session.headers["Authorization"] = f"token {key}:{secret}"
    return base, session


def en_list(base: str, session: requests.Session, filters: list, fields: list[str]) -> list[dict]:
    rows: list[dict] = []
    start = 0
    page_size = 200
    while True:
        response = session.get(
            f"{base}/api/resource/Item",
            params={
                "filters": json.dumps(filters, ensure_ascii=False),
                "fields": json.dumps(fields),
                "limit_page_length": page_size,
                "limit_start": start,
            },
            timeout=60,
        )
        response.raise_for_status()
        batch = response.json().get("data") or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def en_detail(base: str, session: requests.Session, item_code: str) -> dict:
    response = session.get(
        f"{base}/api/resource/Item/{requests.utils.quote(item_code, safe='')}",
        params={
            "fields": json.dumps(
                [
                    "item_code",
                    "item_name",
                    "item_group",
                    "variant_of",
                    "disabled",
                    "customer_items",
                ]
            )
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("data") or {}


def sellfox_skus(client: SellfoxClient, skus: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    unique = list(dict.fromkeys(sku for sku in skus if sku))
    for offset in range(0, len(unique), 50):
        chunk = unique[offset : offset + 50]
        page = 1
        while True:
            data = client.signed_post(
                "/api/commodity/pageList.json",
                {"pageNo": str(page), "pageSize": "50", "skus": chunk},
            )
            rows = data.get("rows") or [] if isinstance(data, dict) else []
            for row in rows:
                sku = str(row.get("sku") or "")
                if sku:
                    found[sku] = {
                        "id": row.get("id"),
                        "sku": row.get("sku"),
                        "name": row.get("name"),
                        "isGroup": row.get("isGroup"),
                        "fullCid": row.get("fullCid"),
                        "fullName": row.get("fullName"),
                        "childSkus": row.get("childSkus"),
                    }
            total = int(data.get("total") or 0) if isinstance(data, dict) else 0
            page_size = int(data.get("pageSize") or 50) if isinstance(data, dict) else 50
            pages = -(-total // page_size) if page_size else 1
            if page >= pages:
                break
            page += 1
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="把快照写到 JSON 文件")
    parser.add_argument("--product", default="软包墙围", help="产品关键字，默认 软包墙围")
    args = parser.parse_args()

    env = load_env()
    base, session = en_session(env)

    print(f"=== EN Items: item_name like {args.product} ===")
    fields = ["item_code", "item_name", "item_group", "variant_of", "disabled"]
    items = en_list(
        base,
        session,
        [["Item", "item_name", "like", f"%{args.product}%"]],
        fields,
    )
    print(f"EN items: {len(items)}")
    details: list[dict] = []
    for row in items:
        detail = en_detail(base, session, row["item_code"])
        details.append(
            {
                "item_code": detail.get("item_code"),
                "item_name": detail.get("item_name"),
                "item_group": detail.get("item_group"),
                "variant_of": detail.get("variant_of"),
                "disabled": detail.get("disabled"),
                "customer_items": [
                    {"customer_group": c.get("customer_group"), "ref_code": c.get("ref_code")}
                    for c in (detail.get("customer_items") or [])
                ],
            }
        )
    for row in details:
        print(json.dumps(row, ensure_ascii=False, indent=2))

    print(f"=== EN Items: item_group 套件# and item_name like {args.product} ===")
    bundle_items = en_list(
        base,
        session,
        [
            ["Item", "item_name", "like", f"%{args.product}%"],
            ["Item", "item_group", "like", "%套件%"],
        ],
        fields,
    )
    print(f"EN bundle items: {len(bundle_items)}")
    bundle_details: list[dict] = []
    for row in bundle_items:
        detail = en_detail(base, session, row["item_code"])
        bundle_details.append(
            {
                "item_code": detail.get("item_code"),
                "item_name": detail.get("item_name"),
                "item_group": detail.get("item_group"),
                "disabled": detail.get("disabled"),
                "customer_items": [
                    {"customer_group": c.get("customer_group"), "ref_code": c.get("ref_code")}
                    for c in (detail.get("customer_items") or [])
                ],
            }
        )
    for row in bundle_details:
        print(json.dumps(row, ensure_ascii=False, indent=2))

    print("=== Sellfox pageList ===")
    client = SellfoxClient(SellfoxConfig.from_env(ROOT / ".env", ROOT / "EN_API" / ".env"))
    all_skus = list(dict.fromkeys([r["item_code"] for r in details] + [r["item_code"] for r in bundle_details]))
    sx = sellfox_skus(client, all_skus)
    print(f"checked SKUs: {len(all_skus)}, found: {len(sx)}")
    for sku, row in sx.items():
        print(json.dumps(row, ensure_ascii=False, indent=2))

    if args.out:
        snapshot = {
            "en_items": details,
            "en_bundle_items": bundle_details,
            "sellfox_by_sku": sx,
        }
        Path(args.out).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"快照已写: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
