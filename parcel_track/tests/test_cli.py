from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from openpyxl import Workbook

from parcel_track.cli import main


def _write_tt(path: Path, number: str = "1Z999AA10123456784") -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["跟踪号", "邮寄方式", "渠道", "订单号", "包裹号", "发货日期", "邮编"])
    ws.append([number, "UPS Ground", "Amazon US", "A1", "P1", "2026-09-01", "77001"])
    wb.save(path)


def test_cli_tt_directory_picks_newest_xlsx(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    old = inbox / "通途非FBA订单_old.xlsx"
    new = inbox / "通途非FBA订单_new.xlsx"
    _write_tt(old)
    _write_tt(new)
    os.utime(old, (1_600_000_000, 1_600_000_000))
    os.utime(new, (1_700_000_000, 1_700_000_000))

    out = tmp_path / "ops.xlsx"
    assert main(["report", "--tt", str(inbox), "--out", str(out), "--mock"]) == 0
    assert out.is_file()


def test_cli_tt_directory_without_xlsx_fails(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    try:
        main(["report", "--tt", str(empty), "--out", str(tmp_path / "ops.xlsx"), "--mock"])
    except FileNotFoundError as exc:
        assert "没有 .xlsx" in str(exc)
    else:
        raise AssertionError("空目录应当报错")


def test_cli_defaults_out_to_dated_file_and_creates_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tt = tmp_path / "tt.xlsx"
    _write_tt(tt)

    assert main(["report", "--tt", str(tt), "--mock"]) == 0

    expected = tmp_path / "parcel_track_output" / f"ops_{_dt.date.today():%Y%m%d}.xlsx"
    assert expected.is_file()


def test_cli_notify_dry_run_prints_card_preview(tmp_path: Path, capsys):
    tt = tmp_path / "tt.xlsx"
    _write_tt(tt)

    rc = main(["report", "--tt", str(tt), "--out", str(tmp_path / "ops.xlsx"),
               "--mock", "--notify", "--dry-run"])

    assert rc == 0
    printed = capsys.readouterr().out
    assert "钉钉卡片预览" in printed
    assert "尾程运营异常" in printed
