"""读通途非FBA订单表：跟踪号 + 身份列。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .classify import TT_PICK, _bare_tracking
from .route import RouteResult, _norm_number, detect_carrier


@dataclass
class TongtuRow:
    number: str
    ident: dict
    route: RouteResult
    source_index: int = 0


@dataclass
class IngestReport:
    rows: list[TongtuRow] = field(default_factory=list)

    @property
    def ups(self) -> list[TongtuRow]:
        return [r for r in self.rows if r.route.carrier == "ups"]

    @property
    def fedex(self) -> list[TongtuRow]:
        return [r for r in self.rows if r.route.carrier == "fedex"]

    @property
    def parked(self) -> list[TongtuRow]:
        return [r for r in self.rows if r.route.carrier is None]


def ingest_tongtu(xlsx: str) -> IngestReport:
    df = pd.read_excel(xlsx, sheet_name=0)
    tc = next(c for c in df.columns if "跟踪号" in str(c))
    out = IngestReport()
    for i, rec in enumerate(df.to_dict("records")):
        raw = rec.get(tc)
        number = _norm_number("" if pd.isna(raw) else str(raw))
        ident = {}
        for k, src in TT_PICK.items():
            v = rec.get(src)
            ident[k] = "" if pd.isna(v) else str(v).strip()
        if not number:
            out.rows.append(TongtuRow(number="", ident=ident, route=RouteResult(None, "missing_tracking"), source_index=i))
            continue
        number = _bare_tracking(number)
        out.rows.append(TongtuRow(number=number, ident=ident, route=detect_carrier(number, ident), source_index=i))
    return out
