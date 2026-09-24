#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPS New 订单库存预检：按 Detail 行分类，保留必要 Header。"""

from __future__ import annotations

from pathlib import Path

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


# 20260924 真实批次的形状：表头 147 字段、H 行 146、**D 行 148** ——
# D 行比表头**多**一个空字段（SPS 自己导出就这样，Excel 另存也常见）。
# pandas 遇到「比表头多」的行会整批 `ParserError: Expected 147 fields in line 3, saw 148`，
# 连未经手改的原始导出都读不进来。
# 这里的 RAGGED_HEADER 是 8 字段，所以 D 行要 9 字段（两个尾逗号）才对得上真实比例。
PADDED_ROWS = [
    "100000001,,H,,,,C1",
    "100000001,1,D,2,STYLE-A,BUYER-A,C1,,",
    "100000002,,H,,,,C2",
    "100000002,1,D,3,STYLE-B,BUYER-B,C2,,",
]


def write_padded_csv(path):
    path.write_text("\n".join([RAGGED_HEADER, *PADDED_ROWS]) + "\n", encoding="utf-8")
    return path


def _with_data_row(index: int, line: str) -> list[str]:
    rows = list(PADDED_ROWS)
    rows[index] = line
    return rows


def test_data_rows_with_extra_trailing_empty_field_are_accepted(tmp_path):
    """末尾多出**空**字段要能读进来（20260924 真实批次就是这形状）。

    回归：以前 pandas 整批 ParserError，页面只给一句「无法读取 SPS 订单 CSV」。
    """
    source = write_padded_csv(tmp_path / "check0stock order x2.csv")
    result = stock_precheck.run_stock_check(source, [], tmp_path / "out")

    assert result.report["po"]["total"] == 2
    assert result.report["details"]["total"] == 2
    # 削掉空字段不能是静默的
    assert result.report["warnings"], "削掉空字段必须留下提醒"
    assert "多出空字段" in result.report["warnings"][0]
    assert "2 行" in result.report["warnings"][0]
    # checked CSV 仍是逐行照搬原文（连那个多出来的空字段也照搬）
    lines = result.checked_csv.read_text(encoding="utf-8").splitlines()
    assert lines[0] == RAGGED_HEADER
    assert lines[1:5] == PADDED_ROWS
    assert lines[2].endswith(",,")


def test_extra_field_with_nonempty_value_is_rejected(tmp_path):
    """多出来的字段**有非空值**就无法判断它属于哪一列 —— 必须拒绝。"""
    source = tmp_path / "bad.csv"
    rows = _with_data_row(1, PADDED_ROWS[1] + "多余的非空值")   # 10 字段，尾部含非空
    source.write_text("\n".join([RAGGED_HEADER, *rows]) + "\n", encoding="utf-8")

    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, [], tmp_path / "out")
    assert exc.value.code == "ragged_source"
    assert "非空值" in exc.value.message


def test_mid_row_shift_is_caught_even_though_trailing_field_is_empty(tmp_path):
    """中间插一列（后面的列整体位移）要能拦住 —— 靠 Record Type 的取值校验。

    这是「容忍空尾字段」的安全网：只看尾部是不是空的，判断不出中间有没有错位。
    """
    source = tmp_path / "shifted.csv"
    cells = PADDED_ROWS[1].rstrip(",").split(",")   # 去掉多余空尾，得 7 个值
    cells.insert(2, "错位列")                        # 中间插一列 → Record Type 位置被占
    rows = _with_data_row(1, ",".join(cells) + ",,")
    source.write_text("\n".join([RAGGED_HEADER, *rows]) + "\n", encoding="utf-8")

    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, [], tmp_path / "out")
    assert exc.value.code == "invalid_record_type"
    assert "错位列" in exc.value.message             # 要把闯进来的值显示出来


def test_empty_record_type_is_shown_as_placeholder(tmp_path):
    """空值要显式写成 (空)，否则提示会以「无法识别的值：」结尾、看着像 bug。"""
    source = tmp_path / "emptyrt.csv"
    rows = _with_data_row(1, "100000001,1,,2,STYLE-A,BUYER-A,C1,,")
    source.write_text("\n".join([RAGGED_HEADER, *rows]) + "\n", encoding="utf-8")

    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, [], tmp_path / "out")
    assert exc.value.code == "invalid_record_type"
    assert "(空)" in exc.value.message


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


def test_incidental_whitespace_and_lowercase_are_legal(tmp_path):
    """源文件里 Record Type 写成小写、字段两侧带空格，都是合法输入，不能报校验失败。

    回归：回读校验曾拿**规范化后**的 DataFrame 去比逐行照搬的原文，
    这类输入会误报 output_verify_failed（内容其实没写错）。
    """
    source = tmp_path / "check0stock order x1.csv"
    source.write_text(
        RAGGED_HEADER + "\n"
        + "100000001,, H ,,,,,C1\n"
        + "100000001,1, d ,2, STYLE-A ,BUYER-A,C1\n",
        encoding="utf-8",
    )
    result = stock_precheck.run_stock_check(source, [], tmp_path / "out")

    # 输出逐行照搬原文：空格与小写都原样留着
    lines = result.checked_csv.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "100000001,, H ,,,,,C1"
    assert lines[2] == "100000001,1, d ,2, STYLE-A ,BUYER-A,C1"
    assert result.report["details"]["total"] == 1


def test_rerun_replaces_both_products(tmp_path):
    """同一批重跑：两个产物都覆盖（Windows 上 shutil.move 撞同名会直接失败）。"""
    source = write_ragged_csv(tmp_path / "check0stock order x3.csv")
    out = tmp_path / "out"

    first = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, out)
    assert first.report["replaced"] == []

    # 第二次换个断货清单（因此内容不同），产物应该整体被换掉
    second = stock_precheck.run_stock_check(source, ["STYLE-D"], out)
    assert second.checked_csv.name == first.checked_csv.name  # 同名 -> 覆盖
    assert second.report["replaced"] == [first.checked_csv.name, first.operations_xlsx.name]

    lines = second.checked_csv.read_text(encoding="utf-8").splitlines()
    assert lines == [RAGGED_HEADER, *RAGGED_ROWS[:5]]  # 这次只砍掉整单缺货的 PO 003
    assert "STYLE-D" not in second.checked_csv.read_text(encoding="utf-8")


def test_partial_publish_failure_rolls_back(tmp_path, monkeypatch):
    """第二个产物发布失败时，第一个要还原 —— 不能留「新 CSV + 旧 XLSX」。"""
    import os as os_mod

    source = write_ragged_csv(tmp_path / "check0stock order x3.csv")
    out = tmp_path / "out"
    first = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, out)
    before_csv = first.checked_csv.read_bytes()
    before_xlsx = first.operations_xlsx.read_bytes()

    real_replace = os_mod.replace

    def flaky_replace(src, dst, *args, **kwargs):
        if str(dst).endswith(".xlsx"):            # 只让 XLSX 这一步失败
            raise OSError(28, "No space left on device")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(stock_precheck.os, "replace", flaky_replace)
    with pytest.raises(OSError):
        stock_precheck.run_stock_check(source, ["STYLE-D"], out)  # 内容不同，能看出有没有换掉

    assert first.checked_csv.read_bytes() == before_csv       # CSV 被回滚
    assert first.operations_xlsx.read_bytes() == before_xlsx  # XLSX 原样
    assert sorted(p.name for p in out.iterdir()) == sorted(
        [first.checked_csv.name, first.operations_xlsx.name]
    )  # 没留下备份等残留


def test_locked_output_is_refused_without_publishing_anything(tmp_path, monkeypatch):
    """产物被占用（Excel 打开着）时整体拒绝，不能出现「新 CSV + 旧 XLSX」。

    真机上 Excel 的锁会让**备份的 copy2** 先失败（不是 open 预探），
    所以这里就照真机那样注入 copy2 的 PermissionError。
    """
    source = write_ragged_csv(tmp_path / "check0stock order x3.csv")
    out = tmp_path / "out"
    first = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, out)

    locked = first.checked_csv
    locked.write_text("上一版的内容", encoding="utf-8")     # 内容换掉，验证它没被动过
    workbook_bytes = first.operations_xlsx.read_bytes()

    real_copy2 = stock_precheck.shutil.copy2

    def flaky_copy2(src, dst, *args, **kwargs):
        if Path(src) == locked:
            raise PermissionError(13, "另一个程序已锁定文件的一部分，进程无法访问。")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(stock_precheck.shutil, "copy2", flaky_copy2)
    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, out)  # 同样的参数 -> 同名

    assert exc.value.code == "output_locked"
    assert "Excel" in exc.value.hint
    assert locked.read_text(encoding="utf-8") == "上一版的内容"       # 没被覆盖
    assert first.operations_xlsx.read_bytes() == workbook_bytes      # 也没被单独换掉


def test_permission_error_during_replace_is_readable_and_rolls_back(tmp_path, monkeypatch):
    """锁在「备份之后、发布之中」才出现：既要整体回滚，也要报可读错误而不是堆栈。"""
    import os as os_mod

    source = write_ragged_csv(tmp_path / "check0stock order x3.csv")
    out = tmp_path / "out"
    first = stock_precheck.run_stock_check(source, RAGGED_NO_STOCK, out)
    before_csv = first.checked_csv.read_bytes()

    real_replace = os_mod.replace

    def flaky_replace(src, dst, *args, **kwargs):
        if str(dst).endswith(".xlsx"):
            raise PermissionError(13, "being used by another process")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(stock_precheck.os, "replace", flaky_replace)
    with pytest.raises(stock_precheck.StockCheckError) as exc:
        stock_precheck.run_stock_check(source, ["STYLE-D"], out)

    assert exc.value.code == "output_locked"
    assert first.checked_csv.read_bytes() == before_csv  # 已经换上的 CSV 被还原


def test_bare_equals_is_not_escaped_but_formula_like_is():
    """转义条件与 openpyxl 对齐：只有「长度 > 1 且以 = 开头」才会写成公式。

    实测 openpyxl 3.1.5 只看这一个条件；`+` / `-` / `@` 开头存的是文本单元格，
    Excel 不会把 xlsx 里的文本单元格再当公式解析（那是 CSV 的注入面）。
    所以不要把 `-1`、`+A1` 这类正常值也改坏。
    """
    frame = pd.DataFrame({"A": ["=1+1", "=", "+1+1", "-1+1", "@x", "normal"]})
    assert stock_precheck._excel_safe(frame)["A"].tolist() == [
        "'=1+1", "=", "+1+1", "-1+1", "@x", "normal"
    ]


def test_formula_like_values_are_escaped_in_xlsx_only(tmp_path):
    """外部 CSV 里以 `=` 开头的值在 xlsx 里不能变成公式；checked CSV 保持原文。"""
    evil = "=cmd|'/c calc'!A1"
    source = tmp_path / "check0stock order x1.csv"
    source.write_text(
        RAGGED_HEADER + "\n"
        "100000001,,H,,,,C1\n"
        f'100000001,1,D,2,"{evil}",BUYER-A,C1\n',
        encoding="utf-8",
    )
    result = stock_precheck.run_stock_check(source, [], tmp_path / "out")

    wb = load_workbook(result.operations_xlsx, data_only=False)
    ws = wb["ASN有货明细"]
    headers = [cell.value for cell in ws[1]]
    cell = ws.cell(row=2, column=headers.index("Vendor Style") + 1)
    assert cell.data_type != "f", "以 = 开头的值被 openpyxl 写成了公式"
    assert cell.value == f"'{evil}"

    # checked CSV 仍是逐行照搬的原始字节
    assert evil in result.checked_csv.read_text(encoding="utf-8")


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
    # 截断取的是**前** limit 行（先 head 再转列表，不是整表转完再切片）
    assert limited["rows"] == [["0"], ["1"], ["2"]]
