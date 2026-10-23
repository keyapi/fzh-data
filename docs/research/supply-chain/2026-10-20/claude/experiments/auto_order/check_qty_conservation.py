#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Explicit-link quantity conservation for 2026 H1–Q3 sales order lines (READ-ONLY).

Question (per the Codex2 ruling): for the SO lines in scope, do the *explicitly
linked* supply / delivery quantities conserve against the demanded quantity?

Scope
  Submitted, non-cancelled Sales Order LINES with `transaction_date` in
  2026-01-01 .. 2026-09-30, split by `is_internal_customer`.
  Cancelled SO lines in the same window are counted separately and never enter
  the conservation arithmetic.

Explicit linkage ONLY (no same-item inference)
  * SO header `po_no` -> Purchase Order of that name (line item must match item
    and UOM);
  * Work Order whose header `sales_order` is this SO (production_item must match
    the line item and UOM);
  * Delivery Note Item with `so_detail` == this SO line (fallback:
    `against_sales_order` == SO and same item, only when `so_detail` is empty);
  * Delivery Plan Item with `so_detail` == this SO line (used for linkage
    evidence only, not for quantity).
  A line with none of the above is recorded as **unobserved** and excluded from
  conservation and from the supply/demand ratio.

Same-unit rule
  Quantities are only summed when the UOM strings match. Any linked record with
  a different UOM marks the line `uom_mismatch` and that record is excluded from
  the sums (recorded, not silently dropped).

Arithmetic (per line)
  * `delivered_obs` = submitted DN quantity explicitly linked to the line;
    `remaining_obs` = demand - delivered_obs;
    identity `delivered_obs + remaining_obs == demand` is checked exactly, and
    the stored `delivered_qty` is compared against `delivered_obs`
    (`field_gap`). Rows without any explicit DN are `no_dn_unverified`.
  * supply/demand ratio uses attributable, same-unit, non-shared quantities:
    `supply_source` is `po`, `wo` (planned qty), `both` or `none`. `both` rows
    are NOT summed into one ratio (that would double count) — they are counted
    separately as `multi_source`.

Sharing / allocation
  * A `po_no` referenced by more than one SO header is shared: its quantity is
    not attributed to any single line (`po_shared`).
  * A Work Order whose SO contains more than one line of the same item is
    ambiguous: not attributed (`wo_shared`).
  * A DN linked only by `against_sales_order` + item (no `so_detail`) while the
    SO has several lines of that item is ambiguous: `dn_ambiguous`, excluded.

Boundary: this checks document linkage and arithmetic only. It does NOT judge
whether the physical stock was sufficient or whether over/under supply really
happened — no inventory history is read.

Budget: <=200 GET, single-threaded, 200 ms interval, stop on timeout / 5xx /
auth error; partial results are still written and marked partial.

Outputs: out/auto_order/qty_conservation.csv, out/auto_order/qty_conservation.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import build_order_suggestions as v01  # noqa: E402  (env loader / client / chunks)

OUT = HERE.parents[2] / "out" / "auto_order"
MAX_GETS = 200
PAGE = 200
SCOPE_FROM = "2026-01-01"
SCOPE_TO = "2026-10-01"          # exclusive
CHUNK = 20                       # document names per "in" filter
TOL = 0.005                      # quantity tolerance
OVER = 1.2
UNDER = 0.9


def d(s):
    return str(s or "")[:10]


def n(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def uom(x):
    return str(x or "").strip()


def num(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


def pct(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def quantiles(vals):
    if not vals:
        return None
    s = sorted(vals)

    def q(p):
        if len(s) == 1:
            return s[0]
        pos = (len(s) - 1) * p
        lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)

    return dict(min=s[0], p25=q(0.25), median=q(0.5), p75=q(0.75), max=s[-1], n=len(s))


def list_flat(c, doctype, fields, filters, order):
    """Paginated list with a total order (parent name + child idx)."""
    out, start = [], 0
    while True:
        res = c.get(f"/api/resource/{doctype}",
                    {"fields": json.dumps(fields), "filters": json.dumps(filters),
                     "limit_page_length": PAGE, "limit_start": start,
                     "order_by": order})
        rows = (res or {}).get("data", []) if isinstance(res, dict) else []
        out.extend(rows)
        if len(rows) < PAGE:
            break
        start += len(rows)
    return out


def fetch_named(c, doctype, fields, filter_head, names, order):
    """Fetch documents by an `in` filter over names, chunked; dedupe by child line.

    `filter_head` is the filter path: `["name"]` for a header field, or
    `["Delivery Note Item", "against_sales_order"]` for a child-table field —
    Frappe rejects the dotted "Child.field" spelling with HTTP 500.
    """
    rows, seen = [], set()
    for chunk in v01._chunks(sorted(names), CHUNK):
        flt = [list(filter_head) + ["in", chunk]]
        for r in list_flat(c, doctype, fields, flt, order):
            key = r.get("line_id") or (r.get("name"), r.get("item_code"),
                                       r.get("creation"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    return rows


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
    stopped = None

    # ---- 1. SO lines ------------------------------------------------
    # docstatus 1 (submitted) and 2 (cancelled) are fetched together so the
    # cancelled count costs no extra request; only 1 + status != Cancelled is
    # in scope.
    so_fields = ["name", "creation", "transaction_date", "docstatus", "status",
                 "is_internal_customer", "po_no",
                 "items.name as line_id", "items.idx", "items.item_code",
                 "items.qty", "items.delivered_qty", "items.uom",
                 "items.stock_uom", "items.delivery_date"]
    so_filters = [["docstatus", "in", [1, 2]],
                  ["transaction_date", ">=", SCOPE_FROM],
                  ["transaction_date", "<", SCOPE_TO]]
    try:
        so_rows = list_flat(c, "Sales Order", so_fields, so_filters,
                            "name asc, idx asc")
    except v01.StopRun as exc:
        stopped = str(exc)
        so_rows = []

    lines, cancelled_lines = [], 0
    seen_lines, seen_cancelled = set(), set()
    so_names = set()
    po_refs = defaultdict(set)          # po_no -> set of SO names referencing it
    for r in so_rows:
        code = r.get("item_code")
        name = r.get("name")
        if not code or not name:
            continue
        line_key = r.get("line_id") or f"{name}|{r.get('idx')}|{code}"
        if int(r.get("docstatus") or 0) == 2 or r.get("status") == "Cancelled":
            if line_key not in seen_cancelled:
                seen_cancelled.add(line_key)
                cancelled_lines += 1
            continue
        line_id = line_key
        if line_id in seen_lines:
            continue
        seen_lines.add(line_id)
        so_names.add(name)
        po_no = str(r.get("po_no") or "").strip()
        if po_no:
            po_refs[po_no].add(name)
        lines.append(dict(
            line_id=line_id,
            so_hash=v01.sha(name),
            line_hash=v01.sha(line_id),
            so_name=name,
            month=d(r.get("transaction_date"))[:7],
            period="H1" if d(r.get("transaction_date"))[:7] <= "2026-06" else "H2",
            internal=bool(r.get("is_internal_customer")),
            po_no=po_no,
            item=code,
            demand=n(r.get("qty")),
            uom=uom(r.get("uom")) or uom(r.get("stock_uom")),
            delivered_field=n(r.get("delivered_qty")),
            delivery_date=d(r.get("delivery_date"))))

    items = sorted({x["item"] for x in lines})

    # ---- 2. explicitly linked documents -----------------------------
    po_rows, wo_rows, dn_rows, dp_rows = [], [], [], []
    if not stopped and lines:
        try:
            po_rows = fetch_named(
                c, "Purchase Order",
                ["name", "docstatus", "status", "items.name as line_id",
                 "items.idx", "items.item_code", "items.qty", "items.uom",
                 "items.stock_uom"],
                ["name"], list(po_refs), "name asc, idx asc")
        except v01.StopRun as exc:
            stopped = str(exc)

    if not stopped and lines:
        try:
            wo_rows = fetch_named(
                c, "Work Order",
                ["name", "creation", "docstatus", "status", "sales_order",
                 "production_item", "qty", "produced_qty", "stock_uom"],
                ["sales_order"], sorted(so_names), "name asc")
        except v01.StopRun as exc:
            stopped = str(exc)

    if not stopped and lines:
        try:
            dn_rows = fetch_named(
                c, "Delivery Note",
                ["name", "docstatus", "status", "items.name as line_id",
                 "items.idx", "items.so_detail", "items.against_sales_order",
                 "items.item_code", "items.qty", "items.uom", "items.stock_uom"],
                ["Delivery Note Item", "against_sales_order"], sorted(so_names),
                "name asc, idx asc")
        except v01.StopRun as exc:
            stopped = str(exc)

    if not stopped and lines:
        try:
            dp_rows = fetch_named(
                c, "Delivery Plan",
                ["name", "docstatus", "status", "items.name as line_id",
                 "items.idx", "items.sales_order", "items.so_detail",
                 "items.item_code", "items.qty", "items.uom"],
                ["Delivery Plan Item", "sales_order"], sorted(so_names),
                "name asc, idx asc")
        except v01.StopRun as exc:
            stopped = str(exc)

    # ---- 3. indexes --------------------------------------------------
    po_by_name = defaultdict(list)
    po_docstatus = Counter()
    for r in po_rows:
        po_docstatus[r.get("docstatus")] += 1
        if r.get("item_code"):
            po_by_name[r["name"]].append(dict(
                item=r["item_code"], qty=n(r.get("qty")),
                uom=uom(r.get("uom")) or uom(r.get("stock_uom")),
                docstatus=int(r.get("docstatus") or 0)))

    lines_of_item = Counter((x["so_name"], x["item"]) for x in lines)
    wo_by_so = defaultdict(list)
    wo_docstatus = Counter()
    for r in wo_rows:
        wo_docstatus[r.get("docstatus")] += 1
        wo_by_so[r.get("sales_order")].append(dict(
            item=r.get("production_item"), qty=n(r.get("qty")),
            produced=n(r.get("produced_qty")),
            uom=uom(r.get("stock_uom")),
            docstatus=int(r.get("docstatus") or 0)))

    dn_by_detail = defaultdict(list)     # so_detail -> rows
    dn_by_so_item = defaultdict(list)    # (so, item) -> rows without so_detail
    dn_stat = Counter()
    for r in dn_rows:
        st = int(r.get("docstatus") or 0)
        dn_stat[st] += 1
        row = dict(item=r.get("item_code"), qty=n(r.get("qty")),
                   uom=uom(r.get("uom")) or uom(r.get("stock_uom")), docstatus=st)
        if r.get("so_detail"):
            dn_by_detail[r["so_detail"]].append(row)
        else:
            dn_by_so_item[(r.get("against_sales_order"), r.get("item_code"))].append(row)

    dp_detail = set()
    dp_stat = Counter()
    for r in dp_rows:
        dp_stat[int(r.get("docstatus") or 0)] += 1
        if r.get("so_detail"):
            dp_detail.add(r["so_detail"])

    # ---- 4. per-line conservation ------------------------------------
    out_rows = []
    for x in lines:
        rec = dict(x)
        for k in ("so_name", "po_no", "line_id", "delivery_date"):
            rec.pop(k, None)

        # --- delivery side (explicit DN only) ---
        dn = list(dn_by_detail.get(x["line_id"], []))
        ambiguous_dn = False
        if not dn:
            cand = dn_by_so_item.get((x["so_name"], x["item"]), [])
            if cand:
                if lines_of_item[(x["so_name"], x["item"])] > 1:
                    ambiguous_dn = True      # cannot say which line it belongs to
                else:
                    dn = list(cand)
        submitted = [r for r in dn if r["docstatus"] == 1]
        draft = [r for r in dn if r["docstatus"] == 0]
        cancelled = [r for r in dn if r["docstatus"] == 2]
        ok_same_uom = [r for r in submitted if r["uom"] == x["uom"]]
        uom_bad = len(submitted) - len(ok_same_uom)
        delivered_obs = sum(r["qty"] for r in ok_same_uom)
        remaining_obs = x["demand"] - delivered_obs
        identity_ok = abs((delivered_obs + remaining_obs) - x["demand"]) <= TOL
        field_gap = x["delivered_field"] - delivered_obs

        if not dn:
            conservation = "no_dn_unverified" if not ambiguous_dn else "dn_ambiguous"
        elif uom_bad:
            conservation = "uom_mismatch"
        elif abs(field_gap) <= TOL:
            conservation = "matched"
        else:
            conservation = "field_mismatch"

        # --- supply side (explicit PO / WO only) ---
        po_qty, po_resolved, po_uom_bad = 0.0, False, 0
        po_shared = False
        if x["po_no"]:
            po_lines = po_by_name.get(x["po_no"], [])
            if po_lines:
                po_resolved = True
                mine = [p for p in po_lines if p["item"] == x["item"]]
                po_shared = len(po_refs.get(x["po_no"], ())) > 1
                for p in mine:
                    if p["uom"] == x["uom"]:
                        po_qty += p["qty"]
                    else:
                        po_uom_bad += 1

        wo_qty, wo_draft, wo_produced = 0.0, 0.0, 0.0
        wo_uom_bad, wo_shared, wo_seen = 0, False, 0
        for w in wo_by_so.get(x["so_name"], []):
            if w["item"] != x["item"]:
                continue
            wo_seen += 1                     # explicit link evidence, any docstatus
            if w["docstatus"] == 2:
                continue                     # cancelled WO: counted, never summed
            if lines_of_item[(x["so_name"], x["item"])] > 1:
                wo_shared = True
                continue
            if w["uom"] == x["uom"]:
                if w["docstatus"] == 1:
                    wo_qty += w["qty"]        # submitted: planned qty
                    wo_produced += w["produced"]
                else:
                    wo_draft += w["qty"]      # draft: recorded, not used in ratio
            else:
                wo_uom_bad += 1

        has_po = po_qty > 0 or po_uom_bad > 0
        has_wo = wo_qty > 0 or wo_uom_bad > 0
        source = ("both" if (has_po and has_wo) else
                  "po" if has_po else "wo" if has_wo else "none")
        shared = po_shared or wo_shared     # DN ambiguity is a delivery-side issue
        dp_linked = x["line_id"] in dp_detail

        # --- observation status (explicit, RESOLVED links only) ---
        linked = bool(dn) or wo_seen > 0 or dp_linked or po_resolved
        supply_qty, ratio, ratio_class = None, None, "no_link"
        if not linked:
            ratio_class = "unobserved"
        elif po_uom_bad or wo_uom_bad:
            ratio_class = "uom_mismatch"
        elif shared:
            ratio_class = "shared"
        elif source == "both":
            ratio_class = "multi_source"
        elif source in ("po", "wo"):
            supply_qty = po_qty if source == "po" else wo_qty
            if x["demand"] > 0:
                ratio = supply_qty / x["demand"]
                ratio_class = ("over" if ratio > OVER else
                               "under" if ratio < UNDER else "normal")
            else:
                ratio_class = "zero_demand"
        elif wo_draft > 0:
            ratio_class = "draft_only"      # plan exists but only as a draft
        else:
            ratio_class = "no_supply_qty"    # linked, but no attributable qty

        rec.update(dict(
            dn_submitted_qty=round(delivered_obs, 3),
            dn_draft_lines=len(draft), dn_cancelled_lines=len(cancelled),
            dn_uom_mismatch=uom_bad,
            remaining_obs=round(remaining_obs, 3),
            identity_ok=identity_ok,
            field_gap=round(field_gap, 3),
            conservation=conservation,
            po_present=int(bool(x["po_no"])),
            po_resolved=int(po_resolved),
            po_qty=round(po_qty, 3),
            po_uom_mismatch=po_uom_bad,
            po_shared=int(po_shared),
            wo_lines=wo_seen,
            wo_planned_qty=round(wo_qty, 3),
            wo_draft_qty=round(wo_draft, 3),
            wo_produced_qty=round(wo_produced, 3),
            wo_uom_mismatch=wo_uom_bad,
            wo_shared=int(wo_shared),
            dp_linked=int(dp_linked),
            explicit_linked=int(linked),
            supply_source=source,
            supply_qty=(round(supply_qty, 3) if supply_qty is not None else ""),
            ratio=(round(ratio, 4) if ratio is not None else ""),
            ratio_class=ratio_class))
        out_rows.append(rec)

    out_rows.sort(key=lambda r: (r["month"], r["internal"], r["so_hash"],
                                 r["item"], r["line_hash"]))

    fields = ["so_hash", "line_hash", "month", "period", "internal", "item",
              "demand", "uom", "delivered_field", "dn_submitted_qty",
              "dn_draft_lines", "dn_cancelled_lines", "dn_uom_mismatch",
              "remaining_obs", "identity_ok", "field_gap", "conservation",
              "po_present", "po_resolved", "po_qty", "po_uom_mismatch",
              "po_shared", "wo_lines", "wo_planned_qty", "wo_draft_qty",
              "wo_produced_qty",
              "wo_uom_mismatch", "wo_shared", "dp_linked", "explicit_linked",
              "supply_source", "supply_qty", "ratio", "ratio_class"]
    csv_path = OUT / "qty_conservation.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()[:16]

    # ---- 5. aggregates ------------------------------------------------
    def stats(sel):
        observed = [x for x in sel if x["explicit_linked"]]
        ratios = [x["ratio"] for x in sel
                  if isinstance(x["ratio"], float)]
        q = quantiles(ratios)
        return dict(
            rows=len(sel), observed=len(observed),
            unobserved=len(sel) - len(observed),
            conservation=Counter(x["conservation"] for x in sel),
            ratio_class=Counter(x["ratio_class"] for x in sel),
            q=q,
            over=sum(1 for v in ratios if v > OVER),
            under=sum(1 for v in ratios if v < UNDER),
            shared=sum(1 for x in sel if x["ratio_class"] == "shared"),
            uom_bad=sum(1 for x in sel if x["ratio_class"] == "uom_mismatch"),
            exact_one=sum(1 for v in ratios if abs(v - 1.0) <= TOL),
            po_unresolved=sum(1 for x in sel
                              if x["po_present"] and not x["po_resolved"]),
            po_resolved=sum(1 for x in sel if x["po_resolved"]),
            dp_linked=sum(1 for x in sel if x["dp_linked"]),
            wo_item_linked=sum(1 for x in sel if x["wo_lines"] > 0),
            dn_linked=sum(1 for x in sel
                          if x["conservation"] in ("matched", "field_mismatch")),
            dn_cancelled=sum(x["dn_cancelled_lines"] for x in sel))

    monthly = []
    for m in sorted({x["month"] for x in out_rows}):
        for internal in (False, True):
            sel = [x for x in out_rows if x["month"] == m and x["internal"] == internal]
            if sel:
                monthly.append(dict(month=m, internal=internal, **stats(sel)))
    half = []
    for p in ("H1", "H2"):
        for internal in (False, True):
            sel = [x for x in out_rows if x["period"] == p and x["internal"] == internal]
            if sel:
                half.append(dict(period=p, internal=internal, **stats(sel)))
    overall = {lab: stats([x for x in out_rows if x["internal"] == i])
               for i, lab in ((False, "外部"), (True, "内部"))}

    def lab(internal):
        return "内部" if internal else "外部"

    elapsed = round(time.time() - c.started, 1)

    # ---- 6. report ----------------------------------------------------
    L = ["---", "okf: v0.1", "type: Report",
         "title: SO 行显式关联的数量守恒核查",
         "date: 2026-10-22", "owner: claude-worker",
         "status: 只读完成；只用显式关联；不作超补/缺补结论",
         "artifacts:",
         "  - experiments/auto_order/check_qty_conservation.py",
         "  - out/auto_order/qty_conservation.csv",
         "---", "",
         "# SO 行显式关联的数量守恒核查", "",
         "> **边界（先读）**：只核对**单据显式关联**与**算术**。"
         "无法显式关联的行一律记「未观测」，不猜测同物料即同一需求。"
         "本报告**不**用库存历史判断真实超补或缺补，也不判断到货是否及时。", "",
         "## 0. 预算、范围与复现", "",
         f"- 请求 **{c.gets}** / {MAX_GETS}；耗时 **{elapsed} s**；单线程；间隔 {args.sleep} s；"
         f"停止原因：{c.stop_reason or '无（正常完成）'}",
         f"- 范围：`transaction_date` ∈ [2026-01-01, 2026-09-30] 的**已提交、非取消** SO 行；"
         f"同期已取消 SO 行 **{cancelled_lines}** 行单独统计、不进守恒",
         f"- SO 行 **{len(out_rows)}**（外部 {overall['外部']['rows']} / 内部 {overall['内部']['rows']}）；"
         f"涉及物料 **{len(items)}**",
         f"- 文档取数：PO {len(po_rows)} 行（docstatus {dict(sorted(po_docstatus.items()))}）、"
         f"WO {len(wo_rows)} 张（{dict(sorted(wo_docstatus.items()))}）、"
         f"DN 行 {len(dn_rows)}（{dict(sorted(dn_stat.items()))}）、"
         f"DP 行 {len(dp_rows)}（{dict(sorted(dp_stat.items()))}）",
         f"- 单位口径：需求/供给双方 UOM 字符串必须相同才相加；不一致记 `uom_mismatch`，"
         f"该记录**不参与**比值，但计数保留",
         f"- 任务口径：DN 只计 docstatus=1；草稿/已取消另计。共享（同一 `po_no` 关联多张 SO、"
         f"同一 WO 对应同一 SO 多行同物料、DN 无 `so_detail` 且多行同物料）一律不计入单行比值",
         f"- CSV 内容哈希（sha256 前 16 位）：`{digest}`", "",
         "```bash",
         "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_qty_conservation.py",
         "```", "",
         "## 1. 守恒恒等式（逐行，仅显式 DN 关联）", "",
         "| 结果 | 外部 | 内部 | 说明 |",
         "|---|---:|---:|---|"]
    for lab_, key, note in (
            ("matched", "matched", "`delivered_obs + remaining_obs = demand`，且与 `delivered_qty` 一致"),
            ("field_mismatch", "field_mismatch", "恒等式成立但与存储的 `delivered_qty` 差额 > 容差"),
            ("no_dn_unverified", "no_dn_unverified", "无显式关联 DN，无法核验（不计入守恒）"),
            ("dn_ambiguous", "dn_ambiguous", "DN 只有 SO+物料级关联，且该 SO 同物料多行，无法归属"),
            ("uom_mismatch", "uom_mismatch", "DN 单位与 SO 行单位不一致")):
        e = overall["外部"]["conservation"][key]
        i = overall["内部"]["conservation"][key]
        L.append(f"| {lab_} | {e} | {i} | {note} |")
    L += ["", "## 2. 按月 × 内外部：观测与比值", "",
          "| 月份 | 内/外 | 行数 | 显式关联 | 未观测 | 比值样本 | 中位数 | >1.2 | <0.9 | 共享 | UOM | PO 未解析 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in monthly:
        med = x["q"]["median"] if x["q"] else None
        L.append(f"| {x['month']} | {lab(x['internal'])} | {x['rows']} | {x['observed']} | "
                 f"{x['unobserved']} | {x['q']['n'] if x['q'] else 0} | {num(med)} | "
                 f"{x['over']} | {x['under']} | {x['shared']} | {x['uom_bad']} | "
                 f"{x['po_unresolved']} |")
    L += ["", "## 3. 比值分布（仅单来源、同单位、可归属的行）", "",
          "| 范围 | 内/外 | n | min | p25 | 中位 | p75 | max | >1.2 | <0.9 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label_, x in (("外部", overall["外部"]), ("内部", overall["内部"])):
        q = x["q"]
        L.append(f"| 全期 | {label_} | {q['n'] if q else 0} | "
                 f"{num(q['min']) if q else '—'} | {num(q['p25']) if q else '—'} | "
                 f"{num(q['median']) if q else '—'} | {num(q['p75']) if q else '—'} | "
                 f"{num(q['max']) if q else '—'} | {x['over']} | {x['under']} |")
    L += ["", "## 4. 上半年 vs 下半年（H2 仅 7–9 月）", "",
          "| 期间 | 内/外 | 行数 | 显式关联 | 未观测 | 比值中位数 | >1.2 | <0.9 |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in half:
        med = x["q"]["median"] if x["q"] else None
        L.append(f"| {x['period']} | {lab(x['internal'])} | {x['rows']} | {x['observed']} | "
                 f"{x['unobserved']} | {num(med)} | {x['over']} | {x['under']} |")
    L += ["", "## 5. 三条事实（附边界）", ""]

    e, i = overall["外部"], overall["内部"]
    ec, ic = e["conservation"], i["conservation"]
    L.append(f"1. **显式关联只能靠 WO/DN**：外部 {e['observed']}/{e['rows']}"
             f"（{pct(e['observed'] / e['rows'] if e['rows'] else None)}）、"
             f"内部 {i['observed']}/{i['rows']}"
             f"（{pct(i['observed'] / i['rows'] if i['rows'] else None)}）行有关联证据；"
             f"其余 **{e['unobserved']} / {i['unobserved']}** 行记「未观测」。"
             f"来源拆解：SO `po_no` 解析到 EN PO —— 外部 {e['po_resolved']} / 内部 {i['po_resolved']} 行"
             f"（**外部 {e['po_unresolved']} / 内部 {i['po_unresolved']} 行有 `po_no` 但无同名 PO**，"
             f"实测 `po_no` 是客户订单号不是 EN PO 单号）；Delivery Plan 关联 "
             f"{e['dp_linked']} / {i['dp_linked']} 行；WO 按 `sales_order` 且同物料 "
             f"{e['wo_item_linked']} / {i['wo_item_linked']} 行；DN 按 `so_detail` "
             f"{e['dn_linked']} / {i['dn_linked']} 行。")
    L.append(f"2. **守恒**：有显式 DN 的行里，外部 matched {ec['matched']}、field_mismatch "
             f"{ec['field_mismatch']}；内部 matched {ic['matched']}、field_mismatch {ic['field_mismatch']}；"
             f"无 DN 可核验的外部 {ec['no_dn_unverified']}、内部 {ic['no_dn_unverified']} 行；"
             f"DN 只有 SO+物料级关联且无法归属的 外部 {ec['dn_ambiguous']} / 内部 {ic['dn_ambiguous']} 行。"
             f"`delivered_obs + remaining_obs = demand` 恒成立，真正被检验的是它与存储 `delivered_qty` 是否一致。")
    eq, iq = e["q"], i["q"]
    L.append(f"3. **供给/需求比值**：可归属样本 外部 {eq['n'] if eq else 0} 行、内部 {iq['n'] if iq else 0} 行；"
             f"中位数 外部 {num(eq['median']) if eq else '—'}、内部 {num(iq['median']) if iq else '—'}；"
             f"其中恰好等于 1.0 的外部 {e['exact_one']} / 内部 {i['exact_one']} 行；"
             f">1.2 外部 {e['over']} / 内部 {i['over']} 行，<0.9 外部 {e['under']} / 内部 {i['under']} 行；"
             f"共享未计入 外部 {e['shared']} / 内部 {i['shared']} 行，UOM 不一致 "
             f"外部 {e['uom_bad']} / 内部 {i['uom_bad']} 行。"
             f"比值只说明单据上的数量关系，**不**说明库存是否真实超补或缺补。")
    if stopped:
        L += ["", f"> ⚠️ 本次运行被预算/故障中断（{stopped}），以上为**部分结果**。"]
    L += ["", "## 6. 方法要点", "",
          "- 只认显式字段：SO 表头 `po_no`、WO 表头 `sales_order`、DN `so_detail`/"
          "`against_sales_order`、DP `so_detail`；**不按同物料推断**。",
          "- 同一 `po_no` 被多张 SO 引用、同一 WO 面对同一 SO 多行同物料、DN 仅 SO+物料级关联——"
          "都记为共享/无法归属，**不重复计入**任何单行比值。",
          "- 有 PO 又有 WO 的行记 `multi_source`，**不把两者相加**（会重复计算）。",
          "- WO 只有**已提交**(docstatus=1)的计划量进入比值；草稿量单列 `wo_draft_qty`，"
          "已取消 WO 只计数不求和。`produced_qty` 仅记录——既往核查已发现该字段会失真。",
          "- 「显式关联」只认**能解析到具体单据/行**的证据：有 `po_no` 但查不到同名 PO 不算关联。",
          "- 分页按 `name asc, idx asc` 稳定排序，子表行 id 兜底去重；CSV 排序含行哈希，保证可复现。",
          "- 只读；CSV 只含哈希化 SO/行标识与物料编码，不含客户名与单据号。", ""]

    (OUT / "qty_conservation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote qty_conservation.csv / qty_conservation.md")
    print(f"requests={c.gets} elapsed={elapsed}s lines={len(out_rows)} "
          f"items={len(items)} cancelled={cancelled_lines} stopped={c.stop_reason} "
          f"csv_sha={digest}")
    if c.stop_reason:
        print("errors:", c.errors[-3:])
        print("by_path:", dict(c.by_path))
    for k in ("外部", "内部"):
        s = overall[k]
        q = s["q"]
        print(f"{k}: rows={s['rows']} observed={s['observed']} unobserved={s['unobserved']} "
              f"cons={dict(s['conservation'])} ratio_n={q['n'] if q else 0} "
              f"med={num(q['median']) if q else '—'} over={s['over']} under={s['under']} "
              f"shared={s['shared']} uom={s['uom_bad']}")


if __name__ == "__main__":
    main()
