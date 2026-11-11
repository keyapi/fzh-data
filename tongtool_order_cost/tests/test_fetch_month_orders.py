# -*- coding: utf-8 -*-
"""fetch_month_orders.py 的纯函数测试（不联网）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "fetch_month_orders", _ROOT / "scripts" / "fetch_month_orders.py")
mod = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader
_SPEC.loader.exec_module(mod)


def test_names() -> None:
    assert mod.names("202609") == ("通途订单202609", "2026年9月订单", "2026年9月FBA订单")


def test_clean_rows_trims_trailing_empty_rows_and_cells() -> None:
    rows = [["A", "B", ""], ["1", "", ""], ["", "", ""], ["", "", ""]]
    assert mod.clean_rows(rows) == [["A", "B"], ["1"]]


def test_clean_rows_keeps_header_and_middle_blanks() -> None:
    rows = [["订单号", "通途SKU"], ["X", ""], ["", "Y"], []]
    assert mod.clean_rows(rows) == [["订单号", "通途SKU"], ["X"], ["", "Y"]]


def test_require_columns() -> None:
    mod.require_columns(["订单号", "通途SKU"], ("订单号", "通途SKU"), "x")
    try:
        mod.require_columns(["订单号"], ("订单号", "通途SKU"), "x")
    except SystemExit as exc:
        assert "通途SKU" in str(exc)
    else:
        raise AssertionError("缺列应退出")
