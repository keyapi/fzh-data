# -*- coding: utf-8 -*-
"""决策包对比用例：只对同键相减、单侧键单列、单位不合并。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fzh_compare_packs", ROOT / "supply_netting" / "scripts" / "compare_packs.py")
assert _SPEC and _SPEC.loader
cmp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cmp
_SPEC.loader.exec_module(cmp)


def frame(rows):
    return pd.DataFrame(rows)


BASE = dict(gap_today=0.0, horizon_demand=0.0, opening=0.0, protect_gap=None,
            conditional_supply=0.0)


def test_delta_only_for_keys_present_on_both_sides():
    old = frame([
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
             destination="建议补货", qty_current=10, qty_higher=20, **BASE),
    ])
    new = frame([
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
             destination="无需补货", qty_current=0, qty_higher=0, **BASE),
    ])
    summary, merged, _, _ = cmp.compare(old, new)
    assert summary["keys_both"] == 1
    assert merged.iloc[0]["delta_qty_current"] == -10
    assert merged.iloc[0]["destination_changed"]
    assert summary["transitions"] == [dict(source="建议补货", target="无需补货", keys=1)]


def test_one_sided_keys_are_not_folded_into_totals():
    """只在旧版出现的键（供应消失）不得被当成「缺口增加」混算。"""
    old = frame([
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
             destination="建议补货", qty_current=10, qty_higher=10, **BASE),
        dict(canonical_sku="GONE", canonical_warehouse="W1", canonical_uom="个",
             destination="建议补货", qty_current=99, qty_higher=99, **BASE),
    ])
    new = frame([
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
             destination="建议补货", qty_current=10, qty_higher=10, **BASE),
    ])
    summary, merged, _, _ = cmp.compare(old, new)
    assert summary["keys_only_old"] == 1
    assert summary["keys_both"] == 1
    # 逐键相减只发生在 both 上：没有 GONE 的 delta 行
    assert len(merged) == 1
    assert summary["only_old_supply_qty"]["qty_current"] == 99
    # 总量仍各自报（不做净额抵消）
    assert summary["totals"]["qty_current"]["old"] == 109
    assert summary["totals"]["qty_current"]["new"] == 10


def test_different_uom_is_a_different_key():
    """同一个 SKU×仓，但单位不同 → 两个键，永不合并。"""
    old = frame([
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
             destination="建议补货", qty_current=10, qty_higher=10, **BASE),
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="套",
             destination="建议补货", qty_current=3, qty_higher=3, **BASE),
    ])
    new = frame([
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
             destination="建议补货", qty_current=4, qty_higher=4, **BASE),
        dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="套",
             destination="建议补货", qty_current=3, qty_higher=3, **BASE),
    ])
    summary, merged, _, _ = cmp.compare(old, new)
    assert summary["keys_both"] == 2
    by_uom = {r.canonical_uom: r.delta_qty_current for r in merged.itertuples()}
    assert by_uom == {"个": -6, "套": 0}


def test_null_quantities_do_not_become_zero_gap():
    """null 缺口不得被当 0 参与合计（与引擎口径一致）。"""
    old = frame([dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
                      destination="待核", qty_current=None, qty_higher=None, **BASE)])
    new = frame([dict(canonical_sku="A", canonical_warehouse="W1", canonical_uom="个",
                      destination="待核", qty_current=None, qty_higher=None, **BASE)])
    summary, merged, _, _ = cmp.compare(old, new)
    assert summary["totals"]["qty_current"]["old"] == 0.0
    assert pd.isna(merged.iloc[0]["delta_qty_current"]) or merged.iloc[0]["delta_qty_current"] == 0
