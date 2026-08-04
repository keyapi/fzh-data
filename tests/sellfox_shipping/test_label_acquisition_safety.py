from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from sellfox_shipping.label_service import LabelService, LabelServiceError
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _package(*, review: str = "approved", warehouse: str = "CENTRADE") -> SellfoxPackageRecord:
    return SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-SAFE-1",
        local_review_status=review,
        address=SellfoxPackageAddress(
            name="Test Buyer",
            address_line_1="1 Main St",
            city="Houston",
            state_or_region="TX",
            postal_code="77001",
            phone="2815550100",
            country_code="US",
        ),
        logistics=SellfoxPackageLogistics(warehouse_name=warehouse),
    )


def _ready_repo(tmp_path, *, review: str = "approved") -> tuple[PackageRepository, SellfoxPackageRecord]:
    repo = PackageRepository(tmp_path / "shipping.db")
    package = _package(review=review)
    repo.upsert(package)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    assert package_id is not None
    repo.upsert_package_dims(
        package_db_id=package_id,
        weight_kg=2,
        length_cm=30,
        width_cm=20,
        height_cm=10,
        sku_count=1,
    )
    return repo, repo.get("sellfox-main", package.package_sn)


def test_preflight_rejects_unapproved_package_before_carrier_call(tmp_path) -> None:
    repo, package = _ready_repo(tmp_path, review="pending")
    service = LabelService(repo)

    with pytest.raises(LabelServiceError, match="approved"):
        service.preflight(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
            service_level="GOFO_PARCEL",
        )

    assert repo.list_label_operations(package_sn=package.package_sn) == []


def test_preflight_rejects_incomplete_vite_warehouse(tmp_path) -> None:
    repo, package = _ready_repo(tmp_path)
    service = LabelService(repo)

    with pytest.raises(LabelServiceError, match="warehouse"):
        service.preflight(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
            service_level="GOFO_PARCEL",
        )


def test_atomic_claim_allows_only_one_active_operation(tmp_path) -> None:
    repo, package = _ready_repo(tmp_path)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    assert package_id is not None
    repositories = [
        PackageRepository(tmp_path / "shipping.db"),
        PackageRepository(tmp_path / "shipping.db"),
    ]

    def claim(local: PackageRepository) -> int:
        return local.claim_label_operation(
            account_key="sellfox-main",
            package_db_id=package_id,
            carrier="vite",
            service_level="GOFO_PARCEL",
            idempotency_key="P-SAFE-1:1",
            request_hash="hash-1",
            actor="operator",
        ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda local: _capture_claim(lambda: claim(local)), repositories))

    assert sum(result[0] for result in results) == 1
    assert len({result[1] for result in results if result[0]}) == 1


def _capture_claim(fn) -> tuple[bool, int | None]:
    try:
        return True, fn()
    except RuntimeError as exc:
        assert "active label operation" in str(exc)
        return False, None


def test_unknown_operation_blocks_new_claim(tmp_path) -> None:
    repo, package = _ready_repo(tmp_path)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    operation = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="P-SAFE-1:1",
        request_hash="hash-1",
        actor="operator",
    )
    repo.transition_label_operation(operation.id, status="UNKNOWN_BLOCKED", error_class="network_unknown")

    with pytest.raises(RuntimeError, match="active label operation"):
        repo.claim_label_operation(
            account_key="sellfox-main",
            package_db_id=package_id,
            carrier="vite",
            service_level="GOFO_PARCEL",
            idempotency_key="P-SAFE-1:2",
            request_hash="hash-2",
            actor="operator",
        )


def test_cancelled_label_releases_active_unique_constraint(tmp_path) -> None:
    repo, package = _ready_repo(tmp_path)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    operation = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="P-SAFE-1:1",
        request_hash="hash-1",
        actor="operator",
    )
    label = repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRACK-1",
        carrier_order_id="ORDER-1",
        request_id="REQ-1",
        label_url="https://example.invalid/label.pdf",
        artifact_id=None,
        total_amount=1,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
        operation_id=operation.id,
    )
    repo.update_label_status(label.id, "cancelled")
    repo.transition_label_operation(operation.id, status="SUCCEEDED")

    replacement = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="FEDEX_GROUND",
        idempotency_key="P-SAFE-1:2",
        request_hash="hash-2",
        actor="operator",
    )
    assert replacement.generation == 2
