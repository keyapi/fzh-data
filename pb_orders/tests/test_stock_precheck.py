#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPS New 订单库存预检：按 Detail 行分类，保留必要 Header。"""

from __future__ import annotations

import pandas as pd
import pytest
from openpyxl import load_workbook

import stock_precheck


COLUMNS = [
    "PO Number",
    "PO Line #",
    "Record Type",
    "Qty Ordered",
    "Vendor Style",
    "Buyers Catalog or Stock Keeping #",
    "Customer Order #",
]


def write_raw_csv(path):
    """3 个 PO：全有货、全缺货、部分缺货。"""
    pd.DataFrame(
        [
            ["100000001", "", "H", "", "", "", "C1"],
            ["100000001", "1", "D", 2, "STYLE-A", "BUYER-A", "C1"],
            ["100000002", "", "H", "", "", "", "C2"],
            ["100000002", "1", "D", 3, "STYLE-B", "BUYER-B", "C2"],
            ["100000003", "", "H", "", "", "", "C3"],
            ["100000003", "1", "D", 1, "STYLE-C", "BUYER-C", "C3"],
            ["100000003", "2", "D", 4, "Style-D", "BUYER-D", "C3"],
        ],
        columns=COLUMNS,
    ).to_csv(path, index=False)
    return path


# 与 SPS 真实导出同构的「参差」形状：末列无名、且数据行比表头少一列。
# 实测 20260917 的真实导出就是这样（表头 147 列、数据行 146 列）。
RAGGED_HEADER = 'PO Number,PO Line #,Record Type,Qty Ordered,Vendor Style,Buyers Catalog or Stock Keeping #,Customer Order #,'
RAGGED_ROWS = [
    "100000001,,H,,,,C1",
    "100000001,1,D,2,STYLE-A,BUYER-A,C1",
    "100000002,,H,,,,C2",
    "100000002,1,D,3,STYLE-B,BUYER-B,C2",
    "100000002,2,D,5,STYLE-C,BUYER-C,C2",
    "100000003,,H,,,,C3",
    "100000003,1,D,1,STYLE-D,BUYER-D,C3",
]
# 断货 STYLE-B（部分缺货 PO -> 保留 Header）与 STYLE-D（整单缺货 -> 整组剔除）
RAGGED_NO_STOCK = ["STYLE-B", "STYLE-D"]
RAGGED_KEPT = [RAGGED_ROWS[i] for i in (0, 1, 2, 4)]


def write_ragged_csv(path):
    path.write_text("\n".join([RAGGED_HEADER, *RAGGED_ROWS]) + "\n", encoding="utf-8")
    return path


def test_detail_level_filter_keeps_header_for_mixed_po(tmp_path):
    source = write_raw_csv(tmp_path / "check0stock.csv")
    result = stock_precheck.run_stock_check(
        source,
        ["style-b", "STYLE-D"],
        tmp_path / "out",
    )

    checked = pd.read_csv(result.checked_csv, dtype=str, keep_default_na=False)
    assert list(checked.columns) == COLUMNS
    assert checked[["PO Number", "Record Type", "PO Line #"]].values.tolist() == [
        ["100000001", "H", ""],
        ["100000001", "D", "1"],
        ["100000003", "H", ""],
        ["100000003", "D", "1"],
    ]
    # 全缺货 PO 整组移除；部分缺货 PO 的 Header 保留，只剔除缺货 Detail。
    assert "100000002" not in set(checked["PO Number"])
    assert "100000003" in set(checked["PO Number"])
    assert "2" not in set(checked.loc[checked["PO Number"] == "100000003", "PO Line #"])


def test_report_reconciles_po_detail_and_quantity(tmp_path):
    result = stock_precheck.run_stock_check(
        write_raw_csv(tmp_path / "raw.csv"),
        ["STYLE-B", "style-d"],
        tmp_path / "out",
    )
    report = result.report

    assert report["po"] == {
        "total": 3,
        "fully_in_stock": 1,
        "partially_out_of_stock": 1,
        "fully_out_of_stock": 1,
        "retained": 2,
    }
    assert report["details"] == {
        "total": 4,
        "in_stock": 2,
        "out_of_stock": 2,
        "retained": 2,
        "diff": 0,
    }
    assert report["quantity"] == {
        "total": 10,
        "in_stock": 3,
        "out_of_stock": 7,
        "diff": 0,
    }
    assert report["mixed_po_count"] == 1
    assert report["no_stock_snapshot"] == ["STYLE-B", "style-d"]


def test_every_operation_detail_table_contains_both_skus(tmp_path):
    result = stock_precheck.run_stock_check(
        write_raw_csv(tmp_path / "raw.csv"),
        ["STYLE-B", "STYLE-D"],
        tmp_path / "out",
    )
    wb = load_workbook(result.operations_xlsx, read_only=True, data_only=True)

    for sheet_name in ("部分缺货PO-逐行操作", "ASN有货明细", "缺货明细", "全部缺货PO"):
        ws = wb[sheet_name]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        assert "Buyers Catalog or Stock Keeping #" in headers, sheet_name
        assert "Vendor Style" in headers, sheet_name

    mixed = list(wb["部分缺货PO-逐行操作"].iter_rows(min_row=2, values_only=True))
    assert len(mixed) == 2
    assert {row[headers.index("Vendor Style")] for row in mixed} == {"STYLE-C", "Style-D"}


def test_checked_csv_round_trip_preserves_columns_and_headers(tmp_path):
    source = write_raw_csv(tmp_path / "raw.csv")
    result = stock_precheck.run_stock_check(source, ["STYLE-D"], tmp_path / "out")
    checked = pd.read_csv(result.checked_csv, dtype=str, keep_default_na=False)

    assert list(checked.columns) == COLUMNS
    retained_pos = set(checked["PO Number"])
    headers = checked[checked["Record Type"] == "H"].groupby("PO Number").size().to_dict()
    details = checked[checked["Record Type"] == "D"].groupby("PO Number").size().to_dict()
    assert set(headers) == retained_pos == set(details)
    assert all(count == 1 for count in headers.values())


def test_missing_required_column_fails_without_outputs(tmp_path):
    source = write_raw_csv(tmp_path / "raw.csv")
    df = pd.read_csv(source)
    df.drop(columns=["Vendor Style"]).to_csv(source, index=False)
    out = tmp_path / "out"

    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, ["STYLE-B"], out)
    assert exc.value.code == "missing_columns"
    assert not out.exists() or not any(out.iterdir())


def test_invalid_detail_data_fails(tmp_path):
    source = write_raw_csv(tmp_path / "raw.csv")
    df = pd.read_csv(source, dtype=str, keep_default_na=False)
    df.loc[(df["PO Number"] == "100000003") & (df["PO Line #"] == "1"), "Qty Ordered"] = "oops"
    df.to_csv(source, index=False)

    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, [], tmp_path / "out")
    assert exc.value.code == "invalid_detail"
    assert "Qty Ordered" in exc.value.message


def test_duplicate_po_line_fails(tmp_path):
    source = write_raw_csv(tmp_path / "raw.csv")
    df = pd.read_csv(source, dtype=str, keep_default_na=False)
    duplicate = df[(df["PO Number"] == "100000003") & (df["PO Line #"] == "1")]
    pd.concat([df, duplicate], ignore_index=True).to_csv(source, index=False)

    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, [], tmp_path / "out")
    assert exc.value.code == "duplicate_po_line"


def test_operations_table_shows_integer_qty_and_sources_columns(tmp_path):
    """SPS 导出里 Qty 是 `1.0` 字面量；人看的表要显示 `1`，且两个 SKU 都在。"""
    source = write_ragged_csv(tmp_path / "raw.csv")
    result = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, tmp_path / "out")
    wb = load_workbook(result.operations_xlsx, read_only=True, data_only=True)

    ws = wb["ASN有货明细"]
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == (
        "PO Number", "PO Line #", "Buyers Catalog or Stock Keeping #", "Vendor Style",
        "Qty Ordered", "库存状态", "PO 库存状态", "SPS 操作",
    )
    by_sku = {row[3]: row for row in rows[1:]}
    assert by_sku["STYLE-A"][4] == "2"      # 不是 "2.0"
    assert by_sku["STYLE-C"][4] == "5"

    # 源 CSV 不受显示处理影响：仍是逐行照搬的原文
    assert "2" in result.checked_csv.read_text(encoding="utf-8")


def test_checked_csv_keeps_source_line_shape(tmp_path):
    """逐行照搬：空列名、参差列数、行尾都与 SPS 导出同构，不重新序列化。"""
    source = write_ragged_csv(tmp_path / "check0stock order x2.csv")
    result = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, tmp_path / "out")

    text = result.checked_csv.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == RAGGED_HEADER  # 末列仍是空的，没有 Unnamed: 7
    assert "Unnamed" not in text
    assert lines[1:] == RAGGED_KEPT
    assert text.endswith("\n") and not text.startswith("﻿")
    assert "\r\n" not in text


def test_checked_csv_is_byte_identical_to_a_sps_style_export(tmp_path):
    """同一份数据、同一批剔除结果 -> 字节级一致（SPS 口径可复现）。"""
    source = write_ragged_csv(tmp_path / "check0stock order x2.csv")
    result = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, tmp_path / "out")

    # SPS 自己导出的 checked0stock 就是「表头 + 保留行」的原文
    expected = "\n".join([RAGGED_HEADER, *RAGGED_KEPT]) + "\n"
    assert result.checked_csv.read_text(encoding="utf-8") == expected


def test_source_with_field_newline_is_rejected(tmp_path):
    """字段里含换行时按行照搬不成立，宁可报错也不出格式不同的文件。"""
    source = tmp_path / "check0stock order x1.csv"
    source.write_text(
        RAGGED_HEADER + "\n"
        + '100000001,,H,,,,C1\n'
        + '100000001,1,D,2,STYLE-A,"BUYER\nA",C1\n',
        encoding="utf-8",
    )
    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, [], tmp_path / "out")
    assert exc.value.code == "ragged_source"


def test_output_name_uses_retained_po_count(tmp_path):
    """名字里的 `x{N}` 要等于筛完剩下的 PO 数（SPS 历史命名也是这么变的）。"""
    source = write_ragged_csv(tmp_path / "raw.csv")
    result = stock_precheck.run_stock_check(
        source, RAGGED_NO_STOCK, tmp_path / "out", name_stem="check0stock order x21 20260917_0338:45"
    )
    # 3 个 PO，STYLE-D 那个整单剔除 -> 剩 2
    assert result.report["po"]["retained"] == 2
    assert result.checked_csv.name == "checked0stock order x2 20260917_0338-45.csv"
    assert result.operations_xlsx.name == "SPS库存检查操作表-order x2 20260917_0338-45.xlsx"


def test_output_name_falls_back_when_stem_empty(tmp_path):
    source = write_ragged_csv(tmp_path / "raw.csv")
    result = stock_precheck.run_stock_check(source, [], tmp_path / "out", name_stem="")
    assert result.checked_csv.name == "checked0stock orders.csv"


def test_po_count_replacement_leaves_other_names_alone():
    assert stock_precheck._with_po_count("order x21 20260917", 18) == "order x18 20260917"
    assert stock_precheck._with_po_count("order 20260917_0338_456788", 5) == "order 20260917_0338_456788"
    # 别把 SKU 里的字符当成记号
    assert stock_precheck._with_po_count("CENx21 order", 3) == "CENx21 order"


def test_web_table_payload_is_built_from_the_same_frames(tmp_path):
    """网页明细表与 xlsx 用同一批 DataFrame；超限才截断且明确标出。"""
    source = write_ragged_csv(tmp_path / "raw.csv")
    result = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, tmp_path / "out")
    tables = result.report["tables"]

    assert set(tables) == {
        "操作总览", "部分缺货PO-逐行操作", "ASN有货明细",
        "缺货明细", "全部缺货PO", "检查报告", "原始剔除行",
    }
    in_stock = tables["ASN有货明细"]
    assert in_stock["columns"][:5] == [
        "PO Number", "PO Line #", "Buyers Catalog or Stock Keeping #",
        "Vendor Style", "Qty Ordered",
    ]
    assert "库存状态" in in_stock["columns"]
    assert in_stock["total"] == 2 and len(in_stock["rows"]) == 2
    assert in_stock["truncated"] is False

    limited = stock_precheck._tables_payload(
        {"ASN有货明细": pd.DataFrame({"A": list(range(10))})}, 3
    )["ASN有货明细"]
    assert limited["total"] == 10 and len(limited["rows"]) == 3 and limited["truncated"] is True
