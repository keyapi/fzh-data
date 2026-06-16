"""
广告位层分析 — Top of Search / Product Pages / Rest of Search 三位效率对比。
"""
import numpy as np
from advertise import load_data, save_json


def _safe_num(series):
    import pandas as pd
    return pd.to_numeric(series, errors="coerce")


# 广告位中文 → 分类映射
PLACEMENT_CATEGORY = {
    "亚马逊站内的搜索结果顶部": "Top of Search",
    "亚马逊站内的商品页面": "Product Pages",
    "亚马逊站内搜索结果的其余位置": "Rest of Search",
    "亚马逊站外": "站外",
}


def classify_placement(name):
    if not isinstance(name, str):
        return "其他"
    for cn, en in PLACEMENT_CATEGORY.items():
        if cn in name or cn == name:
            return en
    if "站外" in name:
        return "站外"
    if "顶部" in name:
        return "Top of Search"
    if "商品页" in name:
        return "Product Pages"
    if "其余" in name:
        return "Rest of Search"
    return "其他"


def analyze(df):
    import pandas as pd
    df = df.copy()
    for col in ("spend", "sales_7d", "orders_7d", "units_7d", "clicks", "impressions",
                "acos", "roas", "ctr", "cpc"):
        if col in df.columns:
            df[col] = _safe_num(df[col])

    # 广告位分类
    if "placement" in df.columns:
        df["placement_category"] = df["placement"].apply(classify_placement)
    else:
        df["placement_category"] = "未知"

    # ── 按广告位聚合 ──────────────────────────────────
    agg_cols = ["spend", "sales_7d", "orders_7d", "units_7d", "clicks", "impressions"]
    acols = [c for c in agg_cols if c in df.columns]
    placement_agg = df.groupby("placement_category")[acols].sum()
    placement_agg["acos"] = placement_agg["spend"] / placement_agg["sales_7d"].replace(0, np.nan)
    placement_agg["roas"] = placement_agg["sales_7d"] / placement_agg["spend"].replace(0, np.nan)
    placement_agg["ctr"] = placement_agg["clicks"] / placement_agg["impressions"].replace(0, np.nan)
    placement_agg["cpc"] = placement_agg["spend"] / placement_agg["clicks"].replace(0, np.nan)
    # 转化率
    placement_agg["cvr"] = placement_agg["orders_7d"] / placement_agg["clicks"].replace(0, np.nan)

    placement_list = []
    for cat in ("Top of Search", "Product Pages", "Rest of Search", "站外", "其他"):
        if cat in placement_agg.index:
            row = placement_agg.loc[cat].to_dict()
            row["placement"] = cat
            for k, v in row.items():
                if isinstance(v, (np.floating,)):
                    row[k] = round(float(v), 4)
                elif pd.isna(v):
                    row[k] = None
            placement_list.append(row)

    # 预算占比
    total_spend = df["spend"].sum()
    for r in placement_list:
        r["spend_share"] = round(r["spend"] / total_spend, 4) if total_spend > 0 else 0

    # ── 逐活动×广告位明细 ─────────────────────────────
    detail_cols = ["campaign_name", "placement_category", "spend", "sales_7d",
                    "orders_7d", "clicks", "impressions", "acos", "roas", "ctr", "cpc"]
    dcols = [c for c in detail_cols if c in df.columns]
    detail = df[dcols].sort_values("spend", ascending=False)
    detail_list = detail.head(100).to_dict(orient="records")
    for r in detail_list:
        for k in r:
            if isinstance(r[k], (np.floating,)):
                r[k] = round(float(r[k]), 4)
            elif pd.isna(r[k]):
                r[k] = None

    # ── 出价调整建议 ──────────────────────────────────
    recommendations = []
    for r in placement_list:
        rec = {"placement": r["placement"]}
        if r.get("acos") is not None and r.get("cvr") is not None:
            if r["acos"] < 0.20 and r["cvr"] > 0.05:
                rec["action"] = "建议提高出价 10-20%，扩大优质流量"
            elif r["acos"] > 0.40:
                rec["action"] = "建议降低出价 15-30% 或暂停，ACOS 过高"
            elif r["cvr"] < 0.02 and r["spend"] > 100:
                rec["action"] = "转化率低，检查广告位素材相关性"
            else:
                rec["action"] = "维持当前出价，继续观察"
        recommendations.append(rec)

    # ── 汇总 ──────────────────────────────────────────
    summary = {
        "placement_categories": len(placement_list),
        "total_spend": round(float(total_spend), 2),
        "total_sales_7d": round(float(df["sales_7d"].sum()), 2),
        "total_orders_7d": int(df["orders_7d"].sum()) if "orders_7d" in df.columns else 0,
        "total_clicks": int(df["clicks"].sum()) if "clicks" in df.columns else 0,
        "total_impressions": int(df["impressions"].sum()) if "impressions" in df.columns else 0,
    }

    return {
        "summary": summary,
        "placements": placement_list,
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
    print(f"\n广告位分析:")
    print(f"  广告位类别: {result['summary']['placement_categories']}")
    for p in result["placements"]:
        print(f"  {p['placement']}: 花费${p['spend']:,.2f} | ACOS {p.get('acos',0):.2%} | "
              f"CTR {p.get('ctr',0):.2%} | CVR {p.get('cvr',0):.2%}")
    for rec in result["recommendations"]:
        print(f"  → {rec['placement']}: {rec['action']}")
