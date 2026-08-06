"""Tests for auto-releasing stuck label operations on re-creation."""

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
    _ready_repo,
)


def _ready_pkg(repo: PackageRepository, sn: str) -> int:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test", address_line_1="1 Main", city="Newark",
                state_or_region="NJ", postal_code="07101",
                country_code="US", phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(warehouse_name="CENTRADE"),
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main", package_sn=sn, local_review_status="approved"
    )
    pid = repo.get_package_db_id("sellfox-main", sn)
    assert pid is not None
    repo.upsert_package_dims(
        package_db_id=pid, weight_kg=2, length_cm=30, width_cm=20, height_cm=10, sku_count=1
    )
    return pid


def _claim_to(repo: PackageRepository, package_id: int, sn: str, status: str, i: int) -> int:
    op = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key=f"auto-{sn}-{i}",
        request_hash=f"hash-{sn}-{i}",
        actor="operator",
    )
    if status == "LABEL_PENDING":
        repo.transition_label_operation(op.id, status="SENT")
        repo.transition_label_operation(
            op.id, status="ACCEPTED", provider_order_id=f"ORDER-{sn}"
        )
        repo.transition_label_operation(op.id, status="LABEL_PENDING")
    elif status == "ACCEPTED":
        repo.transition_label_operation(op.id, status="SENT")
        repo.transition_label_operation(op.id, status="ACCEPTED", provider_order_id=f"ORDER-{sn}")
    elif status == "UNKNOWN_BLOCKED":
        repo.transition_label_operation(op.id, status="SENT")
        repo.transition_label_operation(op.id, status="UNKNOWN_BLOCKED", error_class="ambiguous")
    return op.id


def test_release_active_label_operation_releases_pending(tmp_path: Path) -> None:
    """LABEL_PENDING / ACCEPTED are auto-released; UNKNOWN_BLOCKED is not."""
    repo = PackageRepository(tmp_path / "shipping.db")
    pid_pending = _ready_pkg(repo, "P-REL-PEND")
    pid_accepted = _ready_pkg(repo, "P-REL-ACC")
    pid_unknown = _ready_pkg(repo, "P-REL-UNK")

    op_pending = _claim_to(repo, pid_pending, "P-REL-PEND", "LABEL_PENDING", 0)
    op_accepted = _claim_to(repo, pid_accepted, "P-REL-ACC", "ACCEPTED", 0)
    op_unknown = _claim_to(repo, pid_unknown, "P-REL-UNK", "UNKNOWN_BLOCKED", 0)

    released_pending = repo.release_active_label_operation(pid_pending, actor="operator")
    released_accepted = repo.release_active_label_operation(pid_accepted, actor="operator")
    released_unknown = repo.release_active_label_operation(pid_unknown, actor="operator")

    assert released_pending == 1
    assert released_accepted == 1
    assert released_unknown == 0
    assert repo.get_label_operation(op_pending).status == "CANCELLED"
    assert repo.get_label_operation(op_accepted).status == "CANCELLED"
    assert repo.get_label_operation(op_unknown).status == "UNKNOWN_BLOCKED"


def test_create_label_auto_releases_stuck_pending_and_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    """A second create_label call auto-releases a stuck LABEL_PENDING and succeeds."""
    repo, package = _ready_repo(tmp_path)
    package_id = repo.get_package_db_id("sellfox-main", "P-SAFE-1")
    assert package_id is not None

    # Simulate a stuck LABEL_PENDING operation
    op = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="stuck-1",
        request_hash="hash-stuck",
        actor="operator",
    )
    repo.transition_label_operation(op.id, status="SENT")
    repo.transition_label_operation(
        op.id, status="ACCEPTED", provider_order_id="ORDER-STUCK"
    )
    repo.transition_label_operation(op.id, status="LABEL_PENDING")

    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG
    calls = {"count": 0}

    def fake_vite_create(**kwargs):
        calls["count"] += 1
        return {
            "id": 99,
            "tracking_number": "TRK-NEW",
            "carrier_order_id": "ORDER-NEW",
            "label_url": "https://example.invalid/new.pdf",
            "artifact_id": None,
            "status": "generated",
            "total_amount": 4.2,
            "carrier": "vite",
            "service_level": "GOFO_PARCEL",
        }

    monkeypatch.setattr(service, "_create_vite_label", fake_vite_create)

    result = service.create_label(
        package=package,
        account_key="sellfox-main",
        carrier="vite",
        actor="operator",
        service_level="GOFO_PARCEL",
    )

    assert calls["count"] == 1
    assert result["tracking_number"] == "TRK-NEW"
    # Stuck op was released, a fresh one succeeded
    ops = repo.list_label_operations(package_sn="P-SAFE-1")
    assert any(o.status == "CANCELLED" for o in ops)
    assert any(o.status == "SUCCEEDED" for o in ops)


def test_create_label_blocks_when_valid_label_exists(tmp_path: Path) -> None:
    """A valid active label blocks duplicate creation (no auto-release)."""
    repo, package = _ready_repo(tmp_path)
    package_id = repo.get_package_db_id("sellfox-main", "P-SAFE-1")
    assert package_id is not None

    # Create a valid label
    repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRK-EXISTING",
        carrier_order_id="ORDER-EXISTING",
        request_id="",
        label_url="https://example.invalid/e.pdf",
        artifact_id=None,
        total_amount=4.2,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
        operation_id=None,
    )

    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    with pytest.raises(LabelServiceError, match="已存在有效面单"):
        service.create_label(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
            service_level="GOFO_PARCEL",
        )


def test_lizard_reference_suffix_by_generation(tmp_path: Path) -> None:
    """Generation 1 uses base reference; later generations append -N suffix."""
    from sellfox_shipping.label_service import LabelService
    repo = PackageRepository(tmp_path / "shipping.db")
    service = LabelService(repo)

    assert service._lizard_reference_no("P2B7A9T733766", None) == "P2B7A9T733766"

    pid = _ready_pkg(repo, "P-REF1")
    op1 = _claim_to(repo, pid, "P-REF1", "LABEL_PENDING", 0)
    # op1 generation is 1 → base reference
    assert service._lizard_reference_no("P-REF1", op1) == "P-REF1"

    # Release op1 and claim a second op → generation 2 → -1 suffix
    repo.release_active_label_operation(pid, actor="operator")
    op2 = _claim_to(repo, pid, "P-REF1", "LABEL_PENDING", 1)
    assert service._lizard_reference_no("P-REF1", op2) == "P-REF1-1"


def test_insert_label_stores_derived_reference(tmp_path: Path) -> None:
    """insert_label persists derived_reference_no on the label record."""
    repo = PackageRepository(tmp_path / "shipping.db")
    pid = _ready_pkg(repo, "P-DERIV1")
    label = repo.insert_label(
        account_key="sellfox-main",
        package_db_id=pid,
        carrier="lizard",
        service_level="FedEx-Ground-J-TX",
        tracking_number="1Z-DERIV",
        carrier_order_id="ORD-DERIV",
        request_id="",
        label_url="https://example.invalid/l.pdf",
        artifact_id=None,
        total_amount=10.0,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
        derived_reference_no="P-DERIV1-2",
    )
    assert label.derived_reference_no == "P-DERIV1-2"

    fetched = repo.list_labels_for_package(
        account_key="sellfox-main", package_sn="P-DERIV1"
    )
    assert fetched[0].derived_reference_no == "P-DERIV1-2"
