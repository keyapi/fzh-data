from __future__ import annotations

import pytest

from sellfox_shipping.carriers.errors import CarrierFailure
from sellfox_shipping.label_service import LabelService, LabelServiceError
from sellfox_shipping.package_models import SellfoxPackageRecord
from sellfox_shipping.package_repository import PackageRepository


def _operation(tmp_path):
    repo = PackageRepository(tmp_path / "shipping.db")
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-TAXONOMY",
        local_review_status="approved",
    )
    repo.upsert(package)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    assert package_id is not None
    operation = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="taxonomy-1",
        request_hash="hash-taxonomy",
        actor="operator",
    )
    repo.transition_label_operation(operation.id, status="SENT")
    return repo, operation.id


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_class"),
    [
        (
            CarrierFailure(
                "missing credentials",
                phase="auth",
                outcome="not_sent",
                category="configuration",
                safe_to_create_again=True,
            ),
            "FAILED_SAFE",
            "configuration",
        ),
        (
            CarrierFailure(
                "invalid postal code",
                phase="create",
                outcome="rejected",
                category="validation",
                provider_code="INVALID_POSTAL",
                safe_to_create_again=True,
            ),
            "FAILED_FINAL",
            "validation",
        ),
        (
            CarrierFailure(
                "connection reset after send",
                phase="create",
                outcome="ambiguous",
                category="transport",
            ),
            "UNKNOWN_BLOCKED",
            "transport",
        ),
    ],
)
def test_label_service_maps_explicit_carrier_outcome(
    tmp_path, failure, expected_status, expected_class
) -> None:
    repo, operation_id = _operation(tmp_path)
    service = LabelService(repo)

    service._fail_operation(
        operation_id,
        LabelServiceError(str(failure), failure=failure),
    )

    stored = repo.get_label_operation(operation_id)
    assert stored.status == expected_status
    assert stored.error_class == expected_class


def test_query_failure_with_provider_id_stays_label_pending(tmp_path) -> None:
    repo, operation_id = _operation(tmp_path)
    repo.transition_label_operation(
        operation_id, status="ACCEPTED", provider_order_id="ORDER-1"
    )
    service = LabelService(repo)
    failure = CarrierFailure(
        "rate limited while polling",
        phase="query",
        outcome="retryable_query",
        category="rate_limited",
        provider_order_id="ORDER-1",
        http_status=429,
    )

    service._fail_operation(
        operation_id, LabelServiceError(str(failure), failure=failure)
    )

    stored = repo.get_label_operation(operation_id)
    assert stored.status == "LABEL_PENDING"
    assert stored.provider_order_id == "ORDER-1"
    assert stored.error_class == "rate_limited"


def test_safe_to_create_again_requires_supporting_outcome() -> None:
    with pytest.raises(ValueError, match="safe_to_create_again"):
        CarrierFailure(
            "ambiguous",
            phase="create",
            outcome="ambiguous",
            category="timeout",
            safe_to_create_again=True,
        )

# 鈹€鈹€ Orchestration-level taxonomy tests 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _orchestration_setup(tmp_path, monkeypatch, **kw):
    """Prepare repo + package + mock ViteGofoClient for create_label tests."""
    from sellfox_shipping.package_models import (
        SellfoxPackageAddress,
        SellfoxPackageLogistics,
    )
    from sellfox_shipping.carriers.vite.client import ViteGofoClient

    repo = PackageRepository(tmp_path / "shipping.db")
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn=kw.get("package_sn", "P-TAX-ORCH"),
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

    class _FakeClient:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(ViteGofoClient, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(ViteGofoClient, "__enter__", lambda self: _FakeClient())
    monkeypatch.setattr(ViteGofoClient, "__exit__", lambda *a: False)

    cfg = {
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
    return repo, package, cfg


def test_orch_vite_create_429_unknown_blocked(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteClientError
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)

    class _FailingSvc:
        def __init__(self, *a, **kw):
            pass
        def ship_package(self, *a, **kw):
            raise ViteClientError("rate limited", status_code=429, phase="create")

    monkeypatch.setattr(ViteShipmentService, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ViteShipmentService, "ship_package", _FailingSvc().ship_package)
    monkeypatch.setenv("VITE_API_KEY", "test-key")

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE API error"):
        service.create_label(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "UNKNOWN_BLOCKED"
    assert ops[0].error_class == "rate_limited"


def test_orch_vite_create_400_failed_final(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteClientError
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)

    class _FailingSvc:
        def __init__(self, *a, **kw):
            pass
        def ship_package(self, *a, **kw):
            raise ViteClientError("bad addr", status_code=400, phase="create")

    monkeypatch.setattr(ViteShipmentService, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ViteShipmentService, "ship_package", _FailingSvc().ship_package)
    monkeypatch.setenv("VITE_API_KEY", "test-key")

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE API error"):
        service.create_label(
            package=package, account_key="sellfox-main", carrier="vite", actor="operator"
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "FAILED_FINAL"
    assert ops[0].error_class == "validation"


def test_orch_vite_transport_unknown_blocked(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteClientError
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)

    class _FailingSvc:
        def __init__(self, *a, **kw):
            pass
        def ship_package(self, *a, **kw):
            raise ViteClientError("conn reset", status_code=None, phase="create")

    monkeypatch.setattr(ViteShipmentService, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ViteShipmentService, "ship_package", _FailingSvc().ship_package)
    monkeypatch.setenv("VITE_API_KEY", "test-key")

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE API error"):
        service.create_label(
            package=package, account_key="sellfox-main", carrier="vite", actor="operator"
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "UNKNOWN_BLOCKED"
    assert ops[0].error_class == "transport"


def test_orch_vite_missing_creds_failed_safe(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteGofoClient

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)
    monkeypatch.delenv("VITE_API_KEY", raising=False)
    def boom(*a, **kw):
        raise AssertionError("client must not be created")
    monkeypatch.setattr(ViteGofoClient, "__init__", boom)

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE_API_KEY"):
        service.create_label(
            package=package, account_key="sellfox-main", carrier="vite", actor="operator"
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "FAILED_SAFE"
    assert ops[0].error_class == "configuration"


# ── Orchestration-level taxonomy tests ──────────────────────────

def _orchestration_setup(tmp_path, monkeypatch, **kw):
    """Prepare repo + package + dims + mock ViteGofoClient for create_label."""
    from sellfox_shipping.package_models import (
        SellfoxPackageAddress,
        SellfoxPackageLogistics,
    )
    from sellfox_shipping.carriers.vite.client import ViteGofoClient

    repo = PackageRepository(tmp_path / "shipping.db")
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn=kw.get("package_sn", "P-TAX-ORCH"),
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

    class _FakeClient:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(ViteGofoClient, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(ViteGofoClient, "__enter__", lambda self: _FakeClient())
    monkeypatch.setattr(ViteGofoClient, "__exit__", lambda *a: False)

    cfg = {
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
    return repo, package, cfg


def test_orch_vite_create_429_unknown_blocked(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteClientError
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)

    class _FailingSvc:
        def __init__(self, *a, **kw):
            pass
        def ship_package(self, *a, **kw):
            raise ViteClientError("rate limited", status_code=429, phase="create")

    monkeypatch.setattr(ViteShipmentService, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ViteShipmentService, "ship_package", _FailingSvc().ship_package)
    monkeypatch.setenv("VITE_API_KEY", "test-key")

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE API error"):
        service.create_label(
            package=package,
            account_key="sellfox-main",
            carrier="vite",
            actor="operator",
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "UNKNOWN_BLOCKED"
    assert ops[0].error_class == "rate_limited"


def test_orch_vite_create_400_failed_final(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteClientError
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)

    class _FailingSvc:
        def __init__(self, *a, **kw):
            pass
        def ship_package(self, *a, **kw):
            raise ViteClientError("bad addr", status_code=400, phase="create")

    monkeypatch.setattr(ViteShipmentService, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ViteShipmentService, "ship_package", _FailingSvc().ship_package)
    monkeypatch.setenv("VITE_API_KEY", "test-key")

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE API error"):
        service.create_label(
            package=package, account_key="sellfox-main", carrier="vite", actor="operator"
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "FAILED_FINAL"
    assert ops[0].error_class == "validation"


def test_orch_vite_transport_unknown_blocked(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteClientError
    from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)

    class _FailingSvc:
        def __init__(self, *a, **kw):
            pass
        def ship_package(self, *a, **kw):
            raise ViteClientError("conn reset", status_code=None, phase="create")

    monkeypatch.setattr(ViteShipmentService, "__init__", lambda self, *a, **kw: None)
    monkeypatch.setattr(ViteShipmentService, "ship_package", _FailingSvc().ship_package)
    monkeypatch.setenv("VITE_API_KEY", "test-key")

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE API error"):
        service.create_label(
            package=package, account_key="sellfox-main", carrier="vite", actor="operator"
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "UNKNOWN_BLOCKED"
    assert ops[0].error_class == "transport"


def test_orch_vite_missing_creds_failed_safe(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.vite.client import ViteGofoClient

    repo, package, cfg = _orchestration_setup(tmp_path, monkeypatch)
    monkeypatch.delenv("VITE_API_KEY", raising=False)
    def boom(*a, **kw):
        raise AssertionError("client must not be created")
    monkeypatch.setattr(ViteGofoClient, "__init__", boom)

    service = LabelService(repo)
    service._cfg = cfg

    with pytest.raises(LabelServiceError, match="VITE_API_KEY"):
        service.create_label(
            package=package, account_key="sellfox-main", carrier="vite", actor="operator"
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "FAILED_SAFE"
    assert ops[0].error_class == "configuration"