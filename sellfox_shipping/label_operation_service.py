"""Read-only label-operation projections for CLI and future MCP tools."""

from __future__ import annotations

from typing import Any

from sellfox_shipping.package_repository import (
    LabelOperationRecord,
    PackageRepository,
    ShippingLabelRecord,
)


class LabelOperationQueryService:
    def __init__(self, repository: PackageRepository):
        self._repo = repository

    def list(
        self,
        *,
        account_key: str | None = None,
        package_sn: str | None = None,
        status: str | None = None,
        carrier: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        operations = self._repo.list_label_operations(
            account_key=account_key,
            package_sn=package_sn,
            status=status,
            carrier=carrier,
            limit=limit,
        )
        package_sns = self._repo.get_package_sns_by_db_ids(
            {operation.package_id for operation in operations}
        )
        return [
            self._operation_summary(
                operation, package_sn=package_sns.get(operation.package_id, "")
            )
            for operation in operations
        ]

    def show(self, operation_id: int) -> dict[str, Any]:
        try:
            operation = self._repo.get_label_operation(operation_id)
        except RuntimeError as exc:
            if str(exc) != f"label operation not found: {operation_id}":
                raise
            raise LookupError(str(exc)) from exc
        result = self._operation_summary(
            operation,
            package_sn=self._repo.get_package_sn_by_db_id(operation.package_id) or "",
        )
        label = self._repo.get_label_for_operation(operation_id)
        result["label"] = self._label_summary(label) if label else None
        artifact = (
            self._repo.get_artifact(label.artifact_id)
            if label is not None and label.artifact_id is not None
            else None
        )
        result["artifact"] = (
            {
                "id": artifact.id,
                "kind": artifact.kind,
                "file_name": artifact.file_name,
                "mime_type": artifact.mime_type,
                "file_size": artifact.file_size,
            }
            if artifact is not None
            else None
        )
        return result

    def _operation_summary(
        self, operation: LabelOperationRecord, *, package_sn: str
    ) -> dict[str, Any]:
        return {
            "id": operation.id,
            "account_key": operation.account_key,
            "package_id": operation.package_id,
            "package_sn": package_sn,
            "generation": operation.generation,
            "carrier": operation.carrier,
            "service_level": operation.service_level,
            "status": operation.status,
            "provider_order_id": operation.provider_order_id,
            "tracking_number": operation.tracking_number,
            "attempt_count": operation.attempt_count,
            "error_class": operation.error_class,
            "created_by": operation.created_by,
            "created_at": _isoformat(operation.created_at),
            "updated_at": _isoformat(operation.updated_at),
            "allowed_actions": _allowed_actions(operation),
        }

    @staticmethod
    def _label_summary(label: ShippingLabelRecord) -> dict[str, Any]:
        return {
            "id": label.id,
            "status": label.status,
            "is_active": label.is_active,
            "tracking_number": label.tracking_number,
            "artifact_id": label.artifact_id,
        }


def _allowed_actions(operation: LabelOperationRecord) -> list[str]:
    if (
        operation.status in {"ACCEPTED", "LABEL_PENDING"}
        and operation.provider_order_id
    ):
        return ["resume"]
    if operation.status in {"RESERVED", "SENT", "UNKNOWN_BLOCKED"}:
        return ["investigate"]
    if operation.status in {"ACCEPTED", "LABEL_PENDING"}:
        return ["investigate"]
    return []


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
