"""fulfillment 包离线单测 —— 不连 ERP。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fulfillment import codes as C            # noqa: E402
from fulfillment import quantities as Q        # noqa: E402
from fulfillment import rules as R             # noqa: E402
from fulfillment import stages as S            # noqa: E402

KS = "KS0001-DM-140-YELLOW"
PK = "PK#KS0001-DM-140-YELLOW"
CODE = "CENKZ1325-Yellow-138"


# ── codes ──────────────────────────────────────────────────────────────
def test_classify_code_item_vs_customer():
    assert C.classify_code(PK) == "item_code"
    assert C.classify_code(KS) == "item_code"
    assert C.classify_code("ND#KS0001-DM-140-YELLOW") == "item_code"
    assert C.classify_code(CODE) == "customer_code"


def test_parse_inputs_dedupes_and_keeps_order():
    ents = C.parse_inputs(f" {CODE} , {PK} ; {CODE} ")
    assert [e.raw for e in ents] == [CODE, PK]
    assert [e.kind for e in ents] == ["customer_code", "item_code"]


def test_parse_inputs_forced_kind():
    ents = C.parse_inputs("A,B", default_kind="item_code")
    assert all(e.kind == "item_code" for e in ents)


def test_resolve_inputs_reports_hits_and_misses():
    so_rows = [
        {"so": "SO-1", "line_id": "L1", "item_code": PK, "customer_item_code": CODE},
        {"so": "SO-2", "line_id": "L2", "item_code": PK, "customer_item_code": None},
    ]
    ents = C.parse_inputs(f"{CODE},{PK},{KS}")
    res = C.resolve_inputs(ents, so_rows, {CODE: [{"name": KS}]})
    by_raw = {r.raw: r for r in res}
    # 客户码：只按 customer_item_code 子串命中 L1（L2 该字段为空）；登记物料是 KS
    assert set(by_raw[CODE].hit_lines) == {"L1"}
    assert by_raw[CODE].resolved_items == [KS]
    assert by_raw[CODE].miss_reason == ""
    # 物料码 PK：精确命中 L1 与 L2
    assert set(by_raw[PK].hit_lines) == {"L1", "L2"}
    # 物料码 KS：PK# 行不算命中（精确匹配）→ 未命中
    assert by_raw[KS].hit_lines == []
    assert by_raw[KS].miss_reason


# ── stages ─────────────────────────────────────────────────────────────
def _row(**kw):
    base = dict(so="SO-1", line_id="L1", qty=40, delivered_qty=0, open_qty=40,
                so_status="To Deliver and Bill", so_docstatus=1,
                voided=False, cancelled=False, pps=[], wos=[])
    base.update(kw)
    return base


def _wo(name="WO-1", qty=40, ops=1):
    return {"name": name, "qty": qty, "status": "Not Started", "produced_qty": 0,
            "operations": [{"operation": f"OP{i}", "sequence_id": i, "status": "Completed"}
                           for i in range(1, ops + 1)]}


def test_stage_fully_shipped():
    st = S.resolve_stage(_row(delivered_qty=40, open_qty=0), {})
    assert (st.stage, st.substate) == (3, "已出库完成")


def test_stage_closed_unshipped_is_dead_not_done():
    st = S.resolve_stage(_row(so_status="Closed"), {})
    assert st.stage == 3 and st.substate == "Closed未发(死单)"


def test_stage_no_plan_no_wo():
    assert S.resolve_stage(_row(), {}) .substate == "未排产(无工单无生产计划)"


def test_stage_plan_without_wo():
    st = S.resolve_stage(_row(pps=[{"pp": "PP-1"}]), {})
    assert st.stage == 1 and st.substate == "已排产待下达(有计划无工单)"


def test_stage_wo_not_started():
    st = S.resolve_stage(_row(wos=[_wo()]), {})
    assert (st.stage, st.substate) == (2, "未开工")


def test_stage_in_production_partial():
    jc = {"WO-1": [{"operation": "OP1", "status": "Completed",
                    "for_quantity": 22, "total_completed_qty": 22}]}
    st = S.resolve_stage(_row(wos=[_wo()]), jc)
    assert (st.stage, st.substate) == (2, "生产中")


def test_stage_produced_enough_moves_to_pending_ship():
    jc = {"WO-1": [{"operation": "OP1", "status": "Completed",
                    "for_quantity": 40, "total_completed_qty": 40}]}
    st = S.resolve_stage(_row(wos=[_wo()]), jc)
    assert (st.stage, st.substate) == (3, "生产完成待出库")


def test_stage_voided_is_stage0():
    st = S.resolve_stage(_row(voided=True, so_docstatus=2), {})
    assert st.stage == 0


# ── quantities ─────────────────────────────────────────────────────────
def test_ladder_reconciles_valid_demand():
    jc = {"WO-1": [{"operation": "OP1", "status": "Completed",
                    "for_quantity": 20, "total_completed_qty": 20}]}
    row = _row(qty=40, delivered_qty=10, open_qty=30, wos=[_wo()])
    lad = Q.quantity_ladder(row, jc)
    assert lad["valid_demand_qty"] == 40
    assert lad["credible_produced_qty"] == 20
    assert lad["reconcile_ok"] is True


def test_ladder_voided_zero_valid_demand():
    lad = Q.quantity_ladder(_row(voided=True), {})
    assert lad["valid_demand_qty"] == 0
    assert lad["cancelled_or_amended_qty"] == 40


# ── rules ──────────────────────────────────────────────────────────────
def _ctx(so_rows, anomalies=(), wos=()):
    return {"so_rows": so_rows, "wos": list(wos), "jc_map": {},
            "anomalies": list(anomalies), "totals": {}}


def test_rules_maps_engine_kind_to_code_and_owner():
    rows = [_row(open_qty=40)]
    ctx = _ctx(rows, [{"level": "error", "kind": "死单", "key": "SO-1", "message": "x"}])
    out = R.build_anomalies(ctx)
    dead = [a for a in out if a.code == "CLOSED_UNSHIPPED"]
    assert dead and dead[0].owner_role == "计划" and dead[0].affected_qty == 40


def test_rules_adds_plan_without_wo():
    rows = [_row(pps=[{"pp": "PP-1"}], wos=[])]
    out = R.build_anomalies(_ctx(rows))
    assert any(a.code == "PLAN_NO_WORK_ORDER" for a in out)


def test_rules_adds_dn_draft_stall():
    rows = [_row(draft_dn=15, wos=[_wo()])]
    out = R.build_anomalies(_ctx(rows))
    stall = [a for a in out if a.code == "DN_DRAFT_STALL"]
    assert stall and stall[0].affected_qty == 15


def test_rules_adds_delivery_overdue():
    rows = [_row(delivery_date="2020-01-01", open_qty=40, wos=[_wo()])]
    out = R.build_anomalies(_ctx(rows), today=date(2026, 10, 13))
    assert any(a.code == "DELIVERY_OVERDUE" for a in out)


def test_rules_no_delivery_overdue_when_future_or_closed():
    future = [_row(delivery_date="2030-01-01", open_qty=40, wos=[_wo()])]
    assert not any(a.code == "DELIVERY_OVERDUE"
                   for a in R.build_anomalies(_ctx(future), today=date(2026, 10, 13)))
    closed = [_row(delivery_date="2020-01-01", so_status="Closed", open_qty=40, wos=[_wo()])]
    assert not any(a.code == "DELIVERY_OVERDUE"
                   for a in R.build_anomalies(_ctx(closed), today=date(2026, 10, 13)))


def test_rules_adds_op_stall():
    wo = _wo()
    jc = {"WO-1": [{"operation": "OP1", "status": "Completed", "for_quantity": 10,
                    "total_completed_qty": 10, "actual_end_date": "2026-01-01"}]}
    row = _row(open_qty=40, wos=[wo])
    ctx = {"so_rows": [row], "wos": [wo], "jc_map": jc, "anomalies": [], "totals": {}}
    out = R.build_anomalies(ctx, today=date(2026, 10, 13), stall_days=14)
    assert any(a.code == "OP_STALL" for a in out)
    # 阈值放宽到 400 天则不再告警
    out2 = R.build_anomalies(ctx, today=date(2026, 10, 13), stall_days=400)
    assert not any(a.code == "OP_STALL" for a in out2)


def test_anomalies_sorted_by_severity():
    rows = [_row(open_qty=40, draft_dn=5, wos=[_wo()])]
    ctx = _ctx(rows, [{"level": "error", "kind": "死单", "key": "SO-1", "message": "x"}])
    out = R.build_anomalies(ctx)
    sev = [a.severity for a in out]
    assert sev == sorted(sev, key=lambda s: {"error": 0, "warn": 1, "info": 2}[s])


# ── report / render 冒烟（离线，覆盖 §9 摘要 + 三个适配器）──────────────
def _synthetic_result():
    from fulfillment.model import (FulfillmentLine, FulfillmentQueryResult,
                                   StageResult)
    ln = FulfillmentLine(
        so="SO-1", so_line_id="L1", item_code=PK, item_name="皮壳", customer="C",
        company="FZH", so_status="Closed", so_docstatus=1, delivery_date="2026-01-09",
        ordered_qty=40, shipped_qty=0, open_qty=40, draft_qty=0, progress="-",
        quantities={"ordered_qty": 40, "valid_demand_qty": 40,
                    "cancelled_or_amended_qty": 0, "factory_shipped_qty": 0,
                    "factory_open_qty": 40, "reconcile_ok": True},
        stage=StageResult(3, "Closed未发(死单)", []),
        anomalies=[], input_sources=[CODE])
    ctx = {"empty": False, "so_rows": [], "dn_rows": [], "wos": [], "jc_map": {},
           "pp_rows": [], "item_master": {}, "item_codes": [PK],
           "master_items": [], "master_text": "", "customer_code": CODE,
           "lead_months": 3, "dup_window": 3}
    r = FulfillmentQueryResult(inputs_text=CODE, lines=[ln], totals={
        "order_qty": 40, "valid_qty": 40, "voided_qty": 0, "cancelled_qty": 0,
        "shipped_qty": 0, "open_qty": 40, "dead_qty": 40, "in_progress_qty": 0,
        "draft_qty": 0}, ctx=ctx)
    r.resolutions = C.resolve_inputs(C.parse_inputs(CODE), [
        {"so": "SO-1", "line_id": "L1", "item_code": PK, "customer_item_code": CODE}], {})
    r.anomalies = [R.Anomaly("error", "CLOSED_UNSHIPPED", 40, "x", "y", "SO-1", "计划", "z", so="SO-1")]
    return r


def test_summary_and_partitions_smoke():
    from fulfillment.report import build_partitions, build_summary, headline
    r = _synthetic_result()
    r.summary = build_summary(r)
    r.partitions = build_partitions(r)
    assert "未命中 0" in r.summary["query"]
    assert "Closed" in headline(r)
    assert r.partitions["orders"][0]["so"] == "SO-1"


def test_json_and_excel_render_smoke(tmp_path):
    import json

    from fulfillment import render
    from fulfillment.report import build_partitions, build_summary
    r = _synthetic_result()
    r.summary = build_summary(r)
    r.partitions = build_partitions(r)
    out = render.write_json(r, tmp_path / "r.json")
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["lines"][0]["stage"]["substate"] == "Closed未发(死单)"
    wb = render.build_workbook(r)
    assert wb.sheetnames[0] == "履约总览"
    assert "异常与下一行动" in wb.sheetnames


# ── 整单齐套（opt-in）─────────────────────────────────────────────────────
def test_kit_finished_item_strips_prefix():
    from fulfillment import kit as K
    assert K.finished_item("PK#KS0001-DM-140-YELLOW") == "KS0001-DM-140-YELLOW"
    assert K.finished_item("ND#KS0001-140-CYF-WHITE") == "KS0001-140-CYF-WHITE"
    assert K.finished_item("KS0001-DM-140-YELLOW") == "KS0001-DM-140-YELLOW"


def _kit_line(item_code="PK#X", open_qty=10):
    from fulfillment.model import FulfillmentLine, StageResult
    return FulfillmentLine(
        so="SO-1", so_line_id="L1", item_code=item_code, item_name="", customer="",
        company="", so_status="To Deliver and Bill", so_docstatus=1, delivery_date="",
        ordered_qty=open_qty, shipped_qty=0, open_qty=open_qty, draft_qty=0, progress="-",
        stage=StageResult(2, "生产中", []))


def test_kit_marks_unexpandable_bom(monkeypatch):
    from fulfillment import kit as K
    monkeypatch.setattr(K, "fetch_bom", lambda fin, *a, **k: ("self_ref", []))
    ln = _kit_line()
    K.evaluate_kit([ln], "u", "k", "s", sleep_s=0)
    assert ln.kit["mode"] == "self_ref"
    assert ln.kit["ready_qty"] is None
    assert ln.kit["note"]


def test_kit_full_ready_is_min_over_components(monkeypatch):
    from fulfillment import kit as K
    monkeypatch.setattr(K, "fetch_bom", lambda fin, *a, **k: ("full", [
        {"item_code": "PK#X", "qty": 1.0}, {"item_code": "ND#X", "qty": 2.0}]))
    supplies = {"PK#X": {"produced": 10, "factory_stock": 0, "foreign_stock": 99, "supply": 10},
                "ND#X": {"produced": 0, "factory_stock": 6, "foreign_stock": 0, "supply": 6}}
    monkeypatch.setattr(K, "component_supply", lambda ic, *a, **k: supplies[ic])
    ln = _kit_line()
    K.evaluate_kit([ln], "u", "k", "s", sleep_s=0)
    # PK#X: 10/1 = 10 ; ND#X: 6/2 = 3 → min 3（国外仓 99 不计入 supply）
    assert ln.kit["ready_qty"] == 3
