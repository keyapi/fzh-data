#!/usr/bin/env python
"""SC14 — 边界用例的可执行验收测试（全部用合成数据，离线）。

运行：
  uv run pytest experiments/sc14/test_contract.py -q
  uv run python  experiments/sc14/test_contract.py        # 无 pytest 也能跑

每个用例都对应 SC14 规格里的一条红线；`NEG` 表示反例（错误写法必须被拒）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract import rollup, validate_w1, validate_w3, w3_columns  # noqa: E402


def base(**kw) -> dict:
    r = {
        "sku": "SKU-A", "warehouse": "美东-CENTRADE", "as_of_date": "2026-10-23",
        "stage": "shipped_in_transit", "doc_type": "Delivery Note",
        "doc_name": "DN-26-00061", "doc_line": "1",
        "qty": 100, "uom": "个", "event_date": "2026-10-10",
        "available_date": "2026-11-10", "date_confidence": "confirmed",
        "source_key": "DN-26-00061|1|个", "scope": "in_house",
        "qty_status": "known", "allocation_known": False,
        "tracking_numbers": ["1Z999"], "batch_key": "B1", "date_proof": "shipment.node",
    }
    r.update(kw)
    return r


def codes(rows) -> set[str]:
    return {f.code for f in validate_w1(rows) if f.severity == "error"}


# ---------------------------------------------------------------- 未知 ≠ 0
def test_unknown_qty_is_null_not_zero():
    rows = [base(stage="po_open", qty=None, qty_status="unknown",
                 available_date=None, date_confidence="unknown", date_proof=None)]
    assert codes(rows) == set(), codes(rows)
    col = w3_columns(rollup(rows))
    assert col["supply_confirmed"] == {} and col["supply_expected"] == {}
    assert col["supply_unknown"]["qty_null_rows"] == 1
    assert 0 not in col["supply_unknown"]["qty_known"].values()


def test_unknown_qty_written_as_zero_is_rejected():
    rows = [base(stage="po_open", qty=0, qty_status="unknown",
                 available_date=None, date_confidence="unknown")]
    assert "E_UNKNOWN_AS_NUMBER" in codes(rows)


def test_null_qty_without_status_is_rejected():
    rows = [base(stage="po_open", qty=None, qty_status=None,
                 available_date=None, date_confidence="unknown")]
    assert "E_NULL_QTY_SILENT" in codes(rows)


# ---------------------------------------------------------------- ETA 未证不进判决
def test_unproven_eta_never_enters_confirmed_or_expected():
    rows = [
        base(source_key="A", available_date=None, date_confidence="unknown",
             tracking_numbers=["1Z1"], date_proof=None),
        base(source_key="B", available_date="2026-11-10", date_confidence="estimated"),
        base(source_key="C", available_date="2026-11-12", date_confidence="confirmed"),
    ]
    assert codes(rows) == set(), codes(rows)
    roll = rollup(rows)
    assert [r["source_key"] for r in roll["confirmed"]] == ["C"]
    assert [r["source_key"] for r in roll["expected"]] == ["B"]
    assert [r["source_key"] for r in roll["unknown"]] == ["A"]
    col = w3_columns(roll)
    assert col["supply_confirmed"] == {"个": 100}
    assert col["supply_expected"] == {"个": 100}
    assert col["supply_unknown"]["rows"] == 1


def test_unknown_confidence_with_a_date_is_rejected():
    rows = [base(date_confidence="unknown", available_date="2026-11-01")]
    assert "E_UNKNOWN_HAS_DATE" in codes(rows)


# ---------------------------------------------------------------- 一 DN 多号不复制
def test_one_dn_three_trackings_keeps_total_once():
    rows = [base(qty=120, allocation_known=False,
                 tracking_numbers=["1Z1", "1Z2", "1Z3"])]
    assert codes(rows) == set(), codes(rows)
    roll = rollup(rows)
    assert sum(r["qty"] for r in roll["confirmed"]) == 120  # 不是 360


def test_naive_multi_tracking_duplication_is_rejected():
    rows = [
        base(qty=120, tracking_numbers=["1Z1"]),
        base(qty=120, tracking_numbers=["1Z2"]),
        base(qty=120, tracking_numbers=["1Z3"]),
    ]
    assert "E_DUPLICATED_QTY" in codes(rows)


# ---------------------------------------------------------------- 部分到货不整单抵扣
def test_partial_receipt_splits_into_two_rows():
    rows = [
        base(stage="received", qty=40, received_qty=40, remaining_qty=60,
             doc_qty=100, source_key="DN|1|个|received", event_date="2026-10-20"),
        base(stage="shipped_in_transit", qty=60, received_qty=40, remaining_qty=60,
             doc_qty=100, source_key="DN|1|个|transit"),
    ]
    assert codes(rows) == set(), codes(rows)
    roll = rollup(rows)
    assert roll["opening_by_uom"] == {"个": 40}          # 只抵扣已收的 40
    assert sum(r["qty"] for r in roll["confirmed"]) == 60  # 剩余 60 仍在途
    assert 100 == roll["opening_by_uom"]["个"] + sum(r["qty"] for r in roll["confirmed"])


def test_partial_receipt_booked_as_full_transit_is_rejected():
    rows = [base(stage="shipped_in_transit", qty=100, received_qty=40)]
    assert "E_PARTIAL_AS_FULL" in codes(rows)


def test_partial_rows_that_do_not_sum_to_doc_qty_are_rejected():
    rows = [base(stage="received", qty=40, received_qty=40, remaining_qty=50, doc_qty=100)]
    assert "E_PARTIAL_SUM" in codes(rows)


# ---------------------------------------------------------------- 外部 FBA 两边都不算
def test_external_fba_received_is_neither_on_hand_nor_in_transit():
    rows = [base(stage="received", qty=500, scope="external_fba", source_key="FBA|1")]
    assert codes(rows) == set(), codes(rows)
    roll = rollup(rows)
    assert roll["opening_by_uom"] == {}
    assert roll["confirmed"] == []
    assert len(roll["excluded_external_fba"]) == 1


# ---------------------------------------------------------------- 单位与阶段守恒
def test_uom_units_are_not_summed_together():
    rows = [
        base(uom="个", qty=10, source_key="A"),
        base(uom="套", qty=7, source_key="B"),
    ]
    col = w3_columns(rollup(rows))
    assert col["supply_confirmed"] == {"个": 10, "套": 7}


def test_same_source_key_cannot_appear_twice():
    rows = [base(source_key="X", tracking_numbers=["1"]),
            base(source_key="X", stage="on_hand", available_date=None,
                 date_confidence="unknown", tracking_numbers=["2"])]
    assert "E_STAGE_DUP" in codes(rows)


def test_missing_required_fields_are_rejected():
    r = base()
    del r["source_key"]
    del r["date_confidence"]
    assert "E_REQUIRED" in codes([r])


def test_scope_missing_is_warning_not_error():
    r = base()
    del r["scope"]
    findings = validate_w1([r])
    assert any(f.code == "W_SCOPE_MISSING" and f.severity == "warning" for f in findings)
    assert not [f for f in findings if f.severity == "error"]


# ---------------------------------------------------------------- W3 侧
def test_w3_gap_must_be_null_when_demand_unknown():
    bad = [{"sku": "S", "warehouse": "W", "week": "2026-W44",
            "supply_confirmed": {"个": 10}, "supply_expected": {"个": 5},
            "supply_unknown": {"rows": 1}, "demand": None, "gap": 12,
            "confidence": "low"}]
    assert "E_GAP_WITHOUT_DEMAND" in {f.code for f in validate_w3(bad)}

    ok = [dict(bad[0], gap=None)]
    assert validate_w3(ok) == []


# ---------------------------------------------------------------- runner
if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}  {e}")
        else:
            print(f"PASS  {name}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
