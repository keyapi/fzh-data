from __future__ import annotations

import json

from typer.testing import CliRunner

from sellfox_shipping import cli
from sellfox_shipping.outbox_service import OutboxService
from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed(repo: PackageRepository) -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn="P-CLI-EXEC-1",
            package_status="to_process",
            local_review_status="approved",
            logistics=SellfoxPackageLogistics(
                tracking_number="TN-CLI-EXEC-1", channel_name="FedEx"
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORDER-CLI-EXEC-1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORDER-CLI-EXEC-1",
                    order_item_id="ITEM-CLI-EXEC-1",
                    seller_sku="SKU-CLI-EXEC",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn="P-CLI-EXEC-1",
        local_review_status="approved",
    )


class CountingClient:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.detail_calls = 0

    def submit_to_platform(self, wire_body: dict) -> dict:
        self.submit_calls += 1
        return {"code": 0}

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        self.detail_calls += 1
        return {"packageSn": package_sn, "logistics": {"trackNo": "TN-CLI-EXEC-1"}}


def _seed_candidate(repo: PackageRepository) -> int:
    _seed(repo)
    package_id = repo.get_package_db_id("sellfox-main", "P-CLI-EXEC-1")
    assert package_id is not None
    repo.insert_label(
        account_key="sellfox-main",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TN-CLI-EXEC-1",
        carrier_order_id="ORDER-CLI-CARRIER-1",
        request_id="REQ-CLI-1",
        label_url="https://example.invalid/label.pdf",
        artifact_id=None,
        total_amount=None,
        currency="USD",
        status="generated",
        carrier_response_json="{}",
        created_by="operator",
    )
    report = repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-CLI-EXEC-1",
        tracking_number="TN-CLI-EXEC-1",
        source_type="api_label",
        source_id="label:1:operation:1",
        actor="operator",
    )
    assert report.counts["created"] == 1
    return repo.list_sellfox_outbox(package_sn="P-CLI-EXEC-1")[0].id


def test_confirm_and_policy_cli(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    outbox_id = _seed_candidate(repo)
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    confirmed = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-confirm",
            "--outbox-id",
            str(outbox_id),
            "--actor",
            "ops",
            "--json",
        ],
    )
    assert confirmed.exit_code == 0, confirmed.output
    assert json.loads(confirmed.output)["results"][0]["status"] == "PENDING"

    policy = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-policy-set",
            "--account-key",
            "sellfox-main",
            "--mode",
            "PROBE_ONLY",
            "--actor",
            "ops",
            "--json",
        ],
    )
    assert policy.exit_code == 0, policy.output
    assert json.loads(policy.output)["results"][0]["mode"] == "PROBE_ONLY"

    capability = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-capability-record",
            "--account-key",
            "sellfox-main",
            "--capability-status",
            "SAFE_TRACKNO_ONLY",
            "--evidence-ref",
            "probe-1",
            "--actor",
            "ops",
            "--json",
        ],
    )
    assert capability.exit_code == 0, capability.output


def test_run_once_dry_run_cli_keeps_candidate_untouched(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    outbox_id = _seed_candidate(repo)
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)
    OutboxService(repo).confirm(outbox_id=outbox_id, actor="ops")

    result = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-run-once",
            "--outbox-id",
            str(outbox_id),
            "--actor",
            "ops",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["counts"]["success"] == 1
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "PENDING"
    assert row.lease_owner == ""


def test_run_once_real_cli_calls_http_once(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    outbox_id = _seed_candidate(repo)
    OutboxService(repo).confirm(outbox_id=outbox_id, actor="ops")
    repo.record_sellfox_writeback_capability(
        account_key="sellfox-main",
        capability_status="SAFE_TRACKNO_ONLY",
        evidence_ref="probe-1",
        actor="ops",
    )
    repo.set_sellfox_writeback_policy(
        account_key="sellfox-main", mode="PROBE_ONLY", actor="ops"
    )
    client = CountingClient()
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)
    monkeypatch.setattr(cli, "_get_client", lambda: client)

    result = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-run-once",
            "--outbox-id",
            str(outbox_id),
            "--actor",
            "ops",
            "--no-dry-run",
            "--i-understand-side-effects",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["results"][0]["status"] == "VERIFIED"
    assert client.submit_calls == 1
    assert client.detail_calls == 1
    row = repo.get_sellfox_outbox(outbox_id)
    assert row is not None
    assert row.status == "VERIFIED"
