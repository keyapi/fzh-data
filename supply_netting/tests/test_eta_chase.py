# -*- coding: utf-8 -*-
"""催证清单用例：正缺口键并集、缺证字段组合、汇总计数。"""

from __future__ import annotations

import json

import pandas as pd

from supply_netting.eta_chase import build_chase_list, load_line_evidence

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def keys():
    rows = []
    # A：90 天有缺口；B：只有 150 天缺口；C：无缺口（不应进清单）
    rows += [dict(window_days=90, canonical_sku="A", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
                  qty_current=10.0),
             dict(window_days=150, canonical_sku="A", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
                  qty_current=20.0)]
    rows += [dict(window_days=90, canonical_sku="B", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
                  qty_current=0.0),
             dict(window_days=150, canonical_sku="B", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
                  qty_current=5.0)]
    rows += [dict(window_days=90, canonical_sku="C", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
                  qty_current=0.0),
             dict(window_days=150, canonical_sku="C", canonical_warehouse="美东-CENTRADE", canonical_uom="个",
                  qty_current=0.0)]
    return pd.DataFrame(rows)


def tranches():
    base = dict(item_code_raw="PK#X", conversion_assumed=True, customer="美东公司（CENTADE）",
                role="finished", factory_warehouse="半成品仓 - FZH", qty_status="known",
                qty_basis="", scope="in_house", so_conserved=True, qty_evidence="known",
                authoritative_offset=False, eta_earliest=None, eta_latest=None,
                eta_basis="在途剩余海运未证（unknown）", confidence="unknown",
                spring_buffer_days=0.0, spring_crossing=False,
                dedup_status="po_in_transit_unproven;batch_key_present",
                exclusion_reason=None, layer_overlap_unproven=False)
    rows = [
        dict(base, so="SO-1", so_line_id="L1", canonical_sku="A", branch_warehouse="美东-CENTRADE",
             uom="个", stage="shipped_in_transit", qty=6.0, batch_key="DN-1", source_record="DN-1",
             included_in_stock="unknown"),
        dict(base, so="SO-2", so_line_id="L2", canonical_sku="B", branch_warehouse="美东-CENTRADE",
             uom="个", stage="shipped_in_transit", qty=3.0, batch_key="DN-2", source_record="DN-2",
             included_in_stock="unknown"),
        dict(base, so="SO-3", so_line_id="L3", canonical_sku="C", branch_warehouse="美东-CENTRADE",
             uom="个", stage="shipped_in_transit", qty=9.0, batch_key="DN-3", source_record="DN-3",
             included_in_stock="unknown"),
        dict(base, so="SO-3", so_line_id="L3", canonical_sku="C", branch_warehouse="美东-CENTRADE",
             uom="个", stage="produced_pending_dn", qty=9.0, batch_key="WO-3", source_record="WO-3",
             included_in_stock="unknown"),
    ]
    return pd.DataFrame(rows)


def w1(tmp_path):
    payload = dict(payload=dict(
        links=[dict(so="SO-1", so_line_id="L1", target_doctype="Shipment", target_name="SHIP-1"),
               dict(so="SO-1", so_line_id="L1", target_doctype="Delivery Note", target_name="DN-1")],
        milestones=[dict(so="SO-1", so_line_id="L1", node="dispatch", actual_at="2026-09-01 10:00:00",
                         source_record="Shi-1")],
    ))
    path = tmp_path / "w1.jsonl"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def build(tmp_path):
    kp, tp = tmp_path / "keys.csv", tmp_path / "tranches.csv"
    keys().to_csv(kp, index=False)
    tranches().to_csv(tp, index=False)
    return build_chase_list(kp, tp, w1(tmp_path))


def test_only_positive_gap_keys_enter_and_p1_p2_by_window(tmp_path):
    frame, summary = build(tmp_path)
    assert set(frame["SKU"]) == {"A", "B"}            # C 无缺口，不进清单
    tiers = frame.set_index("SKU")["优先级"].to_dict()
    assert tiers["A"].startswith("P1")
    assert tiers["B"].startswith("P2")
    assert summary["gap90_keys"] == 1 and summary["gap150_keys"] == 2


def test_missing_fields_reflect_shipment_evidence(tmp_path):
    frame, summary = build(tmp_path)
    by_sku = frame.set_index("SKU")
    with_ship = by_sku.loc["A"]
    assert with_ship["有Shipment"] == "是" and with_ship["有ETA"] == "否"
    assert "运单状态与 ETA" in with_ship["缺失字段"]
    without_ship = by_sku.loc["B"]
    assert without_ship["有Shipment"] == "否"
    assert "运单（Shipment）" in without_ship["缺失字段"]
    assert all("是否已入库存快照" in text for text in frame["缺失字段"])
    assert set(frame["是否可抵扣"]) == {"否（在途无 ETA，需先取证）"}


def test_summary_counts_and_quantities(tmp_path):
    frame, summary = build(tmp_path)
    assert summary["chase_rows"] == 2
    assert summary["dn_without_shipment_rows"] == 1        # B 有 DN 无 Shipment
    assert summary["shipment_without_eta_rows"] == 1       # A 有 Shipment 无 ETA
    assert summary["no_any_waybill_rows"] == 1             # B 既无 Shipment 也无 Tracking
    assert summary["chase_qty_by_uom"] == {"个": 9.0}      # 6 + 3，不跨 UOM


def test_line_evidence_loader_collects_dn_shipment_and_dispatch(tmp_path):
    evidence = load_line_evidence(w1(tmp_path))
    line = evidence[("SO-1", "L1")]
    assert "SHIP-1" in line["shipments"]
    assert "DN-1" in line["dns"]
    assert "2026-09-01" in line["dispatch_dates"]
