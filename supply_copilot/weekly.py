# -*- coding: utf-8 -*-
"""把窗口预测（p50/p90 总量）按历史周占比摊成周计划（只读、纯本地、不下单）。

输入
- 需求去向表 ``demand_line_disposition.parquet``（rebuild 产物）
- 预测窗口表 ``forecast_sku_warehouse_windows.parquet``（含 60/90/120/180 天窗口）

做法
1. **历史周占比**：取 ``as_of`` 所在周（周一为起点）之前的最近 12 个完整周
   （周一–周日），按 ``(canonical_sku, canonical_warehouse, canonical_uom)`` 汇总成
   周序列并归一化。占比口径用全部需求行（不按 ``netting_allowed`` 砍）——占比回答
   的是"需求在周与周之间的形状"，与净额阻断无关。
2. 某键少于 4 个完整周有需求（含无历史）→ 均匀分摊，``share_basis="even"``，
   原因写进 ``note``；历史足够 → ``share_basis="history_12w"``。
3. 对 ``lead_days=90`` 的窗口行，按占比摊到从 ``as_of`` 所在周开始的 ``weeks`` 个周。
   周数超过 12 周轮廓时按轮廓循环取，再归一化——保证每键周数量之和等于窗口总量
   （函数内断言，误差 < 0.01）。

边界
- 未知 UOM（空串 / ``unknown`` 等）既不参与占比、也不输出（不猜）。
- 未映射 SKU 的窗口行不输出，只在返回统计里计数。
- 不联网、不写 EN、不打印凭证。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

LEAD_DAYS = 90
HISTORY_WEEKS = 12
MIN_HISTORY_WEEKS = 4
CONSERVATION_TOLERANCE = 0.01
UNKNOWN_UOMS = frozenset({"", "unknown", "nan", "none", "null"})

OUTPUT_COLUMNS = [
    "week_start",
    "week_end",
    "product_id",
    "warehouse",
    "uom",
    "qty",
    "qty_p50",
    "qty_p90",
    "share_basis",
    "share_weeks",
    "note",
]


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def _uom_col(df: pd.DataFrame, *, where: str) -> str:
    """需求表历史上用 ``uom``，窗口表用 ``canonical_uom``；两者都接受。"""
    for name in ("canonical_uom", "uom"):
        if name in df.columns:
            return name
    raise ValueError(f"{where} 缺 UOM 列（canonical_uom / uom）")


def _valid_uom(series: pd.Series) -> pd.Series:
    norm = series.astype("string").str.strip().str.lower()
    return norm.notna() & ~norm.isin(UNKNOWN_UOMS)


def _canonical_by_sku(disp: pd.DataFrame) -> dict[str, str]:
    """通途 SKU → canonical_sku；优先 mapped 行，其余回退到 unmapped:/ambiguous: 标签。"""
    if "tongtool_sku" not in disp.columns or "canonical_sku" not in disp.columns:
        return {}
    d = disp[["tongtool_sku", "canonical_sku", "mapping_status"]].dropna(
        subset=["tongtool_sku", "canonical_sku"]
    )
    fallback = (
        d.drop_duplicates("tongtool_sku")
        .set_index("tongtool_sku")["canonical_sku"]
        .to_dict()
    )
    mapped = (
        d[d["mapping_status"].eq("mapped")]
        .drop_duplicates("tongtool_sku")
        .set_index("tongtool_sku")["canonical_sku"]
        .to_dict()
    )
    return {**fallback, **mapped}


def _history_profiles(
    disp: pd.DataFrame, uom_col: str, hist_starts: list[date], cur_week_start: date
) -> dict[tuple[str, str, str], list[float]]:
    """键 → 12 个完整周的 quantity 序列（无记录的周补 0）。"""
    d = disp.copy()
    d["_date"] = pd.to_datetime(d["demand_date"], errors="coerce").dt.normalize()
    d["_qty"] = pd.to_numeric(d["quantity"], errors="coerce")
    keep = d["_date"].notna() & d["_qty"].notna() & _valid_uom(d[uom_col])
    keep &= (d["_date"] >= pd.Timestamp(hist_starts[0])) & (
        d["_date"] < pd.Timestamp(cur_week_start)
    )
    d = d[keep]
    if d.empty:
        return {}
    d["_week"] = (d["_date"] - pd.to_timedelta(d["_date"].dt.weekday, unit="D")).dt.date
    d["_uom"] = d[uom_col].astype("string").str.strip()
    pivot = d.pivot_table(
        index=["canonical_sku", "canonical_warehouse", "_uom"],
        columns="_week",
        values="_qty",
        aggfunc="sum",
        fill_value=0.0,
    )
    pivot = pivot.reindex(columns=hist_starts, fill_value=0.0)
    return {tuple(key): [float(v) for v in row] for key, row in pivot.iterrows()}


def _plan_shares(
    history: list[float] | None, weeks: int
) -> tuple[list[float], str, int, str]:
    """返回 (每周占比, share_basis, share_weeks, note)；占比之和恒为 1。"""
    positive = 0
    if history is not None:
        arr = pd.Series(history, dtype=float)
        positive = int((arr > 0).sum())
        total = float(arr.sum())
        if total > 0 and positive >= MIN_HISTORY_WEEKS:
            profile = arr / total
            weights = [float(profile.iloc[k % len(profile)]) for k in range(weeks)]
            share = pd.Series(weights, dtype=float)
            share = share / float(share.sum())
            # 把浮点残差塞进最大的一周，保证 13 周之和严格等于窗口总量
            share.iloc[int(share.to_numpy().argmax())] += 1.0 - float(share.sum())
            return (
                [float(x) for x in share],
                "history_12w",
                positive,
                f"按最近 {HISTORY_WEEKS} 个完整周的需求占比分摊",
            )

    share = pd.Series([1.0 / weeks] * weeks, dtype=float)
    share.iloc[0] += 1.0 - float(share.sum())
    if positive:
        note = f"历史仅 {positive} 个完整周有需求（<{MIN_HISTORY_WEEKS}），均匀分摊"
    else:
        note = f"最近 {HISTORY_WEEKS} 个完整周无需求记录，均匀分摊"
    return [float(x) for x in share], "even", positive, note


def build_weekly_plan(
    disposition_path: str | Path,
    windows_path: str | Path,
    out_path: str | Path,
    *,
    as_of: str | date | pd.Timestamp,
    weeks: int = 13,
    service: str = "p90",
) -> dict[str, Any]:
    """窗口总量 → 周计划 parquet；返回统计（含守恒自检结果）。"""
    if service not in ("p50", "p90"):
        raise ValueError(f"service 只能是 p50/p90，收到 {service!r}")
    if int(weeks) < 1:
        raise ValueError(f"weeks 必须 >= 1，收到 {weeks!r}")
    weeks = int(weeks)

    as_of_date = _to_date(as_of)
    cur_week_start = as_of_date - timedelta(days=as_of_date.weekday())
    hist_starts = [cur_week_start - timedelta(days=7 * k) for k in range(HISTORY_WEEKS, 0, -1)]
    hist_end = cur_week_start - timedelta(days=1)

    disp = pd.read_parquet(disposition_path)
    for col in ("canonical_sku", "canonical_warehouse", "demand_date", "quantity"):
        if col not in disp.columns:
            raise ValueError(f"需求表缺列: {col}")
    disp_uom_col = _uom_col(disp, where="需求表")
    profiles = _history_profiles(disp, disp_uom_col, hist_starts, cur_week_start)

    raw = pd.read_parquet(windows_path)
    for col in ("lead_days", "p50", "p90", "canonical_warehouse"):
        if col not in raw.columns:
            raise ValueError(f"窗口表缺列: {col}")
    win_uom_col = _uom_col(raw, where="窗口表")

    rows_loaded = int(len(raw))
    lead = pd.to_numeric(raw["lead_days"], errors="coerce")
    w = raw[lead == LEAD_DAYS].copy()
    rows_other_lead = rows_loaded - int(len(w))

    has_forecast = w[service].notna()
    no_forecast = int(len(w) - int(has_forecast.sum()))
    w = w[has_forecast]

    uom_ok = _valid_uom(w[win_uom_col])
    unknown_uom = int(len(w) - int(uom_ok.sum()))
    w = w[uom_ok].copy()

    if "canonical_sku" in w.columns:
        w["product_id"] = w["canonical_sku"]
    else:
        if "tongtool_sku" not in w.columns:
            raise ValueError("窗口表缺 canonical_sku，也没有 tongtool_sku 可映射")
        w["product_id"] = w["tongtool_sku"].map(_canonical_by_sku(disp))

    mapped = w[w["product_id"].notna() & w["canonical_warehouse"].notna()].copy()
    unmapped_sku = int(len(w) - len(mapped))
    mapped["uom"] = mapped[win_uom_col].astype("string").str.strip()

    agg = mapped.groupby(["product_id", "canonical_warehouse", "uom"], as_index=False).agg(
        p50=("p50", lambda s: s.sum(min_count=1)),
        p90=("p90", lambda s: s.sum(min_count=1)),
    )

    rows: list[dict[str, Any]] = []
    expected: dict[tuple[str, str, str], tuple[float, float, float]] = {}
    basis_counts = {"history_12w": 0, "even": 0}
    for rec in agg.itertuples(index=False):
        pid, wh, uom = str(rec.product_id), str(rec.canonical_warehouse), str(rec.uom)
        key = (pid, wh, uom)
        shares, basis, share_weeks, note = _plan_shares(profiles.get(key), weeks)
        basis_counts[basis] += 1

        qty_total = float(rec.p90 if service == "p90" else rec.p50)
        p50_total = float(rec.p50) if pd.notna(rec.p50) else math.nan
        p90_total = float(rec.p90) if pd.notna(rec.p90) else math.nan
        if math.isnan(qty_total):
            raise AssertionError(f"窗口总量为空（{key}），不应走到这里")

        for k, share in enumerate(shares):
            ws = cur_week_start + timedelta(days=7 * k)
            rows.append(
                {
                    "week_start": ws.isoformat(),
                    "week_end": (ws + timedelta(days=6)).isoformat(),
                    "product_id": pid,
                    "warehouse": wh,
                    "uom": uom,
                    "qty": qty_total * share,
                    "qty_p50": p50_total * share if not math.isnan(p50_total) else math.nan,
                    "qty_p90": p90_total * share if not math.isnan(p90_total) else math.nan,
                    "share_basis": basis,
                    "share_weeks": share_weeks,
                    "note": note,
                }
            )
        expected[key] = (qty_total, p50_total, p90_total)

    out = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not out.empty:
        out = out.sort_values(
            ["product_id", "warehouse", "uom", "week_start"], kind="stable", ignore_index=True
        )

    # 守恒自检：同一键的周数量之和 == 对应窗口总量
    max_err = 0.0
    if not out.empty:
        sums = out.groupby(["product_id", "warehouse", "uom"])[["qty", "qty_p50", "qty_p90"]].sum(
            min_count=1
        )
        for key, (qty_total, p50_total, p90_total) in expected.items():
            row = sums.loc[key]
            for value, total in (
                (row["qty"], qty_total),
                (row["qty_p50"], p50_total),
                (row["qty_p90"], p90_total),
            ):
                if math.isnan(total) or pd.isna(value):
                    continue
                max_err = max(max_err, abs(float(value) - total))
    if max_err >= CONSERVATION_TOLERANCE:
        raise AssertionError(f"周计划不守恒：最大误差 {max_err:.6f}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False, compression="zstd")

    return {
        "as_of": as_of_date.isoformat(),
        "service": service,
        "weeks": weeks,
        "horizon": {
            "week_start": cur_week_start.isoformat(),
            "week_end": (cur_week_start + timedelta(days=7 * weeks - 1)).isoformat(),
        },
        "history_window": [hist_starts[0].isoformat(), hist_end.isoformat()],
        "rows": int(len(out)),
        "keys": int(len(agg)),
        "product_ids": int(out["product_id"].nunique()) if not out.empty else 0,
        "share_basis": basis_counts,
        "dropped": {
            "other_lead_days": rows_other_lead,
            "no_forecast": no_forecast,
            "unknown_uom": unknown_uom,
            "unmapped_sku": unmapped_sku,
        },
        "totals": {
            "qty": float(out["qty"].sum()) if not out.empty else 0.0,
            "qty_p50": float(out["qty_p50"].sum()) if not out.empty else 0.0,
            "qty_p90": float(out["qty_p90"].sum()) if not out.empty else 0.0,
        },
        "max_conservation_error": float(max_err),
        "path": str(out_path),
    }
