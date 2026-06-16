"""
投放层分析 — 匹配类型表现、关键词vs商品投放、顶部搜索份额、光环效应。
"""
import numpy as np
from advertise import load_data, save_json


def _safe_num(series):
    import pandas as pd
    return pd.to_numeric(series, errors="coerce")


def analyze(df):
    import pandas as pd
    df = df.copy()
    for col in ("spend", "sales_7d", "orders_7d", "units_7d", "clicks", "impressions",
                "acos", "roas", "ctr", "cpc", "top_search_is", "conversion_rate_7d",
                "advertised_sku_units_7d", "other_sku_units_7d",
                "advertised_sku_sales_7d", "other_sku_sales_7d"):
        if col in df.columns:
            df[col] = _safe_num(df[col])

    # ── 匹配类型表现 ──────────────────────────────────
    match_cols = ["match_type", "spend", "sales_7d", "orders_7d", "clicks",
                   "impressions", "ctr", "cpc"]
    mcols = [c for c in match_cols if c in df.columns and c != "match_type"]
    if "match_type" in df.columns:
        match = df.groupby("match_type")[mcols].sum()
        match["acos"] = match["spend"] / match["sales_7d"].replace(0, np.nan)
        match["roas"] = match["sales_7d"] / match["spend"].replace(0, np.nan)
        match["ctr_calc"] = match["clicks"] / match["impressions"].replace(0, np.nan)
        match["cpc_avg"] = match["spend"] / match["clicks"].replace(0, np.nan)
        match_list = match.reset_index().to_dict(orient="records")
        for r in match_list:
            for k in r:
                if isinstance(r[k], (np.floating,)):
                    r[k] = round(float(r[k]), 4)
                elif pd.isna(r[k]):
                    r[k] = None
    else:
        match_list = []

    # ── 投放对象 TOP/BOTTOM ────────────────────────────
    target_cols = ["targeting", "match_type", "campaign_name", "spend", "sales_7d",
                    "orders_7d", "clicks", "impressions", "acos", "roas", "ctr", "cpc",
                    "top_search_is"]
    tcols = [c for c in target_cols if c in df.columns]
    targeting_ranking = df[tcols].sort_values("spend", ascending=False)
    top_targets = targeting_ranking.head(20).to_dict(orient="records")
    # 最差投放: 有花费但零销售
    if "sales_7d" in df.columns:
        bottom = df[(df["spend"] > 1) & (df["sales_7d"].fillna(0) == 0)]
        bottom = bottom.sort_values("spend", ascending=False)
        bottom_targets = bottom[tcols].head(20).to_dict(orient="records")
    else:
        bottom_targets = []

    # ── 光环效应 ──────────────────────────────────────
    halo = {}
    if all(c in df.columns for c in ("advertised_sku_sales_7d", "other_sku_sales_7d")):
        adv_sales = df["advertised_sku_sales_7d"].sum()
        other_sales = df["other_sku_sales_7d"].sum()
        total = adv_sales + other_sales
        halo = {
            "advertised_sku_sales": round(float(adv_sales), 2),
            "other_sku_sales": round(float(other_sales), 2),
            "total": round(float(total), 2),
            "halo_ratio": round(float(other_sales / adv_sales), 4) if adv_sales > 0 else None,
        }
    if all(c in df.columns for c in ("advertised_sku_units_7d", "other_sku_units_7d")):
        adv_units = df["advertised_sku_units_7d"].sum()
        other_units = df["other_sku_units_7d"].sum()
        halo["advertised_sku_units"] = int(adv_units)
        halo["other_sku_units"] = int(other_units)

    # ── 汇总 ──────────────────────────────────────────
    total_spend = df["spend"].sum()
    total_sales = df["sales_7d"].sum()
    summary = {
        "target_count": len(df),
        "total_spend": round(float(total_spend), 2),
        "total_sales_7d": round(float(total_sales), 2),
        "total_orders_7d": int(df["orders_7d"].sum()) if "orders_7d" in df.columns else 0,
        "total_clicks": int(df["clicks"].sum()) if "clicks" in df.columns else 0,
        "total_impressions": int(df["impressions"].sum()) if "impressions" in df.columns else 0,
    }

    return {
        "summary": summary,
        "by_match_type": match_list,
        "top_targets": top_targets,
        "bottom_targets": bottom_targets,
        "halo_effect": halo,
    }


if __name__ == "__main__":
    reports = load_data()
    if "targeting" not in reports:
        print("错误: 未找到投放报告")
        exit(1)
    result = analyze(reports["targeting"])
    save_json(result, "targeting_analysis.json")
    print(f"\n投放分析:")
    print(f"  投放数: {result['summary']['target_count']}")
    print(f"  总花费: ${result['summary']['total_spend']:,.2f}")
    print(f"  匹配类型数: {len(result['by_match_type'])}")
    print(f"  零转化投放: {len(result['bottom_targets'])}个")
    if result["halo_effect"]:
        h = result["halo_effect"]
        print(f"  光环效应: 广告SKU ${h['advertised_sku_sales']:,.2f} + 其他SKU ${h['other_sku_sales']:,.2f}")
