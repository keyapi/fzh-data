"""读通途非FBA订单表：跟踪号 + 身份列。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .classify import TT_PICK, _bare_tracking
from .route import RouteResult, detect_carrier, split_tracking_cell


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
    def gls(self) -> list[TongtuRow]:
        return [r for r in self.rows if r.route.carrier == "gls"]

    @property
    def parked(self) -> list[TongtuRow]:
        return [r for r in self.rows if r.route.carrier is None]


def ingest_tongtu(xlsx: str) -> IngestReport:
    df = pd.read_excel(xlsx, sheet_name=0)
    tc = next(c for c in df.columns if "跟踪号" in str(c))
    out = IngestReport()
    for i, rec in enumerate(df.to_dict("records")):
        ident = {}
        for k, src in TT_PICK.items():
            v = rec.get(src)
            ident[k] = "" if pd.isna(v) else str(v).strip()
        raw = rec.get(tc)
        tokens = split_tracking_cell("" if pd.isna(raw) else str(raw))
        if not tokens:
            out.rows.append(TongtuRow(number="", ident=ident, route=RouteResult(None, "missing_tracking"), source_index=i))
            continue
        for tok in tokens:
            number = _bare_tracking(tok)
            out.rows.append(TongtuRow(number=number, ident=ident, route=detect_carrier(number, ident), source_index=i))
    return out
