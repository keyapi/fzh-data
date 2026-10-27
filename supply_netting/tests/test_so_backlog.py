# -*- coding: utf-8 -*-
"""EN 工厂 SO 管线用例：皮壳 1:1、仓库角色、FBA/包材排除、逾期、贴包不改可用。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from supply_netting.so_backlog import (attach_to_pack, build_so_backlog, clean_sku,
                                       finished_item, spring_festival_buffer,
                                       summarize_backlog, summarize_raw)


def so_df(rows):
    return pd.DataFrame(rows, columns=["so", "customer", "delivery_date", "item_code",
                                       "customer_item_code", "warehouse", "open_qty"])


def test_cover_prefix_is_stripped_and_marked_assumed():
    assert finished_item("PK#KS0001-PR-100-TAN") == ("KS0001-PR-100-TAN", True)
    assert finished_item("KS0001-PR-100-TAN") == ("KS0001-PR-100-TAN", False)


def test_deleted_suffix_is_cleaned_from_customer_item_code():
    assert clean_sku("删除TT0312587K0064171") == "TT0312587K0064171"
    assert clean_sku(None) is None


def test_stage_by_warehouse_and_packaging_excluded():
    frame = build_so_backlog(so_df([
        ("SO1", "DANEEY", "2026-10-30", "PK#KS1", "TT1", "半成品仓 - FZH", 10),
        ("SO1", "DANEEY", "2026-10-30", "KS1", "TT1", "成品仓 - FZH", 5),
        ("SO1", "DANEEY", "2026-10-30", "HM1510-YD1", None, "包材仓 - FZH", 3),
    ]), as_of=date(2026, 10, 27))
    stages = dict(zip(frame["factory_warehouse"], frame["stage"]))
    assert stages["半成品仓 - FZH"] == "in_production"
    assert stages["成品仓 - FZH"] == "finished_waiting_shipment"
    assert stages["包材仓 - FZH"] == "packaging_material"
    summary = summarize_backlog(frame)
    assert summary["quantity"] == 15.0            # 包材 3 件不计
    assert summary["excluded"] == {"warehouse_role_packaging": 3.0}


def test_fba_is_excluded_from_branch_pipeline():
    frame = build_so_backlog(so_df([
        ("SO2", "美国FBA仓", "2026-11-01", "KS2", "TT2", "成品仓 - FZH", 7),
    ]), as_of=date(2026, 10, 27))
    assert frame.iloc[0]["excluded_reason"] == "fba_external_scope"
    assert summarize_backlog(frame)["quantity"] == 0.0


def test_dates_are_estimated_and_overdue_flagged():
    frame = build_so_backlog(so_df([
        ("SO3", "CENTRADE", "2026-10-20", "KS3", "TT3", "成品仓 - FZH", 4),
    ]), as_of=date(2026, 10, 27))
    row = frame.iloc[0]
    assert row["scheduled_delivery"] == "2026-10-20"
    assert row["estimated_branch_date"] == "2027-01-18"      # 交付日 + 90 天业务口径
    assert row["order_to_branch_days"] == 90
    assert row["spring_festival_buffer_days"] == 0
    assert row["date_confidence"] == "estimated"
    assert row["date_basis"] == "assumed_business_90d"
    assert bool(row["overdue"]) is True
    assert summarize_backlog(frame)["overdue_quantity"] == 4.0


def test_attach_to_pack_adds_columns_without_touching_available():
    pack = pd.DataFrame([dict(canonical_sku="KS1", canonical_warehouse="美中-FZH-DANEEY",
                              opening=2.0, protect_gap=1.0)])
    backlog = build_so_backlog(so_df([
        ("SO4", "DANEEY", "2026-11-05", "PK#KS1", "TT1", "半成品仓 - FZH", 9),
    ]), as_of=date(2026, 10, 27))
    out = attach_to_pack(pack, backlog)
    assert out.iloc[0]["so_pipeline_qty"] == 9.0
    assert out.iloc[0]["opening"] == 2.0            # 可用量不被改写


def test_any_fba_customer_is_external_scope():
    frame = build_so_backlog(so_df([
        ("SO5", "德国FBA仓", "2026-10-30", "KS5", "TT5", "成品仓 - FZH", 3),
    ]), as_of=date(2026, 10, 27))
    assert frame.iloc[0]["excluded_reason"] == "fba_external_scope"


def test_outsourced_finished_warehouse_is_counted_as_finished():
    frame = build_so_backlog(so_df([
        ("SO6", "DANEEY", "2026-10-30", "KS6", "TT6", "北京委外成品仓 - FZH", 6),
    ]), as_of=date(2026, 10, 27))
    row = frame.iloc[0]
    assert row["role"] == "outsourced_finished"
    assert row["stage"] == "finished_waiting_shipment"
    assert summarize_backlog(frame)["quantity"] == 6.0


def test_raw_summary_keeps_all_open_rows_for_reconciliation():
    frame = build_so_backlog(so_df([
        ("SO7", "DANEEY", "2026-10-30", "KS7", "TT7", "成品仓 - FZH", 10),
        ("SO7", "DANEEY", "2026-10-30", "HM5", None, "包材仓 - FZH", 4),
        ("SO7", "美国FBA仓", "2026-10-30", "KS7", "TT7", "成品仓 - FZH", 6),
    ]), as_of=date(2026, 10, 27))
    raw = summarize_raw(frame)
    assert raw["quantity"] == 20.0                 # 全部开放行
    assert summarize_backlog(frame)["quantity"] == 10.0   # 仅计入管线


def test_spring_festival_adds_two_month_buffer_for_jan_feb_delivery():
    assert spring_festival_buffer(date(2026, 2, 10)) == 60
    assert spring_festival_buffer(date(2026, 1, 3)) == 60
    assert spring_festival_buffer(date(2026, 9, 1)) == 0
    assert spring_festival_buffer(None) == 0

    frame = build_so_backlog(so_df([
        ("SO8", "DANEEY", "2026-02-10", "KS8", "TT8", "成品仓 - FZH", 5),
    ]), as_of=date(2026, 1, 5))
    row = frame.iloc[0]
    assert row["spring_festival_buffer_days"] == 60
    assert row["estimated_branch_date"] == "2026-07-10"      # 2026-02-10 + 90 + 60
    summary = summarize_backlog(frame)
    assert summary["spring_festival_applied_quantity"] == 5.0


def test_tongtool_sku_falls_back_to_item_code_when_customer_code_missing():
    frame = build_so_backlog(so_df([
        ("SO9", "DANEEY", "2026-10-30", "PK#KS9", None, "半成品仓 - FZH", 2),
        ("SO9", "DANEEY", "2026-10-30", "KS9", "删除TT9", "半成品仓 - FZH", 3),
    ]), as_of=date(2026, 10, 27))
    first, second = frame.iloc[0], frame.iloc[1]
    assert first["tongtool_sku"] == "KS9" and first["tongtool_sku_basis"] == "item_code_fallback"
    assert second["tongtool_sku"] == "TT9" and second["tongtool_sku_basis"] == "customer_item_code"
