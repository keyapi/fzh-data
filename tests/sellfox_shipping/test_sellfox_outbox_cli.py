from __future__ import annotations

import json

from typer.testing import CliRunner

from sellfox_shipping import cli
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
            package_sn="P-CLI-1",
            package_status="to_process",
            local_review_status="approved",
            logistics=SellfoxPackageLogistics(
                tracking_number="TN-CLI-1", channel_name="FedEx"
            ),
            orders=[SellfoxPackageOrderRecord(external_order_id="ORDER-CLI-1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="ORDER-CLI-1",
                    order_item_id="ITEM-CLI-1",
                    seller_sku="PRIVATE-SKU",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn="P-CLI-1",
        local_review_status="approved",
    )


def test_scan_candidates_defaults_to_dry_run_without_mutation(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    result = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-scan-candidates",
            "--account-key",
            "sellfox-main",
            "--package-sn",
            "P-CLI-1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "sellfox-outbox-scan-candidates"
    assert payload["dry_run"] is True
    assert payload["counts"] == {
        "input": 1,
        "created": 1,
        "existing": 0,
        "skipped": 0,
        "conflict": 0,
        "failed": 0,
    }
    assert repo.list_sellfox_outbox() == []
    assert "PRIVATE-SKU" not in result.output


def test_scan_candidates_apply_requires_actor_and_persists_scoped_package(
    tmp_path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    rejected = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-scan-candidates",
            "--account-key",
            "sellfox-main",
            "--package-sn",
            "P-CLI-1",
            "--apply",
            "--json",
        ],
    )
    assert rejected.exit_code != 0

    applied = CliRunner().invoke(
        cli.app,
        [
            "sellfox-outbox-scan-candidates",
            "--account-key",
            "sellfox-main",
            "--package-sn",
            "P-CLI-1",
            "--apply",
            "--actor",
            "operator",
            "--json",
        ],
    )
    assert applied.exit_code == 0, applied.output
    assert len(repo.list_sellfox_outbox(package_sn="P-CLI-1")) == 1


def test_outbox_list_and_show_use_safe_json_envelopes(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    repo.create_sellfox_outbox_candidates(
        account_key="sellfox-main",
        package_sn="P-CLI-1",
        tracking_number="TN-CLI-1",
        source_type="excel_tracking_import",
        source_id="batch:1:row:1",
        actor="operator",
    )
    row = repo.list_sellfox_outbox()[0]
    monkeypatch.setattr(cli, "_get_package_repository", lambda: repo)

    listed = CliRunner().invoke(
        cli.app, ["sellfox-outbox-list", "--status", "AWAITING_CONFIRMATION", "--json"]
    )
    shown = CliRunner().invoke(
        cli.app, ["sellfox-outbox-show", "--outbox-id", str(row.id), "--json"]
    )

    assert listed.exit_code == 0, listed.output
    assert shown.exit_code == 0, shown.output
    assert json.loads(listed.output)["counts"]["success"] == 1
    assert json.loads(shown.output)["results"][0]["sources"] == [
        {"source_type": "excel_tracking_import", "source_id": "batch:1:row:1"}
    ]
    assert "PRIVATE-SKU" not in listed.output + shown.output
