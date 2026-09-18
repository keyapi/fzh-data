# -*- coding: utf-8 -*-
from __future__ import annotations

import create_permissions_ledger_sheet as ledger


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_parse_drive_list_raises_on_http_error():
    try:
        ledger.parse_drive_list_response(_Resp(403, {"error": {"message": "denied"}}))
    except RuntimeError as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("expected HTTP error to raise")


def test_parse_drive_list_returns_files_on_200():
    files = ledger.parse_drive_list_response(_Resp(200, {"files": [{"id": "1"}]}))
    assert files == [{"id": "1"}]


def test_refuse_apply_when_drive_list_empty():
    reason = ledger.apply_blocked_reason(file_count=0, new_row_count=1, existing_row_count=300)
    assert reason


def test_refuse_apply_when_new_snapshot_collapses():
    reason = ledger.apply_blocked_reason(file_count=2, new_row_count=10, existing_row_count=300)
    assert reason


def test_allow_apply_when_counts_are_sane():
    assert ledger.apply_blocked_reason(file_count=80, new_row_count=280, existing_row_count=300) is None
