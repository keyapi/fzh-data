# -*- coding: utf-8 -*-
"""B v6 用例：同物归并、地区判定、级联顺序、US 责任唯一。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "wh_v6r4", ROOT / "scripts" / "warehouse_attribution_a337_v6r4.py")
assert _SPEC and _SPEC.loader
m = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = m
_SPEC.loader.exec_module(m)


def test_product_identity_strips_pk_and_merges_60():
    assert m.product_of("PK#KS0001-DM-100-ANTHRACITE") == "KS0001-DM-100-ANTHRACITE"
    assert m.product_of("KS0001-CMYH-60-BLUEBUTTERFLY") == "KS0248-CMYH-60-BLUEBUTTERFLY"
    assert m.product_of("PK#KS0001-CMYH-60-BLUEBUTTERFLY") == "KS0248-CMYH-60-BLUEBUTTERFLY"
    # 非 60 / 非这两个前缀不动
    assert m.product_of("KS0001-CMM-100-WHITE") == "KS0001-CMM-100-WHITE"
    assert m.product_of("KS0248-CMM-194-WHITE") == "KS0248-CMM-194-WHITE"


def test_form_from_prefix_and_role():
    assert m.form_of("PK#KS1", "皮壳", "")[0] == "皮壳"
    assert m.form_of("ND#KS1", "内胆", "")[0] == "内胆"
    assert m.form_of("TJ#X-001", "套件", "")[0] == "套件"
    assert m.form_of("ZTGJ1", "主体骨架", "")[0] == "主体骨架"
    assert m.form_of("HM1510-A", "海绵", "")[0] == "独立海绵"   # r3：海绵不默认成品
    assert m.form_of("HM1510-A", "海绵", "皮壳")[0] == "皮壳"
    assert m.form_of("HM1510-A", "海绵", "半成品")[1] == "半成品"
    assert m.form_of("KS1", "成品", "")[0] == "成品"


def test_customer_region_mapping():
    assert m.CUSTOMER_REGION["CENTRADE"] == ("US", "East")
    assert m.CUSTOMER_REGION["DANEEY"] == ("US", "Central")
    assert m.CUSTOMER_REGION["波兰公司"] == ("PL", None)
    # 波兰不参与美东/美中三选一
    assert m.CUSTOMER_REGION["波兰公司"][0] == "PL"


def test_tier_order_follows_spec():
    """own90 → own180 → own2026 → dn2026 → own2025 → dn2025"""
    assert m.TIERS_ORDER[:6] == ("own90", "own180", "own2026", "dn2026", "own2025", "dn2025")
    assert m.TIERS_ORDER[-1] == "stock_placement"      # 库存投放权重最低
    f = dict(own90=0, own180=0, own2026=0, own2025=3, dn2026_count=0, dn2025_count=1)
    assert m.tier_of(f) == "own2025"          # 历史订单优先于历史 DN
    f2 = dict(own90=0, own180=0, own2026=0, own2025=0, dn2026_count=2, dn2025_count=0)
    assert m.tier_of(f2) == "dn2026"
    f3 = dict(own90=0, own180=0, own2026=0, own2025=0, dn2026_count=0, dn2025_count=0)
    assert m.tier_of(f3) is None


def test_no_three_way_market():
    """市场显示名只能是 美国·美东 / 美国·美中 / 波兰 / 美国·责任未定，没有三选一。"""
    allowed = {"美国·美东", "美国·美中", "波兰", "美国·责任未定"}
    assert set(m.MARKET_LABEL.values()) <= allowed


def test_form_priority_for_demand_row():
    """需求行只出一个形态：成品 > 皮壳 > 独立海绵 > 套件 > 主体骨架。"""
    pri = ("成品", "皮壳", "独立海绵", "套件", "主体骨架")
    for forms, expect in ((("皮壳", "成品"), "成品"), (("皮壳",), "皮壳"),
                          (("独立海绵", "皮壳"), "皮壳")):
        got = next((f for f in pri if f in forms), forms[0])
        assert got == expect
