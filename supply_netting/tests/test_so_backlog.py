# -*- coding: utf-8 -*-
"""EN 工厂 SO 管线用例：皮壳 1:1、仓库角色、FBA/包材排除、逾期、贴包不改可用。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from supply_netting.so_backlog import (attach_to_pack, build_so_backlog, clean_sku,
                                       finished_item, summarize_backlog)


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
    ]), as_of=date(2026, 10, 27), transit_days=45)
    row = frame.iloc[0]
    assert row["scheduled_delivery"] == "2026-10-20"
    assert row["estimated_branch_date"] == "2026-12-04"      # 交付日 + 45 天假设
    assert row["date_confidence"] == "estimated"
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
