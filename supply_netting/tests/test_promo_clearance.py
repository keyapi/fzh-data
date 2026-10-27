# -*- coding: utf-8 -*-
"""9 月异常拆分类用例：五类判定、清库存标记、汇总占比、报告边界。"""

from __future__ import annotations

import pandas as pd

from supply_netting.promo_clearance import CATEGORIES, classify, summarise, write_report


def frame():
    rows = [
        # 断货 + 有在途 → 回补有补货
        dict(sku="A", aug_zero=4, on_order=20, price_chg=-0.05, ratio=2.1, cause="断货回补+有补货"),
        # 断货 + 降价 + 无在途 → 清库存
        dict(sku="B", aug_zero=4, on_order=0, price_chg=-0.12, ratio=2.5,
             cause="断货回补后降价清库存嫌疑"),
        # 断货 + 无降价 + 无在途 → 回补未补货
        dict(sku="C", aug_zero=4, on_order=0, price_chg=0.02, ratio=2.2, cause="断货回补(未补货)"),
        # 无断货 + 单价不动 → 非价格因素
        dict(sku="D", aug_zero=0, on_order=0, price_chg=0.005, ratio=2.4, cause="非价格因素"),
        # 无断货 + 降价 → 清库存
        dict(sku="E", aug_zero=0, on_order=0, price_chg=-0.20, ratio=3.0, cause="降价清库存嫌疑"),
    ]
    demo = pd.DataFrame(rows)
    for month in range(1, 10):
        demo[f"2026-{month:02d}"] = 10.0
    demo["2026-09"] = [10, 22, 13, 12, 30]
    demo["2026-08"] = 5.0
    return demo


def test_five_category_rules():
    out = classify(frame()).set_index("sku")
    assert out.loc["A", "category"] == "断货回补+有补货"
    assert out.loc["B", "category"] == "回补后降价清库存"
    assert out.loc["C", "category"] == "回补未补货"
    assert out.loc["D", "category"] == "非价格因素"
    assert out.loc["E", "category"] == "回补后降价清库存"
    assert set(out["category"]) <= set(CATEGORIES)


def test_clearance_flag_and_demand_exclusion():
    out = classify(frame()).set_index("sku")
    assert bool(out.loc["B", "clearance_suspect"]) is True
    assert bool(out.loc["E", "clearance_suspect"]) is True
    assert bool(out.loc["A", "clearance_suspect"]) is False
    assert "不得当正常需求" in out.loc["B", "demand_exclusion"]
    assert out.loc["A", "demand_exclusion"] == ""
    assert all("unavailable" in text for text in out["promotion_evidence"])


def test_summary_counts_shares_and_agreement():
    out = classify(frame())
    summary = summarise(out)
    assert summary["candidates"] == 5
    assert summary["clearance_skus"] == 2
    assert summary["clearance_sept_qty"] == 52.0      # B 22 + E 30
    assert summary["clearance_sept_share"] > 0
    assert summary["promo_evidence"] == "unavailable"
    assert summary["agreement_with_original"] is not None


def test_report_states_boundaries_and_no_calendar(tmp_path):
    out = classify(frame())
    summary = summarise(out)
    path = tmp_path / "report.md"
    write_report(path, out, summary, "2026-10-28T00:00:00+08:00", dict(candidates="c.csv"))
    text = path.read_text(encoding="utf-8")
    assert "isPromotion 不可得" in text
    assert "不虚构因果" in text
    assert "不建促销日历" in text
    assert "不得混入正常需求" in text or "不得当正常需求" in text
    assert "与原标签的差异" in text
