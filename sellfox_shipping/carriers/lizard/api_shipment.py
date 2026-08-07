"""Lizard API shipment orchestration (opt-in; Excel remains production default).

Flow: build_create_order_body → createOrder → poll getLabel → download PDF → Artifact.

No Web/CLI wiring in this slice — call ``LizardApiShipmentService.ship_package`` from
tests or a future controlled CLI. Inject ``sleep`` / ``fetch_bytes`` / ``monotonic``
for deterministic unit tests (no live HTTP).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import httpx

from sellfox_shipping.carriers.lizard.api_client import (
    LizardApiError,
    parse_create_order_result,
    parse_get_label_result,
)
from sellfox_shipping.carriers.lizard.order_adapter import build_create_order_body
from sellfox_shipping.carriers.lizard.spreadsheet import SHIPPER_CODE_DEFAULT
from sellfox_shipping.package_models import SellfoxPackageRecord

if TYPE_CHECKING:
    from sellfox_shipping.package_repository import PackageRepository

ARTIFACT_KIND = "lizard_api_label"


class LizardLabelNotReadyError(TimeoutError):
    """getLabel did not reach sync_service_status=1 before timeout."""


class LizardLabelMissingUrlError(RuntimeError):
    """Label marked ready but no label_url to download."""


def _default_fetch_bytes(url: str) -> bytes:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


@dataclass(frozen=True)
class LizardApiShipmentResult:
    package_sn: str
    order_code: str
    tracking_number: str
    label_url: str
    artifact_id: int
    poll_count: int


class LizardApiShipmentService:
    """ApiCarrierAdapter-shaped orchestration for 蜴国际 (one package)."""

    def __init__(
        self,
        client: Any,
        repo: PackageRepository,
        *,
        fetch_bytes: Callable[[str], bytes] | None = None,
        sleep: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._client = client
        self._repo = repo
        self._fetch_bytes = fetch_bytes or _default_fetch_bytes
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic

    def ship_package(
        self,
        package: SellfoxPackageRecord,
        *,
        account_key: str,
        actor: str,
        sm_code: str,
        shipper_code: str = SHIPPER_CODE_DEFAULT,
        reference_no: str = "",
        poll_interval_s: float = 15.0,
        poll_timeout_s: float = 180.0,
        operation_id: int | None = None,
        shipper_address: dict[str, str] | None = None,
    ) -> LizardApiShipmentResult:
        sn = (package.package_sn or "").strip()
        if not sn:
            raise ValueError("missing package_sn")
        ref = (reference_no or "").strip() or sn
        body = build_create_order_body(
            package,
            sm_code=sm_code,
            shipper_code=shipper_code,
            reference_no=ref,
            shipper_address=shipper_address,
        )
        created = self._client.create_order(body)
        parsed_create = parse_create_order_result(created)
        order_code = parsed_create["order_code"]
        if not order_code:
            raise RuntimeError(f"createOrder missing order_code for {sn}")

        if operation_id is not None:
            self._repo.transition_label_operation(
                operation_id,
                status="ACCEPTED",
                provider_order_id=order_code,
            )

        tracking = parsed_create.get("tracking_number") or ""
        label_url = parsed_create.get("label_url") or ""
        poll_count = 0

        try:
            deadline = self._monotonic() + max(poll_timeout_s, 0.0)
            ready = False

            while True:
                poll_count += 1
                lab = self._client.get_label(order_code=order_code, reference_no=ref)
                parsed = parse_get_label_result(lab)
                logistics_err = (parsed.get("logistics_err") or "").strip()
                if logistics_err:
                    # Order entered an error state (e.g. duplicate reference) —
                    # do not keep polling; surface the carrier's message.
                    raise LizardApiError(
                        f"Lizard order {order_code} errored: {logistics_err}",
                        status_code=lab.get("code") if isinstance(lab, dict) else None,
                        business_code=parsed.get("code"),
                        phase="create",
                    )
                if parsed.get("tracking_number"):
                    tracking = str(parsed["tracking_number"])
                if parsed.get("label_url"):
                    label_url = str(parsed["label_url"])
                if parsed.get("label_ready"):
                    ready = True
                    break
                if self._monotonic() >= deadline:
                    break
                interval = max(poll_interval_s, 0.0)
                if interval > 0:
                    self._sleep(interval)

            if not ready:
                raise LizardLabelNotReadyError(
                    f"getLabel not ready for {sn} order_code={order_code} "
                    f"after {poll_count} poll(s)"
                )
            if not label_url:
                raise LizardLabelMissingUrlError(
                    f"label ready but missing label_url for {sn} order_code={order_code}"
                )

            content = self._fetch_bytes(label_url)
            if not content:
                raise RuntimeError(f"empty label PDF for {sn}")

            artifact = self._repo.register_artifact(
                account_key=account_key,
                kind=ARTIFACT_KIND,
                file_name=f"lizard-label-{sn}.pdf",
                content=content,
                actor=actor,
                mime_type="application/pdf",
                virtual_folder="lizard/api-labels",
                summary=f"order_code={order_code} tracking={tracking}",
            )
        except Exception as exc:
            if operation_id is not None:
                self._repo.transition_label_operation(
                    operation_id,
                    status="LABEL_PENDING",
                    provider_order_id=order_code,
                    tracking_number=tracking,
                    error_class="label_pending",
                    error_summary=str(exc)[:500],
                    increment_attempt=True,
                )
            raise

        return LizardApiShipmentResult(
            package_sn=sn,
            order_code=order_code,
            tracking_number=tracking,
            label_url=label_url,
            artifact_id=artifact.id,
            poll_count=poll_count,
        )
