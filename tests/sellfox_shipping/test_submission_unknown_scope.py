"""UNKNOWN scope blocking tests (P1C)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from typer.testing import CliRunner

from sellfox_shipping import cli
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.sellfox_client import SellfoxApiError
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


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def submit_to_platform(self, wire_body: dict) -> dict:
        raise self.exc

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        return None


def test_4xx_marks_failed_not_unknown_scope(tmp_path: Path) -> None:
    """A 4xx rejection is FAILED and leaves the scope OPEN (retryable)."""
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    svc = SubmissionService(
        repo,
        _RaisingClient(SellfoxApiError("Sellfox HTTP 400: bad", status_code=400)),
    )
    result = svc.submit_intent(
        intent_id=intent_id, actor="ops", dry_run=False, allow_side_effects=True
    )
    assert result.intent_status == "FAILED"
    assert result.attempt_status == "FAILED"
    assert not repo.is_submission_scope_blocked_by_intent(intent_id)


def test_5xx_marks_unknown_and_blocks_scope(tmp_path: Path) -> None:
    """A 5xx leaves the outcome unknown → UNKNOWN + scope blocked."""
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    svc = SubmissionService(
        repo,
        _RaisingClient(SellfoxApiError("Sellfox HTTP 500: boom", status_code=500)),
    )
    result = svc.submit_intent(
        intent_id=intent_id, actor="ops", dry_run=False, allow_side_effects=True
    )
    assert result.intent_status == "UNKNOWN"
    assert result.attempt_status == "UNKNOWN"
    assert repo.is_submission_scope_blocked_by_intent(intent_id)


@pytest.mark.parametrize("status_code", [401, 429])
def test_ambiguous_4xx_blocks_scope_instead_of_permitting_resubmit(
    tmp_path: Path, status_code: int
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    svc = SubmissionService(
        repo,
        _RaisingClient(SellfoxApiError("ambiguous", status_code=status_code)),
    )

    result = svc.submit_intent(
        intent_id=intent_id, actor="ops", dry_run=False, allow_side_effects=True
    )

    assert result.intent_status == "UNKNOWN"
    assert result.attempt_status == "UNKNOWN"
    assert repo.is_submission_scope_blocked_by_intent(intent_id)


def test_legacy_scope_unblock_api_is_not_available(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    assert not hasattr(repo, "resolve_submission_scope_block")


class _ResolveCountingClient:
    def __init__(self) -> None:
        self.calls = 0

    def submit_to_platform(self, wire_body: dict) -> dict:
        self.calls += 1
        return {"code": 0}

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        return {"logistics": {"trackNo": "TN-BLOCK-1"}}


def test_unknown_scope_can_be_resolved_after_human_check(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    repo.mark_submission_unknown_and_block_scope(
        attempt_id=repo.create_submission_attempt(intent_id=intent_id, actor="ops").id,
        intent_id=intent_id,
        http_summary="HTTP 401 before side effect",
    )
    assert repo.is_submission_scope_blocked_by_intent(intent_id)

    svc = SubmissionService(repo)
    result = svc.resolve_unknown_blocked_scope(
        intent_id=intent_id,
        actor="ops-lead",
        note="401 confirmed before send; readback unchanged; safe to retry",
    )
    assert result["scope_status"] == "OPEN"
    assert result["intent_status"] == "READY"
    assert not repo.is_submission_scope_blocked_by_intent(intent_id)

    client = _ResolveCountingClient()
    submit = SubmissionService(repo, client).submit_intent(
        intent_id=intent_id,
        actor="ops-lead",
        dry_run=False,
        allow_side_effects=True,
    )
    assert client.calls == 1
    assert submit.intent_status == "VERIFIED"


def test_scope_resolve_rejects_non_blocked_scope(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    svc = SubmissionService(repo)
    with pytest.raises(RuntimeError, match="not UNKNOWN_BLOCKED"):
        svc.resolve_unknown_blocked_scope(
            intent_id=intent_id,
            actor="ops-lead",
            note="not blocked",
        )


def test_submission_scope_resolve_cli(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    intent_id = _seed(repo)
    repo.mark_submission_unknown_and_block_scope(
        attempt_id=repo.create_submission_attempt(intent_id=intent_id, actor="ops").id,
        intent_id=intent_id,
        http_summary="HTTP 401 before side effect",
    )
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        [
            "submission-scope-resolve",
            "--intent-id",
            str(intent_id),
            "--actor", "ops-lead",
            "--note", "401 before send; safe to retry",
            "--confirm", "unblock",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["results"][0]["scope_status"] == "OPEN"
    assert payload["results"][0]["intent_status"] == "READY"
