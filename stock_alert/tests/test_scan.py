from __future__ import annotations

from stock_alert.client import StockRow
from stock_alert.scan import apply_names, baseline_by_sku, mark_new, scan


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


def test_scan_drops_zero_available_and_zero_intransit():
    """可用=0 且在途=0 的死库存应被过滤掉；0 可用但有在途、或有货但低 仍计入。"""
    rows = {
        "美中-FZH-DANEEY": [
            _row("美中-FZH-DANEEY", "dead", 0, 0),       # 0/0 → 过滤
            _row("美中-FZH-DANEEY", "incoming", 0, 7),   # 0 可用 + 在途 7 → 计入
            _row("美中-FZH-DANEEY", "low", 3, 0),        # 有货但低 → 计入
        ]
    }
    result = scan(rows, threshold=5)
    assert [s.sku for s in result.warehouses[0].low] == ["incoming", "low"]  # 按可用升序


def test_apply_names_sets_product_names():
    result = scan({"W": [_row("W", "A", 1), _row("W", "B", 2)]}, threshold=5)
    apply_names(result, {"A": "产品甲"})
    assert [i.name for i in result.warehouses[0].low] == ["产品甲", ""]


def test_baseline_by_sku_takes_max_and_skips_blank():
    rows = [
        {"sku": "A", "available": 2},
        {"sku": "A", "available": 7},
        {"sku": " ", "available": 9},
        {"sku": "B", "available": "3"},
    ]
    assert baseline_by_sku(rows) == {"A": 7.0, "B": 3.0}


def test_mark_new_uses_yesterday_threshold_and_missing_sku():
    result = scan({"W": [_row("W", "A", 1), _row("W", "B", 2), _row("W", "C", 3)]}, threshold=5)
    mark_new(result, {"W": {"A": 8, "B": 1}}, threshold=5)
    flags = {i.sku: i.is_new for i in result.warehouses[0].low}
    # A: 昨日 8 >= 5 → 新增；B: 昨日 1 < 5 → 不算；C: 昨日无记录 → 新增
    assert flags == {"A": True, "B": False, "C": True}
    assert result.warehouses[0].baseline_missing is False


def test_mark_new_missing_baseline_marks_all_and_flags():
    result = scan({"W": [_row("W", "A", 1)]}, threshold=5)
    mark_new(result, {"W": {}}, threshold=5)
    assert result.warehouses[0].baseline_missing is True
    assert result.warehouses[0].low[0].is_new is True


def test_mark_new_none_is_noop():
    result = scan({"W": [_row("W", "A", 1)]}, threshold=5)
    mark_new(result, None, threshold=5)
    assert result.warehouses[0].low[0].is_new is False
    assert result.warehouses[0].baseline_missing is False
