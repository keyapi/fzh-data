# -*- coding: utf-8 -*-
"""冻结需求净额表的入口契约：不许降级、不许混用字段。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from supply_netting.demand import (DemandContractError, SERIES_DEFAULT, SERIES_THIRD_PARTY,
                                   load_demand_netting, series_rows, unclassified_quantity)


def frame(**overrides):
    base = dict(
        demand_date=["2026-10-20", "2026-10-20"],
        canonical_sku=["S1", "S1"],
        canonical_warehouse=["W", "W"],
        canonical_uom=["个", "个"],
        quantity=[5, 3],
        quantity_default=[5, 0],
        quantity_third_party=[0, 3],
        netting_allowed=[True, True],
        in_default_series=[True, False],
        order_count=[1, 1], line_count=[1, 1],
    )
    base.update(overrides)
    return pd.DataFrame(base)


class DemandContractTests(unittest.TestCase):
    def write(self, df):
        tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
        tmp.close()
        df.to_parquet(tmp.name, index=False)
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return tmp.name

    def test_accepts_frozen_shape(self):
        df, meta = load_demand_netting(self.write(frame(
            canonical_sku=["S1", "S2"])))
        self.assertEqual(meta["four_key_duplicates"], 0)
        self.assertTrue(meta["netting_allowed_all"])

    def test_rejects_duplicate_four_key(self):
        with self.assertRaises(DemandContractError):
            load_demand_netting(self.write(frame()))

    def test_rejects_blocked_rows(self):
        with self.assertRaises(DemandContractError):
            load_demand_netting(self.write(frame(
                canonical_sku=["S1", "S2"], netting_allowed=[True, False])))

    def test_missing_column_is_an_error(self):
        df = frame(canonical_sku=["S1", "S2"]).drop(columns=["quantity_default"])
        with self.assertRaises(DemandContractError):
            load_demand_netting(self.write(df))

    def test_default_series_uses_quantity_default(self):
        df, _ = load_demand_netting(self.write(frame(canonical_sku=["S1", "S2"])))
        default = series_rows(df, SERIES_DEFAULT)
        third = series_rows(df, SERIES_THIRD_PARTY)
        self.assertEqual([r["quantity"] for r in default], [5])
        self.assertEqual([r["quantity"] for r in third], [3])
        self.assertEqual(default[0]["series"], SERIES_DEFAULT)

    def test_in_default_series_is_not_derived_from_netting_allowed(self):
        # netting_allowed=True 但 in_default_series=False 的行只能进 3PL 序列
        df, _ = load_demand_netting(self.write(frame(canonical_sku=["S1", "S2"])))
        third = series_rows(df, SERIES_THIRD_PARTY)
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0]["quantity"], 3)

    def test_unclassified_quantity_is_reported(self):
        df = frame(canonical_sku=["S1", "S2"])
        df.loc[0, "quantity_default"] = 2  # 5 = 2 + 0 + 3 未归类
        self.assertEqual(unclassified_quantity(df), 3.0)


if __name__ == "__main__":
    unittest.main()
