# -*- coding: utf-8 -*-
"""多窗口切片：真实桶边界、累计不插值、窗口不可相加、180 仅情景、UOM 隔离。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from supply_netting.scripts.horizon_windows import KEY, build_windows

AS_OF = datetime(2026, 10, 26, 5, 17, 34, tzinfo=timezone(timedelta(hours=8)))


def buckets(weeks: int):
    out = [dict(bucket_id="protect", start=AS_OF, end=AS_OF + timedelta(days=7))]
    cursor = AS_OF + timedelta(days=7)
    for index in range(1, weeks + 1):
        out.append(dict(bucket_id=f"w{index}", start=cursor, end=cursor + timedelta(days=7)))
        cursor += timedelta(days=7)
    return out


def netting_rows(weeks: int, uom="个", sku="S1", per_bucket=10.0, opening=0.0):
    rows = [dict(bucket_id="protect", **{"canonical_sku": sku, "canonical_warehouse": "W",
                                         "canonical_uom": uom},
                 period_demand=per_bucket, receipts=0.0, unserved=per_bucket,
                 gap=per_bucket, opening=opening, conditional_receipts=0.0)]
    for index in range(1, weeks + 1):
        rows.append(dict(bucket_id=f"w{index}", **{"canonical_sku": sku,
                                                   "canonical_warehouse": "W",
                                                   "canonical_uom": uom},
                         period_demand=per_bucket, receipts=0.0,
                         unserved=per_bucket * (index + 1), gap=per_bucket * (index + 1),
                         opening=opening, conditional_receipts=0.0))
    return pd.DataFrame(rows)


EMPTY_HISTORY = pd.DataFrame(columns=KEY + ["demand_date", "quantity"])


class HorizonWindowTests(unittest.TestCase):
    def test_windows_use_real_bucket_boundaries(self):
        summary, _ = build_windows(netting_rows(26), buckets(26), AS_OF, EMPTY_HISTORY)
        by_window = {row["window_days"]: row for row in summary.to_dict("records")}
        # 30 天：第一个结束 ≥ as_of+30 的桶是 w4（结束于 +35 天）
        self.assertEqual(by_window[30]["bucket_id"], "w4")
        self.assertEqual(by_window[30]["actual_days"], 35.0)
        self.assertEqual(by_window[30]["buckets_count"], 5)     # protect + w1..w4
        self.assertEqual(by_window[180]["bucket_id"], "w25")
        self.assertEqual(by_window[180]["actual_days"], 182.0)
        self.assertEqual(by_window[180]["buckets_count"], 26)

    def test_windows_are_cumulative_and_not_additive(self):
        summary, _ = build_windows(netting_rows(26), buckets(26), AS_OF, EMPTY_HISTORY)
        by_window = {row["window_days"]: row for row in summary.to_dict("records")}
        demand = [by_window[k]["forecast_demand"] for k in (30, 60, 90, 120, 150, 180)]
        unserved = [by_window[k]["cum_unserved"] for k in (30, 60, 90, 120, 150, 180)]
        self.assertEqual(demand, sorted(demand))
        self.assertEqual(unserved, sorted(unserved))
        # 60 天 = protect + w1..w8，共 9 个桶 ×10；不是 30 天的子集相加
        self.assertAlmostEqual(by_window[60]["forecast_demand"], 90.0)
        self.assertAlmostEqual(by_window[30]["forecast_demand"], 50.0)
        self.assertAlmostEqual(by_window[180]["forecast_demand"], 260.0)

    def test_unserved_comes_from_the_last_bucket_not_string_order(self):
        summary, _ = build_windows(netting_rows(26), buckets(26), AS_OF, EMPTY_HISTORY)
        by_window = {row["window_days"]: row for row in summary.to_dict("records")}
        # protect=10, w1=20, …, w25=260
        self.assertAlmostEqual(by_window[180]["cum_unserved"], 260.0)
        self.assertGreater(by_window[120]["cum_unserved"], by_window[90]["cum_unserved"])

    def test_180_is_marked_scenario_only(self):
        summary, _ = build_windows(netting_rows(26), buckets(26), AS_OF, EMPTY_HISTORY)
        usage = {row["window_days"]: row["usage"] for row in summary.to_dict("records")}
        self.assertEqual(usage[180], "scenario_only")
        self.assertEqual(usage[60], "review_candidate")

    def test_uom_groups_are_not_merged(self):
        frames = [netting_rows(26, uom="个", sku="S1", per_bucket=10.0),
                  netting_rows(26, uom="套", sku="S1", per_bucket=1.0)]
        summary, _ = build_windows(pd.concat(frames, ignore_index=True), buckets(26),
                                   AS_OF, EMPTY_HISTORY)
        rows = summary[summary["window_days"] == 60]
        self.assertEqual(sorted(rows["uom"]), ["个", "套"])
        by_uom = {row["uom"]: row for row in rows.to_dict("records")}
        self.assertAlmostEqual(by_uom["个"]["forecast_demand"], 90.0)
        self.assertAlmostEqual(by_uom["套"]["forecast_demand"], 9.0)
        # 不产生无单位合计行
        self.assertEqual(len(rows), 2)

    def test_key_rows_reconcile_with_summary(self):
        summary, keys = build_windows(netting_rows(26), buckets(26), AS_OF, EMPTY_HISTORY)
        for window in (30, 90, 180):
            s = summary[summary["window_days"] == window].iloc[0]
            k = keys[keys["window_days"] == window]
            self.assertAlmostEqual(s["forecast_demand"], float(k["forecast_demand"].sum()))
            self.assertAlmostEqual(s["cum_unserved"], float(k["cum_unserved"].sum()))


if __name__ == "__main__":
    unittest.main()
