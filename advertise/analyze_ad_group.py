"""
Ad Group analysis — campaign-internal budget allocation and structural diagnostics.
Reuses the same analysis framework as Campaign (80% code similarity).
"""
import os, sys
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols, round_record
from advertise.thresholds import HIGH_ACOS_THRESHOLD, LOW_ROAS_THRESHOLD, WINNER_ACOS_THRESHOLD


def analyze(df):
    df = df.copy()
    numeric_cols(df, ["spend", "sales", "orders", "clicks", "impressions",
                       "acos", "roas", "ctr", "cpc", "conversion_rate",
                       "same_sku_orders", "same_sku_sales", "same_sku_units",
                       "other_sku_orders", "other_sku_sales", "other_sku_units"])

    # ── Per-ad-group aggregation ───────────────────────────────
    gcols = ["ad_group_name", "campaign_name", "campaign_id"]
    gcols = [c for c in gcols if c in df.columns]
    agg = {"spend": "sum", "sales": "sum", "orders": "sum",
           "clicks": "sum", "impressions": "sum",
           "same_sku_sales": "sum", "other_sku_sales": "sum"}
    available = {k: v for k, v in agg.items() if k in df.columns}
    by_group = df.groupby(gcols).agg(available).reset_index()
    by_group["acos"] = by_group["spend"] / by_group["sales"].replace(0, np.nan)
    by_group["roas"] = by_group["sales"] / by_group["spend"].replace(0, np.nan)
    by_group["ctr"] = by_group["clicks"] / by_group["impressions"].replace(0, np.nan)
    by_group["cpc"] = by_group["spend"] / by_group["clicks"].replace(0, np.nan)
    by_group = by_group.sort_values("spend", ascending=False)

    # ── Campaign-internal share analysis ───────────────────────
    campaign_totals = by_group.groupby("campaign_name")["spend"].sum().to_dict()
    share_records = []
    for _, row in by_group.iterrows():
        cam_spend = campaign_totals.get(row["campaign_name"], 1)
        r = {
            "ad_group_name": str(row["ad_group_name"]),
            "campaign_name": str(row["campaign_name"]),
            "campaign_id": str(row.get("campaign_id", "")),
            "spend": round(float(row["spend"]), 2),
            "sales": round(float(row["sales"]), 2),
            "orders": int(row.get("orders", 0) or 0),
            "clicks": int(row.get("clicks", 0) or 0),
            "impressions": int(row.get("impressions", 0) or 0),
            "acos": round(float(row["acos"]), 4) if pd.notna(row["acos"]) else None,
            "roas": round(float(row["roas"]), 2) if pd.notna(row["roas"]) else None,
            "ctr": round(float(row["ctr"]), 4) if pd.notna(row["ctr"]) else None,
            "cpc": round(float(row["cpc"]), 4) if pd.notna(row["cpc"]) else None,
            "same_sku_sales": round(float(row.get("same_sku_sales", 0) or 0), 2),
            "other_sku_sales": round(float(row.get("other_sku_sales", 0) or 0), 2),
            "campaign_spend_share": round(float(row["spend"] / cam_spend), 4) if cam_spend > 0 else None,
        }
        share_records.append(r)

    # ── Structural diagnostics ─────────────────────────────────
    groups_per_campaign = by_group.groupby("campaign_name").size()
    diagnostics = []
    for cam, count in groups_per_campaign.items():
        cam_groups = [r for r in share_records if r["campaign_name"] == cam]
        top_share = max(r["campaign_spend_share"] or 0 for r in cam_groups)
        if count > 10:
            diag = {"campaign_name": str(cam), "issue": "too_many_groups",
                    "detail": f"{count} 个广告组 — 建议拆分为多个活动避免预算争抢",
                    "group_count": int(count),
                    "top_group_share": round(float(top_share), 2)}
        elif count == 1:
            diag = {"campaign_name": str(cam), "issue": "single_group",
                    "detail": f"仅 1 个广告组 — 如果活动复杂可考虑拆分策略",
                    "group_count": int(count),
                    "top_group_share": round(float(top_share), 2)}
        elif top_share > 0.80:
            diag = {"campaign_name": str(cam), "issue": "budget_monopoly",
                    "detail": f"一组消耗 {top_share:.0%} 预算 — 可能饿死同活动其他组",
                    "group_count": int(count),
                    "top_group_share": round(float(top_share), 2)}
        else:
            continue
        diagnostics.append(diag)

    # ── Cross-campaign duplicate name detection ────────────────
    name_counts = by_group.groupby("ad_group_name")["campaign_name"].nunique()
    duplicates = name_counts[name_counts > 1].index.tolist()

    # ── Winners & problems ────────────────────────────────────
    winners = [r for r in share_records if r["acos"] is not None and r["acos"] < WINNER_ACOS_THRESHOLD and r.get("orders", 0) > 0]
    problems = [r for r in share_records if r["acos"] is not None and r["acos"] > HIGH_ACOS_THRESHOLD]
    problems = sorted(problems, key=lambda x: x["spend"], reverse=True)

    total_spend = sum(r["spend"] for r in share_records)
    total_sales = sum(r["sales"] for r in share_records)

    return {
        "summary": {
            "group_count": len(share_records),
            "campaign_count": len(groups_per_campaign),
            "total_spend": round(total_spend, 2),
            "total_sales": round(total_sales, 2),
            "overall_acos": round(total_spend / total_sales, 4) if total_sales > 0 else None,
            "dup_names_across_campaigns": len(duplicates),
            "structural_issues": len(diagnostics),
        },
        "ranking": share_records,
        "winners": winners,
        "problems": problems,
        "structural_diagnostics": diagnostics,
        "duplicate_names": duplicates,
    }


if __name__ == "__main__":
    reports = load_data()
    if "ad_group" not in reports:
        print("错误: 未找到广告组报告 (AdGroup)")
        sys.exit(1)
    result = analyze(reports["ad_group"])
    save_json(result, "ad_group_analysis.json")
    s = result["summary"]
    print(f"\n===== 广告组结构分析 =====")
    print(f"  广告组数: {s['group_count']} (分布在 {s['campaign_count']} 个活动中)")
    print(f"  总花费: ${s['total_spend']:,.2f}  总销售额: ${s['total_sales']:,.2f}")
    print(f"  整体ACOS: {s['overall_acos']:.2%}" if s['overall_acos'] else "  整体ACOS: N/A")
    print(f"  跨活动同名组: {s['dup_names_across_campaigns']} 个")
    print(f"  结构问题: {s['structural_issues']} 个")
    if result["structural_diagnostics"]:
        print(f"\n  结构诊断:")
        for d in result["structural_diagnostics"]:
            print(f"    {d['campaign_name']}: {d['issue']} — {d['detail']}")
    if result["duplicate_names"]:
        print(f"\n  跨活动同名组 (可能自我竞争):")
        for n in result["duplicate_names"]:
            print(f"    {n}")
    print(f"\n  Top 5 广告组:")
    for r in result["ranking"][:5]:
        a = f"ACOS={r['acos']:.1%}" if r['acos'] else ""
        share = f" 份额={r['campaign_spend_share']:.0%}" if r.get('campaign_spend_share') else ""
        print(f"    {r['ad_group_name'][:35]}: spend=${r['spend']:,.2f}  {a}{share}")
