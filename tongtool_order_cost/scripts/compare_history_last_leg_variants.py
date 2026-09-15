# -*- coding: utf-8 -*-
"""多方案费率模型对比：严格时间 Holdout + 真实月初工件，输出对比工作簿。

用法：
    uv run python scripts/compare_history_last_leg_variants.py
    uv run python scripts/compare_history_last_leg_variants.py --from-sheets   # 重新读 gsheet

只读：不写回 Google Sheet、不动 HLF0001、不做 ERPNext 写入。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (  # noqa: E402
    PUBLISH_LEVELS,
    add_outlier_flags,
    build_package_observations,
    legacy_predict_fee_faithful,
    load_legacy_items,
    normalize_channel,
    normalize_postal,
    normalize_warehouse,
    prepare_order_rows,
)
from tongtool_order_cost.model_variants import (  # noqa: E402
    MODERN_LEVELS,
    VARIANTS,
    _predict_baseline,
    build_variant_tiers,
    error_metrics,
    predict_with_variant,
)

DEFAULT_MONTHS = ("202511", "202512", "202601", "202602", "202603", "202604", "202605", "202606")

# 真实月初工件：EN 输出（含老方式预估）与后补真实尾程
ARTIFACTS = {
    "202605": (
        "通途非FBA订单202605 EN估尾程 tongtool_order_costs_2026-06-02_13-49-05.707983.xlsx",
        "只用尾程 通途非FBA订单202605 202607081128.xlsx",
    ),
    "202606": (
        "通途非FBA订单202606 只用EN预估尾程 tongtool_order_costs_2026-07-06_11-42-29.961362.xlsx",
        "只用尾程 通途非FBA订单202606 202608061025.xlsx",
    ),
}
ARTIFACT_DIRS = (
    Path(r"D:/Work/王忠于/成本核算"),
    Path(r"D:/文件存档/成本核算"),
)


def worksheet_name(month: str) -> str:
    return f"{month[:4]}年{int(month[4:])}月订单"


def load_orders(args) -> pd.DataFrame:
    if args.from_sheets:
        from tongtool_order_cost.gsheets import client, gsheet2df

        gc = client()
        frames = []
        for month in args.months:
            sheet = f"通途订单{month}"
            print(f"读取: {sheet} / {worksheet_name(month)}")
            frames.append(prepare_order_rows(gsheet2df(gc, sheet, worksheet_name(month)), month))
        return pd.concat(frames, ignore_index=True)
    cached = pd.read_csv(args.cache, dtype=str)
    return pd.concat(
        [prepare_order_rows(frame, month) for month, frame in cached.groupby("月份")],
        ignore_index=True,
    )


def find_artifact(name: str) -> Path | None:
    for folder in ARTIFACT_DIRS:
        path = folder / name
        if path.exists():
            return path
    return None


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return pd.Series(0.0, index=frame.index)


def load_real_artifact(month: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """返回（月初包裹特征+老方式预估, 实际整包费用）。找不到工件则返回 None。"""
    names = ARTIFACTS.get(month)
    if not names:
        return None
    en_path, late_path = (find_artifact(n) for n in names)
    if not en_path or not late_path:
        print(f"[跳过] {month} 工件缺失：{en_path=} {late_path=}")
        return None

    en = pd.read_excel(en_path)
    en["_pk"] = en["包裹号"].astype(str).str.strip()
    en["_sku"] = en["通途SKU"].astype(str).str.strip()
    en["_qty"] = numeric(en, "发货数量")
    en["_w_kg"] = numeric(en, "通途重量") / 1000
    en["_est"] = numeric(en, "历史预估尾程费用")
    en["_nation"] = en["国家/地区"].astype(str).str.strip().str.upper()

    pkg = en.groupby("_pk").agg(
        国家=("_nation", "first"),
        仓库=("发货仓库", "first"),
        渠道=("渠道", "first"),
        邮寄方式=("邮寄方式", "first"),
        邮编=("邮编", "first"),
        重量kg=("_w_kg", "first"),
        件数=("_qty", "sum"),
        SKU数=("_sku", "nunique"),
        老方式整包预估=("_est", "sum"),
    ).reset_index()
    sku_unique = en.groupby("_pk")["_sku"].unique()
    pkg["通途SKU"] = [u[0] if len(u) == 1 else "" for u in pkg["_pk"].map(sku_unique)]
    pkg["标准仓库"] = pkg["仓库"].map(normalize_warehouse)
    pkg["标准渠道"] = [normalize_channel(c, m) for c, m in zip(pkg["渠道"], pkg["邮寄方式"])]
    pkg["美国ZIP3"] = [normalize_postal(p, n)[1] for p, n in zip(pkg["邮编"], pkg["国家"])]
    pkg["目的地邮编首位"] = pkg["美国ZIP3"].astype("string").str[0].fillna("")
    pkg["观察重量阶梯"] = pkg["重量kg"].map(
        lambda w: "" if not (w > 0) else f"({max(0, int(math.ceil(w)) - 1)},{int(math.ceil(w))}]kg"
    )
    pkg["观察重量_kg"] = pkg["重量kg"]
    pkg["月份"] = month

    late = pd.read_excel(late_path)
    late["_pk"] = late["包裹号"].astype(str).str.strip()
    actual = late.groupby("_pk").agg(
        包裹总运费=("包裹总运费", "max"),
        物流商运费和=("物流商运费", "sum"),
        通途运费和=("通途运费", "sum"),
    ).reset_index()
    actual["实际整包"] = actual["物流商运费和"]
    for fallback in ("包裹总运费", "通途运费和"):
        empty = actual["实际整包"] <= 0
        actual.loc[empty, "实际整包"] = actual.loc[empty, fallback]
    actual["月份"] = month
    return pkg, actual[["_pk", "实际整包", "月份"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="历史尾程模型多变体对比（只读）")
    parser.add_argument("--cache", default=str(ROOT / "out" / "monthly_orders_full.csv.gz"))
    parser.add_argument("--from-sheets", action="store_true")
    parser.add_argument("--months", nargs="+", default=list(DEFAULT_MONTHS))
    parser.add_argument("--train-end", default="202604")
    parser.add_argument("--validation-start", default="202605")
    parser.add_argument("--out", default=str(ROOT / "out" / "history_last_leg_variants.xlsx"))
    args = parser.parse_args(argv)

    rows = load_orders(args)
    observations = add_outlier_flags(build_package_observations(rows))
    legacy = load_legacy_items(ROOT / "out" / "hlf0001_items.csv.gz")

    eligible = observations[observations["建模状态"] == "可建模"].copy()
    training = eligible[eligible["月份"].astype(str) <= args.train_end]
    validation = eligible[eligible["月份"].astype(str) >= args.validation_start].copy()
    print(f"训练包裹 {len(training)}  验证包裹 {len(validation)}")

    holdout_rows = []
    validation["HLF0001"] = validation.apply(
        lambda r: legacy_predict_fee_faithful(legacy, r["国家"], r["通途SKU"], r["观察重量_kg"])[0],
        axis=1,
    )
    holdout_rows.append({"变体": "HLF0001", "范围": "Holdout 总体",
                         **error_metrics(validation["观察费用"], validation["HLF0001"])})

    fitted: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for variant in VARIANTS:
        name = variant["name"]
        baseline = name == "V0_基线"
        tiers, meta = build_variant_tiers(
            training,
            levels=PUBLISH_LEVELS if baseline else MODERN_LEVELS,
            exclusive=variant.get("exclusive", baseline),
            credibility=variant.get("credibility", False),
            drop_flat_months=variant.get("drop_flat_months", False),
            min_samples=variant.get("min_samples", 30),
            min_months=variant.get("min_months", 2),
        )
        prediction = (
            _predict_baseline(validation, tiers) if baseline
            else predict_with_variant(validation, tiers, scheme=variant.get("scheme", "adaptive"))
        )
        holdout_rows.append({"变体": name, "范围": "Holdout 总体",
                             **error_metrics(validation["观察费用"], prediction)})
        fitted[name] = (tiers, meta)
        print(f"  {name}: 层数 {len(tiers)}  "
              f"MAE {error_metrics(validation['观察费用'], prediction).get('MAE')}")

    # 分组：仓库×渠道、重量档、目的地首位
    group_frames = []
    for cols, label in ((("国家", "标准仓库", "标准渠道"), "仓库渠道"),
                        (("国家", "标准仓库", "标准渠道", "观察重量阶梯"), "重量档"),
                        (("国家", "标准仓库", "标准渠道", "目的地邮编首位"), "目的地首位")):
        records = []
        for key, group in validation.groupby(list(cols), dropna=False):
            key = key if isinstance(key, tuple) else (key,)
            dims = dict(zip(cols, key))
            records.append({**dims, "变体": "HLF0001",
                            **error_metrics(group["观察费用"], group["HLF0001"])})
            for variant in VARIANTS:
                name = variant["name"]
                tiers, _ = fitted[name]
                pred = (
                    _predict_baseline(group, tiers) if name == "V0_基线"
                    else predict_with_variant(group, tiers, scheme=variant.get("scheme", "adaptive"))
                )
                records.append({**dims, "变体": name, **error_metrics(group["观察费用"], pred)})
        group_frames.append((f"2{len(group_frames) + 1}_{label}", pd.DataFrame(records)))

    # 真实月初工件
    artifact_summary = []
    artifact_details = []
    for month in args.months:
        loaded = load_real_artifact(month)
        if not loaded:
            continue
        pkg, actual = loaded
        merged = pkg.merge(actual, on=["_pk", "月份"], how="inner")
        merged = merged[(merged["实际整包"] > 0) & (merged["老方式整包预估"] > 0)].copy()
        if merged.empty:
            continue
        merged["观察费用"] = merged["实际整包"]
        artifact_summary.append({"变体": "老方式_月初", "范围": f"{month} 月初缺失",
                                 **error_metrics(merged["观察费用"], merged["老方式整包预估"])})
        for variant in VARIANTS:
            name = variant["name"]
            tiers, _ = fitted[name]
            pred = (
                _predict_baseline(merged, tiers) if name == "V0_基线"
                else predict_with_variant(merged, tiers, scheme=variant.get("scheme", "adaptive"))
            )
            merged[f"预测_{name}"] = pred
            artifact_summary.append({"变体": name, "范围": f"{month} 月初缺失",
                                     **error_metrics(merged["观察费用"], pred)})
        merged["月份"] = month
        artifact_details.append(merged)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame(holdout_rows).to_excel(writer, sheet_name="00_Holdout总体", index=False)
        pd.DataFrame(artifact_summary).to_excel(writer, sheet_name="01_月初工件对比", index=False)
        for sheet_name, frame in group_frames:
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
        if artifact_details:
            pd.concat(artifact_details, ignore_index=True).to_excel(
                writer, sheet_name="30_月初工件明细", index=False
            )
        meta_rows = [{"变体": name, "层级": level, "可信度k": k}
                     for name, (_, meta) in fitted.items() for level, k in meta.items()]
        if meta_rows:
            pd.DataFrame(meta_rows).to_excel(writer, sheet_name="40_可信度k", index=False)

    print(f"\n输出: {out_path}")
    print("\n== 严格时间 Holdout ==")
    print(pd.DataFrame(holdout_rows).to_string(index=False))
    if artifact_summary:
        print("\n== 真实月初工件 ==")
        print(pd.DataFrame(artifact_summary).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
