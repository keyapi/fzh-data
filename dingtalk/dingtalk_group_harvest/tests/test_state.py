from __future__ import annotations

import datetime as dt

from dingtalk.dingtalk_group_harvest import state


def test_window_without_watermark_uses_backfill_days():
    now = dt.datetime(2026, 11, 3, 10, 0, tzinfo=state.CST)
    start, end = state.window({}, backfill_days=60, now=now)
    assert end == "2026-11-03T10:00:00+08:00"
    assert start == "2026-09-04T10:00:00+08:00"


def test_window_with_watermark_overlaps_one_second():
    entry = {"last_message_time": "2026-11-03 09:00:00"}
    now = dt.datetime(2026, 11, 3, 10, 0, tzinfo=state.CST)
    start, _ = state.window(entry, backfill_days=60, now=now)
    assert start == "2026-11-03T08:59:59+08:00"


def test_advance_uses_newest_message():
    entry = {}
    state.advance(
        entry,
        [
            {"createTime": "2026-11-03 09:00:00", "messageId": "a"},
            {"createTime": "2026-11-03 09:05:00", "messageId": "b"},
        ],
        window_end="2026-11-03T10:00:00+08:00",
    )
    assert entry["last_message_time"] == "2026-11-03 09:05:00"
    assert entry["last_message_id"] == "b"


def test_advance_without_messages_moves_to_window_end():
    entry = {}
    state.advance(entry, [], window_end="2026-11-03T10:00:00+08:00")
    assert entry["last_message_time"] == "2026-11-03 10:00:00"


def test_save_and_load_state(tmp_path):
    data = {"version": 1, "groups": {"测试群": {"files": {}, "docs": {}}}}
    state.save_state(data, tmp_path)
    loaded = state.load_state(tmp_path)
    assert loaded == data
    assert (tmp_path / "state" / "watermarks.json").is_file()
