from __future__ import annotations

import json

from typer.testing import CliRunner

from sellfox_shipping import cli
from sellfox_shipping.package_models import SellfoxPackageRecord
from sellfox_shipping.package_repository import PackageRepository


def _package(account_key: str, package_sn: str) -> SellfoxPackageRecord:
    return SellfoxPackageRecord(
        account_key=account_key,
        package_sn=package_sn,
        local_review_status="approved",
    )


def _claim(
    repo: PackageRepository,
    *,
    account_key: str,
    package_sn: str,
    carrier: str = "vite",
):
    repo.upsert(_package(account_key, package_sn))
    package_id = repo.get_package_db_id(account_key, package_sn)
    assert package_id is not None
    return repo.claim_label_operation(
        account_key=account_key,
        package_db_id=package_id,
        carrier=carrier,
        service_level="GOFO_PARCEL",
        idempotency_key=f"{package_sn}:1",
        request_hash=f"hash-{package_sn}",
        actor="operator",
    )


def test_label_operations_list_filters_account_and_reports_unknown_action(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    target = _claim(repo, account_key="account-a", package_sn="P-A")
    _claim(repo, account_key="account-b", package_sn="P-A")
    repo.transition_label_operation(target.id, status="SENT")
    repo.transition_label_operation(
        target.id,
        status="UNKNOWN_BLOCKED",
        error_class="network_unknown",
        error_summary="recipient phone 2815550100 must not be exposed",
    )
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        [
            "label-operations-list",
            "--account-key",
            "account-a",
            "--status",
            "UNKNOWN_BLOCKED",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "label-operations-list"
    assert payload["ok"] is True
    assert payload["counts"] == {"input": 1, "success": 1, "failed": 0}
    assert payload["filters"]["account_key"] == "account-a"
    assert [row["package_sn"] for row in payload["results"]] == ["P-A"]
    assert payload["results"][0]["allowed_actions"] == ["investigate"]
    assert "T" in payload["results"][0]["created_at"]
    assert payload["results"][0]["created_at"].endswith("+08:00")
    assert "retry_create" not in result.output
    assert "2815550100" not in result.output


def test_label_operations_list_marks_provider_operation_resumable(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    operation = _claim(repo, account_key="account-a", package_sn="P-PENDING")
    repo.transition_label_operation(operation.id, status="SENT")
    repo.transition_label_operation(
        operation.id,
        status="ACCEPTED",
        provider_order_id="ORDER-123",
    )
    repo.transition_label_operation(operation.id, status="LABEL_PENDING")
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        ["label-operations-list", "--package-sn", "P-PENDING", "--json"],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(result.output)["results"][0]
    assert row["provider_order_id"] == "ORDER-123"
    assert row["allowed_actions"] == ["resume"]


def test_label_operations_list_returns_complete_empty_envelope(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        ["label-operations-list", "--status", "FAILED_FINAL", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["counts"] == {"input": 0, "success": 0, "failed": 0}
    assert payload["results"] == []
    assert payload["errors"] == []


def test_label_operations_list_terminal_operation_has_no_recovery_action(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    operation = _claim(repo, account_key="account-a", package_sn="P-DONE")
    repo.transition_label_operation(operation.id, status="SENT")
    repo.transition_label_operation(operation.id, status="SUCCEEDED")
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        ["label-operations-list", "--package-sn", "P-DONE", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["results"][0]["allowed_actions"] == []


def test_label_operation_show_includes_safe_label_and_artifact_summary(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    operation = _claim(repo, account_key="account-a", package_sn="P-SHOW")
    repo.transition_label_operation(operation.id, status="SENT")
    repo.transition_label_operation(
        operation.id,
        status="ACCEPTED",
        provider_order_id="ORDER-SHOW",
    )
    artifact = repo.register_artifact(
        account_key="account-a",
        kind="carrier_label",
        file_name="label.pdf",
        content=b"%PDF-safe",
        actor="operator",
    )
    package_id = repo.get_package_db_id("account-a", "P-SHOW")
    assert package_id is not None
    label = repo.insert_label(
        account_key="account-a",
        package_db_id=package_id,
        carrier="vite",
        service_level="GOFO_PARCEL",
        tracking_number="TRACK-SHOW",
        carrier_order_id="ORDER-SHOW",
        request_id="REQ-SHOW",
        label_url="https://secret.example/label.pdf",
        operation_id=operation.id,
        artifact_id=artifact.id,
        total_amount=3.5,
        currency="USD",
        status="generated",
        carrier_response_json='{"recipient_phone": "2815550100"}',
        created_by="operator",
    )
    repo.transition_label_operation(operation.id, status="SUCCEEDED")
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        ["label-operation-show", "--operation-id", str(operation.id), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["results"][0]["package_sn"] == "P-SHOW"
    assert payload["results"][0]["label"] == {
        "id": label.id,
        "status": "generated",
        "is_active": True,
        "tracking_number": "TRACK-SHOW",
        "artifact_id": artifact.id,
    }
    assert payload["results"][0]["artifact"] == {
        "id": artifact.id,
        "kind": "carrier_label",
        "file_name": "label.pdf",
        "mime_type": "application/pdf",
        "file_size": len(b"%PDF-safe"),
    }
    assert "secret.example" not in result.output
    assert "2815550100" not in result.output


def test_label_operation_show_returns_input_error_for_missing_operation(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        ["label-operation-show", "--operation-id", "999", "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "operation_not_found"
    assert payload["errors"][0]["recommended_action"] == "check_operation_id"
