"""
Amazon ad data loader — supports Console CSV + API xlsx formats.
Shared column mappings live in column_maps.py; utilities in utils.py.
"""
import json
import os
import numpy as np
import pandas as pd
from advertise.utils import save_json as _save_json
from advertise.column_maps import detect_api_format, detect_api_report, _API_MAPS

# ── Console CSV column maps (legacy, kept for backward compatibility) ────
from advertise.column_maps import (
    CAMPAIGN_COLUMN_MAP_API    as CAMPAIGN_COLUMN_MAP,
    TARGETING_COLUMN_MAP_API   as TARGETING_COLUMN_MAP,
    SEARCH_TERM_COLUMN_MAP_API as SEARCH_TERM_COLUMN_MAP,
    PLACEMENT_COLUMN_MAP_API   as PLACEMENT_COLUMN_MAP,
    AD_GROUP_COLUMN_MAP_API,
    ADVERTISED_PRODUCT_COLUMN_MAP_API,
    PURCHASED_ITEM_COLUMN_MAP_API,
    BUSINESS_COLUMN_MAP_API,
)

# Re-export for backward compatibility (existing scripts import from advertise)
save_json = _save_json

# Console CSV filename detection (legacy)
_FILE_PATTERNS = [
    ("广告活动", CAMPAIGN_COLUMN_MAP, "campaign"),
    ("投放", TARGETING_COLUMN_MAP, "targeting"),
    ("搜索词", SEARCH_TERM_COLUMN_MAP, "search_term"),
    ("广告位", PLACEMENT_COLUMN_MAP, "placement"),
]


def _detect_report(filename):
    for keyword, col_map, rtype in _FILE_PATTERNS:
        if keyword in filename:
            return col_map, rtype
    return None, None


def _load_single_file(fpath):
    """Load a single xlsx or csv file, returning DataFrame."""
    if fpath.endswith(".csv"):
        return pd.read_csv(fpath, encoding="utf-8")
    return pd.read_excel(fpath)


def _clean_api_data(df):
    """Clean API-format data (already numeric, no $ prefix, percentages as decimals).
    Only runs date normalization since API xlsx has clean float64 values."""
    for date_col in ("start_date", "end_date"):
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df


def _clean_console_data(df):
    """Clean Console-format CSV data: strip $ from money, normalize percentages."""
    import pandas.api.types as pat
    money_cols = ["spend", "sales_7d", "budget", "cpc", "cpc_dedup",
                   "spend_dedup", "advertised_sku_sales_7d", "other_sku_sales_7d"]
    for mc in money_cols:
        if mc in df.columns and not pat.is_numeric_dtype(df[mc]):
            df[mc] = df[mc].astype(str).str.replace(r"[$,\s]", "", regex=True)
            df[mc] = pd.to_numeric(df[mc], errors="coerce")

    for pct_col in ("acos", "ctr", "conversion_rate_7d", "top_search_is"):
        if pct_col in df.columns:
            df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")
            med = df[pct_col].dropna().median()
            if pd.notna(med) and med > 1:
                df[pct_col] = df[pct_col] / 100.0

    for date_col in ("start_date", "end_date"):
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df


def load_data(base_path=None, report_types=None):
    """Load ad reports from the data directory.

    Supports both Console CSV (legacy) and API xlsx formats with auto-detection.
    Searches: base_path → advertise/数据源/ → advertise/data/

    Args:
        base_path: Directory containing report files.
        report_types: Optional list of report type keys to filter
                      (e.g., ['campaign', 'targeting', 'advertised_product']).
                      If None, loads all found types.

    Returns:
        dict: {report_type: DataFrame}
    """
    if base_path is None:
        script_dir = os.path.dirname(__file__)
        # Try API data path first, then legacy Console path
        for candidate in (os.path.join(script_dir, "data"),
                          os.path.join(script_dir, "数据源")):
            if os.path.isdir(candidate):
                base_path = candidate
                break
        if base_path is None:
            base_path = os.path.join(script_dir, "data")

    # If base_path is a single subdirectory, enter it
    if os.path.isdir(base_path):
        entries = os.listdir(base_path)
        if len(entries) == 1 and os.path.isdir(os.path.join(base_path, entries[0])):
            base_path = os.path.join(base_path, entries[0])

    reports = {}
    if not os.path.isdir(base_path):
        print(f"  [警告] 数据目录不存在: {base_path}")
        return reports

    for fname in sorted(os.listdir(base_path)):
        if not fname.endswith((".xlsx", ".csv")):
            continue
        fpath = os.path.join(base_path, fname)

        # Try API detection first, then legacy Console detection
        col_map, rtype = detect_api_report(fname)
        is_api = True
        if col_map is None:
            col_map, rtype = _detect_report(fname)
            is_api = False

        if col_map is None:
            print(f"  [跳过] 无法识别报告类型: {fname}")
            continue
        if report_types and rtype not in report_types:
            continue

        df = _load_single_file(fpath)
        df = df.rename(columns=col_map)
        available = [c for c in col_map.values() if c in df.columns]
        df = df[available]

        if is_api:
            # API xlsx: already clean numeric values
            df = _clean_api_data(df)
        else:
            # Console CSV: needs money/percentage normalization
            df = _clean_console_data(df)

        if rtype in reports:
            # Concatenate multiple files of same type (e.g., different date ranges)
            existing_cols = set(reports[rtype].columns)
            new_cols = set(df.columns)
            common_cols = existing_cols & new_cols
            if common_cols:
                reports[rtype] = pd.concat([reports[rtype][list(common_cols)], df[list(common_cols)]], ignore_index=True)
            print(f"  [加载] {rtype}: +{len(df)} 行 → 累计 {len(reports[rtype])} 行 × {len(reports[rtype].columns)} 列  ← {fname}")
        else:
            reports[rtype] = df
            print(f"  [加载] {rtype}: {len(df)} 行 × {len(df.columns)} 列  ← {fname}")

    return reports


def load_api_data(base_path=None, report_types=None):
    """Load ONLY API-format reports. Shortcut for scripts that don't need Console compat."""
    return load_data(base_path=base_path, report_types=report_types)
