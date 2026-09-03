# -*- coding: utf-8 -*-
"""removed_accounts / kept_accounts 必须跟 README 用词一致。"""
from __future__ import annotations

import sheet_ledger


def _rows(*items: dict) -> list[dict]:
    return list(items)


def test_cleanup_handling_is_a_removal_target():
    row = {"account": "a@x.com", "status": "在职", "note": "", "handling": "清理"}
    assert sheet_ledger.is_removed_row(row) is True


def test_departed_plus_keep_is_not_removed():
    row = {"account": "b@x.com", "status": "离职", "note": "", "handling": "保留"}
    assert sheet_ledger.is_removed_row(row) is False


def test_already_cleaned_stays_in_remove_set_for_idempotent_rerun():
    row = {"account": "c@x.com", "status": "离职", "note": "", "handling": "已清理"}
    assert sheet_ledger.is_removed_row(row) is True


def test_do_not_cancel_is_never_removed():
    row = {"account": "d@x.com", "status": "离职", "note": "", "handling": "不取消"}
    assert sheet_ledger.is_removed_row(row) is False


def test_removed_accounts_uses_is_removed_row(monkeypatch):
    rows = _rows(
        {"account": "a@x.com", "status": "在职", "note": "", "handling": "清理"},
        {"account": "b@x.com", "status": "离职", "note": "", "handling": "保留"},
        {"account": "c@x.com", "status": "离职", "note": "", "handling": "已清(遗留)"},
        {"account": "d@x.com", "status": "在职", "note": "", "handling": "保留"},
    )
    monkeypatch.setattr(sheet_ledger, "load_accounts", lambda gc: rows)
    assert sheet_ledger.removed_accounts(object()) == ["a@x.com", "c@x.com"]
