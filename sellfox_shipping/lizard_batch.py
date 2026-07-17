"""P1B services: export lizard upload Excel; parse tracking return against local DB."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

from sellfox_shipping.carriers.lizard.dims import DimsLookup
from sellfox_shipping.carriers.lizard.spreadsheet import (
    LIZARD_TEMPLATE_VERSION,
    SHIPPER_CODE_DEFAULT,
    TrackingReturnParseResult,
    UploadBuildResult,
    build_upload_dataframe,
    parse_tracking_return,
    write_upload_xlsx,
)
from sellfox_shipping.package_models import PackageListItem, SellfoxPackageRecord


class PackageExportReader(Protocol):
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

    def get(self, account_key: str, package_sn: str) -> SellfoxPackageRecord | None: ...

    def append_audit_event(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        summary: str = "",
    ) -> int: ...


class LizardExportRequest(BaseModel):
    account_key: str
    actor: str
    output_path: Path
    channel_name_contains: str = "蜴"
    local_review_status: str = "approved"
    limit: int = 500
    shipper_code: str = SHIPPER_CODE_DEFAULT

    @field_validator("actor")
    @classmethod
    def _actor_required(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("actor is required")
        return value.strip()


class LizardExportResult(BaseModel):
    template_version: str
    output_path: str
    file_sha256: str
    total_candidates: int
    exported: int
    skipped: int
    skipped_rows: list[dict] = Field(default_factory=list)


class ExportLizardUploadService:
    def __init__(self, reader: PackageExportReader, dims_lookup: DimsLookup):
        self._reader = reader
        self._dims = dims_lookup

    def export(self, request: LizardExportRequest) -> LizardExportResult:
        summaries = self._reader.list_packages(
            account_key=request.account_key,
            local_review_status=request.local_review_status,
            limit=request.limit,
            offset=0,
        )
        needle = (request.channel_name_contains or "").strip()
        packages: list[SellfoxPackageRecord] = []
        for item in summaries:
            if needle and needle not in (item.channel_name or ""):
                continue
            full = self._reader.get(request.account_key, item.package_sn)
            if full is not None:
                packages.append(full)

        # Prefetch when lookup supports it
        prefetch = getattr(self._dims, "prefetch", None)
        if callable(prefetch):
            skus = [
                it.commodity_sku
                for pkg in packages
                for it in pkg.items
                if it.commodity_sku
            ]
            prefetch(skus)

        built: UploadBuildResult = build_upload_dataframe(
            packages,
            dims_lookup=self._dims,
            shipper_code=request.shipper_code,
        )
        path = write_upload_xlsx(built.dataframe, request.output_path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self._reader.append_audit_event(
            actor=request.actor,
            action="lizard.upload_export",
            entity_type="batch",
            entity_id=digest[:16],
            summary=(
                f"exported={built.exported} skipped={built.skipped} "
                f"template={LIZARD_TEMPLATE_VERSION} path={path.name}"
            ),
        )
        return LizardExportResult(
            template_version=built.template_version,
            output_path=str(path),
            file_sha256=digest,
            total_candidates=len(packages),
            exported=built.exported,
            skipped=built.skipped,
            skipped_rows=[
                {"package_sn": r.package_sn, "reason": r.reason}
                for r in built.skipped_rows
            ],
        )


class LizardImportRequest(BaseModel):
    account_key: str
    actor: str
    input_path: Path

    @field_validator("actor")
    @classmethod
    def _actor_required(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("actor is required")
        return value.strip()


class LizardImportResult(BaseModel):
    total: int
    matched: int
    unmatched: int
    matched_rows: list[dict] = Field(default_factory=list)
    unmatched_rows: list[dict] = Field(default_factory=list)
    parsed_at: str = ""


class ImportLizardTrackingService:
    """Parse return Excel and reconcile against known local package_sn values.

    Does not write tracking back to Sellfox yet (P1C). Persists audit only.
    """

    def __init__(self, reader: PackageExportReader):
        self._reader = reader

    def import_file(self, request: LizardImportRequest) -> LizardImportResult:
        known = {
            item.package_sn
            for item in self._reader.list_packages(
                account_key=request.account_key,
                limit=10_000,
                offset=0,
            )
        }
        parsed: TrackingReturnParseResult = parse_tracking_return(
            request.input_path,
            known_package_sns=known,
        )
        result = LizardImportResult(
            total=parsed.total,
            matched=parsed.matched,
            unmatched=parsed.unmatched,
            matched_rows=[
                {
                    "package_sn": r.package_sn,
                    "tracking_number": r.tracking_number,
                    "carrier_order_no": r.carrier_order_no,
                    "freight": r.freight,
                    "delivery_style": r.delivery_style,
                }
                for r in parsed.rows
                if r.matched
            ],
            unmatched_rows=[
                {
                    "package_sn": r.package_sn,
                    "tracking_number": r.tracking_number,
                    "row_index": r.row_index,
                }
                for r in parsed.unmatched_rows
            ],
            parsed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._reader.append_audit_event(
            actor=request.actor,
            action="lizard.tracking_import",
            entity_type="batch",
            entity_id=Path(request.input_path).name,
            summary=f"matched={result.matched} unmatched={result.unmatched} total={result.total}",
        )
        return result
