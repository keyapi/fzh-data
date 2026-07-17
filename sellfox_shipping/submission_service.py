"""P1C: SubmissionIntent preparation, CAS, 1 rps submit, and readback VERIFIED."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.submission_rate_limit import SubmitRateLimiter
from sellfox_shipping.submission_state import aggregate_package_submission_state


class SubmissionScopeBlockedError(RuntimeError):
    """Scope is UNKNOWN_BLOCKED; no new or retried submit allowed."""


class SubmissionCasError(RuntimeError):
    """Compare-and-swap failed; caller must not invoke HTTP."""


@dataclass(frozen=True)
class CanonicalSubmitRequest:
    sellfox_account_id: str
    package_id: int
    order_id: str
    shop_id: str
    tracking_number: str
    carrier_name: str
    shipping_service: str
    items: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "sellfox_account_id": self.sellfox_account_id,
            "package_id": self.package_id,
            "order_id": self.order_id,
            "shop_id": self.shop_id,
            "tracking_number": self.tracking_number,
            "carrier_name": self.carrier_name,
            "shipping_service": self.shipping_service,
            "items": self.items,
        }


@dataclass(frozen=True)
class PrepareSubmitResult:
    package_sn: str
    intent_ids: list[int]
    package_submission_state: str


@dataclass(frozen=True)
class SubmitIntentResult:
    intent_id: int
    attempt_id: int
    intent_status: str
    attempt_status: str
    package_submission_state: str
    http_called: bool
    dry_run: bool
    verified: bool = False
    rate_limited_wait_ms: int = 0


class SellfoxSubmitClient(Protocol):
    def submit_to_platform(self, wire_body: dict[str, object]) -> dict[str, object]:
        """POST submitToPlatform; returns parsed JSON body."""

    def fetch_package_detail(self, package_sn: str) -> dict | None:
        """POST packageDetail; returns data dict or None."""


def build_canonical_request(
    *,
    account_key: str,
    package_db_id: int,
    external_order_id: str,
    shop_id: str,
    tracking_number: str,
    carrier_name: str,
    shipping_service: str,
    items: list[dict[str, object]],
) -> tuple[CanonicalSubmitRequest, str, str]:
    """Return canonical request, JSON snapshot, and SHA-256 request_hash."""
    sorted_items = sorted(
        items,
        key=lambda row: (
            str(row.get("order_item_id", "")),
            int(row.get("quantity", 0)),
        ),
    )
    req = CanonicalSubmitRequest(
        sellfox_account_id=account_key,
        package_id=package_db_id,
        order_id=external_order_id,
        shop_id=shop_id,
        tracking_number=tracking_number,
        carrier_name=carrier_name,
        shipping_service=shipping_service,
        items=sorted_items,
    )
    canonical_json = json.dumps(
        req.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return req, canonical_json, request_hash


def canonical_to_wire_body(req: CanonicalSubmitRequest) -> dict[str, object]:
    """Map internal canonical request to Sellfox submitToPlatform wire JSON."""
    body: dict[str, object] = {
        "shopId": req.shop_id,
        "orderId": req.order_id,
        "carrierName": req.carrier_name,
        "trackNo": req.tracking_number,
        "items": [
            {
                "orderItemId": str(item["order_item_id"]),
                "quantity": int(item["quantity"]),
            }
            for item in req.items
        ],
    }
    if req.shipping_service:
        body["shipService"] = req.shipping_service
    return body


def tracking_matches_detail(detail: dict, expected_track_no: str) -> bool:
    """Conservative match: logistics.trackNo equals expected (non-empty)."""
    expected = (expected_track_no or "").strip()
    if not expected:
        return False
    logistics = detail.get("logistics") if isinstance(detail, dict) else None
    if not isinstance(logistics, dict):
        logistics = {}
    actual = str(
        logistics.get("trackNo")
        or logistics.get("trackingNumber")
        or detail.get("trackNo")
        or ""
    ).strip()
    return bool(actual) and actual == expected


class SubmissionService:
    def __init__(
        self,
        repository: PackageRepository,
        submit_client: SellfoxSubmitClient | None = None,
        rate_limiter: SubmitRateLimiter | None = None,
    ):
        self._repo = repository
        self._client = submit_client
        self._rate_limiter = rate_limiter or SubmitRateLimiter(1.0)

    def recover_stale_in_flight(self, *, actor: str = "system") -> int:
        return self._repo.recover_stale_submission_in_flight(actor=actor)

    def prepare_intents_for_package(
        self,
        *,
        account_key: str,
        package_sn: str,
        actor: str,
        carrier_name: str = "",
        shipping_service: str = "",
    ) -> PrepareSubmitResult:
        record = self._repo.get(account_key, package_sn)
        if record is None:
            raise LookupError(f"Package {package_sn} not found")
        if record.local_review_status != "approved":
            raise ValueError("package local_review_status must be approved")
        tracking = (record.logistics.tracking_number or "").strip()
        if not tracking or tracking == package_sn:
            raise ValueError("package must have a real tracking_number before submit")
        carrier = (carrier_name or record.logistics.channel_name or "").strip()
        if not carrier:
            raise ValueError("carrier_name is required")

        package_db_id = self._repo.get_package_db_id(account_key, package_sn)
        if package_db_id is None:
            raise LookupError(f"Package db id missing for {package_sn}")

        order_ids = self._repo.list_package_order_db_ids(account_key, package_sn)
        if not order_ids:
            raise ValueError("package has no orders")

        intent_ids: list[int] = []
        for order_db_id, external_order_id in order_ids:
            if self._repo.is_submission_scope_blocked(
                account_key=account_key,
                package_db_id=package_db_id,
                order_db_id=order_db_id,
            ):
                raise SubmissionScopeBlockedError(
                    f"scope blocked for order {external_order_id}"
                )
            items = self._repo.list_order_items_for_package_order(
                package_db_id=package_db_id,
                external_order_id=external_order_id,
            )
            if not items:
                raise ValueError(f"no items for order {external_order_id}")
            _, canonical_json, request_hash = build_canonical_request(
                account_key=account_key,
                package_db_id=package_db_id,
                external_order_id=external_order_id,
                shop_id=record.shop_id,
                tracking_number=tracking,
                carrier_name=carrier,
                shipping_service=shipping_service,
                items=items,
            )
            intent = self._repo.upsert_submission_intent(
                account_key=account_key,
                package_db_id=package_db_id,
                order_db_id=order_db_id,
                external_order_id=external_order_id,
                request_hash=request_hash,
                canonical_request=canonical_json,
                confirmed_by=actor,
            )
            intent_ids.append(intent.id)

        states = self._repo.list_intent_statuses_for_package(package_db_id)
        return PrepareSubmitResult(
            package_sn=package_sn,
            intent_ids=intent_ids,
            package_submission_state=aggregate_package_submission_state(states),
        )

    def submit_intent(
        self,
        *,
        intent_id: int,
        actor: str,
        dry_run: bool = True,
        allow_side_effects: bool = False,
        verify_readback: bool = True,
    ) -> SubmitIntentResult:
        intent = self._repo.get_submission_intent(intent_id)
        if intent is None:
            raise LookupError(f"Intent {intent_id} not found")
        if self._repo.is_submission_scope_blocked_by_intent(intent_id):
            raise SubmissionScopeBlockedError("scope is UNKNOWN_BLOCKED")

        if dry_run:
            states = self._repo.list_intent_statuses_for_package(intent.package_id)
            return SubmitIntentResult(
                intent_id=intent_id,
                attempt_id=0,
                intent_status=intent.status,
                attempt_status="",
                package_submission_state=aggregate_package_submission_state(states),
                http_called=False,
                dry_run=True,
            )

        if not allow_side_effects:
            raise ValueError(
                "allow_side_effects required when dry_run is false "
                "(use --i-understand-side-effects on CLI)"
            )

        attempt = self._repo.create_submission_attempt(
            intent_id=intent_id,
            actor=actor,
        )
        cas = self._repo.cas_submission_to_in_flight(
            intent_id=intent_id,
            attempt_id=attempt.id,
            expected_intent_version=intent.version,
        )
        if not cas:
            raise SubmissionCasError("CAS to IN_FLIGHT failed")

        if self._client is None:
            raise RuntimeError("submit client required for side effects")
        canonical = json.loads(intent.canonical_request)
        req = CanonicalSubmitRequest(
            sellfox_account_id=str(canonical["sellfox_account_id"]),
            package_id=int(canonical["package_id"]),
            order_id=str(canonical["order_id"]),
            shop_id=str(canonical.get("shop_id", "")),
            tracking_number=str(canonical["tracking_number"]),
            carrier_name=str(canonical["carrier_name"]),
            shipping_service=str(canonical.get("shipping_service", "")),
            items=list(canonical["items"]),
        )
        wire = canonical_to_wire_body(req)

        wait_s = self._rate_limiter.wait()
        wait_ms = int(round(wait_s * 1000))
        http_called = False
        verified = False
        try:
            http_called = True
            resp = self._client.submit_to_platform(wire)
            if resp.get("code") == 0:
                self._repo.mark_submission_attempt_result(
                    attempt_id=attempt.id,
                    intent_id=intent_id,
                    attempt_status="SUCCESS",
                    intent_status="SUCCESS",
                    http_status=200,
                    http_summary=json.dumps(resp, ensure_ascii=False)[:2000],
                )
                if verify_readback:
                    verified = self._try_verify_after_success(
                        intent_id=intent_id,
                        package_db_id=intent.package_id,
                        expected_track_no=req.tracking_number,
                    )
            else:
                self._repo.mark_submission_attempt_result(
                    attempt_id=attempt.id,
                    intent_id=intent_id,
                    attempt_status="FAILED",
                    intent_status="FAILED",
                    http_status=200,
                    http_summary=json.dumps(resp, ensure_ascii=False)[:2000],
                )
        except Exception as exc:  # noqa: BLE001
            self._repo.mark_submission_unknown_and_block_scope(
                attempt_id=attempt.id,
                intent_id=intent_id,
                http_summary=str(exc)[:2000],
            )

        updated = self._repo.get_submission_intent(intent_id)
        assert updated is not None
        attempt_row = self._repo.get_submission_attempt(attempt.id)
        assert attempt_row is not None
        states = self._repo.list_intent_statuses_for_package(updated.package_id)
        return SubmitIntentResult(
            intent_id=intent_id,
            attempt_id=attempt.id,
            intent_status=updated.status,
            attempt_status=attempt_row.status,
            package_submission_state=aggregate_package_submission_state(states),
            http_called=http_called,
            dry_run=False,
            verified=verified or updated.status == "VERIFIED",
            rate_limited_wait_ms=wait_ms,
        )

    def verify_intent_from_readback(
        self,
        *,
        intent_id: int,
        actor: str,
    ) -> SubmitIntentResult:
        """Promote SUCCESS → VERIFIED via packageDetail when trackNo matches.

        Readback failure or mismatch leaves SUCCESS; does not mark UNKNOWN.
        """
        intent = self._repo.get_submission_intent(intent_id)
        if intent is None:
            raise LookupError(f"Intent {intent_id} not found")
        if intent.status == "VERIFIED":
            states = self._repo.list_intent_statuses_for_package(intent.package_id)
            return SubmitIntentResult(
                intent_id=intent_id,
                attempt_id=0,
                intent_status="VERIFIED",
                attempt_status="",
                package_submission_state=aggregate_package_submission_state(states),
                http_called=False,
                dry_run=False,
                verified=True,
            )
        if intent.status != "SUCCESS":
            raise RuntimeError(
                f"verify requires SUCCESS intent, got {intent.status}"
            )
        canonical = json.loads(intent.canonical_request)
        expected = str(canonical.get("tracking_number") or "")
        verified = self._try_verify_after_success(
            intent_id=intent_id,
            package_db_id=intent.package_id,
            expected_track_no=expected,
        )
        updated = self._repo.get_submission_intent(intent_id)
        assert updated is not None
        states = self._repo.list_intent_statuses_for_package(updated.package_id)
        self._repo.append_audit_event(
            actor=actor,
            action="submission.verify_readback",
            entity_type="intent",
            entity_id=str(intent_id),
            summary=f"verified={verified}",
        )
        return SubmitIntentResult(
            intent_id=intent_id,
            attempt_id=0,
            intent_status=updated.status,
            attempt_status="",
            package_submission_state=aggregate_package_submission_state(states),
            http_called=True,
            dry_run=False,
            verified=verified,
        )

    def _try_verify_after_success(
        self,
        *,
        intent_id: int,
        package_db_id: int,
        expected_track_no: str,
    ) -> bool:
        if self._client is None:
            return False
        package_sn = self._repo.get_package_sn_by_db_id(package_db_id)
        if not package_sn:
            return False
        try:
            detail = self._client.fetch_package_detail(package_sn)
        except Exception:  # noqa: BLE001 — leave SUCCESS
            return False
        if not isinstance(detail, dict):
            return False
        if not tracking_matches_detail(detail, expected_track_no):
            return False
        self._repo.mark_submission_intent_verified(
            intent_id=intent_id,
            summary=f"packageDetail trackNo matched {expected_track_no}",
        )
        return True
