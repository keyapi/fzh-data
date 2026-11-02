# -*- coding: utf-8 -*-
"""PO↔DN v2 修复点的单元测试（F1–F4）。

重点验证「不许发生的事」：
- 逐 SKU 数量误差不能相互对冲（F2）
- 多别名不能静默选一个（F3）
- 反查别名必须清 `删除` 前缀（F4）
- 纯内胆 / FBA 必须归到「无需匹配」，不能算无候选（业务规则）
- 正式归属只认 EN 字段（F1 的数据层回归）
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "po_dn_match_v2", ROOT / "scripts" / "po_dn_candidate_match_v2.py"
)
assert _SPEC and _SPEC.loader
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


def test_qty_fit_rejects_per_sku_cancellation():
    """DN(10,90) vs PO(90,10)：旧总数法给 1.0，逐 SKU 必须给 0。"""
    fit, coverage, unmatched = mod.per_sku_qty_fit({"A": 10, "B": 90}, {"A": 90, "B": 10})
    assert fit == 0.0
    assert coverage == pytest.approx(20 / 100)
    assert unmatched == []


def test_qty_fit_exact_and_unmatched():
    fit, coverage, unmatched = mod.per_sku_qty_fit({"A": 5, "B": 5}, {"A": 5})
    assert fit == pytest.approx(0.5)   # B 全差 5 / DN 合计 10
    assert coverage == pytest.approx(0.5)
    assert unmatched == ["B"]


def test_qty_fit_po_excess_is_penalised_but_bounded():
    fit, coverage, _ = mod.per_sku_qty_fit({"A": 10}, {"A": 12})
    assert fit == pytest.approx(0.8)
    assert coverage == 1.0


def test_clean_code_strips_delete_prefix():
    assert mod.clean_code("删除TT0312587K0064173") == "TT0312587K0064173"
    assert mod.clean_code("  c/velvet-grey-153-705-wow ") == "C/VELVET-GREY-153-705-WOW"
    assert mod.clean_code(None) is None


def test_resolve_aliases_unique_and_normalized_suffix():
    sku, basis = mod.resolve_aliases(["TT0000668K0063796"])
    assert (sku, basis) == ("TT0000668K0063796", "item_code_unique")
    sku, basis = mod.resolve_aliases(["TT0000668K0063796", "TT0000668K0063796-Cover"])
    assert (sku, basis) == ("TT0000668K0063796", "item_code_unique")


def test_resolve_aliases_channel_rule_and_ambiguity():
    # 渠道别名（FBA）被过滤后唯一 → 解析
    sku, basis = mod.resolve_aliases(["BNMIANMAGREEN194FBA1", "CEN961NLINEN-SAGEGREEN-194"])
    assert (sku, basis) == ("CEN961NLINEN-SAGEGREEN-194", "item_code_channel_rule")
    # 两个都是正常货品码 → 隔离，不选
    sku, basis = mod.resolve_aliases(["CENKZ1324-SKYBLUE-153", "CENMM1621-BLUE-153"])
    assert sku is None and basis == "ambiguous"
    # 关闭渠道规则时同样的行也隔离（敏感性口径）
    sku, basis = mod.resolve_aliases(
        ["BNMIANMAGREEN194FBA1", "CEN961NLINEN-SAGEGREEN-194"], use_channel_rule=False
    )
    assert sku is None and basis == "ambiguous"


def test_classify_dn_pure_liner_and_fba():
    import pandas as pd

    pure = pd.DataFrame(
        {"customer": ["DANEEY"] * 2, "item_code": ["ND#KS0001-60-CYF-WHITE", "ND#KS0001-60-CYF-WHITE"]}
    )
    assert mod.classify_dn(pure) == "pure_liner"

    fba = pd.DataFrame({"customer": ["美国FBA仓"], "item_code": ["KS0001-DM-153-IVORY"]})
    assert mod.classify_dn(fba) == "fba"

    mixed = pd.DataFrame(
        {"customer": ["DANEEY", "DANEEY"], "item_code": ["PK#KS0001-X-153", "ND#KS0001-153-CYF-WHITE"]}
    )
    assert mod.classify_dn(mixed) == "matchable"


def test_official_links_export_matches_expected_set():
    """F1/F5 数据层回归：正式链接来自 EN 字段导出，8 张已知全部在内。"""
    export = Path("D:/Work/fzh-order-store/analysis/en_dn_po_field_2026-10-28.json")
    if not export.exists():
        return
    rows = json.loads(export.read_text(encoding="utf-8"))
    links = {
        r["name"]: (r.get("custom_tongtool_purchase_order") or "").strip()
        for r in rows
        if (r.get("custom_tongtool_purchase_order") or "").strip()
    }
    expected = {
        "DN-26-00086": "PO021725",
        "DN-26-00087": "PO021724",
        "DN-26-00104-1": "PO021737",
        "DN-26-00110": "PO021738",
        "DN-26-00111": "PO021739",
        "DN-26-00112": "PO021740",
        "DN-26-00113-1": "PO021741",
        "DN-26-00115": "PO021743",
    }
    for dn, po in expected.items():
        assert links.get(dn) == po
