# -*- coding: utf-8 -*-
"""断货删失分析离线测试（合成数据，不读生产库存）。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from self_fulfilled_demand import stockout_censoring as S


def _cache() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"item_code": "TJ#A-001", "stock_uom": "套", "is_stock_item": 0},
            {"item_code": "KS-SET", "stock_uom": "套", "is_stock_item": 1},
            {"item_code": "PK#1", "stock_uom": "套", "is_stock_item": 1},
        ]
    ).set_index("item_code")


def _c(uom, status, item):
    return pd.Series({"uom": uom, "uom_status": status, "canonical_sku": item})


def test_uom_canonical_tj_is_set() -> None:
    assert S.resolve_uom(_c("套", "known_piece", "TJ#A-001"), _cache()) == (
        "套", "known_piece", "套", True
    )


def test_uom_canonical_non_tj_set_is_conflict() -> None:
    assert S.resolve_uom(_c("套", "known_piece", "KS-SET"), _cache())[2] == "uom_conflict"
    assert S.resolve_uom(_c("套", "known_piece", "PK#1"), _cache())[2] == "uom_conflict"


def test_uom_canonical_piece_and_unknown() -> None:
    assert S.resolve_uom(_c("个", "known_piece", "KS-P"), _cache())[2:] == ("个", True)
    assert S.resolve_uom(_c(None, "missing", "unmapped:X"), _cache())[2:] == ("unknown", False)


def test_build_flags_marks_only_both_state_skus() -> None:
    rows = []
    # A: 1 月有零也有正 → censored；2 月只有正 → not censored
    for d, state, av in [
        ("2026-04-01", "present_zero", 0.0),
        ("2026-04-10", "present_positive", 5.0),
        ("2026-05-01", "present_positive", 8.0),
        # B: 全零 → 不算删失（没有正库存对照）
        ("2026-04-01", "present_zero", 0.0),
        ("2026-05-01", "present_zero", 0.0),
    ]:
        rows.append(
            {
                "sku": "A" if d != "2026-05-01" or av == 8.0 else "B",
                "d": d,
                "warehouse": "W",
                "source": "pj_checkpoint",
                "confidence": "high",
                "stock_state": state,
                "available": av,
                "waiting_shipment": 0.0,
                "intransit": 0.0,
                "physical_on_hand": av,
                "likely_unavailable": state == "present_zero",
                "review_candidate": False,
                "warehouse_role": "primary_sellable",
                "sales_qty": 0.0,
            }
        )
    # 修正 B 的行（上面用 sku 表达式不够直观）
    rows[-2]["sku"] = "B"
    rows[-1]["sku"] = "B"
    stock = pd.DataFrame(rows)
    _, monthly, meta = S.build_flags(stock)
    a = monthly[monthly["sku"] == "A"].set_index("month")
    b = monthly[monthly["sku"] == "B"]
    assert bool(a.loc["2026-04", "censored"]) is True
    assert bool(a.loc["2026-05", "censored"]) is False
    assert not b["censored"].any()
    assert meta["skus_both_zero_positive"] == 1


def test_impute_conservative_uses_median_and_cap() -> None:
    y = np.array([10.0, 20.0, 0.0, 0.0])
    cens = np.array([False, False, True, True])
    # 最近 6 个非删失月：10,20 → 中位 15；P90=20 → 15
    assert S.impute_conservative(y, cens, 2) == 15.0
    # 没有任何历史 → 0
    assert S.impute_conservative(np.array([0.0]), np.array([True]), 0) == 0.0


def test_cumulative_matches_weight_sum() -> None:
    pred = np.repeat(10.0, 6)
    got = S.cumulative(pred, 90, date(2026, 10, 29))
    w = S.F.window_weights(date(2026, 10, 29), 90)
    assert abs(got - 10.0 * sum(w.values())) < 1e-9
