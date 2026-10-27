# -*- coding: utf-8 -*-
"""刷新预测接入：版本校验、窗口换桶、资格与去向。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from supply_netting.engine import build_buckets, net_target
from supply_netting.forecast import (ForecastContractError, forecast_demand_rows,
                                     load_forecast, overlap_keys)

AS_OF = datetime(2026, 10, 27, tzinfo=timezone.utc)


def sku_map(entries):
    return pd.DataFrame([dict(tongtool_sku=tt, item_codes=tuple(items),
                              n_items=len(items),
                              mapping_status="mapped" if len(items) == 1 else "ambiguous",
                              mapping_evidence="test")
                         for tt, items in entries])


def window(**changes):
    row = dict(schema_version="en-demand-forecast-v1", tongtool_sku="TT0000001",
               canonical_warehouse="W", lead_days=60, window_start="2026-10-29",
               window_end="2026-11-28", p50=300.0, p10=250.0, p90=350.0,
               allocation_share=1.0, allocation_status="allocated_by_recent_share",
               forecast_status="ok_autoets", canonical_uom="个", uom_group="个",
               uom_totals_allowed=True, netting_eligible=True, netting_block_reason=None)
    row.update(changes)
    return row


class ForecastFixture(unittest.TestCase):
    def build(self, rows, run_id="forecast-test", expected=None, *, declared=None,
              declared_rows=None, outputs=None, pin=True, pin_sha=None, drop_rows=False, rows_null=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "forecast"
        run_dir = root / run_id
        run_dir.mkdir(parents=True)
        (root / "CURRENT").write_text(run_id, encoding="utf-8")
        windows = run_dir / "forecast_sku_warehouse_windows.parquet"
        pd.DataFrame(rows).to_parquet(windows, index=False)
        import hashlib
        actual_sha = hashlib.sha256(windows.read_bytes()).hexdigest()
        if outputs is None:
            entry = dict(file=windows.name,
                         sha256=declared if declared is not None else actual_sha)
            if drop_rows:
                pass
            elif rows_null:
                entry["rows"] = None
            else:
                entry["rows"] = declared_rows if declared_rows is not None else len(rows)
            outputs = [entry]
        manifest = {
            "schema_version": "en-demand-forecast-v1", "run_id": run_id,
            "generated_at": "2026-10-27T14:54:27+08:00",
            "run": {"decision_date": "2026-10-29", "data_cutoff": "2026-10-26"},
            "code": {"git_head": "deadbeef"},
            "outputs": outputs,
        }
        (run_dir / "forecast_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        import hashlib as _h
        manifest_sha = _h.sha256((run_dir / "forecast_manifest.json").read_bytes()).hexdigest()
        if pin_sha is not None:
            expected_sha = pin_sha
        elif pin:
            expected_sha = manifest_sha
        else:
            expected_sha = None
        return load_forecast(root, expected_run_id=expected,
                             expected_manifest_sha256=expected_sha)

    def meta(self, forecast):
        buckets = build_buckets(AS_OF, protect_days=3, weeks=2)
        _, _, meta = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]), buckets=buckets, as_of=AS_OF)
        return meta


class ForecastTests(ForecastFixture):
    def test_load_verifies_version_and_records_hashes(self):
        forecast = self.build([window()], expected="forecast-test")
        self.assertEqual(forecast.run_id, "forecast-test")
        self.assertEqual(forecast.window_start, "2026-10-29")
        self.assertEqual(forecast.decision_date, "2026-10-29")
        self.assertEqual(len(forecast.manifest_sha256), 64)
        self.assertEqual(len(forecast.windows_sha256), 64)

    def test_wrong_version_is_refused(self):
        with self.assertRaises(ForecastContractError):
            self.build([window()], expected="forecast-20261027-r2")

    def test_windows_hash_mismatch_is_refused(self):
        # R3：上游声明的窗口哈希与实测不符 → 拒绝消费
        with self.assertRaises(ForecastContractError):
            self.build([window()], declared="0" * 64)

    def test_missing_or_duplicate_output_declaration_is_refused(self):
        with self.assertRaises(ForecastContractError):
            self.build([window()], outputs=[])
        with self.assertRaises(ForecastContractError):
            self.build([window()], outputs=[
                dict(file="forecast_sku_warehouse_windows.parquet", rows=1, sha256="a" * 64),
                dict(file="forecast_sku_warehouse_windows.parquet", rows=1, sha256="b" * 64)])

    def test_declared_row_count_mismatch_is_refused(self):
        with self.assertRaises(ForecastContractError):
            self.build([window()], declared_rows=999)

    def test_missing_or_null_row_count_is_refused(self):
        with self.assertRaises(ForecastContractError):   # 缺失
            self.build([window()], drop_rows=True)
        with self.assertRaises(ForecastContractError):   # null（哈希本身正确）
            self.build([window()], rows_null=True)

    def test_non_integer_row_count_is_refused(self):
        for bad in (13554.75, "13554", True, -1, 0):
            with self.assertRaises(ForecastContractError, msg=repr(bad)):
                self.build([window()], declared_rows=bad)

    def test_pin_state_is_recorded_truthfully(self):
        pinned = self.build([window()], pin=True)
        self.assertTrue(pinned.manifest_pinned)
        self.assertEqual(self.meta(pinned)["manifest_sha256_verified"], True)
        self.assertEqual(self.meta(pinned)["manifest_sha256_verification"], "pinned_match")

        unpinned = self.build([window()], pin=False)
        self.assertFalse(unpinned.manifest_pinned)
        meta = self.meta(unpinned)
        self.assertEqual(meta["manifest_sha256_verified"], False)
        self.assertEqual(meta["manifest_sha256_verification"], "unpinned")
        self.assertIsNone(meta["manifest_sha256_pinned"])

    def test_wrong_pin_is_refused(self):
        with self.assertRaises(ForecastContractError):
            self.build([window()], pin_sha="0" * 64)

    def test_window_is_spread_over_buckets_by_days(self):
        forecast = self.build([window()])
        buckets = build_buckets(AS_OF, protect_days=3, weeks=2)
        rows, evidence, meta = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]), buckets=buckets, as_of=AS_OF)
        by_bucket = {row["demand_row_id"].rsplit(":", 1)[1]: float(row["quantity"]) for row in rows}
        # 2026-10-29..11-28 = 30 天，p50=300 → 每天 10；桶只取重叠天数
        self.assertAlmostEqual(by_bucket["protect"], 10.0)   # 10-29..10-30
        self.assertAlmostEqual(by_bucket["w1"], 70.0)
        self.assertAlmostEqual(by_bucket["w2"], 70.0)        # 11-06..11-13
        # 视界只到 11-13；11-13 之后的 15 天不进任何桶（不提前摊）
        self.assertAlmostEqual(meta["demand_quantity"], 150.0)
        self.assertEqual(evidence, [])
        self.assertEqual(meta["run_id"], "forecast-test")
        self.assertEqual(meta["demand_quantity"], round(sum(by_bucket.values()), 6))
        self.assertTrue(all(row["demand_source"] == "forecast" for row in rows))

    def test_ineligible_row_is_kept_as_evidence(self):
        forecast = self.build([window(netting_eligible=False,
                                      netting_block_reason="sku_mapping_missing;uom_missing")])
        rows, evidence, meta = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]),
            buckets=build_buckets(AS_OF), as_of=AS_OF)
        self.assertEqual(rows, [])
        self.assertEqual(evidence[0]["disposition_reason"], "forecast_netting_ineligible")
        self.assertIn("sku_mapping_missing", evidence[0]["exclusion_detail"])
        self.assertEqual(meta["excluded"]["forecast_netting_ineligible"], 1)

    def test_missing_p50_is_not_zero(self):
        forecast = self.build([window(p50=float("nan"))])
        rows, evidence, meta = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]),
            buckets=build_buckets(AS_OF), as_of=AS_OF)
        self.assertEqual(rows, [])
        self.assertEqual(evidence[0]["disposition_reason"], "forecast_quantity_unproven")

    def test_ambiguous_identity_is_not_guessed(self):
        forecast = self.build([window()])
        rows, evidence, _ = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001", "KS0002"])]),
            buckets=build_buckets(AS_OF), as_of=AS_OF)
        self.assertEqual(rows, [])
        self.assertEqual(evidence[0]["disposition_reason"], "forecast_identity_unproven")

    def test_unknown_uom_is_not_guessed(self):
        forecast = self.build([window(canonical_uom="unknown")])
        rows, evidence, _ = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]),
            buckets=build_buckets(AS_OF), as_of=AS_OF)
        self.assertEqual(rows, [])
        self.assertEqual(evidence[0]["disposition_reason"], "forecast_uom_unproven")

    def test_actuals_win_over_forecast_on_same_key(self):
        forecast = self.build([window()])
        history = [dict(canonical_sku="KS0001", canonical_warehouse="W", canonical_uom="个",
                        demand_date="2026-10-30", quantity=Decimal("5"))]
        keys = overlap_keys(history, forecast.window_start, AS_OF.tzinfo)
        rows, evidence, _ = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]),
            buckets=build_buckets(AS_OF), as_of=AS_OF, skip_keys=keys)
        self.assertEqual(rows, [])
        self.assertEqual(evidence[0]["disposition_reason"], "forecast_overlap_with_actuals")

    def test_forecast_and_history_are_bucketed_separately(self):
        forecast = self.build([window()])
        buckets = build_buckets(AS_OF, protect_days=3, weeks=2)
        rows, _, _ = forecast_demand_rows(
            forecast, sku_map([("TT0000001", ["KS0001"])]), buckets=buckets, as_of=AS_OF)
        result = net_target(
            sku="KS0001", warehouse="W", uom="个", as_of=AS_OF, buckets=buckets,
            demand_rows=rows + [dict(demand_row_id="hist", demand_date="2026-10-28",
                                     quantity=Decimal("4"))],
            supply_rows=[], supply_sources_complete=True)
        protect = next(r for r in result["rows"]
                       if r["bucket_id"] == "protect" and r["scenario"] == "expected")
        self.assertEqual(protect["unknown_reason"], "no_snapshot_basis")
        demand = result["demand_sources"]["protect"]
        self.assertAlmostEqual(float(demand["forecast"]), 10.0)
        self.assertEqual(demand["demand_netting"], Decimal(4))


if __name__ == "__main__":
    unittest.main()
