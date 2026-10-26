#!/usr/bin/env python
"""Dump the frozen evidence for the W1 sample-10 (read-only).

Writes JSON to stdout -- pipe it to a local file. No DB writes, no EN access.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

DB = "D:/Work/fzh-order-store/order_store.duckdb"
BASE = Path(__file__).resolve().parents[2] / "out" / "business_phase"

SKUS = [
    "TT0031038K0062927",
    "C/Linen-Natural-100-688-wow",
    "TT0312701K0064561",
    "CENCord995-DKGrey-97",
    "C/Cord-White-100-706-wow",
    "C/Velvet-White-100-664-wow",
    "TT0031010K0062880",
    "CEN1607NLinen-Ivory-194",
    "CENKZ1323-LTGrey-97",
]


def main():
    plan = json.loads((BASE / "plan.json").read_text(encoding="utf-8"))
    ranking = json.loads((BASE / "ranking.json").read_text(encoding="utf-8"))
    wo = json.loads((BASE / "wo_dn_coverage.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (Path(__file__).resolve().parents[2] / "experiments" / "g1_contract" / "out"
         / "dn_wo_jc_se_expand10_phase1_r2" / "association_manifest.json").read_text(encoding="utf-8")
    )
    plan_by = {r["sku"]: r for r in plan["rows"]}
    rank_by = {r["sku"]: r for r in ranking["top50"]}
    wo_by = {m["sku"]: m for m in wo["material_skus"]}

    con = duckdb.connect(DB, read_only=True)
    q_skus = ",".join(repr(s) for s in SKUS)
    stock = {}
    for sku, wh, a, i, w, d in con.execute(
        f"select sku,warehouse,available,intransit,waiting_shipment,defects "
        f"from stock_latest where sku in ({q_skus}) order by sku, warehouse"
    ).fetchall():
        stock.setdefault(sku, []).append(
            dict(warehouse=wh, available=a, intransit=i, waiting_shipment=w, defects=d)
        )
    po = {}
    for sku, pn, wh, qty, openq, status, pdate, eta in con.execute(
        f"select goods_sku,ponum,warehouse,quantity,open_qty,status,purchase_date,will_arrive_date "
        f"from tongtool_po where goods_sku in ({q_skus}) order by goods_sku, purchase_date"
    ).fetchall():
        po.setdefault(sku, []).append(
            dict(ponum=pn, warehouse=wh, quantity=qty, open_qty=openq, status=status,
                 purchase_date=pdate, will_arrive_date=eta)
        )
    con.close()

    out = {"skus": {}}
    for sku in SKUS:
        p = plan_by[sku]
        r = rank_by.get(sku)
        w = wo_by.get(sku)
        out["skus"][sku] = dict(
            rank_top50=r["rank"] if r else None,
            net_qty_6m=r["net_qty_6m"] if r else None,
            monthly_sales={m["month"]: m["qty"] for m in (r["months"] if r else [])},
            mapped_item_code=r.get("mapped_item_code") if r else None,
            item_group=r.get("item_group") if r else None,
            in_coverage_because=p["in_coverage_because"],
            p50_90d=p["demand"].get("p50"),
            p90_like=(p["demand"].get("interval") or {}).get("p90_like"),
            stock_sku_total=p["stock"],
            stock_by_warehouse=stock.get(sku, []),
            po_lines=po.get(sku, []),
            wo_evidence=w,
        )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
