"""Recover stale IN_FLIGHT submission rows (P1C)."""

from __future__ import annotations

from pathlib import Path

from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.submission_service import SubmissionService


def _seed_and_leave_in_flight(repo: PackageRepository) -> int:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn="P2ARECOVER1",
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
                channel_name="FedEx",
                tracking_number="TN-REC-1",
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORD-R")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORD-R",
                    order_item_id="ITEM-R",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn="P2ARECOVER1",
        local_review_status="approved",
    )
    svc = SubmissionService(repo)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2ARECOVER1",
        actor="ops",
    )
    intent_id = prepared.intent_ids[0]
    attempt = repo.create_submission_attempt(intent_id=intent_id, actor="ops")
    intent = repo.get_submission_intent(intent_id)
    assert intent is not None
    ok = repo.cas_submission_to_in_flight(
        intent_id=intent_id,
        attempt_id=attempt.id,
        expected_intent_version=intent.version,
    )
    assert ok is True
    return intent_id


def test_recover_stale_in_flight_marks_unknown_and_blocks_scope(
    tmp_path: Path,
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed_and_leave_in_flight(repo)
    svc = SubmissionService(repo)
    count = svc.recover_stale_in_flight(actor="system")
    assert count >= 1
    intent = repo.get_submission_intent(intent_id)
    assert intent is not None
    assert intent.status == "UNKNOWN"
    assert repo.is_submission_scope_blocked_by_intent(intent_id)


def test_migration_head_includes_submission_tables(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    with repo.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        scopes = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='shipping_submission_scopes'"
        ).scalar_one()
        intents = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='shipping_submission_intents'"
        ).scalar_one()
    assert version == "0023_tongtool_mark"

    assert scopes == "shipping_submission_scopes"
    assert intents == "shipping_submission_intents"
