from __future__ import annotations

import pytest
from pydantic import ValidationError

from sellfox_shipping.package_models import (
    PackageRowError,
    SellfoxPackagePage,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.package_service import (
    ListPackagesService,
    PackageListRequest,
    PackageSyncRequest,
    SyncPackagesService,
)


def _record(package_sn: str, source_row_index: int) -> SellfoxPackageRecord:
    return SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn=package_sn,
        source_row_index=source_row_index,
    )


class FakeGateway:
    def __init__(self, pages: dict[int, SellfoxPackagePage]):
        self.pages = pages
        self.calls: list[int] = []

    def fetch_package_page(self, **kwargs) -> SellfoxPackagePage:
        page_no = kwargs["page_no"]
        self.calls.append(page_no)
        return self.pages[page_no]


def test_sync_packages_paginates_and_reconciles_every_input_row(tmp_path) -> None:
    gateway = FakeGateway(
        {
            1: SellfoxPackagePage(
                page_no=1,
                page_size=2,
                total_size=3,
                records=[_record("P10001", 1)],
                errors=[
                    PackageRowError(
                        row_index=2,
                        package_sn="",
                        reason="missing packageSn",
                    )
                ],
            ),
            2: SellfoxPackagePage(
                page_no=2,
                page_size=2,
                total_size=3,
                records=[_record("P10002", 1)],
            ),
        }
    )
    repository = PackageRepository(tmp_path / "shipping.db")
    service = SyncPackagesService(gateway, repository)

    report = service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
            page_size=2,
        )
    )

    assert gateway.calls == [1, 2]
    assert report.total_in_sellfox == 3
    assert report.input_count == 3
    assert report.success_count == 2
    assert report.failed_count == 1
    assert report.skipped_count == 0
    assert report.unmatched_count == 0
    assert report.created_count == 2
    assert report.updated_count == 0
    assert report.is_reconciled is True
    assert [row.source_row_number for row in report.row_results] == [1, 2, 3]
    assert report.row_results[1].reason == "missing packageSn"


def test_repeated_sync_reports_updates_without_creating_duplicates(tmp_path) -> None:
    page = SellfoxPackagePage(
        page_no=1,
        page_size=20,
        total_size=1,
        records=[_record("P10001", 1)],
    )
    gateway = FakeGateway({1: page})
    repository = PackageRepository(tmp_path / "shipping.db")
    service = SyncPackagesService(gateway, repository)
    request = PackageSyncRequest(
        account_key="sellfox-main",
        date_start="2026-07-15",
        date_end="2026-07-16",
        actor="user-1",
    )
    service.sync(request)

    report = service.sync(request)

    assert report.success_count == 1
    assert report.created_count == 0
    assert report.updated_count == 1
    assert repository.count_rows()["packages"] == 1


def test_sync_uses_server_page_size_when_proxy_reduces_requested_size(
    tmp_path,
) -> None:
    gateway = FakeGateway(
        {
            1: SellfoxPackagePage(
                page_no=1,
                page_size=1,
                total_size=2,
                records=[_record("P10001", 1)],
            ),
            2: SellfoxPackagePage(
                page_no=2,
                page_size=1,
                total_size=2,
                records=[_record("P10002", 1)],
            ),
        }
    )
    service = SyncPackagesService(
        gateway,
        PackageRepository(tmp_path / "shipping.db"),
    )

    report = service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
            page_size=200,
        )
    )

    assert gateway.calls == [1, 2]
    assert report.input_count == report.total_in_sellfox == 2


def test_sync_rejects_record_from_a_different_account(tmp_path) -> None:
    page = SellfoxPackagePage(
        page_no=1,
        page_size=20,
        total_size=1,
        records=[
            SellfoxPackageRecord(
                account_key="sellfox-us-2",
                package_sn="P10001",
                source_row_index=1,
            )
        ],
    )
    repository = PackageRepository(tmp_path / "shipping.db")
    service = SyncPackagesService(FakeGateway({1: page}), repository)

    report = service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
        )
    )

    assert report.success_count == 0
    assert report.failed_count == 1
    assert report.row_results[0].reason == "account mismatch"
    assert repository.count_rows()["packages"] == 0


def test_persistence_error_is_redacted_from_report() -> None:
    class FailingRepository:
        def upsert(self, record):
            raise RuntimeError("email=user@example.com")

        def append_audit_event(self, **kwargs):
            return 1

    page = SellfoxPackagePage(
        page_no=1,
        page_size=20,
        total_size=1,
        records=[_record("P10001", 1)],
    )
    service = SyncPackagesService(FakeGateway({1: page}), FailingRepository())

    report = service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
        )
    )

    assert report.failed_count == 1
    assert report.row_results[0].reason == "persistence error"
    assert "example.com" not in report.model_dump_json()


def test_sync_request_rejects_blank_actor() -> None:
    with pytest.raises(ValidationError):
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="   ",
        )


def test_gateway_failure_after_first_page_returns_partial_report(tmp_path) -> None:
    class FailingSecondPageGateway:
        def fetch_package_page(self, **kwargs):
            if kwargs["page_no"] == 2:
                raise RuntimeError("upstream included private response data")
            return SellfoxPackagePage(
                page_no=1,
                page_size=1,
                total_size=2,
                records=[_record("P10001", 1)],
            )

    repository = PackageRepository(tmp_path / "shipping.db")
    service = SyncPackagesService(FailingSecondPageGateway(), repository)

    report = service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
            page_size=1,
        )
    )

    assert report.sync_status == "partial_failed"
    assert report.input_count == report.success_count == 1
    assert report.total_in_sellfox == 2
    assert report.remaining_count == 1
    assert report.run_errors == ["page 2: gateway error"]
    assert "private response" not in report.model_dump_json()
    assert repository.count_rows()["packages"] == 1


def test_first_page_gateway_failure_reports_unknown_total(tmp_path) -> None:
    class FailingGateway:
        def fetch_package_page(self, **kwargs):
            raise RuntimeError("unavailable")

    service = SyncPackagesService(
        FailingGateway(),
        PackageRepository(tmp_path / "shipping.db"),
    )

    report = service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
        )
    )

    assert report.sync_status == "partial_failed"
    assert report.total_in_sellfox is None
    assert report.remaining_count is None


def test_sync_writes_audit_event_for_actor(tmp_path) -> None:
    page = SellfoxPackagePage(
        page_no=1,
        page_size=20,
        total_size=1,
        records=[_record("P10001", 1)],
    )
    repository = PackageRepository(tmp_path / "shipping.db")
    service = SyncPackagesService(FakeGateway({1: page}), repository)

    service.sync(
        PackageSyncRequest(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-16",
            actor="user-1",
        )
    )

    events = repository.list_audit_events(limit=5)
    assert len(events) == 1
    assert events[0].actor == "user-1"
    assert events[0].action == "packages.sync"
    assert events[0].entity_type == "account"
    assert events[0].entity_id == "sellfox-main"
    assert "input_count" in events[0].summary


def test_list_packages_service_returns_filtered_summaries(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    repository.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn="P10001",
            package_status="to_audit",
        )
    )
    repository.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn="P10002",
            package_status="shipped",
        )
    )
    service = ListPackagesService(repository)

    result = service.list(
        PackageListRequest(
            account_key="sellfox-main",
            package_status="to_audit",
            limit=20,
        )
    )

    assert result.total == 1
    assert [item.package_sn for item in result.items] == ["P10001"]
