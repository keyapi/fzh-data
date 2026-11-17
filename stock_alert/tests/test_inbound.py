from __future__ import annotations

import datetime as _dt

from stock_alert.inbound import aggregate


def test_aggregate_sums_duplicates_filters_non_purchase_and_nonpositive():
    rows = {
        "W": [
            {"sku": "A", "voucher_type": "02", "available_increase": 10},
            {"sku": "A", "voucher_type": "02", "available_increase": "5"},
            {"sku": "B", "voucher_type": "02", "available_increase": -3},
            {"sku": "C", "voucher_type": "04", "available_increase": 99},
            {"sku": " ", "voucher_type": "02", "available_increase": 4},
        ]
    }
    result = aggregate(rows, names={"A": "产品甲"})
    wh = result.warehouses[0]
    assert [(i.sku, i.qty, i.name) for i in wh.items] == [("A", 15.0, "产品甲")]
    assert result.total_skus == 1
    assert result.total_qty == 15


def test_aggregate_sorts_desc_by_qty():
    rows = {
        "W": [
            {"sku": "A", "voucher_type": "02", "available_increase": 1},
            {"sku": "B", "voucher_type": "02", "available_increase": 9},
            {"sku": "C", "voucher_type": "02", "available_increase": 5},
        ]
    }
    result = aggregate(rows)
    assert [i.sku for i in result.warehouses[0].items] == ["B", "C", "A"]


def test_aggregate_empty_and_multiple_warehouses():
    result = aggregate({"W": [], "V": [{"sku": "X", "voucher_type": "02", "available_increase": 2}]},
                       day=_dt.date(2026, 11, 16))
    assert result.day == _dt.date(2026, 11, 16)
    assert result.warehouses[0].count == 0
    assert result.warehouses[1].total_qty == 2
    assert result.total_skus == 1


def test_purchase_inbound_counts_positive_events_only():
    result = aggregate({"W": [
        {"sku": "A", "voucher_type": "02", "available_increase": 10},
        {"sku": "A", "voucher_type": "02", "available_increase": -4},
        {"sku": "A", "voucher_type": "02", "available_increase": 0},
    ]})
    assert result.total_qty == 10


def test_invalid_quantity_is_not_silently_zero():
    import pytest
    for qty in ("broken", None, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            aggregate({"W": [{"sku": "A", "voucher_type": "02", "available_increase": qty}]})
