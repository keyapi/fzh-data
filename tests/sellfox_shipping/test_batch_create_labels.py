"""Tests for the batch create labels endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sellfox_shipping import app as app_module
from sellfox_shipping.label_service import LabelServiceError
from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed(
    tmp_path, monkeypatch, *sns: str
) -> PackageRepository:
    repository = PackageRepository(tmp_path / "shipping.db")
    for sn in sns:
        repository.upsert(
            SellfoxPackageRecord(
                account_key=app_module.config["sellfox"]["proxy_account"],
                package_sn=sn,
                package_status="to_audit",
                shop_name="如森US",
                logistics=SellfoxPackageLogistics(channel_name="蜴国际"),
                orders=[SellfoxPackageOrderRecord(external_order_id=f"O-{sn}")],
                items=[
                    SellfoxPackageItemRecord(
                        external_order_id=f"O-{sn}",
                        order_item_id="I1",
                        seller_sku="S1",
                        commodity_sku="KS-SEED-1",
                        quantity=1,
                    )
                ],
            )
        )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)
    return repository


def test_batch_create_labels_success(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, "P2ABATCH1", "P2ABATCH2")

    calls = []

    def _fake_routing(record, carton_rows):
        return type("R", (), {"carrier": "lizard", "matched": True})()

    def _fake_create_label(self, *, carrier, package, account_key, actor, **kw):
        calls.append((carrier, package.package_sn))
        return {
            "tracking_number": f"TRK-{package.package_sn}",
            "carrier_order_id": f"ORD-{package.package_sn}",
            "status": "generated",
        }

    monkeypatch.setattr(app_module, "_compute_routing", _fake_routing)
    monkeypatch.setattr(
        "sellfox_shipping.label_service.LabelService", lambda repo: type("S", (), {
            "create_label": _fake_create_label
        })()
    )

    resp = TestClient(app_module.app).post("/api/packages/batch-create-labels", json={
        "package_sns": ["P2ABATCH1", "P2ABATCH2"],
        "carrier": "auto",
        "actor": "ops",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] == 2
    assert data["failed"] == 0
    assert len(data["results"]) == 2
    assert data["results"][0]["tracking_number"] == "TRK-P2ABATCH1"
    assert calls == [("lizard", "P2ABATCH1"), ("lizard", "P2ABATCH2")]


def test_batch_create_labels_explicit_carrier(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, "P2ABATCH3")
    calls = []

    def _fake_create_label(self, *, carrier, package, account_key, actor, **kw):
        calls.append(carrier)
        return {"tracking_number": "TRK-3", "carrier_order_id": "ORD-3", "status": "generated"}

    monkeypatch.setattr(
        "sellfox_shipping.label_service.LabelService", lambda repo: type("S", (), {
            "create_label": _fake_create_label
        })()
    )

    resp = TestClient(app_module.app).post("/api/packages/batch-create-labels", json={
        "package_sns": ["P2ABATCH3"],
        "carrier": "vite",
        "actor": "ops",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] == 1
    assert calls == ["vite"]


def test_batch_create_labels_partial_failure(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, "P2ABATCH4", "P2ABATCH5")

    def _fake_create_label(self, *, carrier, package, account_key, actor, **kw):
        if package.package_sn == "P2ABATCH4":
            raise LabelServiceError("preflight failed")
        return {"tracking_number": "TRK-5", "carrier_order_id": "ORD-5", "status": "generated"}

    monkeypatch.setattr(
        "sellfox_shipping.label_service.LabelService", lambda repo: type("S", (), {
            "create_label": _fake_create_label
        })()
    )

    resp = TestClient(app_module.app).post("/api/packages/batch-create-labels", json={
        "package_sns": ["P2ABATCH4", "P2ABATCH5"],
        "carrier": "lizard",
        "actor": "ops",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] == 1
    assert data["failed"] == 1
    failed = [r for r in data["results"] if not r["ok"]]
    assert failed[0]["package_sn"] == "P2ABATCH4"
    assert "preflight failed" in failed[0]["error"]


def test_batch_create_labels_auto_no_routing(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, "P2ABATCH6")

    def _fake_routing(record, carton_rows):
        return type("R", (), {"carrier": "", "matched": False})()

    monkeypatch.setattr(app_module, "_compute_routing", _fake_routing)

    resp = TestClient(app_module.app).post("/api/packages/batch-create-labels", json={
        "package_sns": ["P2ABATCH6"],
        "carrier": "auto",
        "actor": "ops",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] == 1
    assert "无路由建议承运商" in data["results"][0]["error"]


def test_batch_create_labels_empty_sns(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, "P2ABATCH7")
    resp = TestClient(app_module.app).post("/api/packages/batch-create-labels", json={
        "package_sns": [], "carrier": "auto", "actor": "ops"
    })
    assert resp.status_code == 400
