from __future__ import annotations

import datetime as _dt
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from parcel_track.scripts.daily_fetch_and_report import (
    date_range,
    extract_newest_xlsx,
    newest,
    newest_xlsx,
)


def test_date_range_ends_yesterday_never_today():
    """通途不接受「发货时间」截止为当天——这是实测踩过的硬约束。"""
    today = _dt.date(2026, 9, 18)

    start, end = date_range(today)

    assert start == "2026-09-11"
    assert end == "2026-09-17"
    assert end != today.isoformat()


def test_date_range_spans_seven_days():
    start, end = date_range(_dt.date(2026, 1, 5))
    begin = _dt.date.fromisoformat(start)
    finish = _dt.date.fromisoformat(end)

    assert (finish - begin).days == 6      # 含头含尾共 7 天


def test_newest_picks_by_mtime(tmp_path: Path):
    old = tmp_path / "old.zip"
    new = tmp_path / "new.zip"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    import os

    os.utime(old, (1_600_000_000, 1_600_000_000))
    os.utime(new, (1_700_000_000, 1_700_000_000))

    assert newest(tmp_path.glob("*.zip")) == new


def test_newest_ignores_excel_lock_files(tmp_path: Path):
    """Excel 打开文件时会留 `~$xxx.xlsx`，不能被当成最新导出。"""
    real = tmp_path / "real.xlsx"
    lock = tmp_path / "~$real.xlsx"
    real.write_bytes(b"x")
    lock.write_bytes(b"y")
    import os

    os.utime(real, (1_600_000_000, 1_600_000_000))
    os.utime(lock, (1_700_000_000, 1_700_000_000))

    assert newest_xlsx(tmp_path) == real


def test_newest_returns_none_on_missing_dir(tmp_path: Path):
    assert newest_xlsx(tmp_path / "nope") is None


def test_extract_newest_xlsx_pulls_the_sheet_out(tmp_path: Path):
    wb = Workbook()
    wb.active.append(["跟踪号"])
    sheet = tmp_path / "inner.xlsx"
    wb.save(sheet)
    zpath = tmp_path / "订单详情统计.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(sheet, "202609180904.xlsx")

    out = extract_newest_xlsx(zpath, tmp_path / "input", "通途_20260911_20260917.xlsx")

    assert out.is_file()
    assert out.parent.name == "input"
    assert out.name == "通途_20260911_20260917.xlsx"


def test_extract_rejects_zip_without_xlsx(tmp_path: Path):
    zpath = tmp_path / "empty.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("readme.txt", "no sheet here")

    with pytest.raises(ValueError, match="没有 xlsx"):
        extract_newest_xlsx(zpath, tmp_path / "input", "x.xlsx")
