# -*- coding: utf-8 -*-
"""生成 EN `History Last Leg Fee Record` 候选导入文件（只读分析，不写线）。

默认只用本地缓存 `out/monthly_orders_full.csv.gz`（由 analyze_history_last_leg.py
产生），避免重复读表；`--from-sheets` 时重新从 Google Sheet 读取。

输出（均在 gitignore 的 out/ 下）：
- `<out>`           子表导入 CSV（列名与线上字段一致）
- `<out>.parent.json` parent 契约：模型版本、适用期、回测指标、状态 Draft
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (  # noqa: E402
    add_outlier_flags,
    build_package_observations,
    build_publishable_tiers,
    prepare_order_rows,
    summarize_publish_coverage,
)
from tongtool_order_cost.history_last_leg_export import (  # noqa: E402
    ExportContract,
    build_import_rows,
    write_import_rows,
)

DEFAULT_MONTHS = ("202511", "202512", "202601", "202602", "202603", "202604", "202605", "202606")


def worksheet_name(month: str) -> str:
    return f"{month[:4]}年{int(month[4:])}月订单"


def load_cached(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"缓存不存在：{path}；先运行 scripts/analyze_history_last_leg.py")
    return pd.read_csv(path, dtype=str)


def load_from_sheets(months: tuple[str, ...]) -> pd.DataFrame:
    from tongtool_order_cost.gsheets import client, gsheet2df

    gc = client()
    frames = []
    for month in months:
        sheet = f"通途订单{month}"
        print(f"读取: {sheet} / {worksheet_name(month)}")
        frames.append(prepare_order_rows(gsheet2df(gc, sheet, worksheet_name(month)), month))
    return pd.concat(frames, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EN 历史尾程模型导入文件生成（只读）")
    parser.add_argument("--cache", default=str(ROOT / "out" / "monthly_orders_full.csv.gz"))
    parser.add_argument("--from-sheets", action="store_true", help="忽略缓存，重新读取 Google Sheet")
    parser.add_argument("--months", nargs="+", default=list(DEFAULT_MONTHS))
    parser.add_argument("--train-end", default="", help="只用于训练的截止月份 YYYYMM；留空=全量")
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-months", type=int, default=2)
    parser.add_argument("--fee-column", default="去异常中位数", help="写入 avg_per_shipping_cost 的稳健估计列")
    parser.add_argument("--model-version", default="2026.09")
    parser.add_argument("--out", default=str(ROOT / "out" / "history_last_leg_model_import.csv"))
    parser.add_argument("--backtest", default=str(ROOT / "out" / "history_last_leg_backtest.xlsx"))
    args = parser.parse_args(argv)

    if args.from_sheets:
        rows = load_from_sheets(tuple(args.months))
    else:
        cached = load_cached(Path(args.cache))
        rows = pd.concat(
            [prepare_order_rows(frame, month) for month, frame in cached.groupby("月份")],
            ignore_index=True,
        ) if "月份" in cached.columns else cached

    observations = add_outlier_flags(build_package_observations(rows))
    training = observations
    if args.train_end.strip():
        training = observations[observations["月份"].astype(str) <= args.train_end.strip()]
    publishable = build_publishable_tiers(
        training, min_samples=args.min_samples, min_months=args.min_months
    )
    coverage = summarize_publish_coverage(observations, publishable)
    import_rows = build_import_rows(publishable, fee_column=args.fee_column)

    contract = ExportContract(
        model_version=args.model_version,
        data_source=f"tongtool monthly order sheets {args.months[0]}~{args.months[-1]} (non-FBA/self-fulfilled)",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        applicable_from=f"{args.months[0][:4]}-{args.months[0][4:]}-01",
        applicable_to="",
    )
    metrics = _load_backtest_metrics(Path(args.backtest))
    contract = ExportContract(**{**contract.__dict__, **metrics}) if metrics else contract

    out_path = write_import_rows(import_rows, args.out)
    parent_path = out_path.with_suffix(out_path.suffix + ".parent.json")
    parent_path.write_text(
        json.dumps(contract.as_parent_fields(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"导入行: {out_path}（{len(import_rows)} 行）")
    print(f"parent 契约: {parent_path}")
    print(coverage.to_string(index=False))
    print(import_rows.groupby("match_level")["model_key"].size().to_string())
    return 0


def _load_backtest_metrics(path: Path) -> dict[str, float]:
    """从回测工作簿取「渠道自适应」方案的指标，作为发布契约的一部分。"""
    if not path.exists():
        return {}
    try:
        summary = pd.read_excel(path, sheet_name="10_Holdout方案")
    except Exception:
        return {}
    preferred = summary[summary["方案"] == "渠道自适应"]
    if preferred.empty:
        return {}
    row = preferred.iloc[0]
    return {
        "backtest_mae": float(row.get("MAE") or 0),
        "backtest_mdae": float(row.get("MdAE") or 0),
        "backtest_bias": float(row.get("偏差") or 0),
        "backtest_p90": float(row.get("P90绝对误差") or 0),
        "backtest_coverage_percent": float(row.get("覆盖率%") or 0),
    }


if __name__ == "__main__":
    raise SystemExit(main())
