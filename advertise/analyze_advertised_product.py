"""
Advertised Product analysis — ASIN-level profitability and efficiency ranking.
Answers the fundamental question: which products deserve ad spend?
"""
import os, sys
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols, round_record
from advertise.thresholds import ASIN_SPEND_REDLINE, ASIN_ZERO_SALE_DAYS


def analyze(df):
    df = df.copy()
    numeric_cols(df, ["spend", "sales", "orders", "clicks", "impressions",
                       "acos", "roas", "ctr", "cpc", "conversion_rate",
                       "same_sku_orders", "same_sku_sales", "same_sku_units",
                       "other_sku_orders", "other_sku_sales", "other_sku_units"])

    # ── Per-ASIN aggregation (sum across days) ─────────────────
    gcols = ["asin", "sku"]
    extra = ["campaign_name", "ad_group_name", "status"]
    gcols += [c for c in extra if c in df.columns]

    agg = {"spend": "sum", "sales": "sum", "orders": "sum",
           "clicks": "sum", "impressions": "sum",
           "same_sku_sales": "sum", "other_sku_sales": "sum",
           "same_sku_orders": "sum", "other_sku_orders": "sum",
           "same_sku_units": "sum", "other_sku_units": "sum"}
    available = {k: v for k, v in agg.items() if k in df.columns}
    by_asin = df.groupby(gcols).agg(available).reset_index()

    # Derived metrics
    by_asin["acos"] = by_asin["spend"] / by_asin["sales"].replace(0, np.nan)
    by_asin["roas"] = by_asin["sales"] / by_asin["spend"].replace(0, np.nan)
    by_asin["cpc"] = by_asin["spend"] / by_asin["clicks"].replace(0, np.nan)
    by_asin["ctr"] = by_asin["clicks"] / by_asin["impressions"].replace(0, np.nan)
    by_asin["cvr"] = by_asin["orders"] / by_asin["clicks"].replace(0, np.nan)

    # Total other-SKU sales = halo
    by_asin["total_sales_with_halo"] = by_asin["same_sku_sales"].fillna(0) + by_asin["other_sku_sales"].fillna(0)
    by_asin["blended_acos"] = by_asin["spend"] / by_asin["total_sales_with_halo"].replace(0, np.nan)
    by_asin["halo_ratio"] = by_asin["other_sku_sales"].fillna(0) / by_asin["same_sku_sales"].fillna(0).replace(0, np.nan)

    by_asin = by_asin.sort_values("spend", ascending=False)

    # ── Ranking ────────────────────────────────────────────────
    ranking_list = []
    for _, row in by_asin.iterrows():
        r = {
            "asin": str(row.get("asin", "")),
            "sku": str(row.get("sku", "")),
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
            "same_sku_sales": round(float(row.get("same_sku_sales", 0) or 0), 2),
            "other_sku_sales": round(float(row.get("other_sku_sales", 0) or 0), 2),
            "blended_acos": round(float(row["blended_acos"]), 4) if pd.notna(row["blended_acos"]) else None,
            "halo_ratio": round(float(row["halo_ratio"]), 2) if pd.notna(row["halo_ratio"]) and row["halo_ratio"] != float("inf") else None,
            "status": str(row.get("status", "")),
            "campaign_count": len(df[df["asin"] == row["asin"]]["campaign_name"].unique()) if "campaign_name" in df.columns else 0,
        }
        ranking_list.append(r)

    # ── 80/20 analysis ─────────────────────────────────────────
    total_spend = sum(r["spend"] for r in ranking_list)
    top_n = max(1, len(ranking_list) // 3)
    top_spend = sum(r["spend"] for r in ranking_list[:top_n])
    concentration = top_spend / total_spend if total_spend > 0 else 0

    # ── Flags ──────────────────────────────────────────────────
    excellent = [r for r in ranking_list if r["acos"] is not None and r["acos"] < 0.26 and r.get("orders", 0) > 0]
    poor = [r for r in ranking_list if r["acos"] is not None and r["acos"] > 0.66]
    zero_sale = [r for r in ranking_list if r["spend"] > ASIN_SPEND_REDLINE and r.get("orders", 0) == 0]
    low_data = [r for r in ranking_list if r["spend"] < ASIN_SPEND_REDLINE and r.get("orders", 0) == 0]

    # ── Summary ────────────────────────────────────────────────
    total_sales = sum(r["sales"] for r in ranking_list)
    total_orders = sum(r["orders"] for r in ranking_list)
    total_halo = sum(r["other_sku_sales"] for r in ranking_list)

    return {
        "summary": {
            "asin_count": len(ranking_list),
            "total_spend": round(total_spend, 2),
            "total_sales": round(total_sales, 2),
            "total_orders": int(total_orders),
            "total_halo_sales": round(total_halo, 2),
            "overall_acos": round(total_spend / total_sales, 4) if total_sales > 0 else None,
            "blended_acos_with_halo": round(total_spend / (total_sales + total_halo), 4) if (total_sales + total_halo) > 0 else None,
            "spend_concentration_top3rd": round(concentration, 4),
        },
        "ranking": ranking_list,
        "excellent": excellent,
        "poor": poor,
        "zero_sale_high_spend": zero_sale,
        "low_data": low_data,
        "thresholds": {
            "spend_redline": ASIN_SPEND_REDLINE,
            "zero_sale_days": ASIN_ZERO_SALE_DAYS,
            "excellent_acos": 0.26,
            "poor_acos": 0.66,
        },
    }


if __name__ == "__main__":
    reports = load_data()
    if "advertised_product" not in reports:
        print("错误: 未找到广告产品报告 (AdvertisedProduct)")
        sys.exit(1)
    result = analyze(reports["advertised_product"])
    save_json(result, "advertised_product_analysis.json")
    s = result["summary"]
    print(f"\n===== ASIN 广告效率分析 =====")
    print(f"  推广 ASIN 数: {s['asin_count']}")
    print(f"  总花费: ${s['total_spend']:,.2f}")
    print(f"  总销售额: ${s['total_sales']:,.2f}")
    print(f"  光环销售: ${s['total_halo_sales']:,.2f}")
    print(f"  直接ACOS: {s['overall_acos']:.2%}" if s['overall_acos'] else "")
    print(f"  混合ACOS(含光环): {s['blended_acos_with_halo']:.2%}" if s['blended_acos_with_halo'] else "")
    print(f"  花费集中度(Top 1/3): {s['spend_concentration_top3rd']:.0%}")
    print(f"  高效 ASIN: {len(result['excellent'])} 个")
    print(f"  低效 ASIN: {len(result['poor'])} 个")
    print(f"  零销售高花费: {len(result['zero_sale_high_spend'])} 个")
    for r in result["ranking"]:
        halo = f" 光环 {r['halo_ratio']}x" if r.get("halo_ratio") else ""
        print(f"  {r['sku'][:40]}: spend=${r['spend']:,.2f}  ACOS={r['acos']:.1%}" if r['acos'] else f"  {r['sku'][:40]}: N/A" + f"  sales=${r['sales']:,.2f}{halo}")
