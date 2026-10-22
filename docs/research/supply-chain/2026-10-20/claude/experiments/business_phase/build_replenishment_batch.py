#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full mother-set replenishment batch (1,328 SKUs) — tonight's deliverable.

Scope and status model
----------------------
1,237 mapped-eligible SKUs are computed. 29 UOM-unproven and 62 unmapped SKUs
are emitted with status C (out_of_scope_uom / out_of_scope_unmapped) — never
silently dropped.

Status:
  A  evidence sufficient for an approvable quantity  (this batch: 0 rows --
     business demand bounds G8 are still missing, so no row can be approved)
  B  conditional quantity under EXPLICIT assumptions (written per row)
  C  cannot be computed in the same unit, or the mapping is not eligible

Rules enforced here
-------------------
- SO is never netted against the forecast (overlap unproven); internal SO is not
  added as extra terminal demand.
- PO / intransit are scenario variables only, never blindly added.
- Unknown is null + a reason, never 0. "No intransit" is only an assumption.
- MOQ / cost are missing -> note "采购约束待定", never dressed up as an order qty.

Self-check: the 8 frozen representative SKUs must reproduce the balances already
published in N2 B1-B3 (345 / 55 / 181 / 6 / 0 / 0) before the full run starts.

Read-only inputs: destinations.json, ranking.json, plan.json, order_store.duckdb.
Outputs: replenishment_all.csv, replenishment_all.xlsx (if openpyxl exists),
summary.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT_DIR = CLAUDE_DIR / "out" / "business_phase"
DEST = OUT_DIR / "destinations.json"
RANKING = OUT_DIR / "ranking.json"
PLAN = OUT_DIR / "plan.json"
FREEZE = OUT_DIR / "ten_sample_freeze.json"

DECISION_DATE = date(2026, 10, 22)
ASOF = DECISION_DATE
WINDOW_FIRST, WINDOW_LAST = "2026-04", "2026-09"
LEAD_DAYS = (60, 90, 120)
DAY_MONTH = 30.4375
TEST_RE = re.compile(r"(^|[-_])test([-_]|$)", re.IGNORECASE)
PIECE_UOMS = ("个", "件", "套")

COLUMNS = [
    "SKU", "仓", "历史窗口", "预测方法", "未来需求(P50/P90)", "库存日期与数量",
    "PO已知量", "在产已知量", "出库已知量", "去重状态", "提前期情景(L60/L90/L120)",
    "建议补货数量或条件区间", "需要时间", "缺失字段与证据", "状态", "assumptions",
]


def _int(x) -> int:
    """DB row-level NULL -> 0 for aggregate sums only. Missing SKU rows are a
    different case and are handled upstream as UNKNOWN (never 0)."""
    return 0 if x is None else int(x)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def month_len(i: int) -> int:
    y, m = divmod(i, 12)
    return [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]


def window_weights(start: date, days: int) -> dict[int, float]:
    """Calendar bucket weights for [start, start+days); sums to days/30.4375-ish."""
    end = start + timedelta(days=days)
    out = {}
    cur = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    while cur <= last:
        ms = date(cur // 12, cur % 12 + 1, 1)
        nm = date((cur + 1) // 12, (cur + 1) % 12 + 1, 1)
        ov_s, ov_e = max(start, ms), min(end, nm)
        if ov_e > ov_s:
            out[cur] = (ov_e - ov_s).days / (nm - ms).days
        cur += 1
    return out


W = {d: window_weights(DECISION_DATE, d) for d in LEAD_DAYS}
WSUM = {d: sum(w.values()) for d, w in W.items()}
W90 = W[90]
WSUM90 = WSUM[90]


def mean3(y: list[float], n: int) -> float:
    k = min(3, n)
    return sum(y[n - k:n]) / k if k else 0.0


def conf_q(vals: list[float]) -> float:
    """Rolling-empirical / conformal-style upper quantile, level ceil((n+1)*0.9)/n."""
    n = len(vals)
    level = min(1.0, math.ceil((n + 1) * 0.9) / n)
    xs = sorted(vals)
    idx = min(n - 1, math.ceil(level * (n - 1) - 1e-12))
    return xs[idx]


def next_month_first(i: int) -> date:
    return date((i + 1) // 12, (i + 1) % 12 + 1, 1)


def residuals_for(y: list[float], first: int, last: int) -> tuple[list[float], list[float]]:
    """Same-shape 90-day window residuals with label availability applied.

    Returns (absolute residuals, relative residuals (A-F)/F)."""
    abs_r, rel_r = [], []
    for o in range(first + 3, last):
        dec = date((o + 1) // 12, (o + 1) % 12 + 1, 22)
        end = dec + timedelta(days=90)
        end_i = end.year * 12 + end.month - 1
        if end_i > last:            # target month not closed in the data
            continue
        if next_month_first(end_i) > ASOF:   # label not available at decision time
            continue
        m3 = mean3(y, o - first + 1)
        buckets = window_weights(dec, 90)   # same shape, translated to this origin
        F = m3 * sum(buckets.values())
        A = 0.0
        for idx, w in buckets.items():
            A += w * y[idx - first]
        if abs(F) < 1e-9:
            continue
        abs_r.append(A - F)
        rel_r.append((A - F) / F)
    return abs_r, rel_r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--csv", default=str(OUT_DIR / "replenishment_all.csv"))
    ap.add_argument("--xlsx", default=str(OUT_DIR / "replenishment_all.xlsx"))
    ap.add_argument("--summary", default=str(OUT_DIR / "summary.md"))
    args = ap.parse_args()

    db_path = Path(args.db)
    for p in (db_path, DEST, RANKING, PLAN, FREEZE):
        if not p.exists():
            raise SystemExit(f"missing input: {p}")
    db_hash_before = sha256(db_path)

    dest = json.loads(DEST.read_text(encoding="utf-8"))
    rank = json.loads(RANKING.read_text(encoding="utf-8"))
    plan = {r["sku"]: r for r in json.loads(PLAN.read_text(encoding="utf-8"))["rows"]}
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))

    rows = dest["rows"]
    eligible = [r for r in rows if r["destination"] == "mapped_eligible"]
    uom_bad = [r for r in rows if r["destination"] == "mapped_ineligible"]
    unmapped = [r for r in rows if r["destination"] == "unmapped"]
    if len(rows) != 1328 or len(eligible) != 1237 or len(uom_bad) != 29 or len(unmapped) != 62:
        raise SystemExit(f"scope mismatch: total={len(rows)} eligible={len(eligible)} "
                         f"uom={len(uom_bad)} unmapped={len(unmapped)}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # Full history up to 2026-09 is needed for rolling-origin residuals;
        # the 6-month window is only the frozen SALES metric.
        monthly = defaultdict(dict)
        for sku, ym, qty in con.execute("""
                SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
                FROM gs_orders
                WHERE despatch_date <= '2026-09-30'
                  AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
                GROUP BY 1,2""").fetchall():
            monthly[sku][ym] = float(qty)
        sale_window = {s: sum(v for m, v in d.items()
                              if WINDOW_FIRST <= m <= WINDOW_LAST)
                       for s, d in monthly.items()}
        stock = defaultdict(lambda: dict(available=0, intransit=0, waiting=0, defects=0,
                                         rows=0, warehouses=[]))
        for sku, wh, av, it, wt, df in con.execute("""
                SELECT sku, warehouse, available, intransit, waiting_shipment, defects
                FROM stock_latest""").fetchall():
            s = stock[sku]
            s["rows"] += 1
            s["available"] += _int(av)
            s["intransit"] += _int(it)
            s["waiting"] += _int(wt)
            s["defects"] += _int(df)
            s["warehouses"].append(dict(warehouse=wh, available=_int(av),
                                        intransit=_int(it)))
        po = defaultdict(lambda: dict(qty=0.0, lines=[], etas=[]))
        for sku, ponum, wh, qty, eta in con.execute("""
                SELECT goods_sku, ponum, warehouse, open_qty, will_arrive_date
                FROM tongtool_po WHERE open_qty > 0""").fetchall():
            p = po[sku]
            p["qty"] += float(qty)
            p["lines"].append(dict(ponum=ponum, warehouse=wh, qty=float(qty),
                                   eta=eta))
            p["etas"].append(eta)
        uom = {r[0]: r[1] for r in con.execute("SELECT item, uom FROM bom").fetchall()}
        master = {r[0] for r in con.execute("SELECT item FROM item_attr").fetchall()}
    finally:
        con.close()
    if sha256(db_path) != db_hash_before:
        raise SystemExit("DB changed during the run; refusing to publish")

    # ---------------- monthly series + forecasts ----------------------------
    last_i = ym_i(WINDOW_LAST)
    series = {}
    for r in rows:
        sku = r["sku"]
        by = monthly.get(sku, {})
        if not by:
            continue
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        y = [float(by.get(m, 0.0)) for m in months]
        series[sku] = dict(first=first, last=last_i, months=months, y=y)

    pooled_rel = []
    own_abs = {}
    for sku, s in series.items():
        a, rel = residuals_for(s["y"], s["first"], s["last"])
        own_abs[sku] = a
        pooled_rel.extend(rel)
    pooled_q = conf_q(pooled_rel) if len(pooled_rel) >= 3 else 0.0

    def forecast(sku: str):
        s = series.get(sku)
        if not s:
            return None
        m3 = mean3(s["y"], len(s["y"]))
        p50 = {d: m3 * WSUM[d] for d in LEAD_DAYS}
        own = own_abs.get(sku, [])
        if len(own) >= 3:
            lift = conf_q(own)
            method = "mean3 + rolling-90d conformal-style lift (own residuals)"
            status = "own"
        else:
            lift = m3 * pooled_q
            method = ("mean3 + pooled peer-relative conformal-style lift "
                      f"(own n={len(own)})")
            status = "pooled"
        p90 = p50[90] + max(0.0, lift)
        return dict(m3=m3, p50=p50, p90=p90, method=method, calib=status,
                    n_own=len(own), lift=round(lift, 2))

    # ---------------- self-check against the frozen 8 SKUs ------------------
    expected_balance = {}
    for name in ("n2_b1", "n2_b2", "n2_b3"):
        p = OUT_DIR / f"{name}.json"
        if p.exists():
            for c in json.loads(p.read_text(encoding="utf-8"))["chains"]:
                expected_balance[c["sku"]] = dict(
                    balance=c["computable_now"]["balance_available_minus_committed"],
                    source=name)
    for c in freeze["slots"]:
        sku = c.get("sku")
        if sku and sku not in expected_balance and sku in plan:
            expected_balance[sku] = dict(balance=plan[sku]["supply"]["supply_lower"]["value"],
                                         source="plan.supply_lower")
    selfcheck = []
    for sku, exp in sorted(expected_balance.items()):
        st = stock.get(sku, dict(available=0, waiting=0))
        got = round(st["available"] - st["waiting"], 2)
        selfcheck.append(dict(sku=sku, expected=exp["balance"], got=got,
                              match=(abs(got - exp["balance"]) < 1e-6),
                              source=exp["source"]))
    if not all(x["match"] for x in selfcheck):
        raise SystemExit(f"self-check failed: {[x for x in selfcheck if not x['match']]}")

    # ---------------- build rows -------------------------------------------
    out_rows = []

    def supply_notes(sku: str):
        st = stock.get(sku)
        p = po.get(sku)
        notes, assumptions = [], []
        if st is None:
            notes.append("无库存行（不等于 0）")
            avail = None
            assumptions.append("按“无库存记录”处理：库存未知（假设，不是 0）")
        else:
            avail = st["available"]
            if st["rows"] and avail == 0:
                notes.append("available=0 已证为 0（完整盘点快照内有该 SKU）")
        if p is None:
            po_qty = None
            assumptions.append("无未结 PO 记录，按 0 计（假设，不得表述为真实无 PO）")
        else:
            po_qty = p["qty"]
        if st is None or not any(w["intransit"] for w in st["warehouses"]):
            intr = None
            assumptions.append("无在途记录，按 0 计（假设，不得表述为真实无在途）")
        else:
            intr = st["intransit"]
        assumptions.append("在产 WO 未入快照，按 0 计（假设，可能低估供给）")
        return avail, po_qty, intr, notes, assumptions

    for r in rows:
        sku, d = r["sku"], r["destination"]
        st = stock.get(sku)
        p = po.get(sku)
        fc = forecast(sku)
        sale6 = sale_window.get(sku)
        avail, po_qty, intr, notes, assumptions = supply_notes(sku)
        dom_wh = None
        if st and st["warehouses"]:
            dom_wh = max(st["warehouses"], key=lambda w: (w["available"], w["intransit"]))["warehouse"]
        # dedup status
        if p and len(p["lines"]) > 1:
            qs = Counter(x["qty"] for x in p["lines"])
            dups = [q for q, n in qs.items() if n > 1]
        else:
            dups = []
        if dups:
            dedup = "duplicate_candidate_lines"
            dedup_note = f"未结 PO 存在同数量行 {dups}"
        elif p and intr is not None and intr > 0 and abs(intr - po_qty) < 1e-9:
            dedup = "suspected_duplicate"
            dedup_note = f"在途 {intr:g} = 未结 PO {po_qty:g}，疑似同一批"
        elif p is not None or (intr is not None and intr > 0):
            dedup = "unproven"
            dedup_note = "在途与 PO 数量不同或不可比，仍缺逐笔关单键"
        else:
            dedup = "not_applicable"
            dedup_note = "无在途、无未结 PO 记录（按假设处理）"

        missing = list(notes)
        missing.append(f"去重：{dedup_note}")
        missing.append("PO ETA 全表缺失（0/248 行有 will_arrive_date）")
        missing.append("在产 WO 不在快照")
        missing.append("需求上下界 G8 未提供（P50/P90 只是估计）")
        missing.append("MOQ/成本未提供 → 采购约束待定")

        if d == "mapped_eligible" and fc is not None:
            if avail is None:
                # Inventory unknown MUST NOT be treated as 0 (FULL-REVIEW major).
                status = "B_pending_inventory"
                qty_text = ""
                missing.append("库存未知，待核实（无库存行，未按 0 计算）")
                assumptions.append("库存未知：本行不给条件数量；补齐库存行后再算")
                demand_text = f"P50 {fc['p50'][90]:.2f}; P90 {fc['p90']:.2f}"
                method_text = fc["method"]
                lead_text = " / ".join(f"L{d} {fc['p50'][d]:.1f}" for d in LEAD_DAYS)
                status_reason = "pending_inventory"
            else:
                status = "B"
                # scenario quantities for PO / intransit are explicit assumptions,
                # never silent zeros for inventory
                po_s = 0.0 if po_qty is None else float(po_qty)
                intr_s = 0.0 if intr is None else float(intr)
                if dedup == "suspected_duplicate":
                    batch = max(po_s, intr_s)
                    assumptions.append("PO 与在途按同一批只计一次（去重假设）")
                elif dedup == "duplicate_candidate_lines":
                    batch = po_s / 2 + intr_s
                    assumptions.append("重复候选 PO 行按一笔计（假设）")
                else:
                    batch = po_s + intr_s
                    assumptions.append("PO 与在途按两批相加（未去重假设）")
                base = float(avail) + batch
                qty_low = max(0.0, round(fc["p50"][90] - base, 2))
                qty_high = max(0.0, round(fc["p90"] - float(avail), 2))
                if qty_high < qty_low:
                    qty_low, qty_high = qty_high, qty_low
                qty_text = f"{qty_low:g}–{qty_high:g}"
                demand_text = f"P50 {fc['p50'][90]:.2f}; P90 {fc['p90']:.2f}"
                method_text = fc["method"]
                lead_text = " / ".join(f"L{d} {fc['p50'][d]:.1f}" for d in LEAD_DAYS)
                status_reason = "conditional_on_assumptions"
        elif d == "mapped_eligible":
            status = "B"
            qty_text, demand_text, method_text, lead_text = "", "", "no history", ""
            assumptions.append("无 6 个月销售历史，无法给条件数量")
            status_reason = "no_history"
        else:
            status = "C"
            qty_text, demand_text, method_text, lead_text = "", "", "", ""
            status_reason = ("out_of_scope_uom" if d == "mapped_ineligible"
                             else "out_of_scope_unmapped")
            missing.append(f"scope: {status_reason}（不参与补货计算，保留在表内）")

        inv_text = ""
        if st is None:
            inv_text = "null（无库存行，不等于 0；未按 0 计算）"
        else:
            inv_text = (f"2026-10-22: available={avail}"
                        f"（SKU 跨仓汇总；仓列仅为标注，非分仓分配）"
                        + ("；已证为 0" if avail == 0 else ""))
        po_text = "" if po_qty is None else f"{po_qty:g}（{len(p['lines'])} 行，ETA 全缺）"
        if po_qty is None:
            po_text = "null（无未结 PO 记录；按 0 假设）"
        need_text = ("2026-10-22（已有待发订单）"
                     if (st and st["waiting"] > 0) else "")
        out_rows.append({
            "SKU": sku,
            "仓": dom_wh or "（无库存行）",
            "历史窗口": f"{WINDOW_FIRST}..{WINDOW_LAST}（6 完整月，despatch_date）",
            "预测方法": method_text,
            "未来需求(P50/P90)": demand_text,
            "库存日期与数量": inv_text,
            "PO已知量": po_text,
            "在产已知量": "",  # null: WO not in snapshot
            "出库已知量": (f"{sale6:g}" if sale6 is not None else ""),
            "去重状态": dedup,
            "提前期情景(L60/L90/L120)": lead_text,
            "建议补货数量或条件区间": qty_text,
            "需要时间": need_text,
            "缺失字段与证据": "；".join(missing),
            "状态": status,
            "assumptions": ("；".join(assumptions)
                            if status in ("B", "B_pending_inventory") else ""),
            "_sale6": (0.0 if sale6 is None else sale6),
            "_reason": status_reason,
        })

    if len(out_rows) != 1328:
        raise SystemExit(f"row count {len(out_rows)} != 1328")
    if len({r["SKU"] for r in out_rows}) != 1328:
        raise SystemExit("duplicate SKU in output")

    # ---------------- write CSV --------------------------------------------
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    # ---------------- xlsx (only if the dependency already exists) ----------
    xlsx_written = False
    try:
        import importlib.util
        if importlib.util.find_spec("openpyxl") is not None:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "replenishment_all"
            ws.append(COLUMNS)
            for r in out_rows:
                ws.append([r[c] for c in COLUMNS])
            ws.freeze_panes = "A2"
            wb.save(args.xlsx)
            xlsx_written = True
    except Exception as exc:  # never fail the batch because of xlsx
        print(f"xlsx skipped: {exc}")

    # ---------------- summary ----------------------------------------------
    total = len(out_rows)
    status_cnt = Counter(r["状态"] for r in out_rows)
    b_pending = status_cnt.get("B_pending_inventory", 0)
    b_total = status_cnt.get("B", 0) + b_pending
    total_sales = sum(r["_sale6"] for r in out_rows) or 1.0
    sales_by_status = Counter()
    for r in out_rows:
        # B_pending_inventory is a B sub-status
        key = "B" if r["状态"] == "B_pending_inventory" else r["状态"]
        sales_by_status[key] += r["_sale6"]
    blockers = Counter()
    for r in out_rows:
        for part in r["缺失字段与证据"].split("；"):
            key = part.split("：")[0].strip()
            if key:
                blockers[key] += 1
    reasons = Counter(r["_reason"] for r in out_rows if r["状态"] == "C")

    summary = [
        "---", "okf: v0.1", "type: Report",
        "title: 全母集补货建议批处理（1,328 SKU）摘要",
        f"date: {date.today().isoformat()}", "owner: claude-worker",
        "status: 今晚可交付首版；A=0，B 为条件数量，C 为范围外",
        "artifacts:", "  - out/business_phase/replenishment_all.csv",
        ("  - out/business_phase/replenishment_all.xlsx" if xlsx_written
         else "  - （xlsx 未生成：openpyxl 不可用）"),
        "---", "", "# 全母集批处理摘要", "",
        "## 1. 范围与计数", "",
        "| 项 | 值 |", "|---|---:|",
        f"| 输出行数 | {total:,} |",
        f"| SKU 数 | {len({r['SKU'] for r in out_rows}):,} |",
        f"| 映射合格（参与计算） | {len(eligible):,} |",
        f"| 单位待证（C） | {len(uom_bad):,} |",
        f"| 未映射（C） | {len(unmapped):,} |",
        f"| 1,237 + 29 + 62 | {len(eligible) + len(uom_bad) + len(unmapped):,} |", "",
        "## 2. 状态分布与销量占比", "",
        "| 状态 | 行数 | 6 个月净销量 | 销量占比 |", "|---|---:|---:|---:|",
    ]
    for st, n in (("A", status_cnt.get("A", 0)), ("B", b_total),
                  ("C", status_cnt.get("C", 0))):
        summary.append(f"| {st} | {n:,} | "
                       f"{sales_by_status.get(st, 0):,.0f} | "
                       f"{sales_by_status.get(st, 0) / total_sales:.1%} |")
    summary += [
        f"| ├─ 其中 B_pending_inventory（库存未知，数量留空） | {b_pending:,} | "
        f"— | — |",
        "", f"- **A = 0**：需求上下界（G8）未提供、在产不在快照，没有任何行达到"
        "“可审批数量”的证据门槛。这不是漏算，是按 R4 标准的结果。",
        f"- **{b_pending} 行待库存核实**：这些 SKU 在快照中没有库存行（库存未知，**不是 0**），"
        "建议数量留空，状态标 `B_pending_inventory`，不计入可执行数量。",
        "- **库存口径**：库存为 **SKU 跨仓汇总**（`stock_latest` 所有仓相加）；"
        "表里的「仓」列只是标注主仓，**不是分仓补货分配**。",
        f"- C 的原因分布：" + "、".join(f"{k} {v}" for k, v in reasons.items()), "",
                "## 3. 主要阻塞（按行计）", "",
                "| 阻塞项 | 行数 |", "|---|---:|"]
    for k, v in blockers.most_common(10):
        summary.append(f"| {k} | {v:,} |")
    summary += [
        "", "## 4. 自检（8 个冻结代表 SKU 与 N2 已发布结余对齐）", "",
        "| SKU | 期望结余 | 本批重算 | 来源 | 一致 |", "|---|---:|---:|---|---|",
    ]
    for x in selfcheck:
        summary.append(f"| `{x['sku']}` | {x['expected']} | {x['got']} | {x['source']} | "
                       f"{'✅' if x['match'] else '❌'} |")
    summary += [
        "", "## 5. 口径与限制", "",
        "- SO 与预测不重复冲减（重叠未证），内部 SO 不作额外终端需求。",
        "- PO / 在途只作情景变量；无记录时按 0 处理，但这是**假设**，行内 `assumptions` 明写。",
        "- 未知一律 null + 说明，不用 0 冒充；库存缺失时建议数量直接留空（B_pending_inventory）。",
        "- 库存是 SKU 跨仓汇总；「仓」列仅为标注，不是分仓分配。",
        "- “无在途”只是假设，不是真实无在途。",
        "- MOQ / 成本未提供：所有数量都标「采购约束待定」，不是订单量。",
        "- 提前期为 L60/L90/L120 情景（P50 口径），不是承诺到货时间。",
        "- 本表为聚合建议，不含原始订单明细。", "",
    ]
    Path(args.summary).write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"wrote {csv_path} ({csv_path.stat().st_size:,} bytes)")
    if xlsx_written:
        print(f"wrote {args.xlsx}")
    print(f"wrote {args.summary}")
    print("rows", total, "status", dict(status_cnt))
    print("selfcheck", len(selfcheck), "all match:",
          all(x["match"] for x in selfcheck))


if __name__ == "__main__":
    main()
