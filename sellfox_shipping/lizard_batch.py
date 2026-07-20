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
from sellfox_shipping.package_repository import ArtifactRecord


ARTIFACT_KIND_UPLOAD_EXPORT = "lizard_upload_export"
ARTIFACT_KIND_TRACKING_IMPORT = "lizard_tracking_import"


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

    def set_tracking_number(
        self,
        *,
        account_key: str,
        package_sn: str,
        tracking_number: str,
        estimated_cost: float | None = None,
        cost_currency: str | None = None,
    ) -> SellfoxPackageRecord: ...

    def register_artifact(
        self,
        *,
        account_key: str,
        kind: str,
        file_name: str,
        content: bytes,
        actor: str,
        template_version: str = "",
        virtual_folder: str = "",
        mime_type: str = "",
        summary: str = "",
    ) -> ArtifactRecord: ...

    def create_export_batch(
        self,
        *,
        account_key: str,
        actor: str,
        template_version: str,
        export_artifact_id: int | None,
        exported_package_sns: list[str],
        skipped_rows: list[dict],
        summary: str = "",
    ): ...

    def apply_import_to_batch(
        self,
        *,
        batch_id: int,
        import_artifact_id: int | None,
        matched_sns: list[str],
        conflict_sns: list[str],
        unmatched_sns: list[str],
        actor: str,
        summary: str = "",
    ): ...


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
    file_md5: str
    total_candidates: int
    exported: int
    skipped: int
    skipped_rows: list[dict] = Field(default_factory=list)
    artifact_id: int | None = None
    batch_id: int | None = None


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
        content = path.read_bytes()
        digest = hashlib.md5(content, usedforsecurity=False).hexdigest()
        summary = (
            f"exported={built.exported} skipped={built.skipped} "
            f"template={LIZARD_TEMPLATE_VERSION}"
        )
        artifact = self._reader.register_artifact(
            account_key=request.account_key,
            kind=ARTIFACT_KIND_UPLOAD_EXPORT,
            file_name=path.name,
            content=content,
            actor=request.actor,
            template_version=LIZARD_TEMPLATE_VERSION,
            virtual_folder="lizard/export",
            summary=summary,
        )
        skipped_payload = [
            {"package_sn": r.package_sn, "reason": r.reason}
            for r in built.skipped_rows
        ]
        exported_sns = [
            str(v)
            for v in built.dataframe["参考编号/Reference Code"].tolist()
        ] if built.exported else []
        batch = self._reader.create_export_batch(
            account_key=request.account_key,
            actor=request.actor,
            template_version=LIZARD_TEMPLATE_VERSION,
            export_artifact_id=artifact.id,
            exported_package_sns=exported_sns,
            skipped_rows=skipped_payload,
            summary=summary,
        )
        self._reader.append_audit_event(
            actor=request.actor,
            action="lizard.upload_export",
            entity_type="artifact",
            entity_id=str(artifact.id),
            summary=f"{summary} path={path.name} batch={batch.id}",
        )
        return LizardExportResult(
            template_version=built.template_version,
            output_path=str(path),
            file_md5=digest,
            total_candidates=len(packages),
            exported=built.exported,
            skipped=built.skipped,
            skipped_rows=skipped_payload,
            artifact_id=artifact.id,
            batch_id=batch.id,
        )


class LizardImportRequest(BaseModel):
    account_key: str
    actor: str
    input_path: Path
    batch_id: int | None = None

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
    persisted: int = 0
    conflicts: int = 0
    matched_rows: list[dict] = Field(default_factory=list)
    unmatched_rows: list[dict] = Field(default_factory=list)
    conflict_rows: list[dict] = Field(default_factory=list)
    parsed_at: str = ""
    artifact_id: int | None = None
    batch_id: int | None = None


class ImportLizardTrackingService:
    """Parse return Excel, reconcile by package_sn, persist tracking locally.

    Does **not** call Sellfox submitToPlatform (P1C).
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
        input_path = Path(request.input_path)
        content = input_path.read_bytes()
        parsed: TrackingReturnParseResult = parse_tracking_return(
            input_path,
            known_package_sns=known,
        )
        persisted = 0
        conflicts: list[dict] = []
        matched_rows: list[dict] = []
        for row in parsed.rows:
            if not row.matched:
                continue
            existing = self._reader.get(request.account_key, row.package_sn)
            prior = (existing.logistics.tracking_number if existing else "") or ""
            # Sellfox often mirrors packageSn into trackNo before real carrier TN exists.
            prior_is_placeholder = (not prior) or prior == row.package_sn
            entry = {
                "package_sn": row.package_sn,
                "tracking_number": row.tracking_number,
                "carrier_order_no": row.carrier_order_no,
                "freight": row.freight,
                "delivery_style": row.delivery_style,
            }
            if not prior_is_placeholder and prior != row.tracking_number:
                entry["conflict_with"] = prior
                conflicts.append(entry)
                matched_rows.append(entry)
                continue
            self._reader.set_tracking_number(
                account_key=request.account_key,
                package_sn=row.package_sn,
                tracking_number=row.tracking_number,
                estimated_cost=row.freight,
            )
            persisted += 1
            entry["persisted"] = True
            matched_rows.append(entry)

        summary = (
            f"matched={parsed.matched} persisted={persisted} "
            f"conflicts={len(conflicts)} unmatched={parsed.unmatched}"
        )
        artifact = self._reader.register_artifact(
            account_key=request.account_key,
            kind=ARTIFACT_KIND_TRACKING_IMPORT,
            file_name=input_path.name,
            content=content,
            actor=request.actor,
            virtual_folder="lizard/import",
            summary=summary,
        )
        batch_id = request.batch_id
        if batch_id is not None:
            matched_sns = [
                r["package_sn"]
                for r in matched_rows
                if r.get("persisted")
            ]
            conflict_sns = [r["package_sn"] for r in conflicts]
            unmatched_sns = [r.package_sn for r in parsed.unmatched_rows]
            self._reader.apply_import_to_batch(
                batch_id=batch_id,
                import_artifact_id=artifact.id,
                matched_sns=matched_sns,
                conflict_sns=conflict_sns,
                unmatched_sns=unmatched_sns,
                actor=request.actor,
                summary=summary,
            )
        result = LizardImportResult(
            total=parsed.total,
            matched=parsed.matched,
            unmatched=parsed.unmatched,
            persisted=persisted,
            conflicts=len(conflicts),
            matched_rows=matched_rows,
            unmatched_rows=[
                {
                    "package_sn": r.package_sn,
                    "tracking_number": r.tracking_number,
                    "row_index": r.row_index,
                }
                for r in parsed.unmatched_rows
            ],
            conflict_rows=conflicts,
            parsed_at=datetime.now(timezone.utc).isoformat(),
            artifact_id=artifact.id,
            batch_id=batch_id,
        )
        self._reader.append_audit_event(
            actor=request.actor,
            action="lizard.tracking_import",
            entity_type="artifact",
            entity_id=str(artifact.id),
            summary=summary + (f" batch={batch_id}" if batch_id else ""),
        )
        return result
