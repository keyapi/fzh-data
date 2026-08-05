"""Package-level aggregation of order SubmissionIntent states (P1C).

Pure function — no I/O. Spec: research-synthesis §3.3.
"""

from __future__ import annotations

from collections.abc import Iterable

ALLOWED_INTENT_STATES = frozenset(
    {"READY", "VERIFIED", "SUCCESS", "FAILED", "UNKNOWN", "IN_FLIGHT"}
)


def aggregate_package_submission_state(
    intent_states: Iterable[str],
) -> str:
    """Derive package submission UI/state from current order-level intent states.

    Priority: UNKNOWN > IN_FLIGHT > READY > FAILED > VERIFIED > SUCCESS/VERIFIED.
    Empty or illegal input → BLOCKED.
    """
    states = list(intent_states)
    if not states or any(state not in ALLOWED_INTENT_STATES for state in states):
        return "BLOCKED"
    if any(state == "UNKNOWN" for state in states):
        return "PARTIAL_UNKNOWN"
    if any(state == "IN_FLIGHT" for state in states):
        return "SUBMITTING"
    if any(state == "READY" for state in states):
        return (
            "TRACKING_REVIEWED"
            if all(state == "READY" for state in states)
            else "PARTIAL_READY"
        )
    if any(state == "FAILED" for state in states):
        return (
            "SUBMIT_FAILED"
            if all(state == "FAILED" for state in states)
            else "PARTIAL_FAILED"
        )
    if all(state == "VERIFIED" for state in states):
        return "VERIFIED"
    if all(state in {"SUCCESS", "VERIFIED"} for state in states):
        return "SUBMITTED_PENDING_VERIFY"
    return "BLOCKED"
