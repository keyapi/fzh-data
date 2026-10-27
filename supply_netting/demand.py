# -*- coding: utf-8 -*-
"""冻结需求净额表的唯一入口。

只认 ``demand_netting.parquet``（849ba1b0 冻结产物）：
- 四列键 ``demand_date × canonical_sku × canonical_warehouse × canonical_uom`` 必须唯一；
- ``netting_allowed`` 必须全为 True（已过滤资格，阻断量在 ``demand_blocked``）；
- 默认自发货序列取 ``in_default_series=True`` 的 ``quantity_default``；
- 3PL 行（``in_default_series=False``）单独保留，补货责任标 ``unknown``。

``demand_canonical.parquet`` 是明细聚合、四列不唯一，**禁止**在这里读取或按行连接供应。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

NETTING_KEY = ["demand_date", "canonical_sku", "canonical_warehouse", "canonical_uom"]
REQUIRED = NETTING_KEY + [
    "quantity", "quantity_default", "quantity_third_party",
    "netting_allowed", "in_default_series",
]
SERIES_DEFAULT = "default"
SERIES_THIRD_PARTY = "third_party"


class DemandContractError(ValueError):
    """需求入口违反冻结契约时抛出，绝不降级成「差不多能用」。"""


def sha256_of(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_demand_netting(path: str | Path) -> tuple[pd.DataFrame, dict]:
    p = Path(path)
    if not p.exists():
        raise DemandContractError(f"需求净额表不存在：{p}")
    df = pd.read_parquet(p)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise DemandContractError(f"需求净额表缺列：{missing}")

    if not df["netting_allowed"].astype(bool).all():
        bad = int((~df["netting_allowed"].astype(bool)).sum())
        raise DemandContractError(
            f"需求净额表混入 netting_allowed=false 的 {bad} 行；阻断量应只在 demand_blocked"
        )
    duplicated = int(df.duplicated(NETTING_KEY).sum())
    if duplicated:
        raise DemandContractError(f"需求净额表四列键重复 {duplicated} 行，禁止净额")

    meta = dict(
        path=str(p), sha256=sha256_of(p), rows=int(len(df)),
        quantity=float(pd.to_numeric(df["quantity"], errors="coerce").sum()),
        default_rows=int(df["in_default_series"].fillna(False).astype(bool).sum()),
        third_party_rows=int((~df["in_default_series"].fillna(False).astype(bool)).sum()),
        four_key_duplicates=duplicated,
        date_min=str(df["demand_date"].min()), date_max=str(df["demand_date"].max()),
        netting_allowed_all=True,
    )
    return df, meta


def series_rows(df: pd.DataFrame, series: str) -> list[dict]:
    """按 series 展开成引擎行。默认序列用 ``quantity_default``，不用 ``quantity``。"""
    if series == SERIES_DEFAULT:
        keep = df["in_default_series"].fillna(False).astype(bool)
        qty = pd.to_numeric(df.loc[keep, "quantity_default"], errors="coerce").fillna(0)
    elif series == SERIES_THIRD_PARTY:
        keep = ~df["in_default_series"].fillna(False).astype(bool)
        qty = pd.to_numeric(df.loc[keep, "quantity_third_party"], errors="coerce").fillna(0)
    else:
        raise DemandContractError(f"未知需求序列：{series}")

    subset = df.loc[keep]
    rows = []
    for record, quantity in zip(subset.to_dict("records"), qty.tolist()):
        if quantity <= 0:
            continue
        rows.append(dict(
            demand_row_id="|".join(str(record[k]) for k in NETTING_KEY),
            demand_date=record["demand_date"],
            canonical_sku=record["canonical_sku"],
            canonical_warehouse=record["canonical_warehouse"],
            canonical_uom=record["canonical_uom"],
            quantity=quantity,
            series=series,
            scope_mix=record.get("scope_mix"),
            source_mix=record.get("source_mix"),
        ))
    return rows


def unclassified_quantity(df: pd.DataFrame) -> float:
    """``quantity`` 与 ``quantity_default + quantity_third_party`` 的差额（对账用）。"""
    total = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    split = (pd.to_numeric(df["quantity_default"], errors="coerce").fillna(0)
             + pd.to_numeric(df["quantity_third_party"], errors="coerce").fillna(0))
    return float((total - split).sum())


def load_backlog(path: str | Path | None) -> tuple[dict, dict]:
    """可选的未履约 SO 余额（补货责任已定的自发货部分）。

    没有该文件时返回空字典；**不**从 ``demand_canonical`` 反推。
    """
    if not path:
        return {}, dict(source="none", rows=0, quantity=0.0)
    p = Path(path)
    if not p.exists():
        raise DemandContractError(f"未履约 SO 文件不存在：{p}")
    df = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_parquet(p)
    need = ["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise DemandContractError(f"未履约 SO 缺列：{missing}")
    backlog: dict[tuple, float] = {}
    for record in df.to_dict("records"):
        key = (record["canonical_sku"], record["canonical_warehouse"], record["canonical_uom"])
        backlog[key] = backlog.get(key, 0.0) + float(record["quantity"] or 0)
    return backlog, dict(source=str(p), sha256=sha256_of(p), rows=int(len(df)),
                         quantity=float(sum(backlog.values())))
