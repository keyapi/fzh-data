#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SO order-timing backtest using DOCUMENT DATES ONLY (READ-ONLY).

Scope: submitted (docstatus=1, status != Cancelled) Sales Order LINES whose
`transaction_date` falls in 2026-01-01 .. 2026-09-30. Rows are split by
`is_internal_customer` (external / internal) and are NOT otherwise filtered —
closed / completed orders stay in, because the question is about what happened
at order time, not about what is still open.

Per SO line we take: SO creation date, transaction date, delivery date, item,
qty, internal/external. For the same item we read EN Purchase Order and Work
Order records (creation date, qty, status, docstatus; docstatus=2 cancelled
records are ignored) and compute:

  a) `covered_before_delivery` — does ANY PO/WO for the item exist whose
     creation date is on or before the line delivery date? true / false /
     null (null only when the delivery date itself is unknown).
  b) `lag_days` — SO creation -> earliest PO/WO creation for the item.
     Negative when the supply document predates the SO. Null when the item has
     no non-cancelled PO/WO at all. `lag_after_so_days` is reported next to it:
     SO creation -> earliest PO/WO created on/after the SO creation, i.e. the
     subset that could plausibly be a response to this order (null when none).
  c) `no_action` — line has a known delivery date and NO PO/WO created on or
     before it (this includes the case of no PO/WO at all).

Aggregates: month x internal/external (coverage rate, median lag, no-action
rows, unknown-delivery rows) and 2026 H1 (01..06) vs H2 (07..09, PARTIAL —
the scope ends 2026-09-30, so H2 is three months, not six).

BOUNDARY (stated wherever the numbers are reported):
  * "has a PO/WO before the delivery date" does NOT mean the quantity was
    sufficient, nor that it arrived on time, nor that the PO/WO was placed for
    this order — the check is existence of any non-cancelled supply document
    with an earlier creation date, including documents that predate the SO.
  * "no PO/WO before delivery" does NOT mean a missed order — the item may
    have been covered from stock, pre-built, or transferred internally.
  Only observable facts are reported; no causal claim is made.

Budget: <=200 GET, single-threaded, 200 ms interval, stop on timeout / 5xx /
auth error. On a stop the partial result is still written and marked partial.

Outputs:
  out/auto_order/order_timing.csv
  out/auto_order/order_timing_report.md
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
import build_order_suggestions as v01  # noqa: E402  (env loader / client / list_all)

OUT = HERE.parents[2] / "out" / "auto_order"
MAX_GETS = 200
PAGE = 200                     # falls back to whatever the server returns
SCOPE_FROM = "2026-01-01"
SCOPE_TO = "2026-10-01"        # exclusive
CHUNK = 60                     # item codes per PO/WO query


def d(s):
    return str(s or "")[:10]


def days_between(a, b):
    """b - a in whole days; None when either side is unusable."""
    try:
        da = datetime.strptime(a[:10], "%Y-%m-%d").date()
        db = datetime.strptime(b[:10], "%Y-%m-%d").date()
        return (db - da).days
    except Exception:
        return None


def list_flat(c, doctype, fields, filters, order):
    """list_all with the page size this run is allowed to use.

    `order` MUST be a total order (parent name + child idx) — paginating a
    joined parent/child query on `name asc` alone repeats and drops rows at
    page boundaries.
    """
    out, start = [], 0
    while True:
        res = c.get(f"/api/resource/{doctype}",
                    {"fields": json.dumps(fields), "filters": json.dumps(filters),
                     "limit_page_length": PAGE, "limit_start": start,
                     "order_by": order})
        rows = (res or {}).get("data", []) if isinstance(res, dict) else []
        out.extend(rows)
        # stop when the server returned less than the page we asked for
        if len(rows) < PAGE:
            break
        start += len(rows)
    return out


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
    rows, items = [], []

    # ---- 1. SO lines in scope -------------------------------------------
    # NOTE: `delivery_date` exists on both the header and the child table; the
    # header one is aliased so the flattened child key stays `delivery_date`.
    # `items.name as line_id` is the unique child-row key used to drop page-boundary
    # repeats; `items.idx` gives pagination a total order together with the SO name.
    so_fields = ["name", "creation", "transaction_date", "docstatus", "status",
                 "delivery_date as hdr_dd", "is_internal_customer",
                 "items.name as line_id", "items.idx",
                 "items.item_code", "items.qty", "items.delivery_date"]
    so_filters = [["docstatus", "=", 1],
                  ["status", "not in", ["Cancelled"]],
                  ["transaction_date", ">=", SCOPE_FROM],
                  ["transaction_date", "<", SCOPE_TO]]
    try:
        so_rows = list_flat(c, "Sales Order", so_fields, so_filters,
                            "name asc, idx asc")
    except v01.StopRun as exc:
        stopped = str(exc)
        so_rows = []

    lines, seen_lines = [], set()
    for r in so_rows:
        code = r.get("item_code")
        if not code:
            continue
        line_id = r.get("line_id") or f"{r.get('name')}|{r.get('idx')}|{code}"
        if line_id in seen_lines:          # page-boundary repeat
            continue
        seen_lines.add(line_id)
        line_dd = d(r.get("delivery_date"))          # items.delivery_date
        head_dd = d(r.get("hdr_dd"))                 # header delivery_date
        dd, src = (line_dd, "line") if line_dd else (
            (head_dd, "header") if head_dd else ("", "none"))
        lines.append(dict(
            line_id=line_id,
            so_hash=v01.sha(r.get("name") or ""),
            so_creation=d(r.get("creation")),
            transaction_date=d(r.get("transaction_date")),
            status=r.get("status"),
            internal=bool(r.get("is_internal_customer")),
            item=code,
            qty=float(r.get("qty") or 0),
            delivery_date=dd,
            delivery_source=src))
    # a sold line with no item code or no transaction date cannot be placed
    lines = [x for x in lines if x["transaction_date"]]
    items = sorted({x["item"] for x in lines})

    # ---- 2. PO / WO supply records for those items -----------------------
    po_by_item = defaultdict(list)
    wo_by_item = defaultdict(list)
    po_docstatus = Counter()
    wo_docstatus = Counter()

    if not stopped:
        for chunk in v01._chunks(items, CHUNK):
            if stopped:
                break
            try:
                po_rows = list_flat(
                    c, "Purchase Order",
                    ["name", "creation", "docstatus", "status",
                     "items.name as line_id", "items.idx",
                     "items.item_code", "items.qty", "items.schedule_date"],
                    [["Purchase Order Item", "item_code", "in", chunk],
                     ["docstatus", "!=", 2]],
                    "name asc, idx asc")
            except v01.StopRun as exc:
                stopped = str(exc)
                break
            seen = set()
            for r in po_rows:
                code = r.get("item_code")
                if not code:
                    continue
                key = r.get("line_id") or (r.get("name"), code, d(r.get("creation")))
                if key in seen:
                    continue
                seen.add(key)
                po_docstatus[r.get("docstatus")] += 1
                po_by_item[code].append(dict(
                    date=d(r.get("creation")), status=r.get("status"),
                    docstatus=r.get("docstatus"),
                    qty=float(r.get("qty") or 0)))

        for chunk in v01._chunks(items, CHUNK):
            if stopped:
                break
            try:
                wo_rows = list_flat(
                    c, "Work Order",
                    ["name", "creation", "docstatus", "status", "production_item",
                     "qty", "produced_qty", "planned_end_date"],
                    [["production_item", "in", chunk],
                     ["docstatus", "!=", 2]],
                    "name asc")
            except v01.StopRun as exc:
                stopped = str(exc)
                break
            seen = set()
            for r in wo_rows:
                code = r.get("production_item")
                if not code:
                    continue
                key = (r.get("name"), d(r.get("creation")))
                if key in seen:
                    continue
                seen.add(key)
                wo_docstatus[r.get("docstatus")] += 1
                wo_by_item[code].append(dict(
                    date=d(r.get("creation")), status=r.get("status"),
                    docstatus=r.get("docstatus"),
                    qty=float(r.get("qty") or 0)))

    # ---- 3. per-line metrics --------------------------------------------
    out_rows = []
    for x in lines:
        supply = [s for s in (po_by_item.get(x["item"], []) + wo_by_item.get(x["item"], []))
                  if s["date"]]
        first_po = min((s["date"] for s in po_by_item.get(x["item"], []) if s["date"]),
                       default=None)
        first_wo = min((s["date"] for s in wo_by_item.get(x["item"], []) if s["date"]),
                       default=None)
        first = min((s["date"] for s in supply), default=None)
        # first supply document created ON/AFTER the SO creation — this is the
        # "supply action that could belong to this order" subset. Kept separate
        # because a document created years earlier is not a response to the SO.
        after = [s["date"] for s in supply
                 if x["so_creation"] and s["date"] >= x["so_creation"]]
        first_after = min(after, default=None)
        if first is None:
            first_type = "none"
        elif first_po == first_wo == first:
            first_type = "both"
        else:
            first_type = "PO" if first_po == first else "WO"

        # a) coverage — existence of ANY non-cancelled PO/WO created on or
        #    before the delivery date. Unknown only when the date is unknown.
        if not x["delivery_date"]:
            covered = None
        elif first is None:
            covered = False          # no supply document at all -> not covered
        else:
            covered = first <= x["delivery_date"]

        out_rows.append(dict(
            so_hash=x["so_hash"],
            month=x["transaction_date"][:7],
            period="H1" if x["transaction_date"][:7] <= "2026-06" else "H2",
            internal=x["internal"],
            item=x["item"],
            qty=round(x["qty"], 2),
            so_creation=x["so_creation"],
            transaction_date=x["transaction_date"],
            delivery_date=x["delivery_date"],
            delivery_source=x["delivery_source"],
            first_supply_date=first or "",
            first_supply_type=first_type,
            lag_days=(days_between(x["so_creation"], first)
                      if (first and x["so_creation"]) else None),
            first_after_so_date=first_after or "",
            lag_after_so_days=(days_between(x["so_creation"], first_after)
                               if (first_after and x["so_creation"]) else None),
            covered_before_delivery=covered,
            po_count=len(po_by_item.get(x["item"], [])),
            wo_count=len(wo_by_item.get(x["item"], [])),
            supply_statuses="|".join(sorted({str(s["status"]) for s in supply})),
            _line_id=x["line_id"]))     # deterministic tiebreaker, dropped below

    out_rows.sort(key=lambda r: (r["month"], r["internal"], r["so_hash"],
                                 r["item"], r["_line_id"]))
    for r in out_rows:
        r.pop("_line_id")

    fields = ["so_hash", "month", "period", "internal", "item", "qty",
              "so_creation", "transaction_date", "delivery_date", "delivery_source",
              "first_supply_date", "first_supply_type", "lag_days",
              "first_after_so_date", "lag_after_so_days",
              "covered_before_delivery", "po_count", "wo_count", "supply_statuses"]
    csv_path = OUT / "order_timing.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()[:16]

    # ---- 4. aggregates ---------------------------------------------------
    def stats(sel):
        known = [x for x in sel if x["covered_before_delivery"] is not None]
        cov = [x for x in known if x["covered_before_delivery"] is True]
        no_action = [x for x in known if x["covered_before_delivery"] is False]
        unknown = [x for x in sel if x["covered_before_delivery"] is None]
        lags = [x["lag_days"] for x in sel if x["lag_days"] is not None]
        lags_after = [x["lag_after_so_days"] for x in sel if x["lag_after_so_days"] is not None]
        return dict(rows=len(sel), known=len(known), covered=len(cov),
                    coverage_rate=(round(len(cov) / len(known), 4) if known else None),
                    median_lag=(round(statistics.median(lags), 1) if lags else None),
                    lag_n=len(lags),
                    lag_negative=sum(1 for v in lags if v < 0),
                    after_n=len(lags_after),
                    median_lag_after=(round(statistics.median(lags_after), 1)
                                      if lags_after else None),
                    no_action=len(no_action), unknown=len(unknown),
                    # split the "nothing before delivery" rows: no supply doc at
                    # all vs. a supply doc that was created too late
                    no_action_none=sum(1 for x in no_action
                                       if x["first_supply_type"] == "none"),
                    no_action_late=sum(1 for x in no_action
                                       if x["first_supply_type"] != "none"))

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

    def label(internal):
        return "内部" if internal else "外部"

    def pct(v):
        return "—" if v is None else f"{v * 100:.1f}%"

    def num(v):
        return "—" if v is None else f"{v:.1f}"

    overall = {lab: stats([x for x in out_rows if x["internal"] == i])
               for i, lab in ((False, "外部"), (True, "内部"))}
    ext_months = [x for x in monthly
                  if not x["internal"] and x["coverage_rate"] is not None and x["known"]]
    int_months = [x for x in monthly
                  if x["internal"] and x["coverage_rate"] is not None and x["known"]]
    worst_ext = min(ext_months, key=lambda x: (x["coverage_rate"], x["month"])) if ext_months else None
    worst_int = min(int_months, key=lambda x: (x["coverage_rate"], x["month"])) if int_months else None

    elapsed = round(time.time() - c.started, 1)

    # ---- 5. report -------------------------------------------------------
    L = ["---", "okf: v0.1", "type: Report",
         "title: SO 下单时点回测（只用单据日期）",
         "date: 2026-10-22", "owner: claude-worker",
         "status: 只读完成；观测事实，不判断“及时足够”或“漏单”",
         "artifacts:",
         "  - experiments/auto_order/order_timing_backtest.py",
         "  - out/auto_order/order_timing.csv",
         "---", "",
         "# SO 下单时点回测（只用单据日期）", "",
         "> **边界（先读）**：**有 PO/WO ≠ 及时足够**（只证明系统里存在一张更早创建的非取消供给单，"
         "数量、到货、是否为本单下单都未验证，甚至可能早于 SO）；"
         "**无 PO/WO ≠ 漏单**（可能由库存、预生产或调拨满足）。本报告只写观测事实。", "",
         "## 0. 预算、范围与复现", "",
         f"- 请求 **{c.gets}** / {MAX_GETS}；耗时 **{elapsed} s**；单线程；间隔 {args.sleep} s；"
         f"停止原因：{c.stop_reason or '无（正常完成）'}",
         f"- 范围：`transaction_date` ∈ [{SCOPE_FROM}, 2026-09-30]，docstatus=1 且 status≠Cancelled；"
         f"**不过滤已关闭/已完成**（问的是下单当时发生了什么）",
         f"- SO 行 **{len(out_rows)}**（外部 {overall['外部']['rows']} / 内部 {overall['内部']['rows']}）；"
         f"涉及物料 **{len(items)}**；PO/WO 按物料分块查询（每块 {CHUNK} 个）",
         f"- 供给单口径：Purchase Order + Work Order，**docstatus≠2（排除已取消）**，含草稿；"
         f"PO 行 {sum(po_docstatus.values())} 条（docstatus 分布 {dict(sorted(po_docstatus.items(), key=lambda k: str(k[0])))}）、"
         f"WO 行 {sum(wo_docstatus.values())} 条（{dict(sorted(wo_docstatus.items(), key=lambda k: str(k[0])))}）",
         f"- 交期口径：优先行级 `items.delivery_date`，缺失回退表头 `delivery_date`"
         f"（行级 {sum(1 for x in out_rows if x['delivery_source'] == 'line')} / "
         f"表头 {sum(1 for x in out_rows if x['delivery_source'] == 'header')} / "
         f"无 {sum(1 for x in out_rows if x['delivery_source'] == 'none')}）",
         f"- 月份/半年按 **transaction_date** 归属（与筛选口径一致）；`lag_days` 按 **SO creation** 起算",
         f"- CSV 内容哈希（sha256 前 16 位）：`{digest}`", "",
         "```bash",
         "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/order_timing_backtest.py",
         "```", "",
         "## 1. 按月 × 内外部：覆盖率与无动作行", "",
         "| 月份 | 内/外 | 行数 | 有交期 | 交期前有 PO/WO | 覆盖率 | 无动作行 | 交期未知 |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in monthly:
        L.append(f"| {x['month']} | {label(x['internal'])} | {x['rows']} | {x['known']} | "
                 f"{x['covered']} | {pct(x['coverage_rate'])} | {x['no_action']} | "
                 f"{x['unknown']} |")
    missing = sorted({"2026-%02d" % m for m in range(1, 10)}
                     - {x["month"] for x in monthly})
    if missing:
        L += ["", f"> 范围内 **{'、'.join(missing)}** 没有已提交的 SO 行（不是漏算）。"]
    L += ["", "## 1b. 按月 × 内外部：滞后（天）", "",
          "> `全部` = SO 创建日 → 该物料最早一张非取消 PO/WO；负值表示供给单早于 SO。"
          "`SO 后` 只统计在 SO 创建当日或之后创建的首张供给单，更接近“本单触发的动作”。", "",
          "| 月份 | 内/外 | 全部滞后中位数 | 其中负滞后行 | SO 后有供给行 | SO 后滞后中位数 |",
          "|---|---|---:|---:|---:|---:|"]
    for x in monthly:
        L.append(f"| {x['month']} | {label(x['internal'])} | {num(x['median_lag'])} | "
                 f"{x['lag_negative']} | {x['after_n']} | {num(x['median_lag_after'])} |")
    L += ["", "## 2. 2026 上半年 vs 下半年（H2 仅为 7–9 月，非整半年）", "",
          "> 范围止于 2026-09-30，**H2 只有 3 个月**；比较看比例与中位数，不要比绝对行数。", "",
          "| 期间 | 内/外 | 行数 | 有交期 | 覆盖率 | 无动作行 | 全部滞后中位数 | SO 后滞后中位数 |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in half:
        L.append(f"| {x['period']} | {label(x['internal'])} | {x['rows']} | {x['known']} | "
                 f"{pct(x['coverage_rate'])} | {x['no_action']} | "
                 f"{num(x['median_lag'])} | {num(x['median_lag_after'])} |")
    L += ["", "## 3. 三条事实（附边界）", ""]

    e, i = overall["外部"], overall["内部"]
    L.append(f"1. **覆盖率**（交期前存在任一非取消 PO/WO 的行 / 交期已知的行）："
             f"外部 **{e['covered']}/{e['known']}（{pct(e['coverage_rate'])}）**，"
             f"内部 **{i['covered']}/{i['known']}（{pct(i['coverage_rate'])}）**；"
             f"交期未知而行未计入分母：外部 {e['unknown']} 行、内部 {i['unknown']} 行。"
             f"该覆盖率是**存在性**口径，接近饱和，不能读成“按单及时供给”。")
    L.append(f"2. **滞后**：SO 创建日 → 最早供给单，外部中位数 **{num(e['median_lag'])} 天**"
             f"（{e['lag_n']} 行有供给单，其中早于 SO 的 **{e['lag_negative']}** 行），"
             f"内部中位数 **{num(i['median_lag'])} 天**（{i['lag_n']} 行，早于 SO 的 **{i['lag_negative']}** 行）；"
             f"若只看 SO 当日或之后创建的首张供给单，外部中位数 **{num(e['median_lag_after'])} 天**"
             f"（{e['after_n']} 行）、内部 **{num(i['median_lag_after'])} 天**（{i['after_n']} 行）。"
             f"负滞后只说明物料此前已被采购/生产过，不代表为本单下单。")
    worst_txt = []
    if worst_ext:
        worst_txt.append(f"外部最差 {worst_ext['month']}（{pct(worst_ext['coverage_rate'])}，"
                         f"{worst_ext['covered']}/{worst_ext['known']}）")
    if worst_int:
        worst_txt.append(f"内部最差 {worst_int['month']}（{pct(worst_int['coverage_rate'])}，"
                         f"{worst_int['covered']}/{worst_int['known']}）")
    L.append(f"3. **无动作与最差月份**：交期前没有任何 PO/WO 的行 外部 **{e['no_action']}**、"
             f"内部 **{i['no_action']}**（其中完全查不到供给单的 外部 {e['no_action_none']} / "
             f"内部 {i['no_action_none']}，供给单创建晚于交期的 外部 {e['no_action_late']} / "
             f"内部 {i['no_action_late']}）；按月看，{'；'.join(worst_txt) if worst_txt else '无可用月份'}。"
             f"无动作 ≠ 漏单（可能备货/调拨）；有动作 ≠ 及时足够（数量与到货未验证）。")
    if stopped:
        L.append("")
        L.append(f"> ⚠️ 本次运行被预算/故障中断（{stopped}），以上为**部分结果**，"
                 "覆盖率与无动作行不可当作完整口径。")
    L += ["", "## 4. 方法要点", "",
          "- 覆盖判定只看**存在性**与**创建日**：`min(creation) <= delivery_date`。"
          "不读库存、不读到货、不比数量（按任务设定“只用单据日期”）。",
          "- 月份与半年按 `transaction_date` 归属，保证与筛选范围自洽；"
          "`lag_days` 按 `creation` 起算（SO 草稿创建 → 首张供给单创建）。",
          "- PO 明细行按子表行 id 去重，WO 按 (单据名, 创建日) 去重；"
          "SO 行按子表行 id 去重。父表/子表 join 分页在 `name asc` 上不稳定（会重复并漏行），"
          "因此统一按 `name asc, idx asc` 排序，子表行 id 再兜底去重。",
          "- 不做任何写操作；CSV 只含哈希化 SO 标识与物料编码，不含客户名、不含 PO/WO 单号。", ""]

    (OUT / "order_timing_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {csv_path.name} / order_timing_report.md")
    print(f"requests={c.gets} elapsed={elapsed}s lines={len(out_rows)} items={len(items)} "
          f"stopped={c.stop_reason} csv_sha={digest}")
    for k in ("外部", "内部"):
        s = overall[k]
        print(f"{k}: rows={s['rows']} known={s['known']} covered={s['covered']} "
              f"coverage={s['coverage_rate']} median_lag={s['median_lag']} "
              f"neg={s['lag_negative']} median_lag_after={s['median_lag_after']} "
              f"after_n={s['after_n']} no_action={s['no_action']} unknown={s['unknown']}")


if __name__ == "__main__":
    main()
