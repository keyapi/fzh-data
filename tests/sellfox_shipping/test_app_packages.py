from __future__ import annotations

from fastapi.testclient import TestClient

from sellfox_shipping import app as app_module
from sellfox_shipping.package_models import (
    PackageListItem,
    PackageListResult,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def test_list_packages_api_returns_json_summaries(tmp_path, monkeypatch) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    repository.upsert(
        SellfoxPackageRecord(
            account_key=app_module.config["sellfox"]["proxy_account"],
            package_sn="P10001",
            package_status="to_audit",
            logistics=SellfoxPackageLogistics(channel_name="蜴国际"),
            orders=[SellfoxPackageOrderRecord(external_order_id="O-1")],
        )
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)

    response = TestClient(app_module.app).get(
        "/api/packages",
        params={"status": "to_audit", "channel": "蜴国际"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["package_sn"] == "P10001"
    assert payload["items"][0]["order_count"] == 1


def test_get_package_api_returns_full_record(tmp_path, monkeypatch) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    repository.upsert(
        SellfoxPackageRecord(
            account_key=app_module.config["sellfox"]["proxy_account"],
            package_sn="P10002",
            package_status="to_process",
            orders=[SellfoxPackageOrderRecord(external_order_id="O-2")],
        )
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)

    response = TestClient(app_module.app).get("/api/packages/P10002")

    assert response.status_code == 200
    payload = response.json()
    assert payload["package_sn"] == "P10002"
    assert payload["orders"][0]["external_order_id"] == "O-2"


def test_get_package_api_returns_404_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "_get_package_repository",
        lambda: PackageRepository(tmp_path / "shipping.db"),
    )

    response = TestClient(app_module.app).get("/api/packages/MISSING")

    assert response.status_code == 404
