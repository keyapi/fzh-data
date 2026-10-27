"""Acceptance tests for the supply facts contract (pure builders)."""
import importlib.util
import sys
import types
from pathlib import Path
import unittest


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.PermissionError = PermissionError
        self.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        self._dict = lambda value=None: types.SimpleNamespace(**dict(value or {}))
        self.db = types.SimpleNamespace(
            sql=lambda *a, **k: [], has_column=lambda *a, **k: True,
            table_exists=lambda *a, **k: True)

    def has_permission(self, doctype, ptype, doc=None):
        return True

    def throw(self, message, exc=None):
        raise (exc or Exception)(message)

    def get_all(self, *args, **kwargs):
        return []


def _line(**overrides):
    line = {"so": "SO-1", "so_line": "SOI-1", "item_code": "SKU-1", "uom": "个",
            "qty": 100.0, "delivered_qty": 25.0, "warehouse": "WH-1",
            "so_docstatus": 1, "so_status": "To Deliver and Bill",
            "transaction_date": "2026-10-01", "delivery_date": "2026-10-20",
            "scope": "in_house", "role": "finished"}
    line.update(overrides)
    return line


def _ctx(**overrides):
    ctx = {"pps": [], "wos": [], "dns": [], "numbers_by_dn": {}, "shipment_by_number": {},
           "dn_permission": True, "shipment_permission": True, "work_order_permission": True,
           "observed_at": "2026-10-27T10:00:00"}
    ctx.update(overrides)
    return ctx


def _wo(name="WO-1", qty=100.0, produced=60.0, **overrides):
    wo = {"wo": name, "qty": qty, "produced": produced, "status": "In Process",
          "item_code": "SKU-1",
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


def _ship(number="ZMT1", status="已离港", eta="2026-11-01", atd="2026-10-17",
          ata=None, dlvr=None):
    return {"shipment": "SHIP-1", "number": number, "status11": status, "status4": "在途",
            "eta": eta, "atd": atd, "ata": ata, "dlvr": dlvr, "match_status": "Matched"}


class SupplyFactsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = {name: sys.modules.get(name)
                     for name in ("frappe", "frappe.utils", "key_test", "key_test.supply_query")}
        fake = FakeFrappe()
        sys.modules["frappe"] = fake
        sys.modules["frappe.utils"] = types.SimpleNamespace(
            getdate=lambda x: x, today=lambda: "2026-10-27",
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
        stages = self.facts.build_stage_balances(_line(so_docstatus=2), _ctx(dns=[_dn()]))
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0]["stage"], self.facts.STAGE_CANCELLED)
        self.assertEqual(stages[0]["qty"], 100.0)
        self.assertIn("实物另列", stages[0]["exclusion_reason"])

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


if __name__ == "__main__":
    unittest.main()
