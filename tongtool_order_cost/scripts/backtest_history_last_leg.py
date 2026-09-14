# -*- coding: utf-8 -*-
"""用同一批订单回测 HLF0001 与分层模型的误差（只读）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (
    add_outlier_flags,
    backtest_against_legacy,
    build_package_observations,
    build_publishable_tiers,
    compare_holdout_precedence,
    load_legacy_items,
    prepare_order_rows,
    summarize_holdout_dimensions,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="历史尾程：HLF0001 vs 分层模型 回测")
    parser.add_argument("--orders", default=str(ROOT / "out" / "monthly_orders_full.csv.gz"))
    parser.add_argument("--legacy", default=str(ROOT / "out" / "hlf0001_items.csv.gz"))
    parser.add_argument("--out", default=str(ROOT / "out" / "history_last_leg_backtest.xlsx"))
    parser.add_argument("--train-end", default="202604", help="训练截止月份 YYYYMM")
    parser.add_argument("--validation-start", default="202605", help="验证起始月份 YYYYMM")
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-months", type=int, default=2)
    args = parser.parse_args(argv)

    orders = pd.read_csv(args.orders, dtype=str)
    legacy = load_legacy_items(args.legacy)
    print(f"订单行: {len(orders)}  旧模型记录: {len(legacy)}")

    rows = pd.concat(
        [prepare_order_rows(frame, month) for month, frame in orders.groupby("月份")],
        ignore_index=True,
    )
    observations = add_outlier_flags(build_package_observations(rows))
    publishable = build_publishable_tiers(observations)
    by_market, overall = backtest_against_legacy(observations, legacy, publishable)
    holdout_detail, holdout_summary = compare_holdout_precedence(
        observations,
        legacy,
        train_end_month=args.train_end,
        validation_start_month=args.validation_start,
        min_samples=args.min_samples,
        min_months=args.min_months,
    )
    holdout_dimensions = summarize_holdout_dimensions(holdout_detail)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        overall.to_excel(writer, sheet_name="00_全量拟合_总体", index=False)
        by_market.to_excel(writer, sheet_name="01_全量拟合_国家", index=False)
        holdout_summary.to_excel(writer, sheet_name="10_Holdout方案", index=False)
        for sheet_name, frame in holdout_dimensions.items():
            frame.to_excel(writer, sheet_name=f"2{sheet_name[1:]}", index=False)
        holdout_detail.to_excel(writer, sheet_name="30_Holdout明细", index=False)

    print(f"输出: {out_path}")
    print("全量拟合（仅作对照，不作为发布闸门）")
    print(overall.to_string(index=False))
    print("\n严格时间 Holdout（发布闸门）")
    print(holdout_summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
