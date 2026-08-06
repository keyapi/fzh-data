from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sellfox_shipping.outbox_service import OutboxService
from sellfox_shipping.outbox_service import OutboxService, classify_submission_failure
from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


class CountingClient:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.detail_calls = 0
        self.detail_track_no: str | None = "TN-EXEC-1"
        self.submit_response: dict = {"code": 0}

    def submit_to_platform(self, wire_body: dict) -> dict:
        self.submit_calls += 1
        return self.submit_response

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        self.detail_calls += 1
        if self.detail_track_no is None:
            return {"packageSn": package_sn}
        return {
            "packageSn": package_sn,
            "logistics": {"trackNo": self.detail_track_no},
        }


def _seed_package(
    repo: PackageRepository,
    *,
    package_sn: str = "P-EXEC-1",
    tracking: str = "TN-EXEC-1",
) -> int:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=package_sn,
            shop_id="SHOP-1",
            package_status="to_process",
            local_review_status="approved",
            logistics=SellfoxPackageLogistics(
                tracking_number=tracking, channel_name="FedEx"
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORDER-EXEC-1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORDER-EXEC-1",
                    order_item_id="ITEM-EXEC-1",
                    seller_sku="SKU-EXEC",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn=package_sn,
        local_review_status="approved",
    )
    package_id = repo.get_package_db_id("sellfox-main", package_sn)
    assert package_id is not None
    repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number=tracking,
        carrier_order_id="ORDER-CARRIER-1",
        request_id="REQ-1",
        label_url="https://example.invalid/label.pdf",
        artifact_id=None,
        total_amount=None,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
    )
    return package_id


def _create_candidate(repo: PackageRepository, package_sn: str = "P-EXEC-1") -> int:
    report = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn=package_sn,
        tracking_number="TN-EXEC-1",
        source_type="api_label",
        source_id="label:1:operation:1",
        actor="operator",
    )
    assert report.counts["created"] == 1
    row = repo.list_sellfox_outbox(package_sn=package_sn)[0]
    return row.id


def _enable_probe(repo: PackageRepository) -> None:
    repo.record_sellfox_writeback_capability(
        account_key="sellfox-main",
        capability_status="SAFE_TRACKNO_ONLY",
        evidence_ref="probe-2026-08-06",
        actor="ops",
    )
    repo.set_sellfox_writeback_policy(
        account_key="sellfox-main", mode="PROBE_ONLY", actor="ops"
    )


def _confirm(repo: PackageRepository, outbox_id: int) -> None:
    result = OutboxService(repo).confirm(outbox_id=outbox_id, actor="ops")
    assert result["status"] == "PENDING"


def test_confirm_builds_intent_and_moves_to_pending(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)

    result = OutboxService(repo).confirm(outbox_id=outbox_id, actor="ops")

    assert result["status"] == "PENDING"
    assert result["submission_intent_id"] is not None
    assert len(result["request_hash"]) == 64
    intent = repo.get_submission_intent(result["submission_intent_id"])
    assert intent is not None
    assert intent.status == "READY"
    assert intent.request_hash == result["request_hash"]
    with pytest.raises(RuntimeError, match="must be AWAITING_CONFIRMATION"):
        OutboxService(repo).confirm(outbox_id=outbox_id, actor="ops")


def test_policy_default_gate_and_capability_evidence(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)

    service = OutboxService(repo)
    default = service.policy_show("sellfox-main")
    assert default["results"][0]["mode"] == "DISABLED"
    assert default["results"][0]["capability_status"] == "UNVERIFIED"

    with pytest.raises(ValueError, match="SAFE_TRACKNO_ONLY"):
        repo.set_sellfox_writeback_policy(
            account_key="sellfox-main", mode="SCOPED_BATCH", actor="ops"
        )

    _enable_probe(repo)
    scoped = repo.set_sellfox_writeback_policy(
        account_key="sellfox-main", mode="SCOPED_BATCH", actor="ops"
    )
    assert scoped.mode == "SCOPED_BATCH"

    unsafe = repo.record_sellfox_writeback_capability(
        account_key="sellfox-main",
        capability_status="UNSAFE_PLATFORM_SIDE_EFFECT",
        evidence_ref="probe-conclusion",
        actor="ops",
    )
    assert unsafe.mode == "DISABLED"
    assert unsafe.capability_status == "UNSAFE_PLATFORM_SIDE_EFFECT"


def test_concurrent_claim_and_token_fencing(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)

    repo_a = PackageRepository(tmp_path / "shipping.db")
    repo_b = PackageRepository(tmp_path / "shipping.db")
    first = repo_a.claim_sellfox_outbox(
        outbox_id=outbox_id, owner="agent-a", lease_token="token-a", lease_seconds=60
    )
    second = repo_b.claim_sellfox_outbox(
        outbox_id=outbox_id, owner="agent-b", lease_token="token-b", lease_seconds=60
    )
    assert first is True
    assert second is False
    assert not repo_a.finish_sellfox_outbox(
        outbox_id=outbox_id, lease_token="stale-token", status="VERIFIED"
    )
    assert repo_a.finish_sellfox_outbox(
        outbox_id=outbox_id, lease_token="token-a", status="VERIFIED"
    )


def test_dry_run_has_no_state_change_and_no_http(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    client = CountingClient()
    service = OutboxService(repo, submit_client=client)

    result = service.run_once(
        actor="ops", outbox_id=outbox_id, dry_run=True, limit=1
    )

    assert result["dry_run"] is True
    assert result["results"][0]["action"] == "submit"
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "PENDING"
    assert row.lease_owner == ""
    assert client.submit_calls == 0
    assert client.detail_calls == 0


def test_real_run_submits_once_and_verifies(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)
    client = CountingClient()
    service = OutboxService(repo, submit_client=client)

    result = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )

    assert result["counts"]["success"] == 1
    assert result["results"][0]["status"] == "VERIFIED"
    assert client.submit_calls == 1
    assert client.detail_calls == 1
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "VERIFIED"
    intent = repo.get_submission_intent(row.submission_intent_id)
    assert intent is not None
    assert intent.status == "VERIFIED"


def test_delayed_readback_enters_verify_pending_then_verified(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)
    client = CountingClient()
    client.detail_track_no = None
    service = OutboxService(repo, submit_client=client)

    result = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )

    assert result["results"][0]["status"] == "VERIFY_PENDING"
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "VERIFY_PENDING"
    assert row.next_attempt_at is not None
    assert client.submit_calls == 1

    client.detail_track_no = "TN-EXEC-1"
    verified = service.verify(actor="ops", outbox_id=outbox_id)
    assert verified["results"][0]["status"] == "VERIFIED"


def test_unconfirmed_candidate_cannot_be_leased_or_sent(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _enable_probe(repo)
    client = CountingClient()
    service = OutboxService(repo, submit_client=client)

    assert not repo.claim_sellfox_outbox(
        outbox_id=outbox_id, owner="ops", lease_token="token-x", lease_seconds=60
    )
    result = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert result["counts"]["failed"] == 1
    assert client.submit_calls == 0
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "AWAITING_CONFIRMATION"


def test_probe_only_blocks_batch_without_explicit_outbox(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)
    client = CountingClient()
    service = OutboxService(repo, submit_client=client)

    result = service.run_once(
        actor="ops",
        account_key="sellfox-main",
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert result["counts"]["failed"] == 1
    assert client.submit_calls == 0
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "PENDING"


def test_readback_conflict_blocks_without_overwrite(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)
    client = CountingClient()
    client.detail_track_no = "TN-EXEC-OTHER"
    service = OutboxService(repo, submit_client=client)

    first = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert first["results"][0]["status"] == "VERIFY_PENDING"
    verified = service.verify(actor="ops", outbox_id=outbox_id)
    assert verified["results"][0]["status"] == "CONFLICT"
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "CONFLICT"
    assert client.submit_calls == 1
    package = repo.get("sellfox-main", "P-EXEC-1")
    assert package is not None
    assert package.logistics.tracking_number == "TN-EXEC-1"


def test_stale_token_cannot_release_new_lease(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    assert repo.claim_sellfox_outbox(
        outbox_id=outbox_id, owner="ops", lease_token="token-a", lease_seconds=60
    )
    assert not repo.release_sellfox_outbox_lease(
        outbox_id=outbox_id, lease_token="stale-token"
    )
    assert repo.release_sellfox_outbox_lease(
        outbox_id=outbox_id, lease_token="token-a"
    )
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "PENDING"


def test_expired_lease_recovers_to_origin_status(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    repo.set_sellfox_outbox_status(outbox_id, "VERIFY_PENDING")
    assert repo.claim_sellfox_outbox(
        outbox_id=outbox_id, owner="ops", lease_token="token-exp", lease_seconds=60
    )
    with sqlite3.connect(tmp_path / "shipping.db") as connection:
        connection.execute(
            "UPDATE shipping_sellfox_outbox SET lease_expires_at=? WHERE id=?",
            ("2020-01-01 00:00:00", outbox_id),
        )
    repo.recover_stale_sellfox_outbox(actor="ops")
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "VERIFY_PENDING"


def test_submission_failure_classification() -> None:
    assert classify_submission_failure(http_status=401).outbox_status == "MANUAL_REVIEW"
    assert classify_submission_failure(http_status=429).outbox_status == "RETRYABLE"
    assert classify_submission_failure(http_status=502).outbox_status == "UNKNOWN_BLOCKED"
    assert (
        classify_submission_failure(response_text="invalid sku").outbox_status
        == "FAILED_FINAL"
    )
    assert (
        classify_submission_failure(response_text="unexpected payload").outbox_status
        == "UNKNOWN_BLOCKED"
    )


def test_unknown_failure_blocks_and_never_resubmits(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)

    class FlakyClient(CountingClient):
        def submit_to_platform(self, wire_body: dict) -> dict:
            self.submit_calls += 1
            raise RuntimeError("connection reset during submit")

    client = FlakyClient()
    service = OutboxService(repo, submit_client=client)
    first = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )

    assert first["results"][0]["status"] == "UNKNOWN_BLOCKED"
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "UNKNOWN_BLOCKED"

    second = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert second["counts"]["failed"] == 1
    assert client.submit_calls == 1


def test_rate_limit_rejection_is_retryable_then_manual(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)

    client = CountingClient()
    client.submit_response = {"code": 429, "msg": "rate limit, slow down"}
    service = OutboxService(repo, submit_client=client)

    result = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert result["results"][0]["status"] == "RETRYABLE"
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.next_attempt_at is not None

    with sqlite3.connect(tmp_path / "shipping.db") as connection:
        connection.execute(
            "UPDATE shipping_sellfox_outbox SET attempt_count=4, next_attempt_at=NULL "
            "WHERE id=?",
            (outbox_id,),
        )
    exhausted = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert exhausted["results"][0]["status"] == "MANUAL_REVIEW"


def test_recovery_moves_stale_in_flight_to_unknown_blocked(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    repo.set_sellfox_outbox_status(outbox_id, "IN_FLIGHT")

    service = OutboxService(repo)
    preview = service.run_once(actor="ops", account_key="sellfox-main", dry_run=True)
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "IN_FLIGHT"
    assert preview["counts"]["input"] == 0

    result = service.run_once(
        actor="ops",
        account_key="sellfox-main",
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )

    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "UNKNOWN_BLOCKED"
    assert result["counts"]["input"] == 0


def test_disabled_policy_blocks_real_send_without_http(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    client = CountingClient()
    service = OutboxService(repo, submit_client=client)

    result = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )

    assert result["counts"]["failed"] == 1
    assert client.submit_calls == 0
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "PENDING"


def test_readback_failure_blocks_without_resubmit(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)
    client = CountingClient()
    client.detail_track_no = None
    service = OutboxService(repo, submit_client=client)

    first = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert first["results"][0]["status"] == "VERIFY_PENDING"

    class BrokenReadbackClient(CountingClient):
        def fetch_package_detail(self, package_sn: str) -> dict | None:
            self.detail_calls += 1
            raise RuntimeError("connection reset during readback")

    broken = BrokenReadbackClient()
    broken.submit_calls = client.submit_calls
    verify_service = OutboxService(repo, submit_client=broken)
    verify_service.verify(actor="ops", outbox_id=outbox_id)

    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "UNKNOWN_BLOCKED"
    assert broken.submit_calls == 1
    retry = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert retry["counts"]["failed"] == 1
    assert broken.submit_calls == 1


def test_release_lease_restores_origin_status(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    repo.set_sellfox_outbox_status(outbox_id, "VERIFY_PENDING")
    assert repo.claim_sellfox_outbox(
        outbox_id=outbox_id, owner="ops", lease_token="token-rel", lease_seconds=60
    )
    assert repo.release_sellfox_outbox_lease(
        outbox_id=outbox_id, lease_token="token-rel"
    )
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "VERIFY_PENDING"


def test_auth_failure_stops_automatic_retry(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_package(repo)
    outbox_id = _create_candidate(repo)
    _confirm(repo, outbox_id)
    _enable_probe(repo)
    client = CountingClient()
    client.submit_response = {"code": 401, "msg": "unauthorized"}
    service = OutboxService(repo, submit_client=client)

    first = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert first["results"][0]["status"] == "MANUAL_REVIEW"
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "MANUAL_REVIEW"

    second = service.run_once(
        actor="ops",
        outbox_id=outbox_id,
        dry_run=False,
        allow_side_effects=True,
        limit=1,
    )
    assert second["counts"]["failed"] == 1
    assert client.submit_calls == 1
