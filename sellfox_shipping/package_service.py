"""Application service for read-only Sellfox package synchronization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from sellfox_shipping.package_models import (
    PackageListItem,
    PackageListResult,
    SellfoxPackagePage,
)
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

    def append_audit_event(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        summary: str = "",
    ) -> int: ...


class PackageReader(Protocol):
    def list_packages(
        self,
        *,
        account_key: str,
        package_status: str | None = None,
        channel_name: str | None = None,
        local_review_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PackageListItem]: ...

    def count_packages(
        self,
        *,
        account_key: str,
        package_status: str | None = None,
        channel_name: str | None = None,
        local_review_status: str | None = None,
    ) -> int: ...

    def set_local_review_status(
        self,
        *,
        account_key: str,
        package_sn: str,
        local_review_status: str,
    ): ...

    def append_audit_event(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        summary: str = "",
    ) -> int: ...


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


class PackageListRequest(BaseModel):
    account_key: str
    package_status: str | None = None
    channel_name: str | None = None
    local_review_status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @field_validator("account_key")
    @classmethod
    def reject_blank_account(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PackageReviewRequest(BaseModel):
    account_key: str
    package_sn: str
    actor: str
    decision: str
    note: str = ""

    @field_validator("account_key", "package_sn", "actor")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"approved", "rejected", "pending"}:
            raise ValueError("decision must be approved, rejected, or pending")
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


def _redact_gateway_error(exc: Exception) -> str:
    """Keep status/type for operators; never echo response bodies or tokens."""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return f"{type(exc).__name__} http_{status_code}"
    return type(exc).__name__


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
            except Exception as exc:
                report.sync_status = "partial_failed"
                report.run_errors.append(
                    f"page {page_no}: gateway error ({_redact_gateway_error(exc)})"
                )
                report.finished_at = datetime.now(timezone.utc)
                self._write_audit(request, report)
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
                self._write_audit(request, report)
                return report
            page_no += 1

        report.row_results.sort(key=lambda row: row.source_row_number)
        report.sync_status = "completed"
        report.finished_at = datetime.now(timezone.utc)
        self._write_audit(request, report)
        if not report.is_reconciled:
            raise RuntimeError("package sync report failed reconciliation")
        return report

    def _write_audit(
        self,
        request: PackageSyncRequest,
        report: PackageSyncReport,
    ) -> None:
        summary = json.dumps(
            {
                "sync_status": report.sync_status,
                "input_count": report.input_count,
                "success_count": report.success_count,
                "failed_count": report.failed_count,
                "created_count": report.created_count,
                "updated_count": report.updated_count,
                "total_in_sellfox": report.total_in_sellfox,
            },
            ensure_ascii=False,
        )
        try:
            self.repository.append_audit_event(
                actor=request.actor,
                action="packages.sync",
                entity_type="account",
                entity_id=request.account_key,
                summary=summary,
            )
        except Exception:
            # Audit must not discard an already-built sync report.
            report.run_errors.append("audit write failed")


class ListPackagesService:
    """Read local package summaries for review CLI/REST."""

    def __init__(self, repository: PackageReader):
        self.repository = repository

    def list(self, request: PackageListRequest) -> PackageListResult:
        items = self.repository.list_packages(
            account_key=request.account_key,
            package_status=request.package_status,
            channel_name=request.channel_name,
            local_review_status=request.local_review_status,
            limit=request.limit,
            offset=request.offset,
        )
        total = self.repository.count_packages(
            account_key=request.account_key,
            package_status=request.package_status,
            channel_name=request.channel_name,
            local_review_status=request.local_review_status,
        )
        return PackageListResult(total=total, items=items)


class ReviewPackageService:
    """Record local review decisions before Excel export (P1B)."""

    def __init__(self, repository: PackageReader):
        self.repository = repository

    def review(self, request: PackageReviewRequest):
        record = self.repository.set_local_review_status(
            account_key=request.account_key,
            package_sn=request.package_sn,
            local_review_status=request.decision,
        )
        summary = json.dumps(
            {
                "decision": request.decision,
                "note": request.note,
                "package_sn": request.package_sn,
            },
            ensure_ascii=False,
        )
        self.repository.append_audit_event(
            actor=request.actor,
            action="packages.review",
            entity_type="package",
            entity_id=request.package_sn,
            summary=summary,
        )
        return record
