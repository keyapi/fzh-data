"""Acceptance tests for the supply facts contract (pure builders)."""
import datetime
import importlib.util
import sys
import types
from pathlib import Path
import unittest
from unittest import mock


class _AttrDict(dict):
    __getattr__ = dict.__getitem__


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.PermissionError = PermissionError
        self.ValidationError = ValueError
        self.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        self._dict = lambda value=None: _AttrDict(value or {})
        self.so_rows = []
        self.permitted_sos = []
        self.total_sos = 0
        self.dn_rows = []
        self.number_rows = []
        self.shipment_rows = []
        self.permitted_dns = []
        self.permitted_shipments = []
        self.event_rows = []
        self.event_error = None
        self.last_query = None
        self.db = types.SimpleNamespace(
            sql=self.sql, count=self.count, has_column=lambda *a, **k: True,
            table_exists=lambda *a, **k: True)

    def _filter_so_rows(self, query, values):
        values = values or {}
        allowed = set(values.get("permitted") or [])
        rows = [row for row in self.so_rows if row.so in allowed]
        for key, attr in (("sales_order", "so"), ("so_line", "so_line"),
                          ("item_code", "item_code"),
                          ("customer_item_code", "customer_item_code"),
                          ("warehouse", "warehouse")):
            if values.get(key):
                rows = [row for row in rows if getattr(row, attr, None) == values[key]]
        if "soi.qty - soi.delivered_qty" in query:
            rows = [
                row for row in rows
                if not hasattr(row, "qty")
                or float(getattr(row, "qty", 0) or 0) - float(getattr(row, "delivered_qty", 0) or 0) > 0
            ]
        return sorted(rows, key=lambda row: (str(getattr(row, "so", "")),
                                             str(getattr(row, "so_line", ""))))

    def sql(self, query, values=None, as_dict=False):
        values = values or {}
        if "select count(*) as total" in query:
            return [{"total": len(self._filter_so_rows(query, values))}]
        if "select so.name as so" in query:
            self.last_query = query
            rows = self._filter_so_rows(query, values)
            limit = values.get("limit")
            if limit:
                offset = int(values.get("offset") or 0)
                rows = rows[offset:offset + int(limit)]
            return rows
        if "from `tabDelivery Note Item`" in query:
            allowed = set(values.get("lines") or [])
            return [row for row in self.dn_rows if row.so_line in allowed]
        if "from `tabDelivery Note Logistics Number`" in query:
            return list(self.number_rows)
        if "custom_zmt_logistic_number as number" in query:
            return list(self.shipment_rows)
        return []

    def count(self, doctype, filters=None):
        return self.total_sos

    def get_list(self, doctype, filters=None, fields=None, limit_page_length=0):
        if doctype == "Sales Order":
            return [types.SimpleNamespace(name=name) for name in self.permitted_sos]
        if doctype == "Delivery Note":
            return [types.SimpleNamespace(name=name) for name in self.permitted_dns]
        if doctype == "Shipment":
            return [types.SimpleNamespace(name=name)
                    for name in self.permitted_shipments]
        return []

    def has_permission(self, doctype, ptype, doc=None):
        return True

    def throw(self, message, exc=None):
        raise (exc or Exception)(message)

    def get_all(self, *args, **kwargs):
        doctype = args[0] if args else kwargs.get("doctype")
        if doctype == "Shipment Logistics Event" and self.event_error is not None:
            raise self.event_error
        return list(self.event_rows)


def _line(**overrides):
    line = {"so": "SO-1", "so_line": "SOI-1", "item_code": "SKU-1", "uom": "个",
            "qty": 100.0, "delivered_qty": 25.0, "warehouse": "WH-1",
            "so_docstatus": 1, "so_status": "To Deliver and Bill",
            "transaction_date": "2026-10-01", "delivery_date": "2026-10-20",
            "scope": "in_house", "role": "finished"}
    line.update(overrides)
    return line


def _evidence_for_wos(wos, permission=True):
    if not permission:
        unknown = {"qty_proven": None, "qty_estimated": None,
                   "confidence": "unknown", "reasons": ["permission"],
                   "conflicts": [], "source_records": [],
                   "started_at": None, "completed_at": None}
        return {
            "work_orders": [], "wo_count": 0,
            "first_process_done": dict(unknown, **{"class": "first_process_done"}),
            "all_process_done": dict(unknown, **{"class": "all_process_done"}),
            "qc_performed": dict(unknown, **{"class": "qc_performed"}),
            "qc_passed": dict(unknown, **{"class": "qc_passed"}),
            "stock_in_posted": dict(unknown, **{"class": "stock_in_posted"}),
            "conflicts": [], "source_records": [],
        }
    proven = est = stock = 0.0
    unknown = False
    reasons = []
    starts, ends = [], []
    for wo in wos:
        produced = float(wo.get("produced") or 0)
        if (wo.get("stock_uom") or "个") != "个":
            unknown = True
            reasons.append("unit_mismatch")
        elif wo.get("produced_basis") == "wo_produced_qty":
            est += produced
        else:
            proven += produced
        stock += produced
        if wo.get("jc_start"):
            starts.append(wo["jc_start"])
        if wo.get("jc_end"):
            ends.append(wo["jc_end"])
    if unknown:
        proven = est = stock = None
    proven_value = None if unknown or (est and not proven) else proven
    base = {
        "qty_proven": proven_value,
        "qty_estimated": None if unknown else (est or None),
        "confidence": "unknown" if unknown else
                      ("mixed" if proven and est else ("estimated" if est else "proven")),
        "reasons": reasons, "conflicts": [], "source_records": [],
        "started_at": min(starts) if starts else None,
        "completed_at": max(ends) if ends else None,
    }
    all_ev = dict(base, **{"class": "all_process_done",
                           "qty_basis": "wo_produced_qty" if est and not proven
                           else "all_process_done"})
    return {
        "work_orders": [], "wo_count": len(wos),
        "first_process_done": dict(base, **{"class": "first_process_done"}),
        "all_process_done": all_ev,
        "qc_performed": dict(base, **{"class": "qc_performed", "qty_proven": 0.0}),
        "qc_passed": dict(base, **{"class": "qc_passed",
                                   "qty_proven": None, "qty_estimated": None,
                                   "confidence": "unknown"}),
        "stock_in_posted": dict(base, **{"class": "stock_in_posted",
                                         "qty_proven": None if unknown else stock}),
        "conflicts": [], "source_records": [],
    }


def _ctx(**overrides):
    ctx = {"pps": [], "wos": [], "dns": [], "numbers_by_dn": {}, "shipment_by_number": {},
           "dn_permission": True, "shipment_permission": True, "work_order_permission": True,
           "observed_at": "2026-10-27T10:00:00"}
    ctx.update(overrides)
    if "evidence" not in ctx:
        ctx["evidence"] = _evidence_for_wos(
            ctx.get("wos") or [], ctx.get("work_order_permission", True))
    return ctx


def _wo(name="WO-1", qty=100.0, produced=60.0, **overrides):
    wo = {"wo": name, "qty": qty, "produced": produced, "status": "In Process",
          "item_code": "SKU-1", "stock_uom": "个",
          "docstatus": 1, "planned_start_date": "2026-10-02",
          "planned_end_date": "2026-10-15", "jc_start": "2026-10-03",
          "jc_end": "2026-10-14", "tracking_numbers": [],
          "link_proof": "wo.sales_order_item"}
    wo.update(overrides)
    return wo


def _dn(name="DN-1", qty=25.0, docstatus=1, is_return=0, **overrides):
    dn = {"dn": name, "date": "2026-10-16", "status": "To Bill", "docstatus": docstatus,
          "is_return": is_return, "so_line": "SOI-1", "qty": qty, "uom": "个",
          "warehouse": "WH-1"}
    dn.update(overrides)
    return dn


def _dn_row(**overrides):
    row = {"date": "2026-10-16", "status": "", "docstatus": 1, "is_return": 0,
           "return_against": None, "so_line": "SOI-1", "dn_detail": None, "uom": "个"}
    row.update(overrides)
    return _AttrDict(row)


def _ship(number="ZMT1", status="已离港", eta="2026-11-01", atd="2026-10-17",
          ata=None, dlvr=None, status4="在途"):
    return {"shipment": "SHIP-1", "number": number, "status11": status, "status4": status4,
            "eta": eta, "atd": atd, "ata": ata, "dlvr": dlvr, "match_status": "Matched"}


class SupplyFactsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = {name: sys.modules.get(name)
                     for name in ("frappe", "frappe.utils", "key_test",
                                  "key_test.supply_query",
                                  "key_test.production_evidence")}
        fake = FakeFrappe()
        cls.fake = fake
        sys.modules["frappe"] = fake
        sys.modules["frappe.utils"] = types.SimpleNamespace(
            getdate=lambda x: x if isinstance(x, datetime.date) else datetime.date.fromisoformat(str(x)[:10]),
            today=lambda: "2026-10-27",
            now_datetime=lambda: "2026-10-27 10:00:00")
        root = Path(__file__).parents[1]
        service = root / "supply_query.py"
        facts = root / "supply_facts.py"
        if not facts.exists():
            service = root / "key_test" / "key_test__supply_query.py"
            facts = root / "key_test" / "key_test__supply_facts.py"
        package = types.ModuleType("key_test")
        package.__path__ = []
        sys.modules["key_test"] = package
        spec = importlib.util.spec_from_file_location("key_test_accept_supply_query", service)
        cls.service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.service)
        sys.modules["key_test.supply_query"] = cls.service
        spec = importlib.util.spec_from_file_location(
            "key_test.production_evidence", root / "production_evidence.py")
        cls.evidence = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.evidence)
        sys.modules["key_test.production_evidence"] = cls.evidence
        spec = importlib.util.spec_from_file_location("key_test_accept_supply_facts", facts)
        cls.facts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.facts)

    @classmethod
    def tearDownClass(cls):
        for name, module in cls.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def _sum_executed(self, stage_rows):
        return round(sum(r["qty"] or 0 for r in stage_rows
                         if r["stage"] in self.facts.EXECUTED_STAGES
                         and r["qty"] is not None), 6)

    def test_case1_stage_balances_conserve_without_cumulative_double_count(self):
        stages = self.facts.build_stage_balances(_line(), _ctx(wos=[_wo()], dns=[_dn()]))
        self.assertAlmostEqual(self._sum_executed(stages), 100.0)
        by_stage = {r["stage"]: r["qty"] for r in stages}
        self.assertEqual(by_stage["produced_pending_dn"], 35.0)
        self.assertEqual(by_stage["in_production"], 40.0)
        self.assertEqual(by_stage["shipped_in_transit"], 25.0)
        self.assertNotIn("delivered_sellable", by_stage)

    def test_case2_multi_waybill_never_duplicates_dn_quantity(self):
        numbers = {"DN-1": [{"number": "A"}, {"number": "B"}]}
        ships = {"A": _ship("A", "已离港"), "B": _ship("B", "已离港", eta="2026-11-05")}
        ctx = _ctx(dns=[_dn(qty=100.0)], numbers_by_dn=numbers, shipment_by_number=ships)
        stages = self.facts.build_stage_balances(_line(), ctx)
        shipped = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(len(shipped), 1)
        self.assertEqual(shipped[0]["qty"], 100.0)
        tranches = self.facts.build_availability(_line(), ctx, stages)
        self.assertEqual(len(tranches), 1)
        self.assertIsNone(tranches[0]["qty"])
        self.assertEqual(tranches[0]["scenario"], "allocation_unknown")
        links = self.facts.build_links(_line(), ctx)
        waybills = [l for l in links if l["relation"] == "waybill"]
        self.assertEqual(len(waybills), 2)
        self.assertTrue(all(l["qty"] is None for l in waybills))

    def test_waybill_link_explicitly_marks_matched_shipment(self):
        numbers = {"DN-1": [{"number": "WB-1"}]}
        ctx = _ctx(dns=[_dn(qty=10.0)], numbers_by_dn=numbers, shipment_by_number={})
        waybill = next(l for l in self.facts.build_links(_line(), ctx)
                       if l["relation"] == "waybill")
        self.assertEqual(waybill["target_name"], "WB-1")
        self.assertFalse(waybill["target_is_record"])

        ctx = _ctx(dns=[_dn(qty=10.0)], numbers_by_dn=numbers,
                   shipment_by_number={"WB-1": {"shipment": "SHIP-1"}})
        waybill = next(l for l in self.facts.build_links(_line(), ctx)
                       if l["relation"] == "waybill")
        self.assertEqual(waybill["target_name"], "SHIP-1")
        self.assertTrue(waybill["target_is_record"])

    def test_case3_mixed_arrival_counts_once(self):
        numbers = {"DN-1": [{"number": "A"}, {"number": "B"}]}
        ships = {"A": _ship("A", "已上传POD", eta="2026-10-01", ata="2026-10-01"),
                 "B": _ship("B", "已离港", eta="2026-11-05")}
        ctx = _ctx(dns=[_dn(qty=100.0)], numbers_by_dn=numbers, shipment_by_number=ships)
        stages = self.facts.build_stage_balances(_line(), ctx)
        self.assertAlmostEqual(self._sum_executed(stages), 100.0)
        self.assertEqual(sum(r["qty"] for r in stages if r["stage"].startswith("shipped")
                             or r["stage"] == self.facts.STAGE_ARRIVED), 100.0)

    def test_case4_scope_is_preserved_and_never_eligible(self):
        stages = self.facts.build_stage_balances(_line(scope="external_fba"), _ctx(dns=[_dn()]))
        self.assertTrue(all(r["scope"] == "external_fba" for r in stages))
        tranches = self.facts.build_availability(_line(scope="external_fba"), _ctx(dns=[_dn()]), stages)
        self.assertTrue(all(t["eligible"] is False for t in tranches))

    def test_case5_arrival_eta_and_actual_are_separate_and_frozen(self):
        ships = {"A": _ship("A", "已到港", eta="2026-11-05", ata="2026-11-03")}
        ctx = _ctx(dns=[_dn()], numbers_by_dn={"DN-1": [{"number": "A"}]},
                   shipment_by_number=ships)
        first = self.facts.build_milestones(_line(), ctx)
        arrival = next(r for r in first if r["node"] == "arrival")
        self.assertEqual(arrival["latest_expected_at"], "2026-11-05")
        self.assertEqual(arrival["actual_at"], "2026-11-03")
        stages = self.facts.build_stage_balances(_line(), ctx)
        tranche = self.facts.build_availability(_line(), ctx, stages)[0]
        self.assertIsNone(tranche["available_date"])
        ships2 = {"A": _ship("A", "已到港", eta="2026-11-20", ata="2026-11-03")}
        self.facts.build_milestones(_line(), _ctx(dns=[_dn()], numbers_by_dn={"DN-1": [{"number": "A"}]},
                                                  shipment_by_number=ships2))
        self.assertEqual(arrival["latest_expected_at"], "2026-11-05")

    def test_case6_tranches_keep_their_own_dates(self):
        numbers = {"DN-1": [{"number": "A"}], "DN-2": [{"number": "B"}]}
        ships = {"A": _ship("A", "已离港", eta="2026-11-01"),
                 "B": _ship("B", "已离港", eta="2026-11-10")}
        ctx = _ctx(dns=[_dn("DN-1", qty=40.0), _dn("DN-2", qty=60.0)],
                   numbers_by_dn=numbers, shipment_by_number=ships)
        stages = self.facts.build_stage_balances(_line(), ctx)
        tranches = self.facts.build_availability(_line(), ctx, stages)
        self.assertEqual(sorted(t["latest_expected_at"] for t in tranches),
                         ["2026-11-01", "2026-11-10"])
        self.assertEqual(sorted(t["qty"] for t in tranches), [40.0, 60.0])

    def test_case7_cancelled_order_keeps_physical_goods_traceable(self):
        stages = self.facts.build_stage_balances(
            _line(so_docstatus=2), _ctx(wos=[_wo(produced=60.0)], dns=[_dn(qty=25.0)]))
        cancelled = [r for r in stages if r["stage"] == self.facts.STAGE_CANCELLED]
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["qty"], 100.0)
        physical = [r for r in stages
                    if r["stage"] in (self.facts.STAGE_IN_TRANSIT,
                                      self.facts.STAGE_PRODUCED_PENDING,
                                      self.facts.STAGE_ARRIVED)]
        self.assertEqual(round(sum(r["qty"] or 0 for r in physical), 6), 60.0)
        self.assertTrue(all(r["demand_status"] == "cancelled" for r in stages))

    def test_uom_mismatch_does_not_convert_units(self):
        ctx = _ctx(wos=[_wo()], dns=[_dn(qty=2.0, uom="箱")])
        stages = self.facts.build_stage_balances(_line(), ctx)
        self.assertFalse([r for r in stages if r["stage"] == self.facts.STAGE_NOT_PLANNED])
        unknown = [r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN]
        self.assertTrue(unknown)
        self.assertIsNone(unknown[0]["qty"])
        self.assertIn("单位", unknown[0]["exclusion_reason"])
        physical = [r for r in stages if r["uom"] == "箱"]
        self.assertEqual(physical[0]["qty"], 2.0)
        self.assertEqual(physical[0]["qty_status"], "known")
        tranches = self.facts.build_availability(_line(), ctx, stages)
        self.assertEqual(len(tranches), 1)
        self.assertEqual(tranches[0]["uom"], "箱")
        self.assertEqual(tranches[0]["qty"], 2.0)
        self.assertEqual(tranches[0]["qty_status"], "known")

    def test_return_against_nets_the_original_dn(self):
        dns = [_dn(qty=100.0),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        in_transit = next(r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT)
        self.assertEqual(in_transit["qty"], 90.0)
        returned = next(r for r in stages if r["stage"] == self.facts.STAGE_RETURNED)
        self.assertEqual(returned["qty"], 10.0)
        unknown = next(r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN)
        self.assertEqual(unknown["qty"], 10.0)
        self.assertIn("退货", unknown["exclusion_reason"])
        self.assertAlmostEqual(
            sum(r["qty"] for r in stages if r["qty"] is not None
                and r["stage"] not in (self.facts.STAGE_RETURNED, self.facts.STAGE_DRAFT)),
            100.0)

    def test_return_does_not_regenerate_pending_supply(self):
        dns = [_dn(qty=100.0),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1")]
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo(produced=100.0)], dns=dns))
        self.assertFalse([r for r in stages
                          if r["stage"] == self.facts.STAGE_PRODUCED_PENDING])
        tranches = self.facts.build_availability(
            _line(), _ctx(wos=[_wo(produced=100.0)], dns=dns), stages)
        self.assertFalse([t for t in tranches if t["qty"] == 10.0])

    def test_row_sources_restricted_make_stage_unknown(self):
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo()], work_order_permission=False))
        unknown = [r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN]
        self.assertTrue(unknown)
        self.assertEqual(unknown[0]["qty"], 100.0)
        self.assertIn("受限", unknown[0]["exclusion_reason"])
        self.assertFalse([r for r in stages if r["stage"] == self.facts.STAGE_NOT_PLANNED])

    def test_tranche_ids_include_so_line(self):
        dn_ctx = _ctx(dns=[_dn()], numbers_by_dn={"DN-1": [{"number": "A"}]},
                      shipment_by_number={"A": _ship("A")})
        line_a = _line(so_line="SOI-A")
        line_b = _line(so_line="SOI-B")
        ta = self.facts.build_availability(
            line_a, dn_ctx, self.facts.build_stage_balances(line_a, dn_ctx))
        tb = self.facts.build_availability(
            line_b, dn_ctx, self.facts.build_stage_balances(line_b, dn_ctx))
        self.assertNotEqual(ta[0]["tranche_id"], tb[0]["tranche_id"])
        self.assertTrue(ta[0]["tranche_id"].startswith("SOI-A::"))

    def test_row_level_permission_filters_sales_order_lines(self):
        self.fake.so_rows = [
            types.SimpleNamespace(so="SO-1", so_line="A"),
            types.SimpleNamespace(so="SO-2", so_line="B")]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 2
        lines, restricted, _total = self.facts.load_lines({})
        self.assertEqual([row.so for row in lines], ["SO-1"])
        self.assertTrue(restricted)

    def test_draft_dn_does_not_duplicate_stage_quantity(self):
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo()], dns=[_dn(docstatus=0, qty=40.0)]))
        drafts = [r for r in stages if r["stage"] == self.facts.STAGE_DRAFT]
        self.assertEqual(len(drafts), 1)
        self.assertIsNone(drafts[0]["qty"])
        self.assertAlmostEqual(self._sum_executed(stages), 100.0)

    def test_produced_from_wo_qty_is_marked_estimated(self):
        wo = _wo(produced=60.0, produced_basis="wo_produced_qty")
        stages = self.facts.build_stage_balances(_line(), _ctx(wos=[wo]))
        pending = next(r for r in stages if r["stage"] == "produced_pending_dn")
        self.assertEqual(pending["qty_status"], "estimated")
        self.assertEqual(pending["qty_basis"], "wo_produced_qty")

    def test_historical_as_of_rejected_server_side(self):
        with self.assertRaises(Exception):
            self.facts.get_supply_facts({"as_of": "2020-01-01"})

    def test_empty_result_keeps_integrity(self):
        self.fake.so_rows = []
        self.fake.permitted_sos = []
        self.fake.total_sos = 0
        result = self.facts.get_supply_facts({})
        manifest = result["manifest"]
        self.assertTrue(manifest["partial"])
        self.assertEqual(manifest["coverage"]["empty_reason"], "no_matching_lines")
        self.assertEqual(manifest["coverage"]["external_sources"]["receipt"], "not_integrated")
        self.assertIn("empty_result", " ".join(manifest["notes"]))
        self.assertIn("source_status", result)
        self.assertEqual(manifest["coverage"]["source_status"], result["source_status"])
        for state in result["source_status"].values():
            self.assertIn("available", state)
            self.assertIn("restricted", state)
            self.assertIn("reason", state)

    def test_time_log_failure_only_degrades_time(self):
        line = _AttrDict(_line(qty=10.0))
        wo_row = _AttrDict(
            wo="WO-1", qty=10.0, produced_qty=10.0, status="Completed",
            docstatus=1, production_item="SKU-1", stock_uom="个",
            sales_order_item="SOI-1", fg_sales_order_item=None,
            production_plan_item=None, planned_start_date=None,
            planned_end_date=None)
        op_row = _AttrDict(name="OP1", parent="WO-1", operation="裁剪",
                           sequence_id=1, status="Completed", completed_qty=10.0)
        jc_row = _AttrDict(
            name="JC1", work_order="WO-1", operation_id="OP1",
            operation="裁剪", status="Completed", total_completed_qty=10.0,
            for_quantity=10.0, actual_start_date=None,
            actual_end_date="2026-10-20 17:00:00", tracking_number="T1",
            docstatus=1, quality_inspection=None)
        tn_row = _AttrDict(name="T1", work_order="WO-1", qty=10.0)

        def get_all(doctype, filters=None, fields=None, order_by=None):
            if doctype == "Work Order Operation":
                return [op_row]
            if doctype == "Job Card":
                return [jc_row]
            if doctype == "Tracking Number":
                return [tn_row]
            if doctype == "Job Card Time Log":
                raise RuntimeError("boom")
            return []

        def get_list(doctype, filters=None, fields=None, limit_page_length=0):
            return {
                "Work Order": [_AttrDict(name="WO-1")],
                "Job Card": [_AttrDict(name="JC1")],
                "Tracking Number": [_AttrDict(name="T1")],
            }.get(doctype, [])

        def sql(query, values=None, as_dict=False):
            if "from `tabWork Order` w" in query:
                return [wo_row]
            return []

        with mock.patch.object(self.facts.frappe, "get_all", side_effect=get_all), \
             mock.patch.object(self.facts.frappe, "get_list", side_effect=get_list), \
             mock.patch.object(self.facts.frappe.db, "sql", side_effect=sql):
            grouped, status = self.facts.load_wos([line], {})
        self.assertTrue(status["available"])
        self.assertFalse(status["restricted"])
        self.assertEqual(status["job_card_time_log"]["reason"], "query_error")
        wo = grouped["SOI-1"][0]
        evidence = self.facts.build_wo_evidence(
            {"name": wo["wo"], "qty": wo["qty"], "stock_uom": wo["stock_uom"],
             "production_item": wo["item_code"], "docstatus": wo["docstatus"]},
            wo["operations"], wo["job_cards"], wo["tracking_number_rows"],
            [], [], order_uom="个",
            availability={"job_cards": True, "work_order": True,
                          "tracking_numbers": True, "stock_entries": True,
                          "quality_inspections": True})
        self.assertEqual(evidence["all_process_done"]["qty_proven"], 10.0)

    def test_response_carries_source_status_and_recomputes_partial(self):
        self.fake.so_rows = [self._row(1)]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 1
        wo_status = {"available": False, "reason": "query_error",
                     "restricted": False, "restricted_wos": set(),
                     "job_card_unavailable_wos": set(),
                     "tracking_unavailable_wos": set()}
        with mock.patch.object(self.facts, "load_wos", return_value=({}, wo_status)), \
             mock.patch.object(self.facts, "load_stock_entries",
                               return_value=({}, {"available": False,
                                                  "reason": "query_error"})):
            result = self.facts.get_supply_facts(
                filters={"sales_order": "SO-1", "limit": 1})
        self.assertFalse(result["source_status"]["work_order"]["available"])
        self.assertFalse(result["source_status"]["stock_entry"]["available"])
        self.assertEqual(result["source_status"]["work_order"]["reason"],
                         "query_error")
        self.assertEqual(result["source_status"]["stock_entry"]["reason"],
                         "query_error")
        self.assertIn("restricted", result["source_status"]["work_order"])
        self.assertEqual(result["manifest"]["coverage"]["source_status"],
                         result["source_status"])
        self.assertTrue(result["manifest"]["partial"])
        reasons = " ".join(result["manifest"]["partial_reasons"]).lower()
        self.assertIn("work order source unavailable: query_error", reasons)
        self.assertIn("stock entry source unavailable: query_error", reasons)

    def test_in_production_capped_by_wo_coverage(self):
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo(qty=20.0, produced=0.0)]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage["in_production"], 20.0)
        self.assertEqual(by_stage["not_planned"], 80.0)
        self.assertNotIn(self.facts.STAGE_UNKNOWN, by_stage)
        self.assertAlmostEqual(self._sum_executed(stages), 100.0)

    def test_in_production_uses_unproduced_wo_gap_not_pending(self):
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo(qty=40.0, produced=30.0)], dns=[_dn(qty=10.0)]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage["produced_pending_dn"], 20.0)
        self.assertEqual(by_stage["in_production"], 10.0)
        self.assertEqual(by_stage["not_planned"], 60.0)
        self.assertAlmostEqual(self._sum_executed(stages), 100.0)

    def test_partial_return_does_not_infer_in_production(self):
        dns = [_dn(qty=80.0),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1")]
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo(qty=100.0, produced=100.0)], dns=dns))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage["shipped_in_transit"], 70.0)
        self.assertEqual(by_stage["produced_pending_dn"], 20.0)
        self.assertEqual(by_stage["returned"], 10.0)
        self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN], 10.0)
        self.assertNotIn("in_production", by_stage)
        self.assertAlmostEqual(
            sum(q for stage, q in by_stage.items() if stage != "returned"), 100.0)

    def test_milestone_dispatch_requires_order_unit(self):
        ctx = _ctx(dns=[_dn(qty=2.0, uom="箱")])
        dispatch = next(r for r in self.facts.build_milestones(_line(), ctx)
                        if r["node"] == "dispatch")
        self.assertIsNone(dispatch["qty"])
        self.assertEqual(dispatch["qty_status"], "unknown")
        self.assertIn("单位", dispatch["note"])
        ok = next(r for r in self.facts.build_milestones(_line(), _ctx(dns=[_dn(qty=25.0)]))
                  if r["node"] == "dispatch")
        self.assertEqual(ok["qty"], 25.0)
        self.assertEqual(ok["qty_status"], "known")

    def test_wo_unit_mismatch_routes_production_to_unknown(self):
        wo = _wo(qty=100.0, produced=100.0, stock_uom="箱")
        stages = self.facts.build_stage_balances(_line(), _ctx(wos=[wo]))
        stages_by_name = {r["stage"]: r for r in stages if r["qty"] is not None}
        self.assertNotIn("produced_pending_dn", stages_by_name)
        self.assertNotIn("in_production", stages_by_name)
        self.assertNotIn("not_planned", stages_by_name)
        self.assertEqual(stages_by_name[self.facts.STAGE_UNKNOWN]["qty"], 100.0)
        self.assertIn("单位", stages_by_name[self.facts.STAGE_UNKNOWN]["exclusion_reason"])
        milestones = self.facts.build_milestones(_line(), _ctx(wos=[wo]))
        end = next(r for r in milestones if r["node"] == "production_end")
        self.assertIsNone(end["qty"])
        self.assertEqual(end["qty_status"], "unknown")
        links = self.facts.build_links(_line(), _ctx(wos=[wo]))
        produced = [l for l in links if l["relation"] == "produced_by"]
        self.assertTrue(produced)
        self.assertTrue(all(l["qty"] is None for l in produced))

    def test_planned_by_link_requires_order_unit(self):
        pp = {"pp": "PP-1", "ppi": "PPI-1", "planned_qty": 100.0, "stock_uom": "箱",
              "pp_date": "2026-10-01"}
        planned = next(l for l in self.facts.build_links(_line(), _ctx(pps=[pp]))
                       if l["relation"] == "planned_by")
        self.assertIsNone(planned["qty"])
        ok = next(l for l in self.facts.build_links(
            _line(), _ctx(pps=[dict(pp, stock_uom="个")])) if l["relation"] == "planned_by")
        self.assertEqual(ok["qty"], 100.0)

    def test_tranche_ids_unique_per_warehouse_and_keep_dn_warehouse(self):
        dns = [_dn(name="DN-1", qty=40.0, warehouse="WH-A", dn_item="row-a"),
               _dn(name="DN-1", qty=60.0, warehouse="WH-B", dn_item="row-b")]
        ctx = _ctx(dns=dns, numbers_by_dn={"DN-1": [{"number": "A"}]},
                   shipment_by_number={"A": _ship("A")})
        stages = self.facts.build_stage_balances(_line(), ctx)
        transit = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(sorted(r["warehouse"] for r in transit), ["WH-A", "WH-B"])
        self.assertEqual(sorted(r["qty"] for r in transit), [40.0, 60.0])
        tranches = self.facts.build_availability(_line(), ctx, stages)
        self.assertEqual(len(tranches), 2)
        self.assertEqual(len({t["tranche_id"] for t in tranches}), 2)
        self.assertEqual(sorted(t["warehouse"] for t in tranches), ["WH-A", "WH-B"])
        self.assertEqual(sorted(t["qty"] for t in tranches), [40.0, 60.0])

    def test_missing_dn_uom_stays_unknown(self):
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=[_dn(qty=2.0, uom=None)]))
        physical = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(len(physical), 1)
        self.assertEqual(physical[0]["qty"], 2.0)
        self.assertIsNone(physical[0]["uom"])
        self.assertEqual(physical[0]["qty_status"], "unknown")
        self.assertFalse([r for r in stages if r["qty_status"] == "known"])
        hint = next(r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN)
        self.assertIn("单位", hint["exclusion_reason"])

    def test_all_restricted_orders_report_all_restricted(self):
        self.fake.so_rows = []
        self.fake.permitted_sos = []
        self.fake.total_sos = 3
        lines, restricted, _total = self.facts.load_lines({})
        self.assertEqual(lines, [])
        self.assertTrue(restricted)
        result = self.facts.get_supply_facts({})
        self.assertEqual(result["manifest"]["coverage"]["empty_reason"], "all_restricted")
        self.assertIn("all_restricted", " ".join(result["manifest"]["notes"]))

    def test_cross_warehouse_return_nets_original_item(self):
        dns = [_dn(qty=100.0, warehouse="WH-A", dn_item="row-a"),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1",
                   dn_item="row-r", dn_detail="row-a", warehouse="WH-B")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        transit = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(len(transit), 1)
        self.assertEqual(transit[0]["qty"], 90.0)
        self.assertEqual(transit[0]["warehouse"], "WH-A")
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(returned[0]["qty"], 10.0)
        unknown = [r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN
                   and r["qty"] is not None]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["qty"], 10.0)
        self.assertAlmostEqual(sum(r["qty"] for r in stages if r["qty"] is not None
                                   and r["stage"] not in (self.facts.STAGE_RETURNED,
                                                          self.facts.STAGE_DRAFT)), 100.0)

    def test_return_without_item_link_falls_back_to_single_dn_row(self):
        dns = [_dn(qty=100.0, warehouse="WH-A"),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1",
                   warehouse="WH-B")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        transit = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(len(transit), 1)
        self.assertEqual(transit[0]["qty"], 90.0)
        self.assertEqual(sum(1 for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN
                             and r["qty"] is not None), 1)

    def test_unattributable_return_is_reported_without_netting(self):
        dns = [_dn(qty=40.0, warehouse="WH-A", dn_item="row-a"),
               _dn(qty=60.0, warehouse="WH-B", dn_item="row-b"),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1",
                   warehouse="WH-C")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        transit = {r["warehouse"]: r["qty"] for r in stages
                   if r["stage"] == self.facts.STAGE_IN_TRANSIT}
        self.assertEqual(transit, {"WH-A": 40.0, "WH-B": 60.0})
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0]["qty"], 10.0)
        self.assertIn("归属", returned[0]["exclusion_reason"])
        self.assertFalse([r for r in stages
                          if r["stage"] == self.facts.STAGE_UNKNOWN and r["qty"] is not None])
        self.assertAlmostEqual(sum(r["qty"] for r in stages if r["qty"] is not None
                                   and r["stage"] not in (self.facts.STAGE_RETURNED,
                                                          self.facts.STAGE_DRAFT)), 100.0)

    def test_return_beyond_item_capacity_keeps_other_rows(self):
        dns = [_dn(qty=40.0, warehouse="WH-A", dn_item="row-a"),
               _dn(qty=60.0, warehouse="WH-B", dn_item="row-b"),
               _dn(name="DN-R", qty=-50.0, is_return=1, return_against="DN-1",
                   dn_item="row-r", dn_detail="row-a", warehouse="WH-C")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        transit = {r["warehouse"]: r["qty"] for r in stages
                   if r["stage"] == self.facts.STAGE_IN_TRANSIT}
        self.assertEqual(transit, {"WH-B": 60.0})
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(sorted(r["qty"] for r in returned), [10.0, 40.0])
        excess = next(r for r in returned if r["qty"] == 10.0)
        self.assertIn("超退", excess["exclusion_reason"])
        matched = next(r for r in returned if r["qty"] == 40.0)
        self.assertIn("抵扣", matched["exclusion_reason"])
        unknown = [r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN
                   and r["qty"] is not None]
        self.assertEqual([r["qty"] for r in unknown], [40.0])
        self.assertAlmostEqual(sum(r["qty"] for r in stages if r["qty"] is not None
                                   and r["stage"] not in (self.facts.STAGE_RETURNED,
                                                          self.facts.STAGE_DRAFT)), 100.0)

    def test_explicit_detail_mismatch_is_not_single_row_fallback(self):
        dns = [_dn(qty=100.0, warehouse="WH-A", dn_item="row-a"),
               _dn(name="DN-R", qty=-10.0, is_return=1, return_against="DN-1",
                   dn_item="row-r", dn_detail="OTHER-ROW", warehouse="WH-B")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        transit = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(len(transit), 1)
        self.assertEqual(transit[0]["qty"], 100.0)
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(returned[0]["qty"], 10.0)
        self.assertIn("冲突", returned[0]["exclusion_reason"])
        self.assertFalse([r for r in stages
                          if r["stage"] == self.facts.STAGE_UNKNOWN and r["qty"] is not None])

    def test_partial_waybill_status_is_not_arrived(self):
        numbers = {"DN-1": [{"number": "A"}, {"number": "B"}]}
        ships = {"A": _ship("A", "已到港")}
        ctx = _ctx(dns=[_dn(qty=100.0)], numbers_by_dn=numbers,
                   shipment_by_number=ships)
        stages = self.facts.build_stage_balances(_line(), ctx)
        self.assertFalse([r for r in stages if r["stage"] == self.facts.STAGE_ARRIVED])
        transit = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(sum(r["qty"] for r in transit), 100.0)
        self.assertIn("状态", transit[0]["stage_detail"])
        both = {"A": _ship("A", "已到港"), "B": _ship("B", "已到港")}
        arrived = self.facts.build_stage_balances(
            _line(), _ctx(dns=[_dn(qty=100.0)], numbers_by_dn=numbers,
                          shipment_by_number=both))
        # Arrival is still part of transport; only signed/POD changes stage.
        self.assertFalse([r for r in arrived
                          if r["stage"] == self.facts.STAGE_ARRIVED])
        transit_both = [r for r in arrived
                        if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(sum(r["qty"] for r in transit_both), 100.0)
        self.assertIn("运输", transit_both[0]["stage_detail"])

    def test_submitted_plan_without_wo_is_unknown_not_unplanned(self):
        pp = {"pp": "PP-1", "ppi": "PPI-1", "item_code": "SKU-1",
              "planned_qty": 100.0, "stock_uom": "个", "pp_date": "2026-10-01"}
        stages = self.facts.build_stage_balances(_line(), _ctx(pps=[pp]))
        by_stage = {r["stage"]: r for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN]["qty"], 100.0)
        self.assertIn("计划", by_stage[self.facts.STAGE_UNKNOWN]["exclusion_reason"])
        self.assertNotIn(self.facts.STAGE_NOT_PLANNED, by_stage)
        other = dict(pp, item_code="SKU-OTHER")
        stages = self.facts.build_stage_balances(_line(), _ctx(pps=[other]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_NOT_PLANNED], 100.0)

    def test_plan_coverage_beyond_wo_is_unknown_and_rest_unplanned(self):
        pp = {"pp": "PP-1", "ppi": "PPI-1", "item_code": "SKU-1",
              "planned_qty": 100.0, "stock_uom": "个", "pp_date": "2026-10-01"}
        stages = self.facts.build_stage_balances(
            _line(), _ctx(pps=[pp], wos=[_wo(qty=40.0, produced=0.0)]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_IN_PRODUCTION], 40.0)
        self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN], 60.0)
        self.assertNotIn(self.facts.STAGE_NOT_PLANNED, by_stage)
        partial = dict(pp, planned_qty=30.0)
        stages = self.facts.build_stage_balances(_line(), _ctx(pps=[partial]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN], 30.0)
        self.assertEqual(by_stage[self.facts.STAGE_NOT_PLANNED], 70.0)

    def test_load_dns_preserves_return_item_identity_and_warehouses(self):
        self.fake.dn_rows = [
            _dn_row(dn="DN-1", dn_item="row-a", qty=40.0, warehouse="WH-A"),
            _dn_row(dn="DN-1", dn_item="row-b", qty=60.0, warehouse="WH-B"),
            _dn_row(dn="DN-R", dn_item="row-r1", dn_detail="row-a", qty=-10.0,
                    warehouse="WH-C", is_return=1, return_against="DN-1"),
            _dn_row(dn="DN-R", dn_item="row-r2", dn_detail="row-b", qty=-10.0,
                    warehouse="WH-C", is_return=1, return_against="DN-1"),
        ]
        self.fake.permitted_dns = ["DN-1", "DN-R"]
        dns, restricted = self.facts.load_dns([_AttrDict(_line())])
        self.assertFalse(restricted)
        rows = dns["SOI-1"]
        self.assertEqual(sum(1 for r in rows if r["is_return"]), 2)
        ctx = _ctx(dns=rows)
        stages = self.facts.build_stage_balances(_line(), ctx)
        transit = {r["warehouse"]: r["qty"] for r in stages
                   if r["stage"] == self.facts.STAGE_IN_TRANSIT}
        self.assertEqual(transit, {"WH-A": 30.0, "WH-B": 50.0})
        tranches = self.facts.build_availability(_line(), ctx, stages)
        self.assertEqual({t["warehouse"]: t["qty"] for t in tranches},
                         {"WH-A": 30.0, "WH-B": 50.0})
        self.assertEqual(len({t["tranche_id"] for t in tranches}), 2)

    def test_load_dns_aggregates_rows_but_keeps_detail_identity(self):
        self.fake.dn_rows = [
            _dn_row(dn="DN-1", dn_item="row-a", qty=40.0, warehouse="WH-A"),
            _dn_row(dn="DN-1", dn_item="row-b", qty=60.0, warehouse="WH-A"),
            _dn_row(dn="DN-R", dn_item="row-r", qty=-10.0, warehouse="WH-B",
                    is_return=1, return_against="DN-1"),
        ]
        self.fake.permitted_dns = ["DN-1", "DN-R"]
        dns, _ = self.facts.load_dns([_AttrDict(_line())])
        rows = dns["SOI-1"]
        outbound = [r for r in rows if not r["is_return"]]
        self.assertEqual(len(outbound), 1)
        self.assertEqual(sorted(outbound[0]["item_qty"]), ["row-a", "row-b"])
        self.assertAlmostEqual(sum(outbound[0]["item_qty"].values()), 100.0)
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=rows))
        transit = [r["qty"] for r in stages
                   if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(transit, [100.0])
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(returned[0]["qty"], 10.0)
        self.assertIn("归属", returned[0]["exclusion_reason"])

    def test_return_order_does_not_change_capacity_allocation(self):
        base = [_dn(qty=100.0, warehouse="WH-A", dn_item="row-a")]
        no_detail = _dn(name="DN-R1", qty=-60.0, is_return=1,
                        return_against="DN-1", warehouse="WH-B")
        explicit = _dn(name="DN-R2", qty=-60.0, is_return=1,
                       return_against="DN-1", dn_detail="row-a", warehouse="WH-B")
        explicit2 = _dn(name="DN-R3", qty=-60.0, is_return=1,
                        return_against="DN-1", dn_detail="row-a", warehouse="WH-B")
        for ordered in ([no_detail, explicit], [explicit, no_detail],
                        [explicit, explicit2], [explicit2, explicit]):
            stages = self.facts.build_stage_balances(_line(), _ctx(dns=base + ordered))
            returned = sorted(r["qty"] for r in stages
                              if r["stage"] == self.facts.STAGE_RETURNED)
            self.assertEqual(returned, [20.0, 100.0])
            self.assertFalse([r for r in stages
                              if r["stage"] == self.facts.STAGE_IN_TRANSIT])
            self.assertAlmostEqual(
                sum(r["qty"] for r in stages if r["qty"] is not None
                    and r["stage"] not in (self.facts.STAGE_RETURNED,
                                           self.facts.STAGE_DRAFT)), 100.0)

    def test_missing_detail_on_aggregated_multi_detail_group_is_unattributed(self):
        group = _dn(qty=100.0, warehouse="WH-A",
                    dn_items=["row-a", "row-b"],
                    item_qty={"row-a": 40.0, "row-b": 60.0})
        ret = _dn(name="DN-R", qty=-10.0, is_return=1,
                  return_against="DN-1", warehouse="WH-B")
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=[group, ret]))
        transit = [r for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual([r["qty"] for r in transit], [100.0])
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(returned[0]["qty"], 10.0)
        self.assertIn("归属", returned[0]["exclusion_reason"])
        self.assertFalse([r for r in stages
                          if r["stage"] == self.facts.STAGE_UNKNOWN and r["qty"] is not None])
        explicit = _dn(name="DN-R2", qty=-50.0, is_return=1,
                       return_against="DN-1", dn_detail="row-a", warehouse="WH-B")
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=[group, explicit]))
        transit = [r["qty"] for r in stages if r["stage"] == self.facts.STAGE_IN_TRANSIT]
        self.assertEqual(transit, [60.0])
        returned = sorted(r["qty"] for r in stages
                          if r["stage"] == self.facts.STAGE_RETURNED)
        self.assertEqual(returned, [10.0, 40.0])

    def test_include_delivered_surfaces_delivered_lines(self):
        self.fake.so_rows = [types.SimpleNamespace(so="SO-1", so_line="A")]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 1
        lines, _, _total = self.facts.load_lines({})
        self.assertIn("soi.qty - soi.delivered_qty", self.fake.last_query)
        self.assertEqual([row.so_line for row in lines], ["A"])
        lines, _, _total = self.facts.load_lines({"include_delivered": 1})
        self.assertNotIn("soi.qty - soi.delivered_qty", self.fake.last_query)
        self.assertEqual([row.so_line for row in lines], ["A"])

    def _row(self, index=1, so="SO-1"):
        return types.SimpleNamespace(
            so=so, so_line="SOI-%d" % index, item_code="SKU-1", item_name="Item",
            customer_item_code="", qty=10.0, delivered_qty=0.0, uom="个",
            warehouse="WH-1", delivery_date="2026-10-20",
            so_status="To Deliver and Bill", so_docstatus=1,
            transaction_date="2026-10-01", fba_sku="",
            customer="C1", customer_name="Cust")

    def test_unknown_filter_and_top_level_param_are_rejected(self):
        with self.assertRaises(ValueError):
            self.facts._normalize_filters({"sales_ordr": "SO-1"})
        with self.assertRaises(ValueError):
            self.facts._normalize_filters(None, {"sales_order": "SO-1"})
        with self.assertRaises(ValueError):
            self.facts._normalize_filters({"stage": "no_such_stage"})
        allowed = self.facts._normalize_filters(
            {"sales_order": "SO-1"},
            {"cmd": "key_test.supply_facts.get_supply_facts",
             "csrf_token": "x", "_": "123"})
        self.assertEqual(allowed["sales_order"], "SO-1")
        normalized = self.facts._normalize_filters({"stage": "in_production"})
        self.assertEqual(normalized["stage"], "in_production")
        self.assertEqual(normalized["limit"], self.facts.DEFAULT_LIMIT)

    def test_frappe_injected_cmd_and_offset_beyond_last_page(self):
        self.fake.so_rows = [self._row(1)]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 1
        result = self.facts.get_supply_facts(
            filters={"sales_order": "SO-1", "limit": 1, "offset": 10},
            cmd="key_test.supply_facts.get_supply_facts", csrf_token="x")
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["pagination"]["returned"], 0)
        self.assertTrue(result["pagination"]["exhausted"])
        self.assertEqual(result["manifest"]["coverage"]["empty_reason"],
                         "offset_out_of_range")
        self.assertEqual(result["applied_filters"], {"sales_order": "SO-1"})
        self.assertEqual(result["manifest"]["scope"]["offset"], 10)

    def test_single_sales_order_and_so_line_scope(self):
        self.fake.so_rows = [self._row(1, "SO-1"), self._row(2, "SO-2")]
        self.fake.permitted_sos = ["SO-1", "SO-2"]
        self.fake.total_sos = 2
        lines, _, total = self.facts.load_lines({"sales_order": "SO-1", "limit": 10})
        self.assertEqual([row.so_line for row in lines], ["SOI-1"])
        self.assertEqual(total, 1)
        lines, _, total = self.facts.load_lines({"so_line": "SOI-2", "limit": 10})
        self.assertEqual([row.so for row in lines], ["SO-2"])
        self.assertEqual(total, 1)

    def test_two_pages_do_not_duplicate_or_miss(self):
        self.fake.so_rows = [self._row(i) for i in range(1, 6)]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 1
        first, _, total = self.facts.load_lines({"limit": 2, "offset": 0})
        self.assertIn("order by so.name, soi.name", self.fake.last_query)
        second, _, _ = self.facts.load_lines({"limit": 2, "offset": 2})
        third, _, _ = self.facts.load_lines({"limit": 2, "offset": 4})
        self.assertEqual([r.so_line for r in first], ["SOI-1", "SOI-2"])
        self.assertEqual([r.so_line for r in second], ["SOI-3", "SOI-4"])
        self.assertEqual([r.so_line for r in third], ["SOI-5"])
        self.assertEqual(total, 5)
        self.assertEqual(len({r.so_line for r in first + second + third}), 5)

    def test_pagination_metadata_distinguishes_page_from_business_partial(self):
        page = self.facts._pagination({"limit": 2, "offset": 0}, 2, 5, "SOI-2")
        self.assertFalse(page["exhausted"])
        self.assertTrue(page["partial"])
        self.assertEqual(page["next_offset"], 2)
        self.assertEqual(page["termination_reason"], "page_limit")
        last = self.facts._pagination({"limit": 2, "offset": 4}, 1, 5, "SOI-5")
        self.assertTrue(last["exhausted"])
        self.assertFalse(last["partial"])
        self.assertIsNone(last["next_offset"])

    def test_endpoint_echoes_scope_and_pagination(self):
        self.fake.so_rows = [self._row(1)]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 1
        result = self.facts.get_supply_facts(filters={"sales_order": "SO-1", "limit": 1})
        self.assertEqual(result["applied_filters"], {"sales_order": "SO-1"})
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertTrue(result["pagination"]["exhausted"])
        self.assertEqual(result["manifest"]["scope"]["sales_order"], "SO-1")
        self.assertEqual(result["manifest"]["pagination"], result["pagination"])
        self.assertTrue(result["manifest"]["partial"])
        self.assertEqual(result["manifest"]["termination_reason"], "exhausted")

    def _dispatch_support(self):
        path = Path(__file__).with_name("dispatch_support.py")
        spec = importlib.util.spec_from_file_location("zmt_dispatch_support", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_dispatch_guard_skips_only_missing_frappe(self):
        module = self._dispatch_support()

        def missing_frappe(name, *args, **kwargs):
            if name == "frappe":
                raise ModuleNotFoundError("No module named 'frappe'", name="frappe")
            raise AssertionError("business import must not run when frappe is missing")

        self.assertEqual(module._load_dispatch_deps(missing_frappe), (None, None))

    def test_dispatch_guard_does_not_hide_business_import_error(self):
        module = self._dispatch_support()

        def broken_business(name, *args, **kwargs):
            if name == "frappe":
                return types.SimpleNamespace()
            if name == "key_test.supply_facts":
                raise ModuleNotFoundError(
                    "No module named 'key_test.supply_facts'",
                    name="key_test.supply_facts")
            return __import__(name, *args, **kwargs)

        with self.assertRaises(ModuleNotFoundError):
            module._load_dispatch_deps(broken_business)

    def test_popup_request_includes_delivered_lines(self):
        here = Path(__file__).resolve()
        candidates = [
            here.parents[1] / "public" / "js" / "sales_order.js",
            here.parent / "key_test__sales_order_chain_append.js",
        ]
        target = next((path for path in candidates if path.exists()), None)
        self.assertIsNotNone(target, "未找到销售订单 JS")
        text = target.read_text(encoding="utf-8")
        start = text.index("get_supply_facts")
        self.assertIn("include_delivered", text[start:start + 400])

    def test_plan_unit_mismatch_blocks_coverage_allocation(self):
        pp = {"pp": "PP-1", "ppi": "PPI-1", "item_code": "SKU-1",
              "planned_qty": 2.0, "stock_uom": "箱", "pp_date": "2026-10-01"}
        stages = self.facts.build_stage_balances(_line(), _ctx(pps=[pp]))
        by_stage = {r["stage"]: r for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN]["qty"], 100.0)
        self.assertIn("单位", by_stage[self.facts.STAGE_UNKNOWN]["exclusion_reason"])
        self.assertNotIn(self.facts.STAGE_NOT_PLANNED, by_stage)
        stages = self.facts.build_stage_balances(
            _line(), _ctx(pps=[pp], wos=[_wo(qty=40.0, produced=0.0)]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_IN_PRODUCTION], 40.0)
        self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN], 60.0)
        self.assertNotIn(self.facts.STAGE_NOT_PLANNED, by_stage)

    def test_line_facts_carries_production_evidence(self):
        fact = self.facts.build_line_facts(_line(), _ctx(wos=[_wo()], dns=[_dn()]))
        self.assertEqual(fact["production_evidence"]["all_process_done"]["qty_proven"], 60.0)
        self.assertEqual(fact["production_evidence"]["stock_in_posted"]["qty_proven"], 60.0)

    def test_stock_entry_query_failure_is_not_empty_success(self):
        with mock.patch.object(self.facts.frappe.db, "sql",
                               side_effect=RuntimeError("boom")):
            grouped, status = self.facts.load_stock_entries(["WO-1"])
        self.assertEqual(grouped, {})
        self.assertFalse(status["available"])
        self.assertEqual(status["reason"], "query_error")

    def test_stock_entry_permission_is_unavailable(self):
        with mock.patch.object(self.facts.frappe, "has_permission", return_value=False):
            grouped, status = self.facts.load_stock_entries(["WO-1"])
        self.assertEqual(grouped, {})
        self.assertFalse(status["available"])
        self.assertEqual(status["reason"], "permission")

    def test_quality_inspection_query_failure_is_not_empty_success(self):
        with mock.patch.object(self.facts.frappe.db, "sql",
                               side_effect=RuntimeError("boom")):
            grouped, status = self.facts.load_quality_inspections({"JC-1": "WO-1"}, {})
        self.assertEqual(grouped, {})
        self.assertFalse(status["available"])
        self.assertEqual(status["reason"], "query_error")

    def test_implementation_version_bumped_for_interface_change(self):
        self.assertEqual(self.facts.IMPLEMENTATION_VERSION,
                         "key_test.supply_facts@2026-10-30.4")

    def test_manifest_carries_rule_and_implementation_versions(self):
        self.fake.so_rows = []
        self.fake.permitted_sos = []
        self.fake.total_sos = 0
        result = self.facts.get_supply_facts({})
        self.assertEqual(result["manifest"]["rule_version"], self.facts.RULE_VERSION)
        self.assertEqual(result["manifest"]["implementation_version"],
                         self.facts.IMPLEMENTATION_VERSION)
        self.assertEqual(result["implementation_version"], self.facts.IMPLEMENTATION_VERSION)

    def test_dispatch_milestones_split_quantity_and_date_per_dn(self):
        ctx = _ctx(dns=[_dn("DN-1", qty=20.0, date="2026-10-01"),
                        _dn("DN-2", qty=80.0, date="2026-10-10")])
        rows = [r for r in self.facts.build_milestones(_line(), ctx)
                if r["node"] == "dispatch"]
        self.assertEqual(sorted((r["actual_at"], r["qty"]) for r in rows),
                         [("2026-10-01", 20.0), ("2026-10-10", 80.0)])
        self.assertTrue(all(r["qty_status"] == "known" for r in rows))
        self.assertTrue(all(r["source_record"] for r in rows))

    def test_signed_single_shipment_enters_pending_receipt(self):
        fact = self.facts.build_line_facts(
            _line(), _ctx(
                dns=[_dn(qty=100.0)],
                numbers_by_dn={"DN-1": [{"number": "A"}]},
                shipment_by_number={"A": _ship("A", "已签收",
                                               dlvr="2026-10-20")}))
        signed = [r for r in fact["stage_balances"]
                  if r["stage"] == self.facts.STAGE_SIGNED_PENDING]
        self.assertEqual(sum(r["qty"] for r in signed), 100.0)
        row = fact["shipment_progress"][0]
        self.assertTrue(row["is_final"])
        self.assertEqual(row["shipment_signed_at"], "2026-10-20")
        self.assertEqual(row["status_semantics"], "unproven")
        self.assertEqual(row["receipt_completion"], "unknown")
        self.assertIsNone(row["received_qty"])
        self.assertEqual(row["receipt_basis"], "signed_assumed")
        self.assertEqual(row["receipt_source_status"], "not_integrated")
        self.assertEqual(row["inventory_inclusion_status"], "unknown")

    def test_multi_signed_shipments_do_not_copy_dn_qty_to_each(self):
        fact = self.facts.build_line_facts(
            _line(), _ctx(
                dns=[_dn(qty=100.0)],
                numbers_by_dn={"DN-1": [{"number": "A"}, {"number": "B"}]},
                shipment_by_number={
                    "A": _ship("A", "已签收", dlvr="2026-10-20"),
                    "B": _ship("B", "已上传POD", dlvr="2026-10-21")}))
        signed = [r for r in fact["stage_balances"]
                  if r["stage"] == self.facts.STAGE_SIGNED_PENDING]
        self.assertEqual(sum(r["qty"] for r in signed), 100.0)
        rows = fact["shipment_progress"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIsNone(row["received_qty"])
            self.assertIsNone(row["pending_qty"])
            self.assertEqual(row["receipt_completion"], "unknown")

    def test_shipment_progress_dedupes_rows_and_skips_returns(self):
        fact = self.facts.build_line_facts(
            _line(), _ctx(
                dns=[_dn(qty=60.0), _dn(qty=40.0, warehouse="WH-2"),
                     _dn(qty=10.0, is_return=1)],
                numbers_by_dn={"DN-1": [{"number": "A"}, {"number": "A"}]},
                shipment_by_number={"A": _ship("A", "已离港")}))
        rows = fact["shipment_progress"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dn"], "DN-1")
        self.assertEqual(rows[0]["logistic_number"], "A")

    def test_eta_only_is_unknown_not_in_transit(self):
        fact = self.facts.build_line_facts(
            _line(), _ctx(
                dns=[_dn(qty=100.0)],
                numbers_by_dn={"DN-1": [{"number": "A"}]},
                shipment_by_number={"A": _ship("A", "", eta="2026-11-18",
                                               atd=None, status4="")}))
        stages = fact["stage_balances"]
        self.assertEqual(sum(r["qty"] for r in stages
                             if r["stage"] == self.facts.STAGE_UNKNOWN), 100.0)
        self.assertFalse([r for r in stages
                          if r["stage"] == self.facts.STAGE_IN_TRANSIT])
        self.assertEqual(fact["shipment_progress"][0]["stage"], "unknown")

    def test_signed_without_dlvr_keeps_signed_at_null(self):
        fact = self.facts.build_line_facts(
            _line(), _ctx(
                dns=[_dn(qty=100.0)],
                numbers_by_dn={"DN-1": [{"number": "A"}]},
                shipment_by_number={"A": _ship("A", "已签收",
                                               ata="2026-10-20")}))
        row = fact["shipment_progress"][0]
        self.assertTrue(row["is_final"])
        self.assertIsNone(row["shipment_signed_at"])

    def test_duplicate_waybill_identity_is_not_last_write_wins(self):
        self.fake.number_rows = [
            _AttrDict(dn="DN-1", number="ZMT1", is_primary=1)]
        self.fake.shipment_rows = [
            _AttrDict(shipment="SHIP-1", number="ZMT1", status11="已离港",
                      status4="在途", eta=None, atd="2026-10-20", ata=None,
                      dlvr=None, match_status="", modified="2026-10-29"),
            _AttrDict(shipment="SHIP-2", number="ZMT1", status11="已签收",
                      status4="签收", eta=None, atd=None, ata="2026-10-22",
                      dlvr="2026-10-23", match_status="", modified="2026-10-29")]
        self.fake.permitted_shipments = ["SHIP-1", "SHIP-2"]
        try:
            numbers, shipments, restricted, event_status = \
                self.facts.load_shipments(["DN-1"])
            self.assertFalse(restricted)
            self.assertTrue(event_status["available"])
            self.assertEqual(numbers["DN-1"][0]["number"], "ZMT1")
            row = shipments["ZMT1"]
            self.assertTrue(row["identity_conflict"])
            self.assertIsNone(row["shipment"])
            self.assertEqual(sorted(row["shipment_candidates"]),
                             ["SHIP-1", "SHIP-2"])
            self.assertEqual(row["progress"]["conflict_reasons"],
                             ["shipment_identity_conflict"])
            self.assertIsNone(row["progress"]["latest_progress_status"])
            raw = {c["raw_status"] for c in row["progress"]["progress_candidates"]}
            self.assertTrue({"已离港", "已签收"} <= raw)
        finally:
            self.fake.number_rows = []
            self.fake.shipment_rows = []
            self.fake.permitted_shipments = []

    def test_loaded_logistics_events_feed_progress(self):
        self.fake.number_rows = [
            _AttrDict(dn="DN-1", number="ZMT1", is_primary=1)]
        self.fake.shipment_rows = [
            _AttrDict(shipment="SHIP-1", number="ZMT1", status11="",
                      status4="", eta=None, atd=None, ata=None, dlvr=None,
                      match_status="", modified="2026-10-29")]
        self.fake.permitted_shipments = ["SHIP-1"]
        self.fake.event_rows = [
            types.SimpleNamespace(parent="SHIP-1", seq=1,
                                  event_time="2026-10-20 10:00",
                                  event_name="到港", event_date="2026-10-20",
                                  location="", description="已到港")]
        try:
            _, shipments, _, _ = self.facts.load_shipments(["DN-1"])
            progress = shipments["ZMT1"]["progress"]
            self.assertEqual(progress["latest_progress_status"], "已到港")
        finally:
            self.fake.number_rows = []
            self.fake.shipment_rows = []
            self.fake.permitted_shipments = []
            self.fake.event_rows = []

    def test_event_query_failure_is_not_silent_empty(self):
        self.fake.number_rows = [
            _AttrDict(dn="DN-1", number="ZMT1", is_primary=1)]
        self.fake.shipment_rows = [
            _AttrDict(shipment="SHIP-1", number="ZMT1", status11="已离港",
                      status4="在途", eta=None, atd="2026-10-20", ata=None,
                      dlvr=None, match_status="", modified="2026-10-29")]
        self.fake.permitted_shipments = ["SHIP-1"]
        try:
            for error, reason in ((RuntimeError("event query boom"), "query_error"),
                                  (PermissionError("no event read"), "permission")):
                self.fake.event_error = error
                _, shipments, _, event_status = self.facts.load_shipments(["DN-1"])
                self.assertFalse(event_status["available"])
                self.assertEqual(event_status["reason"], reason)
                self.assertTrue(event_status["error"])
                self.assertIn("progress", shipments["ZMT1"])
        finally:
            self.fake.number_rows = []
            self.fake.shipment_rows = []
            self.fake.permitted_shipments = []
            self.fake.event_error = None

    def test_event_query_failure_marks_supply_facts_partial(self):
        self.fake.so_rows = [self._row(1)]
        self.fake.permitted_sos = ["SO-1"]
        self.fake.total_sos = 1
        self.fake.dn_rows = [_AttrDict(
            dn="DN-1", date="2026-10-16", status="", docstatus=1, is_return=0,
            return_against=None, tongtool_po=None, so_line="SOI-1",
            dn_item="DNI-1", dn_detail=None, qty=10.0, uom="个",
            warehouse="WH-1")]
        self.fake.permitted_dns = ["DN-1"]
        self.fake.number_rows = [
            _AttrDict(dn="DN-1", number="ZMT1", is_primary=1)]
        self.fake.shipment_rows = [
            _AttrDict(shipment="SHIP-1", number="ZMT1", status11="已离港",
                      status4="在途", eta=None, atd="2026-10-20", ata=None,
                      dlvr=None, match_status="", modified="2026-10-29")]
        self.fake.permitted_shipments = ["SHIP-1"]
        self.fake.event_error = RuntimeError("event boom")
        try:
            result = self.facts.get_supply_facts({"sales_order": "SO-1"})
            status = result["source_status"]["shipment_logistics_event"]
            self.assertFalse(status["available"])
            self.assertEqual(status["reason"], "query_error")
            self.assertTrue(result["manifest"]["partial"])
            self.assertIn("shipment logistics event source unavailable: query_error",
                          result["manifest"]["notes"])
        finally:
            self.fake.so_rows = []
            self.fake.permitted_sos = []
            self.fake.total_sos = 0
            self.fake.dn_rows = []
            self.fake.permitted_dns = []
            self.fake.number_rows = []
            self.fake.shipment_rows = []
            self.fake.permitted_shipments = []
            self.fake.event_error = None

    def test_conflicting_progress_is_unknown_and_keeps_candidates(self):
        progress = {"latest_progress_status": None, "latest_progress_at": None,
                    "progress_source": None, "is_final": False,
                    "conflict_flag": True,
                    "conflict_reasons": ["same_time_conflict"],
                    "progress_candidates": [{"raw_status": "已到港"},
                                            {"raw_status": "清关中"}]}
        shipment = {"shipment": "SHIP-1", "status11": "已到港", "eta": None,
                    "atd": None, "ata": None, "dlvr": None,
                    "progress": progress}
        fact = self.facts.build_line_facts(
            _line(), _ctx(
                dns=[_dn(qty=100.0)],
                numbers_by_dn={"DN-1": [{"number": "A"}]},
                shipment_by_number={"A": shipment}))
        unknown = [r for r in fact["stage_balances"]
                   if r["stage"] == self.facts.STAGE_UNKNOWN]
        self.assertEqual(sum(r["qty"] for r in unknown), 100.0)
        row = fact["shipment_progress"][0]
        self.assertTrue(row["conflict_flag"])
        self.assertEqual(len(row["progress_candidates"]), 2)

    def test_receipt_and_inventory_are_reported_not_integrated(self):
        result = self.facts.get_supply_facts({})
        self.assertEqual(result["source_status"]["receipt"]["reason"],
                         "not_integrated")
        self.assertEqual(result["source_status"]["inventory"]["reason"],
                         "not_integrated")
        self.assertEqual(result["manifest"]["coverage"]["external_sources"]["inventory"],
                         "not_integrated")

    def test_wo_without_start_evidence_is_unknown_not_in_production(self):
        for docstatus in (0, 1):
            wo = _wo(qty=100.0, produced=0.0, docstatus=docstatus,
                     jc_start=None, jc_end=None)
            stages = self.facts.build_stage_balances(_line(), _ctx(wos=[wo]))
            by_stage = {r["stage"]: r for r in stages if r["qty"] is not None}
            self.assertNotIn(self.facts.STAGE_IN_PRODUCTION, by_stage)
            self.assertEqual(by_stage[self.facts.STAGE_UNKNOWN]["qty"], 100.0)
            self.assertIn("开工", by_stage[self.facts.STAGE_UNKNOWN]["exclusion_reason"])
            self.assertNotIn(self.facts.STAGE_NOT_PLANNED, by_stage)
        started = _wo(qty=100.0, produced=0.0, docstatus=0)
        stages = self.facts.build_stage_balances(_line(), _ctx(wos=[started]))
        self.assertEqual(sum(r["qty"] for r in stages
                             if r["stage"] == self.facts.STAGE_IN_PRODUCTION), 100.0)

    def test_over_production_keeps_source_and_records_excess(self):
        wo = _wo(qty=150.0, produced=150.0)
        ctx = _ctx(wos=[wo])
        stages = self.facts.build_stage_balances(_line(), ctx)
        by_stage = {r["stage"]: r for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_PRODUCED_PENDING]["qty"], 100.0)
        excess = by_stage[self.facts.STAGE_OVER_PRODUCED]
        self.assertEqual(excess["qty"], 50.0)
        self.assertEqual(excess["cumulative_excess_qty"], 50.0)
        self.assertEqual(excess["demand_status"], "excess")
        self.assertIn("150", excess["stage_detail"])
        self.assertAlmostEqual(self._sum_executed(stages), 100.0)
        tranches = self.facts.build_availability(_line(), ctx, stages)
        self.assertFalse([t for t in tranches
                          if t["stage"] == self.facts.STAGE_OVER_PRODUCED])
        miles = self.facts.build_milestones(_line(), ctx)
        start = next(r for r in miles if r["node"] == "production_start")
        end = next(r for r in miles if r["node"] == "production_end")
        self.assertEqual(start["qty"], 150.0)
        self.assertEqual(end["qty"], 150.0)
        self.assertIn("订单", end["note"])

    def test_over_produced_current_balance_excludes_shipped(self):
        ctx = _ctx(wos=[_wo(qty=150.0, produced=150.0)], dns=[_dn(qty=120.0)])
        stages = self.facts.build_stage_balances(_line(), ctx)
        over = next(r for r in stages if r["stage"] == self.facts.STAGE_OVER_PRODUCED)
        self.assertEqual(over["qty"], 30.0)
        self.assertEqual(over["cumulative_excess_qty"], 50.0)
        self.assertEqual(over["demand_status"], "excess")
        self.assertIn("150", over["stage_detail"])
        self.assertIn("50", over["stage_detail"])
        self.assertFalse([t for t in self.facts.build_availability(_line(), ctx, stages)
                          if t["stage"] == self.facts.STAGE_OVER_PRODUCED])

    def test_cancelled_order_still_records_over_production(self):
        stages = self.facts.build_stage_balances(
            _line(so_docstatus=2), _ctx(wos=[_wo(qty=150.0, produced=150.0)]))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_OVER_PRODUCED], 50.0)
        self.assertEqual(by_stage[self.facts.STAGE_CANCELLED], 100.0)

    def test_over_return_keeps_original_and_flags_excess(self):
        dns = [_dn(qty=20.0),
               _dn(name="DN-R", qty=-30.0, is_return=1, return_against="DN-1")]
        stages = self.facts.build_stage_balances(_line(), _ctx(dns=dns))
        returned = [r for r in stages if r["stage"] == self.facts.STAGE_RETURNED]
        self.assertEqual(sorted(r["qty"] for r in returned), [10.0, 20.0])
        excess = next(r for r in returned if r["qty"] == 10.0)
        self.assertIn("超退", excess["exclusion_reason"])
        matched = next(r for r in returned if r["qty"] == 20.0)
        self.assertIn("抵扣", matched["exclusion_reason"])
        self.assertFalse([r for r in stages
                          if r["stage"] == self.facts.STAGE_IN_TRANSIT])
        self.assertAlmostEqual(sum(r["qty"] for r in stages if r["qty"] is not None
                                   and r["stage"] not in (self.facts.STAGE_RETURNED,
                                                          self.facts.STAGE_DRAFT)), 100.0)

    def test_case8_rebuild_is_stable_and_partial_is_explicit(self):
        ctx = _ctx(wos=[_wo()], dns=[_dn()])
        first = self.facts.build_line_facts(_line(), ctx)
        second = self.facts.build_line_facts(_line(), ctx)
        for key in ("stage_balances", "milestones", "availability_schedule", "links"):
            self.assertEqual(first[key], second[key])
        self.assertAlmostEqual(self._sum_executed(first["stage_balances"]), 100.0)
        unknown = self.facts.build_stage_balances(_line(), _ctx(dn_permission=False))
        self.assertEqual(unknown[0]["stage"], self.facts.STAGE_UNKNOWN)
        self.assertEqual(unknown[0]["qty"], 100.0)


def _evidence_dict(**overrides):
    base = {
        "qty_proven": None, "qty_estimated": None, "confidence": "unknown",
        "reasons": [], "conflicts": [], "source_records": [],
        "started_at": None, "completed_at": None, "time_status": "not_applicable",
        "components": {},
    }
    base.update(overrides)
    return base


def _line_evidence(**classes):
    evidence = {
        "work_orders": [], "wo_count": 0,
        "first_process_done": _evidence_dict(),
        "all_process_done": _evidence_dict(),
        "qc_performed": _evidence_dict(),
        "qc_passed": _evidence_dict(),
        "stock_in_posted": _evidence_dict(),
        "conflicts": [], "source_records": [], "subassemblies": [],
    }
    evidence.update(classes)
    return evidence


class ThirdBatchRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SupplyFactsContractTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        SupplyFactsContractTest.tearDownClass.__func__(cls)

    def test_estimated_milestone_is_not_known_and_has_no_actual(self):
        evidence = _line_evidence(
            first_process_done=_evidence_dict(
                qty_estimated=60.0, confidence="estimated",
                started_at="2026-10-03 08:00:00", completed_at="2026-10-03 09:00:00",
                time_status="complete"),
            all_process_done=_evidence_dict(
                qty_estimated=60.0, confidence="estimated",
                started_at="2026-10-03 08:00:00", completed_at="2026-10-14 17:00:00",
                time_status="complete"),
        )
        rows = self.facts.build_milestones(
            _line(), _ctx(wos=[_wo()], evidence=evidence))
        end = next(r for r in rows if r["node"] == "production_end")
        start = next(r for r in rows if r["node"] == "production_start")
        for row in (start, end):
            self.assertIsNone(row["qty"])
            self.assertNotEqual(row["qty_status"], "known")
            self.assertIsNone(row["actual_at"])
            self.assertIn("估算", row["note"])

    def test_unknown_confidence_hides_proven_quantity(self):
        evidence = _line_evidence(
            all_process_done=_evidence_dict(
                qty_proven=100.0, confidence="unknown", reasons=["conflict"]),
        )
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=[_wo(qty=100.0)], evidence=evidence))
        self.assertNotIn(self.facts.STAGE_PRODUCED_PENDING,
                         {r["stage"] for r in stages})
        unknown = next(r for r in stages if r["stage"] == self.facts.STAGE_UNKNOWN)
        self.assertEqual(unknown["qty"], 100.0)

    def test_cancelled_wo_does_not_count_in_coverage(self):
        wos = [_wo(name="WO-1", qty=40.0, produced=0.0),
               _wo(name="WO-X", qty=60.0, produced=0.0, docstatus=2)]
        evidence = _line_evidence(
            all_process_done=_evidence_dict(qty_proven=0.0, confidence="proven"),
            first_process_done=_evidence_dict(qty_proven=0.0, confidence="proven"),
            stock_in_posted=_evidence_dict(qty_proven=0.0, confidence="proven"),
        )
        stages = self.facts.build_stage_balances(
            _line(), _ctx(wos=wos, evidence=evidence))
        by_stage = {r["stage"]: r["qty"] for r in stages if r["qty"] is not None}
        self.assertEqual(by_stage[self.facts.STAGE_IN_PRODUCTION], 40.0)
        self.assertEqual(by_stage[self.facts.STAGE_NOT_PLANNED], 60.0)
        self.assertNotIn(self.facts.STAGE_UNKNOWN, by_stage)

    def test_cancelled_wo_stock_fact_reaches_stage_balances(self):
        evidence = _line_evidence(
            all_process_done=_evidence_dict(qty_proven=0.0, confidence="proven"),
            first_process_done=_evidence_dict(qty_proven=0.0, confidence="proven"),
            stock_in_posted=_evidence_dict(
                qty_proven=12.0, confidence="proven",
                components={"gross_qty": 12.0, "return_qty": 0.0,
                            "net_qty": 12.0, "unallocated_return_qty": 0.0}),
        )
        stages = self.facts.build_stage_balances(
            _line(qty=10.0), _ctx(wos=[_wo(qty=10.0, docstatus=2)],
                                 evidence=evidence))
        over = next(r for r in stages
                    if r["stage"] == self.facts.STAGE_OVER_PRODUCED)
        self.assertEqual(over["qty"], 2.0)


if __name__ == "__main__":
    unittest.main()
