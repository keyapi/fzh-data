from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from sellfox_shipping.carriers.vite.shipment import _build_ship_from, _build_ship_to
from sellfox_shipping.label_service import LabelService, LabelServiceError
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository

COMPLETE_WAREHOUSE_CFG = {
    "warehouses": {
        "CENTRADE": {
            "address": {
                "name": "FZH USNJ Warehouse",
                "address1": "1 Warehouse Rd",
                "city": "Newark",
                "state": "NJ",
                "postal_code": "07101",
                "phone": "9735550100",
            }
        }
    }
}


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
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn=package.package_sn,
        local_review_status=review,
    )
    repo.upsert_package_dims(
        package_db_id=package_id,
        weight_kg=2,
        length_cm=30,
        width_cm=20,
        height_cm=10,
        sku_count=1,
    )
    return repo, repo.get("sellfox-main", package.package_sn)


def _walk_to_succeeded(repo: PackageRepository, operation_id: int) -> None:
    repo.transition_label_operation(operation_id, status="SENT")
    repo.transition_label_operation(operation_id, status="SUCCEEDED")


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
        assert "active label operation" in str(exc) or "active label exists" in str(exc)
        return False, None


def test_active_label_blocks_new_claim(tmp_path) -> None:
    repo, package = _ready_repo(tmp_path)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    assert package_id is not None
    repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRACK-ACTIVE",
        carrier_order_id="ORDER-ACTIVE",
        request_id="REQ-ACTIVE",
        label_url="https://example.invalid/label.pdf",
        artifact_id=None,
        total_amount=1,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
    )

    with pytest.raises(RuntimeError, match="active label exists"):
        repo.claim_label_operation(
            account_key="sellfox-main",
            package_db_id=package_id,
            carrier="vite",
            service_level="GOFO_PARCEL",
            idempotency_key="P-SAFE-1:1",
            request_hash="hash-1",
            actor="operator",
        )


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
    repo.transition_label_operation(operation.id, status="SENT")
    repo.transition_label_operation(
        operation.id, status="UNKNOWN_BLOCKED", error_class="network_unknown"
    )

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


def test_invalid_transition_is_rejected(tmp_path) -> None:
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

    with pytest.raises(RuntimeError, match="invalid transition"):
        repo.transition_label_operation(operation.id, status="SUCCEEDED")


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
    _walk_to_succeeded(repo, operation.id)
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
    repo.transition_label_operation(operation.id, status="CANCELLED")

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


def test_create_label_wires_preflight_claim_and_succeeds(tmp_path, monkeypatch) -> None:
    repo, package = _ready_repo(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    def fake_vite(**kwargs):
        assert kwargs.get("operation_id") is not None
        package_db_id = kwargs["db_id"]
        label = repo.insert_label(
            account_key="sellfox-main",
            package_db_id=package_db_id,
            carrier="vite",
            service_level="GOFO_PARCEL",
            tracking_number="TRACK-OK",
            carrier_order_id="ORDER-OK",
            request_id="REQ-OK",
            label_url="https://example.invalid/ok.pdf",
            artifact_id=None,
            total_amount=3.5,
            currency="USD",
            status="generated",
            carrier_response_json="{}",
            created_by="operator",
            operation_id=kwargs["operation_id"],
        )
        return {
            "id": label.id,
            "tracking_number": "TRACK-OK",
            "carrier_order_id": "ORDER-OK",
            "label_url": "https://example.invalid/ok.pdf",
            "artifact_id": None,
            "status": "generated",
            "total_amount": 3.5,
            "carrier": "vite",
            "service_level": "GOFO_PARCEL",
        }

    monkeypatch.setattr(service, "_create_vite_label", fake_vite)
    result = service.create_label(
        package=package,
        account_key="sellfox-main",
        carrier="vite",
        actor="operator",
        service_level="GOFO_PARCEL",
    )

    assert result["tracking_number"] == "TRACK-OK"
    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "SUCCEEDED"
    assert ops[0].tracking_number == "TRACK-OK"
    labels = repo.list_labels_for_package(account_key="sellfox-main", package_sn=package.package_sn)
    assert labels[0].operation_id == ops[0].id
    assert labels[0].is_active is True


def test_create_label_marks_unknown_blocked_on_ambiguous_carrier_error(
    tmp_path, monkeypatch
) -> None:
    repo, package = _ready_repo(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    def fake_vite(**kwargs):
        raise LabelServiceError("VITE API error: connection reset", http_status=502)

    monkeypatch.setattr(service, "_create_vite_label", fake_vite)

    with pytest.raises(LabelServiceError, match="connection reset"):
        service.create_label(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
            service_level="GOFO_PARCEL",
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "UNKNOWN_BLOCKED"

    with pytest.raises(LabelServiceError, match="active label operation"):
        service.create_label(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
            service_level="GOFO_PARCEL",
        )


def test_build_ship_from_rejects_incomplete_warehouse() -> None:
    with pytest.raises(ValueError, match="address1"):
        _build_ship_from("CENTRADE", {"CENTRADE": {"address": {"name": "X", "city": "Y"}}})


def test_build_ship_to_rejects_missing_recipient_fields() -> None:
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-EMPTY",
        address=SellfoxPackageAddress(name="", address_line_1="", city=""),
    )
    with pytest.raises(ValueError, match="Recipient"):
        _build_ship_to(package)
