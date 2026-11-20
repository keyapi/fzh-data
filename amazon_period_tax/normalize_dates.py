# -*- coding: utf-8 -*-
"""posted-date 规范化（Colab dateparser）。"""
from __future__ import annotations

import pandas as pd


def normalize_posted_dates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "posted-date" not in out.columns:
        return out
    import dateparser

    def convert_date(date_str):
        parsed = dateparser.parse(str(date_str))
        return parsed.strftime("%Y-%m-%d") if parsed else None

    out["posted-date"] = out["posted-date"].astype(str).apply(convert_date)
    if "posted-date-time" in out.columns:
        out.loc[out["posted-date-time"].isnull(), "posted-date"] = None
    return out
