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


REGION_STATS = {
    "in": 821, "ups": 1, "fedex": 1, "gls": 1, "parked": 223,
    "counts": {"delivered_ok": 566, "late_handover": 4, "carrier_slow": 10},
    "by_region": [
        {"region": "美东", "orders": 324, "queried": 101, "parked": 223,
         "counts": {"delivered_ok": 99, "carrier_slow": 2},
         "warehouses": ["美东-CENTRADE"]},
        {"region": "美中", "orders": 222, "queried": 222, "parked": 0,
         "counts": {"delivered_ok": 217, "stuck": 1, "missing_not_handed": 1,
                    "late_handover": 2, "not_found": 1},
         "warehouses": ["美中-FZH-DANEEY"]},
        {"region": "波兰", "orders": 275, "queried": 275, "parked": 0,
         "counts": {"delivered_ok": 250, "in_transit": 2, "carrier_slow": 8,
                    "missing_not_handed": 6, "late_handover": 2, "not_found": 7},
         "warehouses": ["波兰-FZHPoland-covers"]},
    ],
}


def test_summarize_splits_by_region():
    text = summarize(REGION_STATS, when=DAY)
    assert "**美东** · 324 单（已查 101 · 停放 223）" in text
    assert "**美中** · 222 单（已查 222 · 停放 0）" in text
    assert "**波兰** · 275 单（已查 275 · 停放 0）" in text
    # 各区域的待办只在各自小节内出现
    east = text.split("**美东**", 1)[1].split("**美中**", 1)[0]
    assert "承运延误：**2** 票" in east
    assert "漏发/未交接" not in east
    poland = text.split("**波兰**", 1)[1]
    assert "漏发/未交接：**6** 票" in poland
    assert "承运延误：**8** 票" in poland
    assert "合计 821 单 · 已查 598 · 停放 223" in text


def test_summarize_region_block_keeps_other_warehouse_names():
    """全停放的仓（如 WayfairCG-Cranbury仓）也必须出现在卡片里，不能凭空消失。"""
    stats = {"in": 55, "ups": 0, "fedex": 0, "gls": 0, "parked": 55,
             "by_region": [{"region": "其他", "orders": 55, "queried": 0, "parked": 55,
                            "counts": {}, "warehouses": ["WayfairCG-Cranbury仓"]}]}
    text = summarize(stats, when=DAY)
    assert "**其他** · 55 单（已查 0 · 停放 55）" in text
    assert "全部停放，未查询" in text
    assert "WayfairCG-Cranbury仓" in text


def test_summarize_falls_back_to_flat_without_by_region():
    """旧调用（mock/离线）没有 by_region 时仍输出原来的扁平视图。"""
    text = summarize(STATS, when=DAY)
    assert "**待办分类**" in text
    assert "迟发：**1** 票" in text
    assert "美东" not in text
