# -*- coding: utf-8 -*-
"""补证队列用例：只取待核、证据映射、影响未知不按 0、汇总计数。"""

from __future__ import annotations

import pandas as pd

from supply_netting.evidence_queue import (GROUP_EVIDENCE, GROUP_ROLES, build_queue)

COLUMNS = KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom", "destination",
                 "destination_reason", "missing_evidence", "value_status",
                 "demand_evidence_status", "gap_evidence_status", "to_verify",
                 "horizon_demand", "qty_current", "protect_gap"]


def frame():
    rows = [
        dict(canonical_sku="A", canonical_warehouse="美中-FZH-DANEEY", canonical_uom="个",
             destination="待核", destination_reason="预测键未过资格且无库存基准",
             missing_evidence="not_qualified_no_stock_basis", value_status="not_covered",
             demand_evidence_status="not_covered", gap_evidence_status="not_covered",
             to_verify="预测未过资格 1 行", horizon_demand=None, qty_current=None,
             protect_gap=None),
        dict(canonical_sku="B", canonical_warehouse="波兰-FZHPoland-covers", canonical_uom="套",
             destination="待核", destination_reason="无预测覆盖（仅有库存，缺需求证据）",
             missing_evidence="stock_only_no_demand", value_status="not_covered",
             demand_evidence_status="not_covered", gap_evidence_status="not_covered",
             to_verify="缺预测需求证据；不能当作零需求", horizon_demand=None,
             qty_current=None, protect_gap=None),
        dict(canonical_sku="C", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
             destination="建议补货", destination_reason="模型化缺口 > 0",
             missing_evidence="", value_status="known", demand_evidence_status="known",
             gap_evidence_status="known", to_verify="", horizon_demand=10.0,
             qty_current=5.0, protect_gap=5.0),
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


def build(tmp_path):
    path = tmp_path / "pack.parquet"
    frame().to_parquet(path, index=False)
    return build_queue(path)


def test_only_pending_rows_enter_the_queue(tmp_path):
    queue, summary = build(tmp_path)
    assert len(queue) == 2                     # 建议补货的行不进补证队列
    assert "C" not in set(queue["SKU"])
    assert summary["pending_keys"] == 2


def test_evidence_and_roles_follow_group(tmp_path):
    queue, _ = build(tmp_path)
    by_sku = queue.set_index("SKU")
    assert by_sku.loc["A", "缺什么证据"] == "；".join(
        GROUP_EVIDENCE["not_qualified_no_stock_basis"])
    assert by_sku.loc["A", "主责角色"] == GROUP_ROLES["not_qualified_no_stock_basis"][0]
    assert by_sku.loc["A", "协作角色"] == GROUP_ROLES["not_qualified_no_stock_basis"][1]
    assert by_sku.loc["B", "缺什么证据"] == "；".join(GROUP_EVIDENCE["stock_only_no_demand"])
    assert "ETA" in by_sku.loc["B", "不适用证据"]


def test_impact_is_unknown_and_never_zero(tmp_path):
    queue, summary = build(tmp_path)
    assert set(queue["影响"]) == {"未知（不按 0）"}
    # 队列里不出现任何数量列
    for column in ("horizon_demand", "qty_current", "protect_gap", "建议量"):
        assert column not in queue.columns
    assert summary["impact"] == "未知（不按 0）"
    assert set(queue["状态"]) == {"待补证"}
    # 填写栏必须是空（空串），不能预填任何值
    assert set(queue["责任人（待填）"].fillna("")) == {""}


def test_summary_counts_by_group_role_and_uom(tmp_path):
    _, summary = build(tmp_path)
    assert summary["by_group"] == {"not_qualified_no_stock_basis": 1,
                                   "stock_only_no_demand": 1}
    assert summary["by_uom"] == {"个": 1, "套": 1}
    assert summary["by_role_primary"]["运营"] == 2
    assert summary["by_role_supporting"]["仓库"] == 1
