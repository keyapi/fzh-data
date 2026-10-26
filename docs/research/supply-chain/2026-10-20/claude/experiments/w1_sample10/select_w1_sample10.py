#!/usr/bin/env python
"""W1 sample-10 selection — read-only, no quantities, no forecast.

Frozen rules (task 2026-10-23):
  universe        = plan.json rows (Top50 ∪ urgent exceptions = 122)
  main category   = first match in urgent -> overlap -> in_production -> PO -> zero_stock -> normal
  cross labels    = every other attribute, never a second slot
  sort key        = net_qty_6m desc (2026-04..09, despatch_date, zero-filled);
                    tie -> waiting_shipment desc -> sku asc
  slots           = 1 urgent, 2 overlap, 1 in_production, 1 PO(eta_verifiable),
                    1 PO(eta_uncertain), 2 zero_stock, 1 in_stock_sufficient,
                    1 in_stock_short
  no substitution = a slot that finds no eligible SKU is reported as shortfall

Outputs: stdout table + optional CSV (local only).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "out" / "business_phase"
WO_JSON = BASE / "wo_dn_coverage.json"

CATEGORY_ORDER = ["urgent", "overlap", "in_production", "PO", "zero_stock", "normal"]
FLAG_OF = {"urgent": "urgent", "overlap": "overlap", "in_production": "in_production",
           "PO": "po", "zero_stock": "zero_stock", "normal": "in_stock"}


def load():
    plan = json.loads((BASE / "plan.json").read_text(encoding="utf-8"))
    ranking = json.loads((BASE / "ranking.json").read_text(encoding="utf-8"))
    wo = json.loads(WO_JSON.read_text(encoding="utf-8"))
    return plan, ranking, wo


def build_rows(plan, ranking, wo):
    top = {r["sku"]: r for r in ranking["top50"]}
    urgent_rows = {r["sku"]: r for r in ranking["urgent_fulfilment_exceptions"]}
    wo_by_sku = {m["sku"]: m for m in wo["material_skus"]}

    rows = []
    for p in plan["rows"]:
        sku = p["sku"]
        st = p["stock"]
        t = top.get(sku)
        u = urgent_rows.get(sku)
        w = wo_by_sku.get(sku)
        net6 = t["net_qty_6m"] if t else None
        p50 = p["demand"].get("p50")
        avail = st["available"]
        it = st["intransit"]
        po_qty = st["open_po_qty"]
        wait = st["waiting_shipment"]

        flags = {
            "urgent": wait > 0,
            "overlap": po_qty > 0 and it > 0 and po_qty == it,
            "in_production": bool(w and w["open_wo_count"] > 0),
            "po": po_qty > 0,
            "zero_stock": avail == 0 and net6 is not None and net6 > 0,
            "in_stock": avail > 0,
        }
        main = next(c for c in CATEGORY_ORDER if flags[FLAG_OF[c]])
        rows.append(
            {
                "sku": sku,
                "main_category": main,
                "flags": flags,
                "rank_top50": t["rank"] if t else None,
                "net_qty_6m": net6,
                "p50_90d": p50,
                "available": avail,
                "intransit": it,
                "open_po_qty": po_qty,
                "open_po_lines": st["open_po_lines"],
                "waiting_shipment": wait,
                "urgent_waiting": u["waiting_shipment_units"] if u else None,
                "in_coverage_because": p["in_coverage_because"],
                "zero_stock_with_sales": t["zero_stock_with_sales"] if t else None,
            }
        )
    return rows, wo_by_sku


def sort_key(r):
    return (
        -(r["net_qty_6m"] if r["net_qty_6m"] is not None else -1),
        -(r["waiting_shipment"] or 0),
        r["sku"],
    )


SLOTS = [
    ("urgent", {}, "紧急履约"),
    ("overlap", {}, "多阶段重叠 #1"),
    ("overlap", {}, "多阶段重叠 #2"),
    ("in_production", {}, "有在产"),
    ("PO", {"eta": "verifiable"}, "有 PO · ETA 可验证"),
    ("PO", {"eta": "uncertain"}, "有 PO · ETA 不确定"),
    ("zero_stock", {}, "零库存但有历史销量 #1"),
    ("zero_stock", {}, "零库存但有历史销量 #2"),
    ("normal", {"stock": "sufficient"}, "有库存 · 表面充足"),
    ("normal", {"stock": "short"}, "有库存 · 可能不足"),
]


def eta_verifiable(_r):
    """No source exposes a PO arrival date: tongtool_po.will_arrive_date is null
    on 0/524 rows (248 open), no open line has any receipt, and there is no
    PO->DN/Shipment key. Kept as an explicit predicate so the gap is testable."""
    return False


def eligible(r, sub):
    if r["main_category"] is None:
        return False
    if "eta" in sub:
        return r["main_category"] == "PO" and (
            eta_verifiable(r) if sub["eta"] == "verifiable" else not eta_verifiable(r)
        )
    if "stock" in sub:
        if r["main_category"] != "normal":
            return False
        p50 = r["p50_90d"]
        if p50 is None:
            return False
        return r["available"] >= p50 if sub["stock"] == "sufficient" else r["available"] < p50
    return r["main_category"] is None or r["main_category"] == sub.get("_cat")


def select(rows):
    used = set()
    slots = []
    for cat, sub, label in SLOTS:
        cands = []
        for r in rows:
            if r["sku"] in used:
                continue
            if r["main_category"] != cat:
                continue
            if "eta" in sub:
                if sub["eta"] == "verifiable" and not eta_verifiable(r):
                    continue
                if sub["eta"] == "uncertain" and eta_verifiable(r):
                    continue
            if "stock" in sub:
                p50 = r["p50_90d"]
                if p50 is None:
                    continue
                if sub["stock"] == "sufficient" and not (r["available"] >= p50):
                    continue
                if sub["stock"] == "short" and not (r["available"] < p50):
                    continue
            cands.append(r)
        cands.sort(key=sort_key)
        pick = cands[0] if cands else None
        if pick:
            used.add(pick["sku"])
        slots.append({"label": label, "category": cat, "sub": sub, "pick": pick, "n_candidates": len(cands)})
    return slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=None, help="write row-level audit CSV here (local only)")
    args = ap.parse_args()

    plan, ranking, wo = load()
    rows, wo_by_sku = build_rows(plan, ranking, wo)
    slots = select(rows)

    print(f"{'slot':28s} {'category':14s} {'sku':34s} {'rank':>4s} {'net6':>6s} "
          f"{'avail':>6s} {'int':>5s} {'po':>5s} {'wait':>4s} {'cands':>5s}")
    for s in slots:
        p = s["pick"]
        if p is None:
            print(f"{s['label']:28s} {s['category']:14s} {'-- NO ELIGIBLE SAMPLE --':34s}")
            continue
        print(f"{s['label']:28s} {s['category']:14s} {p['sku']:34s} "
              f"{str(p['rank_top50']):>4s} {str(p['net_qty_6m']):>6s} {p['available']:>6} "
              f"{p['intransit']:>5} {p['open_po_qty']:>5.0f} {p['waiting_shipment']:>4} {s['n_candidates']:>5}")

    print("\ncategory counts over universe:")
    from collections import Counter
    for c, n in Counter(r["main_category"] for r in rows).most_common():
        print(f"  {c:14s} {n}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow([
                "slot", "category", "sub", "sku", "rank_top50", "net_qty_6m", "p50_90d",
                "available", "intransit", "open_po_qty", "open_po_lines", "waiting_shipment",
                "flag_urgent", "flag_overlap", "flag_in_production", "flag_po", "flag_zero_stock",
                "flag_in_stock", "in_coverage_because",
            ])
            for s in slots:
                p = s["pick"]
                if p is None:
                    w.writerow([s["label"], s["category"], s["sub"].get("eta") or s["sub"].get("stock") or "",
                                "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "NO_ELIGIBLE_SAMPLE"])
                    continue
                f = p["flags"]
                w.writerow([
                    s["label"], s["category"], s["sub"].get("eta") or s["sub"].get("stock") or "",
                    p["sku"], p["rank_top50"], p["net_qty_6m"], p["p50_90d"], p["available"],
                    p["intransit"], p["open_po_qty"], p["open_po_lines"], p["waiting_shipment"],
                    f["urgent"], f["overlap"], f["in_production"], f["po"], f["zero_stock"],
                    f["in_stock"], "|".join(p["in_coverage_because"]),
                ])
        print(f"\nCSV written: {args.csv}")


if __name__ == "__main__":
    main()
