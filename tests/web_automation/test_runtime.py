from pathlib import Path

import pytest

from web_automation.scripts.runtime import (  # noqa: E402
    BLOCKING_STATES,
    MODES,
    classify_failure,
    load_capabilities,
    parse_failure_code,
    resolve_capability,
    run_result_from_output,
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


def test_parse_failure_code_uses_last_marker():
    text = "oops\nFAILURE_CODE=AUTH_FAILED\nretry\nFAILURE_CODE=ENDPOINT_MISSING\n"
    assert parse_failure_code(text) == "ENDPOINT_MISSING"
    assert parse_failure_code("no marker here") is None


def test_nonzero_output_without_marker_is_unclassified():
    result = run_result_from_output(1, "失败，请检查日志。\n")
    assert result.returncode == 1
    assert result.failure_code == "UNCLASSIFIED_FAILURE"


def test_zero_exit_ignores_failure_code_marker():
    result = run_result_from_output(0, "完成！\nFAILURE_CODE=ENDPOINT_MISSING\n")
    assert result.returncode == 0
    assert result.failure_code is None


def test_nonzero_output_reads_emitted_code():
    result = run_result_from_output(1, "  [失败] 404\nFAILURE_CODE=ENDPOINT_MISSING\n")
    assert result.failure_code == "ENDPOINT_MISSING"
