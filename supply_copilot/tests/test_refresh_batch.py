import json
from pathlib import Path

import pandas as pd
import pytest

from supply_copilot import batch, cli, period

POOL = "美东USNJ"
WAREHOUSE = "美东-CENTRADE"
PACK_AS_OF = "2026-11-13"
RUN_AS_OF = "2026-11-24"
MANIFEST = {"version": "test-pack", "as_of": PACK_AS_OF, "files": []}
D6_COLUMNS = ["product_id", "池", "形态", "UOM", "q95", "PO追加(去重)", "SO已下",
              "CG可调拨抵扣", "建议动作", "新补数量", "催已有量", "需要日", "下单日",
              "路线状态"]
D5_COLUMNS = ["product_id", "pool", "physical_form", "canonical_uom", "horizon",
              "horizon_days", "p50", "q90", "q95", "model"]


def d6_row(pid, q95=100, **extra):
    row = {"product_id": pid, "池": POOL, "形态": "成品", "UOM": "个", "q95": q95,
           "PO追加(去重)": 0, "SO已下": 0, "CG可调拨抵扣": 0, "建议动作": "补",
           "新补数量": 60, "催已有量": 0, "需要日": "2027-02-16", "下单日": "2026-12-28",
           "路线状态": "route_unavailable_manual_review"}
    row.update(extra)
    return row


def d5_row(pid, q95=100, form="成品"):
    return {"product_id": pid, "pool": POOL, "physical_form": form,
            "canonical_uom": "个", "horizon": 97, "horizon_days": 97,
            "p50": 70, "q90": 90, "q95": q95, "model": "ets_ann"}


def make_pack(root: Path, d6_rows, d5_rows, aliases=None, so_records=None):
    data = root / "data"
    data.mkdir(parents=True)
    with pd.ExcelWriter(data / "D6_v6_22.xlsx") as writer:
        pd.DataFrame(d6_rows, columns=D6_COLUMNS).to_excel(
            writer, sheet_name="1_全量动作", index=False)
    with pd.ExcelWriter(data / "D5_v6_8.xlsx") as writer:
        pd.DataFrame(d5_rows, columns=D5_COLUMNS).to_excel(
            writer, sheet_name="1_预测", index=False)
    aliases = aliases or {}
    lines = [f"{pid}\t{alias}\t" for pid, alias in aliases.items()]
    (data / "sku_map.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    records = so_records or []
    (data / "W1_SO.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8")
    return root


def live_rows(alias, available=40, intransit=0, waiting=0,
              snapshot_at="2026-11-24 01:00:00"):
    return [{"sku": alias, "warehouse": WAREHOUSE, "available": available,
             "intransit": intransit, "waiting_shipment": waiting,
             "run_id": "R1", "snapshot_at": snapshot_at}]


def so_record(so, lines, stage_balances=None, as_of="2026-11-20"):
    return {"so": so, "payload": {"as_of": as_of, "lines": lines,
                                  "stage_balances": stage_balances or []}}


def so_line(so, so_line_id, qty, delivered=0.0, transaction_date="2026-11-01",
            customer="美东公司（CENTRADE）", item_code="KS1-BASE"):
    return {"so": so, "so_line": so_line_id, "item_code": item_code,
            "customer": customer, "so_status": "To Deliver and Bill",
            "so_docstatus": 1, "transaction_date": transaction_date,
            "delivery_date": "2026-12-01", "qty": qty, "delivered_qty": delivered,
            "uom": "个", "warehouse": "半成品仓 - FZH", "scope": "in_house",
            "role": "finished"}


def run(root, **kwargs):
    kwargs.setdefault("as_of", RUN_AS_OF)
    kwargs.setdefault("manifest", MANIFEST)
    return batch.refresh_pool(root, "USNJ", **kwargs)


# ------------------------------------------------------------------ period rules

def test_period_full_period_is_not_remaining_period():
    out = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF)
    assert out["basis"] == "full_period"
    assert out["determinate"] is False
    assert out["start"] == PACK_AS_OF and out["end"] == "2027-02-17"
    assert "整期不得当剩余期" in out["reason"]


def test_period_explicit_equal_length_is_determinate_only_with_matching_observation():
    out = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                period_start="2026-11-24", period_end="2027-02-28",
                                supply_observed_at="2026-11-24 05:17:57")
    assert out["basis"] == "explicit_period" and out["determinate"] is True
    assert out["days"] == 97 and out["elapsed_days"] == 0
    assert out["note"] and "起点相差 11 天" in out["note"]


def test_period_elapsed_days_are_refused_not_bridged():
    out = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                period_start="2026-11-13", period_end="2027-02-17",
                                supply_observed_at="2026-11-24 05:17:57")
    assert out["determinate"] is False
    assert out["elapsed_days"] == 11
    assert "已逝 11 天" in out["reason"] and "不得用整期需求减当下库存" in out["reason"]
    assert out["demand_bridge"]["available"] is False


def test_period_observation_before_start_or_missing_is_refused():
    early = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                  period_start="2026-11-24", period_end="2027-02-28",
                                  supply_observed_at="2026-11-23")
    assert early["determinate"] is False and "不是期初库存" in early["reason"]
    missing = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                    period_start="2026-11-24", period_end="2027-02-28")
    assert missing["determinate"] is False and "库存观测时点不明" in missing["reason"]


def test_period_short_explicit_window_is_refused():
    out = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                period_start="2026-11-24", period_end="2026-12-04",
                                supply_observed_at="2026-11-24")
    assert out["determinate"] is False
    assert "不做比例外推" in out["reason"]


def test_period_incomplete_or_before_anchor_is_refused():
    one = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                period_start="2026-11-13")
    assert one["determinate"] is False and "不完整" in one["reason"]
    early = period.resolve_period(horizon_days=97, pack_as_of=PACK_AS_OF, as_of=RUN_AS_OF,
                                  period_start="2026-11-01", period_end="2027-02-05")
    assert early["determinate"] is False and "早于 D5 预测起点" in early["reason"]


def test_period_missing_anchor_is_unknown_time():
    out = period.resolve_period(horizon_days=97, pack_as_of=None, as_of=RUN_AS_OF)
    assert out["determinate"] is False and "时点不明" in out["reason"]


# --------------------------------------------------------------------- snapshot

def test_full_period_run_refuses_determinate_suggestion(tmp_path):
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    result = run(tmp_path, live_rows=live_rows("TT1"))
    row = result["snapshot"]["rows"][0]
    assert row["period"]["basis"] == "full_period"
    assert row["period"]["determinate"] is False
    assert row["decision"]["action"] == "暂不能判断"
    assert row["decision"]["net_requirement"] is None
    assert "整期不得当剩余期" in row["decision"]["reason"]


def test_explicit_period_uses_proven_supply_only(tmp_path):
    make_pack(tmp_path, [d6_row("KS1", q95=100, **{"PO追加(去重)": 30})],
              [d5_row("KS1", q95=100)], {"KS1": "TT1"})
    result = run(tmp_path, live_rows=live_rows("TT1", available=40), sku="KS1",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["supply"]["proven"] == 40
    assert row["supply"]["stages"][-3]["stage"] == "po_open"
    assert row["supply"]["stages"][-3]["counts_as_proven"] is False
    assert row["decision"]["net_requirement"] == 60      # 100 - 40, PO not subtracted
    assert row["decision"]["action"] == "催已有/待核"     # PO open exists, verify first


def test_explicit_period_without_pipeline_buys(tmp_path):
    # current W1 snapshot (as_of == run) so an unobserved SO may be trusted as 0
    records = [so_record("SO-9", [so_line("SO-9", "L1", 5, item_code="KS2")],
                         as_of=RUN_AS_OF)]
    make_pack(tmp_path, [d6_row("KS1", q95=100)], [d5_row("KS1", q95=100)],
              {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1", available=40), sku="KS1",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["decision"]["action"] == "补"
    assert row["decision"]["net_requirement"] == 60
    assert row["so"]["open_qty"] == 0.0
    assert row["so"]["current_for_decision"] is True


def test_stale_so_evidence_never_becomes_zero_pipeline(tmp_path):
    records = [so_record("SO-1", [so_line("SO-1", "L1", 10)], as_of="2026-10-27")]
    make_pack(tmp_path, [d6_row("KS1", q95=100)], [d5_row("KS1", q95=100)],
              {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1", available=40), sku="KS1",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["so"]["current_for_decision"] is False
    assert row["so"]["completeness"] == "stale_observation"
    assert row["decision"]["action"] == "催已有/待核"     # not 补: SO is unknown, not 0
    assert "非当前" in row["decision"]["reason"]


def test_short_explicit_period_keeps_row_but_refuses(tmp_path):
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1",
                 period_start="2026-11-24", period_end="2026-12-04")
    row = result["snapshot"]["rows"][0]
    assert row["period"]["basis"] == "explicit_period"
    assert row["decision"]["action"] == "暂不能判断"
    assert "不做比例外推" in row["decision"]["reason"]


def test_unknown_quantities_stay_null(tmp_path):
    make_pack(tmp_path, [d6_row("KS1", q95=float("nan"))],
              [d5_row("KS1", q95=float("nan"))], {"KS1": "TT1"})
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["demand"]["q95"] is None
    assert row["decision"]["net_requirement"] is None
    assert row["decision"]["action"] == "暂不能判断"


def test_live_unavailable_keeps_supply_null(tmp_path):
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    result = run(tmp_path, live_rows=[], sku="KS1",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["supply"]["proven"] is None
    assert all(stage["qty"] is None for stage in row["supply"]["stages"][:3])
    assert row["decision"]["action"] == "暂不能判断"


# ------------------------------------------------------------------- SO evidence

def test_so_open_deduped_by_so_and_line(tmp_path):
    records = [
        so_record("SO-1", [
            so_line("SO-1", "L1", 10, transaction_date="2026-11-01"),
            so_line("SO-1", "L2", 5, transaction_date="2026-01-01"),
            so_line("SO-1", "L3", 8, transaction_date=None),
        ]),
        so_record("SO-1", [so_line("SO-1", "L1", 10, transaction_date="2026-11-01")]),
    ]
    make_pack(tmp_path, [d6_row("KS1-BASE")], [d5_row("KS1-BASE")],
              {"KS1-BASE": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1-BASE",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    so = result["snapshot"]["rows"][0]["so"]
    assert so["open_qty"] == 23.0                     # 10 + 5 + 8, duplicate 10 skipped
    assert so["duplicate_lines_collapsed"] == 1
    assert so["recent_open_qty"] == 10.0
    assert so["history_open_qty"] == 5.0
    assert so["unknown_date_open_qty"] == 8.0
    assert so["known_three_bucket_sum_equals_known_open"] is True
    assert so["included_in_proven_supply"] is False
    assert result["report"]["so_dedupe"]["duplicate_lines"] == 1
    assert result["report"]["so_three_way"]["balanced"] is True


def test_so_is_never_added_to_proven_supply(tmp_path):
    records = [so_record("SO-1", [so_line("SO-1", "L1", 50)])]
    make_pack(tmp_path, [d6_row("KS1-BASE", q95=100)], [d5_row("KS1-BASE", q95=100)],
              {"KS1-BASE": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1", available=40),
                 sku="KS1-BASE", period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["supply"]["proven"] == 40               # SO 50 not added
    assert row["decision"]["net_requirement"] == 60    # still 100 - 40
    assert row["decision"]["so_included_in_supply"] is False
    assert row["decision"]["action"] == "催已有/待核"
    assert row["so"]["open_qty"] == 50.0


def test_so_not_double_counted_across_form_rows(tmp_path):
    rows = [d6_row("KS1"), d6_row("KS1", **{"形态": "成品+皮壳"})]
    d5 = [d5_row("KS1"), d5_row("KS1", form="成品+皮壳")]
    records = [so_record("SO-1", [so_line("SO-1", "L1", 45, item_code="KS1")],
                         as_of=RUN_AS_OF)]
    make_pack(tmp_path, rows, d5, {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1", available=10))
    report = result["report"]
    assert report["bankers"]["accepted"] == 2
    assert report["so_three_way"]["open_total"] == 45.0      # not 90
    assert report["so_scope"]["in_scope"]["keys"] == 1
    assert report["so_scope"]["in_scope"]["lines"] == 1
    for row in result["snapshot"]["rows"]:
        assert row["so"]["open_qty"] == 45.0                  # row-level repeats
        assert "不可跨行相加" in row["so"]["aggregation"]
    uniq_row_sum = len({row["key"].split("|")[1] for row in result["snapshot"]["rows"]})
    assert uniq_row_sum == 1


def test_so_out_of_scope_is_reported_separately(tmp_path):
    records = [
        so_record("SO-1", [so_line("SO-1", "L1", 10, item_code="KS1")], as_of=RUN_AS_OF),
        so_record("SO-2", [so_line("SO-2", "L1", 20, item_code="KS-OTHER")],
                  as_of=RUN_AS_OF),
        so_record("SO-3", [so_line("SO-3", "L1", 30, item_code="KS-USTX",
                                   customer="美中公司（DANEEY）")], as_of=RUN_AS_OF),
    ]
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1"))
    scope = result["report"]["so_scope"]
    assert result["report"]["so_three_way"]["open_total"] == 10.0
    assert scope["in_scope"]["keys"] == 1
    assert scope["out_of_scope"]["total"]["open_qty"] == 20.0
    assert scope["out_of_scope"]["total"]["open_qty"] == 20.0
    assert "product_not_in_snapshot_scope" in scope["out_of_scope"]["reason"]
    assert scope["other_branches"]["total"]["open_qty"] == 30.0
    assert scope["branch_total"]["open_qty"] == 30.0


def test_so_line_with_missing_quantity_stays_null(tmp_path):
    records = [so_record("SO-1", [so_line("SO-1", "L1", 10, delivered=None,
                                          item_code="KS1")], as_of=RUN_AS_OF)]
    make_pack(tmp_path, [d6_row("KS1", q95=100)], [d5_row("KS1", q95=100)],
              {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1", available=40), sku="KS1",
                 period_start=RUN_AS_OF, period_end="2027-02-28")
    row = result["snapshot"]["rows"][0]
    assert row["so"]["open_qty"] is None            # total contains an unknown line
    assert row["so"]["known_open_qty"] == 0.0       # known part named separately
    assert row["so"]["unknown_qty_lines"] == 1
    assert row["so"]["unknown_lines"][0]["open_qty"] is None
    assert row["so"]["completeness"] == "partial_unknown_qty"
    assert "下界" in row["so"]["unknown_reason"]
    so_open_stage = next(s for s in row["supply"]["stages"]
                         if s["stage"] == "so_open")
    assert so_open_stage["qty"] is None and so_open_stage["known"] is False
    assert so_open_stage["known_subtotal"] == 0.0
    report = result["report"]
    assert report["so_three_way"]["open_total"] is None
    assert report["so_three_way"]["known_open_total"] == 0.0
    assert report["so_three_way"]["balanced"] is None
    assert report["so_three_way"]["known_qty_complete"] is False
    assert report["so_three_way"]["unknown_qty_lines"] == 1
    assert report["so_scope"]["in_scope"]["open_qty"] is None
    assert report["so_scope"]["in_scope"]["known_open_qty"] == 0.0
    assert report["so_scope"]["branch_total"]["open_qty"] is None
    assert row["decision"]["action"] == "催已有/待核"   # SO is a lower bound, not 0


def test_stage_balance_with_missing_quantity_stays_null(tmp_path):
    balances = [{"so": "SO-1", "so_line_id": "L1", "item_code": "KS1",
                 "stage": "in_production", "qty": None, "scope": "in_house",
                 "qty_status": "unknown", "source_record": "WO-1"}]
    records = [so_record("SO-1", [so_line("SO-1", "L1", 7, item_code="KS1")],
                         balances)]
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1")
    row = result["snapshot"]["rows"][0]
    assert row["so_stage"]["so_stage_qty"]["in_production"] is None
    assert row["so_stage"]["so_stage_complete"] is False
    stage = next(s for s in row["supply"]["stages"]
                 if s["stage"] == "w1_stage:in_production")
    assert stage["qty"] is None and stage["known"] is False
    assert result["report"]["so_stage"]["stage_totals"]["in_production"] is None
    assert result["report"]["so_stage"]["stage_known_subtotals"]["in_production"] == 0.0


def test_stage_total_with_known_and_unknown_rows_stays_null(tmp_path):
    balances = [
        {"so": "SO-1", "so_line_id": "L1", "item_code": "KS1",
         "stage": "in_production", "qty": None, "scope": "in_house",
         "qty_status": "unknown", "source_record": "WO-1"},
        {"so": "SO-1", "so_line_id": "L1", "item_code": "KS1",
         "stage": "in_production", "qty": 5.0, "scope": "in_house",
         "qty_status": "known", "source_record": "WO-2"},
    ]
    records = [so_record("SO-1", [so_line("SO-1", "L1", 7, item_code="KS1")],
                         balances)]
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1")
    row = result["snapshot"]["rows"][0]
    assert row["so_stage"]["so_stage_qty"]["in_production"] is None
    assert row["so_stage"]["so_stage_complete"] is False
    stage_report = result["report"]["so_stage"]
    assert stage_report["stage_totals"]["in_production"] is None   # [null, 5] != 5
    assert stage_report["stage_known_subtotals"]["in_production"] == 5.0


def test_so_scope_total_stays_null_on_mixed_known_and_unknown(tmp_path):
    records = [so_record("SO-1", [
        so_line("SO-1", "L1", 10, transaction_date="2026-01-01", item_code="KS1"),
        so_line("SO-1", "L2", 6, delivered=None,
                transaction_date="2026-11-01", item_code="KS1"),
    ], as_of=RUN_AS_OF)]
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1")
    so = result["snapshot"]["rows"][0]["so"]
    assert so["open_qty"] is None and so["known_open_qty"] == 10.0
    assert so["recent_open_qty"] is None and so["known_recent_open_qty"] == 0.0
    assert so["history_open_qty"] == 10.0 and so["known_history_open_qty"] == 10.0
    report = result["report"]
    assert report["so_three_way"]["open_total"] is None
    assert report["so_three_way"]["known_open_total"] == 10.0
    assert report["so_three_way"]["recent"] is None
    assert report["so_three_way"]["known_recent"] == 0.0
    assert report["so_three_way"]["history"] == 10.0
    assert report["so_three_way"]["balanced"] is None
    assert report["so_three_way"]["known_balanced"] is True


def test_tampered_snapshot_file_is_rejected(tmp_path):
    pack = tmp_path / "pack"
    make_pack(pack, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    result = run(pack, live_rows=live_rows("TT1"))
    out = tmp_path / "out"
    paths = batch.write_outputs(out, result)
    path = Path(paths["snapshot_path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rows"][0]["demand"]["q95"] = 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        batch.write_outputs(out, result)
    assert "疑似被改" in str(exc.value)


def test_unknown_stage_is_kept(tmp_path):
    balances = [{"so": "SO-1", "so_line_id": "L1", "item_code": "KS1-BASE",
                 "stage": "unknown", "qty": 7.0, "scope": "in_house",
                 "qty_status": "known", "source_record": "WO-1"}]
    records = [so_record("SO-1", [so_line("SO-1", "L1", 7)], balances)]
    make_pack(tmp_path, [d6_row("KS1-BASE")], [d5_row("KS1-BASE")],
              {"KS1-BASE": "TT1"}, records)
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1-BASE")
    row = result["snapshot"]["rows"][0]
    assert row["so"]["stage_counts"] == {"unknown": 7.0}
    assert row["so_stage"]["so_stage_qty"] == {"unknown": 7.0}
    assert row["so_stage"]["so_stage_included_in_proven_supply"] is False
    assert result["report"]["so_stage"]["included_in_proven_supply"] is False


def test_so_missing_evidence_is_not_zero(tmp_path):
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    (tmp_path / "data" / "W1_SO.jsonl").unlink()
    result = run(tmp_path, live_rows=live_rows("TT1"), sku="KS1",
                 period_start=PACK_AS_OF, period_end="2027-02-17")
    row = result["snapshot"]["rows"][0]
    assert row["so"]["open_qty"] is None
    assert row["so"]["evidence_loaded"] is False
    assert row["decision"]["action"] == "暂不能判断" or "SO" in row["decision"]["reason"]


# ---------------------------------------------------------------- reconciliation

def test_input_equals_accepted_plus_rejected_plus_skipped(tmp_path):
    rows = [
        d6_row("KS1"),
        d6_row(None),                       # rejected: missing product id
        d6_row("KS1"),                      # skipped: duplicate key
        d6_row("KS2"),
    ]
    make_pack(tmp_path, rows, [d5_row("KS1"), d5_row("KS2")],
              {"KS1": "TT1", "KS2": "TT2"})
    result = run(tmp_path, live_rows=live_rows("TT1") + live_rows("TT2"))
    bankers = result["report"]["bankers"]
    assert bankers["input_rows"] == 4
    assert bankers["accepted"] == 2
    assert bankers["rejected"] == 1
    assert bankers["skipped"] == 1
    assert bankers["balanced"] is True
    assert result["report"]["rejected"][0]["reason"] == "missing_product_id"
    assert "source_row" in result["report"]["rejected"][0]
    assert "duplicate_key_in_d6" in result["report"]["skipped"][0]["reason"]


def test_snapshot_hash_is_deterministic(tmp_path):
    make_pack(tmp_path, [d6_row("KS1"), d6_row("KS2", q95=55)],
              [d5_row("KS1"), d5_row("KS2", q95=55)],
              {"KS1": "TT1", "KS2": "TT2"})
    live = live_rows("TT1") + live_rows("TT2", available=10)
    first = run(tmp_path, live_rows=live, period_start=PACK_AS_OF,
                period_end="2027-02-17")
    second = run(tmp_path, live_rows=live, period_start=PACK_AS_OF,
                 period_end="2027-02-17")
    assert first["snapshot"]["snapshot_sha256"] == second["snapshot"]["snapshot_sha256"]
    assert first["snapshot"]["rows_sha256"] == second["snapshot"]["rows_sha256"]
    assert json.dumps(first["report"], ensure_ascii=False, sort_keys=True) == \
        json.dumps(second["report"], ensure_ascii=False, sort_keys=True)


def test_write_outputs_is_idempotent_and_report_fields(tmp_path):
    pack = tmp_path / "pack"
    make_pack(pack, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    result = run(pack, live_rows=live_rows("TT1"), period_start=PACK_AS_OF,
                 period_end="2027-02-17")
    out = tmp_path / "out"
    first = batch.write_outputs(out, result)
    second = batch.write_outputs(out, result)
    assert first["snapshot_file_sha256"] == second["snapshot_file_sha256"]
    report = json.loads(Path(first["report_path"]).read_text(encoding="utf-8"))
    for field in ("bankers", "rejected", "skipped", "so_dedupe", "so_three_way",
                  "so_stage", "source_hashes", "field_dictionary", "warnings"):
        assert field in report
    assert report["bankers"]["balanced"] is True
    assert report["accepted_by_period_basis"] == {"explicit_period": 1}


# ------------------------------------------------------------------------ CLI

def test_cli_legacy_single_sku_still_works(tmp_path, monkeypatch, capsys):
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    from supply_copilot import refresh
    monkeypatch.setattr(refresh, "_tt_skus", lambda root: {"KS1": ["TT1"]})
    monkeypatch.setattr(refresh, "_live_stock",
                        lambda *a, **k: {"status": "matched", "available": 10,
                                         "intransit": 0, "waiting_shipment": 0,
                                         "defects": 0})
    assert cli.main(["refresh", "--branch", "USNJ", "--sku", "KS1",
                     "--data-root", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list) and payload[0]["sku"] == "KS1"
    assert payload[0]["refresh_action"] in ("补", "催已有/待核", "不补")


def test_cli_all_requires_out(tmp_path):
    make_pack(tmp_path, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--branch", "USNJ", "--all", "--data-root", str(tmp_path)])
    assert "--out" in str(exc.value)


def test_cli_all_writes_snapshot_and_report(tmp_path, capsys):
    pack = tmp_path / "pack"
    make_pack(pack, [d6_row("KS1")], [d5_row("KS1")], {"KS1": "TT1"})
    live_path = tmp_path / "live.json"
    live_path.write_text(json.dumps({"rows": live_rows("TT1")}), encoding="utf-8")
    out = tmp_path / "private"
    code = cli.main(["refresh", "--branch", "USNJ", "--all", "--as-of", RUN_AS_OF,
                     "--data-root", str(pack), "--out", str(out),
                     "--live-snapshot", str(live_path),
                     "--period-start", PACK_AS_OF, "--period-end", "2027-02-17"])
    assert code == 0
    assert "输入 1 = 接收 1 + 拒收 0 + 跳过 0" in capsys.readouterr().out
    assert (out / "report.json").exists()
    assert len(list(out.glob("refresh_USNJ_*.json"))) == 1
