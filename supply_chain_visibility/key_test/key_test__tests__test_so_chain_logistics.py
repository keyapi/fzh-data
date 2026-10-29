"""Contract tests for the first-leg logistics dialog service."""
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
        self.db = types.SimpleNamespace(
            sql=self.sql, has_column=lambda doctype, field: True, table_exists=lambda name: True)
        self.queries = []
        self.get_list_calls = []
        self.get_all_calls = []
        self.docs = {}
        self.dn_rows = []
        self.number_rows = []
        self.shipment_rows = []
        self.event_rows = []
        self.permitted = {"Delivery Note": None, "Shipment": None}
        self.readable = {}
        self.PermissionError = PermissionError
        self._ = lambda value: value
        self._dict = lambda value=None: _AttrDict(value or {})
        self.whitelist = lambda *args, **kwargs: (lambda fn: fn)

    def get_doc(self, doctype, name):
        return self.docs[(doctype, name)]

    def has_permission(self, doctype, ptype, doc=None):
        return self.readable.get(doctype, True)

    def throw(self, message, exc=None):
        raise (exc or Exception)(message)

    def get_list(self, doctype, filters=None, or_filters=None, fields=None, limit_page_length=20):
        self.get_list_calls.append(doctype)
        allowed = self.permitted.get(doctype)
        if allowed is None:
            return []
        return [_AttrDict(name=name) for name in allowed]

    def get_all(self, doctype, filters=None, fields=None, order_by=None):
        self.get_all_calls.append((doctype, filters, fields, order_by))
        return list(self.event_rows)

    def sql(self, query, values=None, as_dict=False):
        self.queries.append((query, values))
        if "ifnull(dn.is_return, 0) as is_return" in query:
            return list(self.dn_rows)
        if "from `tabDelivery Note Logistics Number`" in query:
            return list(self.number_rows)
        if "custom_zmt_logistic_number as number" in query:
            return list(self.shipment_rows)
        if "select name as dn, logistic_number as number" in query:
            return []
        return []


def _item(name, item_code="SKU-1", item_name="SKU one"):
    return types.SimpleNamespace(name=name, item_code=item_code, item_name=item_name)


class LogisticsDialogContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved_modules = {
            name: sys.modules.get(name)
            for name in ("frappe", "frappe.utils", "key_test", "key_test.supply_query",
                         "key_test.production_evidence", "key_test.supply_facts",
                         "key_test.so_chain")
        }
        cls.fake_frappe = FakeFrappe()
        sys.modules["frappe"] = cls.fake_frappe
        sys.modules["frappe.utils"] = types.SimpleNamespace(
            getdate=lambda x: x, today=lambda: "2026-10-27",
            now_datetime=lambda: "2026-10-27 10:00:00")
        root = Path(__file__).parents[1]
        service_path = root / "supply_query.py"
        chain_path = root / "so_chain.py"
        if not service_path.exists():
            service_path = root / "key_test" / "key_test__supply_query.py"
            chain_path = root / "key_test" / "key_test__so_chain.py"
        package = types.ModuleType("key_test")
        package.__path__ = []
        sys.modules["key_test"] = package
        spec = importlib.util.spec_from_file_location("key_test_u2_test_supply_query", service_path)
        cls.service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.service)
        sys.modules["key_test.supply_query"] = cls.service
        spec = importlib.util.spec_from_file_location(
            "key_test.production_evidence", root / "production_evidence.py")
        cls.evidence = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.evidence)
        sys.modules["key_test.production_evidence"] = cls.evidence
        spec = importlib.util.spec_from_file_location("key_test.supply_facts", root / "supply_facts.py")
        cls.facts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.facts)
        sys.modules["key_test.supply_facts"] = cls.facts
        chain_spec = importlib.util.spec_from_file_location("key_test_u2_test_so_chain", chain_path)
        cls.chain = importlib.util.module_from_spec(chain_spec)
        chain_spec.loader.exec_module(cls.chain)

    @classmethod
    def tearDownClass(cls):
        for name, module in cls.saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def setUp(self):
        self.fake_frappe.queries.clear()
        self.fake_frappe.get_list_calls.clear()
        self.fake_frappe.get_all_calls.clear()
        self.fake_frappe.readable = {}
        self.fake_frappe.permitted = {"Delivery Note": ["DN-1"], "Shipment": ["SHIP-1", "SHIP-2"]}
        self.fake_frappe.docs[("Sales Order", "SO-1")] = types.SimpleNamespace(
            name="SO-1", items=[_item("SOI-1"), _item("SOI-2", item_code="SKU-2")])
        self.fake_frappe.dn_rows = [types.SimpleNamespace(
            dn="DN-1", date="2026-10-01", status="To Bill", docstatus=1, is_return=0)]
        self.fake_frappe.number_rows = [
            types.SimpleNamespace(dn="DN-1", number="ZMT1", is_primary=1),
            types.SimpleNamespace(dn="DN-1", number="ZMT2", is_primary=0),
        ]
        self.fake_frappe.shipment_rows = [
            types.SimpleNamespace(name="SHIP-1", number="ZMT1", status4="在途", status11="已离港",
                                  last_node="2026-10-05", eta="2026-11-01", atd="2026-10-04",
                                  ata=None, dlvr=None, match_status="Matched", source="智美通"),
            types.SimpleNamespace(name="SHIP-2", number="ZMT2", status4="到港", status11="已到港",
                                  last_node="2026-10-20", eta="2026-10-18", atd="2026-10-04",
                                  ata="2026-10-19", dlvr=None, match_status="Matched", source="智美通"),
        ]
        self.fake_frappe.event_rows = [
            types.SimpleNamespace(parent="SHIP-1", seq=1, event_time="2026-10-04 10:00",
                                  event_name="", event_date="2026-10-04", location="", description="已离港"),
        ]

    def test_collects_numbers_shipments_and_events_in_one_pass(self):
        result = self.chain.get_so_line_logistics("SO-1", "SOI-1")
        self.assertEqual(len(result["dns"]), 1)
        numbers = result["dns"][0]["numbers"]
        self.assertEqual([n["number"] for n in numbers], ["ZMT1", "ZMT2"])
        self.assertEqual(numbers[0]["shipment"], "SHIP-1")
        self.assertEqual(numbers[0]["status11"], "已离港")
        self.assertEqual(numbers[0]["events"][0]["description"], "已离港")
        self.assertEqual(numbers[1]["events"], [])
        self.assertEqual(len(self.fake_frappe.get_all_calls), 1)
        self.assertTrue(result["permissions"]["shipment"])

    def test_unknown_line_is_rejected(self):
        with self.assertRaises(Exception):
            self.chain.get_so_line_logistics("SO-1", "SOI-9")

    def test_no_dn_permission_returns_flag_without_rows(self):
        self.fake_frappe.readable["Delivery Note"] = False
        result = self.chain.get_so_line_logistics("SO-1", "SOI-1")
        self.assertFalse(result["permissions"]["delivery_note"])
        self.assertEqual(result["dns"], [])

    def test_partial_dn_permission_fails_closed(self):
        self.fake_frappe.permitted["Delivery Note"] = []
        result = self.chain.get_so_line_logistics("SO-1", "SOI-1")
        self.assertFalse(result["permissions"]["delivery_note"])
        self.assertEqual(result["dns"], [])

    def test_no_shipment_permission_keeps_dn_list_with_flag(self):
        self.fake_frappe.readable["Shipment"] = False
        result = self.chain.get_so_line_logistics("SO-1", "SOI-1")
        self.assertFalse(result["permissions"]["shipment"])
        self.assertEqual(len(result["dns"]), 1)
        self.assertEqual(result["dns"][0]["numbers"][0]["shipment"], "")
        self.assertEqual(self.fake_frappe.get_all_calls, [])

    def test_no_dn_returns_empty(self):
        self.fake_frappe.dn_rows = []
        result = self.chain.get_so_line_logistics("SO-1", "SOI-1")
        self.assertEqual(result["dns"], [])
        self.assertTrue(result["permissions"]["delivery_note"])

    def test_completion_state_unknown_is_not_completed(self):
        evidence = {"all_process_done": {"qty_proven": None, "confidence": "unknown"},
                    "stock_in_posted": {"qty_proven": None, "confidence": "unknown"}}
        self.assertEqual(self.chain.completion_state(evidence, 10, False),
                         (False, "unknown"))
        self.assertEqual(self.chain.completion_state(evidence, 10, True),
                         (False, "unknown"))

    def test_completion_state_uses_all_process_or_stock(self):
        evidence = {"all_process_done": {"qty_proven": 10, "confidence": "proven"},
                    "stock_in_posted": {"qty_proven": 10, "confidence": "proven"}}
        self.assertEqual(self.chain.completion_state(evidence, 10, False),
                         (True, "complete"))
        self.assertEqual(self.chain.completion_state(evidence, 10, True),
                         (True, "complete"))
        self.assertEqual(self.chain.completion_state(evidence, 11, False),
                         (False, "partial"))


if __name__ == "__main__":
    unittest.main()
