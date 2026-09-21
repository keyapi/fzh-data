from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from fedex_track.cli import _mock_many
from parcel_track.cli import _mock_gls
from ups_track.cli import _mock_query

from parcel_track.ingest import ingest_tongtu
from parcel_track.orchestrate import run_report


def _write_tt(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["跟踪号", "邮寄方式", "渠道", "订单号", "包裹号", "发货日期", "邮编"])
    ws.append(["1Z999AA10123456784", "UPS Ground", "Amazon US", "A1", "P1", "2026-09-01", "77001"])
    ws.append(["382954490594", "FedEx Ground", "Amazon US", "A2", "P2", "2026-09-01", "19702"])
    ws.append(["GFUS010188602773264169", "GOFO", "Amazon US", "A3", "P3", "2026-09-01", "27695"])
    ws.append(["29626585597", "GLS-Poland>>GLS-Poland", "Amazon DE", "A4", "P4", "2026-09-01", "21706"])
    wb.save(path)


def test_ingest_counts(tmp_path: Path):
    x = tmp_path / "tt.xlsx"
    _write_tt(x)
    r = ingest_tongtu(str(x))
    assert len(r.rows) == 4
    assert len(r.ups) == 1
    assert len(r.fedex) == 1
    assert len(r.gls) == 1
    assert len(r.parked) == 1


def test_ingest_splits_multi_number_cell(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["跟踪号", "邮寄方式", "渠道", "订单号", "包裹号", "邮编"])
    ws.append(["29626585597, 1ZE935936893803162", "GLS-Poland>>GLS-Poland", "Mirakl", "A1", "P1", "12305"])
    p = tmp_path / "split.xlsx"
    wb.save(p)
    r = ingest_tongtu(str(p))
    assert len(r.rows) == 2
    assert {x.route.carrier for x in r.rows} == {"gls", "ups"}


def test_ingest_finds_header_below_metadata_rows(tmp_path: Path):
    """订单详情统计导出：前面约 30 行是筛选条件元数据，表头在第 30 行。

    坑：元数据区自己有一行 `跟踪号 | 全部`（只有 2 格），不能拿它当表头。
    """
    wb = Workbook()
    ws = wb.active
    ws.append(["订单详情统计"])
    for i in range(1, 28):
        ws.append([f"筛选条件{i}", "全部"])
    ws.append(["跟踪号", "全部"])          # ← 真陷阱：元数据行名也叫「跟踪号」
    ws.append(["物流商单号", "全部"])
    ws.append(["订单号", "发货时间", "执行发货人", "是否补发货", "平台SKU", "通途SKU",
               "产品名称", "品类", "发货仓库", "渠道账号", "销售站点",
               "邮寄方式", "跟踪号", "物流商单号", "发货日期", "省/州", "邮编"])
    ws.append(["O1", "09:37", "张三", "否", "SKU1", "TT001", "cover", "床品", "US-WH",
               "AMZUS", "Amazon US", "UPS Ground", "1Z999AA10123456784",
               "", "2026-09-10", "NJ", "77001"])
    p = tmp_path / "orderdetail_like.xlsx"
    wb.save(p)

    r = ingest_tongtu(str(p))

    assert len(r.rows) == 1
    assert r.ups and r.ups[0].number == "1Z999AA10123456784"
    assert r.ups[0].ident["邮寄方式"] == "UPS Ground"
    assert r.ups[0].ident["邮编"] == "77001"


def test_read_tongtu_sheet_raises_when_no_tracking_column(tmp_path: Path):
    from parcel_track.ingest import read_tongtu_sheet

    wb = Workbook()
    wb.active.append(["甲", "乙"])
    p = tmp_path / "nope.xlsx"
    wb.save(p)

    with pytest.raises(ValueError, match="跟踪号"):
        read_tongtu_sheet(str(p))


def test_orchestrate_mixed_mock(tmp_path: Path):
    x = tmp_path / "tt.xlsx"
    _write_tt(x)
    out = tmp_path / "ops.xlsx"
    prefix = str(tmp_path / "run")
    stats = run_report(
        str(x), str(out), prefix=prefix, mock=True,
        ups_query=_mock_query, fedex_query=_mock_many, gls_query=_mock_gls,
    )
    assert stats["in"] == 4
    assert stats["ups"] == 1
    assert stats["fedex"] == 1
    assert stats["gls"] == 1
    assert stats["parked"] == 1
    assert stats["called"]["ups"] is True
    assert stats["called"]["fedex"] is True
    assert stats["called"]["gls"] is True
    assert out.is_file()
    wb = load_workbook(out)
    assert "未支持停放" in wb.sheetnames
    parked = wb["未支持停放"]
    reasons = [parked.cell(row=r, column=2).value for r in range(2, 3)]
    assert any("gofo" in str(x) for x in reasons)


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
    assert stats["called"]["gls"] is False
    assert called["fedex"] is False
