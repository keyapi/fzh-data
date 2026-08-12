# -*- coding: utf-8 -*-
"""
本地运行 1.7.0 特殊规则并导出穿透审计工作簿。

用法（在 tongtool_order_cost/ 目录）:
  uv run python scripts/run_audit_170.py \\
    --orders "D:/path/orders.xlsx" \\
    --rules "D:/path/rules.xlsx" \\
    --month 202606 \\
    --account AMZBAINAUS \\
    --fx-usd 6.8167 \\
    --out out/AMZBAINAUS_202606_audit.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.audit import summarize_console, write_audit_workbook
from tongtool_order_cost.engine_170 import apply_special_rules
from tongtool_order_cost.io_loaders import load_fx_table, load_orders, load_rules


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="1.7.0 特殊规则本地审计")
    p.add_argument("--orders", required=True, help="未改成本的订单 Excel/CSV（1.4 同源）")
    p.add_argument("--rules", required=True, help="特殊规则表 Excel/CSV")
    p.add_argument("--month", default="202606", help="订单月 YYYYMM")
    p.add_argument("--account", default="", help="可选：过滤渠道账号")
    p.add_argument("--fx-file", default="", help="汇率表（收款币种,汇率）")
    p.add_argument("--fx-usd", type=float, default=None, help="USD 汇率（优先于订单众数）")
    p.add_argument("--dedup-keep", choices=("last", "first"), default="last")
    p.add_argument(
        "--out",
        default="",
        help="审计 xlsx 输出路径（默认 out/<account>_<month>_audit.xlsx）",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    account = args.account.strip() or None
    orders = load_orders(args.orders, account=account)
    rules = load_rules(args.rules)
    fx, fx_source = load_fx_table(
        fx_file=args.fx_file or None,
        fx_usd=args.fx_usd,
        orders=orders,
    )
    if fx_source == "none" or len(fx) == 0:
        print("ERROR: 无汇率。请提供 --fx-usd 或 --fx-file，或订单含 汇率 列。")
        return 2
    if fx_source.startswith("orders-"):
        print(f"WARN: 使用订单汇率众数近似 — {fx_source}")

    result = apply_special_rules(
        orders,
        rules,
        args.month,
        fx,
        dedup_keep=args.dedup_keep,
        fx_source=fx_source,
        verbose=not args.quiet,
    )

    out = args.out.strip()
    if not out:
        acct = account or "ALL"
        out = str(ROOT / "out" / f"{acct}_{args.month}_audit.xlsx")
    path = write_audit_workbook(result, out)
    summarize_console(result)
    print(f"\n审计工作簿已写入: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
