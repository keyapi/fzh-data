# -*- coding: utf-8 -*-
"""多窗口工作簿 v3 用例：窗口过滤、差值、春节块、sheet 结构与精度。"""

from __future__ import annotations

import openpyxl
import pandas as pd
import pytest

from supply_netting.business_review_multi import build_workbook_v3

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def windows():
    rows = []
    for days, keys_count, qty in ((30, 1, 10.0), (60, 1, 20.0), (90, 2, 30.0),
                                  (150, 3, 45.0), (180, 3, 60.0)):
        rows.append(dict(window_days=days, uom="个", bucket_id=f"w{days}", bucket_end="2027-01-25T00:00:00+08:00",
                         actual_days=days + 1, buckets_count=days // 7, forecast_demand=100.0 * days,
                         cum_unserved=5.0 * days, gap_keys=keys_count, suggestion_keys=keys_count,
                         qty_current=qty, qty_higher=qty * 1.5, usage="review_candidate",
                         note="累计窗口"))
    return pd.DataFrame(rows)


def keys():
    rows = []
    for days in (30, 60, 90, 150, 180):
        for index, sku in enumerate(("S1", "S2", "S3")):
            applies = days == 180 or (days == 90 and index < 2) or (days == 150)
            if days == 30 and index > 0:
                applies = False
            if days == 60 and index > 0:
                applies = False
            rows.append(dict(window_days=days, bucket_end="2027-01-25T00:00:00+08:00",
                             canonical_sku=sku, canonical_warehouse="W", canonical_uom="个",
                             forecast_demand=10.0 + index + days,
                             cum_unserved=2.0 + index,
                             qty_current=(3.5 + index) if applies else 0.0,
                             qty_higher=(5.0 + index) if applies else 0.0,
                             gap=applies))
    return pd.DataFrame(rows)


def actions():
    base = dict(canonical_warehouse="W", canonical_uom="个", data_cutoff="2026-10-26",
                netting_as_of="2026-10-26T05:17:34+08:00", destination_reason="模型化缺口 > 0",
                action_confidence="measured", action_qty=2.0, residual_gap=1.0,
                action_source_so="SO-1", action_source_wo=None, action_gap=3.5,
                baseline_group="original")
    rows = [dict(base, canonical_sku="S1", destination="建议补货", action="催发运"),
            dict(base, canonical_sku="S2", destination="建议补货", action="补单"),
            dict(base, canonical_sku="S3", destination="建议补货", action="核实到仓 ETA"),
            dict(base, canonical_sku="S4", destination="待核", action=None,
                 action_confidence=None, action_basis="待核"),
            dict(base, canonical_sku="S5", destination="无需补货", action="不需补（当前窗口）"),
            dict(base, canonical_sku="S6", destination="不可算", action="",
                 action_basis="净额不可算")]
    return pd.DataFrame(rows)


def so_audit():
    return pd.DataFrame([
        dict(SO="SO-1", 客户="DANEEY", 分公司仓="美中-FZH-DANEEY", 开放量=100.0, 在途=10.0,
             完工待发运=20.0, 在产=5.0, 未排产=0.0, unknown=60.0, 累计超产=0.0, 逾期天数=30,
             预计到仓="2027-04-05", 日期置信度="estimated", 异常="已完工未发运",
             处置建议="可作条件供给"),
        dict(SO="SO-2", 客户="CENTRADE", 分公司仓="美东-CENTRADE", 开放量=50.0, 在途=0.0,
             完工待发运=0.0, 在产=0.0, 未排产=50.0, unknown=0.0, 累计超产=0.0, 逾期天数=10,
             预计到仓=None, 日期置信度="unknown", 异常="有未排产",
             处置建议="需催（在产/未排产）"),
        dict(SO="SO-3", 客户="DANEEY", 分公司仓="美中-FZH-DANEEY", 开放量=30.0, 在途=0.0,
             完工待发运=0.0, 在产=0.0, 未排产=0.0, unknown=0.0, 累计超产=0.0, 逾期天数=5,
             预计到仓=None, 日期置信度="unknown", 异常="无W1阶段证据",
             处置建议="无法判断（无阶段证据）"),
    ])


def so_rows():
    return pd.DataFrame([
        dict(so="SO-1", spring_festival_applicability="applicable", quantity=40.0,
             excluded_reason=None),
        dict(so="SO-2", spring_festival_applicability="applicable", quantity=20.0,
             excluded_reason=None),
        dict(so="SO-4", spring_festival_applicability="applicable", quantity=99.0,
             excluded_reason="fba_external_scope"),
        dict(so="SO-3", spring_festival_applicability="not_applicable", quantity=30.0,
             excluded_reason=None),
    ])


@pytest.fixture()
def built(tmp_path):
    paths = {}
    for name, frame, writer in (("windows", windows(), "to_csv"),
                                ("keys", keys(), "to_csv"),
                                ("audit", so_audit(), "to_csv"),
                                ("so_rows", so_rows(), "to_csv")):
        path = tmp_path / f"{name}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = path
    actions_path = tmp_path / "actions.parquet"
    actions().to_parquet(actions_path, index=False)
    out = tmp_path / "review-v3.xlsx"
    manifest = build_workbook_v3(windows_csv=paths["windows"], keys_csv=paths["keys"],
                                 actions_parquet=actions_path, so_audit_csv=paths["audit"],
                                 so_rows_csv=paths["so_rows"], out_path=out)
    return openpyxl.load_workbook(out), manifest


def test_workbook_has_eight_sheets_and_frozen_headers(built):
    book, manifest = built
    assert book.sheetnames == ["1_说明与边界", "2_90天主表", "3_150天春节压力", "4_180天情景",
                               "5_30-60天参考", "6_180天其他去向", "7_SO审计摘要", "8_版本与证据"]
    for name in book.sheetnames:
        assert book[name].freeze_panes == "A2"
    assert manifest["counts"]["main90_keys"] == 2
    assert manifest["counts"]["scenario180_keys"] == 3


def test_window_tables_only_include_gap_keys(built):
    book, _ = built
    sheet90 = book["2_90天主表"]
    skus90 = [sheet90.cell(r, 1).value for r in range(2, sheet90.max_row + 1)]
    assert set(skus90) == {"S1", "S2"}                  # 90 天只有两键有建议量
    sheet180 = book["4_180天情景"]
    assert sheet180.max_row - 1 == 3


def test_festival_block_uses_counted_rows_only(built):
    book, manifest = built
    sheet = book["3_150天春节压力"]
    block = {}
    for row in range(2, sheet.max_row + 1):
        key = sheet.cell(row, 1).value
        if key in ("SKU", None):
            break
        block[key] = sheet.cell(row, 2).value
    assert block["计入管线穿越"] == "2 单 / 60 件"       # FBA 的 SO-4 不计
    assert block["全部开放行穿越"] == "3 单 / 159 件"
    # v5：两种日期定义并列（不再有「简报/未溯源」的否认性文案）
    assert "日期定义 A" in "".join(block.keys()) and "日期定义 B" in "".join(block.keys())
    assert not any("简报" in str(k) for k in block)


def test_diff_column_is_150_minus_90(built):
    book, _ = built
    sheet = book["3_150天春节压力"]
    header_row = next(r for r in range(1, sheet.max_row + 1)
                      if sheet.cell(r, 1).value == "SKU")
    header = [c.value for c in sheet[header_row]]
    row = dict(zip(header, [c.value for c in sheet[header_row + 1]]))
    assert row["建议量差（150−90）"] == pytest.approx(row["150天建议量"] - row["90天建议量"])


def test_pending_and_not_computable_stay_empty_and_counts_match(built):
    _, manifest = built
    assert manifest["counts"]["pending"] == 1
    assert manifest["counts"]["not_computable"] == 1
    assert manifest["counts"]["action_distribution"] == {"催发运": 1, "补单": 1, "核实到仓 ETA": 1}


def test_quantities_keep_source_precision(built):
    book, _ = built
    sheet = book["2_90天主表"]
    rows = {sheet.cell(r, 1).value: sheet.cell(r, 6).value
            for r in range(2, sheet.max_row + 1)}
    assert rows["S1"] == pytest.approx(3.5)             # 源精度保留，不四舍五入
    fmt = sheet.cell(2, 6).number_format
    assert fmt in ("0.000000", "#,##0")                 # 不四舍五入成 0 或 4
