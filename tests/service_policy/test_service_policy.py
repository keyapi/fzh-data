# -*- coding: utf-8 -*-
"""P2a 服务分档测试：ABC/XYZ→A/B/C/D、class→quantile、D6 动作净额。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from supply_netting.service_policy import (
    CLASS_QUANTILE, assign_abc, assign_service_class, assign_xyz, class_quantile,
)

ROOT = Path(__file__).resolve().parents[2]


def _load_builder():
    path = ROOT / "scripts" / "build_service_policy_20261112.py"
    spec = importlib.util.spec_from_file_location("build_service_policy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_abc_80_15_5():
    abc = assign_abc(pd.Series([50.0, 30.0, 15.0, 5.0]))
    assert list(abc) == ["A", "A", "B", "C"]


def test_xyz_mapping():
    assert assign_xyz("smooth", "smooth") == "X"
    assert assign_xyz("intermittent", "intermittent") == "Y"
    assert assign_xyz("lumpy", "lumpy") == "Z"
    assert assign_xyz("smooth", "new") == "Z"


def test_service_matrix():
    assert assign_service_class("A", "X", "smooth", 10) == "A"
    assert assign_service_class("A", "Z", "lumpy", 10) == "B"
    assert assign_service_class("B", "Y", "intermittent", 10) == "B"
    assert assign_service_class("B", "Z", "lumpy", 10) == "C"
    assert assign_service_class("C", "X", "smooth", 10) == "C"
    assert assign_service_class("C", "Z", "lumpy", 10) == "D"
    assert assign_service_class("A", "X", "new", 10) == "D"
    assert assign_service_class("A", "X", "obsolescent", 10) == "D"
    assert assign_service_class("A", "X", "smooth", 0) == "D"


def test_class_quantile_and_unknown():
    assert [class_quantile(c)["quantile"] for c in ("A", "B", "C", "D")] == [
        0.95, 0.90, 0.85, 0.85]
    with pytest.raises(ValueError):
        class_quantile("Z")


def test_build_policy_synthetic():
    mod = _load_builder()
    keys = ["product_id", "pool", "physical_form", "canonical_uom"]
    d3b = pd.DataFrame([
        dict(product_id="P1", pool="波兰", physical_form="成品", canonical_uom="个",
             sbc_class_train="smooth", demand_pattern_train="smooth"),
        dict(product_id="P2", pool="波兰", physical_form="成品", canonical_uom="个",
             sbc_class_train="intermittent", demand_pattern_train="intermittent"),
        dict(product_id="P3", pool="波兰", physical_form="成品", canonical_uom="个",
             sbc_class_train="lumpy", demand_pattern_train="lumpy"),
        dict(product_id="P4", pool="波兰", physical_form="成品", canonical_uom="个",
             sbc_class_train="smooth", demand_pattern_train="new"),
    ])
    series = pd.DataFrame([
        dict(product_id="P1", pool="波兰", physical_form="成品", canonical_uom="个",
             month="202601", qty=50.0),
        dict(product_id="P2", pool="波兰", physical_form="成品", canonical_uom="个",
             month="202601", qty=30.0),
        dict(product_id="P3", pool="波兰", physical_form="成品", canonical_uom="个",
             month="202601", qty=15.0),
        dict(product_id="P4", pool="波兰", physical_form="成品", canonical_uom="个",
             month="202601", qty=5.0),
    ])
    pol = mod.build_policy(d3b, series).set_index("product_id")
    assert pol.loc["P1", "class"] == "A"          # ABC A + X
    assert pol.loc["P2", "class"] == "A"          # ABC A + Y
    assert pol.loc["P3", "class"] == "C"          # ABC B + Z
    assert pol.loc["P4", "class"] == "D"          # new -> D
    assert pol.loc["P1", "quantile"] == 0.95
    assert pol.loc["P3", "quantile"] == 0.85
    assert pol.loc["P4", "quantile"] == 0.85


def test_d6_action_uses_net_selected_not_net95():
    text = (ROOT / "scripts" / "d6_top50_sandbox_v6_23_20261112.py").read_text(
        encoding="utf-8")
    action_block = text[text.index("def action_of"):text.index("acts = [action_of")]
    assert "r.net_selected" in action_block
    assert "r.net_95" not in action_block
    assert "split_actions(r.net_selected" in text
    assert "split_actions(r.net_95" not in text
