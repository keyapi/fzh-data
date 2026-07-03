"""Shared utilities — extracted from analysis scripts to eliminate duplication."""
import json
import os
import pandas as pd
import numpy as np


def safe_num(series):
    """Convert series to numeric, coercing errors to NaN."""
    return pd.to_numeric(series, errors="coerce")


def save_json(data, filename, out_dir=None):
    """Save analysis result to JSON, handling numpy/pandas serialization."""
    if out_dir is None:
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


def load_env(paths):
    """Load key=value pairs from .env files (no external deps)."""
    env = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
        except FileNotFoundError:
            pass
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def numeric_cols(df, col_names):
    """Ensure named columns are numeric, in-place."""
    for col in col_names:
        if col in df.columns:
            df[col] = safe_num(df[col])


def round_record(record, precision=4):
    """Round float values in a dict, replacing NaN with None."""
    for k in record:
        if isinstance(record[k], (np.floating, float)):
            record[k] = round(float(record[k]), precision)
        elif pd.isna(record[k]) if not isinstance(record[k], str) else False:
            record[k] = None
    return record
