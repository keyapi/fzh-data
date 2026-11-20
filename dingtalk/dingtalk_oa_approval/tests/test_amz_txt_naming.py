# -*- coding: utf-8 -*-
from amz_txt_naming import propose_txt_name


def test_strusery_us_hyphen():
    new, why = propose_txt_name("AMZStrusery-US-1005.txt", hint_ym="2026-10")
    assert new == "AMZStruseryUS-2026-10-05.txt", (new, why)


def test_strip_dup_suffix():
    new, _ = propose_txt_name("AMZTOODDLYUS-2026-10-16(1).txt", hint_ym="2026-10")
    assert new == "AMZTOODDLYUS-2026-10-16.txt"


def test_mmdd():
    new, _ = propose_txt_name("AMZStruseryUS-1015.txt", hint_ym="2026-10")
    assert new == "AMZStruseryUS-2026-10-15.txt"
