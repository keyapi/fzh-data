"""
Product-line level aggregation analysis.
Groups campaigns by product line (SKU prefix / product name pattern)
to provide a per-product view of advertising performance.

Key outputs:
- Per-product spend / sales / ACOS / blended ACOS
- Campaign count and structure health per product
- Gateway ASIN attribution per product
- Cross-product comparison

Usage: python -m advertise.analyze_product_line
"""
import os, json, sys, re
import pandas as pd
import numpy as np
from advertise import load_data, save_json
from advertise.utils import safe_num

SCRIPT_DIR = os.path.dirname(__file__)
OUT_DIR = os.path.join(SCRIPT_DIR, "out")

def load_json_file(name):
    with open(os.path.join(OUT_DIR, name), encoding="utf-8") as f:
        return json.load(f)

# Product line definitions based on campaign naming patterns
PRODUCT_PATTERNS = [
    ("户外沙发", [r"户外.*沙发", r"KS0527", r"outdoor.*sofa", r"patio.*sofa", r"组合.*沙发", r"模块.*沙发"]),
    ("三角无扣靠枕", [r"三角无扣", r"BJ-Pillow", r"BJ.Pillow", r"headboard.*pillow"]),
    ("狗窝/宠物床", [r"dog.*bed", r"狗窝", r"清仓.*自动"]),
    ("阅读枕/靠枕", [r"reading.*pillow", r"靠枕", r"游戏枕"]),
    ("坐垫", [r"坐垫", r"cushion", r"两用"]),
    ("平条涤纶", [r"平条", r"涤纶"]),
    ("其他", []),  # catch-all
]

def classify_product(campaign_name):
    """Classify a campaign into a product line."""
    if not isinstance(campaign_name, str):
        return "其他"
    for product, patterns in PRODUCT_PATTERNS[:-1]:
        for pat in patterns:
            if re.search(pat, campaign_name, re.IGNORECASE):
                return product
    return "其他"

def analyze():
    # Load data and pre-computed analyses
    reports = load_data()
    campaign_json = load_json_file("campaign_analysis.json")
    product_json = load_json_file("advertised_product_analysis.json")
    purchased_json = load_json_file("purchased_item_analysis.json")
    adgroup_json = load_json_file("ad_group_analysis.json")
    cross_json = load_json_file("cross_analysis.json")

    # Build campaign -> product line mapping
    campaign_df = reports.get("campaign")
    if campaign_df is None:
        print("Error: No campaign data")
        sys.exit(1)

    campaign_names = campaign_df["campaign_name"].dropna().unique()
    campaign_product = {}
    for cname in campaign_names:
        campaign_product[cname] = classify_product(cname)

    # Aggregate by product line from campaign data
    product_data = {}
    for _, row in campaign_df.iterrows():
        cname = str(row.get("campaign_name", ""))
        product = campaign_product.get(cname, "其他")
        if product not in product_data:
            product_data[product] = {
                "spend": 0, "sales": 0, "orders": 0,
                "clicks": 0, "impressions": 0,
                "campaigns": set(), "campaign_names": [],
            }
        pd_item = product_data[product]
        pd_item["spend"] += float(row.get("spend", 0) or 0)
        pd_item["sales"] += float(row.get("sales", 0) or 0)
        pd_item["orders"] += int(row.get("orders", 0) or 0)
        pd_item["clicks"] += int(row.get("clicks", 0) or 0)
        pd_item["impressions"] += int(row.get("impressions", 0) or 0)
        if cname not in pd_item["campaigns"]:
            pd_item["campaigns"].add(cname)
            pd_item["campaign_names"].append(cname)

    # Add halo sales from purchased_item data per campaign
    purchased_json_data = purchased_json
    halo_per_campaign = {}
    for item in purchased_json_data.get("cross_sell", []):
        campaign = item.get("campaign", "")
        sales = float(item.get("other_sku_sales", 0) or 0)
        halo_per_campaign[campaign] = halo_per_campaign.get(campaign, 0) + sales

    # Compute per-product metrics
    total_spend = 0
    total_sales = 0
    total_halo = 0

    product_lines = []
    for product, data in sorted(product_data.items(), key=lambda x: x[1]["spend"], reverse=True):
        spend = data["spend"]
        sales = data["sales"]
        halo = 0
        for cn in data["campaigns"]:
            halo += halo_per_campaign.get(cn, 0)

        direct_acos = spend / sales if sales > 0 else None
        blended_acos = spend / (sales + halo) if (sales + halo) > 0 else None
        roas = sales / spend if spend > 0 else None
        blended_roas = (sales + halo) / spend if spend > 0 else None

        # Compute campaign structure health
        n_campaigns = len(data["campaigns"])
        types_in_product = set()
        for cn in data["campaigns"]:
            cnl = cn.lower()
            if "auto" in cnl or "自动" in cnl:
                types_in_product.add("auto")
            if "exact" in cnl or "精准" in cnl:
                types_in_product.add("exact")
            if "broad" in cnl or "广泛" in cnl or "宽泛" in cnl:
                types_in_product.add("broad")
            if "phrase" in cnl or "词组" in cnl:
                types_in_product.add("phrase")
            if "pat" in cnl or "asin" in cnl or "竞品" in cnl:
                types_in_product.add("pat")

        missing_types = {"auto", "exact", "broad", "phrase", "pat"} - types_in_product
        structure_score = len(types_in_product) / 5 * 100

        total_spend += spend
        total_sales += sales
        total_halo += halo

        product_lines.append({
            "product": product,
            "spend": round(spend, 2),
            "sales": round(sales, 2),
            "halo_sales": round(halo, 2),
            "total_sales": round(sales + halo, 2),
            "orders": data["orders"],
            "clicks": data["clicks"],
            "direct_acos": round(direct_acos, 4) if direct_acos is not None else None,
            "blended_acos": round(blended_acos, 4) if blended_acos is not None else None,
            "roas": round(roas, 2) if roas is not None else None,
            "blended_roas": round(blended_roas, 2) if blended_roas is not None else None,
            "campaign_count": n_campaigns,
            "campaign_names": sorted(data["campaign_names"]),
            "campaign_types": sorted(types_in_product),
            "missing_types": sorted(missing_types),
            "structure_score": round(structure_score, 1),
            "recommendation": (
                "结构完整" if structure_score >= 80 else
                f"缺少: {', '.join(missing_types)}" if missing_types else
                "结构可优化"
            ),
        })

    result = {
        "summary": {
            "product_count": len(product_lines),
            "total_spend": round(total_spend, 2),
            "total_direct_sales": round(total_sales, 2),
            "total_halo_sales": round(total_halo, 2),
            "total_blended_sales": round(total_sales + total_halo, 2),
            "overall_direct_acos": round(total_spend / total_sales, 4) if total_sales > 0 else None,
            "overall_blended_acos": round(total_spend / (total_sales + total_halo), 4) if (total_sales + total_halo) > 0 else None,
        },
        "product_lines": product_lines,
    }
    return result


if __name__ == "__main__":
    result = analyze()
    save_json(result, "product_line_analysis.json")

    s = result["summary"]
    print(f"\n===== 产品线聚合分析 =====")
    print(f"  产品线数: {s['product_count']}")
    print(f"  总花费: ${s['total_spend']:,.2f}")
    print(f"  直接销售: ${s['total_direct_sales']:,.2f}")
    print(f"  光环销售: ${s['total_halo_sales']:,.2f}")
    print(f"  总销售(含光环): ${s['total_blended_sales']:,.2f}")
    print(f"  直接ACOS: {s['overall_direct_acos']:.1%}" if s['overall_direct_acos'] else f"  直接ACOS: N/A")
    print(f"  混合ACOS: {s['overall_blended_acos']:.1%}" if s['overall_blended_acos'] else f"  混合ACOS: N/A")

    print(f"\n  产品线排名 (按花费):")
    for pl in result["product_lines"]:
        b = f"混合ACOS {pl['blended_acos']:.1%}" if pl['blended_acos'] else "无销售"
        d = f"直接ACOS {pl['direct_acos']:.1%}" if pl['direct_acos'] else "无销售"
        print(f"    {pl['product'][:20]:20s} | spend=${pl['spend']:>8,.2f} | {d} | {b} | {pl['campaign_count']}活动 | 结构{pl['structure_score']:.0f}% | {pl['recommendation']}")