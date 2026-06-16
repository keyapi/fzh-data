"""
客户搜索词层分析 — 关键词收割、否定词识别、浪费支出排行、搜索词分类。

"人找货"路径的反向挖掘——从买家实际搜索词中分离高转化词和资金消耗词。
"""
import os
import re
import numpy as np
from advertise import load_data, save_json

# ── 可配置阈值 ──────────────────────────────────────────
MIN_CLICKS_HARVEST = 5         # 最少点击量才考虑收割
MAX_ACOS_HARVEST = 0.30        # ACOS < 30% 才建议收割
MIN_SPEND_NEGATIVE = 1.0       # 否定词候选: 最低花费 ($)
MIN_CLICKS_NEGATIVE = 10       # 否定词候选: 最低点击量
WASTE_ACOS_THRESHOLD = 0.80    # ACOS > 80% 标记为低效

# ── 搜索词分类规则 ─────────────────────────────────────
# 品牌词（你的品牌/店铺名，按实际调整）
BRAND_TERMS = {"senight", "snight", "如森"}
# 竞品品牌词（常见枕头品类竞品）
COMPETITOR_BRANDS = {"tempur", "sealy", "simmons", "my pillow", "coop", "sutera",
                      "beckham", "utopia", "epabo", "snuggle", "mlily", "zamat",
                      "cushion lab", "eli", "yippo", "sweetnight", "weekender",
                      "coisum", "vicks", "ziraki", "pancake", "linenspa",
                      "dreamfit", "mediflow", "sleep number", "purple",
                      "casper", "nectar", "ghostbed", "avocado", "saatva",
                      "leesa", "helix", "amerisleep", "bear", "puffy"}
# 垃圾词/不相关词根
JUNK_ROOTS = {"cheap", "free", "used", "wholesale", "refurbished", "bulk",
              "second hand", "return", "clearance", "liquidation",
              "parts", "repair", "manual", "instruction", "recipe", "book",
              "poster", "print", "sticker", "toy", "game", "costume",
              "clothing", "shoes", "socks", "underwear", "food", "candy",
              "camera", "phone", "computer", "cable", "battery", "sofa",
              "table", "chair", "desk", "lamp", "rug", "curtain", "tv",
              "monitor", "speaker", "headphone", "watch", "jewelry",
              "basketball", "football", "yoga mat", "dumbbell",
              "cat", "dog", "pet", "fish", "bird", "rabbit",
              "car", "motorcycle", "bicycle", "truck", "boat",
              "drill", "hammer", "screwdriver", "wrench", "tool",
              "makeup", "lipstick", "nail polish", "perfume",
              "supplement", "vitamin", "protein", "tea", "coffee",
              "massage", "chiropractor", "doctor", "surgery"}

# 品类核心词根（枕头相关品类）
CATEGORY_ROOTS = {"pillow", "cushion", "bolster", "headboard", "headrest",
                  "mattress", "topper", "bed", "sleep", "bedding",
                  "neck", "back", "lumbar", "support", "memory foam",
                  "gel", "cooling", "bamboo", "shredded", "down",
                  "feather", "cotton", "polyester", "microfiber",
                  "wedge", "body", "pregnancy", "maternity", "knee",
                  "leg", "foot", "arm", "chair pad", "seat", "throw",
                  "decorative", "euro", "sham", "case", "cover",
                  "orthopedic", "cervical", "ergonomic", "hotel",
                  "luxury", "firm", "soft", "side", "stomach", "back"}


def _safe_num(series):
    import pandas as pd
    return pd.to_numeric(series, errors="coerce")


def classify_search_term(term):
    """基于规则匹配对搜索词进行分类。"""
    if not isinstance(term, str) or not term.strip():
        return "其他"
    lower = term.lower().strip()

    # 品牌词: 包含自己品牌名
    for b in BRAND_TERMS:
        if b in lower:
            return "品牌词"

    # 竞品词: 包含竞品品牌名
    for c in COMPETITOR_BRANDS:
        if c in lower:
            return "竞品词"

    # 垃圾词: 包含不相关词根
    for j in JUNK_ROOTS:
        if j in lower:
            return "不相关词"

    # 品类词: 包含枕头相关词根
    for cat in CATEGORY_ROOTS:
        if cat in lower:
            return "品类词"

    # 长尾词: 3个词以上
    if len(lower.split()) >= 4:
        return "长尾词"

    return "其他"


def analyze(df):
    import pandas as pd
    df = df.copy()
    for col in ("spend", "sales_7d", "orders_7d", "units_7d", "clicks", "impressions",
                "acos", "roas", "ctr", "cpc", "conversion_rate_7d"):
        if col in df.columns:
            df[col] = _safe_num(df[col])

    # 补充计算 ACOS（如果缺失）
    if "acos" in df.columns and df["acos"].isna().sum() > len(df) * 0.5:
        mask = df["sales_7d"].notna() & (df["sales_7d"] > 0)
        df.loc[mask, "acos"] = df.loc[mask, "spend"] / df.loc[mask, "sales_7d"]

    # ── 关键词收割 ────────────────────────────────────
    harvest_mask = (
        (df["clicks"] >= MIN_CLICKS_HARVEST)
        & (df["orders_7d"].fillna(0) > 0)
        & (df["acos"].notna())
        & (df["acos"] < MAX_ACOS_HARVEST)
    )
    harvest = df[harvest_mask].sort_values(["orders_7d", "sales_7d"], ascending=[False, False])
    harvest_cols = ["search_term", "campaign_name", "match_type", "clicks", "impressions",
                     "orders_7d", "sales_7d", "spend", "acos", "roas", "ctr", "cpc"]
    hcols = [c for c in harvest_cols if c in df.columns]
    harvest_list = harvest[hcols].head(100).to_dict(orient="records")
    for r in harvest_list:
        for k in r:
            if isinstance(r[k], (np.floating,)):
                r[k] = round(float(r[k]), 4)
            elif pd.isna(r[k]):
                r[k] = None

    # ── 否定词候选 ────────────────────────────────────
    negative_mask = (
        (df["spend"] >= MIN_SPEND_NEGATIVE)
        & (df["clicks"] >= MIN_CLICKS_NEGATIVE)
        & (df["orders_7d"].fillna(0) == 0)
    )
    negatives = df[negative_mask].sort_values("spend", ascending=False)
    ncols = [c for c in harvest_cols if c in df.columns]
    negative_list = negatives[ncols].head(100).to_dict(orient="records")
    for r in negative_list:
        for k in r:
            if isinstance(r[k], (np.floating,)):
                r[k] = round(float(r[k]), 4)
            elif pd.isna(r[k]):
                r[k] = None

    # ── 浪费支出排行 ──────────────────────────────────
    if "acos" in df.columns:
        waste = df[df["acos"].notna() & (df["acos"] > WASTE_ACOS_THRESHOLD)]
        waste = waste.sort_values("spend", ascending=False)
        waste_list = waste[hcols].head(50).to_dict(orient="records")
        for r in waste_list:
            for k in r:
                if isinstance(r[k], (np.floating,)):
                    r[k] = round(float(r[k]), 4)
                elif pd.isna(r[k]):
                    r[k] = None
    else:
        waste_list = []

    # ── 搜索词分类 ────────────────────────────────────
    if "search_term" in df.columns:
        df["term_category"] = df["search_term"].apply(classify_search_term)
        cat_stats = df.groupby("term_category").agg(
            spend=("spend", "sum"),
            sales_7d=("sales_7d", "sum"),
            orders_7d=("orders_7d", "sum"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            count=("search_term", "count"),
        ).reset_index()
        cat_stats["acos"] = cat_stats["spend"] / cat_stats["sales_7d"].replace(0, np.nan)
        cat_stats["roas"] = cat_stats["sales_7d"] / cat_stats["spend"].replace(0, np.nan)
        category_list = cat_stats.to_dict(orient="records")
        for r in category_list:
            for k in r:
                if isinstance(r[k], (np.floating,)):
                    r[k] = round(float(r[k]), 4)
                elif pd.isna(r[k]):
                    r[k] = None
    else:
        category_list = []

    # ── 汇总 ──────────────────────────────────────────
    total_spend = df["spend"].sum()
    total_sales = df["sales_7d"].sum()
    summary = {
        "search_term_count": len(df),
        "total_spend": round(float(total_spend), 2),
        "total_sales_7d": round(float(total_sales), 2),
        "total_orders_7d": int(df["orders_7d"].sum()) if "orders_7d" in df.columns else 0,
        "total_clicks": int(df["clicks"].sum()) if "clicks" in df.columns else 0,
        "harvest_count": len(harvest_list),
        "negative_candidate_count": len(negative_list),
        "negative_wasted_spend": round(float(negatives["spend"].sum()), 2),
        "waste_count": len(waste_list),
    }

    return {
        "summary": summary,
        "harvest_keywords": harvest_list,
        "negative_candidates": negative_list,
        "waste_ranking": waste_list,
        "category_distribution": category_list,
        "thresholds": {
            "min_clicks_harvest": MIN_CLICKS_HARVEST,
            "max_acos_harvest": MAX_ACOS_HARVEST,
            "min_spend_negative": MIN_SPEND_NEGATIVE,
            "min_clicks_negative": MIN_CLICKS_NEGATIVE,
            "waste_acos_threshold": WASTE_ACOS_THRESHOLD,
        },
    }


if __name__ == "__main__":
    reports = load_data()
    if "search_term" not in reports:
        print("错误: 未找到搜索词报告")
        exit(1)
    result = analyze(reports["search_term"])
    save_json(result, "search_term_analysis.json")
    s = result["summary"]
    print(f"\n搜索词分析:")
    print(f"  搜索词总数: {s['search_term_count']}")
    print(f"  总花费: ${s['total_spend']:,.2f}")
    print(f"  关键词收割: {s['harvest_count']}个")
    print(f"  否定词候选: {s['negative_candidate_count']}个 (浪费${s['negative_wasted_spend']:,.2f})")
    print(f"  浪费低效词: {s['waste_count']}个")
    print(f"  搜索词分类: {len(result['category_distribution'])}类")
