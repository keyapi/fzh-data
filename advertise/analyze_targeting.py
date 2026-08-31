"""
Targeting analysis — match type performance, keyword vs ASIN targeting, halo effect.
"""
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols, round_record
from advertise.thresholds import TARGETING_MIN_SPEND, TARGETING_TOP_N


def analyze(df):
    df = df.copy()
    numeric_cols(df, ["spend", "sales", "orders", "clicks", "impressions",
                       "acos", "roas", "ctr", "cpc", "conversion_rate",
                       "same_sku_orders", "same_sku_sales", "same_sku_units",
                       "other_sku_orders", "other_sku_sales", "other_sku_units"])

    # ── Match type performance ────────────────────────────────
    if "match_type" in df.columns:
        gcols = ["match_type"]
        agg = {"spend": "sum", "sales": "sum", "orders": "sum",
               "clicks": "sum", "impressions": "sum"}
        available_a = {k: v for k, v in agg.items() if k in df.columns}
        mt = df.groupby(gcols).agg(available_a).reset_index()
        mt["acos"] = mt["spend"] / mt["sales"].replace(0, np.nan)
        mt["roas"] = mt["sales"] / mt["spend"].replace(0, np.nan)
        mt["ctr"] = mt["clicks"] / mt["impressions"].replace(0, np.nan)
        mt["cvr"] = mt["orders"] / mt["clicks"].replace(0, np.nan)
        mt["cpc"] = mt["spend"] / mt["clicks"].replace(0, np.nan)
        match_type_list = []
        for _, row in mt.iterrows():
            match_type_list.append({
                "match_type": str(row["match_type"]),
                "spend": round(float(row["spend"]), 2),
                "sales": round(float(row["sales"]), 2),
                "orders": int(row.get("orders", 0) or 0),
                "clicks": int(row.get("clicks", 0) or 0),
                "impressions": int(row.get("impressions", 0) or 0),
                "acos": round(float(row["acos"]), 4) if pd.notna(row["acos"]) else None,
                "roas": round(float(row["roas"]), 2) if pd.notna(row["roas"]) else None,
                "ctr": round(float(row["ctr"]), 4) if pd.notna(row["ctr"]) else None,
                "cvr": round(float(row["cvr"]), 4) if pd.notna(row["cvr"]) else None,
                "cpc": round(float(row["cpc"]), 4) if pd.notna(row["cpc"]) else None,
            })
    else:
        match_type_list = []

    # ── Top/bottom targets ────────────────────────────────────
    tcols = ["targeting", "match_type", "campaign_name", "ad_group_name",
             "spend", "sales", "orders", "clicks", "impressions",
             "acos", "roas", "ctr", "cpc", "conversion_rate",
             "same_sku_sales", "other_sku_sales"]
    available_t = [c for c in tcols if c in df.columns]
    targets = df[available_t].copy()
    targets = targets.sort_values("spend", ascending=False)

    top_list = []
    for _, row in targets.head(TARGETING_TOP_N).iterrows():
        r = {c: row[c] for c in available_t if c in row.index}
        round_record(r)
        top_list.append(r)

    bottom_list = []
    zero_conv = targets[(targets["spend"] > TARGETING_MIN_SPEND) & (targets["sales"].fillna(0) == 0)]
    zero_conv = zero_conv.sort_values("spend", ascending=False).head(TARGETING_TOP_N)
    for _, row in zero_conv.iterrows():
        r = {c: row[c] for c in available_t if c in row.index}
        round_record(r)
        bottom_list.append(r)

    # ── Halo effect (advertised SKU vs other SKU) ──────────────
    same_sku_sales = df["same_sku_sales"].sum() if "same_sku_sales" in df.columns else 0
    other_sku_sales = df["other_sku_sales"].sum() if "other_sku_sales" in df.columns else 0
    halo_ratio = other_sku_sales / same_sku_sales if same_sku_sales > 0 else None

    halo = {
        "same_sku_sales": round(float(same_sku_sales), 2),
        "other_sku_sales": round(float(other_sku_sales), 2),
        "total_attributed": round(float(same_sku_sales + other_sku_sales), 2),
        "halo_ratio": round(float(halo_ratio), 4) if halo_ratio is not None else None,
    }

    # ── Summary ────────────────────────────────────────────────
    total_spend = df["spend"].sum()
    total_sales = df["sales"].sum()

    return {
        "summary": {
            "total_spend": round(float(total_spend), 2),
            "total_sales": round(float(total_sales), 2),
            "overall_acos": round(float(total_spend / total_sales), 4) if total_sales > 0 else None,
            "target_count": len(df),
        },
        "match_type": match_type_list,
        "top_targets": top_list,
        "bottom_targets": bottom_list,
        "halo_effect": halo,
    }


if __name__ == "__main__":
    reports = load_data()
    if "targeting" not in reports:
        print("错误: 未找到投放报告")
        exit(1)
    result = analyze(reports["targeting"])
    save_json(result, "targeting_analysis.json")
    s = result["summary"]
    print(f"\n投放分析: 总花费 ${s['total_spend']:,.2f}  总销售额 ${s['total_sales']:,.2f}")
    if s['overall_acos']: print(f"  整体ACOS: {s['overall_acos']:.2%}")
    if result["match_type"]:
        print(f"\n匹配类型:")
        for m in result["match_type"]:
            print(f"  {m['match_type']}: ACOS={m['acos']:.1%}  ROAS={m['roas']:.1f}x  CVR={m['cvr']:.1%}" if m['cvr'] else f"  {m['match_type']}: {m['spend']}")
    h = result["halo_effect"]
    print(f"\n光环效应: SameSKU=${h['same_sku_sales']:,.2f} + OtherSKU=${h['other_sku_sales']:,.2f} = ${h['total_attributed']:,.2f} (光环比 {h['halo_ratio']:.2f}x)" if h['halo_ratio'] else "")
    print(f"\n零转化投放 (花费>${TARGETING_MIN_SPEND}, 0销售): {len(result['bottom_targets'])} 个")
