# -*- coding: utf-8 -*-
"""账期过滤必须同时按审批状态（完成/审批中且非拒绝）过滤。"""
from __future__ import annotations

import pandas as pd

from ding_xlsx import enrich
from filter_export_by_period import filter_period_rows


def _enriched() -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "账期日期": ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-10-09"],
            "发起时间": ["2026-11-05 10:00:00"] * 5,
            "审批状态": ["完成", "审批中", "已撤销", "完成", "完成"],
            "审批结果": ["同意", "", "", "拒绝", "同意"],
            "选择平台": ["亚马逊"] * 5,
            "AMZCTRD账户": ["AMZCTRDUS"] * 5,
            "销售额": [10, 20, 30, 40, 50],
            "审批编号": ["A", "B", "C", "D", "E"],
        }
    )
    return enrich(df)


def test_only_approved_rows_kept():
    kept, counts = filter_period_rows(_enriched(), "2026-11", set())
    assert counts == {"period": 4, "excluded_status": 2, "excluded_late": 0, "kept": 2}
    assert sorted(kept["审批编号"]) == ["A", "B"]  # 已撤销 C、拒绝 D 被剔除；10 月 E 不在本月


def test_exclude_keys_still_applies():
    en = _enriched()
    keys = set(en.loc[en["审批编号"] == "A", "_key"])
    kept, counts = filter_period_rows(en, "2026-11", keys)
    assert counts["excluded_late"] == 1
    assert counts["kept"] == 1
    assert list(kept["审批编号"]) == ["B"]
