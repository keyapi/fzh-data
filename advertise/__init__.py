"""
Amazon 广告数据加载模块 — 中文列名 → 英文标准字段名映射 + 自动加载。
"""
import json
import os
import pandas as pd

# ── 4 份报告的中文列名 → 英文标准字段名映射 ──────────────────────────

CAMPAIGN_COLUMN_MAP = {
    "开始日期": "start_date",
    "结束日期": "end_date",
    "广告组合名称": "portfolio_name",
    "广告活动类型": "campaign_type",
    "广告活动名称": "campaign_name",
    "零售商": "retailer",
    "国家/地区": "country",
    "状态": "status",
    "货币": "currency",
    "预算": "budget",
    "定位类型": "targeting_type",
    "竞价策略": "bidding_strategy",
    "展示量": "impressions",
    "去年曝光量": "impressions_dedup",
    "点击量": "clicks",
    "去年点击量": "clicks_dedup",
    "点击率 (CTR)": "ctr",
    "花费": "spend",
    "去年支出": "spend_dedup",
    "单次点击成本 (CPC)": "cpc",
    "去年每次点击成本(CPC)": "cpc_dedup",
    "7天总订单数(#)": "orders_7d",
    "广告投入产出比 (ACOS) 总计": "acos",
    "总广告投资回报率 (ROAS)": "roas",
    "7天总销售额": "sales_7d",
}

TARGETING_COLUMN_MAP = {
    "开始日期": "start_date",
    "结束日期": "end_date",
    "广告组合名称": "portfolio_name",
    "货币": "currency",
    "广告活动名称": "campaign_name",
    "国家/地区": "country",
    "广告组名称": "ad_group_name",
    "零售商": "retailer",
    "投放": "targeting",
    "匹配类型": "match_type",
    "展示量": "impressions",
    "搜索结果首页首位展示量份额": "top_search_is",
    "点击量": "clicks",
    "点击率 (CTR)": "ctr",
    "单次点击成本 (CPC)": "cpc",
    "花费": "spend",
    "广告投入产出比 (ACOS) 总计": "acos",
    "总广告投资回报率 (ROAS)": "roas",
    "7天总销售额": "sales_7d",
    "7天总订单数(#)": "orders_7d",
    "7天总销售量(#)": "units_7d",
    "7天的转化率": "conversion_rate_7d",
    "7天内广告SKU销售量(#)": "advertised_sku_units_7d",
    "7天内其他SKU销售量(#)": "other_sku_units_7d",
    "7天内广告SKU销售额": "advertised_sku_sales_7d",
    "7天内其他SKU销售额": "other_sku_sales_7d",
}

SEARCH_TERM_COLUMN_MAP = {
    "开始日期": "start_date",
    "结束日期": "end_date",
    "广告组合名称": "portfolio_name",
    "货币": "currency",
    "广告活动名称": "campaign_name",
    "广告组名称": "ad_group_name",
    "零售商": "retailer",
    "国家/地区": "country",
    "投放": "targeting",
    "匹配类型": "match_type",
    "客户搜索词": "search_term",
    "展示量": "impressions",
    "点击量": "clicks",
    "点击率 (CTR)": "ctr",
    "单次点击成本 (CPC)": "cpc",
    "花费": "spend",
    "7天总销售额": "sales_7d",
    "广告投入产出比 (ACOS) 总计": "acos",
    "总广告投资回报率 (ROAS)": "roas",
    "7天总订单数(#)": "orders_7d",
    "7天总销售量(#)": "units_7d",
    "7天的转化率": "conversion_rate_7d",
    "7天内广告SKU销售量(#)": "advertised_sku_units_7d",
    "7天内其他SKU销售量(#)": "other_sku_units_7d",
    "7天内广告SKU销售额": "advertised_sku_sales_7d",
    "7天内其他SKU销售额": "other_sku_sales_7d",
}

PLACEMENT_COLUMN_MAP = {
    "开始日期": "start_date",
    "结束日期": "end_date",
    "广告组合名称": "portfolio_name",
    "货币": "currency",
    "广告活动名称": "campaign_name",
    "零售商": "retailer",
    "国家/地区": "country",
    "竞价策略": "bidding_strategy",
    "放置": "placement",
    "展示量": "impressions",
    "点击量": "clicks",
    "单次点击成本 (CPC)": "cpc",
    "花费": "spend",
    "7天总销售额": "sales_7d",
    "广告投入产出比 (ACOS) 总计": "acos",
    "总广告投资回报率 (ROAS)": "roas",
    "7天总订单数(#)": "orders_7d",
    "7天总销售量(#)": "units_7d",
}

# 文件名关键字 → (列名映射, 报告类型)
_FILE_PATTERNS = [
    ("广告活动", CAMPAIGN_COLUMN_MAP, "campaign"),
    ("投放", TARGETING_COLUMN_MAP, "targeting"),
    ("搜索词", SEARCH_TERM_COLUMN_MAP, "search_term"),
    ("广告位", PLACEMENT_COLUMN_MAP, "placement"),
]


def _detect_report(filename):
    """根据文件名识别报告类型。"""
    for keyword, col_map, rtype in _FILE_PATTERNS:
        if keyword in filename:
            return col_map, rtype
    return None, None


def load_data(base_path=None):
    """扫描数据源目录，加载全部 4 份报告，返回 {report_type: DataFrame}。

    自动识别文件名中的关键字（广告活动/投放/搜索词/广告位），
    应用中文→英文列名映射，将百分比转为小数，日期列标准化。
    """
    if base_path is None:
        base_path = os.path.join(os.path.dirname(__file__), "数据源")

    # 如果 base_path 下还有一个子目录，自动进入
    entries = os.listdir(base_path)
    if len(entries) == 1 and os.path.isdir(os.path.join(base_path, entries[0])):
        base_path = os.path.join(base_path, entries[0])

    reports = {}
    for fname in os.listdir(base_path):
        if not fname.endswith((".xlsx", ".csv")):
            continue
        fpath = os.path.join(base_path, fname)
        col_map, rtype = _detect_report(fname)
        if col_map is None:
            print(f"  [跳过] 无法识别报告类型: {fname}")
            continue

        if fname.endswith(".csv"):
            df = pd.read_csv(fpath, encoding="utf-8")
        else:
            df = pd.read_excel(fpath)

        df = df.rename(columns=col_map)
        df = df[[c for c in col_map.values() if c in df.columns]]

        # 清洗货币字符串 ($1,234.56 → 1234.56)
        import pandas.api.types as pat
        money_cols = ["spend", "sales_7d", "budget", "cpc", "cpc_dedup",
                       "spend_dedup", "advertised_sku_sales_7d", "other_sku_sales_7d"]
        for mc in money_cols:
            if mc in df.columns and not pat.is_numeric_dtype(df[mc]):
                df[mc] = df[mc].astype(str).str.replace(r"[$,\s]", "", regex=True)
                df[mc] = pd.to_numeric(df[mc], errors="coerce")

        # 百分比列 → 小数（如果原始是百分号字符串或 >1 的值）
        for pct_col in ("acos", "ctr", "conversion_rate_7d", "top_search_is"):
            if pct_col in df.columns:
                df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")
                # 如果中位数 > 1，说明是百分比整数（如 30 = 30%），转为小数
                med = df[pct_col].dropna().median()
                if pd.notna(med) and med > 1:
                    df[pct_col] = df[pct_col] / 100.0

        # 日期标准化
        for date_col in ("start_date", "end_date"):
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

        reports[rtype] = df
        print(f"  [加载] {rtype}: {len(df)} 行 × {len(df.columns)} 列  ← {fname}")

    return reports


def save_json(data, filename):
    """保存分析结果到 out/ 目录，处理 numpy 类型序列化。"""
    import numpy as np

    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    fpath = os.path.join(out_dir, filename)

    class Encoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                if pd.isna(obj):
                    return None
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            return super().default(obj)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=Encoder)
    print(f"  [保存] {fpath}")
    return fpath
