from __future__ import annotations

import pytest

from dingtalk.dingtalk_group_harvest import dws_client


def test_validate_complete_accepts_clean_ledger():
    dws_client.validate_complete(
        {"complete": True, "hasMore": False, "failures": []}, "test"
    )


@pytest.mark.parametrize(
    "data",
    [
        {"complete": False, "hasMore": False, "failures": []},
        {"complete": True, "hasMore": True, "failures": []},
        {"complete": True, "hasMore": False, "failures": [{"message": "x"}]},
    ],
)
def test_validate_complete_rejects_incomplete(data):
    with pytest.raises(dws_client.DwsIncompleteError):
        dws_client.validate_complete(data, "test")


def test_parse_json_surfaces_error():
    raw = '{"error": {"message": "boom"}}'
    with pytest.raises(dws_client.DwsError, match="boom"):
        dws_client.parse_json(raw)


def test_parse_json_recovers_json_after_log_lines():
    raw = 'log line\n{"ok": true}\n'
    assert dws_client.parse_json(raw) == {"ok": True}
