"""Carrier-agnostic label creation service.

Dispatches to carrier-specific shipment services (VITE, Lizard, etc.)
and persists results to the shipping_labels table.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from typing import Any

from sellfox_shipping.package_models import SellfoxPackageRecord

ARTIFACT_KIND = "vite_label"


@dataclass(frozen=True)
class LabelPreflightResult:
    package_db_id: int
    carrier: str
    service_level: str
    weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float


class LabelServiceError(RuntimeError):
    """Label creation failed for a known reason (bad dims, missing creds, etc.)."""

    def __init__(self, message: str, *, http_status: int = 502, failure: Any = None):
        super().__init__(message)
        self.http_status = http_status
        self.failure = failure


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

    def preflight(
        self,
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        carrier: str,
        actor: str,
        service_level: str = "",
    ) -> LabelPreflightResult:
        errors: list[str] = []

        if not (actor or "").strip():
            errors.append("actor is required")

        carrier_norm = (carrier or "").strip().lower()
        if carrier_norm not in ("vite", "lizard"):
            errors.append(f"Unknown carrier '{carrier}'. Available: vite, lizard")

        sn = (package.package_sn or "").strip()
        if not sn:
            errors.append("package_sn is required")

        db_id = self._repo.get_package_db_id(account_key, sn)
        if db_id is None:
            errors.append(f"Package {sn} not found in local store")

        local = self._repo.get(account_key, sn) if db_id is not None else None
        if local is not None and (local.local_review_status or "").strip() != "approved":
            errors.append(
                "Package local_review_status must be 'approved' before creating a label"
            )

        if db_id is not None:
            dims = self._repo.get_package_dims(db_id)
            if dims is None:
                errors.append("No dimensions available for package")
            else:
                w = dims.weight_kg or 0
                l = dims.length_cm or 0
                wd = dims.width_cm or 0
                h = dims.height_cm or 0
                if w <= 0 or l <= 0 or wd <= 0 or h <= 0:
                    errors.append(
                        f"Invalid dimensions: weight={w}kg length={l}cm "
                        f"width={wd}cm height={h}cm"
                    )
        else:
            dims = None

        addr = package.address
        if not (addr.name or "").strip():
            errors.append("Recipient name is required")
        if not (addr.address_line_1 or "").strip():
            errors.append("Recipient address_line_1 is required")
        if not (addr.city or "").strip():
            errors.append("Recipient city is required")
        if not (addr.state_or_region or "").strip():
            errors.append("Recipient state_or_region is required")
        if not (addr.postal_code or "").strip():
            errors.append("Recipient postal_code is required")
        phone = (addr.phone or addr.mobile or "").strip()
        if not phone:
            errors.append("Recipient phone is required")

        if carrier_norm == "vite":
            wh_name = (package.logistics.warehouse_name or "").strip()
            warehouses = self._cfg.get("warehouses", {})
            wh = warehouses.get(wh_name, {}) if wh_name else {}
            if not wh:
                errors.append(f"Warehouse '{wh_name}' not found in config")
            else:
                wh_addr = wh.get("address", {})
                wh_name_val = (wh_addr.get("name") or "").strip()
                wh_addr1 = (wh_addr.get("address1") or "").strip()
                wh_city = (wh_addr.get("city") or "").strip()
                wh_state = (wh_addr.get("state") or "").strip()
                wh_zip = (wh_addr.get("postal_code") or "").strip()
                wh_phone = (wh_addr.get("phone") or "").strip()
                if not wh_name_val:
                    errors.append("VITE warehouse address.name is required")
                if not wh_addr1:
                    errors.append("VITE warehouse address.address1 is required")
                if not wh_city:
                    errors.append("VITE warehouse address.city is required")
                if not wh_state:
                    errors.append("VITE warehouse address.state is required")
                if not wh_zip:
                    errors.append("VITE warehouse address.postal_code is required")
                if not wh_phone:
                    errors.append("VITE warehouse address.phone is required")

        if errors:
            raise LabelServiceError("; ".join(errors), http_status=400)

        assert db_id is not None and dims is not None  # guarded above
        return LabelPreflightResult(
            package_db_id=db_id,
            carrier=carrier_norm,
            service_level=(service_level or "").strip(),
            weight_kg=dims.weight_kg,
            length_cm=dims.length_cm,
            width_cm=dims.width_cm,
            height_cm=dims.height_cm,
        )

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
        preflight = self.preflight(
            package=package,
            account_key=account_key,
            carrier=carrier,
            actor=actor,
            service_level=service_level,
        )
        resolved_service = preflight.service_level or service_level or (
            "GOFO_PARCEL" if preflight.carrier == "vite" else ""
        )
        request_hash = self._canonical_request_hash(
            package=package,
            account_key=account_key,
            carrier=preflight.carrier,
            service_level=resolved_service,
            channel=channel,
            weight_kg=preflight.weight_kg,
            length_cm=preflight.length_cm,
            width_cm=preflight.width_cm,
            height_cm=preflight.height_cm,
        )
        idempotency_key = (
            f"{package.package_sn}:{preflight.carrier}:"
            f"{resolved_service}:{request_hash[:16]}"
        )

        try:
            operation = self._repo.claim_label_operation(
                account_key=account_key,
                package_db_id=preflight.package_db_id,
                carrier=preflight.carrier,
                service_level=resolved_service,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                actor=actor,
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "active label exists" in msg:
                raise LabelServiceError(
                    "已存在有效面单，不允许重复创建", http_status=409
                ) from exc
            if "active label operation exists" in msg:
                # No valid label, but a stale operation is blocking the claim.
                # Auto-release it and retry once so re-creation works without
                # manual cleanup (carrier will still reject a true duplicate
                # order via reference_no).
                released = self._repo.release_active_label_operation(
                    package_db_id=preflight.package_db_id, actor=actor
                )
                if released == 0:
                    raise LabelServiceError(msg, http_status=409) from exc
                try:
                    operation = self._repo.claim_label_operation(
                        account_key=account_key,
                        package_db_id=preflight.package_db_id,
                        carrier=preflight.carrier,
                        service_level=resolved_service,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        actor=actor,
                    )
                except RuntimeError as exc2:
                    raise LabelServiceError(str(exc2), http_status=409) from exc2
            else:
                raise LabelServiceError(msg, http_status=409) from exc

        self._repo.transition_label_operation(operation.id, status="SENT")

        try:
            if preflight.carrier == "vite":
                result = self._create_vite_label(
                    package=package,
                    account_key=account_key,
                    actor=actor,
                    db_id=preflight.package_db_id,
                    dims=self._repo.get_package_dims(preflight.package_db_id),
                    service_level=resolved_service,
                    channel=channel,
                    operation_id=operation.id,
                )
            else:
                result = self._create_lizard_label(
                    package=package,
                    account_key=account_key,
                    actor=actor,
                    service_level=resolved_service,
                    operation_id=operation.id,
                )
        except LabelServiceError as exc:
            self._fail_or_preserve_pending(operation.id, exc)
            raise
        except ValueError as exc:
            self._fail_or_preserve_pending(
                operation.id,
                LabelServiceError(str(exc), http_status=400),
            )
            raise LabelServiceError(str(exc), http_status=400) from exc
        except Exception as exc:
            pending = self._repo.get_label_operation(operation.id)
            if pending.status == "LABEL_PENDING":
                raise LabelServiceError(
                    f"Label acquisition pending recovery "
                    f"(provider_order_id={pending.provider_order_id}): {exc}",
                    http_status=502,
                ) from exc
            self._repo.transition_label_operation(
                operation.id,
                status="UNKNOWN_BLOCKED",
                error_class="unexpected",
                error_summary=str(exc)[:500],
            )
            raise

        self._repo.finalize_label_success_with_outbox(
            operation_id=operation.id,
            label_id=int(result["id"]),
            actor=actor,
        )
        return result

    def _fail_or_preserve_pending(
        self, operation_id: int, exc: LabelServiceError
    ) -> None:
        """Classify failure unless adapter already parked the op in LABEL_PENDING."""
        current = self._repo.get_label_operation(operation_id)
        if current.status == "LABEL_PENDING":
            return
        self._fail_operation(operation_id, exc)

    @staticmethod
    def _canonical_request_hash(
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        carrier: str,
        service_level: str,
        channel: str,
        weight_kg: float,
        length_cm: float,
        width_cm: float,
        height_cm: float,
    ) -> str:
        addr = package.address
        payload = {
            "account_key": account_key,
            "package_sn": package.package_sn,
            "carrier": carrier,
            "service_level": service_level,
            "channel": channel,
            "warehouse_name": package.logistics.warehouse_name,
            "ship_to": {
                "name": addr.name,
                "address_line_1": addr.address_line_1,
                "address_line_2": addr.address_line_2,
                "city": addr.city,
                "state_or_region": addr.state_or_region,
                "postal_code": addr.postal_code,
                "phone": addr.phone or addr.mobile,
                "country_code": addr.country_code,
            },
            "dims": {
                "weight_kg": weight_kg,
                "length_cm": length_cm,
                "width_cm": width_cm,
                "height_cm": height_cm,
            },
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _fail_operation(self, operation_id: int, exc: LabelServiceError) -> None:
        from sellfox_shipping.carriers.errors import CarrierFailure

        failure = exc.failure
        if isinstance(failure, CarrierFailure):
            if failure.outcome == "not_sent":
                status = "FAILED_SAFE"
            elif failure.outcome == "rejected":
                status = "FAILED_FINAL"
            elif failure.outcome in {"retryable_query", "accepted_pending"}:
                status = "LABEL_PENDING"
            else:
                status = "UNKNOWN_BLOCKED"
            self._repo.transition_label_operation(
                operation_id,
                status=status,
                provider_order_id=failure.provider_order_id,
                tracking_number=failure.tracking_number,
                error_class=failure.category,
                error_summary=str(failure)[:500],
                increment_attempt=status == "LABEL_PENDING",
            )
            return
        if exc.http_status in (400, 404, 503):
            status = "FAILED_SAFE"
            error_class = "validation" if exc.http_status != 503 else "config"
        elif exc.http_status in (401, 403, 422):
            status = "FAILED_FINAL"
            error_class = "carrier_rejected"
        else:
            # Already SENT — ambiguous carrier outcome must block blind retry.
            status = "UNKNOWN_BLOCKED"
            error_class = "network_unknown"
        self._repo.transition_label_operation(
            operation_id,
            status=status,
            error_class=error_class,
            error_summary=str(exc)[:500],
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
        """Cancel a label via carrier API and atomically release local state."""
        from sellfox_shipping.package_repository import ACTIVE_LABEL_OPERATION_STATUSES

        label = self._repo.get_label(label_id)
        if label is None:
            raise LabelServiceError(f"Label {label_id} not found", http_status=404)

        if label.status == "cancelled":
            # Historical inconsistency: label inactive but operation still blocking.
            if label.operation_id is not None:
                op = self._repo.get_label_operation(label.operation_id)
                if op.status in ACTIVE_LABEL_OPERATION_STATUSES:
                    try:
                        self._repo.finalize_label_cancellation(
                            label_id, actor=actor or "system"
                        )
                    except RuntimeError as exc:
                        self._repo.append_audit_event(
                            actor=actor or "system",
                            action="label_operation.cancel_inconsistency",
                            entity_type="shipping_label_operation",
                            entity_id=str(label.operation_id),
                            summary=(
                                f"label_id={label_id} reconcile release failed: {exc}"
                            ),
                        )
                        raise LabelServiceError(
                            f"Cancelled label operation {label.operation_id} "
                            f"could not be released ({exc}). "
                            f"Manual repair required before reclaim.",
                            http_status=409,
                        ) from exc
                    return {
                        "id": label_id,
                        "status": "cancelled",
                        "message": "Reconciled operation release for cancelled label",
                    }
            raise LabelServiceError(
                f"Label {label_id} already cancelled", http_status=409
            )

        if label.carrier == "vite":
            carrier_message = self._request_vite_cancel(label)
        elif label.carrier == "lizard":
            carrier_message = self._request_lizard_cancel(label)
        else:
            raise LabelServiceError(
                f"Cancel not supported for carrier '{label.carrier}'",
                http_status=501,
            )

        try:
            self._repo.finalize_label_cancellation(label_id, actor=actor or "system")
        except RuntimeError as exc:
            self._repo.append_audit_event(
                actor=actor or "system",
                action="label_operation.cancel_inconsistency",
                entity_type="shipping_label_operation",
                entity_id=str(label.operation_id or ""),
                summary=(
                    f"label_id={label_id} carrier cancelled but local finalize failed: {exc}"
                ),
            )
            raise LabelServiceError(
                f"Carrier cancel succeeded, but local finalize failed ({exc}). "
                f"Manual repair required before reclaim.",
                http_status=409,
            ) from exc

        self._repo.append_audit_event(
            actor=actor or "system",
            action="labels.cancel",
            entity_type="shipping_label",
            entity_id=str(label_id),
            summary=f"cancelled {label.carrier}",
        )
        return {
            "id": label_id,
            "status": "cancelled",
            "message": carrier_message,
        }

    def _request_vite_cancel(self, label: Any) -> str:
        from sellfox_shipping.carriers.vite.client import ViteGofoClient, ViteClientError

        api_key = _read_env("VITE_API_KEY")
        if not api_key:
            raise LabelServiceError("VITE_API_KEY not configured", http_status=503)
        vite_base = _read_env("VITE_API_BASE_URL") or "https://api.vitedirect.com"

        ref = label.carrier_order_id or label.request_id
        if not ref:
            raise LabelServiceError(
                "No carrier_order_id or request_id to cancel", http_status=400
            )

        with ViteGofoClient(api_key=api_key, base_url=vite_base) as client:
            try:
                result = client.cancel_label(ref)
            except ViteClientError as exc:
                raise LabelServiceError(
                    f"VITE cancel failed: {exc}", http_status=502
                ) from exc
        return str(result.get("message", "Cancelled"))

    def _request_lizard_cancel(self, label: Any) -> str:
        from sellfox_shipping.carriers.lizard.api_client import (
            LizardApiClient,
            LizardApiError,
        )


        order_code = (label.carrier_order_id or "").strip()
        if not order_code:
            raise LabelServiceError(
                "No carrier_order_id to cancel", http_status=400
            )
        package_sn = (
            self._repo.get_package_sn_by_db_id(label.package_id) or ""
        ).strip()
        if not package_sn:
            raise LabelServiceError(
                "Unable to resolve package_sn for Lizard cancel", http_status=400
            )
        reference_no = self._lizard_reference_no(package_sn, label.operation_id)
        if not reference_no:
            raise LabelServiceError(
                "Unable to resolve reference_no for Lizard cancel", http_status=400
            )
        app_token = _read_env("YIGLOBAL_APP_TOKEN")
        app_key = _read_env("YIGLOBAL_APP_KEY")
        if not app_token or not app_key:
            raise LabelServiceError(
                "YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY not configured",
                http_status=503,
            )
        lizard_base = _read_env("YIGLOBAL_API_BASE_URL") or "http://47.106.72.196"

        with LizardApiClient(
            app_token=app_token,
            app_key=app_key,
            base_url=lizard_base,
        ) as client:
            try:
                result = client.cancel_order(
                    order_code=order_code, reference_no=reference_no
                )
            except LizardApiError as exc:
                raise LabelServiceError(
                    f"Lizard cancel failed: {exc}", http_status=502
                ) from exc
        msg = result.get("msg") or result.get("message") or "Cancelled"
        return f"Cancelled Lizard order {order_code} ({msg})"

    def _load_warehouses_config(self) -> dict:
        """Read config.yaml warehouses (shipper addresses for 蜴国际/VITE ship-from)."""
        from pathlib import Path

        import yaml

        path = Path(__file__).parent / "config.yaml"
        if not path.is_file():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            return (raw or {}).get("warehouses", {}) or {}
        except Exception:
            return {}

    def _lizard_reference_no(
        self, package_sn: str, operation_id: int | None
    ) -> str:
        """Build a unique 蜴国际 reference scoped by operation generation.

        蜴国际 keeps cancelled orders' reference_no reserved, so reusing the
        bare package_sn fails with "参考号重复". Per ops guidance: first attempt
        uses the base reference; each later attempt appends -1, -2, -3... The
        suffix is derived deterministically from the operation generation so
        createOrder / getLabel / cancelOrder all use the same value.
        """
        sn = (package_sn or "").strip()
        if not sn:
            return ""
        gen = 0
        if operation_id is not None:
            try:
                op = self._repo.get_label_operation(operation_id)
                gen = int(op.generation or 0)
            except Exception:
                gen = 0
        if gen <= 1:
            return sn
        return f"{sn}-{gen - 1}"

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
        operation_id: int | None = None,
    ) -> dict[str, Any]:
        from sellfox_shipping.carriers.vite.client import (
            ViteGofoClient,
            ViteClientError,
        )
        from sellfox_shipping.carriers.vite.shipment import ViteShipmentService
        from sellfox_shipping.carriers.errors import CarrierFailure

        api_key = _read_env("VITE_API_KEY")
        if not api_key:
            failure = CarrierFailure(
                "VITE_API_KEY not configured. Set it in .env",
                phase="auth",
                outcome="not_sent",
                category="configuration",
                safe_to_create_again=True,
            )
            raise LabelServiceError(str(failure), http_status=503, failure=failure)
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
                    operation_id=operation_id,
                )
            except ViteClientError as exc:
                raise LabelServiceError(
                    f"VITE API error: {exc}",
                    http_status=exc.http_status or 502,
                    failure=exc,
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
        operation_id: int | None = None,
    ) -> dict[str, Any]:
        from sellfox_shipping.carriers.lizard.api_client import LizardApiClient, LizardApiError
        from sellfox_shipping.carriers.lizard.api_shipment import LizardApiShipmentService
        from sellfox_shipping.carriers.errors import CarrierFailure

        app_token = _read_env("YIGLOBAL_APP_TOKEN")
        app_key = _read_env("YIGLOBAL_APP_KEY")
        if not app_token or not app_key:
            failure = CarrierFailure(
                "YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY not configured",
                phase="auth",
                outcome="not_sent",
                category="configuration",
                safe_to_create_again=True,
            )
            raise LabelServiceError(str(failure), http_status=503, failure=failure)
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

        # Fail-closed shipper address from the package's warehouse (蜴国际 has no
        # shipper codes — the S0143 table was a VITE concept). Never default to a
        # fixed address that could be the wrong warehouse.
        from sellfox_shipping.carriers.lizard.order_adapter import (
            build_shipper_address_from_warehouse,
        )

        try:
            shipper_address = build_shipper_address_from_warehouse(
                package.logistics.warehouse_name or "", self._load_warehouses_config()
            )
        except ValueError as exc:
            raise LabelServiceError(f"蜴国际发货仓库地址缺失: {exc}") from exc

        with LizardApiClient(
            app_token=app_token,
            app_key=app_key,
            base_url=lizard_base,
        ) as client:
            svc = LizardApiShipmentService(client, self._repo)
            try:
                # Unique reference: cancelled orders on 蜴国际 may keep the
                # package_sn reference reserved, so scope each attempt by generation.
                lizard_ref = self._lizard_reference_no(package.package_sn, operation_id)
                result = svc.ship_package(
                    package,
                    account_key=account_key,
                    actor=actor,
                    sm_code=sm_code,
                    reference_no=lizard_ref,
                    operation_id=operation_id,
                    shipper_address=shipper_address,
                )
            except LizardApiError as exc:
                raise LabelServiceError(
                    f"Lizard API error: {exc}",
                    http_status=exc.http_status or 502,
                    failure=exc,
                ) from exc
            except (TimeoutError, RuntimeError) as exc:
                failure = CarrierFailure(
                    f"Lizard API error: {exc}",
                    phase="create",
                    outcome="ambiguous",
                    category="timeout" if isinstance(exc, TimeoutError) else "protocol",
                )
                raise LabelServiceError(
                    str(failure), http_status=502, failure=failure
                ) from exc

        # Local label row — failure here must stay LABEL_PENDING (provider known).
        try:
            label_rec = self._repo.insert_label(
                account_key=account_key,
                package_db_id=db_id or 0,
                carrier="lizard",
                service_level=sm_code,
                tracking_number=result.tracking_number,
                carrier_order_id=result.order_code,
                request_id="",
                label_url=result.label_url,
                operation_id=operation_id,
                artifact_id=result.artifact_id,
                total_amount=None,
                currency="USD",
                status="generated",
                carrier_response_json="",
                created_by=actor,
                derived_reference_no=lizard_ref,
            )
        except Exception as exc:
            if operation_id is not None:
                self._repo.transition_label_operation(
                    operation_id,
                    status="LABEL_PENDING",
                    provider_order_id=result.order_code,
                    tracking_number=result.tracking_number or "",
                    error_class="label_pending",
                    error_summary=f"insert_label failed: {exc}"[:500],
                    increment_attempt=True,
                )
            raise LabelServiceError(
                f"Lizard label created at carrier but local insert failed: {exc}",
                http_status=502,
            ) from exc
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

    # ── Resume ───────────────────────────────────────────────

    def resume_label_acquisition(
        self, operation_id: int, *, actor: str
    ) -> dict[str, Any]:
        """Resume a label operation that has a provider_order_id.

        Only valid for ACCEPTED, LABEL_PENDING, or SUCCEEDED operations.
        SUCCEEDED operations return the existing result (idempotent).
        Never calls create — only getLabel/poll/PDF/artifact.
        """
        from sellfox_shipping.carriers.vite.client import ViteGofoClient, ViteClientError
        from sellfox_shipping.carriers.vite.shipment import ViteShipmentService
        from sellfox_shipping.carriers.lizard.api_client import LizardApiClient, LizardApiError
        from sellfox_shipping.carriers.lizard.api_shipment import LizardApiShipmentService

        op = self._repo.get_label_operation(operation_id)
        if op is None:
            raise LabelServiceError(
                f"operation not found: {operation_id}", http_status=404
            )

        # Idempotent: return existing result for already-succeeded operations
        if op.status == "SUCCEEDED":
            return {
                "operation_id": operation_id,
                "status": "SUCCEEDED",
                "provider_order_id": op.provider_order_id,
                "tracking_number": op.tracking_number,
                "carrier": op.carrier,
                "idempotent": True,
            }

        if op.status not in {"ACCEPTED", "LABEL_PENDING"}:
            raise LabelServiceError(
                f"cannot resume operation {operation_id} in status {op.status}",
                http_status=409,
            )

        provider_order_id = (op.provider_order_id or "").strip()
        if not provider_order_id:
            raise LabelServiceError(
                f"operation {operation_id} missing provider_order_id",
                http_status=400,
            )

        # Claim for exclusive processing
        claim_id = self._repo.acquire_resume_lease(operation_id, actor=actor)
        if claim_id is None:
            raise LabelServiceError(
                f"operation {operation_id} is being processed by another agent",
                http_status=409,
            )

        carrier = (op.carrier or "").strip().lower()
        package_sn = self._repo.get_package_sn_by_db_id(op.package_id) or ""
        package = self._repo.get(op.account_key, package_sn)
        if package is None:
            self._repo.release_resume_lease(operation_id, claim_id=claim_id)
            raise LabelServiceError(
                f"package not found for operation {operation_id}", http_status=404
            )

        try:
            if carrier == "vite":
                return self._resume_vite_label(
                    package=package,
                    account_key=op.account_key,
                    actor=actor,
                    order_id=provider_order_id,
                    operation_id=operation_id,
                    claim_id=claim_id,
                )
            elif carrier == "lizard":
                return self._resume_lizard_label(
                    package=package,
                    account_key=op.account_key,
                    actor=actor,
                    order_code=provider_order_id,
                    reference_no=self._lizard_reference_no(package.package_sn, operation_id),
                    operation_id=operation_id,
                    claim_id=claim_id,
                )
            else:
                raise LabelServiceError(
                    f"unknown carrier {carrier} for resume", http_status=400
                )
        except LabelServiceError:
            raise
        except ViteClientError as exc:
            self._repo.transition_label_operation(
                operation_id,
                status="LABEL_PENDING",
                provider_order_id=provider_order_id,
                error_class=exc.category,
                error_summary=str(exc)[:500],
                increment_attempt=True,
                expected_claim_id=claim_id,
            )
            raise LabelServiceError(
                f"VITE resume error: {exc}", http_status=502, failure=exc
            ) from exc
        except LizardApiError as exc:
            self._repo.transition_label_operation(
                operation_id,
                status="LABEL_PENDING",
                provider_order_id=provider_order_id,
                error_class=exc.category,
                error_summary=str(exc)[:500],
                increment_attempt=True,
                expected_claim_id=claim_id,
            )
            raise LabelServiceError(
                f"Lizard resume error: {exc}", http_status=502, failure=exc
            ) from exc
        except Exception as exc:
            self._repo.transition_label_operation(
                operation_id,
                status="LABEL_PENDING",
                provider_order_id=provider_order_id,
                error_class="resume_internal",
                error_summary=str(exc)[:500],
                increment_attempt=True,
                expected_claim_id=claim_id,
            )
            raise LabelServiceError(
                f"resume failed for operation {operation_id}: {exc}",
                http_status=502,
            ) from exc
        finally:
            self._repo.release_resume_lease(
                operation_id, claim_id=claim_id
            )

    def _resume_vite_label(
        self,
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        actor: str,
        order_id: str,
        operation_id: int,
        claim_id: str,
    ) -> dict[str, Any]:
        import time, random, json
        from sellfox_shipping.carriers.vite.shipment import (
            _kg_to_lb, _cm_to_in, _build_ship_from, _build_ship_to,
            ViteLabelNotReadyError, ViteLabelMissingUrlError,
            ARTIFACT_KIND,
        )
        from sellfox_shipping.carriers.vite.client import ViteGofoClient

        api_key = _read_env("VITE_API_KEY")
        if not api_key:
            raise LabelServiceError("VITE_API_KEY not configured", http_status=503)
        vite_base = _read_env("VITE_API_BASE_URL") or "https://test-api.vitedirect.com"

        with ViteGofoClient(api_key=api_key, base_url=vite_base) as client:
            labels = client.get_label(order_id)
            if not labels:
                raise ViteLabelNotReadyError(f"VITE label not ready for {order_id}")

            label_data = labels[0] if isinstance(labels, list) else labels
            status = str(label_data.get("status") or "").upper()
            tracking = str(label_data.get("trackingNumber") or "")
            label_url = str(label_data.get("url") or "")

            if status != "OK":
                raise ViteLabelNotReadyError(
                    f"VITE label status={status} for {order_id}"
                )
            if not label_url:
                raise ViteLabelMissingUrlError(f"VITE label missing url for {order_id}")

            content = _default_fetch_bytes(label_url)
            if not content:
                raise RuntimeError(f"empty label PDF for {order_id}")

            artifact = self._repo.register_artifact(
                account_key=account_key,
                kind=ARTIFACT_KIND,
                file_name=f"vite-label-{package.package_sn}.pdf",
                content=content,
                actor=actor,
                mime_type="application/pdf",
                virtual_folder="vite/labels",
                summary=f"order_id={order_id} tracking={tracking}",
            )

            label_rec = self._repo.insert_label(
                account_key=account_key,
                package_db_id=self._repo.get_package_db_id(
                    account_key, package.package_sn
                ) or 0,
                carrier="vite",
                service_level="GOFO_PARCEL",
                tracking_number=tracking,
                carrier_order_id=order_id,
                request_id=f"resume-{int(time.time())}",
                label_url=label_url,
                operation_id=operation_id,
                artifact_id=artifact.id,
                total_amount=None,
                currency="USD",
                status="generated",
                carrier_response_json=json.dumps(label_data),
                created_by=actor,
                expected_claim_id=claim_id,
            )

        result = {
            "status": "SUCCEEDED",
            "provider_order_id": order_id,
            "tracking_number": tracking,
            "label_url": label_url,
            "carrier": "vite",
            "service_level": "GOFO_PARCEL",
        }

        self._repo.finalize_label_success_with_outbox(
            operation_id=operation_id,
            label_id=label_rec.id,
            actor=actor,
            expected_claim_id=claim_id,
        )

        return result

    def _resume_lizard_label(
        self,
        *,
        package: SellfoxPackageRecord,
        account_key: str,
        actor: str,
        order_code: str,
        reference_no: str,
        operation_id: int,
        claim_id: str,
    ) -> dict[str, Any]:
        import time, json
        from sellfox_shipping.carriers.lizard.api_client import LizardApiClient
        from sellfox_shipping.carriers.lizard.api_shipment import (
            LizardLabelNotReadyError, LizardLabelMissingUrlError,
            ARTIFACT_KIND, parse_get_label_result,
        )

        app_token = _read_env("YIGLOBAL_APP_TOKEN")
        app_key = _read_env("YIGLOBAL_APP_KEY")
        if not app_token or not app_key:
            raise LabelServiceError(
                "YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY not configured",
                http_status=503,
            )
        lizard_base = _read_env("YIGLOBAL_API_BASE_URL") or "http://47.106.72.196"

        with LizardApiClient(
            app_token=app_token, app_key=app_key, base_url=lizard_base
        ) as client:
            lab = client.get_label(order_code=order_code, reference_no=reference_no)
            parsed = parse_get_label_result(lab)
            tracking = parsed.get("tracking_number") or ""
            label_url = parsed.get("label_url") or ""

            if not parsed.get("label_ready"):
                raise LizardLabelNotReadyError(
                    f"Lizard label not ready for {order_code}"
                )
            if not label_url:
                raise LizardLabelMissingUrlError(
                    f"Lizard label missing url for {order_code}"
                )

            content = _default_fetch_bytes(label_url)
            if not content:
                raise RuntimeError(f"empty label PDF for {order_code}")

            artifact = self._repo.register_artifact(
                account_key=account_key,
                kind=ARTIFACT_KIND,
                file_name=f"lizard-label-{package.package_sn}.pdf",
                content=content,
                actor=actor,
                mime_type="application/pdf",
                virtual_folder="lizard/api-labels",
                summary=f"order_code={order_code} tracking={tracking}",
            )

            op = self._repo.get_label_operation(operation_id)
            service_level = (op.service_level if op else "") or "resumed"
            package_db_id = (
                self._repo.get_package_db_id(account_key, package.package_sn) or 0
            )
            # Local label row — failure here must stay LABEL_PENDING (provider known).
            try:
                label_rec = self._repo.insert_label(
                    account_key=account_key,
                    package_db_id=package_db_id,
                    carrier="lizard",
                    service_level=service_level,
                    tracking_number=tracking,
                    carrier_order_id=order_code,
                    request_id=f"resume-{int(time.time())}",
                    label_url=label_url,
                    operation_id=operation_id,
                    artifact_id=artifact.id,
                    total_amount=None,
                    currency="USD",
                    status="generated",
                    carrier_response_json=json.dumps(lab),
                    created_by=actor,
                    derived_reference_no=reference_no,
                    expected_claim_id=claim_id,
                )
            except Exception as exc:
                self._repo.transition_label_operation(
                    operation_id,
                    status="LABEL_PENDING",
                    provider_order_id=order_code,
                    tracking_number=tracking or "",
                    error_class="label_pending",
                    error_summary=f"insert_label failed: {exc}"[:500],
                    increment_attempt=True,
                    expected_claim_id=claim_id,
                )
                raise LabelServiceError(
                    f"Lizard label retrieved but local insert failed: {exc}",
                    http_status=502,
                ) from exc

        result = {
            "status": "SUCCEEDED",
            "provider_order_id": order_code,
            "tracking_number": tracking,
            "label_url": label_url,
            "carrier": "lizard",
            "service_level": service_level,
        }

        self._repo.finalize_label_success_with_outbox(
            operation_id=operation_id,
            label_id=label_rec.id,
            actor=actor,
            expected_claim_id=claim_id,
        )

        return result



    # ── UNKNOWN_BLOCKED resolution ───────────────────────────

    def resolve_unknown_blocked(
        self,
        operation_id: int,
        *,
        resolution: str,
        confirm: str = "",
        provider_order_id: str = "",
        note: str = "",
        actor: str,
        evidence_id: int,
    ) -> dict[str, Any]:
        """Human-driven resolution of an UNKNOWN_BLOCKED operation.

        resolution must be one of: fail_safe, fail_final, provide_known_id.
        confirm must match resolution to prevent accidental execution.
        provide_known_id requires a non-empty provider_order_id.
        evidence_id must reference an investigation record belonging to this operation.
        """
        VALID_RESOLUTIONS = {"fail_safe", "fail_final", "provide_known_id"}
        if resolution not in VALID_RESOLUTIONS:
            raise LabelServiceError(
                f"invalid resolution {resolution!r}. "
                f"Use: {', '.join(sorted(VALID_RESOLUTIONS))}",
                http_status=400,
            )
        if confirm != resolution:
            raise LabelServiceError(
                f"confirm value must match resolution ({resolution!r})",
                http_status=400,
            )

        op = self._repo.get_label_operation(operation_id)
        if op is None:
            raise LabelServiceError(
                f"operation not found: {operation_id}", http_status=404
            )
        if op.status != "UNKNOWN_BLOCKED":
            raise LabelServiceError(
                f"operation {operation_id} is {op.status}, "
                f"only UNKNOWN_BLOCKED can be manually resolved",
                http_status=409,
            )

        if resolution == "provide_known_id":
            pid = (provider_order_id or "").strip()
            if not pid:
                raise LabelServiceError(
                    "provider_order_id is required for provide_known_id",
                    http_status=400,
                )

            try:
                self._repo.resolve_unknown_blocked_operation(
                    operation_id,
                    target_status="ACCEPTED",
                    resolution=resolution,
                    provider_order_id=pid,
                    note=note,
                    actor=actor,
                    evidence_id=evidence_id,
                    expected_conclusion="confirmed_created",
                )
            except RuntimeError as exc:
                raise LabelServiceError(str(exc), http_status=409) from exc
            return {
                "operation_id": operation_id,
                "status": "ACCEPTED",
                "provider_order_id": pid,
                "resolution": resolution,
                "next_action": "resume",
                "evidence_id": evidence_id,
            }

        target_status = "FAILED_SAFE" if resolution == "fail_safe" else "FAILED_FINAL"
        expected_conclusion = (
            "confirmed_not_created"
            if resolution == "fail_safe"
            else "confirmed_rejected"
        )
        try:
            self._repo.resolve_unknown_blocked_operation(
                operation_id,
                target_status=target_status,
                resolution=resolution,
                note=note,
                actor=actor,
                evidence_id=evidence_id,
                expected_conclusion=expected_conclusion,
            )
        except RuntimeError as exc:
            raise LabelServiceError(str(exc), http_status=409) from exc
        result: dict[str, Any] = {
            "operation_id": operation_id,
            "status": target_status,
            "resolution": resolution,
            "evidence_id": evidence_id,
        }
        if resolution == "fail_safe":
            result["next_action"] = "retry_create_new_generation"
        return result

    def add_investigation(
        self,
        *,
        operation_id: int,
        evidence_type: str,
        conclusion: str,
        provider_order_id: str = "",
        actor: str,
        external_ref: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        """Add an investigation record without resolving the block.

        This is append-only — it records what was checked and found,
        but does not change the operation status.
        """
        VALID_TYPES = {"ticket", "carrier_portal", "email", "other"}
        VALID_CONCLUSIONS = {
            "confirmed_not_created",
            "confirmed_created",
            "confirmed_rejected",
        }
        if evidence_type not in VALID_TYPES:
            raise LabelServiceError(
                f"invalid evidence_type {evidence_type!r}. "
                f"Use: {', '.join(sorted(VALID_TYPES))}",
                http_status=400,
            )
        if conclusion not in VALID_CONCLUSIONS:
            raise LabelServiceError(
                f"invalid conclusion {conclusion!r}. "
                f"Use: {', '.join(sorted(VALID_CONCLUSIONS))}",
                http_status=400,
            )
        if conclusion == "confirmed_created" and not provider_order_id.strip():
            raise LabelServiceError(
                "provider_order_id is required for confirmed_created evidence",
                http_status=400,
            )

        op = self._repo.get_label_operation(operation_id)
        if op is None:
            raise LabelServiceError(
                f"operation not found: {operation_id}", http_status=404
            )

        record = self._repo.add_investigation(
            operation_id=operation_id,
            evidence_type=evidence_type,
            conclusion=conclusion,
            provider_order_id=provider_order_id,
            external_ref=external_ref,
            note=note,
            actor=actor,
        )
        return {
            "investigation_id": record.id,
            "operation_id": operation_id,
            "evidence_type": record.evidence_type,
            "conclusion": record.conclusion,
            "provider_order_id": record.provider_order_id,
            "external_ref": record.external_ref,
            "note": record.note,
            "actor": record.actor,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "operation_status": op.status,
        }


def _default_fetch_bytes(url: str) -> bytes:
    import httpx
    resp = httpx.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.content
