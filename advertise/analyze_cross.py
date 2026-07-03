"""
Cross-report integrated analysis.
Combines data from multiple reports to produce insights no single report can reveal.

Key outputs:
1. Blended ACOS per campaign (corrects for brand halo)
2. Gateway ASIN final determination (should never be paused)
3. Search term → keyword harvesting action list
4. Campaign × Placement efficiency matrix
5. Overall account health score
"""
import json, os, sys
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num, numeric_cols

SCRIPT_DIR = os.path.dirname(__file__)
OUT_DIR = os.path.join(SCRIPT_DIR, "out")


def load_json_file(name):
    with open(os.path.join(OUT_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def analyze(all_reports):
    """Main cross-report analysis. Accepts a dict of DataFrames from load_data()."""
    # Also load pre-computed analysis JSONs for enriched data
    campaign_json = load_json_file("campaign_analysis.json")
    targeting_json = load_json_file("targeting_analysis.json")
    search_json = load_json_file("search_term_analysis.json")
    placement_json = load_json_file("placement_analysis.json")
    adgroup_json = load_json_file("ad_group_analysis.json")
    product_json = load_json_file("advertised_product_analysis.json")
    purchased_json = load_json_file("purchased_item_analysis.json")

    # ═══════════════════════════════════════════════════════════════
    # 1. Blended ACOS per campaign (campaign spend vs total attributed sales)
    # ═══════════════════════════════════════════════════════════════
    # Campaign report gives us spend. PurchasedItem gives us other-SKU sales per campaign.
    # We blend these to get the TRUE efficiency per campaign.

    campaign_totals = {}
    for r in campaign_json["ranking"]:
        cname = r.get("campaign_name", "Unknown")
        if cname not in campaign_totals:
            campaign_totals[cname] = {"spend": 0, "sales": 0, "acos": None, "status": ""}
        campaign_totals[cname]["spend"] += float(r.get("spend", 0) or 0)
        campaign_totals[cname]["sales"] += float(r.get("sales", 0) or 0)
        campaign_totals[cname]["status"] = r.get("status", "")

    # Add other-SKU sales from PurchasedItem per campaign
    purchased_by_campaign = {}
    for cs in purchased_json["cross_sell_map"]:
        cname = cs.get("campaign_name", "")
        purchased_by_campaign[cname] = purchased_by_campaign.get(cname, 0) + float(cs.get("sales", 0) or 0)

    blended_campaigns = []
    for cname, totals in campaign_totals.items():
        other_sku = purchased_by_campaign.get(cname, 0)
        total_sales = totals["sales"] + other_sku
        blended_acos = totals["spend"] / total_sales if total_sales > 0 else None
        direct_acos = totals["spend"] / totals["sales"] if totals["sales"] > 0 else None
        halo_boost_pct = (other_sku / totals["sales"] * 100) if totals["sales"] > 0 else 0

        blended_campaigns.append({
            "campaign_name": cname,
            "spend": round(totals["spend"], 2),
            "direct_sales": round(totals["sales"], 2),
            "other_sku_sales": round(other_sku, 2),
            "total_sales": round(total_sales, 2),
            "direct_acos": round(direct_acos, 4) if direct_acos is not None else None,
            "blended_acos": round(blended_acos, 4) if blended_acos is not None else None,
            "halo_boost_pct": round(halo_boost_pct, 1),
            "status": totals["status"],
        })

    blended_campaigns.sort(key=lambda x: x["spend"], reverse=True)

    # ═══════════════════════════════════════════════════════════════
    # 2. Gateway ASIN final determination
    # ═══════════════════════════════════════════════════════════════
    # Combine AdProduct (ASIN-level direct metrics) + PurchasedItem (halo data)
    # An ASIN is "Gateway" if: it has >$X other-SKU sales AND other-SKU > same-SKU

    purchased_by_asin = {}
    for pi in purchased_json["by_advertised_asin"]:
        asin = pi.get("advertised_asin", "")
        purchased_by_asin[asin] = {
            "other_sku_sales": float(pi.get("purchased_sales", 0) or 0),
            "other_sku_units": int(pi.get("purchased_units", 0) or 0),
            "cross_sell_count": int(pi.get("purchase_events", 0) or 0),
        }

    asin_final = []
    for r in product_json["ranking"]:
        asin = r.get("asin", "")
        halo = purchased_by_asin.get(asin, {})
        total_sales = (float(r.get("sales", 0) or 0) + float(r.get("other_sku_sales", 0) or 0))
        spend = float(r.get("spend", 0) or 0)
        blended_acos = spend / total_sales if total_sales > 0 else None
        direct_acos = r.get("acos")

        is_gateway = False
        gateway_reason = ""
        if halo.get("other_sku_sales", 0) > 100:
            is_gateway = True
            gateway_reason = f"光环销售额 > $100 (${halo['other_sku_sales']:,.2f})"
        if halo.get("cross_sell_count", 0) >= 3:
            is_gateway = True
            gateway_reason += (" | " if gateway_reason else "") + f"拉动{halo['cross_sell_count']}种其他产品"

        asin_final.append({
            "asin": asin,
            "sku": r.get("sku", ""),
            "spend": round(spend, 2),
            "direct_sales": round(float(r.get("sales", 0) or 0), 2),
            "other_sku_sales": round(float(r.get("other_sku_sales", 0) or 0), 2),
            "total_sales": round(total_sales, 2),
            "direct_acos": round(direct_acos, 4) if direct_acos is not None else None,
            "blended_acos": round(blended_acos, 4) if blended_acos is not None else None,
            "cross_sell_count": halo.get("cross_sell_count", 0),
            "is_gateway": is_gateway,
            "gateway_reason": gateway_reason,
            "action": "NEVER_PAUSE" if is_gateway else (
                "PAUSE_CANDIDATE" if direct_acos is not None and direct_acos > 0.66 else "OK"),
        })

    asin_final.sort(key=lambda x: x["spend"], reverse=True)

    # ═══════════════════════════════════════════════════════════════
    # 3. Search term → keyword harvesting list
    # ═══════════════════════════════════════════════════════════════
    harvest_list = []
    for h in search_json.get("harvest_keywords", []):
        harvest_list.append({
            "search_term": h.get("search_term", ""),
            "spend": h.get("spend", 0),
            "sales": h.get("sales", 0),
            "orders": h.get("orders", 0),
            "acos": h.get("acos"),
            "roas": h.get("roas"),
            "clicks": h.get("clicks", 0),
            "action": "加入精准匹配活动",
            "priority": "HIGH" if (h.get("orders", 0) or 0) >= 3 else "MEDIUM",
        })
    harvest_list.sort(key=lambda x: x.get("sales", 0) or 0, reverse=True)

    negate_list = []
    for n in search_json.get("negative_candidates", []):
        negate_list.append({
            "search_term": n.get("search_term", ""),
            "spend": n.get("spend", 0),
            "clicks": n.get("clicks", 0),
            "priority": "HIGH" if (n.get("spend", 0) or 0) > 10 else "MEDIUM",
        })
    negate_list.sort(key=lambda x: x.get("spend", 0) or 0, reverse=True)

    # ═══════════════════════════════════════════════════════════════
    # 4. Campaign × Placement efficiency matrix
    # ═══════════════════════════════════════════════════════════════
    placement_matrix = []
    for p in placement_json["detail"][:30]:
        placement_matrix.append({
            "campaign": p.get("campaign_name", ""),
            "placement": p.get("placement_category", ""),
            "spend": round(float(p.get("spend", 0) or 0), 2),
            "sales": round(float(p.get("sales", 0) or 0), 2),
            "acos": round(float(p.get("acos", 0) or 0), 4) if p.get("acos") is not None else None,
        })

    # ═══════════════════════════════════════════════════════════════
    # 5. Overall health score (0-100)
    # ═══════════════════════════════════════════════════════════════
    cs_c = campaign_json["summary"]
    overall_acos = cs_c.get("overall_acos", 1)
    overall_roas = cs_c.get("overall_roas", 0)
    product_acos = product_json["summary"]["overall_acos"] or 1
    blended_acos = product_json["summary"]["blended_acos_with_halo"] or 1
    halo_ratio = targeting_json["halo_effect"].get("halo_ratio", 0) or 0
    harvest_count = len(harvest_list)
    negate_count = len(negate_list)
    gateway_count = sum(1 for a in asin_final if a["is_gateway"])
    structural_issues = adgroup_json["summary"].get("structural_issues", 0)

    score = 50  # start at midpoint
    if overall_acos < 0.25: score += 15
    elif overall_acos < 0.35: score += 8
    elif overall_acos > 0.60: score -= 15
    elif overall_acos > 0.45: score -= 8

    if overall_roas > 4: score += 10
    elif overall_roas > 2.5: score += 5
    elif overall_roas < 1.5: score -= 10

    if blended_acos < overall_acos: score += 5  # halo helps
    if halo_ratio > 0.5: score += 5  # strong halo
    if harvest_count >= 5: score += 5
    if negate_count > 0: score += 3  # identified waste to cut
    if gateway_count > 0: score += 5  # high-value ASINs identified
    if structural_issues > len(adgroup_json.get("ranking", [])) // 2: score -= 5

    score = max(0, min(100, score))

    health = {
        "score": score,
        "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
        "key_strengths": [],
        "key_weaknesses": [],
    }
    if overall_acos < 0.35:
        health["key_strengths"].append("ACOS 在健康范围内")
    else:
        health["key_weaknesses"].append(f"ACOS ({overall_acos:.1%}) 偏高, 需优化")
    if halo_ratio > 0.5:
        health["key_strengths"].append(f"品牌光环效应强劲 ({halo_ratio:.2f}x)")
    if harvest_count >= 3:
        health["key_strengths"].append(f"{harvest_count} 个 Harvest 搜索词可收割")
    if gateway_count > 0:
        health["key_strengths"].append(f"{gateway_count} 个 Gateway ASIN 驱动交叉销售")
    if structural_issues > 10:
        health["key_weaknesses"].append(f"{structural_issues} 个广告组结构问题需修复")
    if blended_acos > 0.40:
        health["key_weaknesses"].append(f"即使含光环, 混合ACOS仍偏高 ({blended_acos:.1%})")

    # ═══════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════
    total_spend = cs_c["total_spend"]
    total_direct = cs_c["total_sales"]
    total_halo = purchased_json["summary"]["total_purchased_sales"]
    total_all = total_direct + total_halo

    return {
        "summary": {
            "total_spend": round(total_spend, 2),
            "direct_sales": round(total_direct, 2),
            "halo_sales": round(total_halo, 2),
            "total_sales": round(total_all, 2),
            "direct_acos": round(total_spend / total_direct, 4) if total_direct > 0 else None,
            "blended_acos": round(total_spend / total_all, 4) if total_all > 0 else None,
            "halo_impact_pct": round(total_halo / total_direct * 100, 1) if total_direct > 0 else 0,
            "account_health": health,
        },
        "blended_campaign_acos": blended_campaigns,
        "gateway_asin_final": asin_final,
        "harvest_actions": harvest_list,
        "negate_actions": negate_list,
        "placement_matrix": placement_matrix,
    }


if __name__ == "__main__":
    reports = load_data()
    result = analyze(reports)
    save_json(result, "cross_analysis.json")

    s = result["summary"]
    h = s["account_health"]
    print(f"\n===== 跨报告集成分析 =====")
    print(f"  总花费: ${s['total_spend']:,.2f}")
    print(f"  直接销售: ${s['direct_sales']:,.2f}")
    print(f"  光环销售: ${s['halo_sales']:,.2f}")
    print(f"  总销售(含光环): ${s['total_sales']:,.2f}")
    print(f"  直接ACOS: {s['direct_acos']:.1%}")
    print(f"  混合ACOS: {s['blended_acos']:.1%}")
    print(f"  光环增幅: {s['halo_impact_pct']:.1f}%")
    print(f"\n  账户健康度: {h['score']}/100 ({h['grade']}级)")
    print(f"  优势: {', '.join(h['key_strengths'])}")
    print(f"  劣势: {', '.join(h['key_weaknesses'])}")
    print(f"\n  正确ACOS排名 (Top 5):")
    for c in result["blended_campaign_acos"][:5]:
        b = f"→ 混合ACOS {c['blended_acos']:.1%}" if c['blended_acos'] else ""
        print(f"    {c['campaign_name'][:30]}: ${c['spend']:,.2f} | 直接ACOS {c['direct_acos']:.1%}" + b if c['direct_acos'] else "")
    print(f"\n  Gateway ASIN 最终判定:")
    for a in result["gateway_asin_final"]:
        if a["is_gateway"]:
            print(f"    {a['asin']} {a['sku'][:25]}: {a['action']} ({a['gateway_reason']})")
    print(f"\n  关键词收割候选: {len(result['harvest_actions'])} 个")
    print(f"  否定词候选: {len(result['negate_actions'])} 个")
