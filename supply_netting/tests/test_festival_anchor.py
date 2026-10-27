# -*- coding: utf-8 -*-
"""春节锚点（2027-02-06）穿越统计与 180 天口径接线。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from supply_netting.so_backlog import (SPRING_FESTIVAL_ANCHOR,
                                       SPRING_FESTIVAL_BUFFER_DAYS,
                                       build_so_backlog, festival_window,
                                       spring_festival_status, summarize_backlog)


def so_rows(rows):
    frame = pd.DataFrame(rows, columns=["so", "customer", "delivery_date", "item_code",
                                        "customer_item_code", "warehouse", "qty"])
    frame["status"] = "Open"
    frame["delivered_qty"] = 0
    frame["open_qty"] = frame["qty"]
    frame["stock_uom"] = "个"
    return frame


class FestivalAnchorTests(unittest.TestCase):
    def test_anchor_window_and_buffer(self):
        self.assertEqual(SPRING_FESTIVAL_ANCHOR, date(2027, 2, 6))
        self.assertEqual(SPRING_FESTIVAL_BUFFER_DAYS, 60)
        self.assertEqual(festival_window(), (date(2027, 1, 7), date(2027, 3, 8)))

    def test_late_2026_delivery_crosses_via_shipment_path(self):
        # 交付 2026-12-01：生产段 [09-02, 12-01] 不跨窗口，但发运段到 2027-03-01 跨窗口
        status, buffer_days = spring_festival_status(date(2026, 12, 1), anchor=SPRING_FESTIVAL_ANCHOR)
        self.assertEqual((status, buffer_days), ("applicable", 60))

    def test_early_2026_delivery_does_not_cross(self):
        status, buffer_days = spring_festival_status(date(2026, 6, 30), anchor=SPRING_FESTIVAL_ANCHOR)
        self.assertEqual((status, buffer_days), ("not_applicable", 0))

    def test_summary_reports_crossing_orders_lines_quantity(self):
        frame = build_so_backlog(so_rows([
            ("SO1", "DANEEY", "2026-12-01", "KS1", "TT1", "成品仓 - FZH", 5),
            ("SO2", "DANEEY", "2026-06-30", "KS2", "TT2", "成品仓 - FZH", 7),
            ("SO3", "CENTRADE", "2026-11-15", "KS3", "TT3", "半成品仓 - FZH", 10),
        ]), as_of=date(2026, 10, 27))
        summary = summarize_backlog(frame)
        festival = summary["spring_festival"]
        self.assertEqual(festival["anchor"], "2027-02-06")
        self.assertEqual(festival["buffer_days"], 60)
        self.assertEqual(festival["window"], ["2027-01-07", "2027-03-08"])
        self.assertEqual(festival["crossing_counted"]["orders"], 2)      # SO1 + SO3
        self.assertEqual(festival["crossing_counted"]["quantity"], 15.0)
        # 只看生产段时都不跨窗口（交付都在 2026-12 以前）
        self.assertEqual(festival["crossing_production_only"]["orders"], 0)
        self.assertIn("2026-12", festival["crossing_by_delivery_month"]
                      if "2026-12" in festival["crossing_by_delivery_month"] else
                      festival["crossing_by_delivery_month"])

    def test_row_buffer_written_for_crossing_rows(self):
        frame = build_so_backlog(so_rows([
            ("SO1", "DANEEY", "2026-12-01", "KS1", "TT1", "成品仓 - FZH", 5),
        ]), as_of=date(2026, 10, 27), festival_anchor=SPRING_FESTIVAL_ANCHOR)
        row = frame.iloc[0]
        self.assertEqual(row["spring_festival_buffer_days"], 60)
        self.assertEqual(row["spring_festival_applicability"], "applicable")
        self.assertEqual(summarize_backlog(frame)["spring_festival_applied_quantity"], 5.0)


class LeadDaysWiringTests(unittest.TestCase):
    def _fixture(self, tmp: Path, lead_rows):
        run = tmp / "run"
        run.mkdir()
        pd.DataFrame([dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
                           protect_demand=1.0, protect_gap=1.0, horizon_unserved=1.0,
                           needs_review="", opening=0.0, opening_lower_bound=0.0,
                           status="conditional", unknown_reason=None,
                           conditional_supply_qty=0.0, forecast_demand_qty=1.0,
                           historical_demand_qty=0.0)]).to_parquet(
            run / "replenishment_review.parquet", index=False)
        pd.DataFrame([dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
                           scenario="expected", bucket_id="protect", period_demand=1.0,
                           receipts=0.0, unserved=1.0, gap=1.0, opening=0.0,
                           opening_lower_bound=0.0, conditional_receipts=0.0,
                           status="conditional", unknown_reason=None)]).to_parquet(
            run / "supply_netting.parquet", index=False)
        pd.DataFrame(columns=["disposition_reason", "source_layer", "canonical_sku",
                              "canonical_warehouse", "canonical_uom", "qty"]).to_parquet(
            run / "supply_facts.parquet", index=False)
        forecast = tmp / "forecast"
        fx = forecast / "fx"
        fx.mkdir(parents=True)
        (forecast / "CURRENT").write_text("fx", encoding="utf-8")
        pd.DataFrame(lead_rows).to_parquet(fx / "forecast_sku_warehouse_windows.parquet",
                                           index=False)
        (fx / "forecast_manifest.json").write_text(json.dumps({
            "schema_version": "en-demand-forecast-v1", "run_id": "fx",
            "run": {"decision_date": "2026-10-29", "data_cutoff": "2026-10-26"},
            "code": {"git_head": "x"},
            "outputs": [{"file": "forecast_sku_warehouse_windows.parquet",
                         "rows": len(lead_rows), "sha256": _sha(
                             fx / "forecast_sku_warehouse_windows.parquet")}],
        }), encoding="utf-8")
        outputs = {f"{name}_sha256": _sha(run / f"{name}.parquet")
                   for name in ("supply_netting", "replenishment_review", "supply_facts")}
        doc = dict(run_id="run", as_of="2026-10-26T05:17:34+08:00",
                   buckets=[dict(bucket_id="protect", start="2026-10-26T05:17:34+08:00",
                                 end="2026-11-02T05:17:34+08:00")],
                   forecast=dict(run_id="fx", lead_days=180, window_start="2026-10-29",
                                 window_end="2027-04-27",
                                 manifest_sha256=_sha(fx / "forecast_manifest.json"),
                                 windows_sha256=_sha(fx / "forecast_sku_warehouse_windows.parquet")),
                   inputs=dict(demand_netting=dict(date_max="2026-10-26", sha256="h" * 64)),
                   outputs=outputs, partial=True, partial_reasons=[], checks={})
        (run / "supply_netting_manifest.json").write_text(json.dumps(doc), encoding="utf-8")
        history = tmp / "demand.parquet"
        pd.DataFrame([dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
                           demand_date="2026-10-20", quantity_default=1.0,
                           in_default_series=True)]).to_parquet(history, index=False)
        return run, forecast, history

    def test_cli_accepts_lead_days(self):
        from supply_netting.decision_pack import build_parser
        args = build_parser().parse_args(["--run", "r", "--demand", "d", "--out", "o",
                                          "--forecast-lead-days", "180"])
        self.assertEqual(args.forecast_lead_days, 180)

    def test_load_inputs_filters_by_lead_days(self):
        from supply_netting.decision_pack import load_inputs
        rows = [dict(tongtool_sku="TT1", canonical_warehouse="W", canonical_uom="个",
                     lead_days=lead, netting_eligible=True, netting_block_reason=None,
                     window_start="2026-10-29", window_end="2027-04-27", p50=1.0)
                for lead in (60, 180)]
        with tempfile.TemporaryDirectory() as tmp:
            run, forecast, history = self._fixture(Path(tmp), rows)
            # 让历史哈希匹配 r5 声明
            import hashlib
            doc = json.loads((run / "supply_netting_manifest.json").read_text(encoding="utf-8"))
            doc["inputs"]["demand_netting"]["sha256"] = hashlib.sha256(
                history.read_bytes()).hexdigest()
            (run / "supply_netting_manifest.json").write_text(json.dumps(doc), encoding="utf-8")
            inputs = load_inputs(run, forecast_root=forecast, demand_netting=history,
                                 forecast_lead_days=180, expected_sku_map_sha256=None)
            self.assertEqual(sorted(inputs.forecast_windows["lead_days"].unique()), [180])
            inputs60 = load_inputs(run, forecast_root=forecast, demand_netting=history,
                                   forecast_lead_days=60, expected_sku_map_sha256=None)
            self.assertEqual(sorted(inputs60.forecast_windows["lead_days"].unique()), [60])


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
