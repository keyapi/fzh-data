"""Application service for read-only Sellfox package synchronization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from sellfox_shipping.package_models import SellfoxPackagePage
from sellfox_shipping.package_repository import UpsertOutcome


class PackagePageGateway(Protocol):
    def fetch_package_page(
        self,
        *,
        date_start: str,
        date_end: str,
        status: str | None,
        shop_ids: list[str] | None,
        page_no: int,
        page_size: int,
    ) -> SellfoxPackagePage: ...


class PackageWriter(Protocol):
    def upsert(self, record) -> UpsertOutcome: ...


class PackageSyncRequest(BaseModel):
    account_key: str
    date_start: str
    date_end: str
    actor: str
    status: str | None = None
    shop_ids: list[str] | None = None
    page_size: int = Field(default=50, ge=1, le=200)

    @field_validator("account_key", "actor")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PackageSyncRowResult(BaseModel):
    source_row_number: int
    package_sn: str = ""
    outcome: str
    action: str
    reason: str = ""


class PackageSyncReport(BaseModel):
    actor: str
    account_key: str
    total_in_sellfox: int | None = None
    input_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    unmatched_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    sync_status: str = "running"
    run_errors: list[str] = Field(default_factory=list)
    row_results: list[PackageSyncRowResult] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None

    @property
    def is_reconciled(self) -> bool:
        return self.input_count == (
            self.success_count
            + self.skipped_count
            + self.failed_count
            + self.unmatched_count
        )

    @property
    def remaining_count(self) -> int | None:
        if self.total_in_sellfox is None:
            return None
        return max(self.total_in_sellfox - self.input_count, 0)


class SyncPackagesService:
    """Fetch all package pages and persist every valid row with reconciliation."""

    def __init__(
        self,
        gateway: PackagePageGateway,
        repository: PackageWriter,
    ):
        self.gateway = gateway
        self.repository = repository

    def sync(self, request: PackageSyncRequest) -> PackageSyncReport:
        report = PackageSyncReport(
            actor=request.actor,
            account_key=request.account_key,
            started_at=datetime.now(timezone.utc),
        )
        page_no = 1
        processed_rows = 0

        while True:
            try:
                page = self.gateway.fetch_package_page(
                    date_start=request.date_start,
                    date_end=request.date_end,
                    status=request.status,
                    shop_ids=request.shop_ids,
                    page_no=page_no,
                    page_size=request.page_size,
                )
            except Exception:
                report.sync_status = "partial_failed"
                report.run_errors.append(f"page {page_no}: gateway error")
                report.finished_at = datetime.now(timezone.utc)
                return report
            report.total_in_sellfox = page.total_size
            page_offset = processed_rows
            page_input_count = len(page.records) + len(page.errors)

            for error in page.errors:
                report.input_count += 1
                report.failed_count += 1
                report.row_results.append(
                    PackageSyncRowResult(
                        source_row_number=page_offset + error.row_index,
                        package_sn=error.package_sn,
                        outcome="failed",
                        action="parse",
                        reason=error.reason,
                    )
                )

            for fallback_index, record in enumerate(page.records, start=1):
                source_row_index = record.source_row_index or fallback_index
                report.input_count += 1
                if record.account_key != request.account_key:
                    report.failed_count += 1
                    report.row_results.append(
                        PackageSyncRowResult(
                            source_row_number=page_offset + source_row_index,
                            package_sn=record.package_sn,
                            outcome="failed",
                            action="validate",
                            reason="account mismatch",
                        )
                    )
                    continue
                try:
                    outcome = self.repository.upsert(record)
                except Exception:
                    report.failed_count += 1
                    report.row_results.append(
                        PackageSyncRowResult(
                            source_row_number=page_offset + source_row_index,
                            package_sn=record.package_sn,
                            outcome="failed",
                            action="persist",
                            reason="persistence error",
                        )
                    )
                    continue

                report.success_count += 1
                action = "created" if outcome.created else "updated"
                if outcome.created:
                    report.created_count += 1
                else:
                    report.updated_count += 1
                report.row_results.append(
                    PackageSyncRowResult(
                        source_row_number=page_offset + source_row_index,
                        package_sn=record.package_sn,
                        outcome="success",
                        action=action,
                    )
                )

            processed_rows += page_input_count
            if processed_rows >= page.total_size:
                break
            if page_input_count == 0:
                report.sync_status = "partial_failed"
                report.run_errors.append(
                    f"page {page_no}: empty page before total_size"
                )
                report.finished_at = datetime.now(timezone.utc)
                return report
            page_no += 1

        report.row_results.sort(key=lambda row: row.source_row_number)
        report.sync_status = "completed"
        report.finished_at = datetime.now(timezone.utc)
        if not report.is_reconciled:
            raise RuntimeError("package sync report failed reconciliation")
        return report
