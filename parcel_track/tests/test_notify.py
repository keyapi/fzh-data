from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from parcel_track.notify import notify_report, summarize

DAY = _dt.date(2026, 9, 17)

STATS = {
    "in": 4,
    "ups": 1,
    "fedex": 1,
    "gls": 1,
    "parked": 1,
    "classified": 3,
    "counts": {"delivered_ok": 2, "late_handover": 1},
}


def test_summarize_shows_headline_and_quiet_counts():
    text = summarize(STATS, when=DAY)
    assert "2026-09-17" in text
    assert "入 4 单" in text
    assert "迟发：**1** 票" in text
    assert "正常交付 2" in text


def test_summarize_merges_slow_aliases_into_one_line():
    text = summarize({**STATS, "counts": {"carrier_slow": 2, "fedex_slow": 1}}, when=DAY)
    assert "承运延误：**3** 票" in text
    assert text.count("承运延误") == 1


def test_summarize_reports_clean_when_nothing_to_do():
    text = summarize({**STATS, "counts": {"delivered_ok": 5}}, when=DAY)
    assert "待办分类" in text
    assert "- 无异常" in text


def test_summarize_omits_categories_with_zero_count():
    text = summarize(STATS, when=DAY)
    assert "卡件" not in text
    assert "漏发/未交接" not in text


def test_notify_report_dry_run_touches_no_network_or_credentials(tmp_path: Path):
    out = tmp_path / "ops.xlsx"
    result = notify_report(out, STATS, when=DAY, dry_run=True)
    assert result["dry_run"] is True
    assert result["title"] == "尾程运营异常 · 2026-09-17"
    assert result["file"] == str(out)


def test_notify_report_missing_file_fails_before_upload(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        notify_report(tmp_path / "nope.xlsx", STATS, dry_run=False)
