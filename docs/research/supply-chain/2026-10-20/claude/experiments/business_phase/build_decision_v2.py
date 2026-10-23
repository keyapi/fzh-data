#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T3: SKU × warehouse supply/demand decision, with a PR#297-style baseline.

Design
------
- Granularity is SKU × warehouse. Demand is taken from that warehouse's own
  shipped history; a shared pool is NOT assumed transferable across warehouses.
  Cross-warehouse transfer is an explicit assumption and is OFF by default
  (`--allow-transfer` turns on a scenario column only; it never changes the
  default quantity).
- Demand: forecast is monthly mean (last 3 months, zero-filled per warehouse)
  scaled to the lead-time calendar window; P90 uses a conformal-style lift
  (own SKU residuals when >=3, otherwise pooled). SO is NOT netted against the
  forecast (overlap unproven) and internal SO is NOT added as extra demand;
  the before/after netting columns are therefore equal and say why.
- Supply: available (proven), intransit, open PO lines -- each type is deduped
  and reported separately; production is not in the snapshot and is a blocker.
- Lead-time scenarios: L60 / L90 / L120.
- PR#297 baseline (mature method): monthly demand rate × coverage period
  − available − intransit, re-implemented here on the same rows. Differences
  against our bounds-based quantity are reported per row with a reason.
- Purchasing constraints (MOQ / pack multiple / cost) are separate columns and
  are never applied to the suggested quantity.
- Status A / B / B_pending_inventory / C. Unknown is null + reason, never 0.

Outputs: decision_v2.csv, decision_v2.json, summary_v2.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
DEST = OUT / "destinations.json"
RANK = OUT / "ranking.json"
FIRST = OUT / "replenishment_all.csv"

DECISION_DATE = date(2026, 10, 22)
WINDOW_FIRST, WINDOW_LAST = "2026-04", "2026-09"
LEADS = (60, 90, 120)
ALLOW_TRANSFER = False          # shared pool is NOT transferable by default


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def month_len(i: int) -> int:
    y, m = divmod(i, 12)
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    return [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]


def window_weights(start: date, days: int) -> dict[int, float]:
    end = start + timedelta(days=days)
    out, cur = {}, start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    while cur <= last:
        ms = date(cur // 12, cur % 12 + 1, 1)
        nm = date((cur + 1) // 12, (cur + 1) % 12 + 1, 1)
        s, e = max(start, ms), min(end, nm)
        if e > s:
            out[cur] = (e - s).days / (nm - ms).days
        cur += 1
    return out


W = {d: window_weights(DECISION_DATE, d) for d in LEADS}
WSUM = {d: sum(w.values()) for d, w in W.items()}


def conf_q(vals: list[float]) -> float:
    n = len(vals)
    level = min(1.0, math.ceil((n + 1) * 0.9) / n)
    xs = sorted(vals)
    return xs[min(n - 1, math.ceil(level * (n - 1) - 1e-12))]


def _int(x) -> int:
    """DB row NULL -> 0 for aggregation only; a missing SKU/warehouse row is
    UNKNOWN and is handled upstream, never zeroed."""
    return 0 if x is None else int(x)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse_qty(text: str):
    """Parse the first-batch 'low–high' string; None when blank."""
    if not text or "–" not in text:
        return None
    a, b = text.split("–", 1)
    try:
        return float(a), float(b)
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--allow-transfer", action="store_true",
                    help="ONLY adds a transfer scenario column; default quantity unaffected")
    ap.add_argument("--csv", default=str(OUT / "decision_v2.csv"))
    ap.add_argument("--json", default=str(OUT / "decision_v2.json"))
    ap.add_argument("--md", default=str(OUT / "summary_v2.md"))
    args = ap.parse_args()
    allow_transfer = bool(args.allow_transfer)

    db = Path(args.db)
    db_hash = sha(db)
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    eligible = [r for r in dest["rows"] if r["destination"] == "mapped_eligible"]
    out_of_scope = [r for r in dest["rows"] if r["destination"] != "mapped_eligible"]
    first = {}
    if FIRST.exists():
        for r in csv.DictReader(open(FIRST, encoding="utf-8-sig")):
            first[r["SKU"]] = r

    con = duckdb.connect(str(db), read_only=True)
    try:
        wmap = {r[0]: r[1] for r in con.execute(
            "SELECT gs_warehouse, current_warehouse FROM warehouse_map").fetchall()}
        sales = defaultdict(dict)              # (sku, wh) -> {ym: qty}
        for sku, wh_raw, ym, qty in con.execute("""
                SELECT sku_tongtool, warehouse, substr(despatch_date,1,7), SUM(qty)
                FROM gs_orders
                WHERE despatch_date <= '2026-09-30'
                  AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
                GROUP BY 1,2,3""").fetchall():
            wh = wmap.get(wh_raw, wh_raw)
            sales[(sku, wh)][ym] = sales[(sku, wh)].get(ym, 0.0) + float(qty)
        stock = defaultdict(dict)
        for sku, wh, av, it, wt, df in con.execute("""
                SELECT sku, warehouse, available, intransit, waiting_shipment, defects
                FROM stock_latest""").fetchall():
            stock[sku][wh] = dict(available=_int(av), intransit=_int(it),
                                  waiting=_int(wt), defects=_int(df))
        po = defaultdict(list)
        for sku, wh, ponum, qty, eta in con.execute("""
                SELECT goods_sku, warehouse, ponum, open_qty, will_arrive_date
                FROM tongtool_po WHERE open_qty > 0""").fetchall():
            po[sku].append(dict(warehouse=wh, ponum=ponum, qty=float(qty), eta=eta))
        uom = {r[0]: r[1] for r in con.execute("SELECT item, uom FROM bom").fetchall()}
    finally:
        con.close()
    if sha(db) != db_hash:
        raise SystemExit("DB changed during the run")

    last_i = ym_i(WINDOW_LAST)
    # ---- SKU-level residual lift (same convention as the first batch) ------
    sku_series = {}
    for r in eligible:
        sku = r["sku"]
        by = defaultdict(float)
        for (s, wh), d in sales.items():
            if s != sku:
                continue
            for ym, q in d.items():
                by[ym] += q
        if not by:
            continue
        first_i = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first_i, last_i + 1)]
        y = np.array([by.get(m, 0.0) for m in months], dtype=float)
        sku_series[sku] = dict(first=first_i, last=last_i, y=y)
    pooled_rel = []
    own_abs = {}
    sku_rel = {}
    for sku, s in sku_series.items():
        y, first_i, last_i_ = s["y"], s["first"], s["last"]
        abs_r, rel_r = [], []
        for o in range(first_i + 3, last_i_):
            dec = date((o + 1) // 12, (o + 1) % 12 + 1, 22)
            end = dec + timedelta(days=90)
            end_i = end.year * 12 + end.month - 1
            if end_i > last_i_:
                continue
            if date((end_i + 1) // 12, (end_i + 1) % 12 + 1, 1) > DECISION_DATE:
                continue
            tr = o - first_i + 1
            m3 = float(np.mean(y[max(0, tr - 3):tr]))
            ww = window_weights(dec, 90)
            F = m3 * sum(ww.values())
            A = sum(wt * y[k - first_i] for k, wt in ww.items())
            if abs(F) < 1e-9:
                continue
            abs_r.append(A - F)
            rel_r.append((A - F) / F)
        own_abs[sku] = abs_r
        sku_rel[sku] = rel_r
        pooled_rel.extend(rel_r)
    pooled_q = conf_q(pooled_rel) if len(pooled_rel) >= 3 else 0.0

    rows, comparison = [], []
    for r in eligible:
        sku = r["sku"]
        item = r["mapped_item_code"]
        # only warehouses active in the frozen 6-month window (a warehouse used
        # only years ago is not an active stocking location and must not create a
        # fake "inventory unknown" row)
        wh_names = set()
        for (s, wh), d in sales.items():
            if s == sku and any(WINDOW_FIRST <= m <= WINDOW_LAST for m in d):
                wh_names.add(wh)
        for wh in (stock.get(sku, {}) or {}):
            wh_names.add(wh)
        if not wh_names:
            wh_names = {"（无库存与销售记录）"}
        # P90 lift is RELATIVE so a warehouse with zero demand stays zero
        # Relative lift is clipped: with very short own samples the ratio residual
        # can explode and would turn a warehouse-level P90 into nonsense.
        own_rel = sku_rel.get(sku, [])
        if len(own_rel) >= 10:
            rel_q = conf_q(own_rel)
            lift_basis = "own_relative"
        else:
            rel_q = pooled_q
            lift_basis = f"pooled_relative(n_own={len(own_rel)})"
        rel_lift = min(3.0, max(0.0, rel_q))
        sku_total_low = 0.0
        sku_total_high = 0.0
        for wh in sorted(wh_names):
            st = stock.get(sku, {}).get(wh)
            by = sales.get((sku, wh), {})
            months = [m for m in ("2026-07", "2026-08", "2026-09")]
            hist3 = [by.get(m, 0.0) for m in months]
            monthly_rate = sum(hist3) / 3.0
            dem_p50 = {d: monthly_rate * WSUM[d] for d in LEADS}
            dem_p90 = {d: dem_p50[d] * (1.0 + rel_lift) for d in LEADS}
            # supply
            polines = [x for x in po.get(sku, []) if x["warehouse"] == wh]
            po_qty = sum(x["qty"] for x in polines) if polines else None
            po_dups = None
            if polines:
                cnt = Counter(x["qty"] for x in polines)
                po_dups = sorted(q for q, n in cnt.items() if n > 1)
            intr = st["intransit"] if st is not None else None
            avail = st["available"] if st is not None else None
            waiting = st["waiting"] if st is not None else None
            # dedup statuses (kept per document type, never merged)
            if po_qty is None:
                po_dedup = "none_recorded"
            elif po_dups:
                po_dedup = f"duplicate_lines:{po_dups}"
            else:
                po_dedup = "lines_unique"
            if intr is None or intr == 0:
                intr_dedup = "none_recorded"
            elif po_qty is not None and intr > 0 and abs(intr - po_qty) < 1e-9:
                intr_dedup = "suspected_same_batch_as_po"
            else:
                intr_dedup = "no_line_key"
            prod = None
            prod_status = "work_order_not_in_snapshot"

            intr_for_pr = 0.0 if intr is None else float(intr)
            batch_val = None
            assumptions = []
            if avail is None:
                status = "B_pending_inventory"
                qty_lo = qty_hi = None
                missing_extra = "库存未知，待核实（无库存行，未按 0 计算）"
                assumptions.append("库存未知：本行不给条件数量（未按 0 计算）")
                assumptions.append("在产 WO 未入快照，按 0 计（假设）")
            else:
                status = "B"
                missing_extra = None
                po_s = 0.0 if po_qty is None else po_qty
                intr_s = 0.0 if intr is None else float(intr)
                if po_qty is None:
                    assumptions.append("无未结 PO 记录，按 0 计（假设）")
                if intr is None:
                    assumptions.append("无在途记录，按 0 计（假设）")
                assumptions.append("在产 WO 未入快照，按 0 计（假设）")
                if po_dups:
                    batch = po_s / 2 + intr_s
                    assumptions.append("重复候选 PO 行按一笔计（假设）")
                elif intr_dedup == "suspected_same_batch_as_po":
                    batch = max(po_s, intr_s)
                    assumptions.append("PO 与在途按同一批只计一次（去重假设）")
                else:
                    batch = po_s + intr_s
                    assumptions.append("PO 与在途按两批相加（未去重假设）")
                if len([h for h in hist3 if h > 0]) < 3:
                    assumptions.append("仓库级销量样本 <3 个月，月需求率按含 0 的近 3 月均值")
                qty_lo = max(0.0, round(dem_p50[90] - (float(avail) + batch), 2))
                qty_hi = max(0.0, round(dem_p90[90] - float(avail), 2))
                if qty_hi < qty_lo:
                    qty_lo, qty_hi = qty_hi, qty_lo
                batch_val = batch
            # PR#297-style baseline: rate x coverage - available - intransit
            pr = {}
            for d in LEADS:
                if avail is None:
                    pr[d] = None
                else:
                    cov = d / 30.0
                    pr[d] = round(max(0.0, monthly_rate * cov - float(avail)
                                      - intr_for_pr), 2)
            diff = None
            diff_reason = None
            if qty_lo is not None and pr[90] is not None:
                diff = round(qty_lo - pr[90], 2)
                if abs(diff) < 1e-9:
                    diff_reason = "same"
                else:
                    pieces = []
                    if po_qty is not None:
                        pieces.append(f"本方法在情景里按去重批计 PO/在途（批={0.0 if avail is None else batch:g}），PR297 只扣在途")
                    if intr is None:
                        pieces.append("PR297 把‘无在途’当 0，本方法仅作假设并标注")
                    if po_dups:
                        pieces.append("PO 存在重复候选行，本方法按一笔计")
                    pieces.append("本方法用 L90 窗口 P50，PR297 用 3 个月覆盖期（90/30）")
                    diff_reason = "；".join(pieces)
            transfer = "(off)"
            if allow_transfer:
                others = [w for w in wh_names if w != wh]
                surplus = 0.0
                for w2 in others:
                    st2 = stock.get(sku, {}).get(w2)
                    if st2 is not None:
                        surplus += max(0, st2["available"] - 0)
                transfer = f"scenario: {surplus:g} 可考虑跨仓（仍为假设，不生效）"
                assumptions.append("跨仓调拨情景（假设，默认不生效）")
            missing = [m for m in [
                None if avail is not None else "库存未知（无库存行）",
                "PO ETA 全表缺失（0/248 行有 will_arrive_date）" if polines else None,
                "在产 WO 不在快照",
                "MOQ/包装/成本未提供 → 采购约束待定",
                "共享池不默认跨仓可调拨（如需调拨须显式开启并单列假设）",
                "需求上下界 G8 未提供（P50/P90 为估计）",
                missing_extra,
            ] if m]
            rows.append({
                "SKU": sku, "仓": wh, "月需求率": round(monthly_rate, 4),
                "需求P50(冲减前)": round(dem_p50[90], 2),
                "需求P50(冲减后)": round(dem_p50[90], 2),
                "冲减说明": "SO 与预测重叠未证 → 不冲减；内部 SO 不作额外终端需求",
                "已承诺待发": waiting,
                "可用": avail, "在途": intr, "PO未结": po_qty, "在产": prod,
                "PO去重状态": po_dedup, "在途去重状态": intr_dedup,
                "在产状态": prod_status,
                "缺口L60": (round(dem_p50[60] - (float(avail) + batch_val), 2)
                          if batch_val is not None else None),
                "缺口L90": (round(dem_p50[90] - (float(avail) + batch_val), 2)
                          if batch_val is not None else None),
                "缺口L120": (round(dem_p50[120] - (float(avail) + batch_val), 2)
                           if batch_val is not None else None),
                "建议下限L90": qty_lo, "建议上限L90": qty_hi,
                "PR297_L60": pr[60], "PR297_L90": pr[90], "PR297_L120": pr[120],
                "与PR297差异L90": diff, "差异原因": diff_reason,
                "MOQ": None, "包装倍数": None, "成本": None,
                "跨仓调拨": transfer,
                "需要时间": ("2026-10-22（有待发订单）" if waiting else None),
                "缺失字段与证据": "；".join(missing),
                "状态": status,
                "assumptions": "；".join(assumptions) if status.startswith("B") else "",
                "_sku_lo": qty_lo, "_sku_hi": qty_hi,
            })
            if qty_lo is not None:
                sku_total_low += qty_lo
                sku_total_high += qty_hi
        # per-SKU comparison with the first batch (L90 range)
        if first.get(sku):
            old = parse_qty(first[sku].get("建议补货数量或条件区间", ""))
            comparison.append(dict(
                sku=sku, first_low=(old[0] if old else None),
                first_high=(old[1] if old else None),
                v2_low=round(sku_total_low, 2), v2_high=round(sku_total_high, 2),
                diff_low=(round(sku_total_low - old[0], 2) if old else None),
                reason=("粒度从 SKU 聚合改为 SKU×仓后求和；仓库级月需求率取该仓近 3 月均值，"
                        "与 SKU 级 mean3 不同；PO/在途仍按假设计入情景"),
            ))

    # C-class SKUs: one row each, kept in the table
    for r in out_of_scope:
        sku = r["sku"]
        rows.append({
            "SKU": sku, "仓": "（out_of_scope）", "月需求率": None,
            "需求P50(冲减前)": None, "需求P50(冲减后)": None,
            "冲减说明": "不参与计算", "已承诺待发": None, "可用": None,
            "在途": None, "PO未结": None, "在产": None,
            "PO去重状态": "not_computed", "在途去重状态": "not_computed",
            "在产状态": "not_computed",
            "缺口L60": None, "缺口L90": None, "缺口L120": None,
            "建议下限L90": None, "建议上限L90": None,
            "PR297_L60": None, "PR297_L90": None, "PR297_L120": None,
            "与PR297差异L90": None, "差异原因": None,
            "MOQ": None, "包装倍数": None, "成本": None, "跨仓调拨": None,
            "需要时间": None,
            "缺失字段与证据": f"scope: {r['destination']}（不参与计算，保留在表内）",
            "状态": "C", "assumptions": "",
            "_sku_lo": None, "_sku_hi": None,
        })

    columns = ["SKU", "仓", "月需求率", "需求P50(冲减前)", "需求P50(冲减后)", "冲减说明",
               "已承诺待发", "可用", "在途", "PO未结", "在产", "PO去重状态",
               "在途去重状态", "在产状态", "缺口L60", "缺口L90", "缺口L120",
               "建议下限L90", "建议上限L90", "PR297_L60", "PR297_L90", "PR297_L120",
               "与PR297差异L90", "差异原因", "MOQ", "包装倍数", "成本", "跨仓调拨",
               "需要时间", "缺失字段与证据", "状态", "assumptions"]
    csv_path = Path(args.csv)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    status_cnt = Counter(r["状态"] for r in rows)
    wh_cnt = len({r["仓"] for r in rows if r["状态"] != "C"})
    sku_cnt = len({r["SKU"] for r in rows if r["状态"] != "C"})
    changed = [c for c in comparison if c["diff_low"] not in (None, 0.0)]
    summary = [
        "---", "okf: v0.1", "type: Report",
        "title: T3 SKU×仓供需决策（含 PR#297 对拍基线）",
        f"date: {date.today().isoformat()}", "owner: claude-worker",
        "status: 决策表 only；A=0，B 为条件数量，C 为范围外",
        "artifacts:", "  - out/business_phase/decision_v2.csv",
        "  - out/business_phase/decision_v2.json", "---", "",
        "# T3 SKU×仓供需决策", "",
        "## 1. 粒度与行数", "",
        "| 项 | 值 |", "|---|---:|",
        f"| 行数 | {len(rows):,} |",
        f"| 合格 SKU × 仓行 | {sum(1 for r in rows if r['状态'] != 'C'):,} |",
        f"| 合格 SKU 数 | {sku_cnt:,} |",
        f"| 仓数 | {wh_cnt:,} |",
        f"| C 类（每 SKU 一行） | {status_cnt.get('C', 0):,} |", "",
        f"- 跨仓调拨：**默认关闭**（`--allow-transfer` 只增加情景列，不改变默认数量）。",
        "", "## 2. 状态分布", "",
        "| 状态 | 行数 |", "|---|---:|",
    ]
    for st in ("A", "B", "B_pending_inventory", "C"):
        summary.append(f"| {st} | {status_cnt.get(st, 0):,} |")
    summary += [
        "", "## 3. 需求与冲减", "",
        "- 月需求率 = 该仓近 3 个月净销量均值（含 0 填充）；P50_L = 月需求率 × 窗口权重和。",
        "- **不冲减 SO**：SO 与预测重叠未证；内部 SO 不作额外终端需求。"
        "表中“冲减前/后”两列因此相同，并在每行写明原因。",
        "- P90 = P50 + conformal-style lift（own ≥3 否则 pooled），是估计不是保证。", "",
        "## 4. 供给与去重", "",
        "- 可用（proven）、在途、未结 PO **分别**给去重状态；在产不在快照，单列阻塞。",
        "- 情景批：重复 PO 行按一笔；在途=PO 时按同批一次；否则两批相加（均写入 assumptions）。",
        "- 提前期：L60 / L90 / L120 三情景，缺口列见 CSV。", "",
        "## 5. PR#297 对拍（同一输入）", "",
        "- 基线公式：`月需求率 × 覆盖期 − 可用 − 在途`（覆盖期 = lead/30 月），本脚本在同一行上重算。",
        f"- 与我们的 L90 建议下限比较：**{sum(1 for r in rows if r['与PR297差异L90'] not in (None, 0.0)):,} 行不同**，"
        "逐行 `差异原因` 列写明（PO/在途计入方式、重复候选、覆盖期口径）。", "",
        "## 6. 采购约束", "",
        "- MOQ / 包装倍数 / 成本均为 null 并标注“采购约束待定”，**不进建议量**。", "",
        "## 7. 与首版对比", "",
        f"- 首版为 SKU 聚合口径；本版为 SKU×仓，逐 SKU 汇总后与首版比较："
        f"**{len(changed):,} 个 SKU 数量不同**（原因列在 decision_v2.json → comparison）。",
        "", "## 8. 明确不做", "",
        "- 不下单、不跨仓调拨、不把 PR297 差异当谁对谁错；差异只解释口径。",
        "- 不把 B 类条件数量当订单量；MOQ/成本未给前不可执行。", "",
    ]
    Path(args.md).write_text("\n".join(summary) + "\n", encoding="utf-8")

    json_path = Path(args.json)
    json_path.write_text(json.dumps(dict(
        schema_version="t3_decision_v2/1",
        generated_at=__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        inputs=dict(db=dict(path=str(db), sha256=db_hash),
                    destinations_sha256=sha(DEST), ranking_sha256=sha(RANK),
                    first_batch_sha256=(sha(FIRST) if FIRST.exists() else None)),
        settings=dict(allow_transfer_default=ALLOW_TRANSFER,
                      allow_transfer_run=allow_transfer,
                      granularity="SKU × warehouse",
                      leads=list(LEADS),
                      demand_rate="warehouse last-3-month mean (zero-filled)",
                      so_netting="not netted (overlap unproven); internal SO not added",
                      pr297_baseline="monthly rate × coverage(days/30) − available − intransit"),
        counts=dict(rows=len(rows), eligible_rows=sum(1 for r in rows if r["状态"] != "C"),
                    skus=sku_cnt, warehouses=wh_cnt, status=dict(status_cnt),
                    changed_vs_first=len(changed)),
        comparison=[c for c in comparison if c["diff_low"] not in (None, 0.0)][:200],
        rows_sample=rows[:5],
    ), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {csv_path} ({csv_path.stat().st_size:,} bytes)")
    print(f"wrote {json_path} and {args.md}")
    print("rows", len(rows), "eligible rows", sum(1 for r in rows if r["状态"] != "C"),
          "status", dict(status_cnt), "changed vs first", len(changed))


if __name__ == "__main__":
    main()
