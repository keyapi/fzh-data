# -*- coding: utf-8 -*-
from __future__ import annotations

import share_tongtu_order_editor as share


def test_default_is_dry_run_no_email():
    parsed = share.parse_argv(["share_tongtu_order_editor.py"])
    assert parsed["apply"] is False
    assert parsed["email"] is None


def test_apply_flag_is_not_treated_as_email():
    parsed = share.parse_argv(["share_tongtu_order_editor.py", "--apply"])
    assert parsed["apply"] is True
    assert parsed["email"] is None


def test_email_plus_apply():
    parsed = share.parse_argv(["share_tongtu_order_editor.py", "--apply", "fin@x.com"])
    assert parsed["apply"] is True
    assert parsed["email"] == "fin@x.com"


def test_dash_prefix_without_apply_is_rejected():
    try:
        share.parse_argv(["share_tongtu_order_editor.py", "--nope"])
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown flag")
