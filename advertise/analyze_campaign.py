"""
Campaign-level analysis — ACOS/ROAS ranking, budget utilization, portfolio aggregation.
"""
import os
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols, round_record
from advertise.thresholds import (
    HIGH_ACOS_THRESHOLD, LOW_ROAS_THRESHOLD, WINNER_ACOS_THRESHOLD,
    BUDGET_UTILIZATION_IDEAL_MIN, BUDGET_UTILIZATION_IDEAL_MAX,
)


def analyze(df):
    df = df.copy()
    numeric_cols(df, ["spend", "sales", "orders", "clicks", "impressions",
                       "acos", "roas", "ctr", "cpc",
                       "same_sku_sales", "other_sku_sales", "budget"])

    # Derived ACOS/ROAS if missing
    if "acos" not in df.columns or df["acos"].isna().all():
        mask = df["sales"].notna() & (df["sales"] > 0)
        df.loc[mask, "acos"] = df.loc[mask, "spend"] / df.loc[mask, "sales"]
    if "roas" not in df.columns or df["roas"].isna().all():
        mask = df["spend"].notna() & (df["spend"] > 0)
        df.loc[mask, "roas"] = df.loc[mask, "sales"] / df.loc[mask, "spend"]

    total_spend = df["spend"].sum()
    total_sales = df["sales"].sum()

    # ── Summary ────────────────────────────────────────────────
    summary = {
        "total_spend": round(float(total_spend), 2),
        "total_sales": round(float(total_sales), 2),
        "total_orders": int(df["orders"].sum()),
        "total_clicks": int(df["clicks"].sum()),
        "total_impressions": int(df["impressions"].sum()),
        "overall_acos": round(float(total_spend / total_sales), 4) if total_sales > 0 else None,
        "overall_roas": round(float(total_sales / total_spend), 2) if total_spend > 0 else None,
        "overall_ctr": round(float(df["clicks"].sum() / df["impressions"].sum()), 4) if df["impressions"].sum() > 0 else None,
        "campaign_count": len(df),
    }

    # ── Ranking ────────────────────────────────────────────────
    rank_cols = ["campaign_name", "status", "spend", "sales", "acos", "roas",
                 "orders", "clicks", "impressions", "ctr", "cpc"]
    available = [c for c in rank_cols if c in df.columns]
    ranking = df[available].sort_values("spend", ascending=False).copy()

    # Budget utilization
    if "budget" in df.columns:
        ranking["budget_utilization"] = np.where(
            df["budget"].notna() & (df["budget"] > 0),
            df["spend"] / (df["budget"] * 30),
            None,
        )
        ranking["budget_utilization"] = ranking["budget_utilization"].apply(
            lambda x: round(float(x), 4) if pd.notna(x) else None
        )

    # Flags
    ranking["flag"] = ""
    if "acos" in df.columns:
        ranking.loc[df["acos"] < WINNER_ACOS_THRESHOLD, "flag"] = "优胜"
        ranking.loc[df["acos"] > HIGH_ACOS_THRESHOLD, "flag"] = "高风险"
    if "roas" in df.columns:
        ranking.loc[df["roas"] < LOW_ROAS_THRESHOLD, "flag"] = "问题"

    ranking_list = ranking.to_dict(orient="records")

    # ── Portfolio aggregation ──────────────────────────────────
    portfolio = None
    if "portfolio_name" in df.columns:
        pcols = ["portfolio_name", "spend", "sales", "orders", "clicks", "impressions"]
        pcols = [c for c in pcols if c in df.columns]
        pf = df[pcols].groupby("portfolio_name").sum()
        pf["acos"] = pf["spend"] / pf["sales"].replace(0, np.nan)
        pf["roas"] = pf["sales"] / pf["spend"].replace(0, np.nan)
        portfolio = pf.reset_index().to_dict(orient="records")
        for r in portfolio:
            round_record(r)

    # ── Winners & problems ─────────────────────────────────────
    winners_list, problems_list = [], []
    if "acos" in df.columns:
        w = df[df["acos"].notna() & (df["acos"] < WINNER_ACOS_THRESHOLD) & (df["sales"] > 0)]
        w = w.sort_values("sales", ascending=False)
        winners_list = w[available].to_dict(orient="records")
        p = df[df["acos"].notna() & (df["acos"] > HIGH_ACOS_THRESHOLD)]
        p = p.sort_values("spend", ascending=False)
        problems_list = p[available].to_dict(orient="records")

    # ── Status distribution ────────────────────────────────────
    status_counts = df["status"].value_counts().to_dict() if "status" in df.columns else {}

    return {
        "summary": summary,
        "ranking": ranking_list,
        "portfolio": portfolio,
        "status_distribution": {str(k): int(v) for k, v in status_counts.items()},
        "winners": winners_list,
        "problems": problems_list,
        "thresholds": {
            "high_acos": HIGH_ACOS_THRESHOLD,
            "low_roas": LOW_ROAS_THRESHOLD,
            "winner_acos": WINNER_ACOS_THRESHOLD,
        },
    }


if __name__ == "__main__":
    reports = load_data()
    if "campaign" not in reports:
        print("错误: 未找到广告活动报告")
        exit(1)
    result = analyze(reports["campaign"])
    save_json(result, "campaign_analysis.json")
    s = result["summary"]
    print(f"\n广告活动总览:")
    print(f"  活动数: {s['campaign_count']}")
    print(f"  总花费: ${s['total_spend']:,.2f}")
    print(f"  总销售额: ${s['total_sales']:,.2f}")
    print(f"  总订单: {s['total_orders']}")
    print(f"  整体ACOS: {s['overall_acos']:.2%}" if s['overall_acos'] else "  整体ACOS: N/A")
    print(f"  整体ROAS: {s['overall_roas']:.2f}" if s['overall_roas'] else "  整体ROAS: N/A")
    print(f"  优胜活动: {len(result['winners'])} 个  |  问题活动: {len(result['problems'])} 个")
