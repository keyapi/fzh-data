# -*- coding: utf-8 -*-
"""读取月度 Google Sheet 并生成历史尾程费用只读分析工作簿。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.gsheets import client, gsheet2df
from tongtool_order_cost.history_last_leg_analysis import analyze_history_last_leg, write_history_last_leg_workbook

DEFAULT_MONTHS = ("202511", "202512", "202601", "202602", "202603", "202604", "202605", "202606")


def worksheet_name(month: str) -> str:
    return f"{month[:4]}年{int(month[4:])}月订单"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EN 历史尾程费用只读分析")
    parser.add_argument("--months", nargs="+", default=list(DEFAULT_MONTHS), help="月份列表 YYYYMM")
    parser.add_argument("--out", default=str(ROOT / "out" / "history_last_leg_202511_202606.xlsx"))
    parser.add_argument(
        "--cache",
        default=str(ROOT / "out" / "monthly_orders_full.csv.gz"),
        help="把标准化后的订单行缓存到本地（gitignore），供回测复用；留空则跳过",
    )
    args = parser.parse_args(argv)

    gc = client()
    monthly_orders = []
    for month in args.months:
        sheet = f"通途订单{month}"
        worksheet = worksheet_name(month)
        print(f"读取: {sheet} / {worksheet}")
        monthly_orders.append((month, gsheet2df(gc, sheet, worksheet)))

    report = analyze_history_last_leg(monthly_orders)
    out_path = write_history_last_leg_workbook(report, args.out)
    print(f"输出: {out_path}")
    if args.cache.strip():
        cache_path = Path(args.cache)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        report.rows.to_csv(cache_path, index=False, compression="gzip")
        print(f"缓存订单行: {cache_path} ({len(report.rows)} 行)")
    print(report.reconciliation.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
