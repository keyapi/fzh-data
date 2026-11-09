#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弧形海绵带圆柱颈枕旧->新 SKU 转换：映射、冲突与库存判定。"""

from __future__ import annotations

import csv

import arc_sku_migration as mig

HEADER = [
    "PO Number",
    "PO Line #",
    "Record Type",
    "Qty Ordered",
    "Vendor Style",
    "Buyers Catalog or Stock Keeping #",
]


def write_csv(path, body):
    lines = [",".join(HEADER)] + [",".join(row) for row in body]
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig")
    return path


def read_csv(path):
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.reader(text.splitlines()))


def test_maps_old_grey_and_ivory(tmp_path):
    mapping = mig.load_mapping(mig.DEFAULT_MAP)
    csv_path = write_csv(
        tmp_path / "order.csv",
        [
            ["100000001", "", "H", "", "", ""],
            ["100000001", "1", "D", "1", "TT0031058K0062965", "5938375"],
            ["100000001", "2", "D", "1", "TT0031059K0062966", "4020032"],
            ["100000001", "3", "D", "1", "TT0031010K0062876", "4767728"],
        ],
    )
    header, rows = mig.read_order_csv(csv_path)
    plan = mig.analyze_rows(header, rows, mapping)

    assert plan.detail_rows == 3
    assert len(plan.replace) == 2
    assert plan.other_rows == 1
    assert not plan.has_blockers

    out = mig.apply_plan(header, rows, plan)
    detail = [row for row in out if len(row) > 2 and row[2].upper() == "D"]
    assert detail[0][4] == "TT0312672K0064328"
    assert detail[1][4] == "TT0312673K0064329"
    assert detail[2][4] == "TT0031010K0062876"


def test_already_new_sku_passes(tmp_path):
    mapping = mig.load_mapping(mig.DEFAULT_MAP)
    csv_path = write_csv(
        tmp_path / "order.csv",
        [
            ["100000001", "", "H", "", "", ""],
            ["100000001", "1", "D", "1", "TT0312672K0064328", "5938375"],
        ],
    )
    header, rows = mig.read_order_csv(csv_path)
    plan = mig.analyze_rows(header, rows, mapping)

    assert not plan.replace
    assert plan.already_new["TT0312672K0064328"] == 1
    assert not plan.has_blockers


def test_pb_sku_paired_with_wrong_old_sku_is_conflict(tmp_path):
    mapping = mig.load_mapping(mig.DEFAULT_MAP)
    csv_path = write_csv(
        tmp_path / "order.csv",
        [
            ["100000001", "", "H", "", "", ""],
            ["100000001", "1", "D", "1", "TT0031059K0062966", "5938375"],
        ],
    )
    header, rows = mig.read_order_csv(csv_path)
    plan = mig.analyze_rows(header, rows, mapping)

    assert plan.conflicts
    assert "5938375" in plan.conflicts[0]
    assert plan.has_blockers


def test_deep_blue_blocks_write_without_allow(tmp_path):
    csv_path = write_csv(
        tmp_path / "order.csv",
        [
            ["100000001", "", "H", "", "", ""],
            ["100000001", "1", "D", "1", "TT0031058K0062965", "5938375"],
            ["100000001", "2", "D", "1", "TT0312674K0064330", "9999999"],
        ],
    )
    out = tmp_path / "order_新SKU.csv"

    code = mig.main(["map-order", "--csv", str(csv_path), "--out", str(out)])

    assert code == 2
    assert not out.exists()


def test_allow_unmapped_writes_converted_copy(tmp_path):
    csv_path = write_csv(
        tmp_path / "order.csv",
        [
            ["100000001", "", "H", "", "", ""],
            ["100000001", "1", "D", "1", "TT0031058K0062965", "5938375"],
            ["100000001", "2", "D", "1", "TT0312674K0064330", "9999999"],
        ],
    )
    out = tmp_path / "order_新SKU.csv"

    code = mig.main(
        ["map-order", "--csv", str(csv_path), "--out", str(out), "--allow-unmapped"]
    )

    assert code == 0
    rows = read_csv(out)
    assert rows[0] == HEADER
    detail = [row for row in rows if len(row) > 2 and row[2].upper() == "D"]
    assert detail[0][4] == "TT0312672K0064328"
    assert detail[1][4] == "TT0312674K0064330"


def test_check_does_not_write(tmp_path):
    csv_path = write_csv(
        tmp_path / "order.csv",
        [
            ["100000001", "", "H", "", "", ""],
            ["100000001", "1", "D", "1", "TT0031058K0062965", "5938375"],
        ],
    )
    before = sorted(p.name for p in tmp_path.iterdir())

    code = mig.main(["check", "--csv", str(csv_path)])

    assert code == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_evaluate_stock_flags_zero_new_and_nonzero_old():
    mapping = mig.load_mapping(mig.DEFAULT_MAP)
    stock = {
        "TT0312672K0064328": {"availableStockQuantity": 0},
        "TT0031058K0062965": {"availableStockQuantity": 5},
        "TT0312673K0064329": {"availableStockQuantity": 3},
        "TT0031059K0062966": {"availableStockQuantity": 0},
    }
    errors, warnings = mig.evaluate_stock(stock, mapping)

    assert any("TT0312672K0064328" in e for e in errors)
    assert any("TT0031058K0062965" in w for w in warnings)


def test_stock_roles_include_old_new_and_unconfirmed():
    mapping = mig.load_mapping(mig.DEFAULT_MAP)
    roles = {r["sku"]: r["role"] for r in mig.stock_roles(mapping)}

    assert roles["TT0031058K0062965"] == "旧"
    assert roles["TT0312672K0064328"] == "新"
    assert roles["TT0312674K0064330"] == "新?"
