# -*- coding: utf-8 -*-
"""把窗口预测（p50/p90 总量）拆成周计划（只读、纯本地、不下单）。

外部评审结论：单靠 12 周占比不足以支撑未来 13 周的周形状，因此改为分层：

1. **完整周历史 >= 52 周的键**：直接用周度模型按 ``demand_pattern`` 选型
   （smooth/erratic → Holt 线性 ETS，intermittent → SBA，lumpy → TSB），
   模型无正预测时依次回退 naive/MA3、周均；并用最近 8 个滚动原点做回测，
   给出逐周 WAPE 与 ``weeks`` 周累计 WAPE。
2. **历史不足 52 周（>=4 周）**：用最近 4–8 个完整周的均值（周均速率），
   ``method="ma_4_8w"``；不足 4 周或无历史 → 等分分摊 ``method="even_split"``。
3. **最后回退**：周度模型对某键给不出正预测时，才用最近 12 周占比
   ``method="share_12w"``——不再是主方法。
4. 所有方法只决定**周形状**，再缩放到 lead_days=90 窗口总量；每键周数量之和
   == 窗口总量（函数内断言，误差 < 0.01，p50/p90 各自守恒）。

边界
- 未知 UOM（空串 / ``unknown`` 等）既不参与拟合、也不输出（不猜）。
- 未映射 SKU 的窗口行不输出，只在返回统计里计数。
- 不联网、不写 EN、不打印凭证。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

LEAD_DAYS = 90
MIN_MODEL_WEEKS = 52
MIN_MEAN_WEEKS = 4
MAX_MEAN_WEEKS = 8
PROFILE_WEEKS = 12
BACKTEST_ORIGINS = 8
BACKTEST_MIN_TRAIN = 52
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
    "method",
    "backtest_wape",
    "fallback_reason",
]

ModelFn = Callable[[Sequence[float], int], list[float]]


# ---------------------------------------------------------------- 基础工具


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


def _weekly_series(
    disp: pd.DataFrame,
    uom_col: str,
    cur_week_start: date,
    target_keys: set[tuple[str, str, str]],
) -> dict[tuple[str, str, str], list[float]]:
    """键 → 完整周序列（周一起点，缺周补 0），截止到 as_of 前最后一个完整周。"""
    if not target_keys:
        return {}
    d = disp.copy()
    d["_date"] = pd.to_datetime(d["demand_date"], errors="coerce").dt.normalize()
    d["_qty"] = pd.to_numeric(d["quantity"], errors="coerce")
    keep = d["_date"].notna() & d["_qty"].notna() & _valid_uom(d[uom_col])
    keep &= d["_date"] < pd.Timestamp(cur_week_start)
    d = d[keep]
    if d.empty:
        return {}
    d["_week"] = (d["_date"] - pd.to_timedelta(d["_date"].dt.weekday, unit="D")).dt.date
    d["_uom"] = d[uom_col].astype("string").str.strip()
    key_cols = ["canonical_sku", "canonical_warehouse", "_uom"]
    keys = pd.MultiIndex.from_frame(d[key_cols])
    d = d[keys.isin(target_keys)]
    if d.empty:
        return {}

    weekly = d.groupby(key_cols + ["_week"], dropna=False)["_qty"].sum()
    out: dict[tuple[str, str, str], list[float]] = {}
    for key, sub in weekly.groupby(level=[0, 1, 2]):
        values = sub.droplevel([0, 1, 2]).to_dict()
        first, last = min(values), max(values)
        n = (last - first).days // 7 + 1
        week_dates = [first + timedelta(days=7 * k) for k in range(n)]
        out[(str(key[0]), str(key[1]), str(key[2]))] = [
            float(values.get(w, 0.0)) for w in week_dates
        ]
    return out


# ---------------------------------------------------------------- 周度模型


def _holt_ets(series: Sequence[float], periods: int, alpha: float = 0.3, beta: float = 0.1) -> list[float]:
    """Holt 线性 ETS(A,A,N)：水平 + 趋势，负预测截 0。"""
    values = [float(x) for x in series]
    if len(values) < 2:
        return [max(0.0, values[0])] * periods if values else [0.0] * periods
    level = values[0]
    trend = values[1] - values[0]
    for x in values[1:]:
        prev = level
        level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
    return [max(0.0, level + h * trend) for h in range(1, periods + 1)]


def _sba(series: Sequence[float], periods: int, alpha: float = 0.1) -> list[float]:
    """Syntetos–Boylan 近似（带偏差修正的 Croston）。"""
    size: float | None = None
    interval: float | None = None
    gap = 0
    rate = 0.0
    for x in series:
        x = float(x)
        gap += 1
        if x > 0:
            if size is None:
                size, interval = x, float(gap)
            else:
                size = alpha * x + (1 - alpha) * size
                interval = alpha * gap + (1 - alpha) * interval
            gap = 0
        if size and interval:
            rate = (1 - alpha / 2) * size / interval
    return [max(0.0, rate)] * periods


def _tsb(series: Sequence[float], periods: int, alpha: float = 0.1, beta: float = 0.1) -> list[float]:
    """Teunter–Syntetos–Babai：需求发生概率 + 需求规模。"""
    values = [float(x) for x in series]
    nonzero = [x for x in values if x > 0]
    if not values or not nonzero:
        return [0.0] * periods
    prob = len(nonzero) / len(values)
    size = sum(nonzero) / len(nonzero)
    for x in values:
        if x > 0:
            size = alpha * x + (1 - alpha) * size
            prob = beta + (1 - beta) * prob
        else:
            prob = (1 - beta) * prob
    return [max(0.0, prob * size)] * periods


def _mean_rate(series: Sequence[float], periods: int) -> list[float]:
    values = [float(x) for x in series if not math.isnan(float(x))]
    if not values:
        return [0.0] * periods
    window = values[-min(len(values), MIN_MODEL_WEEKS):]
    return [max(0.0, sum(window) / len(window))] * periods


def _ma3_rate(series: Sequence[float], periods: int) -> list[float]:
    values = [float(x) for x in series]
    if not values:
        return [0.0] * periods
    tail = values[-3:]
    return [max(0.0, sum(tail) / len(tail))] * periods


def _demand_pattern(series: Sequence[float]) -> str:
    """ADI / CV² 分类：smooth / erratic / intermittent / lumpy。"""
    values = [float(x) for x in series]
    positive = [x for x in values if x > 0]
    if not values or not positive:
        return "none"
    adi = len(values) / len(positive)
    mean = sum(positive) / len(positive)
    if mean <= 0:
        return "smooth"
    var = sum((x - mean) ** 2 for x in positive) / len(positive)
    cv2 = var / (mean**2)
    if adi < 1.32:
        return "smooth" if cv2 < 0.49 else "erratic"
    return "intermittent" if cv2 < 0.49 else "lumpy"


def _model_forecast(
    series: Sequence[float], periods: int
) -> tuple[list[float] | None, str, str, ModelFn | None]:
    """返回 (周预测, method, fallback_reason, 实际使用的模型函数)。"""
    pattern = _demand_pattern(series)
    if pattern == "none":
        return None, "none", "no_positive_history", None
    if pattern in ("smooth", "erratic"):
        name, fn = "ets", _holt_ets
    elif pattern == "intermittent":
        name, fn = "sba", _sba
    else:
        name, fn = "tsb", _tsb
    try:
        forecast = fn(series, periods)
    except Exception:  # pragma: no cover - 防御：模型异常不炸整批
        forecast = None
    if forecast is not None and sum(forecast) > 0:
        return forecast, name, "", fn

    reason = f"{name}_no_positive_forecast"
    for alt_name, alt_fn in (("naive_ma3", _ma3_rate), ("week_mean", _mean_rate)):
        alternative = alt_fn(series, periods)
        if sum(alternative) > 0:
            return alternative, alt_name, reason, alt_fn
    return None, name, reason, fn


def _backtest(
    series: Sequence[float],
    fn: ModelFn,
    periods: int,
    *,
    max_origins: int = BACKTEST_ORIGINS,
    min_train: int = BACKTEST_MIN_TRAIN,
) -> tuple[float, float, int]:
    """滚动原点回测：返回 (逐周 WAPE, periods 周累计 WAPE, 原点数)。"""
    values = [float(x) for x in series]
    n = len(values)
    origins = list(range(n - periods, min_train - 1, -1))[:max_origins]
    abs_sum = act_sum = cum_abs = cum_act = 0.0
    used = 0
    for origin in origins:
        train = values[:origin]
        actual = values[origin : origin + periods]
        try:
            forecast = fn(train, periods)
        except Exception:  # pragma: no cover
            continue
        if forecast is None or len(actual) == 0:
            continue
        used += 1
        abs_sum += sum(abs(f - a) for f, a in zip(forecast, actual))
        act_sum += sum(abs(a) for a in actual)
        cum_abs += abs(sum(forecast) - sum(actual))
        cum_act += abs(sum(actual))
    weekly = abs_sum / act_sum if act_sum > 0 else math.nan
    cumulative = cum_abs / cum_act if cum_act > 0 else math.nan
    return weekly, cumulative, used


# ---------------------------------------------------------------- 周形状


def _shares_from(profile: Sequence[float], periods: int) -> list[float] | None:
    """把任意长度的周轮廓（如 12 周占比）循环铺到 ``periods`` 个周并归一化。"""
    vals = [0.0 if v is None or math.isnan(float(v)) else max(0.0, float(v)) for v in profile]
    total = sum(vals)
    if not vals or total <= 0:
        return None
    profile_share = [v / total for v in vals]
    weights = [profile_share[k % len(profile_share)] for k in range(periods)]
    scale = sum(weights)
    share = [w / scale for w in weights]
    share[int(max(range(periods), key=lambda i: share[i]))] += 1.0 - sum(share)
    return share


def _uniform(periods: int) -> list[float]:
    share = [1.0 / periods] * periods
    share[0] += 1.0 - sum(share)
    return share


def _plan_for_key(series: list[float] | None, periods: int) -> dict[str, Any]:
    """决定某键的周形状与方法；只返回形状证据，不含数量。"""
    span = len(series) if series else 0

    if span >= MIN_MODEL_WEEKS:
        forecast, method, fallback, fn = _model_forecast(series, periods)
        if forecast is not None:
            share = _shares_from(forecast, periods)
            if share is not None:
                weekly_wape = cumulative_wape = math.nan
                origins = 0
                if fn is not None:
                    weekly_wape, cumulative_wape, origins = _backtest(series, fn, periods)
                return {
                    "share": share,
                    "method": method,
                    "share_basis": "model",
                    "share_weeks": span,
                    "note": f"按 {method} 周度模型预测周形状（历史 {span} 个完整周）",
                    "fallback_reason": fallback,
                    "backtest_wape": cumulative_wape,
                    "backtest_weekly_wape": weekly_wape,
                    "backtest_origins": origins,
                }
        # 模型给不出正预测 → 最后回退 12 周占比
        tail = series[-PROFILE_WEEKS:]
        share = _shares_from(tail, periods) if sum(tail) > 0 else None
        if share is not None:
            return {
                "share": share,
                "method": "share_12w",
                "share_basis": "share_12w",
                "share_weeks": span,
                "note": "周度模型无正预测，最后回退到最近 12 周占比",
                "fallback_reason": fallback or "model_no_positive_forecast",
                "backtest_wape": math.nan,
                "backtest_weekly_wape": math.nan,
                "backtest_origins": 0,
            }
        return _even_result(periods, span, "model_zero_and_share12w_zero")

    if span >= MIN_MEAN_WEEKS:
        window = series[-min(span, MAX_MEAN_WEEKS):]
        rate = sum(window) / len(window)
        if rate > 0:
            return {
                "share": _uniform(periods),
                "method": "ma_4_8w",
                "share_basis": "history_4_8w",
                "share_weeks": span,
                "note": f"历史 {span} 个完整周（不足 {MIN_MODEL_WEEKS}），用最近 {len(window)} 周均值分摊",
                "fallback_reason": f"history_weeks_{span}_lt_{MIN_MODEL_WEEKS}",
                "backtest_wape": math.nan,
                "backtest_weekly_wape": math.nan,
                "backtest_origins": 0,
            }
        return _even_result(periods, span, f"history_weeks_{span}_non_positive")

    reason = f"history_weeks_{span}_lt_{MIN_MEAN_WEEKS}" if span else "no_history"
    return _even_result(periods, span, reason)


def _even_result(periods: int, span: int, reason: str) -> dict[str, Any]:
    return {
        "share": _uniform(periods),
        "method": "even_split",
        "share_basis": "even",
        "share_weeks": span,
        "note": "历史不足，均匀分摊",
        "fallback_reason": reason,
        "backtest_wape": math.nan,
        "backtest_weekly_wape": math.nan,
        "backtest_origins": 0,
    }


# ---------------------------------------------------------------- 主入口


def build_weekly_plan(
    disposition_path: str | Path,
    windows_path: str | Path,
    out_path: str | Path,
    *,
    as_of: str | date | pd.Timestamp,
    weeks: int = 13,
    service: str = "p90",
) -> dict[str, Any]:
    """窗口总量 → 周计划 parquet；返回统计（含方法分布、回测、守恒自检）。"""
    if service not in ("p50", "p90"):
        raise ValueError(f"service 只能是 p50/p90，收到 {service!r}")
    if int(weeks) < 1:
        raise ValueError(f"weeks 必须 >= 1，收到 {weeks!r}")
    weeks = int(weeks)

    as_of_date = _to_date(as_of)
    cur_week_start = as_of_date - timedelta(days=as_of_date.weekday())
    hist_end = cur_week_start - timedelta(days=1)

    disp = pd.read_parquet(disposition_path)
    for col in ("canonical_sku", "canonical_warehouse", "demand_date", "quantity"):
        if col not in disp.columns:
            raise ValueError(f"需求表缺列: {col}")
    disp_uom_col = _uom_col(disp, where="需求表")

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
    target_keys = {
        (str(rec.product_id), str(rec.canonical_warehouse), str(rec.uom))
        for rec in agg.itertuples(index=False)
    }
    series_by_key = _weekly_series(disp, disp_uom_col, cur_week_start, target_keys)

    rows: list[dict[str, Any]] = []
    expected: dict[tuple[str, str, str], tuple[float, float, float]] = {}
    method_counts: dict[str, int] = {}
    basis_counts: dict[str, int] = {}
    wape_cumulative: list[float] = []
    wape_weekly: list[float] = []
    backtests = 0

    for rec in agg.itertuples(index=False):
        pid, wh, uom = str(rec.product_id), str(rec.canonical_warehouse), str(rec.uom)
        key = (pid, wh, uom)
        plan = _plan_for_key(series_by_key.get(key), weeks)
        method_counts[plan["method"]] = method_counts.get(plan["method"], 0) + 1
        basis_counts[plan["share_basis"]] = basis_counts.get(plan["share_basis"], 0) + 1
        if plan["backtest_origins"]:
            backtests += 1
            if not math.isnan(plan["backtest_wape"]):
                wape_cumulative.append(plan["backtest_wape"])
            if not math.isnan(plan["backtest_weekly_wape"]):
                wape_weekly.append(plan["backtest_weekly_wape"])

        qty_total = float(rec.p90 if service == "p90" else rec.p50)
        p50_total = float(rec.p50) if pd.notna(rec.p50) else math.nan
        p90_total = float(rec.p90) if pd.notna(rec.p90) else math.nan
        if math.isnan(qty_total):
            raise AssertionError(f"窗口总量为空（{key}），不应走到这里")

        for k, share in enumerate(plan["share"]):
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
                    "share_basis": plan["share_basis"],
                    "share_weeks": plan["share_weeks"],
                    "note": plan["note"],
                    "method": plan["method"],
                    "backtest_wape": plan["backtest_wape"],
                    "fallback_reason": plan["fallback_reason"],
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
        "history_cutoff": hist_end.isoformat(),
        "rows": int(len(out)),
        "keys": int(len(agg)),
        "product_ids": int(out["product_id"].nunique()) if not out.empty else 0,
        "method_counts": dict(sorted(method_counts.items())),
        "share_basis": basis_counts,
        "backtest": {
            "keys": backtests,
            "median_weekly_wape": _median(wape_weekly),
            "median_cumulative_wape": _median(wape_cumulative),
        },
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


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2)
