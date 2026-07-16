from __future__ import annotations

from fastapi.testclient import TestClient

from sellfox_shipping import app as app_module
from sellfox_shipping.package_models import (
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed(tmp_path, monkeypatch, package_sn: str = "P10001") -> PackageRepository:
    repository = PackageRepository(tmp_path / "shipping.db")
    repository.upsert(
        SellfoxPackageRecord(
            account_key=app_module.config["sellfox"]["proxy_account"],
            package_sn=package_sn,
            package_status="to_audit",
            shop_name="如森US",
            logistics=SellfoxPackageLogistics(
                channel_name="蜴国际",
                tracking_number="",
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="O-1")],
        )
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)
    return repository


def test_packages_page_renders_local_summaries(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch)

    response = TestClient(app_module.app).get("/packages", params={"status": "to_audit"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "P10001" in response.text
    assert "蜴国际" in response.text
    assert "to_audit" in response.text


def test_package_detail_page_renders_orders(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, package_sn="P20002")

    response = TestClient(app_module.app).get("/packages/P20002")

    assert response.status_code == 200
    assert "P20002" in response.text
    assert "O-1" in response.text


def test_package_detail_page_returns_404_html_for_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "_get_package_repository",
        lambda: PackageRepository(tmp_path / "shipping.db"),
    )

    response = TestClient(app_module.app).get("/packages/MISSING")

    assert response.status_code == 404
