"""
Campaign structure blueprint generator.
Reads product_line_analysis.json and suggests the ideal campaign hierarchy
for each product line based on the Daneey strategy framework.

Reference: advertise/参考文档/Daneey_Amazon_Outdoor_Sofa_Optimization_Chat.md
"""
import json, os

SCRIPT_DIR = os.path.dirname(__file__)
OUT_DIR = os.path.join(SCRIPT_DIR, "out")

def load_j(name):
    with open(os.path.join(OUT_DIR, name), encoding="utf-8") as f:
        return json.load(f)

# Ideal budget allocation targets (from Daneey Chat section 9)
BUDGET_TARGETS = {
    "exact": (0.50, 0.60),   # 50-60% budget to exact match
    "phrase": (0.20, 0.25),  # 20-25% to phrase
    "broad": (0.10, 0.15),   # 10-15% to broad
    "auto": (0.05, 0.10),    # 5-10% to auto discovery
    "pat": (0.10, 0.15),     # 10-15% to product targeting
}

# Ideal campaign structure per product type
STRUCTURE_TEMPLATE = {
    "core_campaigns": [
        {"type": "exact", "name": "SP-Exact-Diff-{product}", "budget_pct": 30, "purpose": "主力转化-差异化词"},
        {"type": "exact", "name": "SP-Exact-Core-{product}", "budget_pct": 25, "purpose": "防守-品类大词精准"},
        {"type": "exact", "name": "SP-Exact-Scene-{product}", "budget_pct": 15, "purpose": "场景长尾词收割"},
        {"type": "phrase", "name": "SP-Phrase-Diff-{product}", "budget_pct": 15, "purpose": "扩展差异化词组"},
        {"type": "broad", "name": "SP-Broad-{product}", "budget_pct": 10, "purpose": "挖词-广泛匹配"},
        {"type": "auto", "name": "SP-Auto-Discovery-{product}", "budget_pct": 10, "purpose": "自动发现新词"},
        {"type": "pat", "name": "SP-PAT-Competitor-{product}", "budget_pct": 15, "purpose": "竞品ASIN投放"},
    ],
    "budget_per_campaign": 15,  # suggested daily budget per campaign
    "total_suggested_daily": 100,
}

def suggest_structure(product_name, current_types, current_spend):
    """Suggest ideal campaign structure for a product line."""
    missing = []
    for tmpl in STRUCTURE_TEMPLATE["core_campaigns"]:
        if tmpl["type"] not in current_types:
            missing.append({
                "name": tmpl["name"].replace("{product}", product_name),
                "type": tmpl["type"],
                "purpose": tmpl["purpose"],
                "suggested_daily_budget": int(tmpl["budget_pct"] / 100 * STRUCTURE_TEMPLATE["total_suggested_daily"]),
            })

    # Budget allocation diagnosis
    budget_diag = []
    for tmpl in STRUCTURE_TEMPLATE["core_campaigns"]:
        target_min, target_max = BUDGET_TARGETS.get(tmpl["type"], (0, 0))
        budget_diag.append({
            "type": tmpl["type"],
            "target_pct": f"{target_min*100:.0f}-{target_max*100:.0f}%",
            "has_in_structure": tmpl["type"] in current_types,
        })

    total_daily = STRUCTURE_TEMPLATE["total_suggested_daily"]
    monthly_estimate = total_daily * 30
    current_monthly = current_spend

    return {
        "product": product_name,
        "current_monthly_spend": round(current_monthly, 2),
        "suggested_monthly_budget": monthly_estimate,
        "budget_gap": round(monthly_estimate - current_monthly, 2),
        "missing_campaigns": missing,
        "budget_allocation_targets": budget_diag,
        "structure_template": STRUCTURE_TEMPLATE,
    }

if __name__ == "__main__":
    pl = load_j("product_line_analysis.json")

    print("\n===== Campaign 结构蓝图建议 =====")
    structures = []
    for product in pl["product_lines"]:
        s = suggest_structure(
            product["product"],
            product.get("campaign_types", []),
            product["spend"]
        )
        structures.append(s)

        print(f"\n--- {s['product']} ---")
        print(f"  当前月花费: ${s['current_monthly_spend']:,.2f}")
        print(f"  建议月预算: ${s['suggested_monthly_budget']:,.2f}")
        print(f"  预算差距: ${s['budget_gap']:+,.2f}")
        if s["missing_campaigns"]:
            print(f"  缺少活动 ({len(s['missing_campaigns'])}):")
            for m in s["missing_campaigns"]:
                print(f"    + {m['name']} ({m['type']}) — {m['purpose']}  ${m['suggested_daily_budget']}/天")
        else:
            print(f"  结构完整 ✓")

    import json as j
    from advertise.utils import save_json
    save_json({"blueprints": structures}, "campaign_blueprint.json")