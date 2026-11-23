import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demand_collaboration.core import DomainError, Store
from demand_collaboration.recommendation import build_snapshot
from demand_collaboration.recommendation_scope import filter_snapshot
from demand_collaboration.web import create_app

HEAD = ["SKU", "客户", "仓", "形态", "UOM", "期间", "建议动作", "建议数量", "覆盖", "原因",
        "置信度", "C", "E", "预测", "q50", "q90", "q95", "模型", "需拍板", "特殊品"]


def write_csv(tmp_path, rows, name="USNJ补货建议.csv", headers=HEAD):
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def row(sku="KS0001", **overrides):
    values = {"SKU": sku, "客户": "Amazon-US", "仓": "USNJ", "形态": "成品", "UOM": "件",
              "期间": "2026-11-16 至 2026-11-22", "建议动作": "补", "建议数量": "120",
              "覆盖": "45天", "原因": "低于保护窗", "置信度": "中", "C": "80", "E": "20",
              "预测": "180", "q50": "170", "q90": "210", "q95": "240", "模型": "AutoETS",
              "需拍板": "否", "特殊品": "否"}
    values.update(overrides)
    return [values[name] for name in HEAD]


def snapshot_of(tmp_path, rows):
    path = write_csv(tmp_path, rows)
    return build_snapshot(path, "2026-11-12", period_start="2026-11-12", period_end="2027-02-17")


def test_296_rows_conserved_and_all_fields_retained(tmp_path):
    rows = [row(f"KS{i:04d}", **{"建议数量": str(i + 1)}) for i in range(296)]
    snapshot, report = snapshot_of(tmp_path, rows)
    assert report["input_count"] == 296
    assert report["accepted_count"] == 296
    assert report["rejected_count"] == report["skipped_count"] == 0
    assert report["reconciled"] is True
    assert len(snapshot["rows"]) == 296
    assert snapshot["accepted_count"] == 296
    assert snapshot["service_certified"] is False
    assert snapshot["replenishment_eligible"] is False
    assert snapshot["read_only"] is True
    first = snapshot["rows"][0]
    for key in ("row_id", "sku", "customer", "warehouse", "physical_form", "uom",
                "period_start", "period_end", "action", "qty", "coverage", "reason",
                "confidence", "confidence_level", "c_qty", "e_qty", "forecast",
                "q50", "q90", "q95", "model", "source_row", "source_hash",
                "as_of", "service_certified", "replenishment_eligible"):
        assert key in first, key
    assert first["period_start"] == "2026-11-16" and first["period_end"] == "2026-11-22"
    assert first["coverage"] == 45 and first["coverage_unit"] == "days"
    assert first["c_qty"] == 80 and first["e_qty"] == 20
    assert first["q50"] == 170 and first["q90"] == 210 and first["q95"] == 240
    assert first["source_row"] == 2
    assert len(first["source_hash"]) == 64


def test_unknown_is_null_and_explicit_zero_is_preserved(tmp_path):
    rows = [
        row("KS-UNKNOWN", **{"建议数量": "", "C": "", "E": "未知", "预测": "",
                             "q50": "", "q90": "n/a", "q95": "", "置信度": ""}),
        row("KS-ZERO", **{"建议数量": "0", "C": "0", "E": "0", "置信度": "0.3"}),
    ]
    snapshot, _ = snapshot_of(tmp_path, rows)
    unknown, zero = snapshot["rows"]
    assert unknown["qty"] is None and unknown["c_qty"] is None and unknown["e_qty"] is None
    assert unknown["forecast"] is None and unknown["q50"] is None and unknown["q90"] is None
    assert unknown["confidence"] is None and unknown["confidence_level"] is None
    assert zero["qty"] == 0 and zero["c_qty"] == 0 and zero["e_qty"] == 0
    assert zero["confidence_level"] == "low"
    assert unknown["missing_supply"] is True
    assert zero["missing_supply"] is False


def test_rejected_and_skipped_rows_are_retained_and_reconciled(tmp_path):
    rows = [
        row("KS-A"),
        row("KS-A"),                                   # duplicate identity -> both rejected
        row("KS-B"),
        row("KS-NOUOM", **{"UOM": ""}),
        row("KS-BADDATE", **{"期间": "not-a-date"}),
        row("KS-BADQTY", **{"建议数量": "abc"}),
        [],                                            # interior blank row -> skipped
        row("KS-USTX", **{"仓": "美中USTX"}),
    ]
    snapshot, report = snapshot_of(tmp_path, rows)
    assert report["input_count"] == 7
    assert report["accepted_count"] == 1
    assert report["rejected_count"] == 5
    assert report["skipped_count"] == 1
    assert report["reconciled"] is True
    assert [x["sku"] for x in snapshot["rows"]] == ["KS-B"]
    reasons = {x["reason"] for x in report["rejected"]}
    assert {"duplicate_identity", "missing_uom", "invalid_period", "invalid_number"} <= reasons
    assert {x["reason"] for x in report["skipped"]} == {"outside_usnj_scope"}
    assert all("source_row" in x for x in report["rejected"])


def test_flags_drive_read_only_filters(tmp_path):
    rows = [
        row("KS-DECIDE", **{"需拍板": "是", "置信度": "低", "C": ""}),
        row("KS-SPECIAL", **{"特殊品": "是", "置信度": "0.3", "E": ""}),
        row("KS-CLEAR", **{"置信度": "高"}),
    ]
    snapshot, report = snapshot_of(tmp_path, rows)
    by_sku = {item["sku"]: item for item in snapshot["rows"]}
    assert by_sku["KS-DECIDE"]["needs_decision"] is True
    assert by_sku["KS-DECIDE"]["low_confidence"] is True
    assert by_sku["KS-DECIDE"]["missing_supply"] is True
    assert by_sku["KS-SPECIAL"]["special"] is True
    assert by_sku["KS-SPECIAL"]["low_confidence"] is True
    assert by_sku["KS-SPECIAL"]["missing_supply"] is True
    assert by_sku["KS-CLEAR"]["needs_decision"] is False
    assert by_sku["KS-CLEAR"]["low_confidence"] is False
    assert report["flag_counts"] == {"needs_decision": 1, "low_confidence": 2,
                                     "missing_supply": 2, "special": 1}


def test_snapshot_is_immutable_and_idempotent(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row()])
    store = Store(tmp_path / "db.sqlite")
    first = store.set_recommendation_snapshot(snapshot, "alice")
    second = store.set_recommendation_snapshot(snapshot, "alice")
    assert first == second
    assert first["imported_by"] == "alice"
    assert first["imported_at"]
    assert store.recommendation(first["snapshot_id"]) == first
    tampered = dict(snapshot, rows=[dict(snapshot["rows"][0], qty=999)],
                    snapshot_id=snapshot["snapshot_id"])
    with pytest.raises(DomainError) as exc:
        store.set_recommendation_snapshot(tampered, "alice")
    assert exc.value.status_code == 409
    ineligible = dict(snapshot, service_certified=True)
    with pytest.raises(DomainError):
        store.set_recommendation_snapshot(ineligible, "alice")
    bad_row = {key: value for key, value in snapshot.items()
               if key not in ("snapshot_id", "sha256", "imported_at", "imported_by")}
    bad_row["rows"] = [dict(bad_row["rows"][0], replenishment_eligible=True)]
    with pytest.raises(DomainError):
        store.set_recommendation_snapshot(bad_row, "alice")


def test_loading_snapshot_never_changes_d5_baseline(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row()])
    store = Store(tmp_path / "db.sqlite")
    baseline = {"version": "d5-test", "as_of": "2026-11-11", "demo": True, "rows": [
        {"id": "a", "product_id": "KS1", "sku": "TT1", "name": "靠枕", "branch": "USNJ",
         "unit": "件", "week": "2026-11-16", "baseline_qty": 100}]}
    store.set_baseline(baseline)
    before = store.state()["baseline"]
    store.set_recommendation_snapshot(snapshot, "alice")
    after = store.state()
    assert after["baseline"] == before
    assert after["recommendation"]["snapshot_id"] == snapshot["snapshot_id"]
    assert store.state()["audit"][-1]["action"] == "recommendation_snapshot_loaded"
    # The recommendation snapshot never enters the D5 publication rows.
    publication = store.publish("d5-test", "2026-11-12", "manager", "reviewer")
    assert [item["id"] for item in publication["rows"]] == ["a"]
    assert publication["service_certified"] is False
    assert publication["rows"][0]["replenishment_eligible"] is False


def test_workbench_recommendation_is_read_only_and_identity_is_server_owned(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row("KS-READONLY"), row("KS-SECOND")])
    scope_file = tmp_path / "scope.json"
    scope_file.write_text('{"assignments":[{"user":"alice","sku":"*","branch":"USNJ"}]}', encoding="utf-8")
    client = TestClient(create_app(tmp_path / "work.db", actor="alice", role="operator",
                                   scope_path=scope_file))
    store = client.app.state.store
    store.set_recommendation_snapshot(snapshot, "alice")
    state = client.get("/api/state", headers={"X-Actor": "boss", "X-Role": "reviewer"}).json()
    assert (state["actor"], state["role"]) == ("alice", "operator")
    assert state["baseline"] is None
    assert state["recommendation"]["accepted_count"] == 2
    assert state["recommendation"]["service_certified"] is False
    assert state["recommendation"]["replenishment_eligible"] is False
    assert client.get("/api/recommendations").json()["snapshot_id"] == snapshot["snapshot_id"]
    assert client.get(f"/api/recommendations/{snapshot['snapshot_id']}").status_code == 200
    assert client.get("/api/recommendations/missing").status_code == 404
    for method in ("post", "put", "patch", "delete"):
        assert client.request(method, "/api/recommendations", json={}).status_code == 405
    # A recommendation row is not a D5 baseline row and cannot enter the proposal queue.
    response = client.post("/api/proposals", json={
        "id": "p1", "row_id": snapshot["rows"][0]["row_id"], "event_id": "e1", "kind": "delta",
        "value": 1, "start": "2026-11-16", "end": "2026-11-22", "reason": "越权尝试",
        "evidence": "test", "baseline_version": "none"})
    assert response.status_code in (409, 422)


def test_reviewer_also_has_no_recommendation_write_path(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row()])
    client = TestClient(create_app(tmp_path / "work.db", actor="reviewer", role="reviewer"))
    client.app.state.store.set_recommendation_snapshot(snapshot, "reviewer")
    assert client.get("/api/recommendations").status_code == 200
    assert client.post("/api/recommendations", json={}).status_code == 405
    # Publish/proposal endpoints remain bound to D5, not the recommendation snapshot.
    assert client.post("/api/publish", json={"baseline_version": snapshot["snapshot_id"],
                                             "as_of": "2026-11-12"}).status_code == 409


def test_period_column_variants_are_strict(tmp_path):
    rows = [
        row("KS-STARTEND", **{"期间": ""}),
        row("KS-WEEK", **{"期间": ""}),
    ]
    path = tmp_path / "periods.csv"
    headers = HEAD + ["期间开始", "期间结束", "周"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        first = row("KS-STARTEND", **{"期间": ""}) + ["2026-11-20", "2026-11-30", ""]
        second = row("KS-WEEK", **{"期间": ""}) + ["", "", "2026-11-16"]
        writer.writerow(first)
        writer.writerow(second)
    snapshot, report = build_snapshot(path, "2026-11-12")
    assert report["accepted_count"] == 2
    by_sku = {item["sku"]: item for item in snapshot["rows"]}
    assert (by_sku["KS-STARTEND"]["period_start"], by_sku["KS-STARTEND"]["period_end"]) == (
        "2026-11-20", "2026-11-30")
    assert (by_sku["KS-WEEK"]["period_start"], by_sku["KS-WEEK"]["period_end"]) == (
        "2026-11-16", "2026-11-22")


def test_period_with_explicit_horizon_days(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row("KS-HORIZON", **{"期间": "2026-11-16 起 7 天"})])
    item = snapshot["rows"][0]
    assert (item["period_start"], item["period_end"], item["period_basis"]) == (
        "2026-11-16", "2026-11-22", "period_start_horizon")


def test_missing_required_headers_fail_closed(tmp_path):
    path = write_csv(tmp_path, [row()], headers=["SKU", "期间", "建议动作"])
    with pytest.raises(DomainError) as exc:
        build_snapshot(path, "2026-11-12")
    assert exc.value.code == "missing_columns"


REAL_PILOT = Path("D:/Work/fzh-order-store/analysis/usnj_replenishment_pilot_20261112/USNJ补货建议.csv")


@pytest.mark.skipif(not REAL_PILOT.exists(), reason="real USNJ pilot CSV is not available on this machine")
def test_real_pilot_snapshot_matches_known_release_296():
    snapshot, report = build_snapshot(REAL_PILOT, "2026-11-13",
                                      period_start="2026-11-13", period_end="2027-02-17")
    assert report["reconciled"] is True
    assert (report["accepted_count"], report["rejected_count"],
            report["skipped_count"]) == (296, 0, 0)
    assert report["input_count"] == 296
    assert snapshot["accepted_count"] == len(snapshot["rows"]) == 296
    assert snapshot["service_certified"] is False
    assert snapshot["replenishment_eligible"] is False


@pytest.mark.parametrize("bad", ["1e3", "10-20", "123abc"])
def test_malformed_numbers_are_rejected_not_prefix_parsed(tmp_path, bad):
    path = write_csv(tmp_path, [row("KS-BAD", **{"建议数量": bad})])
    snapshot, report = build_snapshot(path, "2026-11-12",
                                      period_start="2026-11-12", period_end="2027-02-17")
    assert report["accepted_count"] == 0
    assert report["rejected_count"] == 1
    assert report["rejected"][0]["reason"] == "invalid_number"
    assert snapshot["rows"] == []


def test_period_is_required_when_source_has_no_period_column(tmp_path):
    path = write_csv(tmp_path, [row("KS-NOPERIOD")], headers=[h for h in HEAD if h != "期间"])
    with pytest.raises(DomainError) as exc:
        build_snapshot(path, "2026-11-12")
    assert exc.value.code == "missing_columns"


def test_local_page_contains_readonly_usnj_tab(tmp_path):
    client = TestClient(create_app(tmp_path / "page.db", actor="alice", role="operator"))
    html = client.get("/").text
    assert "USNJ 补货建议" in html
    assert "只读" in html and "不可下单" in html


def test_recommendation_scope_default_deny_and_reviewer_all(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row("KS-A"), row("KS-B")])
    db = tmp_path / "scope.db"
    app = create_app(db, actor="alice", role="operator")
    app.state.store.set_recommendation_snapshot(snapshot, "alice")
    client = TestClient(app)
    assert client.get("/api/state").json()["recommendation"]["visible_count"] == 0
    assert client.get("/api/recommendations").json()["visible_count"] == 0
    assert client.get(f"/api/recommendations/{snapshot['snapshot_id']}").status_code == 403

    scope_file = tmp_path / "scope.json"
    scope_file.write_text('{"assignments":[{"user":"alice","sku":"KS-A","branch":"USNJ"}]}',
                          encoding="utf-8")
    scoped = TestClient(create_app(db, actor="alice", role="operator", scope_path=scope_file))
    view = scoped.get("/api/recommendations").json()
    assert view["visible_count"] == 1
    assert [r["sku"] for r in view["rows"]] == ["KS-A"]
    assert view["accepted_count"] == 2  # original snapshot count is not rewritten

    reviewer = TestClient(create_app(db, actor="boss", role="reviewer"))
    assert reviewer.get("/api/recommendations").json()["visible_count"] == 2


def test_scope_string_false_and_invalid_are_denied(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row("KS-A")])
    db = tmp_path / "inactive.db"
    app = create_app(db, actor="alice", role="operator")
    app.state.store.set_recommendation_snapshot(snapshot, "alice")
    scope_file = tmp_path / "scope.json"
    scope_file.write_text('{"assignments":[{"user":"alice","sku":"*","branch":"USNJ",'
                          '"active":"false","valid":"false"}]}', encoding="utf-8")
    client = TestClient(create_app(db, actor="alice", role="operator", scope_path=scope_file))
    assert client.get("/api/recommendations").json()["visible_count"] == 0


def test_scope_hides_rejected_and_skipped_diagnostics(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row("KS-A")])
    snapshot = dict(snapshot, rejected=[{"sku": "SECRET", "reason": "duplicate_identity"}],
                    skipped=[{"sku": "SECRET2", "reason": "outside_usnj_scope"}])
    scope_file = tmp_path / "scope.json"
    scope_file.write_text('{"assignments":[{"user":"alice","sku":"KS-A","branch":"USNJ"}]}',
                          encoding="utf-8")
    view = filter_snapshot(snapshot, "alice", "operator", scope_file)
    assert view["visible_count"] == 1
    assert view["rejected"] == [] and view["skipped"] == []


def test_ownership_pending_rows_visible_to_usnj_assignee(tmp_path):
    snapshot, _ = snapshot_of(tmp_path, [row("KS-PENDING", **{"客户": ""})])
    scope_file = tmp_path / "scope.json"
    scope_file.write_text('{"assignments":[{"user":"jing","sku":"*","branch":"USNJ"}]}',
                          encoding="utf-8")
    view = filter_snapshot(snapshot, "jing", "operator", scope_file)
    assert view["visible_count"] == 1
    assert view["rows"][0]["ownership_pending"] is True


def test_coverage_header_sets_days_unit(tmp_path):
    base = dict(zip(HEAD, row("KS-COVER")))
    headers = [h for h in HEAD if h != "覆盖"] + ["可覆盖天数"]
    values = [base[h] for h in headers[:-1]] + ["45"]
    path = write_csv(tmp_path, [values], headers=headers)
    snapshot, _ = build_snapshot(path, "2026-11-12",
                                 period_start="2026-11-12", period_end="2027-02-17")
    assert snapshot["rows"][0]["coverage"] == 45
    assert snapshot["rows"][0]["coverage_unit"] == "days"


def w1_line(sku="KS0001", customer="美东CENTRADE", qty=10, delivered=0,
            transaction_date="2026-06-01", delivery_date="2026-07-01",
            status="To Deliver", docstatus=1):
    return {"item_code": sku, "customer": customer, "qty": qty,
            "delivered_qty": delivered, "transaction_date": transaction_date,
            "delivery_date": delivery_date, "so_status": status,
            "so_docstatus": docstatus, "so_line": "1", "warehouse": "美东-FZH-CENTRADE",
            "stage": "in_production"}


def write_w1(tmp_path, records):
    path = tmp_path / "supply_facts_raw.jsonl"
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
                    encoding="utf-8")
    return path


def w1_record(so, lines):
    return {"so": so, "payload": {"as_of": "2026-11-13", "lines": lines}}


def test_so_evidence_splits_recent_history_and_unknown_without_loss(tmp_path):
    from demand_collaboration.so_evidence import load as load_so, months_before

    path = write_w1(tmp_path, [
        w1_record("SO-RECENT", [w1_line(qty=10, delivered=2,
                                       transaction_date="2026-05-13",
                                       delivery_date="2026-05-01")]),
        w1_record("SO-HISTORY", [w1_line(qty=4, transaction_date="2026-05-12",
                                        delivery_date="2026-08-01")]),
        w1_record("SO-UNKNOWN", [w1_line(qty=6, transaction_date="")]),
        w1_record("SO-CLOSED", [w1_line(qty=99, status="Closed")]),
        w1_record("SO-DONE", [w1_line(qty=5, delivered=5)]),
        w1_record("SO-ZERO", [w1_line(qty=1, delivered=2)]),
    ])
    evidence = load_so(path, "2026-11-13")
    summary = evidence[("KS0001", "USNJ")]
    assert summary["so_window_start"] == "2026-05-13"
    assert summary["so_open_qty"] == 18
    assert summary["so_open_orders"] == 3
    assert summary["so_recent_open_qty"] == 8
    assert summary["so_recent_open_orders"] == 1
    assert summary["so_history_open_qty"] == 4
    assert summary["so_history_open_orders"] == 1
    assert summary["so_unknown_date_open_qty"] == 6
    assert summary["so_unknown_date_open_orders"] == 1
    assert [line["date_bucket"] for line in summary["so_lines"]] == [
        "recent", "history", "unknown"]
    recent = summary["so_lines"][0]
    assert recent["transaction_date"] == "2026-05-13"
    assert recent["delivery_date"] == "2026-05-01"
    assert recent["qty"] == 10 and recent["delivered"] == 2 and recent["open_qty"] == 8
    assert recent["overdue_days"] == 196
    assert months_before("2026-11-13").isoformat() == "2026-05-13"


def test_so_evidence_month_end_window_is_clamped(tmp_path):
    from demand_collaboration.so_evidence import months_before

    assert months_before("2026-08-31").isoformat() == "2026-02-28"


def test_snapshot_keeps_old_open_so_as_history(tmp_path):
    w1 = write_w1(tmp_path, [w1_record("SO-OLD", [
        w1_line(qty=7, transaction_date="2025-12-01", delivery_date="2026-01-01")])])
    snapshot, _ = build_snapshot(write_csv(tmp_path, [row("KS0001")]), "2026-11-13",
                                 period_start="2026-11-13", period_end="2027-02-17",
                                 so_evidence=w1)
    item = snapshot["rows"][0]
    assert item["so_history_open_qty"] == 7
    assert item["so_history_open_orders"] == 1
    assert item["so_recent_open_qty"] == 0
    assert item["so_has_history"] is True
    assert item["so_window_start"] == "2026-05-13"
    assert item["so_lines"][0]["date_bucket"] == "history"
    assert snapshot["so_window_start"] == "2026-05-13"
    assert snapshot["so_history_retained"] is True


REAL_W1 = Path("D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")


@pytest.mark.skipif(not REAL_W1.exists(), reason="real W1 SO evidence is not available on this machine")
def test_real_w1_buckets_conserve_every_open_line():
    from demand_collaboration.so_evidence import load as load_so

    evidence = load_so(REAL_W1, "2026-11-13")
    assert evidence
    for summary in evidence.values():
        total = (summary["so_recent_open_qty"] + summary["so_history_open_qty"]
                 + summary["so_unknown_date_open_qty"])
        assert total == pytest.approx(summary["so_open_qty"])
        assert len(summary["so_lines"]) >= 1
        assert all(line["date_bucket"] in {"recent", "history", "unknown"}
                   for line in summary["so_lines"])
