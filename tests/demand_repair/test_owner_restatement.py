from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D3B = ROOT / "scripts" / "d3b_history_backtest_v3_5_2026-11-03.py"
D5 = ROOT / "scripts" / "d5_time_validated_v6_3_2026-11-03.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


d3b = _load(D3B, "d3b_v35")
d5 = _load(D5, "d5_v63")


def _b10(rows):
    return pd.DataFrame(rows, columns=["产品键", "地区", "是否需求行", "美国责任方",
                                       "最强证据层级"])


def test_owner_map_requires_unique_us_owner():
    frame = _b10([
        ("P1", "US", "Y", "美中USTX", "own90"),
        ("P2", "US", "Y", None, "own90"),
        ("P3", "US", "Y", "美东USNJ", "own90"),
        ("P3", "US", "Y", "美中USTX", "dn2025"),
        ("P4", "PL", "Y", "美中USTX", "own90"),
    ])
    owner, basis, reason, _ = d3b.build_owner_maps(frame)

    assert owner["P1"] == "美中USTX"
    assert owner["P2"] is None and reason["P2"] == "missing_owner"
    assert owner["P3"] is None and reason["P3"].startswith("multi_owner")
    assert owner.get("P4") is None  # only US demand rows may carry a US owner


def test_owner_evidence_is_selected_deterministically():
    frame = _b10([
        ("P1", "US", "Y", "美中USTX", "own180"),
        ("P1", "US", "Y", "美中USTX", "dn2025"),
    ])
    owner, basis, _, _ = d3b.build_owner_maps(frame)
    assert owner["P1"] == "美中USTX"
    assert basis["P1"] == "dn2025"


def test_current_pool_restates_us_and_preserves_other_pools():
    owner = {"US1": "美中USTX", "US2": "美东USNJ", "NONE": None}
    assert d3b.current_pool_of("美东USNJ", owner["US1"]) == "美中USTX"
    assert d3b.current_pool_of("美中USTX", owner["US2"]) == "美东USNJ"
    assert d3b.current_pool_of("美东USNJ", owner["NONE"]) == "US_unassigned"
    assert d3b.current_pool_of("波兰", owner["NONE"]) == "波兰"


def test_current_key_set_collapses_two_us_pools_and_keeps_reduction():
    asof = {
        ("A", "美东USNJ", "成品", "个"),
        ("A", "美中USTX", "成品", "个"),
        ("B", "美东USNJ", "成品", "个"),
        ("C", "波兰", "成品", "个"),
        ("D", "美东USNJ", "皮壳", "个"),
    }
    current, mapping = d3b.build_current_key_set(
        asof, {"A": "美中USTX", "B": "美东USNJ", "C": None, "D": None})

    assert len(current) == 4  # A's two pools collapse; C/D keep non-US/unassigned
    assert ("A", "美中USTX", "成品", "个") in current
    assert ("B", "美东USNJ", "成品", "个") in current
    assert ("C", "波兰", "成品", "个") in current
    assert ("D", "US_unassigned", "皮壳", "个") in current
    assert len(asof) - len(current) == 1
    assert mapping[("A", "美东USNJ", "成品", "个")] == ("A", "美中USTX", "成品", "个")


def test_current_form_normalisation_only_when_unique():
    by_prod = {"P": {("美中USTX", "成品", "个")}}
    key, why = d3b.fix_key_current("P", "美中USTX", "皮壳", "个", by_prod)
    assert key == ("P", "美中USTX", "成品", "个") and why.startswith("form归一")

    by_prod = {"P": {("美中USTX", "成品", "个"), ("美中USTX", "皮壳", "个")}}
    key, why = d3b.fix_key_current("P", "美中USTX", "套件", "个", by_prod)
    assert key == ("P", "美中USTX", "套件", "个") and why == "跨 form 多候选"


def test_d5_market_of_keeps_current_owner_pools_in_us_market():
    assert d5.market_of("美东USNJ") == "US"
    assert d5.market_of("美中USTX") == "US"
    assert d5.market_of("US_unassigned") == "US"
    assert d5.market_of("波兰") == "PL"
    assert d5.market_of("CG-USTX") == "CG"
