# -*- coding: utf-8 -*-
"""Look up Tongtool goods by SKU via ERP2 goodsQuery (MCP HTTP). Read-only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPO = ROOT.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tongtool_order_cost.tongtool_goods import goods_query, summarize_existence


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("skus", nargs="+", help="Tongtool SKUs (max 10)")
    p.add_argument("--product-type", default="0", help="0 normal / 1 variable / 2 bundle / 3 assemble")
    args = p.parse_args()
    payload = goods_query(args.skus, product_type=args.product_type)
    found = summarize_existence(payload, args.skus)
    print("business_code", payload.get("code") if isinstance(payload, dict) else None)
    print("existence", json.dumps(found, ensure_ascii=False))
    datas = (payload.get("datas") or {}) if isinstance(payload, dict) else {}
    array = datas.get("array") or []
    for item in array:
        if not isinstance(item, dict):
            continue
        print(
            "PRODUCT",
            "sku=", item.get("sku"),
            "name=", (item.get("productName") or "")[:80],
            "status=", item.get("status"),
        )


if __name__ == "__main__":
    main()
