"""TDD: Lizard API ship = create → poll getLabel → register PDF Artifact."""

from __future__ import annotations

from pathlib import Path

import pytest

from sellfox_shipping.carriers.lizard.api_shipment import (
    LizardApiShipmentService,
    LizardLabelNotReadyError,
)
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _pkg(sn: str = "P-API-001") -> SellfoxPackageRecord:
    return SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn=sn,
        address=SellfoxPackageAddress(
            name="Smoke Test",
            company="FZH",
            address_line_1="10812 Fallstone Rd",
            address_line_2="Suite 100",
            city="Houston",
            state_or_region="TX",
            postal_code="77099",
            country="United States",
            country_code="US",
            phone="2816770938",
            email="ops@example.com",
        ),
        logistics=SellfoxPackageLogistics(
            channel_name="FedEx",
            weight_grams=2000.0,
            length_cm=25.0,
            width_cm=20.0,
            height_cm=15.0,
        ),
        items=[
            SellfoxPackageItemRecord(
                external_order_id="O1",
                order_item_id="I1",
                seller_sku="SKU1",
                commodity_sku="KS0001",
                quantity=1,
                variation="Widget",
            )
        ],
    )


class _FakeLizardClient:
    def __init__(self, *, label_ready_after: int = 1, label_url: str = "https://cdn.example/l.pdf"):
        self.label_ready_after = label_ready_after
        self.label_url = label_url
        self.create_bodies: list[dict] = []
        self.get_label_calls = 0

    def create_order(self, body: dict) -> dict:
        self.create_bodies.append(body)
        return {
            "code": 200,
            "result": {
                "order_code": "OC-99",
                "labels": {"tracking_number": "", "label_url": ""},
            },
        }

    def get_label(self, *, order_code: str = "", reference_no: str = "") -> dict:
        assert order_code == "OC-99"
        assert reference_no == "P-API-001"
        self.get_label_calls += 1
        ready = self.get_label_calls >= self.label_ready_after
        return {
            "code": 200,
            "result": {
                "sync_service_status": 1 if ready else 0,
                "order_status": "Success" if ready else "Pending",
                "labels": {
                    "tracking_number": "1ZTEST" if ready else "",
                    "label_url": self.label_url if ready else "",
                },
            },
        }


def test_ship_create_poll_registers_label_artifact(tmp_path: Path):
    repo = PackageRepository(tmp_path / "shipping.db")
    client = _FakeLizardClient(label_ready_after=1)
    pdf = b"%PDF-1.4 fake-label"

    def fetch_bytes(url: str) -> bytes:
        assert url == "https://cdn.example/l.pdf"
        return pdf

    sleeps: list[float] = []
    svc = LizardApiShipmentService(
        client,
        repo,
        fetch_bytes=fetch_bytes,
        sleep=sleeps.append,
    )
    result = svc.ship_package(
        _pkg(),
        account_key="sellfox-main",
        actor="ops-api",
        sm_code="FedEx-Ground-J-TX",
        shipper_code="S0143",
        poll_interval_s=0.5,
        poll_timeout_s=10,
    )

    assert client.create_bodies[0]["reference_no"] == "P-API-001"
    assert result.order_code == "OC-99"
    assert result.tracking_number == "1ZTEST"
    assert result.artifact_id > 0
    assert result.poll_count == 1
    assert sleeps == []  # ready on first poll — no wait
    art = repo.get_artifact(result.artifact_id)
    assert art is not None
    assert art.kind == "lizard_api_label"
    assert art.created_by == "ops-api"
    blob = Path(repo.artifacts_root) / art.storage_relpath
    assert blob.read_bytes() == pdf


def test_ship_polls_until_label_ready(tmp_path: Path):
    repo = PackageRepository(tmp_path / "shipping.db")
    client = _FakeLizardClient(label_ready_after=3)
    sleeps: list[float] = []
    svc = LizardApiShipmentService(
        client,
        repo,
        fetch_bytes=lambda url: b"%PDF-x",
        sleep=sleeps.append,
    )
    result = svc.ship_package(
        _pkg(),
        account_key="sellfox-main",
        actor="ops",
        sm_code="FedEx-Ground-J-TX",
        poll_interval_s=1.0,
        poll_timeout_s=60,
    )
    assert result.poll_count == 3
    assert sleeps == [1.0, 1.0]


def test_ship_timeout_raises_without_artifact(tmp_path: Path):
    repo = PackageRepository(tmp_path / "shipping.db")
    client = _FakeLizardClient(label_ready_after=99)
    clock = {"t": 0.0}

    def monotonic() -> float:
        return clock["t"]

    def sleep(sec: float) -> None:
        clock["t"] += sec

    svc = LizardApiShipmentService(
        client,
        repo,
        fetch_bytes=lambda url: b"%PDF",
        sleep=sleep,
        monotonic=monotonic,
    )
    with pytest.raises(LizardLabelNotReadyError, match="P-API-001"):
        svc.ship_package(
            _pkg(),
            account_key="sellfox-main",
            actor="ops",
            sm_code="FedEx-Ground-J-TX",
            poll_interval_s=5.0,
            poll_timeout_s=12.0,
        )
    assert repo.list_artifacts(account_key="sellfox-main") == []


class _ErrorLizardClient:
    """getLabel immediately reports a business error (e.g. duplicate reference)."""

    def __init__(self):
        self.get_label_calls = 0

    def create_order(self, body: dict) -> dict:
        return {
            "code": 200,
            "result": {"order_code": "OC-ERR", "labels": {}},
        }

    def get_label(self, *, order_code: str = "", reference_no: str = "") -> dict:
        self.get_label_calls += 1
        return {
            "code": 202,
            "result": {
                "sync_service_status": 2,
                "order_status": 1,
                "logistics_err": "订单状态异常-[code] 400, [message] 参考号重复",
            },
        }


def test_ship_polls_only_once_when_logistics_err_present(tmp_path: Path):
    """An order in error state surfaces the carrier message instead of polling to timeout."""
    from sellfox_shipping.carriers.lizard.api_client import LizardApiError

    repo = PackageRepository(tmp_path / "shipping.db")
    client = _ErrorLizardClient()
    svc = LizardApiShipmentService(client, repo)

    with pytest.raises(LizardApiError, match="参考号重复"):
        svc.ship_package(
            _pkg("P-API-ERR"),
            account_key="sellfox-main",
            actor="ops",
            sm_code="FedEx-Ground-J-TX",
            poll_interval_s=5.0,
            poll_timeout_s=120.0,
        )
    # Should fail fast, not spin 120s
    assert client.get_label_calls == 1
