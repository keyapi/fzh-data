import sys
import unittest
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import w1_supply_timeline as w1  # noqa: E402


class PureLogicTest(unittest.TestCase):
    def test_po_remaining(self):
        self.assertEqual(w1.po_remaining({"quantity": 10, "in_quantity": 3}), 7)
        self.assertEqual(w1.po_remaining({"quantity": 10, "in_quantity": 12}), 0)

    def test_wo_progress_first_op(self):
        wo = {"qty": 10, "produced_qty": 0,
              "operations": [{"operation": "cut", "sequence_id": 1},
                             {"operation": "sew", "sequence_id": 2}]}
        jcs = [
            {"operation": "cut", "status": "Completed", "total_completed_qty": 4},
            {"operation": "sew", "status": "Completed", "total_completed_qty": 4},
        ]
        done, src, prog = w1.wo_progress(wo, jcs)
        self.assertEqual((done, src), (4, "jc_first_op"))

    def test_wo_progress_fallback_produced(self):
        wo = {"qty": 10, "produced_qty": 3, "operations": []}
        done, src, _ = w1.wo_progress(wo, [])
        self.assertEqual((done, src), (3, "wo_produced_qty"))

    def test_role_of(self):
        role, parent, conf = w1.role_of("PK#KS1", {})
        self.assertEqual((role, conf), ("cover", "derived"))
        role, _, _ = w1.role_of("KS1", {})
        self.assertEqual(role, "finished")
        role, _, _ = w1.role_of("ND#X", {})
        self.assertEqual(role, "component")

    def test_make_row_booleans_and_nulls(self):
        r = w1.make_row(sku="S", qty=None, qty_status="unknown", counted=True,
                        available_date="", event_date="", tracking_numbers=["A"])
        self.assertIsNone(r["qty"])
        self.assertIsNone(r["available_date"])
        self.assertEqual(r["counted"], 1)
        self.assertEqual(r["tracking_numbers"], ["A"])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "version": "test", "as_of": "2026-10-23",
            "slots": [{
                "slot": "S1", "sku": "S1", "status": "filled",
                "items": [{"item_code": "KS1", "role": "finished", "identity_confidence": "derived"}],
                "production_items": [{"item_code": "PK#KS1", "role": "cover", "identity_confidence": "derived"}],
            }],
        }
        self.wmap = {
            "version": "v",
            "warehouses": [
                {"name": "美东-CENTRADE", "warehouse_id": "1", "scope": "in_house",
                 "warehouse_scope": "3pl", "warehouse_confidence": "confirmed",
                 "warehouse_map_source": "x", "en_finished": "成品 - 美东USNJ"},
                {"name": "美中-FZH-DANEEY", "warehouse_id": "2", "scope": "in_house",
                 "warehouse_scope": "3pl", "warehouse_confidence": "confirmed",
                 "warehouse_map_source": "x", "en_finished": "成品 - 美中USTX"},
            ],
            "external_fba": {"warehouse": "美国FBA仓", "scope": "external_fba",
                             "warehouse_scope": "fba", "warehouse_confidence": "confirmed"},
            "fzh": {"warehouse": "FZH", "warehouse_scope": "own",
                    "warehouse_confidence": "assumed", "en_finished": "成品 - FZH"},
        }
        self.args = Namespace(as_of="2026-10-23", since="2025-01-01", trace_since="2026-08-01")

    def build(self, **overrides):
        data = dict(
            stock=[{"goodsSku": "S1", "warehouseName": "美东-CENTRADE",
                    "availableStockQuantity": 10, "intransitStockQuantity": 5,
                    "waitingShipmentStockQuantity": 2, "defectsStockQuantity": 1}],
            pos=[{"goods_sku": "S1", "status": "0", "quantity": 5, "in_quantity": 0,
                  "warehouseName": "美东-CENTRADE", "PONum": "PO1",
                  "purchaseDate": "2026-10-01 10:00", "willArriveDate": None}],
            so_lines=[{"sku": "S1", "item_code": "KS1", "so": "SO1", "line_id": "SL1",
                       "qty": 10, "delivered_qty": 3, "uom": "个",
                       "delivery_date": "2026-11-01", "so_status": "To Deliver and Bill",
                       "warehouse": "FZH"}],
            wos=[{"name": "WO1", "production_item": "PK#KS1", "qty": 10, "produced_qty": 4,
                  "planned_end_date": None, "status": "Not Started", "operations": [],
                  "stock_uom": "个"}],
            jcs=[],
            dn_lines=[
                {"dn": "DN1", "line_id": "L1", "item_code": "KS1", "qty": 5, "uom": "个",
                 "customer": "CENTRADE", "numbers": ["A", "B"], "posting_date": "2026-10-10",
                 "dn_status": "Submitted", "shipment": None},
                {"dn": "DN2", "line_id": "L2", "item_code": "KS1", "qty": 5, "uom": "个",
                 "customer": "CENTRADE", "numbers": ["C"], "posting_date": "2026-10-11",
                 "dn_status": "Submitted", "shipment": None},
                {"dn": "DN3", "line_id": "L3", "item_code": "KS1", "qty": 5, "uom": "个",
                 "customer": "CENTRADE", "numbers": ["D", "E"], "posting_date": "2026-10-12",
                 "dn_status": "Submitted", "shipment": None},
                {"dn": "DN4", "line_id": "L4", "item_code": "KS1", "qty": 5, "uom": "个",
                 "customer": "美国FBA仓", "numbers": ["F"], "posting_date": "2026-10-13",
                 "dn_status": "Submitted", "shipment": None},
            ],
            shipments={
                "A": {"name": "SHIPA", "custom_zmt_status11": "已签收", "custom_zmt_dlvr": "2026-10-20"},
                "B": {"name": "SHIPB", "custom_zmt_status11": "已签收", "custom_zmt_dlvr": "2026-10-20"},
                "C": {"name": "SHIPC", "custom_zmt_status11": "已离港", "custom_zmt_eta": None},
                "D": {"name": "SHIPD", "custom_zmt_status11": "已签收", "custom_zmt_dlvr": "2026-10-21"},
                "E": {"name": "SHIPE", "custom_zmt_status11": "已离港", "custom_zmt_eta": "2026-11-01"},
                "F": {"name": "SHIPF", "custom_zmt_status11": "已签收", "custom_zmt_dlvr": "2026-10-22"},
            },
            receipts=[],
        )
        data.update(overrides)
        return w1.build(self.cfg, self.wmap, self.args, **data)

    def test_overlap_two_ledgers(self):
        supply, *_ = self.build()
        po = [r for r in supply if r["ledger"] == "po"][0]
        transit = [r for r in supply if r["ledger"] == "stock_intransit"][0]
        self.assertEqual(po["overlap_status"], "same_batch_suspected")
        self.assertEqual(transit["overlap_status"], "same_batch_suspected")
        self.assertEqual(po["counted"], 0)
        self.assertEqual(transit["counted"], 1)

    def test_unknown_stock_not_listed(self):
        supply, *_ = self.build()
        missing = [r for r in supply if r["warehouse"] == "美中-FZH-DANEEY"
                   and r["stage"] == "on_hand"][0]
        self.assertIsNone(missing["qty"])
        self.assertEqual(missing["qty_status"], "unknown")

    def test_production_estimated_cover(self):
        supply, *_ = self.build()
        prod = [r for r in supply if r["stage"] == "in_production"][0]
        self.assertEqual(prod["qty"], 6)
        self.assertEqual(prod["qty_status"], "estimated")
        self.assertEqual(prod["role"], "cover")
        self.assertEqual(prod["parent_sku"], "S1")
        self.assertIsNone(prod["available_date"])
        self.assertEqual(prod["date_confidence"], "unknown")

    def test_jc_does_not_change_remaining(self):
        supply, *_ = self.build(jcs=[{"work_order": "WO1", "operation": "cut",
                                      "status": "Completed", "total_completed_qty": 10}])
        prod = [r for r in supply if r["stage"] == "in_production"][0]
        self.assertEqual(prod["qty"], 6)
        self.assertIn("jc_max_op=10.000", prod["production_progress"])

    def test_one_dn_multi_tracking_one_row(self):
        supply, *_ = self.build()
        received = [r for r in supply if r["stage"] == "received" and r["doc_name"] == "DN1"][0]
        self.assertEqual(len(received["tracking_numbers"]), 2)
        self.assertIsNone(received["qty"])
        self.assertEqual(received["qty_status"], "unknown")
        self.assertEqual(received["received_evidenced"], 1)

    def test_partial_and_fba(self):
        supply, demand, excluded, exceptions = self.build()
        self.assertEqual(len([r for r in exceptions if r["stage"] == "partially_received"]), 1)
        fba = [r for r in supply if r["scope"] == "external_fba"][0]
        self.assertEqual(fba["stage"], "received")

    def test_demand_and_defects_separate(self):
        supply, demand, excluded, exceptions = self.build()
        self.assertEqual(len(demand), 1)
        self.assertEqual(demand[0]["stage"], "so_unfulfilled")
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["notes"], "defects; not supply")


if __name__ == "__main__":
    unittest.main()
