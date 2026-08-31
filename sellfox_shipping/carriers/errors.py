"""Carrier-neutral failure evidence used by label orchestration."""

from __future__ import annotations


class CarrierFailure(RuntimeError):
    VALID_OUTCOMES = {
        "not_sent",
        "rejected",
        "retryable_query",
        "ambiguous",
        "accepted_pending",
    }

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        outcome: str,
        category: str,
        provider_code: str = "",
        http_status: int | None = None,
        provider_order_id: str = "",
        tracking_number: str = "",
        safe_to_create_again: bool = False,
    ):
        if outcome not in self.VALID_OUTCOMES:
            raise ValueError(f"unknown carrier failure outcome: {outcome}")
        if safe_to_create_again and outcome not in {"not_sent", "rejected"}:
            raise ValueError(
                "safe_to_create_again requires outcome not_sent or rejected"
            )
        super().__init__(message)
        self.phase = phase
        self.outcome = outcome
        self.category = category
        self.provider_code = provider_code
        self.http_status = http_status
        self.provider_order_id = provider_order_id
        self.tracking_number = tracking_number
        self.safe_to_create_again = safe_to_create_again


def classify_http_failure(
    *, phase: str, status_code: int | None
) -> tuple[str, str, bool]:
    """Return outcome, category, safe-to-create based on phase-aware evidence."""
    if phase != "create":
        category = "rate_limited" if status_code == 429 else "provider_http"
        return "retryable_query", category, False
    if status_code in {400, 401, 403, 404, 409, 422}:
        category = (
            "authentication" if status_code in {401, 403} else "validation"
        )
        return "rejected", category, True
    if status_code == 429:
        return "ambiguous", "rate_limited", False
    if status_code is not None and status_code >= 500:
        return "ambiguous", "provider_5xx", False
    return "ambiguous", "transport", False
