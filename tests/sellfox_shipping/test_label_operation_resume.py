"""Tests for label-operation-resume CLI and LabelService.resume_label_acquisition."""

from __future__ import annotations

from pathlib import Path

import pytest

from sellfox_shipping.label_service import LabelService, LabelServiceError
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from tests.sellfox_shipping.test_label_acquisition_safety import (
    COMPLETE_WAREHOUSE_CFG,
)


def _ready_repo_with_op(tmp_path, *, status="ACCEPTED", provider_order_id="ORDER-1"):
    repo = PackageRepository(tmp_path / "shipping.db")
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-RESUME-1",
        local_review_status="approved",
        address=SellfoxPackageAddress(
            name="Test Buyer",
            address_line_1="1 Main St",
            city="Houston",
            state_or_region="TX",
            postal_code="77001",
            phone="2815550100",
            country_code="US",
        ),
        logistics=SellfoxPackageLogistics(
            warehouse_name="CENTRADE",
            weight_grams=2000.0,
            length_cm=30.0,
            width_cm=20.0,
            height_cm=10.0,
        ),
    )
    repo.upsert(package)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    assert package_id is not None
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn=package.package_sn,
        local_review_status="approved",
    )
    repo.upsert_package_dims(
        package_db_id=package_id,
        weight_kg=2,
        length_cm=30,
        width_cm=20,
        height_cm=10,
        sku_count=1,
    )
    op = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="resume-1",
        request_hash="hash-resume",
        actor="operator",
    )
    if status != "RESERVED":
        repo.transition_label_operation(op.id, status="SENT")
    repo.transition_label_operation(
        op.id, status=status, provider_order_id=provider_order_id
    )
    return repo, package, op.id


class _FakeViteResumeClient:
    def __init__(self, *, label_ready=True, label_url="https://cdn.example/v.pdf", tracking="9400111"):
        self.label_ready = label_ready
        self.label_url = label_url
        self.tracking = tracking
        self.get_label_calls = 0
        self.create_calls = 0

    def create_shipment_gofo(self, body):
        self.create_calls += 1
        raise AssertionError("create must not be called during resume")

    def create_shipment_fedex(self, body):
        return self.create_shipment_gofo(body)

    def get_label(self, order_id):
        self.get_label_calls += 1
        if not self.label_ready:
            return [{"status": "PENDING", "trackingNumber": "", "url": ""}]
        return [{"status": "OK", "trackingNumber": self.tracking, "url": self.label_url}]


# ── Unit tests for resume validation ──────────────────────────


def test_resume_rejects_non_accepted_status(tmp_path):
    repo, _package, op_id = _ready_repo_with_op(tmp_path, status="FAILED_SAFE")
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="cannot resume operation"):
        service.resume_label_acquisition(op_id, actor="operator")


def test_resume_rejects_missing_provider_order_id(tmp_path):
    repo, _package, op_id = _ready_repo_with_op(tmp_path, status="ACCEPTED", provider_order_id="")
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="missing provider_order_id"):
        service.resume_label_acquisition(op_id, actor="operator")


def test_resume_rejects_succeeded_status(tmp_path):
    repo, _package, op_id = _ready_repo_with_op(tmp_path, status="SUCCEEDED")
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="cannot resume operation"):
        service.resume_label_acquisition(op_id, actor="operator")


# ── Integration: resume succeeds ─────────────────────────────


def test_resume_vite_retrieves_label_and_transitions_to_succeeded(tmp_path, monkeypatch):
    from sellfox_shipping.carriers.vite.client import ViteGofoClient
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, op_id = _ready_repo_with_op(tmp_path)

    client = _FakeViteResumeClient()


    monkeypatch.setattr(ViteGofoClient, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(ViteGofoClient, "__enter__", lambda self: client)
    monkeypatch.setattr(ViteGofoClient, "__exit__", lambda *a: False)
    monkeypatch.setenv("VITE_API_KEY", "test-key")
    monkeypatch.setattr(
        "sellfox_shipping.label_service._default_fetch_bytes",
        lambda url: b"%PDF-1.4",
    )

    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    result = service.resume_label_acquisition(op_id, actor="operator")

    assert result["status"] == "SUCCEEDED"
    assert result["provider_order_id"] == "ORDER-1"
    op = repo.get_label_operation(op_id)
    assert op.status == "SUCCEEDED"
    assert client.create_calls == 0
    assert client.get_label_calls > 0


def test_resume_vite_label_not_ready_stays_label_pending(tmp_path, monkeypatch):
    from sellfox_shipping.carriers.vite.client import ViteGofoClient
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, op_id = _ready_repo_with_op(tmp_path)

    client = _FakeViteResumeClient(label_ready=False)


    monkeypatch.setattr(ViteGofoClient, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(ViteGofoClient, "__enter__", lambda self: client)
    monkeypatch.setattr(ViteGofoClient, "__exit__", lambda *a: False)
    monkeypatch.setenv("VITE_API_KEY", "test-key")
    monkeypatch.setattr(
        "sellfox_shipping.label_service._default_fetch_bytes",
        lambda url: b"%PDF-1.4",
    )

    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="PENDING"):
        service.resume_label_acquisition(op_id, actor="operator")

    op = repo.get_label_operation(op_id)
    assert op.status == "LABEL_PENDING"
    assert op.provider_order_id == "ORDER-1"
    assert client.create_calls == 0


# ── CLI smoke test ───────────────────────────────────────────


def test_cli_resume_bad_operation_id(tmp_path):
    from typer.testing import CliRunner
    from sellfox_shipping.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["label-operation-resume", "--operation-id", "99999"])
    assert result.exit_code != 0
