from __future__ import annotations

from fastapi.testclient import TestClient

from sellfox_shipping import app as app_module
from sellfox_shipping.carriers.lizard.dims import StaticDimsLookup
from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
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
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O-1",
                    order_item_id="I1",
                    seller_sku="S1",
                    commodity_sku="KS-SEED-1",
                    quantity=1,
                )
            ],
        )
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)
    monkeypatch.setattr(
        app_module,
        "_get_lizard_dims_lookup",
        lambda: StaticDimsLookup({}),
    )
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
    assert "重尺补录" in response.text


def test_package_detail_page_returns_404_html_for_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "_get_package_repository",
        lambda: PackageRepository(tmp_path / "shipping.db"),
    )
    monkeypatch.setattr(
        app_module,
        "_get_lizard_dims_lookup",
        lambda: StaticDimsLookup({}),
    )

    response = TestClient(app_module.app).get("/packages/MISSING")

    assert response.status_code == 404


def test_package_carton_override_form_saves(tmp_path, monkeypatch) -> None:
    repo = _seed(tmp_path, monkeypatch, package_sn="P-DIMS-1")
    account = app_module.config["sellfox"]["proxy_account"]

    response = TestClient(app_module.app).post(
        "/packages/P-DIMS-1/carton-override",
        data={
            "commodity_sku": "KS-SEED-1",
            "weight_kg": "3.5",
            "length_cm": "40",
            "width_cm": "30",
            "height_cm": "20",
            "actor": "web-tester",
            "note": "tape measure",
        },
    )
    assert response.status_code == 200
    assert "已保存重尺补录" in response.text
    saved = repo.get_carton_override(account, "KS-SEED-1")
    assert saved is not None
    assert saved.dims.weight_kg == 3.5
