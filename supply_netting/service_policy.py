# -*- coding: utf-8 -*-
"""服务分档（P2a）：ABC × XYZ → A/B/C/D → 分位政策。

只做纯函数，不读文件、不写文件；CLI 在 `scripts/build_service_policy_20261112.py`。
口径：
- ABC：2026 销量降序累计 80/15/5；跨过 80% 的那一件留在 A（A 实际可略超 80%）。
- XYZ：X=smooth，Y=intermittent，Z=lumpy/erratic/n/a 或 obsolescent/new/short/no_demand。
- A/B/C/D：A(X/Y)=A；A(Z)/B(X/Y)=B；B(Z)/C(X/Y)=C；其余（C(Z)、新品、淘汰、零销量）=D。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ABC_CUTS = (0.80, 0.95)

# 先验：A q95 / B q90 / C q85 / D q85（fill-rate 代理）
CLASS_QUANTILE = {
    "A": dict(service_level_prior=0.95, quantile=0.95,
              quantile_label="q95", basis="A_CSL_95"),
    "B": dict(service_level_prior=0.90, quantile=0.90,
              quantile_label="q90", basis="B_CSL_90"),
    "C": dict(service_level_prior=0.85, quantile=0.85,
              quantile_label="q85", basis="C_CSL_85"),
    "D": dict(service_level_prior=0.85, quantile=0.85,
              quantile_label="q85", basis="D_fill_rate_or_q85_proxy"),
}
SERVICE_CLASSES = tuple(CLASS_QUANTILE)


def assign_abc(sales: pd.Series) -> pd.Series:
    """按销量降序累计 80/15/5；返回 A/B/C，索引与输入一致。"""
    s = pd.to_numeric(sales, errors="coerce").fillna(0.0).clip(lower=0.0)
    out = pd.Series("C", index=s.index, dtype=object)
    total = float(s.sum())
    if total <= 0:
        return out
    order = s.sort_values(ascending=False, kind="mergesort").index
    cum = s.loc[order].cumsum() / total
    before = cum.shift(1).fillna(0.0)
    abc = np.where(before < ABC_CUTS[0], "A",
                   np.where(before < ABC_CUTS[1], "B", "C"))
    out.loc[order] = abc
    return out


def assign_xyz(sbc_class, demand_pattern) -> str:
    """X=smooth；Y=intermittent；其余（lumpy/erratic/n/a/新品/淘汰/短史）=Z。"""
    sc = str(sbc_class or "").strip().lower()
    dp = str(demand_pattern or "").strip().lower()
    if dp in ("obsolescent", "new", "short", "no_demand"):
        return "Z"
    if sc == "smooth":
        return "X"
    if sc == "intermittent":
        return "Y"
    return "Z"


def assign_service_class(abc: str, xyz: str, demand_pattern=None, sales_2026=0.0) -> str:
    """ABC×XYZ → A/B/C/D；零销量/新品/淘汰/短史直接 D。"""
    dp = str(demand_pattern or "").strip().lower()
    if float(sales_2026 or 0.0) <= 0 or dp in ("obsolescent", "new", "short", "no_demand"):
        return "D"
    a = str(abc).upper()
    x = str(xyz).upper()
    if a == "A" and x in ("X", "Y"):
        return "A"
    if (a == "A" and x == "Z") or (a == "B" and x in ("X", "Y")):
        return "B"
    if (a == "B" and x == "Z") or (a == "C" and x in ("X", "Y")):
        return "C"
    return "D"


def class_quantile(service_class: str) -> dict:
    """class → 分位政策；未知 class 抛错，不自动补。"""
    key = str(service_class or "").strip().upper()
    if key not in CLASS_QUANTILE:
        raise ValueError(f"未知 service_class：{service_class!r}；不得自动补档")
    return dict(CLASS_QUANTILE[key])
