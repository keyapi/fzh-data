from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from demand_collaboration.core import DomainError, Store


def baseline(version="v1"):
    return {"version": version, "as_of": "2026-11-11", "demo": True, "rows": [
        {"id": "a", "product_id": "KS1", "sku": "TT1", "name": "靠枕", "branch": "PL",
         "unit": "件", "week": "2026-11-16", "baseline_qty": 100, "history": [10, 20],
         "inventory_qty": 40, "supply_note": "供给待核"}]}


def proposal(id="p1", **kw):
    return dict({"id": id, "row_id": "a", "event_id": "promo1", "kind": "delta", "value": 30,
                 "start": "2026-11-16", "end": "2026-11-22", "reason": "促销", "evidence": "计划文档#1",
                 "baseline_version": "v1"}, **kw)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "demand.sqlite")
    s.set_baseline(baseline())
    return s


def approve(s, p="p1", revision=1):
    return s.decide(p, "approved", revision, "manager", "reviewer", "核实活动")


def test_freeze_baseline_and_hash_identity(store):
    b = baseline()
    store.set_baseline(b)
    b["rows"][0]["baseline_qty"] = 200
    with pytest.raises(DomainError) as e:
        store.set_baseline(b)
    assert e.value.status_code == 409
    assert store.state()["baseline"]["rows"][0]["baseline_qty"] == 100


def test_idempotent_submission_does_not_duplicate_or_change_author(store):
    first = store.submit(proposal(), "alice")
    assert store.submit(proposal(), "alice") == first
    with pytest.raises(DomainError):
        store.submit(proposal(), "bob")
    with pytest.raises(DomainError):
        store.submit(proposal(value=40), "alice")
    assert len(store.state()["proposals"]) == 1


@pytest.mark.parametrize("payload", [proposal(value=float("nan")), proposal(value=float("inf")),
    proposal(kind="total", value=-1), proposal(kind="percent", value=-101), proposal(value=True),
    proposal(start="2026-11-17"), proposal(end="2026-11-23"), proposal(reason=""),
    proposal(evidence=""), proposal(row_id="unknown"), proposal(baseline_version="v0"),
    proposal(kind="nonsense")])
def test_invalid_input_fails_closed(store, payload):
    with pytest.raises(DomainError):
        store.submit(payload, "alice")
    assert not store.state()["proposals"]


def test_roles_self_approval_and_revision(store):
    store.submit(proposal(), "alice")
    with pytest.raises(DomainError):
        store.decide("p1", "approved", 1, "alice", "reviewer", "ok")
    with pytest.raises(DomainError):
        store.decide("p1", "approved", 1, "bob", "operator", "ok")
    p = approve(store)
    assert p["revision"] == 2
    with pytest.raises(DomainError):
        store.decide("p1", "cancelled", 1, "manager", "reviewer", "取消")


def test_overlap_blocks_approval_and_unresolved_blocks_publish(store):
    store.submit(proposal(), "alice")
    store.submit(proposal("p2", event_id="other", kind="total", value=150), "bob")
    approve(store)
    with pytest.raises(DomainError):
        approve(store, "p2")
    with pytest.raises(DomainError):
        store.publish("v1", "2026-11-11", "manager", "reviewer")
    store.decide("p2", "rejected", 1, "manager", "reviewer", "重复覆盖")
    pub = store.publish("v1", "2026-11-11", "manager", "reviewer")
    assert pub["rows"][0]["adjusted_qty"] == 130
    assert pub["rows"][0]["proposal_ids"] == ["p1"]
    assert pub["service_certified"] is False
    assert store.state()["baseline"]["rows"][0]["baseline_qty"] == 100
    assert store.publication(pub["id"]) == pub


@pytest.mark.parametrize("kind,value,expected", [("delta",30,130),("total",130,130),("percent",20,120)])
def test_semantics(store,kind,value,expected):
    store.submit(proposal(kind=kind,value=value),"alice")
    approve(store)
    assert store.publish("v1","2026-11-11","manager","reviewer")["rows"][0]["adjusted_qty"] == expected


def test_event_only_and_negative_result_are_not_numeric_approval(store):
    store.submit(proposal(kind="event_only",value=None),"alice")
    with pytest.raises(DomainError):
        approve(store)
    store.decide("p1","rejected",1,"manager","reviewer","影响待估")
    store.submit(proposal("p2",value=-101),"alice")
    with pytest.raises(DomainError):
        approve(store,"p2")


def test_cancellation_expiration_and_new_version_do_not_carry_old_approval(store):
    store.submit(proposal(),"alice")
    approve(store)
    expired = store.publish("v1","2026-11-23","manager","reviewer")
    assert expired["rows"][0]["expired"] is True
    assert expired["rows"][0]["adjusted_qty"] == 100
    store.decide("p1","cancelled",2,"manager","reviewer","活动取消")
    assert store.publish("v1","2026-11-11","manager","reviewer")["rows"][0]["adjusted_qty"] == 100
    store.set_baseline(baseline("v2"))
    with pytest.raises(DomainError):
        store.publish("v1","2026-11-11","manager","reviewer")
    assert store.publish("v2","2026-11-11","manager","reviewer")["rows"][0]["adjusted_qty"] == 100


def test_concurrent_approval_cannot_double_count(store):
    store.submit(proposal(),"alice")
    store.submit(proposal("p2",event_id="promo2"),"bob")
    def attempt(id):
        try:
            approve(store,id)
            return True
        except DomainError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(attempt,["p1","p2"])) == 1


@pytest.mark.parametrize("change", [{"branch":"UNKNOWN"},{"baseline_qty":-1},{"week":"2026-11-17"},{"unit":""},{"baseline_qty":float("inf")}])
def test_invalid_baseline(store,change):
    b = baseline("v2")
    b["rows"][0].update(change)
    with pytest.raises(DomainError):
        store.set_baseline(b)


def test_unknown_fields_are_rejected_and_publication_requires_reviewer(store):
    with pytest.raises(DomainError):
        store.submit(dict(proposal(),author="manager"),"alice")
    with pytest.raises(DomainError):
        store.publish("v1","2026-11-11","alice","operator")


def test_fixed_horizon_preserved_without_fake_weekly_split(store):
    b = baseline("h97")
    b["rows"][0].update(week="2026-11-11", period_end="2027-02-15", physical_form="成品")
    store.set_baseline(b)
    p = proposal(baseline_version="h97",start="2026-11-11",end="2027-02-15")
    store.submit(p,"alice")
    approve(store)
    pub = store.publish("h97","2026-11-11","manager","reviewer")
    assert pub["rows"][0]["adjusted_qty"] == 130
    assert pub["rows"][0]["period_end"] == "2027-02-15"
    assert "exact_source_periods_only" in pub["assumptions"]
    assert store.publish("h97","2027-02-16","manager","reviewer")["rows"][0]["expired"]


def test_overlap_horizons_rejected_same_target_but_forms_independent(store):
    b = baseline("overlap")
    b["rows"][0]["period_end"] = "2027-02-15"
    b["rows"].append(dict(b["rows"][0],id="b",period_end="2027-04-16"))
    with pytest.raises(DomainError) as e:
        store.set_baseline(b)
    assert e.value.code == "overlapping_horizons"
    b["rows"][1]["physical_form"] = "皮壳"
    store.set_baseline(b)


def test_fixed_horizon_rejects_wrong_end_and_bad_date(store):
    b = baseline("bad")
    b["rows"][0]["period_end"] = "2026-11-15"
    with pytest.raises(DomainError):
        store.set_baseline(b)


def test_publication_explicitly_labels_full_period_not_remaining_demand(store):
    b = baseline("h97")
    b["rows"][0].update(week="2026-11-11",period_end="2027-02-15")
    store.set_baseline(b)
    pub = store.publish("h97","2026-11-20","manager","reviewer")
    row = pub["rows"][0]
    assert row["period_state"] == "in_progress"
    assert row["quantity_scope"] == "entire_source_period"
    assert row["adjusted_qty"] == 100
    assert row["needs_remaining_period_forecast"] is True
    assert row["replenishment_eligible"] is False


def test_subperiod_event_only_can_be_recorded_but_never_numerically_approved(store):
    b=baseline("h97")
    b["rows"][0].update(week="2026-11-11",period_end="2027-02-15")
    store.set_baseline(b)
    p=proposal(kind="event_only",value=None,baseline_version="h97",start="2026-11-23",end="2026-11-29")
    assert store.submit(p,"alice")["status"] == "submitted"
    with pytest.raises(DomainError):
        approve(store)
    with pytest.raises(DomainError):
        store.publish("h97","2026-11-11","manager","reviewer")
    with pytest.raises(DomainError):
        store.submit(dict(p,id="p2",start="2026-11-10"),"alice")
    with pytest.raises(DomainError):
        store.submit(dict(p,id="p3",kind="delta",value=30),"alice")


def test_enrichment_fields_and_context_are_accepted(store):
    b=baseline("v2")
    b["rows"][0].update(tongtong_sku="TT1", en_item_code="KS1",
                        context={"inventory_as_of":"2026-11-10","supply_as_of":"2026-11-10"})
    store.set_baseline(b)
    row=store.state()["baseline"]["rows"][0]
    assert row["tongtong_sku"]=="TT1" and row["en_item_code"]=="KS1"
    assert row["context"]["inventory_as_of"]=="2026-11-10"


def test_invalid_context_fails_closed(store):
    b=baseline("v3"); b["rows"][0]["context"]=[1,2]
    with pytest.raises(DomainError):
        store.set_baseline(b)


def test_baseline_as_of_cannot_regress(store):
    b=baseline("v2"); b["as_of"]="2026-11-10"
    with pytest.raises(DomainError) as e:
        store.set_baseline(b)
    assert e.value.code == "baseline_as_of_regression"
