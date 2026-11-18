from __future__ import annotations

import datetime as dt

from stock_alert.tongtool_inbound import ENDPOINT, collect_inbound, fetch_changes, filter_purchase


class _Api:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def request(self, endpoint, body):
        self.calls.append((endpoint, body))
        index = int(body.get("pageNo") or 1) - 1
        rows = self.pages[index] if index < len(self.pages) else []
        return {"datas": {"array": rows}}


def test_fetch_changes_paginates_and_normalizes():
    page = [{"operateTime": "2026-11-18 09:00:00", "goodsSku": f"S{i}",
             "relatedVoucherType": "02", "availableStockIncrease": 1} for i in range(100)]
    api = _Api([page, page[:50]])
    rows = fetch_changes(api, "W", dt.datetime(2026, 11, 18, 0, 0, 0))
    assert len(rows) == 150
    assert api.calls[0][0] == ENDPOINT
    assert api.calls[0][1]["updatedDateFrom"] == "2026-11-18 00:00:00"
    assert rows[0]["sku"] == "S0"
    assert rows[0]["voucher_type"] == "02"
    assert rows[0]["available_increase"] == 1


def test_filter_purchase_window_positive_and_voucher():
    since = dt.datetime(2026, 11, 18, 10, 0, 0)
    until = dt.datetime(2026, 11, 18, 14, 0, 0)
    rows = [
        {"voucher_type": "02", "available_increase": 5, "operate_time": "2026-11-18 11:00:00"},
        {"voucher_type": "02", "available_increase": 0, "operate_time": "2026-11-18 11:00:00"},
        {"voucher_type": "02", "available_increase": -2, "operate_time": "2026-11-18 11:00:00"},
        {"voucher_type": "01", "available_increase": 5, "operate_time": "2026-11-18 11:00:00"},
        {"voucher_type": "02", "available_increase": 5, "operate_time": "2026-11-18 09:59:59"},
        {"voucher_type": "02", "available_increase": 5, "operate_time": "2026-11-18 14:00:01"},
        {"voucher_type": "02", "available_increase": 5, "operate_time": ""},
    ]
    out = filter_purchase(rows, since, until)
    assert [row["available_increase"] for row in out] == [5]


def test_collect_inbound_uses_injected_api():
    api = _Api([[{"operateTime": "2026-11-18 11:00:00", "goodsSku": "A",
                  "relatedVoucherType": "02", "availableStockIncrease": 3}]])
    out = collect_inbound(["W"], dt.datetime(2026, 11, 18, 10, 0, 0),
                          dt.datetime(2026, 11, 18, 14, 0, 0), api=api)
    assert [row["sku"] for row in out["W"]] == ["A"]
