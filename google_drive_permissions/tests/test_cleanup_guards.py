# -*- coding: utf-8 -*-
from __future__ import annotations

import cleanup_gsheet_permissions as cleanup


def test_skip_owner_even_if_on_remove_list():
    assert cleanup.should_skip_delete(
        "gone@x.com", {"role": "owner", "id": "p1"}, add_email="fin@x.com"
    ) is True


def test_skip_current_finance_add_email():
    assert cleanup.should_skip_delete(
        "fin@x.com", {"role": "writer", "id": "p2"}, add_email="fin@x.com"
    ) is True


def test_writer_on_remove_list_is_not_skipped():
    assert cleanup.should_skip_delete(
        "gone@x.com", {"role": "writer", "id": "p3"}, add_email="fin@x.com"
    ) is False


def test_phase2_blocked_when_any_phase1_add_failed():
    assert cleanup.phase2_may_run(ok_add=2, add_plan_len=3) is False


def test_phase2_allowed_when_phase1_empty_or_complete():
    assert cleanup.phase2_may_run(ok_add=0, add_plan_len=0) is True
    assert cleanup.phase2_may_run(ok_add=3, add_plan_len=3) is True
