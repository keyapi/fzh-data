# -*- coding: utf-8 -*-
"""
美中 DANEEY 通途订单 PP 棉用量估算。

用法（在 tongtool_order_cost/ 目录）:
  uv run python scripts/estimate_pp_cotton.py \\
    --orders "D:/Work/王忠于/成本核算/2026年7月订单_order_cost_2026-08-04_16-04-23.xlsx" \\
    --bom "D:/Work/王忠于/成本核算/EN产品BOM成本列表 20260806.xlsx" \\
    --month 202607 \\
    --out "D:/Work/王忠于/成本核算/美中DANEEY_202607_PP棉估算.xlsx"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.io_loaders import load_orders
from tongtool_order_cost.pp_cotton import estimate_pp_cotton, load_bom, write_pp_cotton_workbook


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="美中 DANEEY 通途订单 PP 棉用量估算")
    p.add_argument("--orders", required=True, help="通途订单 Excel（含通途SKU、发货仓库、发货数量）")
    p.add_argument("--bom", required=True, help="EN BOM Cost List Excel")
    p.add_argument("--month", default="", help="可选：过滤发货月 YYYYMM，如 202607")
    p.add_argument(
        "--warehouse",
        choices=("daneey", "all"),
        default="daneey",
        help="仓库过滤，默认仅 DANEEY/USTX/美中",
    )
    p.add_argument("--out", default="", help="输出 xlsx；默认 out/DANEEY_<month>_pp_cotton.xlsx")
    args = p.parse_args(argv)

    orders = load_orders(args.orders)
    bom = load_bom(args.bom)
    month = args.month.strip() or None

    report = estimate_pp_cotton(orders, bom, warehouse_filter=args.warehouse, month=month)

    if args.out.strip():
        out_path = Path(args.out)
    else:
        suffix = month or "all"
        out_path = ROOT / "out" / f"DANEEY_{suffix}_pp_cotton.xlsx"

    write_pp_cotton_workbook(report, out_path)

    print(f"输出: {out_path}")
    for row in report.summary_rows:
        label = row["指标"]
        value = row["值"]
        note = row.get("说明")
        if note:
            print(f"  {label}: {value}  ({note})")
        else:
            print(f"  {label}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
