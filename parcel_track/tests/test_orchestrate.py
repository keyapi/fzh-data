from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from fedex_track.cli import _mock_many
from ups_track.cli import _mock_query

from parcel_track.ingest import ingest_tongtu
from parcel_track.orchestrate import run_report


def _write_tt(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["跟踪号", "邮寄方式", "渠道", "订单号", "包裹号", "发货日期"])
    ws.append(["1Z999AA10123456784", "UPS Ground", "Amazon US", "A1", "P1", "2026-09-01"])
    ws.append(["382954490594", "FedEx Ground", "Amazon US", "A2", "P2", "2026-09-01"])
    ws.append(["GFUS010188602773264169", "GOFO", "Amazon US", "A3", "P3", "2026-09-01"])
    ws.append(["999", "GLS", "Amazon DE", "A4", "P4", "2026-09-01"])
    wb.save(path)


def test_ingest_counts(tmp_path: Path):
    x = tmp_path / "tt.xlsx"
    _write_tt(x)
    r = ingest_tongtu(str(x))
    assert len(r.rows) == 4
    assert len(r.ups) == 1
    assert len(r.fedex) == 1
    assert len(r.parked) == 2


def test_orchestrate_mixed_mock(tmp_path: Path):
    x = tmp_path / "tt.xlsx"
    _write_tt(x)
    out = tmp_path / "ops.xlsx"
    prefix = str(tmp_path / "run")
    stats = run_report(
        str(x), str(out), prefix=prefix, mock=True,
        ups_query=_mock_query, fedex_query=_mock_many,
    )
    assert stats["in"] == 4
    assert stats["ups"] == 1
    assert stats["fedex"] == 1
    assert stats["parked"] == 2
    assert stats["called"]["ups"] is True
    assert stats["called"]["fedex"] is True
    assert out.is_file()
    wb = load_workbook(out)
    assert "未支持停放" in wb.sheetnames
    parked = wb["未支持停放"]
    reasons = [parked.cell(row=r, column=2).value for r in range(2, 4)]
    assert any("gofo" in str(x) for x in reasons)
    assert any("gls" in str(x) for x in reasons)


def test_orchestrate_ups_only_skips_fedex(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["跟踪号", "邮寄方式", "渠道", "订单号", "包裹号"])
    ws.append(["1Z999AA10123456784", "UPS", "Amazon US", "A1", "P1"])
    p = tmp_path / "ups.xlsx"
    wb.save(p)
    called = {"fedex": False}

    def boom(_numbers):
        called["fedex"] = True
        raise AssertionError("FedEx should not be called")

    stats = run_report(
        str(p), str(tmp_path / "ops.xlsx"), prefix=str(tmp_path / "r"),
        ups_query=_mock_query, fedex_query=boom,
    )
    assert stats["called"]["ups"] is True
    assert stats["called"]["fedex"] is False
    assert called["fedex"] is False
