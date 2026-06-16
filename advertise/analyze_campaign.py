"""
广告活动层分析 — ACOS/ROAS 排行、花费vs预算、Portfolio 聚合、状态分布。
"""
import os
import pandas as pd
import numpy as np
from advertise import load_data, save_json

# ── 可配置阈值 ──────────────────────────────────────────
HIGH_ACOS_THRESHOLD = 0.50   # ACOS > 50% 标记为高风险活动
LOW_ROAS_THRESHOLD = 1.0     # ROAS < 1.0 标记为问题活动


def _safe_num(series):
    """将 series 转为数值，无法转换的置 NaN。"""
    return pd.to_numeric(series, errors="coerce")


def analyze(df):
    df = df.copy()
    # 数值化关键列
    for col in ("spend", "sales_7d", "budget", "orders_7d", "clicks", "impressions",
                "acos", "roas", "ctr", "cpc"):
        if col in df.columns:
            df[col] = _safe_num(df[col])

    # ACOS/ROAS: 已有列使用报告自带值，缺失时补充计算
    if "acos" in df.columns and df["acos"].isna().all():
        mask = df["sales_7d"].notna() & (df["sales_7d"] > 0)
        df.loc[mask, "acos"] = df.loc[mask, "spend"] / df.loc[mask, "sales_7d"]
    if "roas" in df.columns and df["roas"].isna().all():
        mask = df["spend"].notna() & (df["spend"] > 0)
        df.loc[mask, "roas"] = df.loc[mask, "sales_7d"] / df.loc[mask, "spend"]

    # ── 全量汇总 ──────────────────────────────────────
    total_spend = df["spend"].sum()
    total_sales = df["sales_7d"].sum()
    total_orders = df["orders_7d"].sum()
    total_clicks = df["clicks"].sum()
    total_impressions = df["impressions"].sum()
    overall_acos = total_spend / total_sales if total_sales > 0 else None
    overall_roas = total_sales / total_spend if total_spend > 0 else None
    overall_ctr = total_clicks / total_impressions if total_impressions > 0 else None

    summary = {
        "total_spend": round(float(total_spend), 2),
        "total_sales_7d": round(float(total_sales), 2),
        "total_orders_7d": int(total_orders),
        "total_clicks": int(total_clicks),
        "total_impressions": int(total_impressions),
        "overall_acos": round(float(overall_acos), 4) if overall_acos is not None else None,
        "overall_roas": round(float(overall_roas), 2) if overall_roas is not None else None,
        "overall_ctr": round(float(overall_ctr), 4) if overall_ctr is not None else None,
        "campaign_count": len(df),
    }

    # ── 活动排行 ──────────────────────────────────────
    rank_cols = ["campaign_name", "status", "portfolio_name", "spend", "sales_7d",
                 "acos", "roas", "orders_7d", "clicks", "impressions", "ctr", "cpc", "budget"]
    available_cols = [c for c in rank_cols if c in df.columns]
    ranking = df[available_cols].sort_values("spend", ascending=False)
    ranking["budget_utilization"] = None
    if "budget" in df.columns:
        ranking["budget_utilization"] = np.where(
            df["budget"].notna() & (df["budget"] > 0),
            df["spend"] / (df["budget"] * 30),  # 日预算 × 30 ≈ 月预算
            None,
        )
        ranking["budget_utilization"] = ranking["budget_utilization"].apply(
            lambda x: round(float(x), 4) if pd.notna(x) else None
        )

    # 标记
    ranking["flag"] = ""
    if "acos" in df.columns:
        ranking.loc[df["acos"] < 0.15, "flag"] = "优胜"
        ranking.loc[df["acos"] > HIGH_ACOS_THRESHOLD, "flag"] = "高风险"
    if "roas" in df.columns:
        ranking.loc[df["roas"] < LOW_ROAS_THRESHOLD, "flag"] = "问题"

    ranking_list = ranking.to_dict(orient="records")

    # ── Portfolio 聚合 ────────────────────────────────
    portfolio_cols = ["portfolio_name", "spend", "sales_7d", "orders_7d", "clicks", "impressions"]
    pcols = [c for c in portfolio_cols if c in df.columns]
    portfolio = df[pcols].groupby("portfolio_name").sum()
    portfolio["acos"] = portfolio["spend"] / portfolio["sales_7d"].replace(0, np.nan)
    portfolio["roas"] = portfolio["sales_7d"] / portfolio["spend"].replace(0, np.nan)
    portfolio_list = portfolio.reset_index().to_dict(orient="records")
    for r in portfolio_list:
        for k in r:
            if isinstance(r[k], (np.floating,)):
                r[k] = round(float(r[k]), 4)
            elif pd.isna(r[k]):
                r[k] = None

    # ── 状态分布 ──────────────────────────────────────
    status_counts = df["status"].value_counts().to_dict() if "status" in df.columns else {}

    # ── 优胜 / 问题活动 ───────────────────────────────
    if "acos" in df.columns:
        winners = df[df["acos"].notna() & (df["acos"] < 0.15) & (df["sales_7d"] > 0)]
        winners = winners.sort_values("sales_7d", ascending=False)
        winners_list = winners[available_cols].to_dict(orient="records")
    else:
        winners_list = []

    if "acos" in df.columns:
        problems = df[df["acos"].notna() & (df["acos"] > HIGH_ACOS_THRESHOLD)]
        problems = problems.sort_values("spend", ascending=False)
        problems_list = problems[available_cols].to_dict(orient="records")
    else:
        problems_list = []

    return {
        "summary": summary,
        "ranking": ranking_list,
        "portfolio": portfolio_list,
        "status_distribution": {str(k): int(v) for k, v in status_counts.items()},
        "winners": winners_list,
        "problems": problems_list,
        "thresholds": {
            "high_acos": HIGH_ACOS_THRESHOLD,
            "low_roas": LOW_ROAS_THRESHOLD,
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
    print(f"  总销售额(7d): ${s['total_sales_7d']:,.2f}")
    print(f"  总订单(7d): {s['total_orders_7d']}")
    print(f"  整体ACOS: {s['overall_acos']:.2%}" if s['overall_acos'] else "  整体ACOS: N/A")
    print(f"  整体ROAS: {s['overall_roas']:.2f}" if s['overall_roas'] else "  整体ROAS: N/A")
    print(f"  优胜活动: {len(result['winners'])}个")
    print(f"  问题活动: {len(result['problems'])}个")
