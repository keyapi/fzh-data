# -*- coding: utf-8 -*-
"""整包价分摊验证：多明细包裹上三种口径的订单级合计对比（只读）。

用途：证明「按整包计费重量查一次 + 按行权重分摊」在**多明细包裹**上的必要性，
并给出可独立复算的数字（不依赖任何一次性分析脚本）。

三种口径：
- 老口径：文件里记录的 `历史预估尾程费用` 逐行求和（即历史上的 `单件价 × 发货数量`）
- 逐行写整包价：对每一行用它自己的 SKU/重量查一次再求和（去掉乘法但不分摊）
- 按整包分摊：用包裹计费重量（`通途重量`）查**一次**，即本仓库的实现口径

用法（两个工件路径由调用方提供，仓库不记录个人目录）：
    uv run python tongtool_order_cost/scripts/verify_package_allocation.py \
        --en-output "<月初 EN 预估输出 xlsx>" \
        --late "<事后补上真实尾程的导出 xlsx>" \
        --cache tongtool_order_cost/out/monthly_orders_full.csv.gz
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (  # noqa: E402
    add_outlier_flags,
    build_package_observations,
    normalize_channel,
    normalize_postal,
    normalize_warehouse,
    prepare_order_rows,
)
from tongtool_order_cost.model_variants import (  # noqa: E402
    build_recommended_tiers,
    predict_with_variant,
)


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return pd.Series(0.0, index=frame.index)


def weight_tier(weight_kg: float) -> str:
    if not weight_kg or weight_kg <= 0:
        return ""
    upper = int(np.ceil(weight_kg))
    return f"({max(0, upper - 1)},{upper}]kg"


def package_features(month_start: pd.DataFrame) -> pd.DataFrame:
    """把月初文件按包裹聚合成发布层要求的维度。"""
    frame = month_start.copy()
    frame["_pk"] = frame["包裹号"].astype(str).str.strip()
    frame["_qty"] = numeric(frame, "发货数量")
    frame["_pkg_kg"] = numeric(frame, "通途重量") / 1000
    frame["_row_weight"] = numeric(frame, "商品重量")
    frame["_nation"] = frame["国家/地区"].astype(str).str.strip().str.upper()

    grouped = frame.groupby("_pk").agg(
        国家=("_nation", "first"),
        仓库=("发货仓库", "first"),
        渠道=("渠道", "first"),
        邮寄方式=("邮寄方式", "first"),
        邮编=("邮编", "first"),
        重量kg=("_pkg_kg", "first"),
        行数=("_pk", "size"),
        件数=("_qty", "sum"),
        老口径=("历史预估尾程费用", lambda s: float(numeric(pd.DataFrame({"v": s}), "v").sum())),
        行重量=("_row_weight", lambda s: list(s)),
    ).reset_index()
    grouped["通途SKU"] = [
        values.pop() if len(values) == 1 else ""
        for values in (
            {str(v).strip() for v in frame.loc[frame["_pk"] == pk, "通途SKU"]}
            for pk in grouped["_pk"]
        )
    ]
    grouped["标准仓库"] = grouped["仓库"].map(normalize_warehouse)
    grouped["标准渠道"] = [
        normalize_channel(channel, method)
        for channel, method in zip(grouped["渠道"], grouped["邮寄方式"])
    ]
    grouped["美国ZIP3"] = [
        normalize_postal(postal, nation)[1]
        for postal, nation in zip(grouped["邮编"], grouped["国家"])
    ]
    grouped["目的地邮编首位"] = grouped["美国ZIP3"].astype("string").str[0].fillna("")
    grouped["观察重量阶梯"] = grouped["重量kg"].map(weight_tier)
    grouped["观察重量_kg"] = grouped["重量kg"]
    return grouped


def per_row_total(row: pd.DataFrame, tiers: pd.DataFrame) -> float:
    """逐行写整包价：每行用它自己的（逐件）重量查一次再求和。"""
    total = 0.0
    for row_weight in row["行重量"]:
        unit_kg = float(row_weight or 0) / 1000
        single = pd.DataFrame([{
            "国家": row["国家"], "标准仓库": row["标准仓库"], "标准渠道": row["标准渠道"],
            "通途SKU": row["通途SKU"], "美国ZIP3": row["美国ZIP3"],
            "目的地邮编首位": row["目的地邮编首位"], "观察重量阶梯": weight_tier(unit_kg),
        }])
        total += float(predict_with_variant(single, tiers, scheme="zone_first").iloc[0])
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="整包价分摊验证（只读）")
    parser.add_argument("--en-output", required=True, help="月初 EN 预估输出 xlsx")
    parser.add_argument("--late", required=True, help="事后补上真实尾程的导出 xlsx")
    parser.add_argument("--cache", default=str(ROOT / "out" / "monthly_orders_full.csv.gz"))
    parser.add_argument("--train-end", default="202604", help="只用于训练的截止月份")
    args = parser.parse_args(argv)

    raw = pd.read_csv(args.cache, dtype=str)
    rows = pd.concat(
        [prepare_order_rows(frame, month) for month, frame in raw.groupby("月份")],
        ignore_index=True,
    )
    observations = add_outlier_flags(build_package_observations(rows))
    training = observations[
        (observations["建模状态"] == "可建模")
        & (observations["月份"].astype(str) <= args.train_end)
    ]
    tiers = build_recommended_tiers(training)
    print(f"训练包裹 {len(training)}  发布层 {len(tiers)}")

    month_start = pd.read_excel(args.en_output)
    late = pd.read_excel(args.late)
    packages = package_features(month_start)

    late["_pk"] = late["包裹号"].astype(str).str.strip()
    actual = late.groupby("_pk").agg(
        包裹总运费=("包裹总运费", "max"),
        物流商运费和=("物流商运费", "sum"),
        通途运费和=("通途运费", "sum"),
    ).reset_index()
    actual["实际"] = actual["物流商运费和"]
    for fallback in ("包裹总运费", "通途运费和"):
        empty = actual["实际"] <= 0
        actual.loc[empty, "实际"] = actual.loc[empty, fallback]
    packages = packages.merge(actual[["_pk", "实际"]], on="_pk", how="left")

    multi = packages[packages["行数"] > 1].copy()
    multi["按整包分摊"] = predict_with_variant(multi, tiers, scheme="zone_first")
    multi["逐行写整包价"] = multi.apply(lambda row: per_row_total(row, tiers), axis=1)
    usable = multi[multi["实际"] > 0]

    print(f"\n多明细行包裹 {len(multi)} 个（有实际费用的 {len(usable)} 个）"
          f"  行数分布 {usable['行数'].value_counts().sort_index().to_dict()}")
    print("\n== 订单级合计对比 ==")
    base = usable["实际"].sum()
    for label, column in (("老口径 ×件数", "老口径"),
                          ("逐行写整包价（不分摊）", "逐行写整包价"),
                          ("按整包分摊（本仓库实现）", "按整包分摊"),
                          ("实际整包", "实际")):
        value = usable[column].sum()
        delta = (value / base - 1) * 100 if base else float("nan")
        print(f"  {label:24s} {value:11,.2f}   相对实际 {delta:+7.1f}%")
    print("\n== 抽样 ==")
    print(usable[["_pk", "行数", "件数", "老口径", "逐行写整包价", "按整包分摊", "实际"]]
          .head(6).round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
