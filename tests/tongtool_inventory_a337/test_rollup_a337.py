# -*- coding: utf-8 -*-
"""A337 归并回归用例：码规范化、皮壳不回落成品、共享码不硬归。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fzh_a337", ROOT / "scripts" / "tongtool_inventory_rollup_a337.py")
assert _SPEC and _SPEC.loader
m = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = m
_SPEC.loader.exec_module(m)


def test_norm_casefolds_and_strips_prefixes():
    assert m.norm("  TT0031K001 ") == "tt0031k001"
    assert m.norm("删除TT0031K001") == "tt0031k001"
    assert m.norm("~TT0031K001") == "tt0031k001"
    assert m.norm("?~TT0031K001-Foam") == "tt0031k001-foam"
    assert m.norm("~删除TT0031K001") == "tt0031k001"      # 前缀可叠加
    assert m.norm("N/BXP2920-BlueButterfly-60") == "n/bxp2920-bluebutterfly-60"


def test_cover_regex_matches_variants():
    assert m.COVER_RE.match("tt1-cover")
    assert m.COVER_RE.match("tt1-Cover2")
    assert not m.COVER_RE.match("tt1-foam")


def test_pool_classification():
    assert m.pool_of("美东-CENTRADE") == "美国"
    assert m.pool_of("波兰-FZHPoland-covers") == "波兰"
    assert m.pool_of("WayfairCG-Cranbury仓") == "CG"
    assert m.pool_of("大件云仓") == "第三方(大件云仓)"
    assert m.pool_of("美中-FZH-DANEEY-退货产品仓") == "退货仓"


def test_uom_bundle_is_set_and_unproven_marked():
    uoms = {"KS0001-A": "个"}
    assert m.uom_of("TJ#X-001", "套件", uoms) == ("套", True)
    assert m.uom_of("KS0001-A", "成品", uoms) == ("个", True)
    assert m.uom_of("KS9999-Z", "成品", uoms) == ("个", False)   # 未证
    assert m.uom_of(None, None, uoms) == ("unknown", False)
