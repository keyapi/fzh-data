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
    assert "商品行" in response.text


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
    assert "已保存" in response.text
    assert "重尺补录" in response.text
    saved = repo.get_carton_override(account, "KS-SEED-1")
    assert saved is not None
    assert saved.dims.weight_kg == 3.5


def test_package_prepare_submit_and_dry_run_web(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    account = app_module.config["sellfox"]["proxy_account"]
    repo.upsert(
        SellfoxPackageRecord(
            account_key=account,
            package_sn="P2AWEBPREP",
            shop_id="SHOP-1",
            local_review_status="approved",
            logistics=SellfoxPackageLogistics(
                channel_name="FedEx",
                tracking_number="TN-WEB-PREP",
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="O-WEB")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O-WEB",
                    order_item_id="I-WEB",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key=account,
        package_sn="P2AWEBPREP",
        local_review_status="approved",
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repo)
    monkeypatch.setattr(
        app_module,
        "_get_lizard_dims_lookup",
        lambda: StaticDimsLookup({}),
    )
    client = TestClient(app_module.app)
    page = client.get("/packages/P2AWEBPREP")
    assert page.status_code == 200
    assert "赛狐回写确认" in page.text

    prepared = client.post(
        "/packages/P2AWEBPREP/prepare-submit",
        data={"actor": "web-tester"},
    )
    assert prepared.status_code == 200
    assert "已准备提交意图" in prepared.text
    assert "TRACKING_REVIEWED" in prepared.text
    intents = repo.list_submission_intents_for_package(
        account_key=account, package_sn="P2AWEBPREP"
    )
    assert len(intents) == 1
    dry = client.post(
        f"/packages/P2AWEBPREP/submit-intent/{intents[0].id}",
        data={"actor": "web-tester"},
    )
    assert dry.status_code == 200
    assert "dry-run OK" in dry.text
    assert "未调用 HTTP" in dry.text
