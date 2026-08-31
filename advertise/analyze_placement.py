"""
Placement analysis — Top of Search / Product Pages / Rest of Search comparison.
Supports both Console CSV (Chinese placement names) and API xlsx (English names).
"""
import os
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols, round_record
from advertise.thresholds import (
    PLACEMENT_ACOS_GOOD, PLACEMENT_CVR_GOOD,
    PLACEMENT_ACOS_BAD, PLACEMENT_CVR_BAD,
    PLACEMENT_MIN_SPEND, PLACEMENT_RAISE_PCT, PLACEMENT_LOWER_PCT,
)

# ── Placement classification (Console + API) ────────────────────────────
_PLACEMENT_MAP = {
    # Console export (legacy)
    "亚马逊站内的搜索结果顶部": "Top of Search",
    "亚马逊站内的商品页面": "Product Pages",
    "亚马逊站内搜索结果的其余位置": "Rest of Search",
    "亚马逊站外": "Off-Amazon",
    # API export (English)
    "Top of Search": "Top of Search",
    "Product Pages": "Product Pages",
    "Rest of Search": "Rest of Search",
    "Off Amazon": "Off-Amazon",
    # API export (Chinese — Sellfox API actual values)
    "搜索结果顶部(首页)": "Top of Search",
    "产品页面": "Product Pages",
    "搜索结果的其余位置": "Rest of Search",
    # API: Amazon Business placement
    "产品页面(企业购广告位)": "Product Pages (Business)",
    "Product Pages (Amazon Business)": "Product Pages (Business)",
}


def classify_placement(val):
    if val is None or pd.isna(val):
        return "Other"
    return _PLACEMENT_MAP.get(str(val).strip(), "Other")


def analyze(df):
    df = df.copy()
    numeric_cols(df, ["spend", "sales", "orders", "clicks", "impressions",
                       "acos", "roas", "ctr", "cpc", "conversion_rate",
                       "same_sku_orders", "same_sku_sales", "same_sku_units",
                       "other_sku_orders", "other_sku_sales", "other_sku_units"])

    if "placement" in df.columns:
        df["placement_category"] = df["placement"].apply(classify_placement)
    else:
        df["placement_category"] = "Unknown"

    # ── Summary by placement ─────────────────────────────────
    gcols = ["placement_category"]
    agg = {"spend": "sum", "sales": "sum", "orders": "sum",
           "clicks": "sum", "impressions": "sum",
           "same_sku_sales": "sum", "other_sku_sales": "sum",
           "same_sku_orders": "sum", "other_sku_orders": "sum"}
    available = {k: v for k, v in agg.items() if k in df.columns}
    pdf = df.groupby(gcols).agg(available).reset_index()
    pdf["acos"] = pdf["spend"] / pdf["sales"].replace(0, np.nan)
    pdf["roas"] = pdf["sales"] / pdf["spend"].replace(0, np.nan)
    pdf["cpc"] = pdf["spend"] / pdf["clicks"].replace(0, np.nan)
    pdf["ctr"] = pdf["clicks"] / pdf["impressions"].replace(0, np.nan)
    pdf["cvr"] = pdf["orders"] / pdf["clicks"].replace(0, np.nan) if "orders" in df.columns else None

    placements_list = []
    for _, row in pdf.iterrows():
        r = {
            "placement": row["placement_category"],
            "spend": round(float(row["spend"]), 2),
            "sales": round(float(row["sales"]), 2),
            "orders": int(row.get("orders", 0) or 0),
            "clicks": int(row.get("clicks", 0) or 0),
            "impressions": int(row.get("impressions", 0) or 0),
            "acos": round(float(row["acos"]), 4) if pd.notna(row["acos"]) else None,
            "roas": round(float(row["roas"]), 2) if pd.notna(row["roas"]) else None,
            "cpc": round(float(row["cpc"]), 4) if pd.notna(row["cpc"]) else None,
            "ctr": round(float(row["ctr"]), 4) if pd.notna(row["ctr"]) else None,
            "cvr": round(float(row["cvr"]), 4) if row.get("cvr") is not None and pd.notna(row["cvr"]) else None,
            "same_sku_sales": round(float(row.get("same_sku_sales", 0) or 0), 2),
            "other_sku_sales": round(float(row.get("other_sku_sales", 0) or 0), 2),
        }
        placements_list.append(r)

    total_spend = sum(p["spend"] for p in placements_list)
    total_sales = sum(p["sales"] for p in placements_list)

    # ── Detail rows (top 100 by spend) ───────────────────────
    detail_cols = ["placement_category", "campaign_name", "spend", "sales", "orders",
                   "clicks", "impressions", "acos", "roas", "cpc", "ctr"]
    available_d = [c for c in detail_cols if c in df.columns]
    detail = df[available_d].sort_values("spend", ascending=False).head(100)
    detail_list = detail.to_dict(orient="records")
    for r in detail_list:
        round_record(r)

    # ── Recommendations ──────────────────────────────────────
    recommendations = []
    for p in placements_list:
        acos = p.get("acos")
        cvr = p.get("cvr")
        sp = p.get("spend", 0)
        nm = p["placement"]
        if acos is None or cvr is None or sp < PLACEMENT_MIN_SPEND:
            recommendations.append({"placement": nm, "action": "insufficient_data",
                                    "detail": f"花费 ${sp:,.2f} 不足以做出价判断"})
        elif acos < PLACEMENT_ACOS_GOOD and cvr > PLACEMENT_CVR_GOOD:
            recommendations.append({"placement": nm, "action": "raise_bid",
                                    "detail": f"ACOS {acos:.1%}, CVR {cvr:.1%} — "
                                    f"建议提高出价 {PLACEMENT_RAISE_PCT[0]}-{PLACEMENT_RAISE_PCT[1]}%"})
        elif acos > PLACEMENT_ACOS_BAD:
            recommendations.append({"placement": nm, "action": "lower_bid",
                                    "detail": f"ACOS {acos:.1%} — "
                                    f"建议降低出价 {PLACEMENT_LOWER_PCT[0]}-{PLACEMENT_LOWER_PCT[1]}% 或暂停"})
        elif cvr < PLACEMENT_CVR_BAD and sp > PLACEMENT_MIN_SPEND:
            recommendations.append({"placement": nm, "action": "check_creative",
                                    "detail": f"CVR {cvr:.1%} 偏低 — 检查广告素材与广告位的匹配度"})
        else:
            recommendations.append({"placement": nm, "action": "maintain",
                                    "detail": f"ACOS {acos:.1%}, CVR {cvr:.1%} — 维持当前出价, 继续观察"})

    return {
        "summary": {"total_spend": round(total_spend, 2),
                     "total_sales": round(total_sales, 2),
                     "overall_acos": round(total_spend / total_sales, 4) if total_sales > 0 else None,
                     "placement_count": len(placements_list)},
        "placements": placements_list,
        "detail": detail_list,
        "recommendations": recommendations,
    }


if __name__ == "__main__":
    reports = load_data()
    if "placement" not in reports:
        print("错误: 未找到广告位报告")
        exit(1)
    result = analyze(reports["placement"])
    save_json(result, "placement_analysis.json")
    s = result["summary"]
    print(f"\n广告位分析: 总花费 ${s['total_spend']:,.2f}  总销售额 ${s['total_sales']:,.2f}")
    if s['overall_acos']:
        print(f"  整体ACOS: {s['overall_acos']:.2%}")
    for p in result["placements"]:
        a = f"ACOS={p['acos']:.1%}" if p['acos'] else ""
        print(f"  {p['placement']}: spend=${p['spend']:,.2f}  sales=${p['sales']:,.2f}  {a}")
    for r in result["recommendations"]:
        print(f"  → {r['placement']}: {r['action']}")
