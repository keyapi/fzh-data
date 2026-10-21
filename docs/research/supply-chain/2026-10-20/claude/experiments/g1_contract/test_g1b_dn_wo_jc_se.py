#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1b_dn_wo_jc_se 的离线单测（不联网；HTTP 预算用 mock 覆盖）。

回归覆盖 adapter review（2026-10-21）的 9 项发现：
  P1-1 逐行全精度 C1、P1-2 DN join 语义、P1-3 UOM 分区、P1-4 SE 父元数据、
  P1-5 SE 覆盖传播、P1-6 C4 原始输入/孤儿/子键唯一、P2-7 有符号退货、
  P2-8 请求级 HTTP 预算、P2-9 最终 payload 校验和。
并覆盖 v2 交叉复审（2026-10-21 FAIL）的 3 项发现：
  SE finished 量按 UOM 分桶、子行未解决向父 SE/WO 传播、匹配 JC 组非法工序显式披露。
并覆盖 v3 交叉复审（2026-10-21 FAIL，1 P2）的发现：
  JC 工序 payload 逐个校验（null/字符串/空对象/非法 sum_qty）→ 整组 invalid、无 progress。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def detail(se_name="SE-1", wo="WO-1", lines=None, ds=1, etype="Manufacture",
           posting="2026-05-02", fetched="2026-10-20T19:00:00+08:00"):
    """合法缓存明细：快照 generated_at=2026-10-20T18:00（本地），取回时间晚于它。"""
    return {"ok": True, "se": se_name, "docstatus": ds, "work_order": wo,
            "stock_entry_type": etype, "posting_date": posting,
            "fetched_at": fetched, "lines": [se_line()] if lines is None else lines}


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
             code="C-TEST", generated_at="2026-10-20T18:00:00", se_error=None):
    return {"query": {"customer_code": code, "item": None},
            "generated_at": generated_at,
            "so_rows": so_rows if so_rows is not None else [so(delivered=4)],
            "dn_rows": dn_rows if dn_rows is not None else [dn()],
            "wos": wos if wos is not None else [wo()],
            "jc_summary": jc_map if jc_map is not None else jc(),
            "se_rows": se_rows if se_rows is not None else [se(lines=[se_line()])],
            "se_query_error": se_error,
            "_scope": code, "_path": "mem", "_sha256": "0" * 64}


def run(snap, details=None):
    return m.build_scope(snap, {"by_se": details or {}}, WINDOW, "delivery")


def manifest(scopes_or_scope, **kw):
    scopes = scopes_or_scope if isinstance(scopes_or_scope, list) else [scopes_or_scope]
    return m.build_manifest(scopes, WINDOW, "delivery", kw.get("details"),
                            kw.get("probe"), kw.get("run_id", "r1"),
                            kw.get("budget"))


def final_manifest(scopes_or_scope, **kw):
    return m.finalize_manifest(manifest(scopes_or_scope, **kw))


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

    def test_uom_helpers(self):
        self.assertTrue(m.uom_known("个"))
        self.assertFalse(m.uom_known("  "))
        self.assertFalse(m.uom_known(None))
        self.assertEqual(m.uom_key(None), "unknown")


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

    def test_wrong_container_type(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            data = snapshot()
            data["se_rows"] = {"SE-1": {}}
            p.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(m.InputError):
                m.load_snapshot(p)


class LinkTests(unittest.TestCase):
    def test_happy_path_all_conserved(self):
        sc = run(snapshot())
        c1 = sc["checks"]["C1_so_dn"]
        self.assertTrue(c1["pass"])
        self.assertEqual(c1["lines_pass"], 1)
        self.assertEqual(c1["per_uom"][0]["pass"], True)
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
        c1 = sc["checks"]["C1_so_dn"]
        self.assertFalse(c1["pass"])
        self.assertEqual(c1["per_uom"][0]["delta"], 4.0)

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
        r = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(r["disposition"], "unlinked")
        self.assertEqual(r["reason_code"], "dn_item_ambiguous")

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
        self.assertEqual(sc["checks"]["C1_so_dn"]["lines_unresolved"], 1)

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


# ── P1-1：C1 逐行全精度，不允许抵消/四舍五入 ─────────────
class C1PerLinePrecisionTests(unittest.TestCase):
    def test_opposite_deltas_do_not_cancel(self):
        rows = [so(line="L1", delivered=4), so(line="L2", delivered=5)]
        dns = [dn(qty=4.005),
               dn(line="L2", dn_id="DN-2", dn_line="D2", qty=4.995)]
        sc = run(snapshot(so_rows=rows, dn_rows=dns))
        c1 = sc["checks"]["C1_so_dn"]
        self.assertFalse(c1["pass"])
        self.assertEqual(c1["lines_fail"], 2)
        self.assertEqual(c1["lines_pass"], 0)
        # 聚合 delta 正好抵消到 0，但逐行判定仍必须失败
        self.assertAlmostEqual(c1["per_uom"][0]["delta"], 0.0, places=9)
        self.assertFalse(c1["per_uom"][0]["pass"])
        for ln in sc["checks"]["C1_lines"]:
            self.assertFalse(ln["pass"])

    def test_rounding_does_not_hide_004(self):
        sc = run(snapshot(so_rows=[so(delivered=4.004)], dn_rows=[dn(qty=4)]))
        c1 = sc["checks"]["C1_so_dn"]
        self.assertFalse(c1["pass"])
        self.assertAlmostEqual(c1["per_uom"][0]["delta"], 0.004, places=9)
        self.assertEqual(round(c1["per_uom"][0]["delta"], 2), 0.0)
        line = sc["checks"]["C1_lines"][0]
        self.assertEqual(line["delivered"], 4.004)
        self.assertEqual(line["dn_net"], 4.0)

    def test_audit_requires_every_line(self):
        rows = [so(line="L1", delivered=4), so(line="L2", delivered=5)]
        dns = [dn(qty=4.005),
               dn(line="L2", dn_id="DN-2", dn_line="D2", qty=4.995)]
        man = final_manifest(run(snapshot(so_rows=rows, dn_rows=dns)))
        self.assertFalse(man["audit_ok"])
        self.assertEqual(man["coverage"]["c1"]["lines_fail"], 2)


# ── P1-2：DN join 只在显式引用缺失时回退；校验物料身份 ────
class DnJoinTests(unittest.TestCase):
    def test_missing_explicit_ref_does_not_fall_back(self):
        snap = snapshot(dn_rows=[dn(line="L999", item="KS1")])
        sc = run(snap)
        r = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(r["disposition"], "unlinked")
        self.assertEqual(r["reason_code"], "dn_so_line_ref_not_found")
        self.assertNotEqual(r.get("link", {}).get("link_mode"), "so_item_unique")

    def test_exact_ref_conflicting_item_is_mismatch(self):
        snap = snapshot(dn_rows=[dn(item="KS9", qty=4)])
        sc = run(snap)
        dn_row = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(dn_row["disposition"], "mismatch")
        self.assertEqual(dn_row["reason_code"], "dn_item_mismatch")
        so_row = find(sc, "so_line", "SO-1::L1")
        self.assertEqual(so_row["disposition"], "mismatch")
        self.assertEqual(so_row["reason_code"], "so_line_dn_item_mismatch")
        self.assertFalse(sc["checks"]["C1_so_dn"]["pass"])

    def test_exact_ref_matching_item_still_links(self):
        sc = run(snapshot())
        self.assertEqual(find(sc, "dn_line", "DN-1::D1")["link"]["link_mode"],
                         "so_line_id")

    def test_missing_item_blocks_fallback(self):
        snap = snapshot(dn_rows=[dn(line=None, item=None)])
        r = find(run(snap), "dn_line", "DN-1::D1")
        self.assertEqual(r["disposition"], "unlinked")
        self.assertEqual(r["reason_code"], "dn_item_missing")


# ── P1-3：所有数量聚合按 UOM 分区；未知/缺失 UOM 拒绝 ────
class UomPartitionTests(unittest.TestCase):
    def test_missing_dn_uom_rejected(self):
        sc = run(snapshot(dn_rows=[dn(uom=None)]))
        r = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(r["reason_code"], "dn_uom_missing")
        self.assertEqual(r["disposition"], "unverified")
        self.assertEqual(find(sc, "so_line", "SO-1::L1")["disposition"], "unverified")
        self.assertFalse(sc["checks"]["C1_so_dn"]["pass"])

    def test_missing_so_uom_rejected(self):
        sc = run(snapshot(so_rows=[so(uom=None, delivered=0)], dn_rows=[]))
        self.assertEqual(find(sc, "so_line", "SO-1::L1")["reason_code"],
                         "so_line_uom_missing")
        self.assertEqual(sc["checks"]["C1_so_dn"]["lines_unresolved"], 1)
        self.assertTrue(sc["checks"]["C1_so_dn"]["unresolved"])

    def test_se_mixed_finished_uom_not_summed(self):
        lines = [se_line(qty=5, uom="个", name="A"),
                 se_line(qty=5, uom="盒", name="B")]
        sc = run(snapshot(se_rows=[se(finished=10, lines=lines)]))
        r = find(sc, "se", "SE-1")
        self.assertEqual(r["disposition"], "unverified")
        self.assertEqual(r["reason_code"], "se_finished_uom_mixed")
        self.assertIsNone(r["qty"]["finished_lines_sum"])
        self.assertEqual(find(sc, "wo", "WO-1")["disposition"], "unverified")

    def test_c1_grouped_by_uom(self):
        rows = [so(line="L1", delivered=4, uom="个"),
                so(line="L2", item="KS2", delivered=3, uom="条")]
        dns = [dn(qty=4), dn(line="L2", item="KS2", dn_id="DN-2", dn_line="D2",
                             qty=3, uom="条")]
        sc = run(snapshot(so_rows=rows, dn_rows=dns))
        c1 = sc["checks"]["C1_so_dn"]
        self.assertTrue(c1["pass"])
        self.assertEqual({x["uom"] for x in c1["per_uom"]}, {"个", "条"})
        self.assertNotIn("so_delivered", c1)   # 顶层绝不出现跨 UOM 合计

    def test_window_summary_partitioned_by_uom(self):
        rows = [so(line="L1", delivered=4, uom="个"),
                so(line="L2", item="KS2", delivered=3, uom="条")]
        dns = [dn(qty=4), dn(line="L2", item="KS2", dn_id="DN-2", dn_line="D2",
                             qty=3, uom="条")]
        man = final_manifest(run(snapshot(so_rows=rows, dn_rows=dns)))
        inw = man["scopes"][0]["window"]["in_window"]
        self.assertEqual(set(inw["by_uom"]), {"个", "条"})
        self.assertNotIn("qty", inw)          # 没有跨单位总量字段
        self.assertEqual(inw["by_uom"]["个"]["qty"], 10.0)
        self.assertEqual(inw["by_uom"]["条"]["qty"], 10.0)

    def test_association_and_c2_partitioned_by_uom(self):
        rows = [so(line="L1", delivered=4, uom="个")]
        sc = run(snapshot(so_rows=rows, dn_rows=[dn(qty=4)]))
        self.assertEqual(sc["association"]["wo_qty_by_link_uom"]["linked"],
                         {"个": 10.0})
        self.assertIn("个", sc["checks"]["C2_wo_se"]["by_uom"])
        # 无 SO 的工单量进入 unknown，不与已知 UOM 混算
        sc2 = run(snapshot(wos=[wo(so_id="")], jc_map=jc("WO-1")))
        self.assertEqual(sc2["association"]["wo_qty_by_link_uom"]["wo_no_sales_order"],
                         {"unknown": 10.0})


# ── P1-4：合并缓存 SE 明细前校验父元数据/来源时间 ─────────
class SeMetadataTests(unittest.TestCase):
    def _run_with(self, **overrides):
        det = detail(**overrides)
        return run(snapshot(se_rows=[se()]), {"SE-1": det})

    def test_valid_cached_detail_conserved(self):
        sc = run(snapshot(se_rows=[se()]), {"SE-1": detail()})
        r = find(sc, "se", "SE-1")
        self.assertEqual(r["disposition"], "conserved")
        self.assertEqual(r["link"]["detail_source"], "en_get")

    def test_docstatus_drift(self):
        sc = self._run_with(ds=2)
        r = find(sc, "se", "SE-1")
        self.assertEqual(r["disposition"], "unverified")
        self.assertEqual(r["reason_code"], "se_detail_docstatus_drift")
        self.assertIn("se_detail_docstatus_drift", r["link"]["detail_problems"])

    def test_work_order_drift(self):
        sc = self._run_with(wo="WO-OTHER")
        r = find(sc, "se", "SE-1")
        self.assertEqual(r["reason_code"], "se_detail_work_order_drift")
        self.assertEqual(find(sc, "wo", "WO-1")["disposition"], "unverified")

    def test_entry_type_invalid(self):
        sc = self._run_with(etype="Material Transfer")
        self.assertEqual(find(sc, "se", "SE-1")["reason_code"],
                         "se_detail_entry_type_invalid")

    def test_posting_date_drift(self):
        sc = self._run_with(posting="2026-06-01")
        self.assertEqual(find(sc, "se", "SE-1")["reason_code"],
                         "se_detail_posting_date_drift")

    def test_detail_predates_snapshot(self):
        sc = self._run_with(fetched="2026-10-20T09:00:00+08:00")
        self.assertEqual(find(sc, "se", "SE-1")["reason_code"],
                         "se_detail_predates_snapshot")

    def test_drift_blocks_audit_and_evidence(self):
        sc = self._run_with(ds=2)
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertFalse(man["evidence_complete"])


# ── P1-5：se_query_error 与未解决已提交 SE 传播到 WO/C2/完整性 ──
class SeCoverageTests(unittest.TestCase):
    def test_query_error_with_empty_se_blocks_flags(self):
        sc = run(snapshot(se_rows=[], se_error="QueryError: timeout"))
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertFalse(man["evidence_complete"])
        self.assertFalse(man["conservation"]["C2_wo_se"][0]["complete"])
        self.assertTrue(man["coverage"]["se"]["query_errors"])
        self.assertEqual(find(sc, "wo", "WO-1")["reason_code"],
                         "wo_se_query_incomplete")
        self.assertTrue(any(f["reason_code"] == "wo_se_query_incomplete"
                            for f in man["findings"]))

    def test_one_unresolved_se_blocks_wo_even_if_another_is_conserved(self):
        se_rows = [se(name="SE-1", lines=[se_line()]),
                   se(name="SE-2", work_order="WO-1", finished=None)]
        sc = run(snapshot(se_rows=se_rows), {"SE-1": detail("SE-1")})
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "conserved")
        self.assertEqual(find(sc, "se", "SE-2")["disposition"], "unverified")
        wo_row = find(sc, "wo", "WO-1")
        self.assertEqual(wo_row["disposition"], "unverified")
        self.assertEqual(wo_row["reason_code"], "wo_se_incomplete")
        man = final_manifest(sc)
        self.assertFalse(man["evidence_complete"])
        self.assertFalse(man["audit_ok"])
        cov = man["coverage"]["se"]
        self.assertEqual(cov["submitted_total"], 2)
        self.assertEqual(cov["resolved_total"], 1)
        self.assertEqual([u["se"] for u in cov["unresolved_submitted"]], ["SE-2"])

    def test_submitted_se_outside_snapshot_counted(self):
        se_rows = [se(name="SE-1", lines=[se_line()]),
                   se(name="SE-X", work_order="WO-9", lines=[se_line()])]
        sc = run(snapshot(se_rows=se_rows))
        cov = sc["se_coverage"]
        self.assertEqual(cov["out_of_snapshot"], 1)
        self.assertEqual(len(cov["unresolved"]), 1)
        self.assertFalse(cov["complete"])
        man = final_manifest(sc)
        self.assertFalse(man["evidence_complete"])

    def test_all_resolved_is_complete(self):
        sc = run(snapshot())
        man = final_manifest(sc)
        self.assertTrue(man["coverage"]["se"]["complete"])
        self.assertTrue(man["conservation"]["C2_wo_se"][0]["complete"])
        self.assertTrue(man["audit_ok"])
        self.assertTrue(man["evidence_complete"])

    def test_known_subtotal_distinct_from_complete(self):
        se_rows = [se(name="SE-1", lines=[se_line()]),
                   se(name="SE-2", work_order="WO-1", finished=None)]
        sc = run(snapshot(se_rows=se_rows), {"SE-1": detail("SE-1")})
        c2 = sc["checks"]["C2_wo_se"]
        self.assertEqual(c2["known_subtotal"]["compared"], 0)
        self.assertFalse(c2["complete"])


# ── v3 交叉复审（2026-10-21 v2 FAIL）：UOM 分桶 / 子行传播 / JC 非法披露 ──
class CrossReviewV3Tests(unittest.TestCase):
    def test_single_se_mixed_uom_blocks_whole_chain(self):
        """10 EA + 2 BOX 在同一个 SE：不得出现 12，SE/WO/C2/audit/evidence 全部降级。"""
        lines = [se_line(qty=10, uom="EA", name="A"),
                 se_line(qty=2, uom="BOX", name="B")]
        sc = run(snapshot(se_rows=[se(finished=12, lines=lines)]))
        se_row = find(sc, "se", "SE-1")
        self.assertEqual(se_row["disposition"], "unverified")
        self.assertEqual(se_row["reason_code"], "se_finished_uom_mixed")
        self.assertIsNone(se_row["qty"]["finished_lines_sum"])
        self.assertIsNone(se_row["qty"]["finished_lines_sum_exact"])
        wo_row = find(sc, "wo", "WO-1")
        self.assertEqual(wo_row["disposition"], "unverified")
        self.assertIsNone(wo_row["qty"]["se_finished_qty"])
        self.assertEqual(wo_row["qty"]["se_finished_by_uom"], {})
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertFalse(man["evidence_complete"])
        self.assertFalse(man["conservation"]["C2_wo_se"][0]["complete"])
        self.assertEqual([u["reason_code"] for u in
                          man["coverage"]["se"]["unresolved_submitted"]],
                         ["se_finished_uom_mixed"])

    def test_cross_se_same_wo_mixed_uom_never_summed(self):
        """同一 WO 的两张 SE 各为 EA/BOX：分桶保留，绝不合成 12。"""
        se_rows = [se(name="SE-1", lines=[se_line(qty=10, uom="EA", name="A")]),
                   se(name="SE-2", finished=2,
                      lines=[se_line(qty=2, uom="BOX", name="B")])]
        sc = run(snapshot(se_rows=se_rows, wos=[wo(qty=12, produced=12)],
                          jc_map=jc("WO-1")))
        # 每张 SE 自身同单位，可以各自守恒；错的是 WO 级跨单位合计
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "conserved")
        self.assertEqual(find(sc, "se", "SE-2")["disposition"], "conserved")
        wo_row = find(sc, "wo", "WO-1")
        self.assertEqual(wo_row["disposition"], "unverified")
        self.assertEqual(wo_row["reason_code"], "wo_uom_mixed")
        self.assertIsNone(wo_row["qty"]["se_finished_qty"])
        self.assertIsNone(wo_row["qty"]["se_finished_qty_exact"])
        self.assertEqual(wo_row["qty"]["se_finished_by_uom"],
                         {"BOX": 2.0, "EA": 10.0})
        self.assertIn("wo_se_finished_uom_mixed", wo_row["reason_detail"])
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertFalse(man["evidence_complete"])
        self.assertFalse(man["conservation"]["C2_wo_se"][0]["complete"])
        mixed = man["coverage"]["se"]["unresolved_work_orders"]
        self.assertEqual([(m["work_order"], m["reason_code"]) for m in mixed],
                         [("WO-1", "wo_uom_mixed")])
        self.assertEqual(mixed[0]["se_finished_by_uom"], {"BOX": 2.0, "EA": 10.0})
        wo_summary = man["scopes"][0]["checks"]["C2_wo_se"]
        self.assertNotIn("se_finished_qty", wo_summary)   # C2 不产跨单位总量

    def test_invalid_finished_flag_child_blocks_parent_and_flags(self):
        """非法 is_finished_item 子行必须让父 SE/WO 不 conserved，并阻断 audit/evidence。"""
        lines = [se_line(qty=10, name="A"),
                 se_line(qty=5, name="B", fin="maybe")]
        sc = run(snapshot(se_rows=[se(finished=10, lines=lines)]))
        child = find(sc, "se_line", "SE-1::B")
        self.assertEqual(child["disposition"], "unverified")
        self.assertEqual(child["reason_code"], "se_line_finished_flag_invalid")
        se_row = find(sc, "se", "SE-1")
        self.assertEqual(se_row["disposition"], "unverified")
        self.assertEqual(se_row["reason_code"], "se_line_child_unresolved")
        self.assertIn("se_line_finished_flag_invalid", se_row["reason_detail"])
        self.assertIsNone(se_row["qty"]["finished_lines_sum_exact"])
        wo_row = find(sc, "wo", "WO-1")
        self.assertEqual(wo_row["disposition"], "unverified")
        self.assertEqual(wo_row["reason_code"], "wo_se_incomplete")
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertFalse(man["evidence_complete"])
        self.assertFalse(man["conservation"]["C2_wo_se"][0]["complete"])

    def test_matched_jc_malformed_operations_emit_invalid_row(self):
        """匹配到 WO 但工序明细非法的 JC 组：显式 invalid 行，不得计 matched。"""
        cases = [
            ("garbage", None, "jc_group_invalid"),
            ({"cards": 0, "operations": "garbage", "last_operation": None}, None,
             "jc_operations_invalid"),
            ({"cards": 0, "operations": {}, "last_operation": None}, None,
             "jc_no_operations"),
        ]
        for jc_value, _ops, reason in cases:
            with self.subTest(reason=reason):
                jc_map = {"WO-1": jc_value}
                sc = run(snapshot(jc_map=jc_map))
                rows = [r for r in by_type(sc, "jc_operation")
                        if r["row_key"] == "WO-1::<invalid_operations>"]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["disposition"], "invalid")
                self.assertEqual(rows[0]["reason_code"], reason)
                self.assertEqual(sc["jc_stats"],
                                 {"read": 1, "matched": 0, "orphan": 0, "invalid": 1})
                # JC 仍只作进度证据：守恒不受影响，但非法披露不可丢
                self.assertEqual(find(sc, "wo", "WO-1")["disposition"], "conserved")
                man = final_manifest(sc)
                self.assertEqual(man["coverage"]["invalid_jc_groups"], 1)
                self.assertEqual(man["coverage"]["orphan_jc_groups"], 0)


# ── v4 交叉复审 P2：JC 工序 payload 逐个校验 ──
class CrossReviewV4Tests(unittest.TestCase):
    """匹配到 WO 的 JC 组：任一工序 payload 非法 → 整组 invalid、不出 progress。"""

    CASES = [
        ("CUT", None, "jc_operation_payload_invalid"),
        ("CUT", "done", "jc_operation_payload_invalid"),
        ("CUT", {}, "jc_operation_sum_qty_invalid"),
        ("CUT", {"cards": 1, "sum_qty": "n/a", "jc_ids": ["J1"]},
         "jc_operation_sum_qty_invalid"),
    ]

    def test_malformed_operation_payloads_are_invalid(self):
        for op, payload, reason in self.CASES:
            with self.subTest(payload=payload):
                jc_map = {"WO-1": {"cards": 1, "operations": {op: payload},
                                   "last_operation": op}}
                sc = run(snapshot(jc_map=jc_map))
                self.assertEqual(sc["jc_stats"],
                                 {"read": 1, "matched": 0, "orphan": 0, "invalid": 1})
                rows = by_type(sc, "jc_operation")
                self.assertEqual([r["row_key"] for r in rows], [f"WO-1::{op}"])
                self.assertEqual(rows[0]["disposition"], "invalid")
                self.assertEqual(rows[0]["reason_code"], reason)
                self.assertIsNone(rows[0]["qty"]["sum_qty"])
                self.assertNotIn("progress", {r["disposition"] for r in rows})
                wo_row = find(sc, "wo", "WO-1")
                self.assertEqual(wo_row["disposition"], "conserved")   # JC 不参与守恒
                self.assertIn("jc_operation_payload_invalid", wo_row["reason_detail"])
                man = final_manifest(sc)
                self.assertEqual(man["coverage"]["invalid_jc_groups"], 1)
                self.assertEqual(man["coverage"]["orphan_jc_groups"], 0)

    def test_one_malformed_operation_invalidates_whole_group(self):
        """组内仍有合法工序时也不出 progress：整组只落非法项披露。"""
        jc_map = {"WO-1": {"cards": 2, "last_operation": "质检", "operations": {
            "裁剪": {"cards": 1, "sum_qty": 10.0, "jc_ids": ["J1"]},
            "质检": {"cards": 1, "sum_qty": None, "jc_ids": ["J2"]}}}}
        sc = run(snapshot(jc_map=jc_map))
        self.assertEqual(sc["jc_stats"],
                         {"read": 1, "matched": 0, "orphan": 0, "invalid": 1})
        self.assertEqual(
            [(r["row_key"], r["disposition"], r["reason_code"])
             for r in by_type(sc, "jc_operation")],
            [("WO-1::质检", "invalid", "jc_operation_sum_qty_invalid")])
        self.assertEqual(sc["checks"]["C4_rows"]["jc_groups"],
                         {"read": 1, "matched": 0, "orphan": 0, "invalid": 1})


# ── P1-6：C4 数原始输入、保留 rejected/orphan、校验子键唯一 ──
class C4RawLedgerTests(unittest.TestCase):
    def test_non_dict_rows_are_retained_as_rejected(self):
        snap = snapshot(se_rows=[se(lines=[se_line()]), "junk"],
                        dn_rows=[dn(), 123])
        sc = run(snap)
        rejected = {(r["row_type"], r["reason_code"]) for r in sc["rejected"]}
        self.assertIn(("se", "row_not_object"), rejected)
        self.assertIn(("dn_line", "row_not_object"), rejected)
        c4 = sc["checks"]["C4_rows"]
        self.assertEqual(c4["read"]["se"], 2)
        self.assertEqual(c4["emitted"]["se"], 2)
        self.assertEqual(c4["read"]["dn_line"], 2)
        self.assertEqual(c4["emitted"]["dn_line"], 2)
        self.assertTrue(c4["all_match"])
        man = final_manifest(sc)
        self.assertFalse(man["evidence_complete"])
        self.assertFalse(man["audit_ok"])
        self.assertEqual(len(man["coverage"]["rejected_rows"]), 2)

    def test_jc_group_for_absent_wo_is_orphan(self):
        jc_map = dict(jc())
        jc_map["WO-X"] = {"cards": 1, "operations": {
            "裁剪": {"cards": 1, "sum_qty": 3.0, "jc_ids": ["J9"]}},
            "last_operation": "裁剪"}
        sc = run(snapshot(jc_map=jc_map))
        r = find(sc, "jc_operation", "WO-X::裁剪")
        self.assertEqual(r["disposition"], "orphan")
        self.assertEqual(r["reason_code"], "jc_work_order_out_of_snapshot")
        self.assertEqual(sc["jc_stats"]["orphan"], 1)
        c4 = sc["checks"]["C4_rows"]
        self.assertEqual(c4["jc_groups"]["matched"], 1)
        self.assertEqual(c4["jc_groups"]["orphan"], 1)
        self.assertTrue(c4["all_match"])

    def test_duplicate_se_line_ids_fail_uniqueness(self):
        lines = [se_line(name="SL1", qty=10), se_line(name="SL1", qty=1)]
        sc = run(snapshot(se_rows=[se(lines=lines)]))
        dup_rows = [r for r in by_type(sc, "se_line")
                    if r["reason_code"] == "se_line_duplicate_key"]
        self.assertEqual(len(dup_rows), 1)
        self.assertEqual(dup_rows[0]["disposition"], "rejected")
        self.assertFalse(sc["checks"]["C4_rows"]["unique_keys"])
        self.assertTrue(sc["child_dup"])
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertFalse(man["evidence_complete"])

    def test_missing_se_line_id_not_silently_deduped(self):
        lines = [se_line(name=None, qty=5), se_line(name=None, qty=5)]
        sc = run(snapshot(se_rows=[se(finished=10, lines=lines)]))
        rows = by_type(sc, "se_line")
        self.assertEqual({r["reason_code"] for r in rows}, {"se_line_key_missing"})
        self.assertEqual(len({r["row_key"] for r in rows}), 2)
        self.assertEqual(find(sc, "se", "SE-1")["disposition"], "unverified")


# ── P2-7：有符号退货归一，只扣减一次 ─────────────────────
class SignedReturnTests(unittest.TestCase):
    def _net(self, return_qty):
        snap = snapshot(so_rows=[so(delivered=2)],
                        dn_rows=[dn(qty=4),
                                 dn(dn_id="DN-R", dn_line="DR1", qty=return_qty, ret=1)])
        sc = run(snap)
        return find(sc, "so_line", "SO-1::L1"), find(sc, "dn_line", "DN-R::DR1")

    def test_negative_return_is_normalized(self):
        so_row, ret_row = self._net(-2)
        self.assertEqual(ret_row["qty"]["qty"], 2.0)
        self.assertEqual(ret_row["qty"]["qty_raw"], -2.0)
        self.assertTrue(ret_row["qty"]["sign_normalized"])
        self.assertEqual(so_row["qty"]["dn_net"], 2.0)      # 4 - 2，不是 4 - (-2)
        self.assertEqual(so_row["disposition"], "conserved")

    def test_positive_return_same_result_no_double_subtraction(self):
        so_row, ret_row = self._net(2)
        self.assertFalse(ret_row["qty"]["sign_normalized"])
        self.assertEqual(so_row["qty"]["dn_net"], 2.0)
        self.assertEqual(so_row["disposition"], "conserved")

    def test_non_return_negative_is_invalid(self):
        snap = snapshot(dn_rows=[dn(qty=-2, ret=0)])
        sc = run(snap)
        r = find(sc, "dn_line", "DN-1::D1")
        self.assertEqual(r["reason_code"], "dn_qty_invalid")
        self.assertEqual(r["disposition"], "unverified")
        self.assertEqual(find(sc, "so_line", "SO-1::L1")["disposition"], "unverified")


# ── P2-8：请求级 HTTP 预算（明细 + 探针 + 翻页 + 重试共享）──
class HttpBudgetTests(unittest.TestCase):
    def test_budget_exhaustion_and_remaining(self):
        b = m.HttpBudget(2)
        self.assertEqual(b.remaining, 2)
        b.spend("enrich")
        b.spend("probe")
        self.assertEqual(b.remaining, 0)
        with self.assertRaises(m.BudgetExhausted):
            b.spend("probe")
        self.assertTrue(b.exhausted)
        self.assertEqual(b.by_kind, {"enrich": 1, "probe": 1})

    def test_retries_are_charged(self):
        b = m.HttpBudget(2)
        with mock.patch.object(m.requests, "get",
                               side_effect=m.requests.ConnectionError("down")), \
             mock.patch.object(m.time, "sleep", return_value=None):
            with self.assertRaises(m.BudgetExhausted):
                m.budgeted_get_status(b, "/x", "http://x", "k", "s")
        self.assertEqual(b.used, 2)
        self.assertEqual(b.by_kind["retry"], 1)
        self.assertTrue(b.exhausted)

    def test_pagination_pages_are_charged(self):
        b = m.HttpBudget(10)
        responses = [(200, {"data": [{"name": "a"}, {"name": "b"}]}),
                     (200, {"data": [{"name": "c"}]})]
        with mock.patch.object(m, "budgeted_get_status", side_effect=responses):
            out = m.budgeted_paginated_get(b, "Stock Entry", "http://x", "k", "s",
                                           [], ["name"], page_size=2)
        self.assertEqual(out["pages"], 2)
        self.assertEqual(len(out["rows"]), 3)

    def test_enrichment_reports_exhaustion(self):
        snap = snapshot(se_rows=[se(name="SE-1"), se(name="SE-2")])
        b = m.HttpBudget(0)
        with mock.patch.object(m.iss, "load_credentials", return_value=("k", "s")), \
             mock.patch.object(m, "budgeted_get_status",
                               side_effect=m.BudgetExhausted("empty")):
            with tempfile.TemporaryDirectory() as d:
                payload = m.enrich_se_details([snap], Path(d), b, 0.0, None, "x.env")
        log = payload["log"]
        self.assertTrue(log["budget_exceeded"])
        self.assertTrue(log["budget_exhausted"])
        self.assertEqual(log["http"], 0)
        self.assertEqual(log["not_requested"], ["SE-1", "SE-2"])

    def test_probe_reports_exhaustion(self):
        sc = run(snapshot(wos=[wo(produced=12)],
                          se_rows=[se(finished=10, lines=[se_line(qty=10)])]))
        b = m.HttpBudget(0)
        with mock.patch.object(m.iss, "load_credentials", return_value=("k", "s")), \
             mock.patch.object(m, "budgeted_get_single",
                               side_effect=m.BudgetExhausted("empty")):
            with tempfile.TemporaryDirectory() as d:
                payload = m.probe_wo_mismatches([sc], Path(d), 5, 0.0, b, "x.env")
        self.assertTrue(payload["log"]["budget_exceeded"])
        self.assertEqual(payload["log"]["not_probed"], ["WO-1"])
        self.assertEqual(payload["probes"]["WO-1"]["error"], "budget_exhausted")

    def test_manifest_marks_partial_when_budget_exhausted(self):
        b = m.HttpBudget(1)
        b.spend("enrich")
        with self.assertRaises(m.BudgetExhausted):
            b.spend("probe")
        man = final_manifest(run(snapshot()), budget=b)
        self.assertTrue(man["http_budget"]["exhausted"])
        self.assertEqual(man["run_status"], "partial_http_budget_exhausted")

    def test_budget_log_does_not_change_stable_hash(self):
        b1, b2 = m.HttpBudget(10), m.HttpBudget(10)
        b1.spend("enrich")
        b2.spend("probe")
        m1 = manifest(run(snapshot()), budget=b1)
        m2 = manifest(run(snapshot()), budget=b2)
        m2["as_of"] = m1["as_of"]
        self.assertEqual(m.stable_hash(m1), m.stable_hash(m2))


# ── P2-9：payload_sha256 覆盖含 stable_sha256 的最终字段 ──
class PayloadHashTests(unittest.TestCase):
    def test_payload_hash_covers_final_shape(self):
        man = final_manifest(run(snapshot()))
        self.assertIn("stable_sha256", man)
        self.assertIn("payload_sha256", man)
        body = {k: v for k, v in man.items() if k != "payload_sha256"}
        self.assertEqual(m.canonical_sha(body), man["payload_sha256"])

    def test_tampering_stable_hash_invalidates_payload(self):
        man = final_manifest(run(snapshot()))
        original = man["payload_sha256"]
        man["stable_sha256"] = "0" * 64
        body = {k: v for k, v in man.items() if k != "payload_sha256"}
        self.assertNotEqual(m.canonical_sha(body), original)

    def test_finalize_is_idempotent(self):
        man = final_manifest(run(snapshot()))
        snapshot_payload = (man["stable_sha256"], man["payload_sha256"])
        again = m.finalize_manifest(json.loads(json.dumps(man)))
        self.assertEqual((again["stable_sha256"], again["payload_sha256"]),
                         snapshot_payload)

    def test_payload_hash_detects_tamper(self):
        man = final_manifest(run(snapshot()))
        h = man.pop("payload_sha256")
        self.assertEqual(m.canonical_sha(man), h)
        man["audit_ok"] = not man["audit_ok"]
        self.assertNotEqual(m.canonical_sha(man), h)


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
        details = {"SE-1": detail()}
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

    def test_so_open_identity(self):
        snap = snapshot(so_rows=[so(qty=10, delivered=4, open_q=5)])
        sc = run(snap)
        self.assertIn("so_line_open_identity_mismatch",
                      find(sc, "so_line", "SO-1::L1")["reason_detail"])

    def test_voided_so_excluded_from_c1(self):
        snap = snapshot(so_rows=[so(ds=2, delivered=0)], dn_rows=[])
        sc = run(snap)
        self.assertEqual(find(sc, "so_line", "SO-1::L1")["disposition"], "excluded")
        c1 = sc["checks"]["C1_so_dn"]
        self.assertEqual(c1["per_uom"], [])
        self.assertEqual(c1["lines_excluded"], 1)
        self.assertTrue(c1["pass"])


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
        self.assertIn("so_line_date_missing", find(sc, "so_line", "SO-1::L3")["reason_detail"])


class AccountingTests(unittest.TestCase):
    def test_row_accounting_matches(self):
        sc = run(snapshot())
        man = final_manifest(sc)
        self.assertTrue(man["audit_ok"])
        for t in ("so_line", "dn_line", "wo", "se"):
            self.assertTrue(man["row_accounting"][t]["match"], t)
        self.assertEqual(man["row_accounting"]["se_line"]["derived"], 1)
        self.assertTrue(man["scopes"][0]["checks"]["C4_rows"]["all_match"])

    def test_duplicate_keys_fail_audit(self):
        snap = snapshot(so_rows=[so(line="L1"), so(line="L1")])
        sc = run(snap)
        man = final_manifest(sc)
        self.assertFalse(man["audit_ok"])
        self.assertTrue(man["coverage"]["duplicate_keys"])

    def test_stable_hash_ignores_run_id(self):
        sc = run(snapshot())
        a = manifest(sc)
        b = manifest(sc, run_id="r2")
        b["as_of"] = a["as_of"]
        self.assertEqual(m.stable_hash(a), m.stable_hash(b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
