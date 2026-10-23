#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B package: fixed linkage audit across four policy stages (READ-ONLY).

Fixes / handles two things:

1. The Delivery Plan false negative. Selecting the header `status` together with
   child-table fields makes EN silently return 0 rows. This script queries DP
   twice over the *same* SO chunks — once with `status` (old, broken shape) and
   once without it (corrected shape) — and reports before/after hit counts plus
   the recomputed linkage rate.

2. Stage-aware linkage audit. SOs are bucketed into
   A 2024-11..2025-05 (no DP), B 2025-06..2025-12 (DP introduced),
   C 2026-01..2026-06 (scan + policy), D 2026-07..2026-10.
   Each stage gets the explicit hit rate of SO -> DP / DN / WO / MR / PP and a
   classification of the SOs that were not hit.

Per SO line three things are kept apart:
  * raw demand (`items.qty`);
  * DN net delivered (submitted DN rows; returns carry negative qty and net out);
  * the residual demand - net — reported as an arithmetic balance, NOT as an
    independent verification of anything.
Independent anomalies are counted separately: negative demand, DN returns,
net over-delivery, a single DN row larger than the line, duplicate submitted DN
rows for the same line, and cancelled documents.

Every explicit link row is also checked for quantity, date and warehouse.
A row missing any of the three is `partial`; Production Plan links can never be
complete (its child table carries only the SO link and the SO date).

Pagination note: EN times out (HTTP 500) on wide child-table scans sorted by
`name asc, idx asc`, while `name asc` works; OFFSET paging on `name asc` alone
repeats and drops rows. Everything here therefore pages with a keyset
(`name >= last`) and dedupes by line id.

Boundary: explicit links only; no same-item inference; no stock conclusion.

Budget: <=200 GET, single-threaded, 200 ms. A path is abandoned after 3
consecutive HTTP 500s and reported as unavailable instead of silently zero.

Outputs: out/auto_order/linkage_audit_v2.csv / .md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import build_order_suggestions as v01  # noqa: E402

OUT = HERE.parents[2] / "out" / "auto_order"
MAX_GETS = 200
PAGE = 500                # EN honors 500 rows/page when sorted by name alone
CHUNK_LINES = 10          # SO names per child-table line query
CHUNK_LINK = 20           # SO names per link scan query
MAX_CONSEC_500 = 3        # abandon a path after this many consecutive 500s
TOL = 0.005

STAGES = [
    ("A", "2024-11-01", "2025-06-01", "2024-11..2025-05", "无 DP"),
    ("B", "2025-06-01", "2026-01-01", "2025-06..2025-12", "DP 上线"),
    ("C", "2026-01-01", "2026-07-01", "2026-01..2026-06", "扫码+政策"),
    ("D", "2026-07-01", "2026-11-01", "2026-07..2026-10", "近期"),
]

PATHS = ["DP", "DN", "WO", "MR", "PP"]


def sha(x) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def stage_of(date_str: str):
    d = str(date_str or "")[:10]
    for code, start, end, _label, _note in STAGES:
        if start <= d < end:
            return code
    return None


def pct(a, b):
    return "—" if not b else f"{a / b * 100:.1f}%"


def fnum(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}"


class Runner:
    def __init__(self, c):
        self.c = c
        self.unavailable = {}
        self.consec_500 = Counter()
        self.fail_notes = []

    def list_page(self, doctype, fields, filters):
        return self.c.get(f"/api/resource/{doctype}",
                          {"fields": json.dumps(fields), "filters": json.dumps(filters),
                           "limit_page_length": PAGE, "limit_start": 0,
                           "order_by": "name asc"}) or {}

    def keyset(self, key, doctype, fields, base_filters):
        """Yield rows, paging with `name >= last` (never skips a parent)."""
        last, guard = None, 0
        while guard < 200:
            guard += 1
            flt = list(base_filters) + ([["name", ">=", last]] if last else [])
            try:
                res = self.list_page(doctype, fields, flt)
            except v01.StopRun as exc:
                self.consec_500[key] += 1
                self.fail_notes.append(f"{key}: {exc}")
                if self.consec_500[key] >= MAX_CONSEC_500:
                    self.unavailable[key] = f"abandoned after {MAX_CONSEC_500} failures: {exc}"
                return
            self.consec_500[key] = 0
            rows = res.get("data", []) or []
            if not rows:
                return
            yield from rows
            if len(rows) < PAGE:
                return
            new_last = rows[-1].get("name")
            if not new_last or new_last == last:
                self.fail_notes.append(f"{key}: stopped inside one parent ({new_last})")
                return
            last = new_last

    def scan(self, key, doctype, fields, head, names, normalise):
        """`head=None` scans the whole doctype (keyset, no name filter) and keeps
        only rows whose SO is in `names`. Used for Production Plan, whose child
        table has no usable index: filtering by `sales_order in [...]` returns
        HTTP 500."""
        rows_out, seen = [], set()
        if key in self.unavailable:
            return rows_out
        if head is None:
            wanted = set(names)
            before = len(self.fail_notes)
            for r in self.keyset(key, doctype, fields, []):
                k = r.get("line_id") or (r.get("name"), r.get("sales_order"))
                if k in seen:
                    continue
                seen.add(k)
                row = normalise(r)
                if row.get("so") in wanted:
                    rows_out.append(row)
            if len(self.fail_notes) > before:
                self.unavailable[key] = ("EN 对子表查询持续返回 500；该路径不可观测，"
                                         "不是「没有关联」")
            return rows_out
        for chunk in v01._chunks(sorted(names), CHUNK_LINK):
            chunk_set = set(chunk)
            seen_chunk = set()
            for r in self.keyset(key, doctype, fields,
                                 [list(head) + ["in", chunk]]):
                k = r.get("line_id") or (
                    r.get("name"),
                    r.get("sales_order") or r.get("against_sales_order"),
                    r.get("item_code") or r.get("production_item"))
                if k in seen:
                    continue
                seen.add(k)
                row = normalise(r)
                rows_out.append(row)
                if row.get("so") in chunk_set:
                    seen_chunk.add(row["so"])
                # NOTE: no early exit once every SO is seen — later pages may
                # still hold additional lines for those same SOs.
            if key in self.unavailable:
                return rows_out
        return rows_out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(v01.ENV))
    ap.add_argument("--base", default=v01.BASE)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    v01.MAX_GETS = MAX_GETS
    v01.SLEEP_S = args.sleep
    env = v01.load_env(Path(args.env))
    c = v01.Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])
    R = Runner(c)
    notes = []

    # ---- 1. SO headers ------------------------------------------------
    headers = list(R.keyset(
        "SO headers", "Sales Order",
        ["name", "transaction_date", "docstatus", "status", "is_internal_customer"],
        [["docstatus", "in", [1, 2]],
         ["transaction_date", ">=", STAGES[0][1]],
         ["transaction_date", "<", STAGES[-1][2]]]))

    so_meta = {}
    for r in headers:
        st = stage_of(r.get("transaction_date"))
        if not st:
            continue
        so_meta[r["name"]] = dict(
            stage=st, internal=bool(r.get("is_internal_customer")),
            cancelled=(int(r.get("docstatus") or 0) == 2 or r.get("status") == "Cancelled"))
    active = {n: m for n, m in so_meta.items() if not m["cancelled"]}

    # ---- 2. SO lines ---------------------------------------------------
    lines, seen_lines = [], set()
    line_fields = ["name", "items.name as line_id", "items.idx", "items.item_code",
                   "items.qty", "items.delivered_qty", "items.uom", "items.stock_uom",
                   "items.delivery_date", "items.warehouse"]
    for chunk in v01._chunks(sorted(active), CHUNK_LINES):
        if "SO lines" in R.unavailable:
            break
        for r in R.keyset("SO lines", "Sales Order", line_fields,
                          [["name", "in", chunk]]):
            lid = r.get("line_id") or f"{r.get('name')}|{r.get('idx')}"
            if lid in seen_lines or not r.get("item_code"):
                continue
            seen_lines.add(lid)
            m = active.get(r["name"])
            if not m:
                continue
            lines.append(dict(
                so=r["name"], line_id=lid, stage=m["stage"], internal=m["internal"],
                item=r["item_code"], qty=float(r.get("qty") or 0),
                delivered_field=float(r.get("delivered_qty") or 0),
                uom=str(r.get("uom") or r.get("stock_uom") or "").strip(),
                delivery_date=str(r.get("delivery_date") or "")[:10],
                warehouse=r.get("warehouse") or ""))

    lines_of = Counter((x["so"], x["item"]) for x in lines)

    # ---- 3. explicit link scans ---------------------------------------
    def norm_dp(r):
        return dict(so=r.get("sales_order"), detail=r.get("so_detail"),
                    item=r.get("item_code"), qty=r.get("qty"), uom=r.get("uom"),
                    date=str(r.get("delivery_date") or "")[:10],
                    wh=r.get("warehouse") or "", docstatus=r.get("docstatus"),
                    doc=r.get("name"))

    def norm_dn(r):
        return dict(so=r.get("against_sales_order"), detail=r.get("so_detail"),
                    item=r.get("item_code"), qty=r.get("qty"), uom=r.get("uom"),
                    date=str(r.get("posting_date") or "")[:10],
                    wh=r.get("warehouse") or "", docstatus=r.get("docstatus"),
                    doc=r.get("name"))

    def norm_wo(r):
        return dict(so=r.get("sales_order"), detail=None,
                    item=r.get("production_item"), qty=r.get("qty"),
                    uom=r.get("stock_uom"),
                    date=str(r.get("planned_end_date") or r.get("planned_start_date") or "")[:10],
                    wh=r.get("source_warehouse") or r.get("fg_warehouse") or "",
                    docstatus=r.get("docstatus"), doc=r.get("name"))

    def norm_mr(r):
        return dict(so=r.get("sales_order"), detail=r.get("so_detail"),
                    item=r.get("item_code"), qty=r.get("qty"), uom=r.get("uom"),
                    date=str(r.get("schedule_date") or "")[:10],
                    wh=r.get("warehouse") or "", docstatus=r.get("docstatus"),
                    doc=r.get("name"))

    def norm_pp(r):
        return dict(so=r.get("sales_order"), detail=None, item=None, qty=None,
                    uom=None, date=str(r.get("sales_order_date") or "")[:10],
                    wh="", docstatus=r.get("docstatus"), doc=r.get("name"))

    specs = [
        ("DP", "Delivery Plan",
         ["name", "docstatus", "delivery_date", "items.name as line_id",
          "items.sales_order", "items.so_detail", "items.item_code", "items.qty",
          "items.uom", "items.warehouse"], ["Delivery Plan Item", "sales_order"], norm_dp),
        ("DN", "Delivery Note",
         ["name", "docstatus", "posting_date", "items.name as line_id",
          "items.against_sales_order", "items.so_detail", "items.item_code",
          "items.qty", "items.uom", "items.warehouse"],
         ["Delivery Note Item", "against_sales_order"], norm_dn),
        ("WO", "Work Order",
         ["name", "docstatus", "sales_order", "production_item", "qty",
          "stock_uom", "planned_start_date", "planned_end_date",
          "source_warehouse", "fg_warehouse"], ["sales_order"], norm_wo),
        ("MR", "Material Request",
         ["name", "docstatus", "items.sales_order",
          "items.sales_order_item as so_detail", "items.item_code", "items.qty",
          "items.uom", "items.warehouse", "items.schedule_date"],
         ["Material Request Item", "sales_order"], norm_mr),
        ("PP", "Production Plan",
         ["name", "docstatus", "items.sales_order", "items.sales_order_date"],
         None, norm_pp),
    ]
    links = {}
    for key, doctype, fields, head, norm in specs:
        links[key] = R.scan(key, doctype, fields, head, list(active), norm)

    dp_broken_rows = R.scan(
        "DP_broken", "Delivery Plan",
        ["name", "docstatus", "status", "items.name as line_id",
         "items.sales_order", "items.so_detail", "items.item_code", "items.qty"],
        ["Delivery Plan Item", "sales_order"], list(active), norm_dp)
    dp_broken = {r["so"] for r in dp_broken_rows if r["so"]}

    hit = {k: {r["so"] for r in links.get(k, []) if r["so"]} for k in PATHS}

    # ---- 4. per-line DN net + anomalies ------------------------------
    dp_by_detail = defaultdict(list)
    for r in links.get("DP", []):
        if r["detail"]:
            dp_by_detail[r["detail"]].append(r)

    def rec_complete(r):
        return (r["qty"] not in (None, "") and float(r["qty"] or 0) > 0
                and bool(r["date"]) and bool(r["wh"]))

    dn_by_detail = defaultdict(list)
    dn_by_so_item = defaultdict(list)
    for r in links.get("DN", []):
        if r["detail"]:
            dn_by_detail[r["detail"]].append(r)
        elif r["so"]:
            dn_by_so_item[(r["so"], r["item"])].append(r)

    anomalies = Counter()
    out_rows = []
    for x in lines:
        # so_detail alone is not enough: the row must also belong to this SO
        dn = [r for r in dn_by_detail.get(x["line_id"], []) if r["so"] == x["so"]]
        ambiguous = False
        if not dn:
            cand = dn_by_so_item.get((x["so"], x["item"]), [])
            if cand:
                if lines_of[(x["so"], x["item"])] > 1:
                    ambiguous = True
                else:
                    dn = list(cand)

        submitted = [r for r in dn if int(r["docstatus"] or 0) == 1]
        cancelled = [r for r in dn if int(r["docstatus"] or 0) == 2]
        # a DN line counts towards this SO line only if the item and the UOM
        # both agree; anything else is recorded, never summed
        same_uom = [r for r in submitted
                    if str(r["uom"] or "").strip() == x["uom"]
                    and r["item"] == x["item"]]
        if submitted and len(same_uom) != len(submitted):
            anomalies["dn_item_or_uom_mismatch"] += 1
        net = sum(float(r["qty"] or 0) for r in same_uom)
        residual = x["qty"] - net

        if x["qty"] < 0:
            anomalies["negative_demand"] += 1
        if any(float(r["qty"] or 0) < 0 for r in submitted):
            anomalies["dn_return"] += 1
        if same_uom and net > x["qty"] + TOL:
            anomalies["net_over_delivery"] += 1
        if any(float(r["qty"] or 0) > x["qty"] + TOL for r in same_uom):
            anomalies["dn_row_gt_line"] += 1
        if cancelled:
            anomalies["dn_cancelled"] += 1
        if ambiguous:
            anomalies["dn_ambiguous"] += 1
        dup = Counter((round(float(r["qty"] or 0), 3), r["date"]) for r in submitted)
        if any(v > 1 for v in dup.values()):
            anomalies["duplicate_dn_rows"] += 1

        linked_paths = [k for k in PATHS if x["so"] in hit.get(k, set())]
        # line-level linkage: only DN and DP carry so_detail
        line_recs = list(dn) + [r for r in dp_by_detail.get(x["line_id"], [])
                                if r["so"] == x["so"]]
        if line_recs:
            line_link = "complete" if all(rec_complete(r) for r in line_recs) else "partial"
        elif linked_paths:
            line_link = "so_level_only"     # WO/MR/PP link at SO level, not to this line
        else:
            line_link = "no_link"
        out_rows.append(dict(
            so_hash=sha(x["so"]), line_hash=sha(x["line_id"]), stage=x["stage"],
            internal=x["internal"], item=x["item"], demand=round(x["qty"], 3),
            delivered_field=round(x["delivered_field"], 3), dn_net=round(net, 3),
            residual=round(residual, 3), delivery_date=x["delivery_date"],
            warehouse=x["warehouse"], dn_rows=len(submitted),
            dn_ambiguous=int(ambiguous), line_link=line_link,
            linked="|".join(linked_paths),
            so_dp=int("DP" in linked_paths), so_dn=int("DN" in linked_paths),
            so_wo=int("WO" in linked_paths), so_mr=int("MR" in linked_paths),
            so_pp=int("PP" in linked_paths)))

    out_rows.sort(key=lambda r: (r["stage"], r["internal"], r["so_hash"],
                                 r["item"], r["line_hash"]))
    fields = ["so_hash", "line_hash", "stage", "internal", "item", "demand",
              "delivered_field", "dn_net", "residual", "delivery_date",
              "warehouse", "dn_rows", "dn_ambiguous", "line_link", "linked",
              "so_dp", "so_dn", "so_wo", "so_mr", "so_pp"]
    csv_path = OUT / "linkage_audit_v2.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()[:16]

    # ---- 5. completeness (qty / date / warehouse) --------------------
    completeness = {}
    for key in PATHS:
        rows = links.get(key, [])
        qty_ok = sum(1 for r in rows
                     if r["qty"] not in (None, "") and float(r["qty"] or 0) > 0)
        date_ok = sum(1 for r in rows if r["date"])
        wh_ok = sum(1 for r in rows if r["wh"])
        full = sum(1 for r in rows
                   if (r["qty"] not in (None, "") and float(r["qty"] or 0) > 0)
                   and r["date"] and r["wh"])
        completeness[key] = dict(n=len(rows), qty=qty_ok, date=date_ok,
                                 wh=wh_ok, full=full)

    # ---- 6. stage aggregation ----------------------------------------
    stage_table = []
    for code, _s, _e, label, note in STAGES:
        names = [n for n, m in active.items() if m["stage"] == code]
        row = dict(code=code, label=label, note=note, so=len(names),
                   cancelled=sum(1 for m in so_meta.values()
                                 if m["stage"] == code and m["cancelled"]),
                   lines=sum(1 for x in lines if x["stage"] == code),
                   demand=sum(x["qty"] for x in lines if x["stage"] == code),
                   dn_net=sum(r["dn_net"] for r in out_rows if r["stage"] == code),
                   residual=sum(r["residual"] for r in out_rows if r["stage"] == code))
        for k in PATHS:
            row[k] = sum(1 for n in names if n in hit.get(k, set()))
        row["none"] = sum(1 for n in names
                          if not any(n in hit.get(k, set()) for k in PATHS))
        stage_table.append(row)

    elapsed = round(time.time() - c.started, 1)

    # ---- 7. report ----------------------------------------------------
    L = ["---", "okf: v0.1", "type: Report",
         "title: B 包：SO 关联修复与分阶段审计",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读；DP 修正前后对比 + 四阶段命中率 + 线级三类/异常",
         "artifacts:",
         "  - experiments/auto_order/fix_linkage_audit.py",
         "  - out/auto_order/linkage_audit_v2.csv",
         "---", "",
         "# B 包：SO 关联修复与分阶段审计", "",
         "> **边界**：只用显式关联；不按同物料推断；不读库存。"
         "「需求 − 净交付 = 余额」只是同一批单据的算术结果，**不作为独立验证**。", "",
         "## 0. 预算与数据完整性", "",
         f"- 请求 **{c.gets}** / {MAX_GETS}；耗时 **{elapsed} s**；单线程；间隔 {args.sleep} s；"
         f"停止原因：{c.stop_reason or '无（正常完成）'}"
         + ('（有失败请求，已继续；见下方异常）' if c.stop_reason else ""),
         f"- SO 头 **{len(so_meta)}**（含已取消 {sum(1 for m in so_meta.values() if m['cancelled'])}）；"
         f"已审计 **{len(active)}**；加载明细行 **{len(lines)}**",
         f"- 不可用路径：{R.unavailable or '无'}",
         f"- CSV 哈希（sha256 前 16）：`{digest}`", ""]
    if notes or R.fail_notes:
        L += ["### 请求异常（前 8 条）", ""]
        for x in (notes + R.fail_notes)[:8]:
            L.append(f"- {x}")
        L.append("")

    L += ["## 1. DP 查询修正：同一批 SO 的前后对比", "",
          "| 口径 | 命中 SO 数 | 关联率 |", "|---|---:|---:|",
          f"| 修正前（表头 `status` + 子表字段） | **{len(dp_broken)}** | {pct(len(dp_broken), len(active))} |",
          f"| 修正后（去掉 `status`） | **{len(hit['DP'])}** | {pct(len(hit['DP']), len(active))} |", ""]

    L += ["## 2. 分阶段显式命中率（SO → 路径）", "",
          "| 阶段 | 时间 | 机制 | SO | 已取消 | DP | DN | WO | MR | PP | 五路全无 |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in stage_table:
        L.append(f"| {r['code']} | {r['label']} | {r['note']} | {r['so']} | {r['cancelled']} | "
                 f"{pct(r['DP'], r['so'])} | {pct(r['DN'], r['so'])} | {pct(r['WO'], r['so'])} | "
                 f"{pct(r['MR'], r['so'])} | {pct(r['PP'], r['so'])} | {r['none']} |")

    a_dp = next((r for r in stage_table if r["code"] == "A"), None)
    if a_dp and a_dp["so"] and a_dp["DP"]:
        L += ["", f"> 观测：阶段 A 名义上是「无 DP」，但显式 DP 命中 **{a_dp['DP']}/{a_dp['so']}"
              f"（{pct(a_dp['DP'], a_dp['so'])}）**——阶段标签与数据不一致，"
              f"命中率以实测为准。", ""]
    L += ["", "### 2b. 未命中原因分类（按阶段 × 路径，SO 数）", "",
          "| 阶段 | 路径 | 有命中 | 无显式引用 | 机制未上线 | 路径不可用 |",
          "|---|---|---:|---:|---:|---:|"]
    for r in stage_table:
        for k in PATHS:
            if k in R.unavailable:
                L.append(f"| {r['code']} | {k} | — | — | — | 是 |")
                continue
            # 不预设「阶段 A 没有 DP」：实测 A 也有 DP 命中，原因分类只写观测
            L.append(f"| {r['code']} | {k} | {r[k]} | {r['so'] - r[k]} | 0 | 0 |")

    L += ["", "## 3. 原始需求 / DN 净交付 / 余额（按阶段，逐行口径）", "",
          "| 阶段 | 行数 | 原始需求 | DN 净交付 | 余额（需求−净交付） |",
          "|---|---:|---:|---:|---:|"]
    for r in stage_table:
        L.append(f"| {r['code']} | {r['lines']} | {fnum(r['demand'])} | "
                 f"{fnum(r['dn_net'])} | {fnum(r['residual'])} |")
    L += ["", "> 余额只是算术结果，**不是**独立验证，也不代表真实未履约；独立信号见第 4 节。", ""]

    L += ["## 4. 独立异常（逐行计数）", "",
          "| 异常 | 行数 | 说明 |", "|---|---:|---|"]
    for k, desc in (
            ("negative_demand", "需求数量为负"),
            ("dn_return", "DN 含负数行（退货）"),
            ("net_over_delivery", "DN 净交付 > 行需求"),
            ("dn_row_gt_line", "单张 DN 行数量 > 行需求"),
            ("duplicate_dn_rows", "同一行出现重复 DN（数量+日期相同）"),
            ("dn_cancelled", "存在已取消 DN"),
            ("dn_ambiguous", "DN 仅 SO+物料级关联且同物料多行"),
            ("dn_item_or_uom_mismatch", "DN 行的物料或单位与 SO 行不一致（不计入净交付）")):
        L.append(f"| {k} | {anomalies.get(k, 0)} | {desc} |")

    line_link = Counter(r["line_link"] for r in out_rows)
    L += ["", "### 4b. 行级关联齐备度（DN+DP 能精确到行）", "",
          "| 状态 | 行数 | 含义 |", "|---|---:|---|",
          f"| complete | {line_link.get('complete', 0)} | 该行有行级关联，且数量/日期/仓三项齐备 |",
          f"| partial | {line_link.get('partial', 0)} | 有行级关联，但至少一项缺失 |",
          f"| so_level_only | {line_link.get('so_level_only', 0)} | 只有 WO/MR/PP 的 SO 级关联，无法归属到本行 |",
          f"| no_link | {line_link.get('no_link', 0)} | 五条路径都没有显式关联 |",
          "",
          "> CSV 的 `so_dp/so_dn/so_wo/so_mr/so_pp` 是 **SO 级**命中标记；"
          "行级归属只有 DN、DP 能通过 `so_detail` 做到（列 `line_link`）。", ""]

    L += ["", "## 5. 数量 / 交货日 / 仓 三项齐备率（按路径）", "",
          "| 路径 | 关联行 | 有数量 | 有日期 | 有仓 | 三项齐备 | 齐备率 |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for k in PATHS:
        c_ = completeness[k]
        L.append(f"| {k} | {c_['n']} | {c_['qty']} | {c_['date']} | {c_['wh']} | "
                 f"{c_['full']} | {pct(c_['full'], c_['n'])} |")
    L += ["", "> PP 子表只有 SO 链接与 SO 日期，没有数量/仓，因此 PP 关联天然 `partial`；"
          "DP 的日期取表头 `delivery_date`。", ""]

    L += ["## 6. 结论", ""]
    L.append(f"1. **修好后 DP 关联率 {pct(len(hit['DP']), len(active))}**"
             f"（修正前 {pct(len(dp_broken), len(active))}，{len(dp_broken)} → {len(hit['DP'])} 张 SO）："
             f"差异来自查询字段组合，不是数据缺失。")
    worst = [f"{r['code']}（五路全无 {r['none']}/{r['so']}）"
             for r in stage_table if r["so"] and r["none"]]
    L.append(f"2. **仍缺链的阶段**：{'；'.join(worst) if worst else '无'}；"
             f"各路径命中率见第 2 节，未命中原因见 2b（只区分「无显式引用 / 机制未上线 / 路径不可用」）。")
    total_anom = sum(anomalies.values())
    L.append(f"3. **独立异常 {total_anom} 条**（逐类见第 4 节）；三项（数量/日期/仓）齐备率见第 5 节，"
             f"未齐备的关联一律记 `partial`。")
    if R.unavailable:
        L += ["", f"> ⚠️ 本次有路径不可用（{', '.join(R.unavailable)}），相关命中率是**下界**。"]
    L += ["", "## 7. 方法要点", "",
          "- 只认显式字段：DP/`sales_order`+`so_detail`、DN/`against_sales_order`+`so_detail`、"
          "WO/`sales_order`、MR/`sales_order`、PP/`sales_order`；不做同物料推断。",
          "- DN 只计 docstatus=1；负数行按退货净额处理；已取消/草稿单独计数。",
          "- 余额只作算术结果；独立异常单列（负数/超交付/重复 DN）。",
          "- 分页用 keyset（`name >= last`）+ 行 id 去重：EN 的 `name asc, idx asc` 会超时，"
          "纯 `name asc` 的 OFFSET 分页会重复/漏行。",
          "- 连续 3 次 500 放弃该路径并标下界；单号哈希化，CSV 不含客户名与单据号。", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/fix_linkage_audit.py",
          "```", ""]

    (OUT / "linkage_audit_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote linkage_audit_v2.csv / .md")
    print(f"requests={c.gets} elapsed={elapsed}s so={len(so_meta)} active={len(active)} "
          f"lines={len(lines)} dp_broken={len(dp_broken)} dp_fixed={len(hit['DP'])} "
          f"stopped={c.stop_reason} unavailable={R.unavailable} csv_sha={digest}")
    for k in PATHS:
        print(f"  {k}: hits={len(hit[k])} rows={len(links.get(k, []))} "
              f"complete={completeness[k]['full']}/{completeness[k]['n']}")
    print(f"  anomalies={dict(anomalies)}")


if __name__ == "__main__":
    main()
