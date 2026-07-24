"""UNKNOWN scope blocking tests (P1C)."""

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
from sellfox_shipping.submission_service import (
    SubmissionScopeBlockedError,
    SubmissionService,
    build_canonical_request,
)


def _seed(repo: PackageRepository) -> int:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn="P2ABLOCK1",
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
                tracking_number="TN-BLOCK-1",
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORD-B")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORD-B",
                    order_item_id="ITEM-B",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn="P2ABLOCK1",
        local_review_status="approved",
    )
    svc = SubmissionService(repo)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2ABLOCK1",
        actor="ops",
    )
    return prepared.intent_ids[0]


def test_unknown_scope_blocks_prepare_with_new_hash(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    repo.mark_submission_unknown_and_block_scope(
        attempt_id=repo.create_submission_attempt(intent_id=intent_id, actor="ops").id,
        intent_id=intent_id,
        http_summary="timeout",
    )
    repo.set_tracking_number(
        account_key="sellfox-main",
        package_sn="P2ABLOCK1",
        tracking_number="TN-BLOCK-NEW",
    )
    svc = SubmissionService(repo)
    with pytest.raises(SubmissionScopeBlockedError):
        svc.prepare_intents_for_package(
            account_key="sellfox-main",
            package_sn="P2ABLOCK1",
            actor="ops",
        )


def test_unknown_scope_blocks_submit(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    repo.mark_submission_unknown_and_block_scope(
        attempt_id=repo.create_submission_attempt(intent_id=intent_id, actor="ops").id,
        intent_id=intent_id,
        http_summary="timeout",
    )
    svc = SubmissionService(repo)
    with pytest.raises(SubmissionScopeBlockedError):
        svc.submit_intent(intent_id=intent_id, actor="ops", dry_run=True)


def test_different_hash_after_tracking_change(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    intent = repo.get_submission_intent(intent_id)
    assert intent is not None
    pkg_id = repo.get_package_db_id("sellfox-main", "P2ABLOCK1")
    assert pkg_id is not None
    _, _, new_hash = build_canonical_request(
        account_key="sellfox-main",
        package_db_id=pkg_id,
        external_order_id="ORD-B",
        shop_id="SHOP-1",
        tracking_number="TN-OTHER",
        carrier_name="FedEx",
        shipping_service="",
        items=[{"order_item_id": "ITEM-B", "quantity": 1}],
    )
    assert new_hash != intent.request_hash
