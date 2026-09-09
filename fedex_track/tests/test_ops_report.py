"""ops_report._cat 对齐 runbook；多票跟踪号 strip。"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

from fedex_track.ops_report import (
    HANDLING_DAYS,
    STUCK_DAYS,
    TRANSIT_SLOW_DAYS,
    _bare_tracking,
    _cat,
    _late_level,
)


def _ts(*ymd):
    return pd.Timestamp(_dt.datetime(*ymd))


def test_friday_label_monday_pickup_not_late():
    # 2026-09-04 周五建标，2026-09-07 周一收件：营业日=1，减 HANDLING 3 → 不判迟
    now = _ts(2026, 9, 10, 12, 0)
    label = _ts(2026, 9, 4, 10, 0)
    pu = _ts(2026, 9, 7, 9, 0)
    dev = _ts(2026, 9, 8, 15, 0)
    assert HANDLING_DAYS == 3
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev) == "delivered_ok"


def test_late_handover_uses_label_to_pickup_bizdays():
    now = _ts(2026, 9, 10, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)  # 周二
    pu = _ts(2026, 9, 8, 10, 0)     # 下周二；含 Labor Day，营业日=4 > HANDLING 3
    dev = _ts(2026, 9, 9, 10, 0)
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev) == "late_handover"


def test_fedex_slow_uses_transit_slow_days_not_calendar_7():
    now = _ts(2026, 9, 20, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)
    pu = _ts(2026, 9, 1, 16, 0)  # 同日收件 → 不迟发
    # 9/1→9/11：含 Labor Day 仍 > TRANSIT_SLOW_DAYS(6)；9/10 恰好 =6 不算延误
    dev = _ts(2026, 9, 11, 16, 0)
    assert TRANSIT_SLOW_DAYS == 6
    assert _cat(dev, pu, label, pd.NaT, now, last_event=dev) == "fedex_slow"


def test_stuck_uses_last_scan_not_label_age():
    now = _ts(2026, 9, 20, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)  # 面单已 >7 天
    pu = _ts(2026, 9, 2, 10, 0)
    last = _ts(2026, 9, 19, 10, 0)  # 昨天还有扫描
    assert STUCK_DAYS == 7
    assert _cat(pd.NaT, pu, label, pd.NaT, now, last_event=last) == "in_transit"


def test_stuck_when_last_scan_stale():
    now = _ts(2026, 9, 20, 12, 0)
    label = _ts(2026, 9, 1, 10, 0)
    pu = _ts(2026, 9, 2, 10, 0)
    last = _ts(2026, 9, 10, 10, 0)
    assert _cat(pd.NaT, pu, label, pd.NaT, now, last_event=last) == "stuck"


def test_bare_tracking_strips_ticket_suffix():
    assert _bare_tracking("382954490594[1]") == "382954490594"
    assert _bare_tracking("382954490594") == "382954490594"


def test_late_level_none_does_not_raise():
    assert _late_level(None) == "迟发"
    assert _late_level(0) == "准时"
    assert _late_level(1) == "轻度迟发"
    assert _late_level(3) == "中度迟发"
    assert _late_level(6) == "重度迟发"
