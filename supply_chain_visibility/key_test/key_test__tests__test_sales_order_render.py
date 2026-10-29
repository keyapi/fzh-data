# -*- coding: utf-8 -*-
"""Node/DOM smoke tests for the supply-chain human view (no jsdom)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[1]
HARNESS = Path(__file__).resolve().parent / "js" / "render_harness.js"
JS_PRIMARY = ROOT / "public" / "js" / "sales_order.js"
JS_MIRROR = ROOT / "key_test__sales_order_chain_append.js"


def _js_path():
    if JS_PRIMARY.exists():
        return JS_PRIMARY
    return JS_MIRROR


def _line(**overrides):
    line = {
        "so_line": "SOI-1", "item_code": "KS0001", "item_name": "成品",
        "customer_item_code": "C-1", "qty": 10.0, "delivered": 0.0,
        "open_qty": 10.0, "reported": 10.0, "instock": 10.0,
        "all_process_estimated": None, "instock_estimated": None,
        "reported_status": "known", "instock_status": "known",
        "reported_confidence": "proven", "instock_confidence": "proven",
        "qc_status": "known", "qc_passed_status": "Accepted",
        "stage": 3, "substate": "全工序完成待出库", "delivery_date": "2026-10-30",
        "overdue_days": 0, "wo_count": 1, "tn_count": 1, "prog": None,
        "work_orders": [], "forgot_complete": [], "dns": [],
        "subassemblies": [], "evidence_reasons": [], "evidence_conflicts": [],
    }
    line.update(overrides)
    return line


def _render_doc(lines):
    if not NODE:
        raise unittest.SkipTest("node not available")
    payload = json.dumps({"sales_order": "SO-1", "lines": lines}, ensure_ascii=False)
    proc = subprocess.run(
        [NODE, str(HARNESS), str(_js_path())],
        input=payload, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node harness failed: %s" % proc.stderr[-800:])
    return json.loads(proc.stdout)


def render(lines):
    return _render_doc(lines)["html"]


class SalesOrderRenderTest(unittest.TestCase):
    def test_unknown_instock_is_dash_and_not_flagged(self):
        html = render([_line(instock=None, instock_status="unknown")])
        self.assertIn("—", html)
        self.assertNotIn("background:#fff9e6", html)

    def test_unknown_reported_is_not_treated_as_complete(self):
        html = render([_line(reported=None, reported_status="unknown",
                             instock=None, instock_status="unknown")])
        self.assertNotIn("background:#fff9e6", html)

    def test_estimated_is_labelled(self):
        html = render([_line(reported=None, all_process_estimated=10.0,
                             reported_confidence="estimated",
                             reported_status="estimated",
                             instock=10.0, instock_status="known")])
        self.assertIn("10（估算）", html)
        self.assertNotIn("background:#fff9e6", html)

    def test_estimated_subassembly_shows_estimated_quantity(self):
        sub = {
            "wo": "WO-PK", "production_item": "PK#KS0001", "qty": 10.0,
            "uom": "个", "docstatus": 1, "wo_cancelled": False,
            "all_process_done": {"qty_proven": None, "qty_estimated": 10.0,
                                 "qty_status": "estimated",
                                 "confidence": "estimated"},
            "stock_in_posted": {"qty_proven": None, "qty_estimated": None,
                                "qty_status": "unknown",
                                "confidence": "unknown"},
        }
        html = _render_doc([_line(subassemblies=[sub])])["tree"]
        self.assertIn("10（估算）", html)
        self.assertIn("PK#KS0001", html)

    def test_both_known_mismatch_is_flagged(self):
        html = render([_line(reported=10.0, instock=8.0,
                             reported_status="known", instock_status="known")])
        self.assertIn("background:#fff9e6", html)

    def test_qc_and_confidence_are_visible(self):
        html = render([_line()])
        self.assertIn("QC", html)
        self.assertIn("Accepted", html)
        self.assertIn("known", html)

    def test_restricted_identity_is_not_rendered(self):
        html = render([_line(subassemblies=[], evidence_conflicts=["permission"])])
        self.assertNotIn("HIDDEN-DOC", html)
        self.assertIn("permission", html)


if __name__ == "__main__":
    unittest.main()
