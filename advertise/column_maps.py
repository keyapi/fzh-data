"""API-format xlsx column mappings — Sellfox API → English field names.
These map the Chinese headers from Sellfox API downloaded xlsx files.
Column definitions from: advertise/docs/reference/sp-report-column-reference.md
"""
import os

# ── SP Campaign (API xlsx) — 26 columns ─────────────────────────────────
CAMPAIGN_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "conversion_rate",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "same_sku_orders",
    "其他产品广告订单量": "other_sku_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "same_sku_sales",
    "其他产品广告销售额": "other_sku_sales",
    "广告销量": "units",
    "本广告产品销量": "same_sku_units",
    "其他产品广告销量": "other_sku_units",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "广告活动运行状态": "status",
    "广告组合ID": "portfolio_id",
    "广告活动ID": "campaign_id",
}

# ── SP Targeting (API xlsx) — 30 columns ────────────────────────────────
TARGETING_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "投放": "targeting",
    "匹配类型": "match_type",
    "广告组": "ad_group_name",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "conversion_rate",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "same_sku_orders",
    "其他产品广告订单量": "other_sku_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "same_sku_sales",
    "其他产品广告销售额": "other_sku_sales",
    "广告销量": "units",
    "本广告产品销量": "same_sku_units",
    "其他产品广告销量": "other_sku_units",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "投放运行状态": "status",
    "广告活动ID": "campaign_id",
    "广告组ID": "ad_group_id",
    "广告投放ID": "target_id",
}

# ── SP Search Term (API xlsx) — 32 columns ──────────────────────────────
SEARCH_TERM_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "用户搜索词": "search_term",
    "投放": "targeting",
    "匹配类型": "match_type",
    "广告活动": "campaign_name",
    "广告组": "ad_group_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "conversion_rate",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "same_sku_orders",
    "其他产品广告订单量": "other_sku_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "same_sku_sales",
    "其他产品广告销售额": "other_sku_sales",
    "广告销量": "units",
    "本广告产品销量": "same_sku_units",
    "其他产品广告销量": "other_sku_units",
    "广告组合名称": "portfolio_name",
    "币种": "currency",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "广告活动ID": "campaign_id",
    "广告组ID": "ad_group_id",
    "广告投放ID": "target_id",
}

# ── SP Placement (API xlsx) — 26 columns ────────────────────────────────
PLACEMENT_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "广告位": "placement",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "conversion_rate",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "same_sku_orders",
    "其他产品广告订单量": "other_sku_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "same_sku_sales",
    "其他产品广告销售额": "other_sku_sales",
    "广告销量": "units",
    "本广告产品销量": "same_sku_units",
    "其他产品广告销量": "other_sku_units",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "广告活动运行状态": "status",
    "广告活动ID": "campaign_id",
}

# ── SP Ad Group (API xlsx) — 27 columns ─────────────────────────────────
AD_GROUP_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "广告组": "ad_group_name",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "conversion_rate",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "same_sku_orders",
    "其他产品广告订单量": "other_sku_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "same_sku_sales",
    "其他产品广告销售额": "other_sku_sales",
    "广告销量": "units",
    "本广告产品销量": "same_sku_units",
    "其他产品广告销量": "other_sku_units",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "广告组运行状态": "status",
    "广告活动ID": "campaign_id",
    "广告组ID": "ad_group_id",
}

# ── SP Advertised Product (API xlsx) — 30 columns ───────────────────────
ADVERTISED_PRODUCT_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "asin": "asin",
    "sku": "sku",
    "广告组": "ad_group_name",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "广告花费": "spend",
    "广告曝光量": "impressions",
    "广告点击量": "clicks",
    "CPC": "cpc",
    "广告点击率": "ctr",
    "广告转化率": "conversion_rate",
    "ACoS": "acos",
    "ROAS": "roas",
    "广告订单量": "orders",
    "本广告产品订单量": "same_sku_orders",
    "其他产品广告订单量": "other_sku_orders",
    "广告销售额": "sales",
    "本广告产品销售额": "same_sku_sales",
    "其他产品广告销售额": "other_sku_sales",
    "广告销量": "units",
    "本广告产品销量": "same_sku_units",
    "其他产品广告销量": "other_sku_units",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "广告产品运行状态": "status",
    "广告活动ID": "campaign_id",
    "广告组ID": "ad_group_id",
    "广告产品ID": "ad_product_id",
}

# ── SP Purchased Item (API xlsx) — 16 columns ───────────────────────────
PURCHASED_ITEM_COLUMN_MAP_API = {
    "店铺": "shop_name",
    "日期": "date",
    "ASIN": "advertised_asin",
    "SKU": "advertised_sku",
    "投放": "targeting",
    "匹配类型": "match_type",
    "其他ASIN": "purchased_asin",
    "广告组": "ad_group_name",
    "广告活动": "campaign_name",
    "定位类型": "targeting_type",
    "其他SKU销量": "purchased_units",
    "其他SKU销售额": "purchased_sales",
    "广告活动开始时间": "start_date",
    "广告活动结束时间": "end_date",
    "广告活动ID": "campaign_id",
    "广告组ID": "ad_group_id",
}

# ── SP Business Report (API xlsx) — 26 columns ──────────────────────────
# Same schema as Placement, with placement values like "产品页面(企业购广告位)"
BUSINESS_COLUMN_MAP_API = PLACEMENT_COLUMN_MAP_API.copy()

# ── Consolidated maps for API format ─────────────────────────────────────
_API_MAPS = {
    "campaign": CAMPAIGN_COLUMN_MAP_API,
    "targeting": TARGETING_COLUMN_MAP_API,
    "search_term": SEARCH_TERM_COLUMN_MAP_API,
    "placement": PLACEMENT_COLUMN_MAP_API,
    "ad_group": AD_GROUP_COLUMN_MAP_API,
    "advertised_product": ADVERTISED_PRODUCT_COLUMN_MAP_API,
    "purchased_item": PURCHASED_ITEM_COLUMN_MAP_API,
    "business": BUSINESS_COLUMN_MAP_API,
}

# ── API file name → report type detection ───────────────────────────────
_API_FILE_PATTERNS = [
    ("Campaign", _API_MAPS["campaign"], "campaign"),
    ("Targeting", _API_MAPS["targeting"], "targeting"),
    ("SearchTerm", _API_MAPS["search_term"], "search_term"),
    ("Placement", _API_MAPS["placement"], "placement"),
    ("AdGroup", _API_MAPS["ad_group"], "ad_group"),
    ("AdvertisedProduct", _API_MAPS["advertised_product"], "advertised_product"),
    ("PurchasedItem", _API_MAPS["purchased_item"], "purchased_item"),
    ("BusinessReport", _API_MAPS["business"], "business"),
]


def get_api_map(report_type):
    """Return the API column map for a given report type key."""
    return _API_MAPS.get(report_type)


def detect_api_format(df):
    """Return True if the dataframe uses API-format Chinese column names."""
    return "店铺" in df.columns


def detect_api_report(filename):
    """Detect SP report type from API-format filename.
    Skips SB- and SD- prefixed files (those are separate report types).
    """
    # SB/SD files have different schemas — skip them
    base = os.path.basename(filename)
    if base.startswith("SB-") or base.startswith("SD-"):
        return None, None
    for keyword, col_map, rtype in _API_FILE_PATTERNS:
        if keyword in filename:
            return col_map, rtype
    return None, None
