from channel_account_sync.owners import (
    collapsed_segments,
    effective_owner,
    en_last_owner,
    needed_for_existing,
    month_columns,
)


def _rec(**months: str) -> dict:
    return {f"运营人员{ym}": val for ym, val in months.items()}


def test_empty_before_go_live_is_skipped():
    assert effective_owner("", had_owner=False) is None
    assert effective_owner("样品", had_owner=False) is None


def test_empty_after_go_live_becomes_pending():
    assert effective_owner("", had_owner=True) == "待分配"
    assert effective_owner("样品", had_owner=True) == "待分配"


def test_pending_tokens_are_written_as_is():
    assert effective_owner("待分配", had_owner=False) == "待分配"
    assert effective_owner("待定", had_owner=True) == "待定"


def test_consecutive_same_person_collapses_to_one_row():
    rec = _rec(
        **{
            "202511": "于彬",
            "202512": "于彬",
            "202601": "于彬",
            "202607": "林俊彪",
            "202608": "陈立彬",
        }
    )
    segs = collapsed_segments(rec)
    assert [(s["from_ym"], s["from_date"], s["owner"]) for s in segs] == [
        ("202511", "2025-11-01", "于彬"),
        ("202607", "2026-07-01", "林俊彪"),
        ("202608", "2026-08-01", "陈立彬"),
    ]


def test_needed_skips_until_person_changes_vs_en():
    segs = [
        {"from_ym": "202511", "from_date": "2025-11-01", "owner": "于彬"},
        {"from_ym": "202607", "from_date": "2026-07-01", "owner": "林俊彪"},
        {"from_ym": "202608", "from_date": "2026-08-01", "owner": "陈立彬"},
    ]
    needed = needed_for_existing(segs, "2025-11-01", "于彬")
    assert [s["owner"] for s in needed] == ["林俊彪", "陈立彬"]


def test_needed_skips_same_person_even_in_later_months():
    segs = [
        {"from_ym": "202607", "from_date": "2026-07-01", "owner": "林俊彪"},
        {"from_ym": "202608", "from_date": "2026-08-01", "owner": "林俊彪"},
    ]
    assert needed_for_existing(segs, "2026-07-01", "林俊彪") == []


def test_combo_ampersand_name_is_one_owner_string():
    rec = _rec(**{"202608": "荆春雨&张振朋"})
    segs = collapsed_segments(rec)
    assert segs == [
        {"from_ym": "202608", "from_date": "2026-08-01", "owner": "荆春雨&张振朋"}
    ]


def test_en_last_owner_picks_latest_from_date():
    fd, user = en_last_owner(
        {
            "owners": [
                {"user": "于彬", "from_date": "2025-11-01"},
                {"user": "林俊彪", "from_date": "2026-07-01"},
            ]
        }
    )
    assert (fd, user) == ("2026-07-01", "林俊彪")


def test_month_columns_oldest_first():
    header = ["渠道账号", "运营人员202608", "运营人员202511", "运营人员202607"]
    assert month_columns(header) == ["运营人员202511", "运营人员202607", "运营人员202608"]
