# -*- coding: utf-8 -*-
"""未履约 SO 审计用例：预计到仓口径、阶段聚合、异常与处置分类。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from supply_netting.so_audit import (SPRING_FESTIVAL_2027, audit_all, audit_so,
                                     crosses_spring_festival, estimate_arrival, summarize)


def so_lines(rows):
    return pd.DataFrame(rows, columns=["so", "customer", "branch_warehouse", "factory_warehouse",
                                       "quantity", "scheduled_delivery", "excluded_reason"])


def payload(stages, milestones=(), lines=(), partial="True"):
    return dict(
        stage_balances=[
            dict(so="SO-1", item_code="KS1", stage=stage, qty=qty, scope=scope,
                 cumulative_excess_qty=excess, source_record=record, exclusion_reason=reason)
            for stage, qty, scope, excess, record, reason in stages
        ],
        milestones=list(milestones),
        lines=[dict(qty=q, delivered_qty=d) for q, d in lines],
        manifest=dict(partial=partial, rule_version="2026-10-27.7", coverage=dict(shipments=1)),
    )


def test_spring_festival_crossing_and_buffer():
    # 生产/运输路径穿越 2027-02-06 窗口 → 加 60 天
    assert crosses_spring_festival(date(2026, 12, 1)) is True
    assert crosses_spring_festival(date(2026, 6, 1)) is False
    arrival, buffer_days, festival = estimate_arrival(date(2026, 12, 1))
    assert festival is True and buffer_days == 60
    assert arrival == date(2026, 12, 1) + pd.Timedelta(days=150).to_pytimedelta()
    # 未穿越 → 只加 90 天
    arrival2, buffer2, festival2 = estimate_arrival(date(2026, 6, 1))
    assert festival2 is False and buffer2 == 0
    assert (arrival2 - date(2026, 6, 1)).days == 90


def test_audit_so_aggregates_stages_and_flags_anomalies():
    lines = so_lines([("SO-1", "DANEEY", "美中-FZH-DANEEY", "半成品仓 - FZH", 100.0,
                       "2026-09-01", None)])
    p = payload([
        ("produced_pending_dn", 30.0, "in_house", 0.0, "WO-1", ""),
        ("in_production", 40.0, "in_house", 0.0, "WO-2", ""),
        ("shipped_in_transit", 20.0, "in_house", 0.0, "DN-1", ""),
        ("over_produced", 5.0, "in_house", 5.0, "WO-3", ""),
        ("unknown", 10.0, "external_fba", 0.0, None, ""),
    ], milestones=[dict(node="production_end", qty=30.0, actual_at="2026-10-01")],
        lines=[(100.0, 0.0)])
    row = audit_so("SO-1", lines, p)
    assert row["完工待发运"] == 30.0 and row["在产"] == 40.0 and row["在途"] == 20.0
    assert row["累计超产"] == 5.0
    assert row["FBA量"] == 10.0
    assert "已完工未发运" in row["异常"] and "超产" in row["异常"] and "FBA/自营混" in row["异常"]
    assert row["WO已完工"] == 1
    assert row["逾期天数"] == 56          # 2026-09-01 → 2026-10-27
    assert row["处置建议"] == "可作条件供给"
    assert row["日期置信度"] == "estimated"


def test_unknown_only_so_gets_unknown_date_and_cannot_judge():
    lines = so_lines([("SO-2", "CENTRADE", "美东-CENTRADE", "成品仓 - FZH", 50.0,
                       "2026-10-01", None)])
    p = payload([("not_planned", 50.0, "in_house", 0.0, None, "")],
                milestones=[], lines=[(50.0, 0.0)])
    row = audit_so("SO-2", lines, p)
    assert row["预计到仓"] == ""
    assert row["日期置信度"] == "unknown"
    assert row["处置建议"] == "需催（在产/未排产）"


def test_no_stage_rows_is_cannot_judge():
    lines = so_lines([("SO-3", "DANEEY", "美中-FZH-DANEEY", "成品仓 - FZH", 20.0,
                       "2026-09-01", None)])
    row = audit_so("SO-3", lines, payload([]))
    assert row["处置建议"] == "无法判断（无阶段证据）"
    assert "无W1阶段证据" in row["异常"]


def test_old_anchor_is_floored_at_audit_date():
    """DN 早已发出但一直没更新：不能算出过去的“预计到仓”。"""
    lines = so_lines([("SO-4", "DANEEY", "美中-FZH-DANEEY", "半成品仓 - FZH", 10.0,
                       "2026-08-01", None)])
    p = payload([("shipped_in_transit", 10.0, "in_house", 0.0, "DN-9", "")],
                milestones=[dict(node="dispatch", qty=10.0, actual_at="2026-05-21")],
                lines=[(10.0, 0.0)])
    row = audit_so("SO-4", lines, p)
    assert row["锚点日"] == "2026-05-21"
    assert row["起算日"] == "2026-10-27"
    assert row["预计到仓"] > "2026-10-27"
    assert any("阶段证据陈旧" in a for a in row["异常"].split("；"))


def test_summary_categorises_orders_and_quantities():
    lines = so_lines([
        ("SO-5", "DANEEY", "美中-FZH-DANEEY", "半成品仓 - FZH", 10.0, "2026-09-01", None),
        ("SO-6", "DANEEY", "美中-FZH-DANEEY", "半成品仓 - FZH", 5.0, "2026-09-01", None),
        ("SO-7", "DANEEY", "美中-FZH-DANEEY", "半成品仓 - FZH", 2.0, "2026-09-01", None),
    ])
    w1 = {
        "SO-5": payload([("shipped_in_transit", 10.0, "in_house", 0.0, "DN-1", "")],
                        lines=[(10.0, 0.0)]),
        "SO-6": payload([("in_production", 5.0, "in_house", 0.0, "WO-1", "")],
                        lines=[(5.0, 0.0)]),
        "SO-7": payload([], lines=[(2.0, 0.0)]),
    }
    audit = audit_all(lines, w1)
    summary = summarize(audit)
    assert summary["orders"] == 3
    assert summary["conditional_supply"]["orders"] == 1
    assert summary["need_push"]["orders"] == 1
    assert summary["cannot_judge"]["orders"] == 1
    assert summary["open_qty"] == 17.0
