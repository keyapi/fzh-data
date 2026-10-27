# -*- coding: utf-8 -*-
"""业务审核工作簿用例：不重算、待核不按 0、六个 sheet 与中文表头。"""

from __future__ import annotations

import openpyxl
import pandas as pd

from supply_netting.business_review import build_workbook

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
           "missing_evidence"]


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
                so_stage_fba_not_planned=0.0, action_source_so="", action_source_wo="",
                action_basis="", action_applicability="evidence")
    rows = [
        dict(base, canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
             destination="建议补货", destination_reason="模型化缺口 > 0", opening=1.0,
             horizon_demand=44.0, qty_current=44.0, qty_higher=85.0, action="催发运",
             action_qty=30.0, residual_gap=14.0, so_stage_produced_pending_dn=140.0,
             action_source_so="SO-1"),
        dict(base, canonical_sku="S2", canonical_warehouse="W", canonical_uom="个",
             destination="无需补货", destination_reason="期初覆盖已知需求", opening=9.0,
             horizon_demand=0.0, qty_current=0.0, qty_higher=0.0, action="不需补（当前窗口）",
             action_qty=0.0, residual_gap=0.0),
        dict(base, canonical_sku="S3", canonical_warehouse="W", canonical_uom="个",
             destination="待核", destination_reason="预测键未过资格", opening=None,
             horizon_demand=None, qty_current=None, qty_higher=None, action=None,
             action_qty=None, residual_gap=None, action_applicability="no_supply_evidence",
             missing_evidence="not_qualified"),
        dict(base, canonical_sku="S4", canonical_warehouse="W", canonical_uom="个",
             destination="不可算", destination_reason="no_snapshot_basis", opening=None,
             horizon_demand=None, qty_current=None, qty_higher=None, action="不可算",
             action_qty=None, residual_gap=None),
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


def build(tmp_path):
    path = tmp_path / "actions.parquet"
    frame().to_parquet(path, index=False)
    out = tmp_path / "review.xlsx"
    manifest = build_workbook(path, out)
    return out, manifest


def test_workbook_has_six_sheets_with_chinese_headers(tmp_path):
    out, manifest = build(tmp_path)
    book = openpyxl.load_workbook(out)
    assert book.sheetnames == ["1_说明与边界", "2_建议补货91", "3_无需补货452",
                               "4_待核3469", "5_不可算2", "6_版本与hash"]
    assert book["2_建议补货91"].cell(1, 1).value == "SKU"
    assert book["2_建议补货91"].cell(1, 4).value == "当前缺口"
    assert manifest["counts"] == dict(suggested=1, no_need=1, pending=1, not_computable=1,
                                      pending_by_group={"not_qualified": 1})


def test_numbers_come_straight_from_input(tmp_path):
    out, manifest = build(tmp_path)
    sheet = openpyxl.load_workbook(out)["2_建议补货91"]
    assert sheet.cell(2, 4).value == 44.0        # 当前缺口 = qty_current，未重算
    assert sheet.cell(2, 5).value == 85.0        # 高服务参考 = qty_higher
    assert sheet.cell(2, 7).value == 30.0        # 动作数量原值
    assert sheet.cell(2, 8).value == 14.0        # 剩余需补原值
    assert manifest["quantities"]["suggested_qty_current"] == 44.0
    assert manifest["quantities"]["suggested_qty_higher"] == 85.0


def test_pending_rows_are_blank_not_zero(tmp_path):
    out, manifest = build(tmp_path)
    sheet = openpyxl.load_workbook(out)["4_待核3469"]
    header = [c.value for c in sheet[1]]
    row = [c.value for c in sheet[2]]
    summary = dict(zip(header, row))
    assert summary["影响键数"] == 1
    assert summary["涉及库存数"] is None          # 全空 → 留空，不写 0
    assert "待核为空" in header[7]
    detail_header = [c.value for c in sheet[4]]
    assert "责任人（待填）" in detail_header
    assert sheet.cell(5, 8).value is None          # 填写栏留空
    assert manifest["blind_window_days"] == 2.779
