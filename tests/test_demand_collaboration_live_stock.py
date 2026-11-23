import csv
import json

import pytest
from fastapi.testclient import TestClient

from demand_collaboration.core import Store
from demand_collaboration.live_stock import (SCHEMA, LiveStockError, LiveStockSource,
                                             attach_to_snapshot, build_overlay,
                                             validate_run)
from demand_collaboration.recommendation import build_snapshot
from demand_collaboration.web import create_app


@pytest.fixture
def credential_sources(monkeypatch, tmp_path):
    from demand_collaboration import live_stock
    for name in ('ERP_API_KEY', 'ERP_API_SECRET', 'PROD_ERP_API_KEY',
                 'PROD_ERP_API_SECRET', 'DEMAND_LIVE_STOCK_ENV'):
        monkeypatch.delenv(name, raising=False)
    default = tmp_path / 'EN_API' / '.env'
    default.parent.mkdir()
    monkeypatch.setattr(live_stock, 'DEFAULT_ENV_FILE', str(default))
    return live_stock, default


def test_credentials_process_environment_is_portable(credential_sources, monkeypatch):
    module, _ = credential_sources
    monkeypatch.setenv('ERP_API_KEY', 'ek')
    monkeypatch.setenv('ERP_API_SECRET', 'es')
    assert module.credentials() == ('ek', 'es')


def test_credentials_explicit_file_precedes_process(credential_sources, monkeypatch, tmp_path):
    module, _ = credential_sources
    explicit = tmp_path / 'selected.env'
    explicit.write_text('ERP_API_KEY=fk\nERP_API_SECRET=fs\n', encoding='utf-8')
    monkeypatch.setenv('ERP_API_KEY', 'ek')
    monkeypatch.setenv('ERP_API_SECRET', 'es')
    assert module.credentials(explicit) == ('fk', 'fs')


def test_credentials_process_precedes_repo_default(credential_sources, monkeypatch):
    module, default = credential_sources
    default.write_text('ERP_API_KEY=fk\nERP_API_SECRET=fs\n', encoding='utf-8')
    monkeypatch.setenv('ERP_API_KEY', 'ek')
    monkeypatch.setenv('ERP_API_SECRET', 'es')
    assert module.credentials() == ('ek', 'es')


def test_credentials_partial_source_does_not_mix_or_leak(credential_sources, monkeypatch):
    module, default = credential_sources
    default.write_text('ERP_API_KEY=fk\nERP_API_SECRET=fs\n', encoding='utf-8')
    monkeypatch.setenv('ERP_API_KEY', 'sensitive-test-value')
    with pytest.raises(LiveStockError) as error:
        module.credentials()
    assert 'sensitive-test-value' not in str(error.value)


def test_credentials_partial_explicit_file_refuses_fallback(credential_sources, monkeypatch, tmp_path):
    module, _ = credential_sources
    explicit = tmp_path / 'incomplete.env'
    explicit.write_text('ERP_API_KEY=fk\n', encoding='utf-8')
    monkeypatch.setenv('ERP_API_KEY', 'ek')
    monkeypatch.setenv('ERP_API_SECRET', 'es')
    with pytest.raises(LiveStockError):
        module.credentials(explicit)


def test_credentials_default_file_and_legacy_production_names(credential_sources):
    module, default = credential_sources
    default.write_text('PROD_ERP_API_KEY=pk\nPROD_ERP_API_SECRET=ps\n', encoding='utf-8')
    assert module.credentials() == ('pk', 'ps')


def test_credentials_explicit_missing_file_is_not_ignored(credential_sources, monkeypatch, tmp_path):
    module, _ = credential_sources
    monkeypatch.setenv('ERP_API_KEY', 'ek')
    monkeypatch.setenv('ERP_API_SECRET', 'es')
    with pytest.raises(LiveStockError):
        module.credentials(tmp_path / 'absent.env')

RUN = {"job": "stock_snapshot", "status": "Success", "complete": 1,
       "run_id": "run-1", "snapshot_at": "2026-11-13T05:00:00",
       "snapshot_date": "2026-11-13", "row_count": 1}


def stock_row(sku="KS1", warehouse="W1", available=13, intransit=5,
              waiting_shipment=4, defects=1, name="row-1"):
    return {"name": name, "sku": sku, "warehouse": warehouse, "warehouse_id": "w1",
            "available": available, "intransit": intransit,
            "waiting_shipment": waiting_shipment, "defects": defects,
            "snapshot_at": RUN["snapshot_at"], "run_id": RUN["run_id"]}


def overlay(rows=None, **extra):
    payload = {"schema": SCHEMA, "source": "en_tongtool_stock_latest", "status": "ok",
               "stale": False, "run_id": RUN["run_id"],
               "snapshot_at": RUN["snapshot_at"], "snapshot_date": RUN["snapshot_date"],
               "row_count": len(rows or []), "fetched_at": "2026-11-13T06:00:00",
               "rows": rows or []}
    payload.update(extra)
    return payload


def view():
    return {"rows": [
        {"sku": "KS1", "warehouse": "W1", "c_qty": 10, "e_qty": 2},
        {"sku": "KS2", "warehouse": "W1", "c_qty": 0, "e_qty": 0},
    ]}


def test_build_overlay_preserves_unknown_and_explicit_zero():
    rows = [stock_row(available="", intransit=3, waiting_shipment=None, defects=0)]
    out = build_overlay(rows, dict(RUN, row_count=1))
    item = out["rows"][0]
    assert item["available"] is None
    assert item["intransit"] == 3
    assert item["waiting_shipment"] is None
    assert item["defects"] == 0


def test_build_overlay_aggregates_duplicates_only_when_all_known():
    rows = [stock_row(available=2, name="a"), stock_row(available=3, name="b")]
    out = build_overlay(rows, dict(RUN, row_count=2))
    assert out["rows"][0]["available"] == 5
    assert out["rows"][0]["duplicate_rows"] == 2

    rows = [stock_row(available=2, name="a"), stock_row(available="", name="b")]
    out = build_overlay(rows, dict(RUN, row_count=2))
    assert out["rows"][0]["available"] is None


def test_attach_matches_by_sku_and_warehouse_and_computes_deltas():
    original = view()
    out = attach_to_snapshot(original, overlay([stock_row()]))
    matched, unmatched = out["rows"]
    assert matched["live_stock"]["status"] == "matched"
    assert matched["live_stock"]["available"] == 13
    assert matched["live_stock"]["available_delta_vs_snapshot"] == 3
    assert matched["live_stock"]["intransit_delta_vs_snapshot"] == 3
    assert matched["live_stock"]["waiting_shipment"] == 4
    assert matched["live_stock"]["defects"] == 1
    assert unmatched["live_stock"]["status"] == "not_found"
    assert "available" not in unmatched["live_stock"]
    assert out["live_stock"]["run_id"] == "run-1"
    assert out["live_stock"]["snapshot_at"] == RUN["snapshot_at"]
    assert (out["live_stock"]["matched_count"], out["live_stock"]["unmatched_count"]) == (1, 1)
    # The stored view is never mutated by decoration.
    assert "live_stock" not in original["rows"][0]
    assert "live_stock" not in original


def test_unavailable_overlay_never_zero_fills():
    out = attach_to_snapshot(view(), {"schema": SCHEMA, "status": "unavailable",
                                      "stale": True, "error": "EN down", "rows": []})
    assert out["live_stock"]["status"] == "unavailable"
    assert out["rows"][0]["live_stock"] is None


def test_source_falls_back_to_stale_cache(tmp_path):
    cache = tmp_path / "live.json"
    cache.write_text(json.dumps(overlay([stock_row()])), encoding="utf-8")

    def boom():
        raise LiveStockError("EN unreachable")

    source = LiveStockSource(cache_path=str(cache), ttl_seconds=0, fetcher=boom)
    out = source.get(force=True)
    assert out["status"] == "fallback_stale"
    assert out["stale"] is True
    assert "EN unreachable" in out["fallback_reason"]
    assert out["rows"][0]["sku"] == "KS1"


def test_source_without_cache_marks_unavailable(tmp_path):
    def boom():
        raise LiveStockError("EN unreachable")

    source = LiveStockSource(cache_path=str(tmp_path / "missing.json"), ttl_seconds=0,
                             fetcher=boom)
    out = source.get(force=True)
    assert out["status"] == "unavailable"
    assert out["stale"] is True
    assert "EN unreachable" in out["error"]
    assert attach_to_snapshot(view(), out)["rows"][0]["live_stock"] is None


def test_source_writes_cache_after_successful_fetch(tmp_path):
    cache = tmp_path / "live.json"
    source = LiveStockSource(cache_path=str(cache), ttl_seconds=0,
                             fetcher=lambda: overlay([stock_row()]))
    out = source.get(force=True)
    assert out["status"] == "ok" and out["stale"] is False
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["schema"] == SCHEMA
    assert saved["run_id"] == "run-1"
    assert saved["rows"][0]["available"] == 13


def test_validate_run_rejects_incomplete_or_missing_identity():
    validate_run(RUN)
    for bad in (dict(RUN, complete=0), dict(RUN, status="Running"),
                dict(RUN, run_id=""), dict(RUN, row_count=-1)):
        with pytest.raises(LiveStockError):
            validate_run(bad)


def write_recommendation(tmp_path):
    path = tmp_path / "rec.csv"
    headers = ["SKU", "客户", "仓", "形态", "UOM", "期间", "建议动作", "建议数量", "C", "E"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerow(["KS1", "Amazon-US", "USNJ", "成品", "件",
                         "2026-11-16 至 2026-11-22", "补", "120", "10", "2"])
    return path


def test_web_decorates_state_but_never_writes_overlay_into_snapshot(tmp_path):
    snapshot, _ = build_snapshot(write_recommendation(tmp_path), "2026-11-13",
                                 period_start="2026-11-13", period_end="2027-02-17")
    client = TestClient(create_app(tmp_path / "work.db", actor="alice", role="reviewer",
                                   live_stock_provider=lambda: overlay([stock_row(warehouse="USNJ")])))
    store: Store = client.app.state.store
    store.set_recommendation_snapshot(snapshot, "alice")
    state = client.get("/api/state").json()
    row = state["recommendation"]["rows"][0]
    assert row["live_stock"]["available"] == 13
    assert state["recommendation"]["live_stock"]["run_id"] == "run-1"
    stored = store.recommendation(snapshot["snapshot_id"])
    assert "live_stock" not in stored["rows"][0]
    assert "live_stock" not in stored


def test_missing_alias_marks_partial_and_hides_total():
    from demand_collaboration.live_stock import attach_to_snapshot
    overlay = {"schema": "en-live-stock-overlay/v1", "status": "ok", "run_id": "r1",
               "snapshot_at": "2026-11-13 05:17:00",
               "rows": [{"sku": "TT-A", "warehouse": "W", "available": 2,
                         "intransit": 0, "waiting_shipment": 0, "defects": 0}]}
    view = {"rows": [{"sku": "EN-X", "tongtool_skus": ["TT-A", "TT-B"], "warehouse": "W"}],
            "accepted_count": 1}
    out = attach_to_snapshot(view, overlay)
    live = out["rows"][0]["live_stock"]
    assert live["partial"] is True
    assert live["missing_alias_count"] == 1
    assert live["available"] is None


def test_unknown_quantity_marks_partial_even_with_all_aliases():
    from demand_collaboration.live_stock import attach_to_snapshot
    overlay = {"schema": "en-live-stock-overlay/v1", "status": "ok", "run_id": "r1",
               "snapshot_at": "2026-11-13 05:17:00",
               "rows": [{"sku": "TT-A", "warehouse": "W", "available": None,
                         "intransit": 0, "waiting_shipment": 0, "defects": 0}]}
    view = {"rows": [{"sku": "EN-X", "tongtool_skus": ["TT-A"], "warehouse": "W"}],
            "accepted_count": 1}
    out = attach_to_snapshot(view, overlay)
    live = out["rows"][0]["live_stock"]
    assert live["partial"] is True
    assert live["available"] is None
