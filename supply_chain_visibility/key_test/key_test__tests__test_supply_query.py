"""Contract tests for the SO report's row-scoped query service."""
import importlib.util
import sys
import types
from pathlib import Path
import unittest


class _AttrDict(dict):
    __getattr__ = dict.__getitem__


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.db = types.SimpleNamespace(sql=self.sql)
        self.queries = []
        self.permissions = {}
        self.candidates = {}
        self.so_rows = []
        self.shipped_rows = []
        self.selected_rows = []
        self.readable = {}
        self.list_calls = []
        self.PermissionError = PermissionError
        self._ = lambda value: value
        self._dict = lambda value=None: _AttrDict(value or {})

    def get_list(self, doctype, filters=None, or_filters=None, fields=None, limit_page_length=20):
        self.list_calls.append((doctype, filters, or_filters))
        return self.permissions.get(doctype, [])

    def has_permission(self, doctype, ptype):
        return self.readable.get(doctype, True)

    def throw(self, message, exc):
        raise exc(message)

    def sql(self, query, values=None, as_dict=False):
        self.queries.append((query, values))
        if "select so.name as so" in query:
            return self.so_rows
        if "select distinct dn.name as name" in query:
            if values.get("dn_from_date") == "2099-01-01":
                return []
            return list(self.candidates.get("Delivery Note", []))
        if "from `tabWork Order` w" in query:
            return list(self.candidates.get("Work Order", []))
        if "from `tabTracking Number`" in query:
            return list(self.candidates.get("Tracking Number", []))
        if "select distinct dni.so_detail" in query:
            return [types.SimpleNamespace(so_detail="SOI-1")]
        if "sum(dni.qty) as selected_dn_qty" in query:
            return self.selected_rows
        if "sum(dni.qty) as shipped" in query:
            return self.shipped_rows
        return []


class QueryServiceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved_modules = {
            name: sys.modules.get(name)
            for name in ("frappe", "frappe.utils", "key_test", "key_test.supply_query")
        }
        cls.fake_frappe = FakeFrappe()
        sys.modules["frappe"] = cls.fake_frappe
        sys.modules["frappe.utils"] = types.SimpleNamespace(getdate=lambda x: x, today=lambda: "2026-10-26")
        root = Path(__file__).parents[1]
        service_path = root / "supply_query.py"
        report_path = root / "key_test" / "report" / "so_chain_overview" / "so_chain_overview.py"
        if not service_path.exists():
            service_path = root / "key_test" / "key_test__supply_query.py"
            report_path = root / "key_test" / "key_test__report__so_chain_overview__so_chain_overview.py"
        spec = importlib.util.spec_from_file_location("key_test_u2_test_supply_query", service_path)
        cls.service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.service)
        package = types.ModuleType("key_test")
        package.__path__ = []
        sys.modules["key_test"] = package
        sys.modules["key_test.supply_query"] = cls.service
        report_spec = importlib.util.spec_from_file_location("key_test_u2_test_report", report_path)
        cls.report = importlib.util.module_from_spec(report_spec)
        report_spec.loader.exec_module(cls.report)

    @classmethod
    def tearDownClass(cls):
        for name, module in cls.saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def setUp(self):
        self.fake_frappe.queries.clear()
        self.fake_frappe.list_calls.clear()
        self.fake_frappe.permissions = {
            "Sales Order": [_AttrDict(name="SO-1")],
            "Delivery Note": [_AttrDict(name="DN-1")],
            "Work Order": [_AttrDict(name="WO-1", sales_order_item="SOI-1", fg_sales_order_item=None, production_plan_item=None)],
            "Production Plan Item": [],
            "Production Plan": [],
            "Tracking Number": [_AttrDict(name="TN-1", work_order="WO-1")],
        }
        self.fake_frappe.candidates = {
            "Delivery Note": [_AttrDict(name="DN-1")],
            "Work Order": [_AttrDict(name="WO-1", sales_order_item="SOI-1", fg_sales_order_item=None, production_plan_item=None)],
            "Tracking Number": [_AttrDict(name="TN-1", work_order="WO-1")],
        }
        self.fake_frappe.so_rows = [
            types.SimpleNamespace(so="SO-1", customer="C-1", so_status="Open", so_line="SOI-1",
                                  item_code="SKU-1", customer_item_code="C-SKU-1", delivery_date="2026-01-01",
                                  open_qty=1, qty=2, uom="个"),
            types.SimpleNamespace(so="SO-1", customer="C-1", so_status="Open", so_line="SOI-2",
                                  item_code="SKU-1", customer_item_code="C-SKU-1", delivery_date="2026-01-01",
                                  open_qty=1, qty=2, uom="套"),
        ]
        self.fake_frappe.shipped_rows = [
            types.SimpleNamespace(so_line="SOI-1", uom="个", shipped=8),
            types.SimpleNamespace(so_line="SOI-2", uom="套", shipped=5),
        ]
        self.fake_frappe.selected_rows = [
            types.SimpleNamespace(so_line="SOI-1", uom="个", selected_dn_qty=3),
        ]
        self.fake_frappe.readable = {}

    def test_filters_scope_candidate_so_rows_and_sql_values_are_bound(self):
        self.service.get_report_data({"sales_order": "SO-1", "item_code": "SKU-1", "warehouse": "WH-1"})
        query, values = self.fake_frappe.queries[0]
        self.assertIn("soi.parent in %(sales_orders)s", query)
        self.assertIn("soi.item_code = %(item_code)s", query)
        self.assertNotIn("SKU-1", query)
        self.assertEqual(values["sales_orders"], ("SO-1",))
        self.assertEqual(values["item_code"], "SKU-1")

    def test_dn_join_uses_so_detail_and_separates_selected_qty(self):
        rows, shipped, selected, _, _, _ = self.service.get_report_data({"delivery_note": "DN-1"})
        queries = "\n".join(query for query, _ in self.fake_frappe.queries)
        self.assertIn("dni.so_detail", queries)
        self.assertIn("selected_dn_qty", queries)
        self.assertNotIn("group by dni.against_sales_order, dni.item_code", queries)
        self.assertEqual([row.so_line for row in rows], ["SOI-1"])
        self.assertEqual(shipped["SOI-1"], 8)
        self.assertEqual(selected["SOI-1"], 3)

    def test_duplicate_item_lines_keep_separate_lifetime_totals(self):
        rows, shipped, _, line_wo, line_tn, _ = self.service.get_report_data({})
        self.assertEqual([row.so_line for row in rows], ["SOI-1", "SOI-2"])
        self.assertEqual(shipped, {"SOI-1": 8, "SOI-2": 5})
        self.assertEqual(line_wo["SOI-1"], ["WO-1"])
        self.assertEqual(line_tn["SOI-1"], 1)

    def test_so_date_and_customer_filters_are_named_and_permission_scoped(self):
        self.service.get_report_data({"customer": "C-1", "from_date": "2026-01-01", "to_date": "2026-01-31"})
        doctype, filters, _ = self.fake_frappe.list_calls[0]
        self.assertEqual(doctype, "Sales Order")
        self.assertIn(["customer", "=", "C-1"], filters)
        self.assertIn(["transaction_date", ">=", "2026-01-01"], filters)
        self.assertIn(["transaction_date", "<=", "2026-01-31"], filters)

    def test_warehouse_is_applied_to_selected_dn_amount(self):
        self.service.get_report_data({"dn_from_date": "2026-01-01", "warehouse": "WH-1"})
        so_query = self.fake_frappe.queries[0][0]
        so_values = self.fake_frappe.queries[0][1]
        self.assertIn("soi.warehouse = %(warehouse)s", so_query)
        self.assertEqual(so_values["warehouse"], "WH-1")

    def test_unmatched_dn_date_filter_returns_no_so_rows(self):
        rows, _, _, _, _, _ = self.service.get_report_data({"dn_from_date": "2099-01-01"})
        self.assertEqual(rows, [])
        self.assertEqual(len(self.fake_frappe.queries), 2)
        self.assertFalse(any("tabWork Order" in query for query, _ in self.fake_frappe.queries))

    def test_disallowed_so_is_not_sent_to_sql(self):
        self.fake_frappe.readable["Sales Order"] = False
        with self.assertRaises(PermissionError):
            self.service.get_report_data({"sales_order": "SO-FORBIDDEN"})
        self.assertEqual(self.fake_frappe.queries, [])

    def test_no_dn_read_permission_yields_unknown_and_blocks_dn_filters(self):
        self.fake_frappe.readable["Delivery Note"] = False
        rows, shipped, selected, _, _, _ = self.service.get_report_data({})
        self.assertTrue(rows)
        self.assertIsNone(shipped)
        self.assertIsNone(selected)
        with self.assertRaises(PermissionError):
            self.service.get_report_data({"delivery_note": "DN-1"})

    def test_row_restricted_dn_access_is_unknown_and_filter_fails_closed(self):
        self.fake_frappe.permissions["Delivery Note"] = []
        rows, shipped, _, _, _, _ = self.service.get_report_data({})
        self.assertTrue(rows)
        self.assertIsNone(shipped)
        with self.assertRaises(PermissionError):
            self.service.get_report_data({"dn_from_date": "2026-01-01"})

    def test_partial_dn_read_permission_does_not_report_subset_as_full_total(self):
        self.fake_frappe.candidates["Delivery Note"].append(_AttrDict(name="DN-2"))
        rows, shipped, _, _, _, _ = self.service.get_report_data({})
        self.assertTrue(rows)
        self.assertIsNone(shipped)
        with self.assertRaises(PermissionError):
            self.service.get_report_data({"dn_from_date": "2026-01-01"})

    def test_sales_user_without_production_permissions_gets_unknown_counts(self):
        self.fake_frappe.readable.update({
            "Work Order": False,
            "Production Plan": False,
            "Tracking Number": False,
        })
        _, _, _, line_wo, line_tn, _ = self.service.get_report_data({})
        self.assertIsNone(line_wo)
        self.assertIsNone(line_tn)

    def test_row_restricted_work_order_and_tracking_records_stay_unknown(self):
        self.fake_frappe.permissions["Work Order"] = []
        self.fake_frappe.permissions["Tracking Number"] = []
        _, _, _, line_wo, line_tn, _ = self.service.get_report_data({})
        self.assertIsNone(line_wo)
        self.assertIsNone(line_tn)

    def test_report_keeps_restricted_source_quantities_unknown(self):
        self.fake_frappe.readable.update({
            "Delivery Note": False,
            "Work Order": False,
            "Production Plan": False,
            "Tracking Number": False,
        })
        _, data, _, chart, summary = self.report.execute({"sales_order": "SO-1"})
        self.assertIsNone(data[0]["shipped"])
        self.assertIsNone(data[0]["open_qty"])
        self.assertIsNone(data[0]["selected_dn_qty"])
        self.assertIsNone(data[0]["wo_n"])
        self.assertIsNone(data[0]["tn_n"])
        self.assertIn("出库信息无权限，已发量未知", data[0]["flags"])
        self.assertEqual(summary[2]["value"], 2)
        self.assertEqual(chart["data"]["labels"], ["信息不可见", "未排产", "生产中/待发", "已发完成/Closed未发"])
        self.assertEqual(chart["data"]["datasets"][0]["values"], [2, 0, 0, 0])

    def test_kpi_totals_stay_separate_by_unit(self):
        _, _, _, _, summary = self.report.execute({"sales_order": "SO-1"})
        summary_values = {row["label"]: row["value"] for row in summary}
        self.assertEqual(summary_values["未发总量（个）"], 1)
        self.assertEqual(summary_values["未发总量（套）"], 1)
        self.assertNotIn("未发总量", summary_values)

    def test_missing_uom_does_not_present_any_quantity_as_unitful(self):
        self.fake_frappe.so_rows[0].uom = None
        _, data, _, _, summary = self.report.execute({"sales_order": "SO-1"})
        self.assertIsNone(data[0]["qty"])
        self.assertIsNone(data[0]["shipped"])
        self.assertIsNone(data[0]["open_qty"])
        self.assertIn("订单单位缺失，数量未知", data[0]["flags"])
        summary_values = {row["label"]: row["value"] for row in summary}
        self.assertEqual(summary_values["未发量未知行（权限/单位受限）"], 1)

    def test_only_overdue_kpis_use_filtered_rows(self):
        self.fake_frappe.so_rows[0].so_status = "Closed"
        self.fake_frappe.so_rows[0].delivery_date = "2026-01-01"
        self.fake_frappe.so_rows[1].so_status = "Open"
        self.fake_frappe.so_rows[1].delivery_date = "2026-01-01"
        _, data, _, chart, summary = self.report.execute({"only_overdue": 1})
        summary_values = {row["label"]: row["value"] for row in summary}
        self.assertEqual(len(data), 1)
        self.assertEqual(summary_values["行数(未发完)"], len(data))
        self.assertEqual(summary_values["交期已过(行)"], len(data))
        self.assertEqual(summary_values["死单(Closed未发)"], 0)
        self.assertEqual(sum(chart["data"]["datasets"][0]["values"]), len(data))

    def test_dn_uom_mismatch_keeps_signed_amount_unknown_without_conversion(self):
        self.fake_frappe.shipped_rows[0].uom = "套"
        _, data, _, _, summary = self.report.execute({"sales_order": "SO-1"})
        self.assertIsNone(data[0]["shipped"])
        self.assertIsNone(data[0]["open_qty"])
        self.assertIn("DN行UOM与SO行UOM不一致，已发量/未发量未知", data[0]["flags"])
        summary_values = {row["label"]: row["value"] for row in summary}
        self.assertEqual(summary_values["未发量未知行（权限/单位受限）"], 1)

    def test_selected_dn_uom_mismatch_does_not_sum_as_so_unit(self):
        self.fake_frappe.selected_rows[0].uom = "套"
        _, data, _, _, _ = self.report.execute({"sales_order": "SO-1", "delivery_note": "DN-1"})
        self.assertIsNone(data[0]["selected_dn_qty"])


if __name__ == "__main__":
    unittest.main()
