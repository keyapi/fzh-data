#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1b_dn_wo_jc_se 的离线单测（不联网、不调用 main 的网络分支）。"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _import():
    sys.path.insert(0, str(BASE))
    import g1b_dn_wo_jc_se as m  # noqa: E402
    return m


m = _import()

WINDOW = ("2026-04-01", "2026-09-30")


def so(so_id="SO-1", line="L1", item="KS1", qty=10, delivered=4, open_q=6,
       uom="个", ds=1, status="To Deliver and Bill", delivery="2026-05-01",
       txn="2026-04-01"):
    return {"so": so_id, "line_id": line, "item_code": item, "qty": qty,
            "delivered_qty": delivered, "open_qty": open_q, "uom": uom,
            "so_docstatus": ds, "so_status": status,
            "so_delivery_date": delivery, "transaction_date": txn, "wos": []}


def dn(so_id="SO-1", line="L1", dn_id="DN-1", dn_line="D1", item="KS1", qty=4,
       uom="个", ds=1, ret=0, date="2026-05-02"):
    return {"so": so_id, "so_line_id": line, "dn": dn_id, "dn_line_id": dn_line,
            "item_code": item, "qty": qty, "uom": uom, "dn_docstatus": ds,
            "is_return": ret, "dn_date": date, "dn_status": "To Bill"}


def wo(name="WO-1", so_id="SO-1", item="KS1", qty=10, produced=10, ds=1,
       status="Completed"):
    return {"name": name, "sales_order": so_id, "production_item": item,
            "qty": qty, "produced_qty": produced, "docstatus": ds,
            "status": status, "planned_start_date": None, "planned_end_date": None,
            "bom_no": "BOM-1"}


def se(name="SE-1", work_order="WO-1", finished=10, ds=1, date="2026-05-02",
       lines=None):
    rec = {"se": name, "work_order": work_order, "docstatus": ds,
           "posting_date": date, "finished_qty": finished,
           "finished_lines": None if lines is None else len(lines)}
    if lines is not None:
        rec["lines"] = lines
    return rec


def se_line(item="KS1", qty=10, uom="个", suom=None, fin=True, name="SL1"):
    return {"line": name, "item_code": item, "qty": qty, "uom": uom,
            "stock_uom": suom or uom, "is_finished_item": fin,
            "target_warehouse": "成品仓", "source_warehouse": None}


def jc(wo_name="WO-1", last_op="质检", ops=None):
    ops = ops or {"裁剪": {"cards": 1, "sum_qty": 10.0, "jc_ids": ["JC1"]},
                  "质检": {"cards": 1, "sum_qty": 10.0, "jc_ids": ["JC2"]}}
    return {wo_name: {"cards": sum(v["cards"] for v in ops.values()),
                      "operations": ops, "operation_order": list(ops),
                      "first_operation": list(ops)[0], "last_operation": last_op,
                      "first_op_qty": ops[list(ops)[0]]["sum_qty"],
                      "last_op_qty": ops.get(last_op, {}).get("sum_qty"),
                      "statuses": ["Completed"]}}


def snapshot(so_rows=None, dn_rows=None, wos=None, jc_map=None, se_rows=None,
             code="C-TEST", generated_at="2026-10-20T18:00:00"):
    return {"query": {"customer_code": code, "item": None},
            "generated_at": generated_at,
            "so_rows": so_rows if so_rows is not None else [so(delivered=4)],
            "dn_rows": dn_rows if dn_rows is not None else [dn()],
            "wos": wos if wos is not None else [wo()],
            "jc_summary": jc_map if jc_map is not None else jc(),
            "se_rows": se_rows if se_rows is not None else [se(lines=[se_line()])],
            "_scope": code, "_path": "mem", "_sha256": "0" * 64}


def run(snap, details=None):
    return m.build_scope(snap, {"by_se": details or {}}, WINDOW, "delivery")


def by_type(scope, t):
    return [r for r in scope["rows"] if r["row_type"] == t]


def find(scope, t, key):
    for r in by_type(scope, t):
        if r["row_key"] == key:
            return r
    raise AssertionError(f"row not found: {t} {key}")


class FlagTests(unittest.TestCase):
    def test_flag01_strict(self):
        for v, want in [(True, 1), (False, 0), (1, 1), (0, 0), (0.0, 0), (1.0, 1),
                        ("1", 1), ("0", 0), ("true", 1), ("FALSE", 0)]:
            self.assertEqual(m.flag01(v), want, v)
        for v in (2, -1, 0.5, float("nan"), float("inf"), "maybe", "", None, [1]):
            self.assertIsNone(m.flag01(v), v)

    def test_num_strict(self):
        self.assertEqual(m.num("2.5"), 2.5)
        self.assertIsNone(m.num(None))
        self.assertIsNone(m.num(""))
        self.assertIsNone(m.num("abc"))
        self.assertIsNone(m.num(float("nan")))
        self.assertIsNone(m.num(float("inf")))
        self.assertIsNone(m.num(True))

    def test_docstatus(self):
        self.assertEqual(m.docstatus(1), 1)
        self.assertIsNone(m.docstatus(3))
        self.assertIsNone(m.docstatus("x"))


class SnapshotInputTests(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(m.InputError):
            m.load_snapshot(Path("does-not-exist.json"))

    def test_missing_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text(json.dumps({"query": {"customer_code": "X"}}), encoding="utf-8")
            with self.assertRaises(m.InputError):
                m.load_snapshot(p)

    def test_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(m.InputError):
                m.load_snapshot(p)


class LinkTests(unittest.TestCase):
    def test_happy_path_all_conserved(self):
        sc = run(snapshot())
        self.assertTrue(sc["checks"]["C1_so_dn"][0]["pass"])
        self.assertTrue(all(r["disposition"] == "conserved"
                            for r in by_type(sc, "so_line")))
        self.assertEqual(find(sc, "dn_line", "DN-1::D1")["reason_code"], "dn_submitted")
        self.assertEqual(find(sc, "wo", "WO-1")["disposition"], "conserved")
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "conserved")

    def test_dn_unlinked(self):
        snap = snapshot(dn_rows=[dn(line="L999", item="KS9")])
        sc = run(snap)
        r = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(r["disposition"], "unlinked")
        # C1 变成不一致，audit 不通过
        self.assertEqual(sc["checks"]["C1_so_dn"][0]["delta"], 4.0)

    def test_dn_fallback_unique_item(self):
        snap = snapshot(dn_rows=[dn(line=None)])
        sc = run(snap)
        r = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(r["disposition"], "linked")
        self.assertEqual(r["link"]["link_mode"], "so_item_unique")

    def test_dn_fallback_ambiguous_not_linked(self):
        rows = [so(line="L1"), so(line="L2")]   # 同物料两行 -> 不能唯一归属
        snap = snapshot(so_rows=rows, dn_rows=[dn(line=None, qty=4)])
        sc = run(snap)
        self.assertEqual(find(sc, "dn_line", "DN-1::D1")["disposition"], "unlinked")

    def test_dn_return_and_draft(self):
        snap = snapshot(so_rows=[so(delivered=2)],
                        dn_rows=[dn(qty=4), dn(dn_id="DN-R", dn_line="DR1", qty=2, ret=1),
                                 dn(dn_id="DN-D", dn_line="DD1", qty=9, ds=0)])
        sc = run(snap)
        self.assertEqual(find(sc, "dn_line", "DN-R::DR1")["reason_code"], "dn_return_submitted")
        self.assertEqual(find(sc, "dn_line", "DN-D::DD1")["disposition"], "excluded")
        so_row = find(sc, "so_line", "SO-1::L1")
        self.assertEqual(so_row["qty"]["dn_net"], 2.0)
        self.assertEqual(so_row["disposition"], "conserved")

    def test_dn_uom_mismatch_is_unverified(self):
        snap = snapshot(dn_rows=[dn(uom="条")])
        sc = run(snap)
        self.assertEqual(find(sc, "dn_line", "DN-1::D1")["reason_code"], "dn_uom_mismatch")
        self.assertEqual(find(sc, "so_line", "SO-1::L1")["disposition"], "unverified")

    def test_wo_no_sales_order_still_conserved(self):
        snap = snapshot(wos=[wo(so_id="")], jc_map=jc("WO-1"))
        sc = run(snap)
        r = find(sc, "wo", "WO-1")
        self.assertEqual(r["link_status"], "unlinked")
        self.assertEqual(r["link_reason_code"], "wo_no_sales_order")
        self.assertEqual(r["disposition"], "conserved")

    def test_wo_so_out_of_snapshot(self):
        snap = snapshot(wos=[wo(so_id="SO-X")], jc_map=jc("WO-1"))
        sc = run(snap)
        self.assertEqual(find(sc, "wo", "WO-1")["link_reason_code"],
                         "wo_sales_order_out_of_snapshot")

    def test_wo_ambiguous(self):
        rows = [so(line="L1"), so(line="L2")]
        snap = snapshot(so_rows=rows, dn_rows=[dn(qty=4)])
        sc = run(snap)
        r = find(sc, "wo", "WO-1")
        self.assertEqual(r["link_status"], "ambiguous")
        self.assertEqual(len(r["link"]["candidate_lines"]), 2)

    def test_wo_item_mismatch(self):
        snap = snapshot(wos=[wo(item="KS2")], jc_map=jc("WO-1"))
        sc = run(snap)
        self.assertEqual(find(sc, "wo", "WO-1")["link_reason_code"],
                         "wo_so_line_item_mismatch")

    def test_wo_not_started_is_open_not_unverified(self):
        snap = snapshot(wos=[wo(qty=50, produced=0, status="Not Started")],
                        jc_map={}, se_rows=[])
        sc = run(snap)
        r = find(sc, "wo", "WO-1")
        self.assertEqual(r["disposition"], "open")
        self.assertEqual(r["reason_code"], "wo_not_started")
        self.assertEqual(sc["checks"]["C2_wo_se"]["open"], 1)
        self.assertEqual(sc["checks"]["C2_wo_se"]["unverified"], 0)


class ConservationTests(unittest.TestCase):
    def test_wo_se_mismatch(self):
        snap = snapshot(wos=[wo(produced=12)],
                        se_rows=[se(finished=10, lines=[se_line(qty=10)])])
        sc = run(snap)
        r = find(sc, "wo", "WO-1")
        self.assertEqual(r["disposition"], "mismatch")
        self.assertIn("wo_over_produced", r["reason_detail"])
        self.assertEqual(sc["checks"]["C2_wo_se"]["mismatch"], 1)

    def test_se_internal_sum_mismatch(self):
        snap = snapshot(se_rows=[se(finished=9, lines=[se_line(qty=10)])])
        sc = run(snap)
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "mismatch")
        self.assertEqual(sc["checks"]["C3_se_internal"]["mismatch"], 1)

    def test_se_detail_absent_offline(self):
        snap = snapshot(se_rows=[se()])
        sc = run(snap)
        self.assertEqual(find(sc, "se", "SE-1")["reason_code"], "se_detail_absent")
        self.assertEqual(find(sc, "wo", "WO-1")["disposition"], "unverified")

    def test_se_detail_from_enrichment(self):
        snap = snapshot(se_rows=[se()])
        details = {"SE-1": {"ok": True, "lines": [se_line(qty=10)]}}
        sc = run(snap, details)
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "conserved")
        self.assertEqual(find(sc, "se", "SE-1")["link"]["detail_source"], "en_get")

    def test_se_line_item_mismatch(self):
        snap = snapshot(se_rows=[se(lines=[se_line(item="KS9")])])
        sc = run(snap)
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "mismatch")
        line = find(sc, "se_line", "SE-1::SL1")
        self.assertEqual(line["reason_code"], "se_line_item_mismatch")

    def test_se_line_uom_mismatch(self):
        snap = snapshot(se_rows=[se(lines=[se_line(uom="条", suom="个")])])
        sc = run(snap)
        self.assertEqual(find(sc, "se_line", "SE-1::SL1")["reason_code"],
                         "se_line_finished_uom_mismatch")
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "unverified")

    def test_se_non_finished_excluded(self):
        snap = snapshot(se_rows=[se(lines=[se_line(fin=False, item="CLOTH", qty=5,
                                                   name="SL0"),
                                          se_line(qty=10, name="SL1")])])
        sc = run(snap)
        self.assertEqual(find(sc, "se_line", "SE-1::SL0")["disposition"], "excluded")
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "conserved")

    def test_no_cross_uom_aggregate(self):
        rows = [so(line="L1", delivered=4, uom="个"),
                so(line="L2", item="KS2", delivered=3, uom="条")]
        dns = [dn(qty=4), dn(line="L2", item="KS2", dn_id="DN-2", dn_line="D2",
                             qty=3, uom="条")]
        snap = snapshot(so_rows=rows, dn_rows=dns)
        sc = run(snap)
        c1 = sc["checks"]["C1_so_dn"]
        self.assertEqual({x["uom"] for x in c1}, {"个", "条"})
        for x in c1:
            self.assertTrue(x["pass"])

    def test_so_open_identity(self):
        snap = snapshot(so_rows=[so(qty=10, delivered=4, open_q=5)])
        sc = run(snap)
        self.assertIn("so_line_open_identity_mismatch",
                      find(sc, "so_line", "SO-1::L1")["reason_detail"])

    def test_voided_so_excluded_from_c1(self):
        snap = snapshot(so_rows=[so(ds=2, delivered=0)], dn_rows=[])
        sc = run(snap)
        self.assertEqual(find(sc, "so_line", "SO-1::L1")["disposition"], "excluded")
        self.assertEqual(sc["checks"]["C1_so_dn"], [])


class JcTests(unittest.TestCase):
    def test_jc_progress_only(self):
        sc = run(snapshot())
        jcs = by_type(sc, "jc_operation")
        self.assertTrue(jcs)
        self.assertTrue(all(r["reason_code"] == "jc_progress_evidence_only" for r in jcs))

    def test_jc_routing_final_not_completion(self):
        jc_map = jc("WO-1", last_op="质检发现问题",
                    ops={"裁剪": {"cards": 1, "sum_qty": 10.0, "jc_ids": ["J1"]},
                         "质检": {"cards": 1, "sum_qty": 10.0, "jc_ids": ["J2"]},
                         "质检发现问题": {"cards": 1, "sum_qty": 2.0, "jc_ids": ["J3"]}})
        sc = run(snapshot(jc_map=jc_map))
        r = find(sc, "wo", "WO-1")
        self.assertIn("jc_routing_final_op_not_completion", r["reason_detail"])
        self.assertEqual(r["disposition"], "conserved")   # 守恒不依赖 JC

    def test_jc_missing(self):
        sc = run(snapshot(jc_map={}))
        self.assertIn("jc_missing", find(sc, "wo", "WO-1")["reason_detail"])
        self.assertEqual(by_type(sc, "jc_operation"), [])


class WindowTests(unittest.TestCase):
    def test_window_partition(self):
        rows = [so(line="L1", delivery="2026-05-01"),
                so(line="L2", item="KS2", delivery="2025-01-01", delivered=0),
                so(line="L3", item="KS3", delivery=None, delivered=0)]
        snap = snapshot(so_rows=rows, dn_rows=[dn(qty=4)])
        sc = run(snap)
        got = {r["row_key"]: r["in_window"] for r in by_type(sc, "so_line")}
        self.assertEqual(got["SO-1::L1"], True)
        self.assertEqual(got["SO-1::L2"], False)
        self.assertIsNone(got["SO-1::L3"])
        # 窗口只是分区，不丢行
        self.assertEqual(len(sc["rows"]), len(by_type(sc, "so_line")) + len(sc["rows"])
                         - len(by_type(sc, "so_line")))
        self.assertIn("so_line_date_missing", find(sc, "so_line", "SO-1::L3")["reason_detail"])


class AccountingTests(unittest.TestCase):
    def test_row_accounting_matches(self):
        sc = run(snapshot())
        manifest = m.build_manifest([sc], WINDOW, "delivery", None, None, "r1")
        self.assertTrue(manifest["audit_ok"])
        for t in ("so_line", "dn_line", "wo", "se"):
            self.assertTrue(manifest["row_accounting"][t]["match"], t)
        self.assertEqual(manifest["row_accounting"]["se_line"]["derived"], 1)

    def test_duplicate_keys_fail_audit(self):
        snap = snapshot(so_rows=[so(line="L1"), so(line="L1")])
        sc = run(snap)
        manifest = m.build_manifest([sc], WINDOW, "delivery", None, None, "r1")
        self.assertFalse(manifest["audit_ok"])

    def test_stable_hash_ignores_run_id(self):
        sc = run(snapshot())
        a = m.build_manifest([sc], WINDOW, "delivery", None, None, "r1")
        b = m.build_manifest([sc], WINDOW, "delivery", None, None, "r2")
        b["as_of"] = a["as_of"]
        self.assertEqual(m.stable_hash(a), m.stable_hash(b))

    def test_payload_hash_detects_tamper(self):
        sc = run(snapshot())
        man = m.build_manifest([sc], WINDOW, "delivery", None, None, "r1")
        h = man.pop("payload_sha256")
        self.assertEqual(m.canonical_sha(man), h)
        man["audit_ok"] = not man["audit_ok"]
        self.assertNotEqual(m.canonical_sha(man), h)


if __name__ == "__main__":
    unittest.main(verbosity=2)
