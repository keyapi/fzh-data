"""Permission, scope, and source-coverage contracts for supply timeline."""
import importlib.util
import json
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


class _Row(dict):
    __getattr__ = dict.__getitem__


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.db = types.SimpleNamespace(exists=lambda doctype, name=None: name in self.existing if doctype == "DocType" else False)
        self.existing = {"Tongtool Stock Latest", "Tongtool Stock Run", "Item", "Warehouse"}
        self.queries = []
        self.calls = []
        self.permissions = {}
        self.allowed = True
        self.system_manager = True
        self.stock_snapshot_dir = None
        self._ = lambda text: text
        self._dict = lambda value=None: dict(value or {})
        self.session = types.SimpleNamespace(user="administrator@example.com")
        self.utils = types.SimpleNamespace(today=lambda: "2026-10-26")
        self.utils.now_datetime = lambda: "2026-10-26 06:00:00"

    def has_permission(self, doctype, ptype="read"):
        self.calls.append(("has_permission", doctype, ptype))
        return self.allowed

    def get_roles(self):
        self.calls.append(("get_roles",))
        return ["System Manager"] if self.system_manager else ["Stock User"]

    def get_list(self, doctype, filters=None, fields=None, order_by=None, limit_page_length=20):
        self.calls.append((doctype, filters, fields, order_by, limit_page_length))
        if doctype == "Tongtool Stock Latest" and filters and "run_id" in filters:
            return self.permissions.get("Tongtool Stock Latest:run_count", [])
        key = (doctype, repr(filters))
        rows = self.permissions.get(key, self.permissions.get(doctype, []))
        if filters:
            for field, condition in filters.items():
                if isinstance(condition, (list, tuple)) and len(condition) == 2 and condition[0] == "in":
                    rows = [row for row in rows if row.get(field) in condition[1]]
                elif isinstance(condition, str):
                    rows = [row for row in rows if row.get(field) == condition]
        return rows

    def get_single(self, doctype):
        return types.SimpleNamespace(stock_snapshot_dir=self.stock_snapshot_dir)


class FakeDuckDB:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def connect(self, *args, **kwargs):
        return self

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class SupplyTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._missing = object()
        cls._previous_modules = {
            name: sys.modules.get(name, cls._missing)
            for name in ("frappe", "key_test.supply_timeline_query", "duckdb")
        }
        cls.fake = FakeFrappe()
        sys.modules["frappe"] = cls.fake
        base = Path(__file__).parents[1]
        path = base / "supply_timeline_query.py"
        mirror_base = base / "key_test" if (base / "key_test").is_dir() else base
        if not path.exists():
            path = mirror_base / "key_test__supply_timeline_query.py"
        spec = importlib.util.spec_from_file_location("key_test.supply_timeline_query", path)
        cls.service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.service)
        sys.modules["key_test.supply_timeline_query"] = cls.service
        report_path = base / "key_test" / "report" / "supply_timeline" / "supply_timeline.py"
        if not report_path.exists():
            report_path = mirror_base / "key_test__report__supply_timeline__supply_timeline.py"
        report_spec = importlib.util.spec_from_file_location("key_test.supply_timeline_report", report_path)
        cls.report = importlib.util.module_from_spec(report_spec)
        report_spec.loader.exec_module(cls.report)
        config_path = path.parent / "config" / "supply_timeline_skus.json"
        if not config_path.exists():
            config_path = mirror_base / "key_test__config__supply_timeline_skus.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        cls.slots = config["slots"]
        cls.skus = [slot["sku"] for slot in cls.slots]

    @classmethod
    def tearDownClass(cls):
        for name, module in cls._previous_modules.items():
            if module is cls._missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def setUp(self):
        self._previous_duckdb = sys.modules.get("duckdb", self.__class__._missing)
        self.fake.calls.clear()
        self.fake.queries.clear()
        self.fake.existing = {"Tongtool Stock Latest", "Tongtool Stock Run"}
        self.fake.allowed = True
        self.fake.system_manager = True
        self.fake.stock_snapshot_dir = None
        self.fake.permissions = {}

    def _latest_rows(self):
        return [_Row(
            name="LATEST-%02d" % index, sku=self.skus[0], warehouse="美东-CENTRADE" if index == 1 else "TT-WH-%02d" % index,
            warehouse_id="WID-%02d" % index, available=index, intransit=index + 10,
            waiting_shipment=0, defects=0, snapshot_at="2026-10-26 05:25:00",
            run_id="RUN-1",
        ) for index in range(1, 15)]

    def _configure_complete_latest(self):
        self.fake.permissions["Tongtool Stock Latest"] = self._latest_rows()
        self.fake.permissions["Tongtool Stock Run"] = [_Row(
            name="RUN-1", run_id="RUN-1", snapshot_date="2026-10-26",
            started_at="2026-10-26 05:17:00", finished_at="2026-10-26 05:31:00",
            status="Success", complete=1, warehouse_count=14, row_count=14,
            source="tongtool",
        )]
        self.fake.permissions["Tongtool Stock Latest:run_count"] = [
            _Row(name="LATEST-%02d" % index, warehouse="美东-CENTRADE" if index == 1 else "TT-WH-%02d" % index)
            for index in range(1, 15)
        ]

    def tearDown(self):
        if self._previous_duckdb is self.__class__._missing:
            sys.modules.pop("duckdb", None)
        else:
            sys.modules["duckdb"] = self._previous_duckdb

    def test_default_scope_is_nine_configured_skus_and_latest_get_list_is_permission_scoped(self):
        self._configure_complete_latest()
        rows, message = self.service.get_report_data({})
        self.assertEqual(len(self.skus), 9)
        self.assertTrue(any(call[0] == "Tongtool Stock Latest" for call in self.fake.calls))
        latest_call = next(call for call in self.fake.calls if call[0] == "Tongtool Stock Latest")
        self.assertEqual(latest_call[2], self.service.LATEST_FIELDS)
        self.assertNotIn("avg_cost", latest_call[2])
        self.assertEqual(latest_call[1]["sku"], ["in", self.skus])
        self.assertIn(("get_roles",), self.fake.calls)
        self.assertEqual(
            {row["warehouse"] for row in rows if row["stage"] == "on_hand"},
            {"美东-CENTRADE", *{f"TT-WH-{index:02d}" for index in range(2, 15)}},
        )
        self.assertFalse(any(call[0] in {"Item", "Warehouse"} for call in self.fake.calls))
        self.assertIn("完整可承诺供给", message)
        self.assertEqual({row["sku"] for row in rows}, set(self.skus))

    def test_sample_tongtool_sku_is_not_treated_as_erpnext_item_or_warehouse(self):
        self._configure_complete_latest()
        self.assertNotEqual(self.slots[0]["sku"], self.slots[0]["items"][0]["item_code"])
        rows, _ = self.service.get_report_data({"sku": self.slots[0]["sku"], "warehouse_name": "美东-CENTRADE"})
        latest_call = next(call for call in self.fake.calls if call[0] == "Tongtool Stock Latest")
        self.assertEqual(latest_call[1]["warehouse"], "美东-CENTRADE")
        self.assertTrue(rows)
        self.assertFalse(any(call[0] in {"Item", "Warehouse"} for call in self.fake.calls))

    def test_on_hand_and_intransit_are_separate_and_unknown_is_not_zero(self):
        self._configure_complete_latest()
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        by_stage = {row["stage"]: row for row in rows}
        self.assertIsNone(by_stage["on_hand"]["qty"])
        self.assertEqual(by_stage["on_hand"]["evidence_qty"], 1)
        self.assertEqual(by_stage["on_hand"]["date_confidence"], "confirmed")
        self.assertEqual(by_stage["on_hand"]["snapshot_confidence"], "run_verified")
        self.assertFalse(by_stage["on_hand"]["counted"])
        self.assertIsNone(by_stage["shipped_in_transit"]["qty"])
        self.assertEqual(by_stage["shipped_in_transit"]["evidence_qty"], 11)
        self.assertEqual(by_stage["shipped_in_transit"]["date_confidence"], "unknown")
        self.assertIsNone(by_stage["shipped_in_transit"]["available_date"])
        self.assertEqual(by_stage["shipped_in_transit"]["source_bucket"], "stock_intransit")
        self.assertEqual(by_stage["shipped_in_transit"]["ledger"], "stock_intransit")
        self.assertEqual(by_stage["shipped_in_transit"]["overlap_status"], "unproven")
        self.assertEqual(by_stage["shipped_in_transit"]["source_coverage"], "intransit_field_only")
        self.assertFalse(by_stage["shipped_in_transit"]["counted"])
        self.assertEqual(by_stage["on_hand"]["run_started_at"], "2026-10-26 05:17:00")
        self.assertEqual(by_stage["on_hand"]["run_finished_at"], "2026-10-26 05:31:00")
        self.assertEqual(by_stage["on_hand"]["snapshot_at"], "2026-10-26 05:25:00")
        self.assertEqual(by_stage["on_hand"]["query_as_of"], "2026-10-26 06:00:00")
        self.assertIsNone(by_stage["unknown"]["qty"])
        self.assertIsNone(by_stage["unknown"]["evidence_qty"])
        self.assertEqual(by_stage["unknown"]["source_coverage"], "not_connected")
        self.assertNotEqual(by_stage["on_hand"]["source_key"], by_stage["shipped_in_transit"]["source_key"])

    def test_partial_run_is_unknown_and_keeps_quantity_as_evidence(self):
        self._configure_complete_latest()
        self.fake.permissions["Tongtool Stock Run"][0]["complete"] = 0
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        incomplete = [row for row in rows if row["source_coverage"] == "incomplete_run"]
        self.assertTrue(incomplete)
        self.assertTrue(all(row["stage"] == "unknown" for row in rows))
        self.assertEqual({row["qty"] for row in incomplete}, {None})
        self.assertEqual({row["evidence_qty"] for row in incomplete}, {1, 11})

    def test_subset_or_row_count_mismatch_run_is_unknown(self):
        self._configure_complete_latest()
        self.fake.permissions["Tongtool Stock Run"][0]["warehouse_count"] = 4
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        self.assertTrue(rows)
        self.assertTrue(all(row["stage"] == "unknown" for row in rows))
        self.assertEqual(rows[0]["date_confidence"], "unknown")

    def test_snapshot_run_date_mismatch_is_stale_unknown(self):
        self._configure_complete_latest()
        self.fake.permissions["Tongtool Stock Latest"][0]["snapshot_at"] = "2026-10-20 05:25:00"
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        stale = [row for row in rows if row["source_coverage"] == "stale_snapshot"]
        self.assertTrue(stale)
        self.assertTrue(all(row["stage"] == "unknown" for row in rows))

    def test_latest_row_without_snapshot_timestamp_is_unknown(self):
        self._configure_complete_latest()
        self.fake.permissions["Tongtool Stock Latest"][0]["snapshot_at"] = None
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        unknown = [row for row in rows if row["source_coverage"] == "unknown_snapshot_date"]
        self.assertEqual(len(unknown), 2)
        self.assertTrue(all(row["qty"] is None for row in unknown))
        self.assertEqual({row["evidence_qty"] for row in unknown}, {1, 11})

    def test_missing_sku_warehouse_pair_is_unknown_when_another_sku_has_that_warehouse(self):
        self._configure_complete_latest()
        rows = self._latest_rows()
        # SKU 1 has only the first warehouse; SKU 2 carries the other 13.
        sku2_rows = [_Row(**dict(row, name="SKU2-" + row.name, sku=self.skus[1])) for row in rows[1:]]
        self.fake.permissions["Tongtool Stock Latest"] = [rows[0], *sku2_rows]
        self.fake.permissions["Tongtool Stock Run"][0]["row_count"] = 14
        self.fake.permissions["Tongtool Stock Latest:run_count"] = [
            _Row(name=f"R-{index}", warehouse=row.warehouse)
            for index, row in enumerate([rows[0], *sku2_rows])
        ]
        result, _ = self.service.get_report_data({"sku": f"{self.skus[0]},{self.skus[1]}"})
        absent = [row for row in result if row["sku"] == self.skus[0] and row["warehouse"] == "TT-WH-02"]
        self.assertEqual(len(absent), 1)
        self.assertEqual(absent[0]["stage"], "unknown")
        self.assertEqual(absent[0]["source_coverage"], "not_reported")
        self.assertIsNone(absent[0]["qty"])

    def test_unknown_uom_never_borrows_erpnext_item_uom_or_sums_rows(self):
        self._configure_complete_latest()
        rows = self._latest_rows()
        second_sku_rows = [_Row(**dict(row, name="ALT-" + row.name, sku=self.skus[1])) for row in rows]
        self.fake.permissions["Tongtool Stock Latest"] = rows + second_sku_rows
        self.fake.permissions["Tongtool Stock Run"][0]["row_count"] = 28
        self.fake.permissions["Tongtool Stock Latest:run_count"] = [_Row(name=f"L-{index}") for index in range(28)]
        rows, _ = self.service.get_report_data({})
        on_hand = [row for row in rows if row["stage"] == "on_hand"]
        self.assertEqual(len(on_hand), 28)
        self.assertTrue(all(row["uom"] is None for row in on_hand))
        self.assertTrue(all(row["uom_confidence"] == "unknown" for row in on_hand))
        self.assertEqual(len({(row["sku"], row["warehouse"], row["batch"]) for row in on_hand}), 28)

    def test_scope_over_nine_and_unlisted_skus_is_rejected(self):
        with self.assertRaises(self.service.TimelineScopeError):
            self.service.get_report_data({"sku": ",".join(self.skus + ["SKU-10"])})
        with self.assertRaises(self.service.TimelineScopeError):
            self.service.get_report_data({"sku": "SKU-UNAUTHORIZED"})

    def test_empty_source_returns_message_without_inventing_rows(self):
        self.fake.existing.discard("Tongtool Stock Latest")
        rows, message = self.service.get_report_data({})
        self.assertEqual(rows, [])
        self.assertIn("不可用", message)

    def test_empty_latest_table_returns_explicit_unreported_rows(self):
        self.fake.permissions["Tongtool Stock Latest"] = []
        rows, message = self.service.get_report_data({})
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row["stage"] == "unknown" for row in rows))
        self.assertTrue(all(row["source_coverage"] == "not_reported" for row in rows))
        self.assertIn("已标记为未上报", message)

    def test_script_report_exposes_provenance_and_caution_message(self):
        self._configure_complete_latest()
        columns, rows, message, chart, summary = self.report.execute({"sku": self.skus[0]})
        fields = {column["fieldname"] for column in columns}
        self.assertTrue({"batch", "source_key", "qty", "evidence_qty", "date_confidence", "snapshot_confidence", "available_date", "source_coverage", "source_bucket", "overlap_status", "counted", "uom", "uom_confidence", "run_started_at", "run_finished_at", "snapshot_at", "query_as_of"} <= fields)
        self.assertNotIn("avg_cost", fields)
        self.assertEqual(next(column for column in columns if column["fieldname"] == "sku")["fieldtype"], "Data")
        self.assertEqual(next(column for column in columns if column["fieldname"] == "warehouse")["fieldtype"], "Data")
        report_json_path = Path(__file__).parents[1] / "key_test" / "report" / "supply_timeline" / "supply_timeline.json"
        if not report_json_path.exists():
            report_json_path = Path(__file__).parents[1] / "key_test" / "key_test__report__supply_timeline__supply_timeline.json"
        self.assertEqual(json.loads(report_json_path.read_text(encoding="utf-8"))["roles"], [{"role": "System Manager"}])
        self.assertTrue(rows)
        self.assertIn("接通并核验这些来源后才能计算完整可承诺供给", message)
        self.assertIsNone(chart)

    def test_script_report_exposes_layer_fields(self):
        self._configure_complete_latest()
        columns, rows, message, chart, summary = self.report.execute({"sku": self.skus[0]})
        fields = {column["fieldname"] for column in columns}
        self.assertTrue({
            "source_layer", "qty_status", "uom_proven", "timezone_status",
            "identity_confidence", "b_min_eligible", "b_max_eligible", "exclusion_reason",
        } <= fields)
        self.assertTrue(rows)
        self.assertTrue(all(row["source_layer"] in ("inventory_snapshot", "uncovered_chain") for row in rows))
        self.assertTrue(any(row["source_layer"] == "uncovered_chain" for row in rows))
        self.assertTrue(all(row["uom_proven"] is False for row in rows))
        self.assertTrue(all(row["b_min_eligible"] is False for row in rows))
        self.assertTrue(all(row["b_max_eligible"] is False for row in rows))
        self.assertTrue(all(row["timezone_status"] == "unverified" for row in rows))
        self.assertIsNone(chart)

    def test_history_checks_permission_and_uses_bound_filters(self):
        self.fake.stock_snapshot_dir = "C:/stock"
        duck = FakeDuckDB([
            ("2026-10-20", "2026-10-20 05:30:00", "美东-CENTRADE", "WID-01", self.skus[0], 12, 3, "Tongtool", "RUN-OLD")
        ])
        sys.modules["duckdb"] = duck
        with patch("pathlib.Path.is_file", return_value=True):
            rows, _ = self.service.get_report_data({"snapshot_date": "2026-10-20", "sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        self.assertTrue(any(call[0] == "has_permission" for call in self.fake.calls))
        query, params = duck.queries[0]
        self.assertIn("read_parquet(?)", query)
        self.assertNotIn(self.skus[0], query)
        self.assertIn(self.skus[0], params)
        self.assertNotIn("avg_cost", query)
        self.assertTrue(rows)
        self.assertEqual({row["stage"] for row in rows}, {"unknown"})
        evidence = [row for row in rows if row["source_coverage"] == "historical_evidence_only"]
        self.assertTrue(all(row["source_coverage"] == "historical_evidence_only" for row in evidence))
        self.assertEqual({row["qty"] for row in evidence}, {None})
        self.assertEqual({row["evidence_qty"] for row in evidence}, {12, 3})
        self.assertTrue(all(row["stage"] == "unknown" for row in evidence))
        self.assertTrue(all(row["date_confidence"] == "unknown" for row in evidence))
        self.assertTrue(all(row["snapshot_confidence"] == "evidence_only" for row in evidence))
        self.assertFalse(any(call[0] in {"Item", "Warehouse"} for call in self.fake.calls))

    def test_history_refuses_when_explicit_permission_is_missing(self):
        self.fake.allowed = False
        self.fake.stock_snapshot_dir = "C:/stock"
        rows, message = self.service.get_report_data({"snapshot_date": "2026-10-20"})
        self.assertEqual(rows, [])
        self.assertIn("权限", message)

    def test_non_system_manager_cannot_use_parquet_or_unverified_latest_fields(self):
        self.fake.system_manager = False
        self.fake.stock_snapshot_dir = "C:/stock"
        rows, message = self.service.get_report_data({"snapshot_date": "2026-10-20"})
        self.assertEqual(rows, [])
        self.assertIn("System Manager", message)

    def test_missing_sample_sku_produces_unknown_not_an_empty_result(self):
        self._configure_complete_latest()
        rows, _ = self.service.get_report_data({"sku": self.skus[1], "warehouse_name": "美东-CENTRADE"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "unknown")
        self.assertIsNone(rows[0]["qty"])
        self.assertEqual(rows[0]["source_coverage"], "not_reported")

    def test_complete_snapshot_from_a_past_date_is_stale_unknown(self):
        self._configure_complete_latest()
        self.fake.permissions["Tongtool Stock Run"][0]["snapshot_date"] = "2026-10-25"
        self.fake.permissions["Tongtool Stock Latest"][0]["snapshot_at"] = "2026-10-25 05:25:00"
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        stale = [row for row in rows if row["source_coverage"] == "stale_snapshot"]
        self.assertEqual(len(stale), 2)
        self.assertTrue(all(row["qty"] is None for row in stale))
        self.assertEqual({row["evidence_qty"] for row in stale}, {1, 11})

    def test_future_snapshot_date_is_unknown(self):
        self._configure_complete_latest()
        self.fake.utils.today = lambda: "2026-10-26"
        self.fake.permissions["Tongtool Stock Run"][0]["snapshot_date"] = "2026-10-27"
        self.fake.permissions["Tongtool Stock Latest"][0]["snapshot_at"] = "2026-10-27 05:25:00"
        future, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        rows = [row for row in future if row["source_coverage"] == "future_snapshot"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["stage"] == "unknown" and row["qty"] is None for row in rows))

    def test_sc14_date_confidence_values_are_not_reused_for_snapshot_confidence(self):
        self._configure_complete_latest()
        rows, _ = self.service.get_report_data({"sku": self.skus[0], "warehouse_name": "美东-CENTRADE"})
        self.assertTrue({row["date_confidence"] for row in rows} <= {"confirmed", "estimated", "unknown"})
        self.assertIn("run_verified", {row["snapshot_confidence"] for row in rows})

    def test_unknown_source_keys_include_sku_warehouse_and_batch(self):
        self._configure_complete_latest()
        rows, _ = self.service.get_report_data({})
        keys = [row["source_key"] for row in rows if row["source_coverage"] == "not_connected"]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(self.skus[0], keys[0])
        self.assertIn("美东-CENTRADE", keys[0])
        self.assertIn("RUN-1", keys[0])


if __name__ == "__main__":
    unittest.main()
