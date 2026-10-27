# -*- coding: utf-8 -*-
"""2026-10-27 口径新增输入层用例：子仓角色、退货仓、占位 SKU、通途采购单、F2 逐桶口径。

全部合成数据，不读生产/业务 fixture。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from supply_netting.engine import build_buckets, net_target
from supply_netting.supply import (build_supply_facts, load_po_tongtool, _placeholder_matcher)
from self_fulfilled_demand.canonical import load_warehouse_config, resolve_warehouse_role

UOM = "个"
AS_OF = datetime(2026, 10, 27, tzinfo=timezone.utc)
BUCKETS = build_buckets(AS_OF, protect_days=3, weeks=2)
CFG = load_warehouse_config()


def stock_frame(rows):
    return pd.DataFrame(
        [
            dict(snapshot_date=date(2026, 10, 23),
                 snapshot_at=pd.Timestamp("2026-10-23 10:47:42"),
                 warehouse_id="wh", warehouse_name=wh, sku=sku,
                 available=available, intransit=intransit,
                 waiting_shipment=0.0, defects=0.0, avg_cost=1.0,
                 source="fixture", run_id="run-test", schema_version=1)
            for sku, wh, available, intransit in rows
        ]
    )


SKU_MAP = pd.DataFrame(
    [dict(tongtool_sku="TT-KS1", item_codes=("KS1",), mapping_status="mapped"),
     dict(tongtool_sku="TT-PO1", item_codes=("KS1",), mapping_status="mapped")]
)
UOM_CACHE = pd.DataFrame([dict(item_code="KS1", stock_uom=UOM)])


def build(rows, po_tongtool=None):
    stock = stock_frame(rows)
    tt = pd.DataFrame(po_tongtool) if po_tongtool is not None else None
    return build_supply_facts(stock, pd.DataFrame(columns=["document_key", "sku", "qty", "warehouse"]),
                              sku_map=SKU_MAP, uom_cache=UOM_CACHE, warehouse_cfg=CFG,
                              po_tongtool_df=tt)


def reasons(evidence):
    return [row.get("disposition_reason") for row in evidence]


# ── 1. 子仓角色映射 ──────────────────────────────────────────────────────

def test_cover_subwarehouse_maps_to_parent_with_conversion_assumed():
    profile = resolve_warehouse_role("FZH-DANEEY-皮壳仓库", CFG)
    assert profile["canonical_warehouse"] == "美中-FZH-DANEEY"
    assert profile["warehouse_role"] == "cover"
    assert profile["conversion_assumed"] is True
    assert profile["counts_as_available"] is True


def test_cover_subwarehouse_stock_counts_at_parent_warehouse():
    rows, balances, evidence = build([("TT-KS1", "FZH-DANEEY-皮壳仓库", 12, 0)])
    assert len(rows) == 1
    assert rows[0].warehouse == "美中-FZH-DANEEY"       # 1:1 可发成品口径：归主仓
    assert rows[0].qty == Decimal("12")
    assert "warehouse_unmapped" not in reasons(evidence)


# ── 2. 退货仓 ────────────────────────────────────────────────────────────

def test_return_warehouse_is_excluded_from_available_supply():
    rows, balances, evidence = build([("TT-KS1", "FZH-DANEEY-退货产品仓", 7, 0)])
    assert rows == []
    assert "return_warehouse_excluded" in reasons(evidence)
    fact = next(r for r in evidence if r.get("disposition_reason") == "return_warehouse_excluded")
    assert fact["warehouse_role"] == "return"
    assert fact["qty"] == Decimal("7")


def test_return_warehouse_intransit_is_excluded_too():
    rows, balances, evidence = build([("TT-KS1", "FZH-DANEEY-退货产品仓", 0, 5)])
    assert balances == []
    assert "return_warehouse_excluded" in reasons(evidence)


# ── 3. 占位 SKU ──────────────────────────────────────────────────────────

def test_placeholder_sku_is_excluded_and_evidenced():
    rows, balances, evidence = build([("Buttonkit-pl", "美中-FZH-DANEEY", 9999866, 0)])
    assert rows == []
    fact = next(r for r in evidence if r.get("disposition_reason") == "placeholder_excluded")
    assert fact["qty"] == Decimal("9999866")


def test_placeholder_detection_by_pattern_and_threshold():
    match = _placeholder_matcher(CFG)
    assert match("Cotton-US", 1) == "explicit"
    assert match("Cotton-XX", 1) is not None          # 正则
    assert match("ANY-SKU", 100000) is not None        # available 异常大
    assert match("KS1", 10) is None


def test_normal_intermediate_density_is_not_placeholder():
    rows, _, evidence = build([("TT-KS1", "美中-FZH-DANEEY", 20, 0)])
    assert len(rows) == 1 and "placeholder_excluded" not in reasons(evidence)


# ── 4. 通途采购单 ────────────────────────────────────────────────────────

def _po_file(tmp_path: Path, records) -> Path:
    path = tmp_path / "po.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    return path


def test_tongtool_po_keeps_open_status_and_computes_open_qty(tmp_path):
    path = _po_file(tmp_path, [
        dict(PONum="PO1", goods_sku="TT-PO1", quantity=100, in_quantity=40, status="4",
             warehouseName="美东-CENTRADE", willArriveDate=None, purchaseArrivalDate=None),
        dict(PONum="PO2", goods_sku="TT-PO1", quantity=10, in_quantity=10, status="3",
             warehouseName="美东-CENTRADE", willArriveDate=None, purchaseArrivalDate=None),
        dict(PONum="PO3", goods_sku="TT-PO1", quantity=5, in_quantity=0, status="0",
             warehouseName="美中-FZH-DANEEY", willArriveDate=None, purchaseArrivalDate=None),
    ])
    frame, meta = load_po_tongtool(path)
    assert set(frame["document_key"]) == {"PO1", "PO3"}      # 已收(status 3)不进开放量
    assert float(frame["qty"].sum()) == 65                    # 60 + 5
    assert meta["rows"] == 2 and meta["with_eta"] == 0


def test_tongtool_po_without_eta_stays_conditional(tmp_path):
    path = _po_file(tmp_path, [
        dict(PONum="PO1", goods_sku="TT-PO1", quantity=10, in_quantity=0, status="0",
             warehouseName="美中-FZH-DANEEY", willArriveDate=None, purchaseArrivalDate=None),
    ])
    frame, _ = load_po_tongtool(path)
    rows, balances, evidence = build([("TT-KS1", "美中-FZH-DANEEY", 0, 0)], po_tongtool=frame.to_dict("records"))
    po_rows = [r for r in rows if r.source_layer == "tongtool_po"]
    assert len(po_rows) == 1
    assert po_rows[0].available_date is None
    assert po_rows[0].date_confidence == "unknown"
    # 无 ETA 的 PO 不进已证到货
    result = net_target(sku="KS1", warehouse="美中-FZH-DANEEY", uom=UOM, as_of=AS_OF,
                        buckets=BUCKETS, demand_rows=[dict(demand_row_id="d1",
                                                           demand_date="2026-10-28",
                                                           canonical_sku="KS1",
                                                           canonical_warehouse="美中-FZH-DANEEY",
                                                           canonical_uom=UOM,
                                                           quantity=Decimal("4"))],
                        supply_rows=rows)
    protect = {r["bucket_id"]: r for r in result["rows"] if r["scenario"] == "expected"}["protect"]
    assert protect["receipts"] == Decimal("0")
    assert protect["conditional_receipts"] == Decimal("10")
    assert protect["status"] == "conditional"


def test_tongtool_po_matches_by_tongtool_sku_without_en_mapping(tmp_path):
    path = _po_file(tmp_path, [
        dict(PONum="PO9", goods_sku="UNKNOWN-TT-SKU", quantity=3, in_quantity=0, status="0",
             warehouseName="美中-FZH-DANEEY", willArriveDate=None, purchaseArrivalDate=None),
    ])
    frame, _ = load_po_tongtool(path)
    rows, _, evidence = build([], po_tongtool=frame.to_dict("records"))
    assert rows == []
    assert "identity_unproven" in reasons(evidence)


def test_missing_tongtool_po_file_is_not_fabricated(tmp_path):
    frame, meta = load_po_tongtool(tmp_path / "nope.jsonl")
    assert len(frame) == 0
    assert meta["exists"] is False and meta["rows"] == 0


# ── 5. F2 逐桶口径 ──────────────────────────────────────────────────────

def test_period_demand_and_carried_unserved_are_separate_columns():
    from supply_chain_visibility.supply_row import SupplyRow
    supply = [SupplyRow(sku="KS1", warehouse="W", stage="on_hand", source_layer="inventory_snapshot",
                        qty=Decimal("1"), qty_status="known", uom=UOM, uom_proven=True,
                        event_date="2026-10-27", available_date=None, date_confidence="unknown",
                        timezone_status="unverified", identity_confidence="proven",
                        source_as_of=None, scope="in_house", warehouse_confidence="confirmed",
                        role="finished", b_min_eligible=False, b_max_eligible=True,
                        source_key="snap", source_complete=True)]
    demand_rows = [dict(demand_row_id="d1", demand_date="2026-10-28", canonical_sku="KS1",
                        canonical_warehouse="W", canonical_uom=UOM, quantity=Decimal("3")),
                   dict(demand_row_id="d2", demand_date="2026-11-08", canonical_sku="KS1",
                        canonical_warehouse="W", canonical_uom=UOM, quantity=Decimal("2"))]
    result = net_target(sku="KS1", warehouse="W", uom=UOM, as_of=AS_OF, buckets=BUCKETS,
                        demand_rows=demand_rows, supply_rows=supply)
    rows = {r["bucket_id"]: r for r in result["rows"] if r["scenario"] == "expected"}
    assert rows["protect"]["period_demand"] == Decimal("3")
    assert rows["protect"]["carried_unserved"] == Decimal("0")
    # 保护期缺 2 件 → 后续桶 carried 承接，period_demand 仍是本桶真实需求
    assert rows["w1"]["period_demand"] == Decimal("0")
    assert rows["w1"]["carried_unserved"] == Decimal("2")
    assert rows["w2"]["period_demand"] == Decimal("2")
    assert rows["w2"]["carried_unserved"] == Decimal("2")
    # 兼容列仍保留：demand = period + carried
    assert rows["w1"]["demand"] == Decimal("2")
    assert rows["w2"]["demand"] == Decimal("4")
