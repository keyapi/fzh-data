"""parcel_track 运营异常表：从统一 summary 行生成 Excel。"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

from .normalize import classified_row
from .ops_excel import write_ops_workbook


def build_from_summaries(summaries: list[dict], ident_by_number: dict[str, dict], out_xlsx: str, parked=None, now=None):
    now = now or pd.Timestamp(_dt.datetime.now())
    rows = []
    for s in summaries:
        carrier = s.get("承运商") or ""
        n = str(s.get("跟踪号") or "")
        ident = ident_by_number.get(n, {})
        rows.append(classified_row(s, ident, now, carrier))
    df = pd.DataFrame(rows)
    write_ops_workbook(
        df if len(df) else pd.DataFrame(columns=["_key"]),
        out_xlsx,
        title="尾程运营异常总览（Amazon 口径 · 营业日）",
        slow_label="承运延误",
        notes_title="混合承运商异常报表口径",
        parked=parked,
    )
    return df
