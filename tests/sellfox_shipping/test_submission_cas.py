"""CAS and HTTP guard tests for submission (P1C)."""

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
from sellfox_shipping.submission_service import SubmissionService


class CountingSubmitClient:
    def __init__(self) -> None:
        self.calls = 0

    def submit_to_platform(self, wire_body: dict) -> dict:
        self.calls += 1
        return {"code": 0, "wire": wire_body}

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        return {
            "packageSn": package_sn,
            "logistics": {"trackNo": "TN-SUBMIT-1", "channelName": "FedEx"},
        }


def _seed_package(repo: PackageRepository, sn: str = "P2ASUBMIT1") -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
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
                channel_name="蜴国际-FedEx",
                tracking_number="TN-SUBMIT-1",
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORD-1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORD-1",
                    order_item_id="ITEM-1",
                    seller_sku="SKU-A",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn=sn,
        local_review_status="approved",
    )


def test_cas_rejects_stale_version(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo, "P2ACAS1")
    svc = SubmissionService(repo)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2ACAS1",
        actor="ops",
    )
    intent_id = prepared.intent_ids[0]
    intent = repo.get_submission_intent(intent_id)
    assert intent is not None
    attempt = repo.create_submission_attempt(intent_id=intent_id, actor="ops")
    assert repo.cas_submission_to_in_flight(
        intent_id=intent_id,
        attempt_id=attempt.id,
        expected_intent_version=intent.version,
    )
    assert not repo.cas_submission_to_in_flight(
        intent_id=intent_id,
        attempt_id=attempt.id,
        expected_intent_version=intent.version,
    )


def test_in_flight_intent_blocks_submit_before_http(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    client = CountingSubmitClient()
    svc = SubmissionService(repo, client)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2ASUBMIT1",
        actor="ops",
    )
    intent_id = prepared.intent_ids[0]
    with repo._session_factory.begin() as session:
        from sellfox_shipping.package_repository import SubmissionIntentRow

        row = session.get(SubmissionIntentRow, intent_id)
        assert row is not None
        row.status = "IN_FLIGHT"
    with pytest.raises(RuntimeError, match="cannot submit"):
        svc.submit_intent(
            intent_id=intent_id,
            actor="ops",
            dry_run=False,
            allow_side_effects=True,
        )
    assert client.calls == 0


def test_successful_submit_calls_http_once(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    client = CountingSubmitClient()
    svc = SubmissionService(repo, client)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2ASUBMIT1",
        actor="ops",
    )
    result = svc.submit_intent(
        intent_id=prepared.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    assert client.calls == 1
    assert result.intent_status == "VERIFIED"
    assert result.verified is True
    assert result.http_called is True


def test_dry_run_never_calls_http(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    client = CountingSubmitClient()
    svc = SubmissionService(repo, client)
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main",
        package_sn="P2ASUBMIT1",
        actor="ops",
    )
    result = svc.submit_intent(
        intent_id=prepared.intent_ids[0],
        actor="ops",
        dry_run=True,
    )
    assert client.calls == 0
    assert result.dry_run is True
    assert result.attempt_id == 0
