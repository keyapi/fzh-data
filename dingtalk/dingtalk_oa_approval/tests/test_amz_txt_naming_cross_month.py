# -*- coding: utf-8 -*-
"""文件名短日期跨月 + 重命名目标碰撞。"""
from amz_txt_naming import propose_txt_name, settlement_date_from_stem


def test_mmdd_prev_month_same_year():
    """账期月 2026-10 的桶里出现 -0930 → 2026-09-30（旧实现返回 None）。"""
    assert settlement_date_from_stem("AMZStruseryUS-0930", hint_ym="2026-10") == "2026-09-30"
    new, why = propose_txt_name("AMZStruseryUS-0930.txt", hint_ym="2026-10")
    assert new == "AMZStruseryUS-2026-09-30.txt", why


def test_mmdd_cross_year_uses_previous_year():
    """账期月 2026-01 的桶里出现 -1231 → 2025-12-31。"""
    assert settlement_date_from_stem("AMZStruseryUS-1231", hint_ym="2026-01") == "2025-12-31"


def test_mmdd_same_as_hint_month():
    assert settlement_date_from_stem("AMZStruseryUS-1015", hint_ym="2026-10") == "2026-10-15"


def test_target_exists_is_skipped():
    new, why = propose_txt_name(
        "AMZStruseryUS-0930.txt",
        hint_ym="2026-10",
        existing={"AMZStruseryUS-2026-09-30.txt"},
    )
    assert new is None
    assert why == "目标已存在"


def test_target_case_insensitive_collision():
    new, why = propose_txt_name(
        "AMZStruseryUS-0930.txt",
        hint_ym="2026-10",
        existing={"amzstruseryus-2026-09-30.TXT"},
    )
    assert new is None
