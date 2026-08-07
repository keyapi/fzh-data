"""Tests for writing valid label tracking numbers back to Sellfox."""

from __future__ import annotations

from pathlib import Path

import pytest

from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.submission_service import SubmissionService


class _FakeSubmitClient:
    def __init__(self) -> None:
        self.calls = 0
        self.last_wire: dict | None = None

    def submit_to_platform(self, wire_body: dict) -> dict:
        self.calls += 1
        self.last_wire = wire_body
        return {"code": 0, "wire": wire_body}

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        return None


def _seed(repo: PackageRepository, sn: str = "P2ALABEL1") -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
            shop_id="SHOP-1",
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test",
                address_line_1="1 Main",
                city="Newark",
                state_or_region="NJ",
                postal_code="07101",
                country_code="US",
                phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(
                channel_name="蜴国际-FedEx",
                tracking_number="TN-SELLFOX",  # would be the Sellfox-provided one
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORD-1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORD-1",
                    order_item_id="ITEM-1",
                    seller_sku="SKU-A",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main", package_sn=sn, local_review_status="approved"
    )


def _insert_label(
    repo: PackageRepository,
    sn: str = "P2ALABEL1",
    *,
    tracking: str = "1Z-LABEL-TRACK",
    carrier: str = "lizard",
    status: str = "generated",
) -> None:
    package_id = repo.get_package_db_id("sellfox-main", sn)
    assert package_id is not None
    repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier=carrier,
        service_level="FedEx-Ground-J-TX",
        tracking_number=tracking,
        carrier_order_id="M6180-1",
        request_id="",
        label_url="https://example.invalid/l.pdf",
        artifact_id=None,
        total_amount=12.0,
        currency="USD",
        status=status,
        carrier_response_json="{}",
        created_by="operator",
        operation_id=None,
    )


def test_prepare_uses_explicit_tracking_override(tmp_path: Path) -> None:
    """tracking_number param overrides the Sellfox logistics tracking."""
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, "P2AOVR1")
    svc = SubmissionService(repo)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2AOVR1",
        actor="ops",
        carrier_name="lizard",
        tracking_number="1Z-EXPLICIT",
    )
    assert prepared.intent_ids
    intent = repo.get_submission_intent(prepared.intent_ids[0])
    assert intent is not None
    assert "1Z-EXPLICIT" in intent.canonical_request


def test_submit_label_tracking_no_valid_label(tmp_path: Path) -> None:
    """Package without a valid non-cancelled label raises LookupError."""
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, "P2ANONE1")
    svc = SubmissionService(repo)
    with pytest.raises(LookupError, match="no valid label"):
        svc.submit_label_tracking(
            account_key="sellfox-main", package_sn="P2ANONE1", actor="ops"
        )


def test_submit_label_tracking_cancelled_label_ignored(tmp_path: Path) -> None:
    """A cancelled label with a tracking number is not used."""
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, "P2ACANCEL1")
    _insert_label(repo, "P2ACANCEL1", status="cancelled")
    svc = SubmissionService(repo)
    with pytest.raises(LookupError, match="no valid label"):
        svc.submit_label_tracking(
            account_key="sellfox-main", package_sn="P2ACANCEL1", actor="ops"
        )


def test_submit_label_tracking_uses_label_tracking_and_submits(
    tmp_path: Path,
) -> None:
    """submit_label_tracking uses label tracking and calls submitToPlatform."""
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, "P2ASUB1")
    _insert_label(repo, "P2ASUB1", tracking="1Z-LABEL-TRACK", carrier="lizard")
    client = _FakeSubmitClient()
    svc = SubmissionService(repo, client)

    result = svc.submit_label_tracking(
        account_key="sellfox-main", package_sn="P2ASUB1", actor="ops"
    )

    assert result.tracking_number == "1Z-LABEL-TRACK"
    assert result.carrier_name == "lizard"
    assert result.http_called is True
    assert client.calls >= 1
    assert client.last_wire is not None
    assert client.last_wire["trackNo"] == "1Z-LABEL-TRACK"
    assert client.last_wire["carrierName"] == "lizard"


def test_submit_label_tracking_wire_body_shape(tmp_path: Path) -> None:
    """Wire body matches Sellfox submitToPlatform expectations."""
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, "P2AWIRE1")
    _insert_label(repo, "P2AWIRE1", tracking="1Z-WIRE", carrier="vite")
    client = _FakeSubmitClient()
    svc = SubmissionService(repo, client)

    svc.submit_label_tracking(
        account_key="sellfox-main", package_sn="P2AWIRE1", actor="ops"
    )

    wire = client.last_wire
    assert wire is not None
    assert set(wire.keys()) >= {"shopId", "orderId", "trackNo", "carrierName", "items"}
    assert wire["trackNo"] == "1Z-WIRE"
    assert wire["carrierName"] == "vite"
    assert isinstance(wire["items"], list)
    assert wire["items"][0]["orderItemId"] == "ITEM-1"
    # Official schema declares quantity as string (0 < qty < 999999)
    assert wire["items"][0]["quantity"] == "1"


def test_direct_sellfox_client_submit_to_platform(monkeypatch) -> None:
    """DirectSellfoxClient.submit_to_platform POSTs to the right endpoint."""
    from sellfox_shipping.direct_sellfox_client import DirectSellfoxClient

    client = DirectSellfoxClient(
        app_id="test-app", app_secret="test-secret", api_domain="https://openapi.sellfox.com"
    )
    captured = {}

    def _fake_post(path: str, body: dict) -> dict:
        captured["path"] = path
        captured["body"] = body
        return {"code": 0, "data": {"ok": True}}

    monkeypatch.setattr(client, "_post", _fake_post)
    wire = {"trackNo": "1Z-DIRECT", "orderId": "ORD-1"}
    result = client.submit_to_platform(wire)

    assert result["code"] == 0
    assert captured["path"] == "/api/packageShip/submitToPlatform.json"
    assert captured["body"] == wire


class _FakeResp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return {}


class _FakeHttpClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    def post(self, *args, **kwargs):
        return self._resp


def test_direct_client_ensure_http_ok_surfaces_error_body() -> None:
    """DirectSellfoxClient surfaces the Sellfox error body on 4xx."""
    from sellfox_shipping.direct_sellfox_client import DirectSellfoxClient

    fake = _FakeResp(400, '{"code":40014,"msg":"参数异常"}')
    with pytest.raises(RuntimeError) as ei:
        DirectSellfoxClient._ensure_http_ok("/api/x.json", fake)
    assert "400" in str(ei.value)
    assert "参数异常" in str(ei.value)


def test_proxy_client_post_raises_with_error_body() -> None:
    """SellfoxClient._post includes the proxy/Sellfox error body on 4xx."""
    from sellfox_shipping.sellfox_client import SellfoxClient

    fake = _FakeResp(400, '{"code":40014,"msg":"参数异常"}')
    client = SellfoxClient(
        proxy_base_url="https://proxy.example",
        proxy_account="acc",
        proxy_api_key="key",
        http_client=_FakeHttpClient(fake),  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError) as ei:
        client._post("/api/x.json", {})
    assert "400" in str(ei.value)
    assert "参数异常" in str(ei.value)
