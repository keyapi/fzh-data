from __future__ import annotations

from pathlib import Path

import pytest

from sellfox_shipping.app import _get_vite_rate
from sellfox_shipping.carriers.lizard.api_shipment import (
    LizardApiShipmentService,
    LizardLabelNotReadyError,
)
from sellfox_shipping.carriers.vite.shipment import (
    ViteLabelNotReadyError,
    ViteShipmentService,
)
from sellfox_shipping.label_service import LabelService, LabelServiceError
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from tests.sellfox_shipping.test_label_acquisition_safety import (
    COMPLETE_WAREHOUSE_CFG,
    _ready_repo,
)


class _FakeViteClient:
    def __init__(
        self,
        *,
        order_id: str = "PPGF-ORDER-1",
        label_ready: bool = True,
        label_url: str = "https://cdn.example/v.pdf",
        tracking: str = "9400111",
    ):
        self.order_id = order_id
        self.label_ready = label_ready
        self.label_url = label_url
        self.tracking = tracking
        self.create_calls = 0
        self.get_label_calls = 0

    def create_shipment_gofo(self, body: dict) -> dict:
        self.create_calls += 1
        return {"orderId": self.order_id, "totalAmount": 4.2, "currency": "USD"}

    def create_shipment_fedex(self, body: dict) -> dict:
        return self.create_shipment_gofo(body)

    def get_label(self, order_id: str) -> list[dict]:
        assert order_id == self.order_id
        self.get_label_calls += 1
        if not self.label_ready:
            return [{"status": "PENDING", "trackingNumber": "", "url": ""}]
        return [
            {
                "status": "OK",
                "trackingNumber": self.tracking,
                "url": self.label_url,
            }
        ]


class _FakeLizardClient:
    def __init__(self):
        self.create_bodies: list[dict] = []
        self.get_label_calls = 0

    def create_order(self, body: dict) -> dict:
        self.create_bodies.append(body)
        return {
            "code": 200,
            "result": {
                "order_code": "OC-PENDING-1",
                "labels": {"tracking_number": "1ZPEND", "label_url": ""},
            },
        }

    def get_label(self, *, order_code: str = "", reference_no: str = "") -> dict:
        self.get_label_calls += 1
        return {
            "code": 200,
            "result": {
                "sync_service_status": 0,
                "order_status": "Pending",
                "labels": {"tracking_number": "1ZPEND", "label_url": ""},
            },
        }


def _claim_sent(repo: PackageRepository, package_sn: str = "P-SAFE-1") -> tuple[int, int]:
    package_id = repo.get_package_db_id("sellfox-main", package_sn)
    assert package_id is not None
    op = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key=f"{package_sn}:vite",
        request_hash="hash-recover",
        actor="operator",
    )
    repo.transition_label_operation(op.id, status="SENT")
    return package_id, op.id


def _vite_package(repo: PackageRepository) -> SellfoxPackageRecord:
    pkg = repo.get("sellfox-main", "P-SAFE-1")
    assert pkg is not None
    return pkg


def test_vite_poll_timeout_marks_label_pending_with_provider_id(tmp_path: Path) -> None:
    repo, _ = _ready_repo(tmp_path)
    package_id, op_id = _claim_sent(repo)
    client = _FakeViteClient(label_ready=False)
    times = iter([0.0, 1.0, 999.0])

    svc = ViteShipmentService(
        client,
        repo,
        warehouses_cfg=COMPLETE_WAREHOUSE_CFG["warehouses"],
        sleep=lambda _s: None,
        monotonic=lambda: next(times, 999.0),
        fetch_bytes=lambda _url: b"%PDF",
    )

    with pytest.raises(ViteLabelNotReadyError):
        svc.ship_package(
            _vite_package(repo),
            account_key="sellfox-main",
            actor="operator",
            package_dims={
                "weight_kg": 2,
                "length_cm": 30,
                "width_cm": 20,
                "height_cm": 10,
            },
            poll_interval_s=0.0,
            poll_timeout_s=0.01,
            operation_id=op_id,
        )

    assert client.create_calls == 1
    op = repo.get_label_operation(op_id)
    assert op.status == "LABEL_PENDING"
    assert op.provider_order_id == "PPGF-ORDER-1"
    _ = package_id


def test_vite_pdf_download_failure_marks_label_pending(tmp_path: Path) -> None:
    repo, _ = _ready_repo(tmp_path)
    _, op_id = _claim_sent(repo)
    client = _FakeViteClient(label_ready=True)

    svc = ViteShipmentService(
        client,
        repo,
        warehouses_cfg=COMPLETE_WAREHOUSE_CFG["warehouses"],
        sleep=lambda _s: None,
        monotonic=lambda: 0.0,
        fetch_bytes=lambda _url: b"",
    )

    with pytest.raises(RuntimeError, match="empty label PDF"):
        svc.ship_package(
            _vite_package(repo),
            account_key="sellfox-main",
            actor="operator",
            package_dims={
                "weight_kg": 2,
                "length_cm": 30,
                "width_cm": 20,
                "height_cm": 10,
            },
            operation_id=op_id,
        )

    assert client.create_calls == 1
    op = repo.get_label_operation(op_id)
    assert op.status == "LABEL_PENDING"
    assert op.provider_order_id == "PPGF-ORDER-1"
    assert op.tracking_number == "9400111"


def test_vite_artifact_failure_marks_label_pending(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _ready_repo(tmp_path)
    _, op_id = _claim_sent(repo)
    client = _FakeViteClient(label_ready=True)

    def boom(**_kwargs):
        raise RuntimeError("artifact write failed")

    monkeypatch.setattr(repo, "register_artifact", boom)
    svc = ViteShipmentService(
        client,
        repo,
        warehouses_cfg=COMPLETE_WAREHOUSE_CFG["warehouses"],
        sleep=lambda _s: None,
        monotonic=lambda: 0.0,
        fetch_bytes=lambda _url: b"%PDF-1.4",
    )

    with pytest.raises(RuntimeError, match="artifact write failed"):
        svc.ship_package(
            _vite_package(repo),
            account_key="sellfox-main",
            actor="operator",
            package_dims={
                "weight_kg": 2,
                "length_cm": 30,
                "width_cm": 20,
                "height_cm": 10,
            },
            operation_id=op_id,
        )

    assert client.create_calls == 1
    op = repo.get_label_operation(op_id)
    assert op.status == "LABEL_PENDING"
    assert op.provider_order_id == "PPGF-ORDER-1"


def test_lizard_poll_timeout_marks_label_pending(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-API-PEND",
        local_review_status="approved",
        address=SellfoxPackageAddress(
            name="Smoke Test",
            address_line_1="10812 Fallstone Rd",
            city="Houston",
            state_or_region="TX",
            postal_code="77099",
            country_code="US",
            phone="2816770938",
        ),
        logistics=SellfoxPackageLogistics(
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
            )
        ],
    )
    repo.upsert(package)
    package_id = repo.get_package_db_id("sellfox-main", package.package_sn)
    assert package_id is not None
    op = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="lizard",
        service_level="FedEx-Ground-J-TX",
        idempotency_key="P-API-PEND:1",
        request_hash="hash-liz",
        actor="operator",
    )
    repo.transition_label_operation(op.id, status="SENT")

    client = _FakeLizardClient()
    times = iter([0.0, 1.0, 999.0])
    svc = LizardApiShipmentService(
        client,
        repo,
        sleep=lambda _s: None,
        monotonic=lambda: next(times, 999.0),
        fetch_bytes=lambda _url: b"%PDF",
    )

    with pytest.raises(LizardLabelNotReadyError):
        svc.ship_package(
            package,
            account_key="sellfox-main",
            actor="operator",
            sm_code="FedEx-Ground-J-TX",
            poll_interval_s=0.0,
            poll_timeout_s=0.01,
            operation_id=op.id,
        )

    assert len(client.create_bodies) == 1
    stored = repo.get_label_operation(op.id)
    assert stored.status == "LABEL_PENDING"
    assert stored.provider_order_id == "OC-PENDING-1"
    assert stored.tracking_number == "1ZPEND"


def test_crash_window_sent_with_linked_label_cancel_allows_reclaim(tmp_path: Path) -> None:
    repo, package = _ready_repo(tmp_path)
    package_id, op_id = _claim_sent(repo)
    label = repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRACK-CRASH",
        carrier_order_id="ORDER-CRASH",
        request_id="REQ-CRASH",
        label_url="https://example.invalid/c.pdf",
        artifact_id=None,
        total_amount=1,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
        operation_id=op_id,
    )
    with repo.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE shipping_label_operations SET status='SENT' WHERE id=?",
            (op_id,),
        )
    assert repo.get_label_operation(op_id).status == "SENT"

    label_rec, op_rec = repo.finalize_label_cancellation(label.id, actor="operator")
    assert label_rec.status == "cancelled"
    assert label_rec.is_active is False
    assert op_rec is not None
    assert op_rec.status == "CANCELLED"

    replacement = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="P-SAFE-1:gen2",
        request_hash="hash-2",
        actor="operator",
    )
    assert replacement.generation == 2
    assert package.package_sn == "P-SAFE-1"


def test_reconcile_cancelled_label_with_active_operation(tmp_path: Path, monkeypatch) -> None:
    """Simulate crash after label inactive write but before operation CANCELLED."""
    repo, _ = _ready_repo(tmp_path)
    package_id, op_id = _claim_sent(repo)
    repo.transition_label_operation(
        op_id, status="ACCEPTED", provider_order_id="ORDER-ORPHAN"
    )
    label = repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRACK-ORPHAN",
        carrier_order_id="ORDER-ORPHAN",
        request_id="REQ-ORPHAN",
        label_url="https://example.invalid/o.pdf",
        artifact_id=None,
        total_amount=1,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
        operation_id=op_id,
    )
    # Only label side written — the old non-atomic cancel crash window.
    repo.update_label_status(label.id, "cancelled")
    with repo.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE shipping_label_operations SET status='ACCEPTED' WHERE id=?",
            (op_id,),
        )
    assert repo.get_label_operation(op_id).status == "ACCEPTED"

    service = LabelService(repo)
    # Should not call carrier again; reconciliation is local.
    monkeypatch.setattr(
        service,
        "_request_vite_cancel",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("carrier cancel must not run")),
    )
    out = service.cancel_label(label.id, actor="operator")
    assert out["status"] == "cancelled"
    assert "Reconciled" in out["message"]
    assert repo.get_label_operation(op_id).status == "CANCELLED"

    replacement = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="P-SAFE-1:after-reconcile",
        request_hash="hash-reconcile",
        actor="operator",
    )
    assert replacement.generation == 2


def test_label_pending_to_cancelled_is_allowed(tmp_path: Path) -> None:
    repo, _ = _ready_repo(tmp_path)
    _, op_id = _claim_sent(repo)
    repo.transition_label_operation(
        op_id, status="ACCEPTED", provider_order_id="PPGF-1"
    )
    repo.transition_label_operation(op_id, status="LABEL_PENDING")
    cancelled = repo.transition_label_operation(op_id, status="CANCELLED")
    assert cancelled is not None
    assert cancelled.status == "CANCELLED"


def test_cancel_label_surfaces_operation_transition_failure(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _ = _ready_repo(tmp_path)
    package_id, op_id = _claim_sent(repo)
    repo.transition_label_operation(
        op_id, status="UNKNOWN_BLOCKED", error_class="network_unknown"
    )
    label = repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRACK-UNK",
        carrier_order_id="ORDER-UNK",
        request_id="REQ-UNK",
        label_url="https://example.invalid/u.pdf",
        artifact_id=None,
        total_amount=1,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
        operation_id=None,
    )
    with repo.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE shipping_labels SET operation_id=? WHERE id=?",
            (op_id, label.id),
        )

    service = LabelService(repo)
    monkeypatch.setenv("VITE_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        service,
        "_request_vite_cancel",
        lambda _label: "Cancelled",
    )

    with pytest.raises(LabelServiceError, match="local finalize failed"):
        service.cancel_label(label.id, actor="operator")

    # Atomic finalize rolled back — label must still be active.
    assert repo.get_label(label.id).status == "generated"
    assert repo.get_label(label.id).is_active is True
    assert repo.get_label_operation(op_id).status == "UNKNOWN_BLOCKED"


def test_lizard_insert_label_failure_marks_label_pending(
    tmp_path: Path, monkeypatch
) -> None:
    repo, package = _ready_repo(tmp_path)
    service = LabelService(repo)
    service._cfg = COMPLETE_WAREHOUSE_CFG

    class _Result:
        tracking_number = "1ZINSERT"
        order_code = "OC-INSERT-1"
        label_url = "https://cdn.example/liz.pdf"
        artifact_id = 1

    create_calls = {"n": 0}

    def fake_ship(**kwargs):
        create_calls["n"] += 1
        assert kwargs.get("operation_id") is not None
        # Adapter already ACCEPTED before returning.
        repo.transition_label_operation(
            kwargs["operation_id"],
            status="ACCEPTED",
            provider_order_id="OC-INSERT-1",
        )
        return _Result()

    class _FakeLizardSvc:
        def __init__(self, *args, **kwargs):
            pass

        def ship_package(self, package, *, account_key, actor, sm_code, operation_id=None, **kwargs):
            return fake_ship(operation_id=operation_id)

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setenv("YIGLOBAL_APP_TOKEN", "tok")
    monkeypatch.setenv("YIGLOBAL_APP_KEY", "key")
    monkeypatch.setattr(
        "sellfox_shipping.carriers.lizard.api_client.LizardApiClient",
        lambda **_k: _FakeClient(),
    )
    monkeypatch.setattr(
        "sellfox_shipping.carriers.lizard.api_shipment.LizardApiShipmentService",
        _FakeLizardSvc,
    )

    def boom_insert(**_kwargs):
        raise RuntimeError("insert_label boom")

    monkeypatch.setattr(repo, "insert_label", boom_insert)

    # create_label will claim+SENT then call _create_lizard_label
    with pytest.raises(LabelServiceError, match="local insert failed"):
        service.create_label(
            package=package,
            account_key="sellfox-main",
            carrier="lizard",
            actor="operator",
            service_level="FedEx-Ground-J-TX",
        )

    ops = repo.list_label_operations(package_sn=package.package_sn)
    assert len(ops) == 1
    assert ops[0].status == "LABEL_PENDING"
    assert ops[0].provider_order_id == "OC-INSERT-1"
    assert create_calls["n"] == 1


def test_vite_rate_skips_api_when_address_incomplete(monkeypatch) -> None:
    calls = {"client": 0}

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            calls["client"] += 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "sellfox_shipping.carriers.vite.ViteGofoClient",
        _BoomClient,
    )
    monkeypatch.setenv("VITE_API_KEY", "test-key-not-real")

    record = SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn="P-RATE-1",
        address=SellfoxPackageAddress(name="", address_line_1="", city=""),
        logistics=SellfoxPackageLogistics(warehouse_name="CENTRADE"),
    )
    result = _get_vite_rate(
        record,
        {"weight_kg": 2, "length_cm": 30, "width_cm": 20, "height_cm": 10},
        routing_result=None,
    )
    assert result is not None
    assert "error" in result
    assert calls["client"] == 0
