"""Regression tests for the Lizard ratesv2 ca_zone request contract."""

from __future__ import annotations

from sellfox_shipping import app as app_module
from sellfox_shipping.carriers.lizard import api_client as lizard_api_module
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


class _FakeLizardClient:
    captured_body: dict | None = None
    rates_response: dict = {}

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> "_FakeLizardClient":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def ratesv2(self, body: dict) -> dict:
        _FakeLizardClient.captured_body = body
        return self.rates_response


def _seed_package(tmp_path, monkeypatch, warehouse_name: str) -> PackageRepository:
    repo = PackageRepository(tmp_path / "shipping.db")
    account = app_module.config["sellfox"]["proxy_account"]
    repo.upsert(
        SellfoxPackageRecord(
            account_key=account,
            package_sn="P2ARATE001",
            package_status="to_process",
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test Buyer",
                address_line_1="1 Main St",
                city="Newark",
                state_or_region="NJ",
                postal_code="07101",
                country_code="US",
                phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(
                channel_name="lizard-FedEx",
                warehouse_name=warehouse_name,
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="O1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O1",
                    order_item_id="I1",
                    seller_sku="SKU-A",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key=account, package_sn="P2ARATE001", local_review_status="approved"
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repo)
    monkeypatch.setenv("YIGLOBAL_APP_TOKEN", "test-token")
    monkeypatch.setenv("YIGLOBAL_APP_KEY", "test-key")
    return repo


def _fake_rates_response() -> dict:
    return {
        "result": {
            "SM-EXPENSIVE": {
                "total_charge": "25.00",
                "currency_code": "USD",
                "charge_weight": 3.0,
                "zone": "1",
                "address_type_text": "residential",
            },
            "SM-CHEAP": {
                "total_charge": "12.50",
                "currency_code": "USD",
                "charge_weight": 3.0,
                "zone": "1",
                "address_type_text": "residential",
            },
        }
    }


def test_lizard_rate_uses_global_ca_zone_and_s0143_shipper(
    tmp_path, monkeypatch
) -> None:
    repo = _seed_package(tmp_path, monkeypatch, warehouse_name="CENTRADE")
    fake = _FakeLizardClient()
    fake.rates_response = _fake_rates_response()
    monkeypatch.setattr(lizard_api_module, "LizardApiClient", lambda **kw: fake)

    record = repo.get(app_module.config["sellfox"]["proxy_account"], "P2ARATE001")
    assert record is not None
    package_dims = {"weight_kg": 2.0, "length_cm": 30, "width_cm": 20, "height_cm": 10}

    best = app_module._get_lizard_rate(record, package_dims)

    assert best is not None
    assert best["service"] == "SM-CHEAP"
    assert best["total_amount"] == 12.5

    body = _FakeLizardClient.captured_body
    assert body is not None
    assert body["ca_zone"] == 0
    shipper = body["shipper_address"]
    assert shipper["shipper_postal_code"] == "77099"
    assert shipper["shipper_state_province"] == "TX"
    assert shipper["shipper_city"] == "Houston"

    db_id = repo.get_package_db_id(
        app_module.config["sellfox"]["proxy_account"], "P2ARATE001"
    )
    history = repo.list_package_rates(db_id, limit=10)
    assert {row.service for row in history} == {"SM-EXPENSIVE", "SM-CHEAP"}


def test_lizard_rate_empty_result_returns_explicit_error(
    tmp_path, monkeypatch
) -> None:
    repo = _seed_package(tmp_path, monkeypatch, warehouse_name="DANEEY")
    fake = _FakeLizardClient()
    fake.rates_response = {"result": {}}
    monkeypatch.setattr(lizard_api_module, "LizardApiClient", lambda **kw: fake)

    record = repo.get(app_module.config["sellfox"]["proxy_account"], "P2ARATE001")
    assert record is not None
    package_dims = {"weight_kg": 2.0, "length_cm": 30, "width_cm": 20, "height_cm": 10}

    result = app_module._get_lizard_rate(record, package_dims)
    assert result is not None
    assert result.get("error") == "No rates returned from Lizard API"
    assert _FakeLizardClient.captured_body["ca_zone"] == 0
