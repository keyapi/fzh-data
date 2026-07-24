"""
Purchased Item analysis — brand halo effect and cross-sell attribution.
Highest ROI analysis: 13 rows of data that transform ad ROI understanding.
"""
import os, sys
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols

# ── Config ──────────────────────────────────────────────────────────────
GATEWAY_OTHER_SKU_RATIO = 0.50  # OtherSKU sales > 50% of total → potential Gateway ASIN


def analyze(df):
    df = df.copy()
    numeric_cols(df, ["purchased_units", "purchased_sales"])

    # Each row shows: advertised_asin → purchased_asin with purchased units/sales
    # Key insight: ASIN A's ad brought sales for ASIN B — that's brand halo

    # ── Blended (halo-inclusive) metrics ──────────────────────
    total_purchased_sales = df["purchased_sales"].sum()
    total_purchased_units = df["purchased_units"].sum()

    # ── Per advertised ASIN aggregation ───────────────────────
    gcols = ["advertised_asin", "advertised_sku", "campaign_name"]
    gcols = [c for c in gcols if c in df.columns]
    by_asin = df.groupby(gcols).agg(
        purchased_units=("purchased_units", "sum"),
        purchased_sales=("purchased_sales", "sum"),
        purchase_events=("purchased_sales", "count"),
    ).reset_index().sort_values("purchased_sales", ascending=False)

    asin_list = []
    for _, row in by_asin.iterrows():
        asin_list.append({
            "advertised_asin": str(row.get("advertised_asin", "")),
            "advertised_sku": str(row.get("advertised_sku", "")),
            "purchased_units": int(row["purchased_units"]),
            "purchased_sales": round(float(row["purchased_sales"]), 2),
            "purchase_events": int(row["purchase_events"]),
        })

    # ── Cross-sell mapping (advertised ASIN → purchased ASIN) ──
    map_cols = ["advertised_asin", "purchased_asin", "campaign_name", "targeting", "match_type"]
    map_cols = [c for c in map_cols if c in df.columns]
    cross_sell = df[map_cols + ["purchased_units", "purchased_sales"]].copy()
    cross_sell = cross_sell.sort_values("purchased_sales", ascending=False)
    cross_list = []
    for _, row in cross_sell.iterrows():
        cross_list.append({
            "advertised_asin": str(row.get("advertised_asin", "")),
            "purchased_asin": str(row.get("purchased_asin", "")),
            "campaign_name": str(row.get("campaign_name", "")),
            "targeting": str(row.get("targeting", "")),
            "match_type": str(row.get("match_type", "")),
            "units": int(row["purchased_units"]),
            "sales": round(float(row["purchased_sales"]), 2),
        })

    # ── Gateway ASIN detection ────────────────────────────────
    # An ASIN is a "Gateway" if its other-SKU sales from PurchasedItem
    # exceeds a significant portion of total halo sales OR has >1 cross-sell ASIN
    gateways = []
    for a in asin_list:
        if a["purchase_events"] >= 2:  # sold at least 2 other SKUs
            gateways.append(a)

    # ── Grand summary ─────────────────────────────────────────
    unique_advertised = len(by_asin)
    unique_purchased = df["purchased_asin"].nunique() if "purchased_asin" in df.columns else 0

    return {
        "summary": {
            "total_purchased_sales": round(float(total_purchased_sales), 2),
            "total_purchased_units": int(total_purchased_units),
            "unique_advertised_asins": unique_advertised,
            "unique_purchased_asins": int(unique_purchased),
            "total_rows": len(df),
            "gateway_candidates": len(gateways),
        },
        "by_advertised_asin": asin_list,
        "cross_sell_map": cross_list,
        "gateway_asins": gateways,
    }


if __name__ == "__main__":
    reports = load_data()
    if "purchased_item" not in reports:
        print("错误: 未找到已购产品报告 (PurchasedItem)")
        sys.exit(1)

    result = analyze(reports["purchased_item"])
    save_json(result, "purchased_item_analysis.json")
    s = result["summary"]

    print(f"\n===== 品牌光环分析 (Purchased Item) =====")
    print(f"  已购产品行数: {s['total_rows']}")
    print(f"  广告 ASIN 数: {s['unique_advertised_asins']}")
    print(f"  被购买 ASIN 数: {s['unique_purchased_asins']}")
    print(f"  其他SKU总销售: ${s['total_purchased_sales']:,.2f}")
    print(f"  其他SKU总销量: {s['total_purchased_units']} 件")
    print(f"  潜在Gateway ASIN: {s['gateway_candidates']} 个")

    if result["gateway_asins"]:
        print(f"\n  Gateway ASIN 清单:")
        for g in result["gateway_asins"]:
            print(f"    {g['advertised_sku']} ({g['advertised_asin']}): "
                  f"拉动 {g['purchased_units']} 件 ${g['purchased_sales']:,.2f} "
                  f"({g['purchase_events']} 种其他产品)")

    print(f"\n  交叉销售 Top 5:")
    for c in result["cross_sell_map"][:5]:
        print(f"    {c['advertised_asin']} → {c['purchased_asin']}: "
              f"{c['units']} 件 ${c['sales']:,.2f} (via {c['campaign_name']})")
