# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.sku_map import (
    CEN_BLACK97,
    DO_NOT_TOUCH,
    OLD_TO_NEW,
    RULE_CANON_FOAM100,
    RULE_TYPO_FOAM97,
    sku_col,
)


def test_old_to_new_is_one_to_one() -> None:
    assert len(OLD_TO_NEW) == len(set(OLD_TO_NEW.values()))
    assert not set(OLD_TO_NEW) & set(OLD_TO_NEW.values())


def test_gray60_and_foam97_are_not_order_remaps() -> None:
    assert "BNFBAvelvetgray60" in DO_NOT_TOUCH
    assert RULE_TYPO_FOAM97 not in OLD_TO_NEW
    assert RULE_CANON_FOAM100 not in OLD_TO_NEW
    assert CEN_BLACK97 not in OLD_TO_NEW
    assert CEN_BLACK97 not in DO_NOT_TOUCH


def test_sku_col_prefers_tongtool_name() -> None:
    df = pd.DataFrame(columns=["图片", "MSKU", "通途SKU", "SKU"])
    assert sku_col(df) == "通途SKU"


def test_sku_col_falls_back_to_sku() -> None:
    df = pd.DataFrame(columns=["图片", "MSKU", "SKU", "品类"])
    assert sku_col(df) == "SKU"
