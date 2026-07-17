"""Unit tests for package-level submission state aggregation (P1C)."""

from __future__ import annotations

import pytest

from sellfox_shipping.submission_state import (
    ALLOWED_INTENT_STATES,
    aggregate_package_submission_state,
)


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("READY",), "TRACKING_REVIEWED"),
        (("READY", "READY"), "TRACKING_REVIEWED"),
        (("READY", "FAILED"), "PARTIAL_READY"),
        (("READY", "SUCCESS"), "PARTIAL_READY"),
        (("READY", "VERIFIED"), "PARTIAL_READY"),
        (("IN_FLIGHT",), "SUBMITTING"),
        (("IN_FLIGHT", "FAILED"), "SUBMITTING"),
        (("IN_FLIGHT", "READY"), "SUBMITTING"),
        (("UNKNOWN",), "PARTIAL_UNKNOWN"),
        (("UNKNOWN", "READY"), "PARTIAL_UNKNOWN"),
        (("UNKNOWN", "IN_FLIGHT"), "PARTIAL_UNKNOWN"),
        (("FAILED",), "SUBMIT_FAILED"),
        (("FAILED", "FAILED"), "SUBMIT_FAILED"),
        (("FAILED", "SUCCESS"), "PARTIAL_FAILED"),
        (("FAILED", "VERIFIED"), "PARTIAL_FAILED"),
        (("VERIFIED",), "VERIFIED"),
        (("VERIFIED", "VERIFIED"), "VERIFIED"),
        (("SUCCESS",), "SUBMITTED_PENDING_VERIFY"),
        (("SUCCESS", "SUCCESS"), "SUBMITTED_PENDING_VERIFY"),
        (("SUCCESS", "VERIFIED"), "SUBMITTED_PENDING_VERIFY"),
    ],
)
def test_aggregate_priority_cases(
    states: tuple[str, ...], expected: str
) -> None:
    assert aggregate_package_submission_state(states) == expected


def test_empty_or_illegal_is_blocked() -> None:
    assert aggregate_package_submission_state([]) == "BLOCKED"
    assert aggregate_package_submission_state(()) == "BLOCKED"
    assert aggregate_package_submission_state(["NOPE"]) == "BLOCKED"
    assert aggregate_package_submission_state(["READY", "NOPE"]) == "BLOCKED"


def test_allowed_intent_states_match_plan() -> None:
    assert ALLOWED_INTENT_STATES == frozenset(
        {"READY", "VERIFIED", "SUCCESS", "FAILED", "UNKNOWN", "IN_FLIGHT"}
    )
