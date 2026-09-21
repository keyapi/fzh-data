import pandas as pd
import pytest

from ding_xlsx import build_key, norm_amount, unique_key
from late_submission_keys import keys_for_period


def test_norm_amount_collapses_int_float_and_str():
    """线上回归：表里存 `0.0`、导出侧算 `0`，同一个 0 金额必须归一到同一个键。"""
    for v in (0, 0.0, "0", "0.0", "0.00", " 0 "):
        assert norm_amount(v) == "0", v
    assert norm_amount("13773.45") == "13773.45"
    assert norm_amount(285.8) == "285.8"
    assert norm_amount("-28.2") == "-28.2"
    assert norm_amount(1000) == "1000"


def test_norm_amount_passes_through_non_numeric_and_blank():
    assert norm_amount("") == ""
    assert norm_amount(None) == ""
    assert norm_amount(float("nan")) == ""
    assert norm_amount("abc") == "abc"


def test_build_key_is_dtype_independent():
    """金额从 Excel、从 Google 表读进来可能是 int / float / str，键必须一致。"""
    keys = {
        build_key("202608041508000385990", "2026-07-06", "eBay（US）", amt)
        for amt in ("0", "0.0", 0, 0.0)
    }
    assert keys == {"202608041508000385990|2026-07-06|eBay（US）|0"}


def test_unique_key_matches_registry_row_for_live_ebay_case():
    """登记表那行（销售额存成 `0`）和导出侧那行（浮点 0.0）要落到同一个键。"""
    export_row = pd.Series(
        {
            "审批编号": "202608041508000385990",
            "账期日期": "2026-07-06",
            "销售账户_展开": "eBay（US）",
            "销售额": 0.0,
        }
    )
    sheet_row = {
        "审批编号": "202608041508000385990",
        "账期日期": "2026-07-06",
        "销售账户": "eBay（US）",
        "销售额": "0",
    }
    assert unique_key(export_row) == build_key(
        sheet_row["审批编号"], sheet_row["账期日期"], sheet_row["销售账户"], sheet_row["销售额"]
    )


HEADER = ["审批编号", "账期日期", "销售账户", "销售额", "应收账款", "后续账期须剔除", "动作"]


def _rows():
    return [
        # 迟交：账期在 7 月、8/9 月核算都要剔除
        ["202608040956000194652", "2026-07-24", "AMZTOODDLYUS", "13773.45", "0", "2026-08,2026-09", "迟交补入7月核算"],
        # 迟交但销售额空、只有应收账款 → 落应收账款
        ["202608060947000411145", "2026-07-25", "AMZBAINADE", "", "-45.37", "2026-08,2026-09", "迟交补入7月核算"],
        # 早交：账期属 8 月，剔除列留空 → 8 月核算要保留
        ["202607310900000052516", "2026-08-04", "WFUS", "1.00", "0", "", "早交：账期属8月"],
    ]


def test_keys_for_period_takes_only_rows_tagged_for_that_month():
    keys, skipped = keys_for_period(HEADER, _rows(), "2026-08")
    assert keys == [
        "202608040956000194652|2026-07-24|AMZTOODDLYUS|13773.45",
        "202608060947000411145|2026-07-25|AMZBAINADE|-45.37",
    ]
    assert skipped == []


def test_keys_for_period_keeps_early_submission_out_of_august():
    """早交行（剔除列空）不能被当成 8 月要剔除的对象。"""
    keys, _ = keys_for_period(HEADER, _rows(), "2026-08")
    assert not any("WFUS" in k for k in keys)


def test_keys_for_period_september_matches_same_late_rows():
    keys, _ = keys_for_period(HEADER, _rows(), "2026-09")
    assert len(keys) == 2


def test_keys_for_period_unknown_month_is_empty():
    keys, _ = keys_for_period(HEADER, _rows(), "2026-10")
    assert keys == []


def test_keys_for_period_skips_duplicate_keys():
    rows = _rows() + [_rows()[0]]
    keys, skipped = keys_for_period(HEADER, rows, "2026-08")
    assert len(keys) == 2
    assert any("重复" in s for s in skipped)


def test_keys_for_period_requires_registry_columns():
    with pytest.raises(SystemExit, match="审批编号"):
        keys_for_period(["别的列"], [], "2026-08")


def test_keys_for_period_tolerates_short_rows():
    """Google 表末尾常有缺列的行，不能因此抛 IndexError。"""
    rows = [["202608040956000194652", "2026-07-24", "AMZTOODDLYUS", "1", "0", "2026-08"]]
    keys, _ = keys_for_period(HEADER, rows, "2026-08")
    assert keys == ["202608040956000194652|2026-07-24|AMZTOODDLYUS|1"]
