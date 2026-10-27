from decimal import Decimal
import unittest

from supply_chain_visibility.supply_row import SupplyRow, require_valid, to_dict, validate_supply_row


def row(**changes):
    values = {
        "sku": "S1", "warehouse": "WH-A", "stage": "on_hand",
        "source_layer": "inventory_snapshot", "qty": Decimal("5"),
        "qty_status": "known", "uom": "Nos", "uom_proven": True,
        "event_date": "2026-10-14", "available_date": "2026-10-14",
        "date_confidence": "confirmed", "timezone_status": "verified",
        "identity_confidence": "proven",
    }
    values.update(changes)
    return SupplyRow(**values)


class SupplyRowTests(unittest.TestCase):
    def test_valid_row(self):
        self.assertEqual(validate_supply_row(row()), [])
        self.assertEqual(to_dict(row())["qty"], "5")

    def test_unknown_quantity_cannot_be_zero_or_counted(self):
        self.assertIn("qty=null requires qty_status=unknown",
                      validate_supply_row(row(qty=None, qty_status="known")))
        self.assertIn("qty_status=unknown requires qty=null",
                      validate_supply_row(row(qty=Decimal("0"), qty_status="unknown")))
        self.assertIn("unknown quantity cannot enter B_min/B_max",
                      validate_supply_row(row(qty=None, qty_status="unknown", b_min_eligible=True)))

    def test_unknown_date_cannot_be_available(self):
        self.assertIn("date_confidence=unknown requires available_date=null",
                      validate_supply_row(row(date_confidence="unknown", available_date="2026-10-14")))

    def test_not_collected_and_unknown_uom_cannot_enter_bmin(self):
        self.assertIn("not_collected rows cannot enter B_min/B_max",
                      validate_supply_row(row(not_collected=True, b_max_eligible=True)))
        self.assertIn("B_min requires a proven UOM",
                      validate_supply_row(row(uom_proven=False, b_min_eligible=True)))

    def test_external_fba_unmapped_and_cover_gates(self):
        self.assertIn("external_fba rows cannot enter B_min/B_max",
                      validate_supply_row(row(scope="external_fba", b_max_eligible=True)))
        self.assertIn("unmapped rows cannot enter B_min/B_max",
                      validate_supply_row(row(warehouse_confidence="unmapped", b_max_eligible=True)))
        self.assertIn("cover conversion is unproven; cannot enter B_min",
                      validate_supply_row(row(role="cover", b_min_eligible=True)))

    def test_require_valid_raises(self):
        with self.assertRaises(ValueError):
            require_valid(row(stage="bogus"))


if __name__ == "__main__":
    unittest.main()
