from __future__ import annotations

import datetime as _dt

import pandas as pd

from parcel_track.classify import (
    GLS_HANDLING_DAYS,
    HANDLING_DAYS,
    PL_HOLIDAYS_2026,
    STUCK_DAYS,
    TRANSIT_SLOW_DAYS,
    _cat,
    policy_for,
)


def _ts(*ymd):
    return pd.Timestamp(_dt.datetime(*ymd))


def test_late_handover_only():
    now = _ts(2026, 9, 10, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)
    pu = _ts(2026, 9, 4, 10, 0)
    dev = _ts(2026, 9, 5, 10, 0)
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev) == "late_handover"


def test_delay_wins_over_late():
    now = _ts(2026, 9, 20, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)
    pu = _ts(2026, 9, 4, 10, 0)
    dev = _ts(2026, 9, 18, 10, 0)
    assert TRANSIT_SLOW_DAYS == 6
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev) == "carrier_slow"


def test_stuck_stale_scan():
    now = _ts(2026, 9, 20, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)
    pu = _ts(2026, 9, 2, 10, 0)
    last = _ts(2026, 9, 10, 10, 0)
    assert STUCK_DAYS == 7
    assert _cat(pd.NaT, pu, label, pd.NaT, now, last_event=last) == "stuck"


def test_friday_monday_not_late():
    now = _ts(2026, 9, 10, 12, 0)
    label = _ts(2026, 9, 4, 10, 0)
    pu = _ts(2026, 9, 7, 9, 0)
    dev = _ts(2026, 9, 8, 15, 0)
    assert HANDLING_DAYS == 1
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev) == "delivered_ok"


def test_gls_handling_2_thursday_monday_not_late():
    """Thu 录入 → Mon 交接：美国历 HANDLING=1 会迟发；GLS HANDLING=2 不算迟。"""
    now = _ts(2026, 9, 10, 12, 0)
    label = _ts(2026, 8, 27, 10, 0)  # Thursday
    pu = _ts(2026, 8, 31, 10, 0)     # Monday
    dev = _ts(2026, 9, 1, 10, 0)
    handling, holidays = policy_for("gls")
    assert handling == GLS_HANDLING_DAYS == 2
    assert holidays == PL_HOLIDAYS_2026
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev, handling_days=1, holidays=holidays) == "late_handover"
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev, handling_days=handling, holidays=holidays) == "delivered_ok"
