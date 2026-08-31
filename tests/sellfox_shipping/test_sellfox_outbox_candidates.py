from __future__ import annotations

import pytest

from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed_package(
    repo: PackageRepository,
    *,
    package_sn: str = "P-OUTBOX-1",
    tracking: str = "TN-OUTBOX-1",
    package_status: str = "to_process",
    review: str = "approved",
    order_count: int = 2,
) -> int:
    orders = [
        SellfoxPackageOrderRecord(external_order_id=f"ORDER-{index}")
        for index in range(1, order_count + 1)
    ]
    items = [
        SellfoxPackageItemRecord(
            external_order_id=order.external_order_id,
            order_item_id=f"ITEM-{index}",
            seller_sku=f"SKU-{index}",
            quantity=1,
        )
        for index, order in enumerate(orders, start=1)
    ]
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=package_sn,
            package_status=package_status,
            local_review_status=review,
            logistics=SellfoxPackageLogistics(
                tracking_number=tracking,
                channel_name="FedEx",
            ),
            orders=orders,
            items=items,
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn=package_sn,
        local_review_status=review,
    )
    package_id = repo.get_package_db_id("sellfox-main", package_sn)
    assert package_id is not None
    return package_id


def _add_active_label(
    repo: PackageRepository, package_id: int, tracking: str
) -> None:
    repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number=tracking,
        carrier_order_id=f"ORDER-{tracking}",
        request_id=f"REQ-{tracking}",
        label_url="https://example.invalid/label.pdf",
        artifact_id=None,
        total_amount=None,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
    )


def test_migration_creates_default_disabled_policy_and_outbox_tables(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo)
    _add_active_label(repo, package_id, "TN-OUTBOX-1")

    policy = repo.get_sellfox_writeback_policy("sellfox-main")

    assert policy.mode == "DISABLED"
    assert policy.capability_status == "UNVERIFIED"
    with repo.engine.connect() as connection:
        names = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "shipping_sellfox_outbox" in names
    assert "shipping_sellfox_outbox_sources" in names
    assert "shipping_sellfox_writeback_policies" in names


def test_one_package_with_two_orders_creates_two_order_candidates(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo)
    _add_active_label(repo, package_id, "TN-OUTBOX-1")

    report = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OUTBOX-1",
        source_type="api_label",
        source_id="label:10:operation:20",
        actor="operator",
    )

    assert report.counts == {
        "input": 2,
        "created": 2,
        "existing": 0,
        "skipped": 0,
        "conflict": 0,
        "failed": 0,
    }
    rows = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")
    assert [row.external_order_id for row in rows] == ["ORDER-1", "ORDER-2"]
    assert all(row.status == "AWAITING_CONFIRMATION" for row in rows)


def test_duplicate_sources_reuse_candidate_and_preserve_each_source(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo, order_count=1)
    _add_active_label(repo, package_id, "TN-OUTBOX-1")

    first = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OUTBOX-1",
        source_type="api_label",
        source_id="label:10:operation:20",
        actor="operator",
    )
    second = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OUTBOX-1",
        source_type="excel_tracking_import",
        source_id="batch:4:row:7",
        actor="operator",
    )

    assert first.counts["created"] == 1
    assert second.counts["existing"] == 1
    rows = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")
    assert len(rows) == 1
    assert {(source.source_type, source.source_id) for source in rows[0].sources} == {
        ("api_label", "label:10:operation:20"),
        ("excel_tracking_import", "batch:4:row:7"),
    }


def test_new_tracking_supersedes_unsent_candidate(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo, order_count=1)
    _add_active_label(repo, package_id, "TN-OLD")
    repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OLD",
        source_type="excel_tracking_import",
        source_id="batch:1:row:1",
        actor="operator",
    )

    report = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-NEW",
        source_type="excel_tracking_import",
        source_id="batch:2:row:1",
        actor="operator",
    )

    assert report.counts["created"] == 1
    rows = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")
    assert [(row.tracking_number, row.status) for row in rows] == [
        ("TN-NEW", "AWAITING_CONFIRMATION"),
        ("TN-OLD", "SUPERSEDED"),
    ]


def test_new_tracking_conflicts_with_sent_candidate_without_overwrite(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo, order_count=1)
    _add_active_label(repo, package_id, "TN-OLD")
    repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OLD",
        source_type="api_label",
        source_id="label:1",
        actor="operator",
    )
    old = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")[0]
    repo.set_sellfox_outbox_status(old.id, "IN_FLIGHT")

    report = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-NEW",
        source_type="excel_tracking_import",
        source_id="batch:2:row:1",
        actor="operator",
    )

    assert report.counts["conflict"] == 1
    rows = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")
    assert [(row.tracking_number, row.status) for row in rows] == [
        ("TN-NEW", "CONFLICT"),
        ("TN-OLD", "IN_FLIGHT"),
    ]
    assert rows[0].conflicts_with_outbox_id == old.id


def test_tracking_reverted_to_superseded_candidate_reactivates_it(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo, order_count=1)
    _add_active_label(repo, package_id, "TN-OLD")
    repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OLD",
        source_type="api_label",
        source_id="label:1:operation:1",
        actor="operator",
    )
    repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-NEW",
        source_type="excel_tracking_import",
        source_id="batch:1:row:1",
        actor="operator",
    )

    report = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OLD",
        source_type="excel_tracking_import",
        source_id="batch:2:row:1",
        actor="operator",
    )

    assert report.counts["existing"] == 1
    rows = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")
    assert sorted(
        [(row.tracking_number, row.status) for row in rows]
    ) == [("TN-NEW", "SUPERSEDED"), ("TN-OLD", "AWAITING_CONFIRMATION")]


def test_excel_finalizer_reverts_to_superseded_candidate(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo, order_count=1)
    repo.finalize_excel_tracking_with_outbox(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OLD",
        source_id="batch:1:row:1",
        actor="operator",
    )
    repo.finalize_excel_tracking_with_outbox(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-NEW",
        source_id="batch:2:row:1",
        actor="operator",
    )

    report = repo.finalize_excel_tracking_with_outbox(
        account_key="sellfox-main",
        package_sn="P-OUTBOX-1",
        tracking_number="TN-OLD",
        source_id="batch:3:row:1",
        actor="operator",
    )

    assert report[1].counts["existing"] == 1
    rows = repo.list_sellfox_outbox(package_sn="P-OUTBOX-1")
    assert sorted(
        [(row.tracking_number, row.status) for row in rows]
    ) == [("TN-NEW", "SUPERSEDED"), ("TN-OLD", "AWAITING_CONFIRMATION")]


def test_candidate_generation_reports_placeholder_unapproved_and_shipped_as_skipped(
    tmp_path,
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo, package_sn="P-PLACEHOLDER", tracking="P-PLACEHOLDER", order_count=1)
    _seed_package(repo, package_sn="P-PENDING", review="pending", order_count=1)
    _seed_package(repo, package_sn="P-SHIPPED", package_status="has_shipped", order_count=1)

    results = [
        repo.create_sellfox_outbox_candidates(
            account_key="sellfox-main",
            package_sn=package_sn,
            tracking_number=tracking,
            source_type="excel_tracking_import",
            source_id=f"scan:{package_sn}",
            actor="operator",
        )
        for package_sn, tracking in [
            ("P-PLACEHOLDER", "P-PLACEHOLDER"),
            ("P-PENDING", "TN-PENDING"),
            ("P-SHIPPED", "TN-SHIPPED"),
        ]
    ]

    assert [result.counts["skipped"] for result in results] == [1, 1, 1]
    assert repo.list_sellfox_outbox() == []


def test_label_success_finalizer_updates_operation_tracking_and_candidates_atomically(
    tmp_path,
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo, tracking="")
    operation = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="P-OUTBOX-1:1",
        request_hash="request-hash",
        actor="operator",
    )
    repo.transition_label_operation(operation.id, status="SENT")
    repo.transition_label_operation(
        operation.id, status="ACCEPTED", provider_order_id="PROVIDER-1"
    )
    label = repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TN-FINAL",
        carrier_order_id="PROVIDER-1",
        request_id="REQ-1",
        label_url="https://example.invalid/label.pdf",
        operation_id=operation.id,
        artifact_id=None,
        total_amount=None,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
    )

    report = repo.finalize_label_success_with_outbox(
        operation_id=operation.id,
        label_id=label.id,
        actor="operator",
    )

    package = repo.get("sellfox-main", "P-OUTBOX-1")
    assert package is not None
    assert package.logistics.tracking_number == "TN-FINAL"
    assert repo.get_label_operation(operation.id).status == "SUCCEEDED"
    assert report.counts["existing"] == 2
    assert all(
        source.source_id == f"label:{label.id}:operation:{operation.id}"
        for row in repo.list_sellfox_outbox()
        for source in row.sources
    )


def test_insert_label_rolls_back_label_operation_tracking_and_outbox_together(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    package_id = _seed_package(repo, tracking="")
    operation = repo.claim_label_operation(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        idempotency_key="P-OUTBOX-1:atomic",
        request_hash="request-hash",
        actor="operator",
    )
    repo.transition_label_operation(operation.id, status="SENT")
    repo.transition_label_operation(
        operation.id, status="ACCEPTED", provider_order_id="PROVIDER-ATOMIC"
    )

    def fail_candidate_generation(*args, **kwargs):
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr(
        repo,
        "_create_sellfox_outbox_candidates_in_session",
        fail_candidate_generation,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="injected outbox failure"):
        repo.insert_label(
            account_key="sellfox-main",
            package_db_id=package_id,
            carrier="vite",
            service_level="GOFO_PARCEL",
            tracking_number="TN-ATOMIC",
            carrier_order_id="PROVIDER-ATOMIC",
            request_id="REQ-ATOMIC",
            label_url="https://example.invalid/label.pdf",
            operation_id=operation.id,
            artifact_id=None,
            total_amount=None,
            currency="USD",
            status="generated",
            carrier_response_json="{}",
            created_by="operator",
        )

    package = repo.get("sellfox-main", "P-OUTBOX-1")
    assert package is not None
    assert package.logistics.tracking_number == ""
    assert repo.get_label_operation(operation.id).status == "ACCEPTED"
    assert repo.list_labels_for_package(
        account_key="sellfox-main", package_sn="P-OUTBOX-1"
    ) == []
    assert repo.list_sellfox_outbox(package_sn="P-OUTBOX-1") == []


def test_excel_finalizer_reports_pending_package_as_skipped(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo, package_sn="P-SKIP", review="pending", order_count=1)
    _, report = repo.finalize_excel_tracking_with_outbox(
        account_key="sellfox-main",
        package_sn="P-SKIP",
        tracking_number="TN-SKIP",
        source_id="batch:1:row:1",
        actor="operator",
    )
    assert report.counts["skipped"] == 1
    assert report.results[0]["reason"] == "package_not_approved"
    assert repo.list_sellfox_outbox(package_sn="P-SKIP") == []


def test_excel_finalizer_reports_placeholder_tracking_as_skipped(tmp_path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo, package_sn="P-PLACE", tracking="P-PLACE", order_count=1)
    _, report = repo.finalize_excel_tracking_with_outbox(
        account_key="sellfox-main",
        package_sn="P-PLACE",
        tracking_number="P-PLACE",
        source_id="batch:1:row:1",
        actor="operator",
    )
    assert report.counts["skipped"] == 1
    assert report.results[0]["reason"] == "tracking_missing_or_placeholder"
    assert repo.list_sellfox_outbox(package_sn="P-PLACE") == []
