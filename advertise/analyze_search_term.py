"""
客户搜索词层分析 — 聚合 → 5 桶分类 → 操作建议。

核心流程（对齐 Trellis/WisePPC/SellerSprite 2026 标准）：
1. 按 search_term 聚合（消除同一词分散在多行的失真）
2. 计算统一指标（CTR/CPC/ACoS/ROAS/CVR）
3. 5 桶分类: Harvest / Negate / Monitor / Protect / Ignore
4. 搜索词语义分类（品牌/品类/竞品/长尾/不相关）
5. 生成决策日志（差异化上次运行）

参考:
- Trellis Search Term Report Workflow
- WisePPC 2026 搜索词报告优化指南
- SellerSprite Amazon PPC Optimization Playbook 2026
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from advertise import load_data, save_json

# ── 可配置阈值（对齐 2026 行业标准）────────────────────

# Harvest 收割: 已验证的高转化词 → 建议加入精准匹配
MIN_ORDERS_HARVEST = 2          # 最少订单数（1个是巧合, 2+是信号）
MAX_ACOS_HARVEST = 0.30         # 最大 ACoS（取决于产品毛利率）

# Negate 否定: 花钱不转化的词 → 建议屏蔽
MIN_CLICKS_NEGATE = 15          # 最少点击量（< 15 是小样本, 不是判决）
MIN_SPEND_NEGATE = 2.0          # 最低花费 ($)

# Monitor 观察: 数据量不足，暂不决策
MAX_CLICKS_MONITOR = 15         # 点击量低于此值 → 观察

# Ignore 忽略: 花费可忽略不计
MAX_SPEND_IGNORE = 1.0          # 花费低于此值 → 忽略
MAX_CLICKS_IGNORE = 5           # 点击量低于此值 → 忽略

# 归因窗口警告
ATTRIBUTION_WINDOW_DAYS = 7     # SP 广告 7 天点击归因
MIN_REPORT_DAYS = 14            # 报告期最少天数（确保归因完整）

# Protect 保护: 品牌词/战略词列表（按实际维护）
PROTECTED_TERMS = set()

# ── 搜索词语义分类规则 ─────────────────────────────────
BRAND_TERMS = {"senight", "snight", "如森"}
COMPETITOR_BRANDS = {"tempur", "sealy", "simmons", "my pillow", "coop", "sutera",
                      "beckham", "utopia", "epabo", "snuggle", "mlily", "zamat",
                      "cushion lab", "eli", "yippo", "sweetnight", "weekender",
                      "coisum", "vicks", "ziraki", "pancake", "linenspa",
                      "dreamfit", "mediflow", "sleep number", "purple",
                      "casper", "nectar", "ghostbed", "avocado", "saatva",
                      "leesa", "helix", "amerisleep", "bear", "puffy"}
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
    return pd.to_numeric(series, errors="coerce")


def classify_term_category(term):
    """基于规则匹配对搜索词语义分类。"""
    if not isinstance(term, str) or not term.strip():
        return "其他"
    lower = term.lower().strip()
    for b in BRAND_TERMS:
        if b in lower:
            return "品牌词"
    for c in COMPETITOR_BRANDS:
        if c in lower:
            return "竞品词"
    for j in JUNK_ROOTS:
        if j in lower:
            return "不相关词"
    for cat in CATEGORY_ROOTS:
        if cat in lower:
            return "品类词"
    if len(lower.split()) >= 4:
        return "长尾词"
    return "其他"


def _serialize(val):
    """安全序列化 numpy/pandas 值。"""
    if isinstance(val, list):
        return val
    if isinstance(val, (np.floating,)):
        if pd.isna(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (np.integer,)):
        return int(val)
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass
    return val


def analyze(df):
    df = df.copy()

    # ── Step 0: 数值化 + 日期范围检查 ──────────────────
    metric_cols = ("spend", "sales_7d", "orders_7d", "units_7d", "clicks",
                    "impressions", "acos", "roas", "ctr", "cpc", "conversion_rate_7d")
    for col in metric_cols:
        if col in df.columns:
            df[col] = _safe_num(df[col])

    report_days = None
    if "start_date" in df.columns and "end_date" in df.columns:
        min_date = pd.to_datetime(df["start_date"]).min()
        max_date = pd.to_datetime(df["end_date"]).max()
        report_days = (max_date - min_date).days + 1

    # ── Step 1: 按 search_term 聚合 ─────────────────────
    if "search_term" not in df.columns:
        raise ValueError("搜索词报告缺少 'search_term'（客户搜索词）列")

    agg_spec = {
        "spend": "sum",
        "sales_7d": "sum",
        "orders_7d": "sum",
        "units_7d": "sum",
        "clicks": "sum",
        "impressions": "sum",
    }
    # 收集每个搜索词关联的广告活动和匹配类型
    contrib_spec = {}
    if "campaign_name" in df.columns:
        contrib_spec["campaign_name"] = lambda x: list(x.unique())
    if "match_type" in df.columns:
        contrib_spec["match_type"] = lambda x: list(x.unique())
    if "targeting" in df.columns:
        contrib_spec["targeting"] = lambda x: list(x.unique())

    grp = df.groupby("search_term", dropna=True)
    aggregated = grp.agg({**agg_spec, **contrib_spec})

    # ── Step 2: 计算统一指标 ────────────────────────────
    aggregated["ctr"] = aggregated["clicks"] / aggregated["impressions"].replace(0, np.nan)
    aggregated["cpc"] = aggregated["spend"] / aggregated["clicks"].replace(0, np.nan)
    aggregated["acos"] = np.where(
        aggregated["sales_7d"] > 0,
        aggregated["spend"] / aggregated["sales_7d"],
        np.nan,
    )
    aggregated["roas"] = np.where(
        aggregated["spend"] > 0,
        aggregated["sales_7d"] / aggregated["spend"],
        np.nan,
    )
    aggregated["cvr"] = aggregated["orders_7d"] / aggregated["clicks"].replace(0, np.nan)

    # 语义分类
    aggregated["term_category"] = aggregated.index.map(classify_term_category)

    # ── Step 3: 5 桶分类 ────────────────────────────────
    terms = aggregated.reset_index()
    n_total = len(terms)

    # Protect 保护（品牌/战略词 — 需手动维护 PROTECTED_TERMS）
    protect_mask = terms["search_term"].isin(PROTECTED_TERMS)

    # Harvest 收割
    harvest_mask = (
        (~protect_mask)
        & (terms["orders_7d"] >= MIN_ORDERS_HARVEST)
        & (terms["acos"].notna())
        & (terms["acos"] <= MAX_ACOS_HARVEST)
    )

    # Negate 否定（注意：必须在 Protect 和 Harvest 之后判断）
    negate_clicks_mask = (
        (~protect_mask)
        & (~harvest_mask)
        & (terms["clicks"] >= MIN_CLICKS_NEGATE)
        & (terms["spend"] >= MIN_SPEND_NEGATE)
        & (terms["orders_7d"].fillna(0) == 0)
    )
    # 不相关词直接否定（不管点击量）
    negate_irrelevant_mask = (
        (~protect_mask)
        & (~harvest_mask)
        & (terms["term_category"] == "不相关词")
        & (terms["spend"] >= MIN_SPEND_NEGATE)
        & (terms["orders_7d"].fillna(0) == 0)
    )
    negate_mask = negate_clicks_mask | negate_irrelevant_mask

    # Ignore 忽略
    ignore_mask = (
        (~protect_mask)
        & (~harvest_mask)
        & (~negate_mask)
        & (terms["spend"] < MAX_SPEND_IGNORE)
        & (terms["clicks"] < MAX_CLICKS_IGNORE)
    )

    # Monitor 观察（其余）
    already_classified = protect_mask | harvest_mask | negate_mask | ignore_mask
    monitor_mask = ~already_classified

    terms["bucket"] = "Monitor"
    terms.loc[protect_mask, "bucket"] = "Protect"
    terms.loc[harvest_mask, "bucket"] = "Harvest"
    terms.loc[negate_mask, "bucket"] = "Negate"
    terms.loc[ignore_mask, "bucket"] = "Ignore"

    # ── Step 4: 输出序列化 ──────────────────────────────
    output_cols = [
        "search_term", "bucket", "term_category",
        "spend", "sales_7d", "orders_7d", "clicks", "impressions",
        "acos", "roas", "ctr", "cpc", "cvr",
        "campaign_name", "match_type",
    ]
    avail = [c for c in output_cols if c in terms.columns]

    def _bucket_list(df, bucket_name, sort_by="spend", limit=200):
        subset = df[df["bucket"] == bucket_name].sort_values(sort_by, ascending=False)
        result = subset[avail].head(limit).to_dict(orient="records")
        for r in result:
            for k, v in r.items():
                r[k] = _serialize(v)
        return result

    harvest_list = _bucket_list(terms, "Harvest", sort_by="sales_7d")
    negate_list = _bucket_list(terms, "Negate", sort_by="spend")
    monitor_list = _bucket_list(terms, "Monitor", sort_by="spend")
    protect_list = _bucket_list(terms, "Protect", sort_by="spend")

    # ── Step 5: 搜索词分类统计（基于聚合后数据）─────────
    cat_stats = terms.groupby("term_category").agg(
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
        for k, v in r.items():
            r[k] = _serialize(v)

    # ── Step 6: 桶分布统计 ──────────────────────────────
    bucket_counts = terms["bucket"].value_counts().to_dict()
    negate_spend = float(terms.loc[terms["bucket"] == "Negate", "spend"].sum())
    harvest_spend = float(terms.loc[terms["bucket"] == "Harvest", "spend"].sum())
    harvest_sales = float(terms.loc[terms["bucket"] == "Harvest", "sales_7d"].sum())
    monitor_spend = float(terms.loc[terms["bucket"] == "Monitor", "spend"].sum())

    # ── Step 7: 汇总 ────────────────────────────────────
    summary = {
        "raw_row_count": len(df),
        "unique_search_terms": n_total,
        "total_spend": round(float(terms["spend"].sum()), 2),
        "total_sales_7d": round(float(terms["sales_7d"].sum()), 2),
        "total_orders_7d": int(terms["orders_7d"].sum()),
        "total_clicks": int(terms["clicks"].sum()),
        "report_days": report_days,
        "attribution_warning": (
            f"报告期 {report_days} 天 < 推荐最小 {MIN_REPORT_DAYS} 天（SP 7天点击归因）。"
            f"末尾 {ATTRIBUTION_WINDOW_DAYS} 天归因可能不完整。"
        ) if report_days and report_days < MIN_REPORT_DAYS else None,
        "buckets": {
            "Harvest": {"count": int(bucket_counts.get("Harvest", 0)),
                         "spend": round(harvest_spend, 2),
                         "sales": round(harvest_sales, 2)},
            "Negate": {"count": int(bucket_counts.get("Negate", 0)),
                        "spend": round(negate_spend, 2)},
            "Monitor": {"count": int(bucket_counts.get("Monitor", 0)),
                         "spend": round(monitor_spend, 2)},
            "Protect": {"count": int(bucket_counts.get("Protect", 0))},
            "Ignore": {"count": int(bucket_counts.get("Ignore", 0))},
        },
    }

    return {
        "summary": summary,
        "harvest_keywords": harvest_list,
        "negative_candidates": negate_list,
        "monitor_list": monitor_list,
        "protect_list": protect_list,
        "category_distribution": category_list,
        "thresholds": {
            "min_orders_harvest": MIN_ORDERS_HARVEST,
            "max_acos_harvest": MAX_ACOS_HARVEST,
            "min_clicks_negate": MIN_CLICKS_NEGATE,
            "min_spend_negate": MIN_SPEND_NEGATE,
            "max_clicks_monitor": MAX_CLICKS_MONITOR,
            "max_spend_ignore": MAX_SPEND_IGNORE,
            "max_clicks_ignore": MAX_CLICKS_IGNORE,
            "attribution_window_days": ATTRIBUTION_WINDOW_DAYS,
            "min_report_days": MIN_REPORT_DAYS,
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
    print(f"\n搜索词分析 (聚合 → 5桶分类):")
    print(f"  原始行数: {s['raw_row_count']}")
    print(f"  去重搜索词: {s['unique_search_terms']}")
    print(f"  总花费: ${s['total_spend']:,.2f}")
    print(f"  总销售额(7d): ${s['total_sales_7d']:,.2f}")
    if s.get("attribution_warning"):
        print(f"  ⚠️ 归因警告: {s['attribution_warning']}")
    print(f"  桶分布:")
    for name, info in s["buckets"].items():
        extra = ""
        if info.get("spend"):
            extra = f" — ${info['spend']:,.2f}"
        if info.get("sales"):
            extra += f" 销售${info['sales']:,.2f}"
        print(f"    {name}: {info['count']}个{extra}")
    print(f"  分类: {len(result['category_distribution'])}类")
