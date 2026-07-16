from __future__ import annotations

import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from sellfox_shipping import cli
from sellfox_shipping.package_service import PackageSyncReport


class FakeSyncService:
    def __init__(self):
        self.request = None

    def sync(self, request):
        self.request = request
        now = datetime.now(timezone.utc)
        return PackageSyncReport(
            actor=request.actor,
            account_key=request.account_key,
            total_in_sellfox=2,
            input_count=2,
            success_count=2,
            created_count=2,
            sync_status="completed",
            started_at=now,
            finished_at=now,
        )


def test_packages_sync_cli_uses_shared_service_and_outputs_json(monkeypatch) -> None:
    service = FakeSyncService()
    monkeypatch.setattr(cli, "_get_package_sync_service", lambda: service)

    result = CliRunner().invoke(
        cli.app,
        [
            "packages-sync",
            "--date-start",
            "2026-07-15",
            "--date-end",
            "2026-07-16",
            "--actor",
            "user-1",
            "--page-size",
            "100",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["input_count"] == 2
    assert payload["success_count"] == 2
    assert payload["is_reconciled"] is True
    assert service.request.actor == "user-1"
    assert service.request.page_size == 100


def test_packages_sync_cli_returns_nonzero_for_partial_failure(monkeypatch) -> None:
    class PartialFailureService(FakeSyncService):
        def sync(self, request):
            report = super().sync(request)
            report.sync_status = "partial_failed"
            report.run_errors = ["page 2: gateway error"]
            return report

    monkeypatch.setattr(
        cli,
        "_get_package_sync_service",
        lambda: PartialFailureService(),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "packages-sync",
            "--date-start",
            "2026-07-15",
            "--date-end",
            "2026-07-16",
            "--actor",
            "user-1",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["sync_status"] == "partial_failed"


def test_packages_list_cli_uses_shared_service_and_outputs_json(monkeypatch) -> None:
    from sellfox_shipping.package_models import PackageListItem, PackageListResult

    class FakeListService:
        def __init__(self):
            self.request = None

        def list(self, request):
            self.request = request
            return PackageListResult(
                total=1,
                items=[
                    PackageListItem(
                        account_key=request.account_key,
                        package_sn="P10001",
                        package_status="to_audit",
                        channel_name="蜴国际",
                        order_count=2,
                        item_count=1,
                    )
                ],
            )

    service = FakeListService()
    monkeypatch.setattr(cli, "_get_package_list_service", lambda: service)

    result = CliRunner().invoke(
        cli.app,
        [
            "packages-list",
            "--status",
            "to_audit",
            "--channel",
            "蜴国际",
            "--limit",
            "10",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["total"] == 1
    assert payload["items"][0]["package_sn"] == "P10001"
    assert service.request.package_status == "to_audit"
    assert service.request.channel_name == "蜴国际"
    assert service.request.limit == 10
