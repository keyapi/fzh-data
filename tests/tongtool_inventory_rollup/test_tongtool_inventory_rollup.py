# -*- coding: utf-8 -*-
"""通途库存 EN 归并用例：形态识别、映射优先级、仓池、行数守恒。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fzh_inv_rollup", ROOT / "scripts" / "tongtool_inventory_rollup.py")
assert _SPEC and _SPEC.loader
roll = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = roll
_SPEC.loader.exec_module(roll)


# ---------------------------------------------------------------- 形态

def test_form_detection_covers_variants():
    assert roll.form_of("X-Cover", None, {}) == "皮壳"
    assert roll.form_of("X-Cover2", None, {}) == "皮壳"      # 回归：Cover2 曾漏判
    assert roll.form_of("X-Foam", None, {}) == "海绵"
    assert roll.form_of("X-Foam1", None, {}) == "海绵"
    assert roll.form_of("X-Foam2", None, {}) == "海绵"
    assert roll.form_of("ND#123", None, {}) == "内胆"
    assert roll.form_of("TT0001K0001", None, {}) == "成品"


def test_registry_overrides_form_for_bundle_and_frame():
    reg = {"TT9": ("TJ#A-001", "套件#"), "TT8": ("ZTGJX", "主体骨架")}
    assert roll.form_of("TT9", "TJ#A-001", reg) == "套件"
    assert roll.form_of("TT8", "ZTGJX", reg) == "组件"


def test_strip_form_removes_cover_and_foam_suffixes():
    assert roll.strip_form("TT1-Cover") == "TT1"
    assert roll.strip_form("TT1-Cover2") == "TT1"
    assert roll.strip_form("TT1-Foam2") == "TT1"
    assert roll.strip_form("TT1") == "TT1"


# ---------------------------------------------------------------- 映射

def mapper():
    return dict(registry={},
                cc_active={"A1": "EN-ACTIVE", "B1": "EN-ACTIVE2"},
                sm_active={"C1": "EN-SKU"}, cc_deleted={"D1": "EN-DEL"})


def test_active_code_wins_over_deleted_code():
    m = mapper()
    m["cc_deleted"]["A1"] = "EN-DEL-CONFLICT"
    en, src = roll.map_sku("A1", m)
    assert en == "EN-ACTIVE" and "活跃" in src


def test_deleted_code_used_only_as_last_resort():
    en, src = roll.map_sku("D1", mapper())
    assert en == "EN-DEL" and "删除" in src


def test_mapping_falls_back_to_base_sku_for_cover():
    en, src = roll.map_sku("A1-Cover", mapper())
    assert en == "EN-ACTIVE" and "base" in src


def test_unmapped_returns_none():
    en, src = roll.map_sku("ZZZ", mapper())
    assert en is None and src == "未映射"


# ---------------------------------------------------------------- 仓池

def test_pool_classification():
    assert roll.pool_of("美东-CENTRADE") == "美国"
    assert roll.pool_of("美中-FZH-DANEEY") == "美国"
    assert roll.pool_of("波兰-FZHPoland-covers") == "波兰"
    assert roll.pool_of("WayfairCG-Cranbury仓") == "CG"
    assert roll.pool_of("美中-FZH-DANEEY-退货产品仓") == "退货仓"
    assert roll.pool_of("大件云仓") == "其他"


# ---------------------------------------------------------------- 端到端：行数守恒

def _frame(rows):
    base = dict(snapshot_date="2026-10-28", snapshot_at=pd.Timestamp("2026-10-28 05:17:51"),
                warehouse_id="w", available=1.0, intransit=0.0, waiting_shipment=0.0,
                defects=0.0, avg_cost=1.0, source="tongtool_api", run_id="r", schema_version=1)
    return pd.DataFrame([{**base, **r} for r in rows])


def test_every_row_lands_in_exactly_one_bucket():
    f = _frame([
        dict(sku="A1", warehouse_name="美东-CENTRADE", available=10.0),          # 计入
        dict(sku="A1-Cover", warehouse_name="美东-CENTRADE", available=2.0),     # 计入
        dict(sku="ZZZ", warehouse_name="美东-CENTRADE", available=5.0),          # 未映射
        dict(sku="X-FBA", warehouse_name="美东-CENTRADE", available=7.0),        # FBA
        dict(sku="A1", warehouse_name="大件云仓", available=9.0),                # 第三方
        dict(sku="A1", warehouse_name="美中-FZH-DANEEY-退货产品仓", available=1.0),  # 退货
        dict(sku="Buttonkit-pl", warehouse_name="波兰-FZHPoland-covers", available=9_999_866.0),
    ])
    uom = pd.DataFrame({"item_code": ["EN-ACTIVE"], "stock_uom": ["个"]})
    out = roll.classify(f, mapper(), {"Buttonkit-pl"}, {"大件云仓"}, uom)
    assert len(out) == len(f)
    assert set(out["bucket"]) <= {"计入", "规则排除", "未映射"}
    assert out["bucket"].value_counts().sum() == len(f)
    # 同一 SKU 可出现在多仓（合法），但 (sku, 仓) 不得重复——避免同一行被计两次
    assert not out.duplicated(subset=["sku", "warehouse_name"]).any()


def test_placeholder_threshold_excludes_big_numbers():
    f = _frame([dict(sku="A1", warehouse_name="波兰-FZHPoland-covers", available=200_000.0)])
    uom = pd.DataFrame({"item_code": ["EN-ACTIVE"], "stock_uom": ["个"]})
    out = roll.classify(f, mapper(), set(), set(), uom)
    assert out.iloc[0]["exclusion"] == "超大占位"
    assert not out.iloc[0]["is_counted"]


def test_uom_for_bundle_is_set_and_unproven_marked():
    reg = {"TT9": ("TJ#A-001", "套件#")}
    m = dict(registry=reg, cc_active={}, sm_active={}, cc_deleted={})
    f = _frame([dict(sku="TT9", warehouse_name="波兰-FZHPoland-covers", available=3.0),
                dict(sku="A1", warehouse_name="波兰-FZHPoland-covers", available=4.0)])
    uom = pd.DataFrame({"item_code": [], "stock_uom": []})   # 空缓存 → 未证
    out = roll.classify(f, m, set(), set(), uom).set_index("sku")
    assert out.loc["TT9", "form"] == "套件" and out.loc["TT9", "uom"] == "套"
    assert bool(out.loc["TT9", "uom_proven"]) is True
    assert out.loc["A1", "uom"] == "个" and bool(out.loc["A1", "uom_proven"]) is False


def test_blank_v5_sku_cell_is_not_treated_as_a_sku():
    """回归：v5「参与计算的通途SKU」为空时，str(NaN) 会把 "nan" 当成 SKU，污染差异明细。"""
    import numpy as np
    empty = pd.DataFrame({"EN物料": [], "x": [], "y": [], "z": [], "参与计算的通途SKU": []})
    v5 = dict(us=pd.DataFrame({"EN物料": ["A"], "x": [1], "y": [1], "z": [1],
                               "参与计算的通途SKU": [np.nan]}), pl=empty)
    sku2en, en2skus = roll.v5_universe(v5)
    assert "nan" not in sku2en
    assert en2skus["A"] == set()
