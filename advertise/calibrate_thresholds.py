"""
Threshold calibration — analyzes actual data distributions to recommend optimal values.
Usage: python -m advertise.calibrate_thresholds
"""
import json, os, sys, math
import numpy as np
from advertise import load_data
from advertise.utils import safe_num

OUT_DIR = os.path.join(os.path.dirname(__file__), "out")

def load_j(name):
    with open(os.path.join(OUT_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def percentile(values, p):
    """p-th percentile of a list of numbers."""
    clean = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not clean:
        return None
    return float(np.percentile(clean, p))


def analyze():
    """Analyze distributions and recommend thresholds."""
    campaign = load_j("campaign_analysis.json")
    targeting = load_j("targeting_analysis.json")
    search = load_j("search_term_analysis.json")
    ad_product = load_j("advertised_product_analysis.json")

    result = {}

    # ═══════════════════════════════════════════════════════════════
    # 1. ACOS distribution (campaign-level)
    # ═══════════════════════════════════════════════════════════════
    acos_values = [r.get("acos") for r in campaign["ranking"] if r.get("acos") is not None]
    acos_clean = [a for a in acos_values if a is not None and not math.isnan(a)]

    result["acos_distribution"] = {
        "count": len(acos_clean),
        "p10": round(percentile(acos_clean, 10), 4),
        "p25": round(percentile(acos_clean, 25), 4),
        "p50": round(percentile(acos_clean, 50), 4),
        "p75": round(percentile(acos_clean, 75), 4),
        "p90": round(percentile(acos_clean, 90), 4),
        "mean": round(float(np.mean(acos_clean)), 4),
        "std": round(float(np.std(acos_clean)), 4),
    }

    # Sensitivity: how many campaigns flagged at different ACOS thresholds
    acos_sensitivity = []
    for t in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]:
        flagged = sum(1 for a in acos_clean if a > t)
        pct = flagged / len(acos_clean) * 100 if acos_clean else 0
        acos_sensitivity.append({"threshold": t, "flagged": flagged, "pct": round(pct, 1)})
    result["acos_sensitivity"] = acos_sensitivity

    # ═══════════════════════════════════════════════════════════════
    # 2. ROAS distribution
    # ═══════════════════════════════════════════════════════════════
    roas_values = [r.get("roas") for r in campaign["ranking"] if r.get("roas") is not None]
    roas_clean = [r for r in roas_values if r is not None and not math.isnan(r)]

    result["roas_distribution"] = {
        "count": len(roas_clean),
        "p10": round(percentile(roas_clean, 10), 2),
        "p25": round(percentile(roas_clean, 25), 2),
        "p50": round(percentile(roas_clean, 50), 2),
        "p75": round(percentile(roas_clean, 75), 2),
        "p90": round(percentile(roas_clean, 90), 2),
        "mean": round(float(np.mean(roas_clean)), 2),
    }

    # ═══════════════════════════════════════════════════════════════
    # 3. CVR distribution
    # ═══════════════════════════════════════════════════════════════
    product_ranking = ad_product.get("ranking", [])
    cvr_values = [r.get("cvr") for r in product_ranking if r.get("cvr") is not None]
    cvr_clean = [c for c in cvr_values if c is not None and not math.isnan(c)]
    if cvr_clean:
        result["cvr_distribution"] = {
            "count": len(cvr_clean),
            "p25": round(percentile(cvr_clean, 25), 4),
            "p50": round(percentile(cvr_clean, 50), 4),
            "p75": round(percentile(cvr_clean, 75), 4),
            "mean": round(float(np.mean(cvr_clean)), 4),
        }

    # ═══════════════════════════════════════════════════════════════
    # 4. Search term metrics distribution
    # ═══════════════════════════════════════════════════════════════
    harvest = search.get("harvest_keywords", [])
    negatives = search.get("negative_candidates", [])

    # Spend distribution for search terms
    all_terms = harvest + negatives + search.get("monitor_list", [])
    spends = [t.get("spend", 0) for t in all_terms if t.get("spend") is not None]
    spends_clean = [s for s in spends if s is not None and not math.isnan(s) and s > 0]
    if spends_clean:
        result["search_term_spend"] = {
            "count": len(spends_clean),
            "p25": round(percentile(spends_clean, 25), 2),
            "p50": round(percentile(spends_clean, 50), 2),
            "p75": round(percentile(spends_clean, 75), 2),
            "p90": round(percentile(spends_clean, 90), 2),
            "mean": round(float(np.mean(spends_clean)), 2),
        }

    # Clicks distribution
    clicks = [t.get("clicks", 0) for t in all_terms if t.get("clicks") is not None]
    clicks_clean = [c for c in clicks if c is not None and not math.isnan(c) and c > 0]
    if clicks_clean:
        result["search_term_clicks"] = {
            "count": len(clicks_clean),
            "p25": round(percentile(clicks_clean, 25), 1),
            "p50": round(percentile(clicks_clean, 50), 1),
            "p75": round(percentile(clicks_clean, 75), 1),
            "p90": round(percentile(clicks_clean, 90), 1),
            "mean": round(float(np.mean(clicks_clean)), 1),
        }

    # ═══════════════════════════════════════════════════════════════
    # 5. Recommended thresholds
    # ═══════════════════════════════════════════════════════════════
    recs = {}

    # HIGH_ACOS: flag campaigns with ACOS > P75
    p75_acos = percentile(acos_clean, 75)
    recs["high_acos"] = {
        "current": 0.40,
        "recommended": round(p75_acos, 2) if p75_acos else 0.40,
        "rationale": f"Set at P75 of campaign ACOS distribution — flags the worst 25% of campaigns",
    }

    # WINNER_ACOS: campaigns with ACOS < P25 and sales > 0
    p25_acos = percentile(acos_clean, 25)
    recs["winner_acos"] = {
        "current": 0.15,
        "recommended": round(p25_acos, 2) if p25_acos else 0.15,
        "rationale": f"Set at P25 — top 25% of campaigns by ACOS efficiency",
    }

    # MIN_CLICKS_NEGATE: clicks needed before we can call a search term a loser
    p50_clicks = percentile(clicks_clean, 50) if clicks_clean else 15
    recs["min_clicks_negate"] = {
        "current": 15,
        "recommended": max(10, int(p50_clicks)) if p50_clicks else 15,
        "rationale": f"Set above median clicks per search term ({int(p50_clicks)}), "
                     f"so we only negate after enough data",
    }

    # MAX_ACOS_HARVEST: max ACOS to consider a term worth harvesting
    recs["max_acos_harvest"] = {
        "current": 0.30,
        "recommended": 0.30,  # This should match gross_margin - 5% safety margin
        "rationale": "Should equal gross_margin - 5% safety margin. "
                     "Current 30% assumes ~35% margin. Set in config/bjryecltd-us.json",
        "note": "MANUAL: ask user for actual gross margin to set this correctly",
    }

    result["recommended_thresholds"] = recs

    # ═══════════════════════════════════════════════════════════════
    # 6. Data sufficiency check
    # ═══════════════════════════════════════════════════════════════
    result["data_sufficiency"] = {
        "months_available": 1,
        "campaign_count": len(acos_clean),
        "search_term_count": len(all_terms),
        "asin_count": len(product_ranking),
        "sufficient_for_baseline": len(acos_clean) >= 10,
        "sufficient_for_trend": False,  # needs 2+ months
        "recommendation": "Current data sufficient for single-period threshold calibration. "
                         "Need 2+ months for trend-based adaptive thresholds.",
    }

    return result


if __name__ == "__main__":
    result = analyze()

    # Pretty print summary
    print("===== 阈值标定分析 =====\n")

    d = result["acos_distribution"]
    print(f"ACOS 分布 ({d['count']} 个活动):")
    print(f"  P10={d['p10']:.1%}  P25={d['p25']:.1%}  P50={d['p50']:.1%}  P75={d['p75']:.1%}  P90={d['p90']:.1%}")

    print(f"\nACOS 阈值敏感度 (高于X则标记):")
    for s in result["acos_sensitivity"]:
        bar = "█" * int(s["pct"] / 2)
        print(f"  >{s['threshold']:.0%}: {s['flagged']:3d} 个活动 ({s['pct']:5.1f}%) {bar}")

    print(f"\n建议阈值调整:")
    for name, rec in result["recommended_thresholds"].items():
        cur = rec["current"]
        rec_val = rec["recommended"]
        arrow = "↑" if rec_val > cur else "↓" if rec_val < cur else "="
        note = f" [{rec.get('note', '')}]" if rec.get('note') else ""
        print(f"  {name}: {cur} {arrow} {rec_val} — {rec['rationale']}{note}")

    print(f"\n数据充分性: {'✓ 足够做基线标定' if result['data_sufficiency']['sufficient_for_baseline'] else '✗ 数据不足'}")
    print(f"  需趋势分析: {'还需要 ' + str(2 - result['data_sufficiency']['months_available']) + ' 个月数据' if not result['data_sufficiency']['sufficient_for_trend'] else '✓ 已足够'}")

    # Save
    out = os.path.join(OUT_DIR, "threshold_calibration.json")
    import json as j
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        j.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[保存] {out}")
