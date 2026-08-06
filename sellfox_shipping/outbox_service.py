"""PR 2: Sellfox writeback outbox confirmation, lease, execution and readback."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sellfox_shipping.package_repository import (
    SELLFOX_OUTBOX_RETRY_BACKOFF_SECONDS,
    SELLFOX_OUTBOX_VERIFY_BACKOFF_SECONDS,
    PackageRepository,
    SellfoxOutboxRecord,
)
from sellfox_shipping.submission_service import (
    SubmissionCasError,
    SubmissionScopeBlockedError,
    SubmissionService,
    build_canonical_request,
)


class OutboxPolicyBlockedError(RuntimeError):
    """Real writeback is not authorized by the account policy."""


@dataclass(frozen=True)
class SubmissionFailure:
    """Canonical failure taxonomy for one Sellfox writeback attempt."""

    error_class: str
    outbox_status: str
    summary: str
    retryable: bool = False


def classify_submission_failure(
    *,
    response_text: str = "",
    exception_text: str = "",
    http_status: int | None = None,
) -> SubmissionFailure:
    """Map an ambiguous Sellfox response/exception to a safe outbox outcome."""
    text = f"{response_text or ''} {exception_text or ''}".lower()
    status = http_status

    if status in {401, 403} or any(
        marker in text for marker in ("401", "403", "unauthorized", "token", "sign")
    ):
        return SubmissionFailure(
            error_class="configuration_blocked",
            outbox_status="MANUAL_REVIEW",
            summary="authentication/authorization needs human fix",
        )
    if status == 429 or any(
        marker in text for marker in ("429", "rate limit", "限流", "frequent", "频繁")
    ):
        return SubmissionFailure(
            error_class="not_sent_retryable",
            outbox_status="RETRYABLE",
            summary="explicit rate-limit rejection before side effect",
            retryable=True,
        )
    if status in {500, 502, 503, 504} or any(
        marker in text
        for marker in ("timeout", "timed out", "connection", "5xx", "502", "503")
    ):
        return SubmissionFailure(
            error_class="ambiguous",
            outbox_status="UNKNOWN_BLOCKED",
            summary="network/server result is unknown; no resubmit",
        )
    if any(
        marker in text
        for marker in (
            "invalid",
            "not found",
            "不存在",
            "参数",
            "param",
            "sku",
            "商品",
            "order item",
            "订单明细",
        )
    ):
        return SubmissionFailure(
            error_class="rejected_final",
            outbox_status="FAILED_FINAL",
            summary="explicit business rejection; fix input before new generation",
        )
    return SubmissionFailure(
        error_class="ambiguous",
        outbox_status="UNKNOWN_BLOCKED",
        summary="unrecognized failure; no automatic resubmit",
    )


def _extract_track_no(detail: dict | None) -> str:
    if not isinstance(detail, dict):
        return ""
    logistics = detail.get("logistics")
    if not isinstance(logistics, dict):
        logistics = {}
    return str(
        logistics.get("trackNo")
        or logistics.get("trackingNumber")
        or detail.get("trackNo")
        or ""
    ).strip()


class OutboxService:
    """Confirm, lease and execute Sellfox tracking writeback without re-buying labels."""

    def __init__(
        self,
        repository: PackageRepository,
        submission_service: SubmissionService | None = None,
        submit_client: object | None = None,
        now_fn=None,
    ):
        self._repo = repository
        self._submission = submission_service or SubmissionService(
            repository, submit_client
        )
        self._now = now_fn or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # -- confirmation -------------------------------------------------

    def confirm(self, *, outbox_id: int, actor: str) -> dict:
        actor = (actor or "").strip()
        if not actor:
            raise ValueError("actor is required")
        row = self._get_outbox(outbox_id)
        if row.status != "AWAITING_CONFIRMATION":
            raise RuntimeError(
                f"outbox {outbox_id} must be AWAITING_CONFIRMATION, got {row.status}"
            )
        intent = self._prepare_intent_for_outbox(row, actor)
        updated = self._repo.confirm_sellfox_outbox(
            outbox_id=outbox_id,
            submission_intent_id=intent.id,
            request_hash=intent.request_hash,
            actor=actor,
        )
        self._repo.append_audit_event(
            actor=actor,
            action="sellfox_outbox.confirm",
            entity_type="shipping_sellfox_outbox",
            entity_id=str(outbox_id),
            summary=f"intent={intent.id}",
        )
        return _outbox_result(updated)

    def confirm_batch(
        self, *, outbox_ids: list[int], actor: str
    ) -> dict:
        actor = (actor or "").strip()
        if not actor:
            raise ValueError("actor is required")
        results: list[dict] = []
        errors: list[dict] = []
        for outbox_id in outbox_ids:
            try:
                results.append(self.confirm(outbox_id=outbox_id, actor=actor))
            except (LookupError, RuntimeError, ValueError) as exc:
                errors.append(
                    {
                        "outbox_id": outbox_id,
                        "code": "confirm_failed",
                        "message": str(exc),
                        "recommended_action": "inspect_outbox",
                    }
                )
        return {
            "command": "sellfox-outbox-confirm-batch",
            "ok": not errors,
            "counts": {
                "input": len(outbox_ids),
                "success": len(results),
                "failed": len(errors),
            },
            "results": results,
            "errors": errors,
            "recommended_action": "run_once_after_confirmation",
        }

    # -- policy ---------------------------------------------------------

    def policy_show(self, account_key: str) -> dict:
        policy = self._repo.get_sellfox_writeback_policy(account_key, create=False)
        return _policy_result(policy)

    def policy_set(self, *, account_key: str, mode: str, actor: str) -> dict:
        policy = self._repo.set_sellfox_writeback_policy(
            account_key=account_key, mode=mode, actor=actor
        )
        return _policy_result(policy)

    def capability_record(
        self,
        *,
        account_key: str,
        capability_status: str,
        evidence_ref: str,
        actor: str,
    ) -> dict:
        policy = self._repo.record_sellfox_writeback_capability(
            account_key=account_key,
            capability_status=capability_status,
            evidence_ref=evidence_ref,
            actor=actor,
        )
        return _policy_result(policy)

    # -- execution ------------------------------------------------------

    def run_once(
        self,
        *,
        actor: str,
        account_key: str | None = None,
        outbox_id: int | None = None,
        dry_run: bool = True,
        allow_side_effects: bool = False,
        limit: int = 1,
    ) -> dict:
        actor = (actor or "").strip()
        if not actor:
            raise ValueError("actor is required")
        if not dry_run and not allow_side_effects:
            raise ValueError(
                "allow_side_effects required for real writeback "
                "(use --i-understand-side-effects)"
            )
        self._repo.recover_stale_sellfox_outbox(actor=actor)

        rows = self._select_rows(
            account_key=account_key, outbox_id=outbox_id, limit=limit
        )
        results: list[dict] = []
        errors: list[dict] = []
        for row in rows:
            try:
                if dry_run:
                    results.append(self._plan_row(row))
                else:
                    self._enforce_policy(row, outbox_id=outbox_id, limit=limit)
                    results.append(self._execute_row(row, actor=actor))
            except (LookupError, RuntimeError, ValueError) as exc:
                errors.append(
                    {
                        "outbox_id": row.id,
                        "package_sn": row.package_sn,
                        "code": "run_failed",
                        "message": str(exc),
                        "recommended_action": "inspect_and_resolve",
                    }
                )
        return {
            "command": "sellfox-outbox-run-once",
            "ok": not errors,
            "dry_run": dry_run,
            "counts": {
                "input": len(rows),
                "success": len(results),
                "failed": len(errors),
            },
            "results": results,
            "errors": errors,
            "recommended_action": (
                "confirm_before_real_run"
                if dry_run
                else "verify_or_inspect_results"
            ),
        }

    def verify(
        self,
        *,
        actor: str,
        account_key: str | None = None,
        outbox_id: int | None = None,
        limit: int = 10,
    ) -> dict:
        actor = (actor or "").strip()
        if not actor:
            raise ValueError("actor is required")
        rows = self._select_rows(
            account_key=account_key,
            outbox_id=outbox_id,
            limit=limit,
            statuses=("VERIFY_PENDING",),
        )
        results: list[dict] = []
        errors: list[dict] = []
        for row in rows:
            try:
                results.append(self._verify_row(row, actor=actor))
            except (LookupError, RuntimeError, ValueError) as exc:
                errors.append(
                    {
                        "outbox_id": row.id,
                        "package_sn": row.package_sn,
                        "code": "verify_failed",
                        "message": str(exc),
                        "recommended_action": "inspect_and_resolve",
                    }
                )
        return {
            "command": "sellfox-outbox-verify",
            "ok": not errors,
            "counts": {
                "input": len(rows),
                "success": len(results),
                "failed": len(errors),
            },
            "results": results,
            "errors": errors,
            "recommended_action": "inspect_verified_and_conflicts",
        }

    # -- internals ------------------------------------------------------

    def _get_outbox(self, outbox_id: int) -> SellfoxOutboxRecord:
        row = self._repo.get_sellfox_outbox(outbox_id)
        if row is None:
            raise LookupError(f"Sellfox outbox {outbox_id} not found")
        return row

    def _select_rows(
        self,
        *,
        account_key: str | None,
        outbox_id: int | None,
        limit: int,
        statuses: tuple[str, ...] = (),
    ) -> list[SellfoxOutboxRecord]:
        if outbox_id is not None:
            return [self._get_outbox(outbox_id)]
        if not account_key:
            raise ValueError("account_key is required when outbox_id is not set")
        if statuses:
            rows = self._repo.list_sellfox_outbox(
                account_key=account_key, status=statuses[0], limit=limit
            )
            return [row for row in rows if row.status in statuses]
        return self._repo.list_due_sellfox_outbox(account_key=account_key, limit=limit)

    def _prepare_intent_for_outbox(
        self, row: SellfoxOutboxRecord, actor: str
    ) -> object:
        record = self._repo.get(row.account_key, row.package_sn)
        if record is None:
            raise LookupError(f"Package {row.package_sn} not found")
        if record.local_review_status != "approved":
            raise ValueError("package local_review_status must be approved")
        tracking = (row.tracking_number or "").strip()
        package_tracking = (record.logistics.tracking_number or "").strip()
        if not tracking or tracking == row.package_sn:
            raise ValueError("outbox tracking is missing or a placeholder")
        if package_tracking != tracking:
            raise ValueError(
                "outbox tracking diverges from package tracking; re-scan candidates"
            )
        carrier = (record.logistics.channel_name or "").strip()
        if not carrier:
            raise ValueError("carrier_name is required")
        package_db_id = self._repo.get_package_db_id(row.account_key, row.package_sn)
        if package_db_id is None:
            raise LookupError(f"Package db id missing for {row.package_sn}")
        if self._repo.is_submission_scope_blocked(
            account_key=row.account_key,
            package_db_id=package_db_id,
            order_db_id=row.order_db_id,
        ):
            raise SubmissionScopeBlockedError(
                f"scope blocked for order {row.external_order_id}"
            )
        items = self._repo.list_order_items_for_package_order(
            package_db_id=package_db_id, external_order_id=row.external_order_id
        )
        if not items:
            raise ValueError(f"no items for order {row.external_order_id}")
        shipping_service = ""
        for label in self._repo.list_labels_for_package(
            account_key=row.account_key, package_sn=row.package_sn
        ):
            if (
                label.is_active
                and label.status != "cancelled"
                and label.tracking_number == tracking
            ):
                shipping_service = label.service_level or ""
                break
        _, canonical_json, request_hash = build_canonical_request(
            account_key=row.account_key,
            package_db_id=package_db_id,
            external_order_id=row.external_order_id,
            shop_id=record.shop_id,
            tracking_number=tracking,
            carrier_name=carrier,
            shipping_service=shipping_service,
            items=items,
        )
        return self._repo.upsert_submission_intent(
            account_key=row.account_key,
            package_db_id=package_db_id,
            order_db_id=row.order_db_id,
            external_order_id=row.external_order_id,
            request_hash=request_hash,
            canonical_request=canonical_json,
            confirmed_by=actor,
        )

    def _plan_row(self, row: SellfoxOutboxRecord) -> dict:
        plan = {
            "outbox_id": row.id,
            "package_sn": row.package_sn,
            "external_order_id": row.external_order_id,
            "tracking_number": row.tracking_number,
            "status": row.status,
            "confirmed": row.submission_intent_id is not None,
            "policy": self._repo.get_sellfox_writeback_policy(
                row.account_key, create=False
            ).mode,
            "action": "verify" if row.status == "VERIFY_PENDING" else "submit",
            "would_http": False,
        }
        if row.status not in {
            "PENDING",
            "RETRYABLE",
            "VERIFY_PENDING",
        }:
            plan["blocked"] = "status_not_claimable"
            plan["recommended_action"] = "inspect_candidate"
        elif row.submission_intent_id is None:
            plan["blocked"] = "not_confirmed"
            plan["recommended_action"] = "confirm_first"
        else:
            plan["blocked"] = None
            plan["recommended_action"] = "no_side_effect_in_dry_run"
        return plan

    def _enforce_policy(
        self, row: SellfoxOutboxRecord, *, outbox_id: int | None, limit: int
    ) -> None:
        policy = self._repo.get_sellfox_writeback_policy(
            row.account_key, create=False
        )
        if policy.mode == "DISABLED":
            raise OutboxPolicyBlockedError(
                "writeback policy DISABLED; record capability evidence first"
            )
        if policy.mode == "PROBE_ONLY":
            if outbox_id is None or limit != 1:
                raise OutboxPolicyBlockedError(
                    "PROBE_ONLY permits exactly one explicit --outbox-id execution"
                )
        if policy.mode == "SCOPED_BATCH" and limit > 50:
            raise OutboxPolicyBlockedError(
                "SCOPED_BATCH limit must be at most 50"
            )

    def _execute_row(self, row: SellfoxOutboxRecord, *, actor: str) -> dict:
        if row.status not in {
            "PENDING",
            "RETRYABLE",
            "VERIFY_PENDING",
        }:
            raise RuntimeError(f"outbox {row.id} status {row.status} is not claimable")
        if row.submission_intent_id is None:
            raise RuntimeError(f"outbox {row.id} is not confirmed")

        token = uuid.uuid4().hex
        if not self._repo.claim_sellfox_outbox(
            outbox_id=row.id, owner=actor, lease_token=token, lease_seconds=120
        ):
            raise RuntimeError(f"outbox {row.id} claim lost or not claimable")

        try:
            if row.status == "VERIFY_PENDING":
                return self._verify_row(row, actor=actor, lease_token=token)
            if not self._repo.mark_sellfox_outbox_in_flight(
                outbox_id=row.id, lease_token=token
            ):
                raise RuntimeError(f"outbox {row.id} lost lease before send")

            intent = self._repo.get_submission_intent(row.submission_intent_id)
            if intent is None:
                raise LookupError(f"intent {row.submission_intent_id} missing")
            if intent.status == "VERIFIED":
                self._repo.finish_sellfox_outbox(
                    outbox_id=row.id,
                    lease_token=token,
                    status="VERIFIED",
                    error_class="already_verified",
                    error_summary="intent already VERIFIED; no HTTP",
                    increment_attempt=False,
                )
                return _outbox_result(self._get_outbox(row.id))
            if intent.status == "SUCCESS":
                self._finish_verify_pending(row.id, token, attempt_count=row.attempt_count)
                return _outbox_result(self._get_outbox(row.id))
            if intent.status in {"UNKNOWN", "IN_FLIGHT"}:
                self._repo.finish_sellfox_outbox(
                    outbox_id=row.id,
                    lease_token=token,
                    status="UNKNOWN_BLOCKED",
                    error_class="ambiguous",
                    error_summary=f"intent {intent.status} cannot be resubmitted",
                    increment_attempt=False,
                )
                return _outbox_result(self._get_outbox(row.id))

            result = self._submission.submit_intent(
                intent_id=row.submission_intent_id,
                actor=actor,
                dry_run=False,
                allow_side_effects=True,
            )
            return self._finish_after_submit(row, token, result)
        except OutboxPolicyBlockedError:
            raise
        except Exception as exc:  # noqa: BLE001
            current = self._repo.get_sellfox_outbox(row.id)
            if (
                current is not None
                and current.status in {"LEASED", "IN_FLIGHT"}
                and current.lease_token == token
            ):
                failure = classify_submission_failure(exception_text=str(exc))
                self._repo.finish_sellfox_outbox(
                    outbox_id=row.id,
                    lease_token=token,
                    status=failure.outbox_status,
                    error_class=failure.error_class,
                    error_summary=failure.summary,
                    increment_attempt=False,
                )
            raise

    def _finish_after_submit(self, row, token, result) -> dict:
        if result.intent_status == "VERIFIED":
            self._repo.finish_sellfox_outbox(
                outbox_id=row.id,
                lease_token=token,
                status="VERIFIED",
                error_class="",
                error_summary="",
                increment_attempt=True,
            )
        elif result.intent_status == "SUCCESS":
            self._finish_verify_pending(row.id, token, attempt_count=row.attempt_count)
        elif result.intent_status == "UNKNOWN":
            self._repo.finish_sellfox_outbox(
                outbox_id=row.id,
                lease_token=token,
                status="UNKNOWN_BLOCKED",
                error_class="ambiguous",
                error_summary="submit result UNKNOWN; no resubmit",
                increment_attempt=True,
            )
        elif result.intent_status == "FAILED":
            attempt = (
                self._repo.get_submission_attempt(result.attempt_id)
                if result.attempt_id
                else None
            )
            failure = classify_submission_failure(
                response_text=attempt.http_summary if attempt else "",
                http_status=attempt.http_status if attempt else None,
            )
            if (
                failure.outbox_status == "RETRYABLE"
                and row.attempt_count + 1 >= 5
            ):
                failure = SubmissionFailure(
                    error_class="not_sent_retryable",
                    outbox_status="MANUAL_REVIEW",
                    summary="retry budget exhausted; human review required",
                )
            next_attempt_at = None
            if failure.outbox_status == "RETRYABLE":
                delay_index = min(row.attempt_count, 4)
                next_attempt_at = self._now() + timedelta(
                    seconds=SELLFOX_OUTBOX_RETRY_BACKOFF_SECONDS[delay_index]
                )
            self._repo.finish_sellfox_outbox(
                outbox_id=row.id,
                lease_token=token,
                status=failure.outbox_status,
                error_class=failure.error_class,
                error_summary=failure.summary,
                increment_attempt=True,
                next_attempt_at=next_attempt_at,
            )
        else:
            self._repo.finish_sellfox_outbox(
                outbox_id=row.id,
                lease_token=token,
                status="UNKNOWN_BLOCKED",
                error_class="ambiguous",
                error_summary=f"unexpected intent status {result.intent_status}",
                increment_attempt=True,
            )
        return _outbox_result(self._get_outbox(row.id))

    def _finish_verify_pending(
        self, outbox_id: int, token: str, *, attempt_count: int
    ) -> None:
        if attempt_count >= 4:
            next_attempt_at = self._now() + timedelta(hours=1)
        else:
            next_attempt_at = self._now() + timedelta(
                seconds=SELLFOX_OUTBOX_VERIFY_BACKOFF_SECONDS[
                    min(attempt_count, 3)
                ]
            )
        self._repo.finish_sellfox_outbox(
            outbox_id=outbox_id,
            lease_token=token,
            status="VERIFY_PENDING",
            error_class="verify_pending",
            error_summary="accepted; waiting for packageDetail readback",
            increment_attempt=True,
            next_attempt_at=next_attempt_at,
        )

    def _verify_row(
        self,
        row: SellfoxOutboxRecord,
        *,
        actor: str,
        lease_token: str = "",
    ) -> dict:
        client = getattr(self._submission, "_client", None)
        if client is None:
            self._repo.finish_sellfox_outbox(
                outbox_id=row.id,
                lease_token=lease_token,
                status="MANUAL_REVIEW",
                error_class="configuration_blocked",
                error_summary="readback client unavailable",
                increment_attempt=False,
            )
            raise RuntimeError("readback client unavailable for verification")
        try:
            detail = client.fetch_package_detail(row.package_sn)
        except Exception as exc:  # noqa: BLE001
            failure = classify_submission_failure(exception_text=str(exc))
            if failure.outbox_status == "RETRYABLE":
                status = "VERIFY_PENDING"
                error_class = "verify_pending"
                summary = "readback transient failure; keep waiting"
                if row.attempt_count >= 4:
                    next_attempt_at = self._now() + timedelta(hours=1)
                else:
                    next_attempt_at = self._now() + timedelta(
                        seconds=SELLFOX_OUTBOX_VERIFY_BACKOFF_SECONDS[
                            min(row.attempt_count, 3)
                        ]
                    )
            else:
                status = "UNKNOWN_BLOCKED"
                error_class = failure.error_class
                summary = f"readback failed: {failure.summary}; no resubmit"
                next_attempt_at = None
            self._repo.finish_sellfox_outbox(
                outbox_id=row.id,
                lease_token=lease_token,
                status=status,
                error_class=error_class,
                error_summary=summary,
                increment_attempt=True,
                next_attempt_at=next_attempt_at,
            )
            raise
        actual = _extract_track_no(detail)
        if actual == row.tracking_number:
            status = "VERIFIED"
            error_class = ""
            error_summary = f"packageDetail trackNo matched {row.tracking_number}"
        elif not actual or actual == row.package_sn:
            status = "VERIFY_PENDING"
            error_class = "verify_pending"
            error_summary = "trackNo not visible yet; keep waiting"
        else:
            status = "CONFLICT"
            error_class = "readback_conflict"
            error_summary = (
                "packageDetail trackNo differs from confirmed tracking; "
                "no overwrite, human review required"
            )
        next_attempt_at = None
        if status == "VERIFY_PENDING":
            if row.attempt_count >= 4:
                next_attempt_at = self._now() + timedelta(hours=1)
            else:
                next_attempt_at = self._now() + timedelta(
                    seconds=SELLFOX_OUTBOX_VERIFY_BACKOFF_SECONDS[
                        min(row.attempt_count, 3)
                    ]
                )
        self._repo.finish_sellfox_outbox(
            outbox_id=row.id,
            lease_token=lease_token,
            status=status,
            error_class=error_class,
            error_summary=error_summary,
            increment_attempt=True,
            next_attempt_at=next_attempt_at,
        )
        self._repo.append_audit_event(
            actor=actor,
            action="sellfox_outbox.verify_readback",
            entity_type="shipping_sellfox_outbox",
            entity_id=str(row.id),
            summary=f"status={status}",
        )
        return _outbox_result(self._get_outbox(row.id))


def _policy_result(policy) -> dict:
    return {
        "command": "sellfox-outbox-policy",
        "ok": True,
        "counts": {"input": 1, "success": 1, "failed": 0},
        "results": [
            {
                "account_key": policy.account_key,
                "mode": policy.mode,
                "capability_status": policy.capability_status,
                "evidence_ref": policy.evidence_ref,
                "approved_by": policy.approved_by,
                "approved_at": policy.approved_at,
            }
        ],
        "errors": [],
        "recommended_action": "record_capability_before_probe",
    }


def _outbox_result(row: SellfoxOutboxRecord) -> dict:
    return {
        "outbox_id": row.id,
        "account_key": row.account_key,
        "package_id": row.package_id,
        "package_sn": row.package_sn,
        "order_db_id": row.order_db_id,
        "external_order_id": row.external_order_id,
        "generation": row.generation,
        "tracking_number": row.tracking_number,
        "status": row.status,
        "submission_intent_id": row.submission_intent_id,
        "request_hash": row.request_hash,
        "attempt_count": row.attempt_count,
        "confirmed_by": row.confirmed_by,
        "confirmed_at": row.confirmed_at,
        "next_attempt_at": row.next_attempt_at,
        "lease_owner": row.lease_owner,
        "lease_expires_at": row.lease_expires_at,
        "last_error_class": row.last_error_class,
        "last_error_summary": row.last_error_summary,
        "conflicts_with_outbox_id": row.conflicts_with_outbox_id,
        "sources": [
            {"source_type": source.source_type, "source_id": source.source_id}
            for source in row.sources
        ],
        "recommended_action": "inspect_status",
    }
