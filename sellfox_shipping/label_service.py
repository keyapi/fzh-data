"""Carrier-agnostic label creation service.

Dispatches to carrier-specific shipment services (VITE, Lizard, etc.)
and persists results to the shipping_labels table.
"""

from __future__ import annotations

import os
from typing import Any

from sellfox_shipping.package_models import SellfoxPackageRecord

ARTIFACT_KIND = "vite_label"


class LabelServiceError(RuntimeError):
    """Label creation failed for a known reason (bad dims, missing creds, etc.)."""

    def __init__(self, message: str, *, http_status: int = 502):
        super().__init__(message)
        self.http_status = http_status


def _read_env(key: str) -> str:
    val = (os.getenv(key) or "").strip()
    return val


def _load_config() -> dict:
    from pathlib import Path
    import yaml

    config_path = Path(__file__).resolve().parent / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class LabelService:
    """Create labels via carrier APIs and store results.

    Usage::

        from sellfox_shipping.label_service import LabelService
        from sellfox_shipping.package_repository import PackageRepository

        repo = PackageRepository("data/shipping.db")
        service = LabelService(repo)
        label = service.create_label(
            package=record,
            account_key="sellfox-main",
            carrier="vite",
            actor="web-user",
        )
    """

    def __init__(self, repo: Any) -> None:
        from sellfox_shipping.package_repository import PackageRepository

        self._repo: PackageRepository = repo
        self._cfg = _load_config()

    def create_label(
        self,
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        carrier: str,
        actor: str,
        service_level: str = "",
        channel: str = "",
    ) -> dict[str, Any]:
        """Create a shipping label for a package.

        Returns a dict with keys: id, tracking_number, carrier_order_id,
        label_url, artifact_id, status, total_amount, carrier, service_level.
        """
        carrier = (carrier or "").strip().lower()
        if not carrier:
            raise LabelServiceError("carrier is required", http_status=400)
        if carrier not in ("vite", "lizard"):
            raise LabelServiceError(
                f"Unknown carrier '{carrier}'. Available: vite, lizard",
                http_status=400,
            )

        sn = package.package_sn

        # Prevent duplicate active labels
        existing = self._repo.list_labels_for_package(
            account_key=account_key, package_sn=sn
        )
        for lbl in existing:
            if lbl.status != "cancelled":
                raise LabelServiceError(
                    f"已存在有效面单 (追踪号: {lbl.tracking_number}, 承运商: {lbl.carrier})。"
                    f"请先取消现有面单后再创建新的。",
                    http_status=409,
                )

        # Resolve dims
        db_id = self._repo.get_package_db_id(account_key, sn)
        if db_id is None:
            raise LabelServiceError(
                f"Package {sn} not found in local store", http_status=404
            )
        dims = self._repo.get_package_dims(db_id)

        if carrier == "vite":
            return self._create_vite_label(
                package=package,
                account_key=account_key,
                actor=actor,
                db_id=db_id,
                dims=dims,
                service_level=service_level,
                channel=channel,
            )
        else:
            return self._create_lizard_label(
                package=package,
                account_key=account_key,
                actor=actor,
                service_level=service_level,
            )

    def get_labels_for_package(
        self, account_key: str, package_sn: str
    ) -> list[dict[str, Any]]:
        records = self._repo.list_labels_for_package(
            account_key=account_key, package_sn=package_sn
        )
        result: list[dict[str, Any]] = []
        for r in records:
            result.append({
                "id": r.id,
                "carrier": r.carrier,
                "service_level": r.service_level,
                "tracking_number": r.tracking_number,
                "carrier_order_id": r.carrier_order_id,
                "label_url": r.label_url,
                "artifact_id": r.artifact_id,
                "label_format": r.label_format,
                "total_amount": r.total_amount,
                "currency": r.currency,
                "status": r.status,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return result

    def download_label_pdf(self, label_id: int) -> tuple[bytes, str, str] | None:
        """Return (content, filename, mime_type) for a label's PDF artifact."""
        label = self._repo.get_label(label_id)
        if label is None:
            return None
        if label.artifact_id is None:
            return None
        artifact = self._repo.get_artifact(label.artifact_id)
        if artifact is None:
            return None
        path = self._repo.resolve_artifact_path(artifact)
        if not path.is_file():
            return None
        return path.read_bytes(), artifact.file_name, artifact.mime_type or "application/pdf"

    def cancel_label(self, label_id: int, *, actor: str = "") -> dict[str, Any]:
        """Cancel a label via carrier API and update local status."""
        label = self._repo.get_label(label_id)
        if label is None:
            raise LabelServiceError(f"Label {label_id} not found", http_status=404)
        if label.status == "cancelled":
            raise LabelServiceError(f"Label {label_id} already cancelled", http_status=409)

        if label.carrier == "vite":
            return self._cancel_vite_label(label, actor)
        else:
            raise LabelServiceError(
                f"Cancel not supported for carrier '{label.carrier}'",
                http_status=501,
            )

    def _cancel_vite_label(
        self, label: Any, actor: str
    ) -> dict[str, Any]:
        from sellfox_shipping.carriers.vite.client import ViteGofoClient, ViteClientError

        api_key = _read_env("VITE_API_KEY")
        if not api_key:
            raise LabelServiceError("VITE_API_KEY not configured", http_status=503)
        vite_base = _read_env("VITE_API_BASE_URL") or "https://api.vitedirect.com"

        ref = label.carrier_order_id or label.request_id
        if not ref:
            raise LabelServiceError("No carrier_order_id or request_id to cancel", http_status=400)

        with ViteGofoClient(api_key=api_key, base_url=vite_base) as client:
            try:
                result = client.cancel_label(ref)
            except ViteClientError as exc:
                raise LabelServiceError(
                    f"VITE cancel failed: {exc}", http_status=502
                ) from exc

        self._repo.update_label_status(label.id, "cancelled")
        self._repo.append_audit_event(
            actor=actor or "system",
            action="labels.cancel",
            entity_type="shipping_label",
            entity_id=str(label.id),
            summary=f"cancelled {label.carrier} order={ref}",
        )
        return {
            "id": label.id,
            "status": "cancelled",
            "message": result.get("message", "Cancelled"),
        }

    def list_enabled_carriers(self) -> list[dict[str, str]]:
        """Return carriers with enabled=true from config."""
        carriers = self._cfg.get("carriers", {})
        result: list[dict[str, str]] = []
        for name, cfg in carriers.items():
            if cfg.get("enabled") and name in ("vite", "lizard"):
                result.append({
                    "name": name,
                    "label": cfg.get("label", name.upper()),
                })
        return result

    # ── private ────────────────────────────────────────────────────

    def _create_vite_label(
        self,
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        actor: str,
        db_id: int,
        dims: Any,
        service_level: str,
        channel: str,
    ) -> dict[str, Any]:
        from sellfox_shipping.carriers.vite.client import (
            ViteGofoClient,
            ViteClientError,
        )
        from sellfox_shipping.carriers.vite.shipment import ViteShipmentService

        api_key = _read_env("VITE_API_KEY")
        if not api_key:
            raise LabelServiceError(
                "VITE_API_KEY not configured. Set it in .env", http_status=503
            )
        vite_base = _read_env("VITE_API_BASE_URL") or "https://test-api.vitedirect.com"

        dims_dict = None
        if dims is not None:
            dims_dict = {
                "weight_kg": dims.weight_kg,
                "length_cm": dims.length_cm,
                "width_cm": dims.width_cm,
                "height_cm": dims.height_cm,
            }

        warehouses_cfg = self._cfg.get("warehouses", {})

        with ViteGofoClient(api_key=api_key, base_url=vite_base) as client:
            svc = ViteShipmentService(
                client,
                self._repo,
                warehouses_cfg=warehouses_cfg,
            )
            try:
                result = svc.ship_package(
                    package,
                    account_key=account_key,
                    actor=actor,
                    service_type=service_level or "GOFO_PARCEL",
                    channel=channel or "GFUS",
                    package_dims=dims_dict,
                )
            except ViteClientError as exc:
                msg = str(exc)
                status = getattr(exc, "status_code", None) or 502
                if status == 401:
                    raise LabelServiceError(
                        f"VITE authentication failed: {msg}", http_status=502
                    ) from exc
                raise LabelServiceError(
                    f"VITE API error: {msg}", http_status=502
                ) from exc

        # Return the persisted label record
        labels = self._repo.list_labels_for_package(
            account_key=account_key, package_sn=package.package_sn, limit=1
        )
        if labels:
            r = labels[0]
            return {
                "id": r.id,
                "tracking_number": result.tracking_number,
                "carrier_order_id": result.order_id,
                "label_url": result.label_url,
                "artifact_id": result.artifact_id,
                "status": r.status,
                "total_amount": result.total_amount,
                "carrier": "vite",
                "service_level": service_level or "GOFO_PARCEL",
            }
        raise LabelServiceError("Label created but not found in store", http_status=500)

    def _create_lizard_label(
        self,
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        actor: str,
        service_level: str,
    ) -> dict[str, Any]:
        from sellfox_shipping.carriers.lizard.api_client import LizardApiClient, LizardApiError
        from sellfox_shipping.carriers.lizard.api_shipment import LizardApiShipmentService

        app_token = _read_env("YIGLOBAL_APP_TOKEN")
        app_key = _read_env("YIGLOBAL_APP_KEY")
        if not app_token or not app_key:
            raise LabelServiceError(
                "YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY not configured", http_status=503
            )
        lizard_base = _read_env("YIGLOBAL_API_BASE_URL") or "http://47.106.72.196"

        # Determine sm_code: user selection > rate history > default
        sm_code = (service_level or "").strip()
        db_id = self._repo.get_package_db_id(account_key, package.package_sn)
        if not sm_code and db_id:
            rates = self._repo.list_package_rates(db_id, limit=10)
            for r in rates:
                if r.carrier == "lizard" and r.channel:
                    sm_code = r.channel
                    break
        if not sm_code:
            sm_code = "FedEx-Ground-J-TX"

        # Fill logistics dims from DB if Sellfox data is missing
        if db_id and package.logistics.weight_grams <= 0:
            dims = self._repo.get_package_dims(db_id)
            if dims:
                package = package.model_copy(update={
                    "logistics": package.logistics.model_copy(update={
                        "weight_grams": dims.weight_kg * 1000,
                        "length_cm": dims.length_cm,
                        "width_cm": dims.width_cm,
                        "height_cm": dims.height_cm,
                    })
                })

        with LizardApiClient(
            app_token=app_token,
            app_key=app_key,
            base_url=lizard_base,
        ) as client:
            svc = LizardApiShipmentService(client, self._repo)
            try:
                result = svc.ship_package(
                    package,
                    account_key=account_key,
                    actor=actor,
                    sm_code=sm_code,
                )
            except (LizardApiError, TimeoutError, RuntimeError) as exc:
                raise LabelServiceError(
                    f"Lizard API error: {exc}", http_status=502
                ) from exc

        # Insert label record (LizardApiShipmentService doesn't auto-insert)
        label_rec = self._repo.insert_label(
            account_key=account_key,
            package_db_id=db_id or 0,
            carrier="lizard",
            service_level=sm_code,
            tracking_number=result.tracking_number,
            carrier_order_id=result.order_code,
            request_id="",
            label_url=result.label_url,
            artifact_id=result.artifact_id,
            total_amount=None,
            currency="USD",
            status="generated",
            carrier_response_json="",
            created_by=actor,
        )
        return {
            "id": label_rec.id,
            "tracking_number": result.tracking_number,
            "carrier_order_id": result.order_code,
            "label_url": result.label_url,
            "artifact_id": result.artifact_id,
            "status": "generated",
            "total_amount": None,
            "carrier": "lizard",
            "service_level": sm_code,
        }
