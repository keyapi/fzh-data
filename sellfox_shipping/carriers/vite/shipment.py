"""VITE shipment orchestration (mirrors carriers/lizard/api_shipment.py).

Flow: build body → create_shipment_gofo → poll get_label → download PDF → Artifact.

Inject ``sleep`` / ``fetch_bytes`` / ``monotonic`` for deterministic tests.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Callable

import httpx

from sellfox_shipping.carriers.vite.client import ViteGofoClient, ViteClientError
from sellfox_shipping.package_models import SellfoxPackageRecord

if TYPE_CHECKING:
    from sellfox_shipping.package_repository import PackageRepository

ARTIFACT_KIND = "vite_label"
VITE_FEDEX_CHANNEL = (os.getenv("VITE_FEDEX_CHANNEL") or "ODFC").strip()
GOFO_MAX_SIDE_INCHES = 22.0


# ── helpers ───────────────────────────────────────────────────────

def _kg_to_lb(kg: float) -> float:
    return round(kg * 2.20462, 2)


def _cm_to_in(cm: float) -> float:
    return round(cm / 2.54, 1)


def _build_ship_from(warehouse_name: str, warehouses_cfg: dict) -> dict:
    """Build VITE sender address from warehouse config."""
    wh = warehouses_cfg.get(warehouse_name, {})
    addr = wh.get("address", {})
    if addr.get("address1"):
        return {
            "fullName": (addr.get("name") or "FZH Warehouse")[:35],
            "company": (addr.get("company") or "")[:35],
            "address1": addr["address1"][:50],
            "address2": (addr.get("address2") or "")[:50],
            "city": (addr.get("city") or "")[:28],
            "state": (addr.get("state") or "")[:2],
            "zipCode": (addr.get("postal_code") or "")[:10],
            "phoneNumber": (addr.get("phone") or "0000000000")[:15],
        }
    return {
        "fullName": "FZH Test",
        "address1": "90 Chester rd",
        "city": "Belmont",
        "state": "MA",
        "zipCode": "02478",
        "phoneNumber": "1111111111",
    }


def _build_ship_to(package: SellfoxPackageRecord) -> dict:
    """Build VITE recipient address from package record."""
    addr = package.address
    return {
        "fullName": (addr.name or "Customer")[:35],
        "address1": (addr.address_line_1 or "")[:50],
        "address2": (addr.address_line_2 or "")[:35],
        "city": (addr.city or "")[:28],
        "state": (addr.state_or_region or addr.city or "XX")[:2],
        "zipCode": (addr.postal_code or "")[:10],
        "phoneNumber": (addr.phone or addr.mobile or "0000000000")[:15],
    }


def _default_fetch_bytes(url: str) -> bytes:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


# ── result dataclass ──────────────────────────────────────────────


@dataclass(frozen=True)
class ViteShipmentResult:
    package_sn: str
    order_id: str
    tracking_number: str
    label_url: str
    artifact_id: int
    total_amount: float | None
    poll_count: int


class ViteLabelNotReadyError(TimeoutError):
    """getLabel did not reach status=OK before timeout."""


class ViteLabelMissingUrlError(RuntimeError):
    """Label marked OK but no url to download."""


# ── service ───────────────────────────────────────────────────────


class ViteShipmentService:
    """Orchestrate VITE label creation for one package."""

    def __init__(
        self,
        client: ViteGofoClient,
        repo: PackageRepository,
        *,
        fetch_bytes: Callable[[str], bytes] | None = None,
        sleep: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        warehouses_cfg: dict | None = None,
    ) -> None:
        self._client = client
        self._repo = repo
        self._fetch_bytes = fetch_bytes or _default_fetch_bytes
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._warehouses = warehouses_cfg or {}

    def ship_package(
        self,
        package: SellfoxPackageRecord,
        *,
        account_key: str,
        actor: str,
        service_type: str = "GOFO_PARCEL",
        channel: str = "GFUS",
        package_dims: dict[str, float] | None = None,
        poll_interval_s: float = 5.0,
        poll_timeout_s: float = 180.0,
    ) -> ViteShipmentResult:
        sn = (package.package_sn or "").strip()
        if not sn:
            raise ValueError("missing package_sn")

        # Resolve dimensions
        dims = package_dims or {}
        if not dims:
            dims = self._resolve_dims_from_repo(package)
        if not dims:
            raise ValueError(f"no dimensions available for {sn}")

        weight_lb = _kg_to_lb(dims.get("weight_kg", 0))
        length_in = _cm_to_in(dims.get("length_cm", 0))
        width_in = _cm_to_in(dims.get("width_cm", 0))
        height_in = _cm_to_in(dims.get("height_cm", 0))

        if weight_lb <= 0 or max(length_in, width_in, height_in) <= 0:
            raise ValueError(f"invalid dimensions for {sn}: weight={weight_lb}lb dims={length_in}x{width_in}x{height_in}in")

        # Request ID: timestamp + random (VITE requirement: globally unique)
        import random
        request_id = f"{int(time.time() * 1000)}{random.randint(100, 999)}"

        # Build body — use user-selected service type, no dimension auto-override
        use_fedex = (service_type or "").upper().startswith("FEDEX")
        if use_fedex:
            service_type = "FEDEX_GROUND"
            channel = VITE_FEDEX_CHANNEL

        body: dict[str, Any] = {
            "requestId": request_id,
            "serviceType": service_type,
            "channel": channel,
            "shipDate": date.today().isoformat(),
            "reference": sn,
            "from": _build_ship_from(
                package.logistics.warehouse_name or "", self._warehouses
            ),
            "to": _build_ship_to(package),
            "packages": [{
                "weight": weight_lb,
                "length": length_in,
                "width": width_in,
                "height": height_in,
            }],
        }

        # Create shipment
        try:
            if use_fedex:
                created = self._client.create_shipment_fedex(body)
            else:
                created = self._client.create_shipment_gofo(body)
        except ViteClientError:
            raise
        except Exception as exc:
            raise ViteClientError(f"VITE create shipment failed: {exc}") from exc

        order_id = str(created.get("orderId") or "").strip()
        if not order_id:
            raise RuntimeError(f"VITE create shipment missing orderId for {sn}")

        total_amount = created.get("totalAmount")
        carrier_response_json = json.dumps(created, ensure_ascii=False)

        # Poll for label readiness
        deadline = self._monotonic() + max(poll_timeout_s, 0.0)
        poll_count = 0
        tracking_number = ""
        label_url = ""
        ready = False

        while True:
            poll_count += 1
            try:
                labels = self._client.get_label(order_id)
            except ViteClientError:
                raise
            except Exception as exc:
                raise ViteClientError(f"VITE get_label failed: {exc}") from exc

            if labels:
                label_data = labels[0] if isinstance(labels, list) else labels
                status = str(label_data.get("status") or "").upper()
                if label_data.get("trackingNumber"):
                    tracking_number = str(label_data["trackingNumber"])
                if label_data.get("url"):
                    label_url = str(label_data["url"])
                if status == "OK":
                    ready = True
                    break
                if status == "FAILED":
                    err = label_data.get("errorMessage", "unknown error")
                    raise RuntimeError(f"VITE label failed for {sn}: {err}")

            if self._monotonic() >= deadline:
                break
            interval = max(poll_interval_s, 0.0)
            if interval > 0:
                self._sleep(interval)

        if not ready:
            raise ViteLabelNotReadyError(
                f"VITE label not ready for {sn} order_id={order_id} "
                f"after {poll_count} poll(s)"
            )
        if not label_url:
            raise ViteLabelMissingUrlError(
                f"VITE label ready but missing url for {sn} order_id={order_id}"
            )

        # Download PDF
        content = self._fetch_bytes(label_url)
        if not content:
            raise RuntimeError(f"empty label PDF for {sn}")

        # Register artifact
        artifact = self._repo.register_artifact(
            account_key=account_key,
            kind=ARTIFACT_KIND,
            file_name=f"vite-label-{sn}.pdf",
            content=content,
            actor=actor,
            mime_type="application/pdf",
            virtual_folder="vite/labels",
            summary=f"order_id={order_id} tracking={tracking_number}",
        )

        # Insert label record
        label_record = self._repo.insert_label(
            account_key=account_key,
            package_db_id=self._repo.get_package_db_id(account_key, sn) or 0,
            carrier="vite",
            service_level=service_type,
            tracking_number=tracking_number,
            carrier_order_id=order_id,
            request_id=request_id,
            label_url=label_url,
            artifact_id=artifact.id,
            total_amount=float(total_amount) if total_amount is not None else None,
            currency=created.get("currency", "USD"),
            status="generated",
            carrier_response_json=carrier_response_json,
            created_by=actor,
        )

        return ViteShipmentResult(
            package_sn=sn,
            order_id=order_id,
            tracking_number=tracking_number,
            label_url=label_url,
            artifact_id=artifact.id,
            total_amount=float(total_amount) if total_amount is not None else None,
            poll_count=poll_count,
        )

    def _resolve_dims_from_repo(
        self, package: SellfoxPackageRecord
    ) -> dict[str, float] | None:
        try:
            from sellfox_shipping.package_repository import PackageDimsRecord
            db_id = self._repo.get_package_db_id(
                package.account_key, package.package_sn
            )
            if db_id is None:
                return None
            dims = self._repo.get_package_dims(db_id)
            if dims is None:
                return None
            return {
                "weight_kg": dims.weight_kg,
                "length_cm": dims.length_cm,
                "width_cm": dims.width_cm,
                "height_cm": dims.height_cm,
            }
        except Exception:
            return None
