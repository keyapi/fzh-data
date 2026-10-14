from __future__ import annotations

from stock_alert.client import StockRow
from stock_alert.scan import scan


def _row(wh: str, sku: str, available: float, intransit: float = 0.0) -> StockRow:
    return StockRow(wh, sku, available, intransit, 0.0, 0.0)


def test_scan_filters_below_threshold_and_aggregates():
    rows = {
        "美中-FZH-DANEEY": [
            _row("美中-FZH-DANEEY", "A", 0, intransit=2),
            _row("美中-FZH-DANEEY", "B", 4, intransit=1),
            _row("美中-FZH-DANEEY", "C", 5),  # 恰好等于阈值，不算
            _row("美中-FZH-DANEEY", "D", 12),
        ],
        "美东-CENTRADE": [
            _row("美东-CENTRADE", "E", 3),
        ],
    }
    result = scan(rows, threshold=5)
    by_wh = {w.warehouse: w for w in result.warehouses}

    assert by_wh["美中-FZH-DANEEY"].count == 2
    assert by_wh["美中-FZH-DANEEY"].intransit_total == 3
    assert [s.sku for s in by_wh["美中-FZH-DANEEY"].low] == ["A", "B"]  # 按可用升序
    assert by_wh["美东-CENTRADE"].count == 1
    assert result.total_low == 3


def test_scan_empty_is_zero():
    result = scan({}, threshold=5)
    assert result.total_low == 0
    assert result.warehouses == []


def test_scan_none_below_threshold():
    rows = {"波兰-FZHPoland-covers": [_row("波兰-FZHPoland-covers", "A", 50)]}
    result = scan(rows, threshold=5)
    assert result.warehouses[0].count == 0
    assert result.total_low == 0
