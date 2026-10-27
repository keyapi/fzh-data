# -*- coding: utf-8 -*-
"""业务审核工作簿用例：不重算、B3 合计、精度不丢、标签口径、待核不按 0、R6/R7 列。"""

from __future__ import annotations

import openpyxl
import pandas as pd
import pytest

from supply_netting.business_review import LABEL_GAP, LABEL_HIGHER, build_workbook

COLUMNS = ["canonical_sku", "canonical_warehouse", "canonical_uom", "destination",
           "destination_reason", "netting_as_of", "netting_horizon_end", "forecast_window",
           "data_cutoff", "opening", "horizon_demand", "qty_current", "qty_higher",
           "action", "action_qty", "residual_gap", "action_basis", "action_source_so",
           "action_source_wo", "so_stage_produced_pending_dn", "so_stage_in_production",
           "so_stage_in_transit", "so_stage_not_planned",
           "so_stage_unknown_missing_start", "so_stage_unknown_other",
           "so_stage_fba_produced_pending_dn", "so_stage_fba_in_production",
           "so_stage_fba_in_transit", "so_stage_fba_not_planned", "to_verify",
           "timely_coverage_flag", "transit_dedup_status", "action_applicability",
           "missing_evidence", "action_confidence", "conditional_supply_qty",
           "conditional_supply", "so_est_branch_date", "first_gap_bucket_end"]


def frame():
    base = dict(netting_as_of="2026-10-26T05:17:34+08:00",
                netting_horizon_end="2026-11-30T05:17:34+08:00",
                forecast_window="2026-10-29..2026-12-28", data_cutoff="2026-10-26",
                to_verify="条件供应 110 无 ETA，未计入", timely_coverage_flag="",
                transit_dedup_status="", so_stage_produced_pending_dn=0.0,
                so_stage_in_production=0.0, so_stage_in_transit=0.0,
                so_stage_not_planned=0.0, so_stage_unknown_missing_start=0.0,
                so_stage_unknown_other=0.0, so_stage_fba_produced_pending_dn=0.0,
                so_stage_fba_in_production=0.0, so_stage_fba_in_transit=0.0,
                so_stage_fba_not_planned=0.0, action_source_so="", action_source_wo=None,
                action_basis="", action_applicability="evidence", action_confidence="measured",
                conditional_supply_qty=0.0, conditional_supply=0.0,
                so_est_branch_date=None, first_gap_bucket_end="2026-11-02T05:17:34+08:00")
    rows = [
        dict(base, canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
             destination="建议补货", destination_reason="模型化缺口 > 0", opening=1.0,
             horizon_demand=44.028819, qty_current=44.0, qty_higher=85.0, action="催发运",
             action_qty=30.0, residual_gap=14.0, so_stage_produced_pending_dn=140.0,
             action_source_so="SO-1", conditional_supply_qty=55.0),
        dict(base, canonical_sku="S2", canonical_warehouse="W", canonical_uom="个",
             destination="无需补货", destination_reason="期初覆盖已知需求", opening=9.0,
             horizon_demand=0.000538, qty_current=0.0, qty_higher=0.0,
             action="不需补（当前窗口）", action_qty=0.0, residual_gap=0.0),
        dict(base, canonical_sku="S3", canonical_warehouse="W", canonical_uom="个",
             destination="无需补货", destination_reason="期初覆盖已知需求", opening=3.0,
             horizon_demand=1625.0, qty_current=0.0, qty_higher=0.0,
             action="不需补（当前窗口）", action_qty=0.0, residual_gap=0.0),
        dict(base, canonical_sku="S4", canonical_warehouse="W", canonical_uom="个",
             destination="待核", destination_reason="预测键未过资格", opening=None,
             horizon_demand=None, qty_current=None, qty_higher=None, action=None,
             action_qty=None, residual_gap=None, action_applicability="no_supply_evidence",
             missing_evidence="not_qualified"),
        dict(base, canonical_sku="S5", canonical_warehouse="W", canonical_uom="个",
             destination="不可算", destination_reason="no_snapshot_basis", opening=None,
             horizon_demand=None, qty_current=None, qty_higher=None, action="不可算",
             action_qty=None, residual_gap=None),
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


@pytest.fixture()
def built(tmp_path):
    path = tmp_path / "actions.parquet"
    frame().to_parquet(path, index=False)
    out = tmp_path / "review.xlsx"
    manifest = build_workbook(path, out)
    return openpyxl.load_workbook(out), manifest


def test_sheets_and_chinese_headers(built):
    book, manifest = built
    assert book.sheetnames == ["1_说明与边界", "2_建议补货91", "3_无需补货452",
                               "4_待核3469", "5_不可算2", "6_版本与hash"]
    header = [c.value for c in book["2_建议补货91"][1]]
    assert header[:4] == ["SKU", "仓库", "单位", "期初"]
    assert LABEL_GAP in header and LABEL_HIGHER in header
    assert manifest["counts"]["suggested"] == 1


def test_no_need_demand_total_uses_horizon_demand_not_zero(built):
    book, manifest = built
    sheet = book["3_无需补货452"]
    summary = {sheet.cell(r, 1).value: sheet.cell(r, 2).value for r in range(2, 8)}
    assert summary["视界末需求合计"] == pytest.approx(1625.000538)   # 不是缺口 0
    assert summary["当前缺口合计"] == 0
    assert manifest["quantities"]["no_need_horizon_demand_total"] == pytest.approx(1625.000538)


def test_small_positive_values_keep_precision_and_four_decimal_format(built):
    book, _ = built
    sheet = book["3_无需补货452"]
    cells = [sheet.cell(r, 5) for r in range(10, 10 + 2)]     # 两条数据行
    values = [c.value for c in cells]
    assert 0.000538 in values                      # 源精度保留，未被 round
    tiny = next(c for c in cells if c.value == 0.000538)
    assert tiny.number_format == "0.0000"          # 显示 4 位，不会显示成 0
    big = next(c for c in cells if c.value == 1625.0)
    assert big.number_format in ("#,##0", "0.0000")


def test_labels_state_gap_and_flat95_not_promise(built):
    book, manifest = built
    sheet = book["1_说明与边界"]
    text = "\n".join(str(sheet.cell(r, 2).value) for r in range(2, sheet.max_row + 1))
    assert "视界末缺口逐键向上取整合计（不含服务缓冲）" in text
    assert "flat95" in text and "不是 95% 承诺" in text
    assert manifest["labels"][LABEL_HIGHER].startswith("flat95")


def test_suggested_sheet_has_evidence_columns(built):
    book, _ = built
    header = [c.value for c in book["2_建议补货91"][1]]
    for column in ("期初", "未来需求", "条件供应量", "条件供应资格", "最近日期",
                   "动作置信度", "源记录定位"):
        assert column in header
    row = [c.value for c in book["2_建议补货91"][2]]
    record = dict(zip(header, row))
    assert record["未来需求"] == 44.028819          # 不四舍五入
    assert record["条件供应量"] == 55.0
    assert record["动作置信度"] == "measured"
    assert record["源记录定位"] == "SO-1"           # 空 WO 不写成 nan


def test_pending_rows_are_blank_not_zero(built):
    book, _ = built
    sheet = book["4_待核3469"]
    header = [c.value for c in sheet[1]]
    summary = dict(zip(header, [c.value for c in sheet[2]]))
    assert summary["影响键数"] == 1
    assert summary["涉及库存数"] is None
    assert "责任人（待填）" in [c.value for c in sheet[4]]
    assert sheet.cell(5, 8).value is None


def test_version_sheet_has_commit_and_acceptance(built):
    book, manifest = built
    sheet = book["6_版本与hash"]
    values = {sheet.cell(r, 1).value: sheet.cell(r, 2).value for r in range(2, sheet.max_row + 1)}
    assert "生成 commit" in values and values["生成 commit"]
    assert values["验收状态"] == "返修后待 Codex 复核"
    assert "Codex" in values["审核记录"]
    assert manifest["review_history"]
