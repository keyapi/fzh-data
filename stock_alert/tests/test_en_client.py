from __future__ import annotations

import datetime as _dt

from stock_alert.en_client import EnStockClient


class _FakeEn(EnStockClient):
    def __init__(self, responses):
        super().__init__("http://x", "k", "s")
        self.responses = list(responses)
        self.calls: list[tuple] = []

    def _get(self, path, params=None):
        self.calls.append((path, params))
        return self.responses.pop(0)


def test_to_row_maps_fields():
    row = EnStockClient._to_row({
        "warehouse": "W", "sku": "A", "available": 0,
        "intransit": 2, "defects": 1, "waiting_shipment": 3,
    })
    assert (row.warehouse, row.sku, row.available, row.intransit, row.defects, row.waiting) == (
        "W", "A", 0.0, 2.0, 1.0, 3.0)


def test_freshness_ok():
    today = "2026-11-04"
    en = _FakeEn([
        {"data": [{"name": "r1", "status": "Success", "complete": 1,
                   "snapshot_at": today + " 10:57:49", "creation": today + " 11:10:35"}]},
        {"data": [{"snapshot_at": today + " 10:57:49"}]},
    ])
    ok, detail = en.check_freshness(_dt.date(2026, 11, 4))
    assert ok, detail


def test_freshness_failed_run():
    today = "2026-11-04"
    en = _FakeEn([{"data": [{"name": "r", "status": "Failed", "complete": 0,
                             "snapshot_at": today + " 05:17:03", "creation": today + " 05:17:04"}]}])
    ok, detail = en.check_freshness(_dt.date(2026, 11, 4))
    assert not ok and "未成功" in detail


def test_freshness_stale_snapshot():
    en = _FakeEn([{"data": [{"name": "r", "status": "Success", "complete": 1,
                             "snapshot_at": "2026-11-03 05:17:21", "creation": "2026-11-04 05:17:00"}]}])
    ok, detail = en.check_freshness(_dt.date(2026, 11, 4))
    assert not ok and "不是今天" in detail


def test_freshness_latest_table_stale():
    today = "2026-11-04"
    en = _FakeEn([
        {"data": [{"name": "r", "status": "Success", "complete": 1,
                   "snapshot_at": today + " 10:57:49", "creation": today + " 11:10:35"}]},
        {"data": [{"snapshot_at": "2026-11-03 10:00:00"}]},
    ])
    ok, detail = en.check_freshness(_dt.date(2026, 11, 4))
    assert not ok and "Latest" in detail


def test_list_stocks_paginates():
    en = _FakeEn([
        {"data": [{"warehouse": "W", "sku": "A", "available": 0},
                  {"warehouse": "W", "sku": "B", "available": 9}]},
        {"data": [{"warehouse": "W", "sku": "C", "available": 1}]},
    ])
    rows = en.list_stocks("W", page_size=2)
    assert [r.sku for r in rows] == ["A", "B", "C"]
    assert en.calls[0][1]["limit_start"] == "0"
    assert en.calls[1][1]["limit_start"] == "2"


def test_list_stocks_filters_by_warehouse():
    en = _FakeEn([{"data": []}])
    en.list_stocks("美中-FZH-DANEEY")
    params = en.calls[0][1]
    assert "美中-FZH-DANEEY" in params["filters"]
