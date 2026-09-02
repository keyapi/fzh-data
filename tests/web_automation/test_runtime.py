from pathlib import Path

import pytest

from web_automation.scripts.runtime import (  # noqa: E402
    BLOCKING_STATES,
    MODES,
    classify_failure,
    load_capabilities,
    resolve_capability,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "web_automation" / "capabilities.yaml"


def test_matrix_contains_phase_a_routes():
    matrix = load_capabilities(MATRIX)
    assert {
        "tongtu.stock.export",
        "tongtu.sales.export",
        "sellfox.stock.export",
        "sellfox.other-inbound.import",
        "sellfox.other-outbound.import",
        "sellfox.restock.import",
        "web.generic.explore",
    } <= set(matrix)


def test_modes_and_states_are_closed_sets():
    assert MODES == {
        "API_ONLY",
        "API_FIRST_BROWSER_FALLBACK",
        "BROWSER_ONLY",
        "MANUAL_CONFIRM",
    }
    assert BLOCKING_STATES == {
        "NEED_BROWSER",
        "NEED_LOGIN",
        "NEED_OCR",
        "NEED_USER_CONFIRMATION",
        "BLOCKED",
    }


def test_auth_error_never_falls_back():
    cap = resolve_capability(load_capabilities(MATRIX), "sellfox.stock.export")
    assert classify_failure(cap, "AUTH_FAILED") == "blocked"
    assert classify_failure(cap, "ENDPOINT_UNSUPPORTED") == "fallback"


def test_unknown_task_is_rejected():
    with pytest.raises(KeyError, match="unknown capability"):
        resolve_capability(load_capabilities(MATRIX), "sellfox.unknown")
