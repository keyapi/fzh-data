# -*- coding: utf-8 -*-
"""断货删失适配层（供 forecast.py 可选启用；默认关闭）。

只做两件事：
1. 读 `stockout_monthly_flags.parquet`，取已证 UOM（个/套）的 `censored` 月；
2. 按月给训练序列做保守/激进补值，并返回可审计统计。

不虚构损失销量：补值只是训练输入的情景假设；观测销量是下界。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_FLAGS = (
    "D:/Work/fzh-order-store/en-demand-v1/stockout-censoring-2026-10-28/"
    "stockout_monthly_flags.parquet"
)
ALLOWED_UOM = ("个", "套")
MODES = ("conservative", "aggressive")


def tj_bundle_allowed(item: str, is_stock_item: Any) -> bool:
    """UOM-CANONICAL：套只用于 TJ# bundle（stock_uom=套 且 is_stock_item=0）。"""
    if not item or not str(item).startswith("TJ#"):
        return False
    try:
        return int(is_stock_item) == 0
    except (TypeError, ValueError):
        return False


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def load_flags(path: str | Path = DEFAULT_FLAGS) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    """返回 ``{sku: {month: info}}`` 与加载元数据。

    只收 `censored=true` 且 UOM 已证（个/套）的行；unknown/uom_conflict 不进入训练补值。
    """
    p = Path(path)
    df = pd.read_parquet(p)
    required = {"sku", "month", "censored", "uom_group"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"flags 缺列: {sorted(missing)}")
    df = df[df["censored"].fillna(False).astype(bool)].copy()
    df = df[df["uom_group"].isin(ALLOWED_UOM)]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in df.itertuples(index=False):
        out.setdefault(str(r.sku), {})[str(r.month)] = {
            "stockout_status": getattr(r, "stockout_status", ""),
            "zero_dates": int(getattr(r, "zero_dates", 0) or 0),
            "pos_dates": int(getattr(r, "pos_dates", 0) or 0),
            "high_zero_dates": int(getattr(r, "high_zero_dates", 0) or 0),
            "uom_group": str(r.uom_group),
        }
    meta = {
        "path": str(p),
        "sha256": _sha(p),
        "censored_rows": int(len(df)),
        "skus": int(len(out)),
        "months": int(df["month"].nunique()),
        "allowed_uom": list(ALLOWED_UOM),
    }
    return out, meta


def _impute_conservative(y: np.ndarray, censored: np.ndarray, i: int) -> float:
    """只补删失零月：最近 6 个非删失月中位数，P90 截顶；无历史/中位 0 则不补。"""
    idx = [j for j in range(max(0, i - 6), i) if not censored[j]]
    if not idx:
        return 0.0
    med = float(np.median(y[idx]))
    if med <= 0:
        return 0.0
    # 只使用 i 之前可见的数据（防止用未来月份定分位）
    pos = [float(v) for j, v in enumerate(y[:i]) if (not censored[j]) and v > 0]
    cap = float(np.percentile(pos, 90)) if pos else med
    return min(med, cap)


def _impute_aggressive(y: np.ndarray, censored: np.ndarray, i: int) -> float:
    """敏感性：所有删失月按最近 3/6 个非删失月均值补，无截顶。"""
    for k in (3, 6):
        idx = [j for j in range(max(0, i - k), i) if not censored[j]]
        if idx:
            return float(np.mean(y[idx]))
    pos = [float(v) for j, v in enumerate(y[:i]) if not censored[j] and v > 0]
    return float(np.mean(pos)) if pos else 0.0


@dataclass
class CensorStats:
    censored_months: int = 0
    censored_zero_months: int = 0
    replaced_months: int = 0
    added_units: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "censored_months": self.censored_months,
            "censored_zero_months": self.censored_zero_months,
            "replaced_months": self.replaced_months,
            "added_units": round(self.added_units, 3),
        }


def apply_as_of(
    months: list[str],
    y: np.ndarray,
    flags: dict[str, dict[str, Any]],
    upto: int,
    mode: str = "conservative",
) -> tuple[np.ndarray, CensorStats]:
    """只使用 origin 之前（``y[:upto]``）的数据重算补值。

    回测每个原点必须调用本函数，不能用全期补值序列。
    """
    sub_months = months[:upto]
    sub_y = np.asarray(y[:upto], dtype=float)
    allowed = set(sub_months)
    sub_flags = {m: v for m, v in flags.items() if m in allowed}
    return apply(sub_months, sub_y, sub_flags, mode)


def apply(
    months: list[str],
    y: np.ndarray,
    flags: dict[str, dict[str, Any]],
    mode: str = "conservative",
) -> tuple[np.ndarray, CensorStats]:
    """按月补值；只改训练输入，不生成任何“损失销量”数字。"""
    if mode not in MODES:
        raise ValueError(f"未知 censoring mode: {mode}")
    y = np.asarray(y, dtype=float).copy()
    if not flags:
        return y, CensorStats()
    cens = np.zeros(len(months), dtype=bool)
    for i, m in enumerate(months):
        if m in flags:
            cens[i] = True
    stats = CensorStats(
        censored_months=int(cens.sum()),
        censored_zero_months=int(((y == 0) & cens).sum()),
    )
    if mode == "conservative":
        for i in np.where(cens)[0]:
            if y[i] > 1e-9:
                continue  # 有销量：观测已是下界，不硬补
            imp = _impute_conservative(y, cens, i)
            if imp > 1e-9:
                y[i] = imp
                stats.replaced_months += 1
                stats.added_units += imp
    else:
        for i in np.where(cens)[0]:
            imp = _impute_aggressive(y, cens, i)
            new = max(float(y[i]), imp)
            if new > float(y[i]) + 1e-9:
                stats.replaced_months += 1
                stats.added_units += new - float(y[i])
            y[i] = new
    return y, stats


def as_json(meta: dict[str, Any], mode: str, enabled: bool) -> dict[str, Any]:
    return {"enabled": enabled, "mode": mode, **meta}


def rebuild_flags_as_of(
    stock: pd.DataFrame,
    origin_date: str | Any,
    allowed_skus: set[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    """只用 origin 当时可见的库存观测重建删失 flags。

    关键：`both_states_sku`（同时有零/有正库存）也只用可见窗口判断；
    不能用全期才知道的“后来有正库存”给早期月份打删失标记。
    """
    s = stock.copy()
    s["d"] = pd.to_datetime(s["d"])
    cutoff = pd.Timestamp(origin_date)
    s = s[s["d"] <= cutoff]
    if not len(s):
        return {}
    s["is_zero"] = s["stock_state"].eq("present_zero")
    s["is_pos"] = s["stock_state"].eq("present_positive")
    sday = (
        s.groupby(["sku", "d"], as_index=False)
        .agg(
            n_avail=("available", "count"),
            avail_sum=("available", "sum"),
            n_zero=("is_zero", "sum"),
            n_pos=("is_pos", "sum"),
        )
    )
    sday["state"] = np.where(
        (sday["n_avail"] > 0) & (sday["avail_sum"] <= 0),
        "zero",
        np.where(sday["avail_sum"] > 0, "positive", "unknown"),
    )
    sday = sday[sday["state"] != "unknown"].copy()
    if not len(sday):
        return {}
    states = sday.groupby("sku")["state"].agg(set)
    both = set(states[states.apply(lambda x: "zero" in x and "positive" in x)].index)
    both &= allowed_skus
    if not both:
        return {}
    sday = sday[sday["sku"].isin(both)]
    sday["month"] = sday["d"].dt.strftime("%Y-%m")
    monthly = (
        sday.groupby(["sku", "month"], as_index=False)
        .agg(
            zero_dates=("state", lambda x: int((x == "zero").sum())),
            pos_dates=("state", lambda x: int((x == "positive").sum())),
            high_zero_dates=("state", lambda x: 0),
        )
    )
    monthly = monthly[monthly["zero_dates"] > 0]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in monthly.itertuples(index=False):
        out.setdefault(str(r.sku), {})[str(r.month)] = {
            "stockout_status": "observed_zero_only" if r.pos_dates == 0 else "observed_mixed",
            "zero_dates": int(r.zero_dates),
            "pos_dates": int(r.pos_dates),
            "high_zero_dates": 0,
            "uom_group": "",
        }
    return out
