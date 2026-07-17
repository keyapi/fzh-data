"""1 rps submit rate limit + packageDetail readback → VERIFIED."""

from __future__ import annotations

import time
from pathlib import Path

from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.submission_rate_limit import SubmitRateLimiter
from sellfox_shipping.submission_service import SubmissionService


class FakeSubmitAndDetailClient:
    def __init__(self, *, track_no: str = "TN-OK", detail_ok: bool = True) -> None:
        self.submit_calls = 0
        self.detail_calls = 0
        self.track_no = track_no
        self.detail_ok = detail_ok
        self.submit_times: list[float] = []

    def submit_to_platform(self, wire_body: dict) -> dict:
        self.submit_calls += 1
        self.submit_times.append(time.monotonic())
        return {"code": 0, "msg": "ok"}

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        self.detail_calls += 1
        if not self.detail_ok:
            raise TimeoutError("detail timeout")
        return {
            "packageSn": package_sn,
            "logistics": {"trackNo": self.track_no, "channelName": "FedEx"},
        }


def _seed(repo: PackageRepository, sn: str = "P2ARPS1", tn: str = "TN-OK") -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
            shop_id="SHOP-1",
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="T",
                address_line_1="1",
                city="X",
                state_or_region="NJ",
                postal_code="07101",
                country_code="US",
                phone="555",
            ),
            logistics=SellfoxPackageLogistics(
                channel_name="FedEx",
                tracking_number=tn,
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="O-RPS")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O-RPS",
                    order_item_id="I-RPS",
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


def test_rate_limiter_enforces_one_per_second() -> None:
    limiter = SubmitRateLimiter(min_interval_seconds=1.0)
    t0 = time.monotonic()
    w1 = limiter.wait()
    w2 = limiter.wait()
    elapsed = time.monotonic() - t0
    assert w1 == 0.0
    assert w2 >= 0.9
    assert elapsed >= 0.9


def test_two_submits_spaced_by_rate_limit(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, sn="P2ARPS-A", tn="TN-A")
    _seed(repo, sn="P2ARPS-B", tn="TN-B")
    client = FakeSubmitAndDetailClient(track_no="TN-A")
    # Second package submit will use different track in client — reconfigure per call
    svc = SubmissionService(
        repo,
        client,
        rate_limiter=SubmitRateLimiter(min_interval_seconds=1.0),
    )
    a = svc.prepare_intents_for_package(
        account_key="sellfox-main", package_sn="P2ARPS-A", actor="ops"
    )
    b = svc.prepare_intents_for_package(
        account_key="sellfox-main", package_sn="P2ARPS-B", actor="ops"
    )
    client.track_no = "TN-A"
    r1 = svc.submit_intent(
        intent_id=a.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    client.track_no = "TN-B"
    r2 = svc.submit_intent(
        intent_id=b.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    assert client.submit_calls == 2
    assert r2.rate_limited_wait_ms >= 900
    gap = client.submit_times[1] - client.submit_times[0]
    assert gap >= 0.9


def test_success_readback_matching_track_becomes_verified(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    client = FakeSubmitAndDetailClient(track_no="TN-OK")
    svc = SubmissionService(repo, client, rate_limiter=SubmitRateLimiter(0.0))
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main", package_sn="P2ARPS1", actor="ops"
    )
    result = svc.submit_intent(
        intent_id=prepared.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    assert result.intent_status == "VERIFIED"
    assert result.verified is True
    assert client.detail_calls == 1


def test_success_readback_mismatch_stays_success(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo, tn="TN-LOCAL")
    client = FakeSubmitAndDetailClient(track_no="TN-OTHER")
    svc = SubmissionService(repo, client, rate_limiter=SubmitRateLimiter(0.0))
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main", package_sn="P2ARPS1", actor="ops"
    )
    result = svc.submit_intent(
        intent_id=prepared.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    assert result.intent_status == "SUCCESS"
    assert result.verified is False


def test_readback_error_leaves_success_not_unknown(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    client = FakeSubmitAndDetailClient(detail_ok=False)
    svc = SubmissionService(repo, client, rate_limiter=SubmitRateLimiter(0.0))
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main", package_sn="P2ARPS1", actor="ops"
    )
    result = svc.submit_intent(
        intent_id=prepared.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    assert result.intent_status == "SUCCESS"
    assert result.verified is False
    assert not repo.is_submission_scope_blocked_by_intent(prepared.intent_ids[0])


def test_verify_intent_cli_path_from_success(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    client = FakeSubmitAndDetailClient(track_no="TN-OK")
    svc = SubmissionService(repo, client, rate_limiter=SubmitRateLimiter(0.0))
    prepared = svc.prepare_intents_for_package(
        account_key="sellfox-main", package_sn="P2ARPS1", actor="ops"
    )
    # Force SUCCESS without verify by stubbing detail fail then fixing
    client.detail_ok = False
    svc.submit_intent(
        intent_id=prepared.intent_ids[0],
        actor="ops",
        dry_run=False,
        allow_side_effects=True,
    )
    client.detail_ok = True
    verified = svc.verify_intent_from_readback(
        intent_id=prepared.intent_ids[0],
        actor="ops",
    )
    assert verified.intent_status == "VERIFIED"
    assert verified.verified is True
