"""Period semantics for the replenishment refresh snapshot.

D5 forecasts are produced for a fixed horizon (97 or 157 days) anchored at the
pack's ``as_of``.  That total is a **full-period** demand and must never be
used as the demand of whatever remains of the window: a refresh run days after
the anchor would then over-order by the elapsed consumption.

A determinate suggestion is therefore only allowed when the caller declares an
explicit period of exactly the same length (an assumption they own), or when
the run has a valid explicit period and the evidence is otherwise complete.
Without an explicit period the row keeps ``period_basis="full_period"`` and the
caller refuses to judge instead of guessing.
"""
from __future__ import annotations

from datetime import date, timedelta

FULL_PERIOD = "full_period"
EXPLICIT_PERIOD = "explicit_period"


def parse_date(value):
    """ISO ``YYYY-MM-DD`` → ``date``; anything else → ``None`` (never guessed)."""
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def resolve_period(*, horizon_days, pack_as_of, as_of,
                   period_start=None, period_end=None):
    """Decide the period basis, bounds and whether a determinate answer is allowed.

    ``horizon_days`` is the D5 horizon length; ``pack_as_of`` is the anchor of
    that forecast; ``as_of`` is the refresh time point the caller asked for.
    """
    anchor = parse_date(pack_as_of)
    run_at = parse_date(as_of)
    try:
        days = int(float(horizon_days)) if horizon_days is not None else 0
    except (TypeError, ValueError):
        days = 0
    explicit = period_start is not None or period_end is not None
    basis = EXPLICIT_PERIOD if explicit else FULL_PERIOD
    out = {"basis": basis, "start": None, "end": None, "days": days or None,
           "determinate": False, "reason": None, "note": None,
           "forecast_anchor": anchor.isoformat() if anchor else None,
           "forecast_horizon_days": days or None,
           "as_of": run_at.isoformat() if run_at else None,
           "declared_start": period_start, "declared_end": period_end}

    if anchor is None:
        out["reason"] = "时点不明：数据包缺少可用 as_of，无法确定 D5 预测起点"
        return out
    full_end = anchor + timedelta(days=max(days, 1) - 1)
    if not explicit:
        out["start"], out["end"] = anchor.isoformat(), full_end.isoformat()
        out["reason"] = (
            f"D5 为整期预测（{days} 天，起点 {anchor.isoformat()}）；未提供显式期间，"
            "整期不得当剩余期用于补货"
        )
        return out

    if period_start is None or period_end is None:
        out["reason"] = "显式期间不完整：period_start 与 period_end 必须同时提供"
        return out
    start, end = parse_date(period_start), parse_date(period_end)
    if start is None or end is None:
        out["reason"] = "显式期间无法解析为 YYYY-MM-DD"
        return out
    out["start"], out["end"] = start.isoformat(), end.isoformat()
    span = (end - start).days + 1
    out["days"] = span
    if span <= 0:
        out["reason"] = "显式期间结束日早于开始日"
        return out
    if start < anchor:
        out["reason"] = (
            f"显式期间起点 {start.isoformat()} 早于 D5 预测起点 {anchor.isoformat()}，"
            "该期间不在预测覆盖范围内"
        )
        return out
    if days and span != days:
        out["reason"] = (
            f"显式期间 {span} 天 ≠ D5 预测期 {days} 天；不做比例外推，"
            "剩余期需求不能由整期总量代替"
        )
        return out
    out["determinate"] = True
    if start != anchor:
        shift = (start - anchor).days
        out["note"] = (
            f"D5 整期总量套用到调用方显式声明的等长期间（起点相差 {shift} 天，"
            "属调用方假设，非模型重算）"
        )
    return out
