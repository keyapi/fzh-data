# -*- coding: utf-8 -*-
"""End-to-end contract tests for get_so_chain (adapter -> evidence -> stages).

These tests exercise the whitelisted entry point, not helper functions.
"""
import importlib.util
import datetime
import json
import shutil
import subprocess
import sys
import types
import unittest
from pathlib import Path


class AttrDict(dict):
    __getattr__ = dict.__getitem__


def _d(**kwargs):
    return AttrDict(kwargs)


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.PermissionError = PermissionError
        self.ValidationError = ValueError
        self.whitelist = lambda *a, **k: (lambda fn: fn)
        self._dict = lambda value=None: AttrDict(value or {})
        self.db = types.SimpleNamespace(
            sql=self.sql, has_column=lambda *a, **k: True,
            table_exists=lambda *a, **k: True)
        self.reset()

    def reset(self):
        self.so = types.SimpleNamespace(
            name="SO-1", docstatus=1, status="To Deliver and Bill",
            customer="C1", customer_name="客户", amended_from=None,
            items=[types.SimpleNamespace(
                name="SOI-1", item_code="KS0001", item_name="成品",
                customer_item_code="C-1", qty=10.0, delivered_qty=0.0,
                uom="个", delivery_date="2026-10-30")])
        self.wo_rows = []
        self.pp_rows = []
        self.pp_item_rows = []
        self.item_rows = []
        self.op_rows = []
        self.jc_rows = []
        self.jc_time_log_rows = []
        self.tn_rows = []
        self.se_rows = []
        self.se_detail_rows = []
        self.qi_rows = []
        self.dn_rows = []
        self.readable = {}
        self.permitted = {}
        self.wo_queries = []
        self.fail_queries = set()

    # -- frappe API ---------------------------------------------------------
    def get_doc(self, doctype, name):
        return self.so

    def has_permission(self, doctype, ptype, doc=None):
        return self.readable.get(doctype, True)

    def throw(self, message, exc=None):
        raise (exc or Exception)(message)

    def get_list(self, doctype, filters=None, or_filters=None, fields=None,
                 limit_page_length=20):
        rows = self._rows_for(doctype)
        names = [r.get("name") for r in rows if r.get("name")]
        allowed = self.permitted.get(doctype)
        if allowed is not None:
            names = [n for n in names if n in set(allowed)]
        return [_d(name=n) for n in names]

    def get_all(self, doctype, filters=None, fields=None, order_by=None):
        rows = list(self._rows_for(doctype))
        filters = filters or {}
        for key, value in filters.items():
            if isinstance(value, (list, tuple)) and len(value) == 2:
                op, target = value
                if op == "in":
                    rows = [r for r in rows if r.get(key) in set(target)]
                elif op == "<":
                    rows = [r for r in rows if (r.get(key) or 0) < target]
                elif op == "=":
                    rows = [r for r in rows if r.get(key) == target]
            else:
                rows = [r for r in rows if r.get(key) == value]
        return [_d(**dict(r)) for r in rows]

    def _rows_for(self, doctype):
        return {
            "Work Order": self.wo_rows,
            "Production Plan Item": self.pp_item_rows,
            "Item": self.item_rows,
            "Operation": self.op_rows,
            "Work Order Operation": self.op_rows,
            "Job Card": self.jc_rows,
            "Job Card Time Log": self.jc_time_log_rows,
            "Tracking Number": self.tn_rows,
            "Stock Entry": self.se_rows,
            "Stock Entry Detail": self.se_detail_rows,
            "Quality Inspection": self.qi_rows,
            "Delivery Note Item": self.dn_rows,
            "Sales Order": [{"name": "SO-1"}],
        }.get(doctype, [])

    def sql(self, query, values=None, as_dict=False):
        values = values or {}
        for needle in self.fail_queries:
            if needle in query:
                raise RuntimeError("boom: %s" % needle)
        if "from `tabWork Order` w" in query:
            self.wo_queries.append(query)
            line = values.get("line")
            rows = [r for r in self.wo_rows
                    if r.get("sales_order_item") == line
                    or r.get("fg_sales_order_item") == line]
            return [_d(**dict(r)) for r in rows]
        if "from `tabProduction Plan Item` ppi" in query:
            return [_d(**dict(r)) for r in self.pp_rows]
        if "from `tabStock Entry`" in query:
            wos = set(values.get("wos") or ())
            return [_d(**dict(r)) for r in self.se_rows if r.get("work_order") in wos]
        if "from `tabQuality Inspection`" in query:
            names = set(values.get("names") or ())
            return [_d(**dict(r)) for r in self.qi_rows
                    if r.get("reference_name") in names]
        if "from `tabDelivery Note Item` dni" in query:
            return [_d(**dict(r)) for r in self.dn_rows]
        return []


# -- record builders --------------------------------------------------------
def wo(name, item="KS0001", qty=10.0, uom="个", docstatus=1, ppi=None,
       so_line="SOI-1", fg_line=None):
    return {
        "name": name, "qty": qty, "status": "In Process", "docstatus": docstatus,
        "produced_qty": 0.0, "production_item": item, "stock_uom": uom,
        "production_plan_item": ppi, "sales_order_item": so_line,
        "fg_sales_order_item": fg_line,
    }


def op(wo_name, operation, seq, name=None):
    return {"name": name or "%s-OP%d" % (wo_name, seq), "parent": wo_name,
            "operation": operation, "sequence_id": seq, "status": "Completed",
            "completed_qty": 0.0}


def jc(wo_name, routing_name, operation, tn="", qty=10.0, docstatus=1,
       status="Completed", start="2026-10-20 08:00:00", end="2026-10-20 17:00:00"):
    return {
        "name": "JC-%s-%s-%s" % (wo_name, operation, tn or "batch"),
        "work_order": wo_name, "operation_id": routing_name,
        "operation": operation, "status": status, "docstatus": docstatus,
        "total_completed_qty": qty, "for_quantity": qty,
        "actual_start_date": start,
        "actual_end_date": end,
        "tracking_number": tn,
    }


def tn(name, wo_name, qty=10.0):
    return {"name": name, "work_order": wo_name, "qty": qty,
            "initial_work_order": None, "so_materials": None,
            "finished_product_work_order": None}


def se(name, wo_name, item="KS0001", qty=10.0, uom="个", docstatus=1):
    return {"name": name, "work_order": wo_name, "docstatus": docstatus,
            "is_return": 0, "posting_date": "2026-10-21", "posting_time": "09:00:00",
            "outgoing_stock_entry": None}


def se_detail(name, parent, item="KS0001", qty=10.0, uom="个"):
    return {"name": name, "parent": parent, "is_finished_item": 1,
            "item_code": item, "qty": qty, "uom": uom, "stock_uom": uom,
            "t_warehouse": "WH", "batch_no": None, "stock_tracking_number": None,
            "against_stock_entry": None}


def qi(name, ref_name, item="KS0001", status="Accepted"):
    return {"name": name, "docstatus": 1, "status": status,
            "reference_type": "Job Card", "reference_name": ref_name,
            "item_code": item, "sample_size": 1, "stock_tracking_number": None,
            "report_date": "2026-10-21"}


class SoChainEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = {name: sys.modules.get(name) for name in (
            "frappe", "frappe.utils", "key_test", "key_test.supply_query",
            "key_test.production_evidence", "key_test.supply_facts",
            "key_test.so_chain")}
        cls.fake = FakeFrappe()
        sys.modules["frappe"] = cls.fake
        sys.modules["frappe.utils"] = types.SimpleNamespace(
            getdate=lambda x: (x if isinstance(x, datetime.date)
                               else datetime.date.fromisoformat(str(x)[:10])),
            today=lambda: datetime.date(2026, 10, 29),
            now_datetime=lambda: "2026-10-29 10:00:00")
        root = Path(__file__).parents[1]
        package = types.ModuleType("key_test")
        package.__path__ = []
        sys.modules["key_test"] = package
        specs = (
            ("key_test_u7_test_supply_query", "key_test.supply_query",
             root / "supply_query.py", root / "key_test" / "key_test__supply_query.py"),
            ("key_test.production_evidence", "key_test.production_evidence",
             root / "production_evidence.py", root / "key_test" / "key_test__production_evidence.py"),
            ("key_test.supply_facts", "key_test.supply_facts",
             root / "supply_facts.py", root / "key_test" / "key_test__supply_facts.py"),
            ("key_test_u7_test_so_chain", "key_test.so_chain",
             root / "so_chain.py", root / "key_test" / "key_test__so_chain.py"),
        )
        cls.modules = {}
        for modname, alias, primary, mirror in specs:
            path = primary if primary.exists() else mirror
            spec = importlib.util.spec_from_file_location(modname, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[alias] = module
            cls.modules[alias] = module
        cls.chain = cls.modules["key_test.so_chain"]

    @classmethod
    def tearDownClass(cls):
        for name, module in cls.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def setUp(self):
        self.fake.reset()

    # -- helpers ------------------------------------------------------------
    def full_chain(self, wo_name="WO-1", item="KS0001", qty=10.0, uom="个",
                   tn_name="T1", end="2026-10-20 17:00:00", with_qc=True,
                   docstatus=1, with_stock=True, so_line="SOI-1", fg_line=None,
                   ppi=None, time_logs=False):
        self.fake.wo_rows.append(wo(wo_name, item, qty, uom, docstatus=docstatus,
                                    ppi=ppi, so_line=so_line, fg_line=fg_line))
        ops = [("裁剪", 1), ("缝制", 2)] + ([("质检", 3)] if with_qc else [])
        names = []
        for operation, seq in ops:
            row = op(wo_name, operation, seq)
            self.fake.op_rows.append(row)
            names.append(row)
        self.fake.tn_rows.append(tn(tn_name, wo_name, qty))
        jc_start = None if time_logs else "2026-10-20 08:00:00"
        jc_end = None if time_logs else end
        for row in names:
            self.fake.jc_rows.append(jc(wo_name, row["name"], row["operation"],
                                        tn_name, qty, start=jc_start, end=jc_end))
            if time_logs:
                self.fake.jc_time_log_rows.append({
                    "parent": "JC-%s-%s-%s" % (wo_name, row["operation"], tn_name),
                    "from_time": "2026-10-20 08:00:00", "to_time": end})
        if with_stock:
            se_name = "SE-" + wo_name
            self.fake.se_rows.append(se(se_name, wo_name, item, qty, uom))
            self.fake.se_detail_rows.append(se_detail("SED-" + wo_name, se_name,
                                                      item, qty, uom))
        if with_qc:
            ref = "JC-%s-%s-%s" % (wo_name, ops[0][0], tn_name)
            self.fake.qi_rows.append(qi("QI-" + wo_name, ref, item))
        return "JC-%s-%s-%s" % (wo_name, ops[0][0], tn_name)

    def line(self, result, idx=0):
        return result["lines"][idx]

    # -- P0-1 ---------------------------------------------------------------
    def test_real_chain_reads_stock_entries_and_selects_stock_uom(self):
        self.full_chain()
        result = self.chain.get_so_chain("SO-1")
        line = self.line(result)
        self.assertEqual(line["reported"], 10.0)
        self.assertEqual(line["instock"], 10.0)
        self.assertEqual(line["reported_status"], "known")
        self.assertEqual(line["instock_status"], "known")
        self.assertEqual(line["qc_passed_status"], "Accepted")
        self.assertEqual(line["stage"], 3)
        self.assertEqual(line["completion_status"], "complete")
        self.assertTrue(any("stock_uom" in query for query in self.fake.wo_queries))

    # -- P0-2 ---------------------------------------------------------------
    def test_subassemblies_are_not_added_to_finished_goods(self):
        self.full_chain("WO-FG", "KS0001", 10.0)
        self.full_chain("WO-PK", "PK#KS0001", 10.0, tn_name="T2",
                        with_qc=False, fg_line="SOI-1")
        self.full_chain("WO-ND", "ND#KS0001", 10.0, tn_name="T3",
                        with_qc=False, fg_line="SOI-1")
        line = self.line(self.chain.get_so_chain("SO-1"))
        self.assertEqual(line["reported"], 10.0)
        self.assertEqual(line["instock"], 10.0)
        self.assertEqual({s["production_item"] for s in line["subassemblies"]},
                         {"PK#KS0001", "ND#KS0001"})
        for sub in line["subassemblies"]:
            self.assertEqual(sub["all_process_done"]["qty_proven"], 10.0)

    def test_mixed_units_are_not_summed(self):
        self.full_chain("WO-A", "KS0001", 5.0, uom="个", tn_name="T1")
        self.full_chain("WO-B", "KS0001", 5.0, uom="箱", tn_name="T2")
        line = self.line(self.chain.get_so_chain("SO-1"))
        self.assertIsNone(line["reported"])
        self.assertIsNone(line["instock"])
        self.assertEqual(line["reported_status"], "unknown")
        self.assertNotEqual(line["stage"], 3)
        self.assertFalse(line["completion_status"] == "complete")

    def test_overlapping_tracking_identity_is_unknown(self):
        self.full_chain("WO-A", "KS0001", 5.0, tn_name="T-SHARED")
        self.full_chain("WO-B", "KS0001", 5.0, tn_name="T-SHARED")
        line = self.line(self.chain.get_so_chain("SO-1"))
        self.assertIsNone(line["reported"])
        self.assertIn("tracking_identity_overlap", line["evidence_conflicts"])

    # -- P0-3 ---------------------------------------------------------------
    def test_estimated_only_never_completes_or_reaches_stage_three(self):
        self.fake.wo_rows.append(wo("WO-1"))
        row = op("WO-1", "裁剪", 1)
        self.fake.op_rows.append(row)
        self.fake.jc_rows.append(jc("WO-1", row["name"], "裁剪", "", 10.0))
        line = self.line(self.chain.get_so_chain("SO-1"))
        self.assertIsNone(line["reported"])
        self.assertEqual(line["reported_status"], "estimated")
        self.assertEqual(line["all_process_estimated"], 10.0)
        self.assertNotEqual(line["stage"], 3)
        self.assertFalse(line["completed"] if "completed" in line else False)
        self.assertEqual(line["work_orders"][0]["completed"], False)
        self.assertNotEqual(line["work_orders"][0]["completion_status"], "complete")

    # -- P1-1 ---------------------------------------------------------------
    def test_restricted_job_card_keeps_stock_fact_and_hides_identity(self):
        hidden = self.full_chain()
        self.fake.permitted["Job Card"] = []
        result = self.chain.get_so_chain("SO-1")
        line = self.line(result)
        self.assertEqual(line["instock"], 10.0)
        self.assertIsNone(line["reported"])
        self.assertFalse(result["source_status"]["job_card"]["available"])
        self.assertNotIn(hidden, json.dumps(result, default=str))
        self.assertNotEqual(line["completion_status"], "complete")

    def test_restricted_work_order_is_not_leaked(self):
        self.full_chain("WO-1")
        self.full_chain("WO-2", tn_name="T2", with_qc=False)
        self.fake.permitted["Work Order"] = ["WO-1"]
        result = self.chain.get_so_chain("SO-1")
        line = self.line(result)
        self.assertNotIn("WO-2", json.dumps(result, default=str))
        self.assertIsNone(line["reported"])
        self.assertFalse(result["source_status"]["work_order"]["available"])

    def test_source_query_failure_is_not_reported_as_empty_success(self):
        self.full_chain()
        self.fake.fail_queries.add("from `tabStock Entry`")
        result = self.chain.get_so_chain("SO-1")
        line = self.line(result)
        self.assertFalse(result["source_status"]["stock_entry"]["available"])
        self.assertEqual(result["source_status"]["stock_entry"]["reason"], "query_error")
        self.assertTrue(result["partial"])
        self.assertTrue(any("stock entry" in reason.lower()
                            for reason in result["partial_reasons"]))
        self.assertIsNone(line["instock"])
        self.assertEqual(line["instock_status"], "unknown")

    # -- P1-2 ---------------------------------------------------------------
    def test_time_rollup_uses_latest_completion(self):
        self.full_chain("WO-1", qty=5.0, tn_name="T1", end="2026-10-20 17:00:00")
        self.full_chain("WO-2", qty=5.0, tn_name="T2", end="2026-10-20 18:00:00")
        line = self.line(self.chain.get_so_chain("SO-1"))
        evidence = line["production_evidence"]["all_process_done"]
        self.assertEqual(evidence["completed_at"], "2026-10-20 18:00:00")
        self.assertEqual(evidence["started_at"], "2026-10-20 08:00:00")

    # -- P1-3 ---------------------------------------------------------------
    def test_cancelled_work_order_with_valid_stock_entry_is_reachable(self):
        self.full_chain("WO-1", docstatus=2, with_qc=False)
        result = self.chain.get_so_chain("SO-1")
        line = self.line(result)
        self.assertEqual(line["instock"], 10.0)
        self.assertIsNone(line["reported"])
        codes = {c.get("code") for c in
                 line["production_evidence"]["work_orders"][0]["conflicts"]}
        self.assertIn("wo_cancelled_with_valid_stock_in", codes)
        self.assertNotEqual(line["stage"], 3)
        self.assertEqual(line["work_orders"][0]["completed"], False)


    # -- P1-1 / P1-3 follow-ups --------------------------------------------
    def test_time_logs_are_used_when_top_level_dates_missing(self):
        self.full_chain(time_logs=True)
        line = self.line(self.chain.get_so_chain("SO-1"))
        evidence = line["production_evidence"]["all_process_done"]
        self.assertEqual(evidence["started_at"], "2026-10-20 08:00:00")
        self.assertEqual(evidence["completed_at"], "2026-10-20 17:00:00")
        self.assertEqual(evidence["time_status"], "complete")

    def test_without_plan_permission_does_not_leak_plan_names(self):
        self.full_chain(ppi="PPI-1")
        self.fake.pp_rows = [{"pp": "PP-SECRET", "ppi": "PPI-1",
                              "planned_qty": 10.0, "pending_qty": 0.0}]
        self.fake.readable["Production Plan"] = False
        result = self.chain.get_so_chain("SO-1")
        self.assertNotIn("PP-SECRET", json.dumps(result, default=str))
        self.assertFalse(result["source_status"]["production_plan"]["available"])

    def test_without_dn_permission_does_not_leak_dn_names(self):
        self.full_chain()
        self.fake.dn_rows = [{
            "dn": "DN-SECRET", "date": "2026-10-21", "status": "To Bill",
            "docstatus": 1, "is_return": 0, "item_code": "KS0001",
            "qty": 10.0, "so_detail": "SOI-1"}]
        self.fake.readable["Delivery Note"] = False
        result = self.chain.get_so_chain("SO-1")
        self.assertNotIn("DN-SECRET", json.dumps(result, default=str))
        self.assertFalse(result["source_status"]["delivery_note"]["available"])

    def test_stock_status_is_conservative_across_lines(self):
        self.fake.so.items.append(types.SimpleNamespace(
            name="SOI-2", item_code="KS0002", item_name="成品2",
            customer_item_code="C-2", qty=5.0, delivered_qty=0.0, uom="个",
            delivery_date="2026-10-30"))
        self.full_chain("WO-1", "KS0001", 10.0, tn_name="T1", so_line="SOI-1")
        self.full_chain("WO-2", "KS0002", 5.0, tn_name="T2", so_line="SOI-2")
        self.fake.permitted["Stock Entry"] = ["SE-WO-2"]
        result = self.chain.get_so_chain("SO-1")
        self.assertFalse(result["source_status"]["stock_entry"]["available"])
        self.assertTrue(result["partial"])

    def test_real_estimated_response_renders_estimated_quantity(self):
        self.fake.wo_rows.append(wo("WO-1"))
        row = op("WO-1", "裁剪", 1)
        self.fake.op_rows.append(row)
        self.fake.jc_rows.append(jc("WO-1", row["name"], "裁剪", "", 10.0))
        result = self.chain.get_so_chain("SO-1")
        line = self.line(result)
        self.assertIsNone(line["reported"])
        self.assertEqual(line["all_process_estimated"], 10.0)
        self.assertEqual(line["reported_status"], "estimated")
        html = self._render(result["lines"])
        self.assertIn("10（估算）", html)
        self.assertNotIn("background:#fff9e6", html)

    def _render(self, lines):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        harness = Path(__file__).resolve().parent / "js" / "render_harness.js"
        root = Path(__file__).resolve().parents[1]
        js_path = root / "public" / "js" / "sales_order.js"
        if not js_path.exists():
            js_path = root / "key_test__sales_order_chain_append.js"
        payload = json.dumps({"sales_order": "SO-1", "lines": lines},
                             ensure_ascii=False)
        proc = subprocess.run(
            [node, str(harness), str(js_path)], input=payload,
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        return json.loads(proc.stdout)["html"]


if __name__ == "__main__":
    unittest.main()
