# -*- coding: utf-8 -*-
"""A337 v5 用例：60cm 合并、出库仓→市场→DN客户。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fzh_a337v5", ROOT / "scripts" / "warehouse_attribution_a337_v5.py")
assert _SPEC and _SPEC.loader
m = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = m
_SPEC.loader.exec_module(m)


def test_merge60_collapses_ks0001_and_ks0248():
    assert m.merge60("KS0001-CMYH-60-BLUEBUTTERFLY") == "KS0248-CMYH-60-BLUEBUTTERFLY"
    assert m.merge60("KS0248-CMYH-60-BLUEBUTTERFLY") == "KS0248-CMYH-60-BLUEBUTTERFLY"
    # PK# 前缀保留
    assert m.merge60("PK#KS0001-DM-60-GREY") == "PK#KS0248-DM-60-GREY"
    assert m.merge60("PK#KS0248-DM-60-GREY") == "PK#KS0248-DM-60-GREY"


def test_merge60_leaves_non_60_alone():
    assert m.merge60("KS0001-XMMBS-194-HEMPNATURAL") == "KS0001-XMMBS-194-HEMPNATURAL"
    assert m.merge60("KS0003-DM-60-GREY") == "KS0003-DM-60-GREY"      # 非 KS0248/KS0001
    assert m.merge60("KS0248-CMM-100-WHITE") == "KS0248-CMM-100-WHITE"  # 100cm 不动


def test_market_from_warehouse():
    assert m.market_of_wh("美东-CENTRADE") == "美东"
    assert m.market_of_wh("FZH-DANEEY-皮壳仓库") == "美中"
    assert m.market_of_wh("美中-FZH-DANEEY") == "美中"
    assert m.market_of_wh("波兰-FZHPoland-covers") == "波兰"
    assert m.market_of_wh("WayfairCG-Cranbury仓") == "CG"


def test_dn_customer_mapping():
    assert m.dn_customer("美东") == "CENTRADE"
    assert m.dn_customer("美中") == "DANEEY"
    assert m.dn_customer("波兰") == "波兰公司"
    assert m.dn_customer("未证") == "无DN证据"
