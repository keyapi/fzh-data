"""Tests for UNKNOWN_BLOCKED resolution CLI."""

from __future__ import annotations

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


def _ready_unknown_blocked(tmp_path, *, provider_order_id=""):
    repo = PackageRepository(tmp_path / "shipping.db")
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-UNK-1",
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
        idempotency_key="unk-1",
        request_hash="hash-unk",
        actor="operator",
    )
    repo.transition_label_operation(op.id, status="SENT")
    repo.transition_label_operation(
        op.id,
        status="UNKNOWN_BLOCKED",
        provider_order_id=provider_order_id,
        error_class="transport",
        error_summary="connection reset",
    )
    return repo, package, op.id


# ── Reject non-UNKNOWN_BLOCKED ───────────────────────────────


def test_resolve_rejects_non_unknown_blocked(tmp_path):
    from tests.sellfox_shipping.test_label_operation_resume import _ready_repo_with_op
    repo, _package, op_id = _ready_repo_with_op(tmp_path, status="ACCEPTED")
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="only UNKNOWN_BLOCKED"):
        service.resolve_unknown_blocked(
            op_id, resolution="fail_safe", confirm="fail_safe", actor="operator"
        )


def test_resolve_rejects_missing_confirm_match(tmp_path):
    repo, _package, op_id = _ready_unknown_blocked(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="confirm"):
        service.resolve_unknown_blocked(
            op_id, resolution="fail_safe", confirm="wrong", actor="operator"
        )


# ── fail_safe: carrier confirmed NOT created ──────────────────


def test_resolve_fail_safe_frees_slot_for_new_generation(tmp_path):
    repo, _package, op_id = _ready_unknown_blocked(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    result = service.resolve_unknown_blocked(
        op_id,
        resolution="fail_safe",
        confirm="fail_safe",
        note="checked VITE portal: no order created",
        actor="operator",
    )

    assert result["status"] == "FAILED_SAFE"
    op = repo.get_label_operation(op_id)
    assert op.status == "FAILED_SAFE"
    assert "no order created" in (op.error_summary or "")

    # Should allow a new generation
    package_id = repo.get_package_db_id("sellfox-main", "P-UNK-1")
    new_op = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="unk-gen2",
        request_hash="hash-gen2",
        actor="operator",
    )
    assert new_op.generation == 2


# ── fail_final: confirmed final rejection ─────────────────────


def test_resolve_fail_final_permanent_rejection(tmp_path):
    repo, _package, op_id = _ready_unknown_blocked(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    result = service.resolve_unknown_blocked(
        op_id,
        resolution="fail_final",
        confirm="fail_final",
        note="carrier confirmed: invalid address, no retry",
        actor="operator",
    )

    assert result["status"] == "FAILED_FINAL"
    op = repo.get_label_operation(op_id)
    assert op.status == "FAILED_FINAL"


# ── provide_known_id: human found order on carrier portal ────


def test_resolve_provide_known_id_enables_resume(tmp_path):
    repo, _package, op_id = _ready_unknown_blocked(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    result = service.resolve_unknown_blocked(
        op_id,
        resolution="provide_known_id",
        confirm="provide_known_id",
        provider_order_id="ORDER-FOUND-ON-PORTAL",
        note="found in VITE dashboard, tracking=1Z9999",
        actor="operator",
    )

    assert result["status"] == "ACCEPTED"
    op = repo.get_label_operation(op_id)
    assert op.status == "ACCEPTED"
    assert op.provider_order_id == "ORDER-FOUND-ON-PORTAL"


def test_resolve_provide_known_id_requires_provider_order_id(tmp_path):
    repo, _package, op_id = _ready_unknown_blocked(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="provider_order_id is required"):
        service.resolve_unknown_blocked(
            op_id,
            resolution="provide_known_id",
            confirm="provide_known_id",
            provider_order_id="",
            actor="operator",
        )


# ── CLI smoke ────────────────────────────────────────────────


def test_cli_resolve_bad_operation_id(tmp_path):
    from typer.testing import CliRunner
    from sellfox_shipping.cli import app
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "label-operation-resolve",
            "--operation-id", "99999",
            "--resolution", "fail_safe",
            "--confirm", "fail_safe",
        ],
    )
    assert result.exit_code != 0


def test_cli_resolve_succeeds(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from sellfox_shipping.cli import app
    from sellfox_shipping.label_service import LabelService

    repo, _package, op_id = _ready_unknown_blocked(tmp_path)
    monkeypatch.setattr(
        "sellfox_shipping.cli._get_label_service",
        lambda: LabelService(repo),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "label-operation-resolve",
            "--operation-id", str(op_id),
            "--resolution", "fail_safe",
            "--confirm", "fail_safe",
            "--note", "checked via CLI",
        ],
    )
    assert result.exit_code == 0
    assert "FAILED_SAFE" in result.output
