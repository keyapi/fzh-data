#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""October bucket interval rebuild: feasibility check (OFFLINE, READ-ONLY).

Approved method (Codex2 / D37): rebuild the 2026-10-01 opening inventory from
the verified 2026-07-31 snapshot plus Aug 1 - Sep 30 flows:
    stock_low  = S_low  + net_change_low
    stock_high = S_high + net_change_high
    gap = [max(0, D - stock_high), max(0, D - stock_low)]

Four conditions must hold per SKU x warehouse; if any fails the interval is
abandoned (no forcing, no "assume zero inflow / zero loss").

This script only *checks* feasibility and writes the counts; it never invents a
flow. Outputs:
  out/business_phase/oct_interval_rebuild.json   (local, machine summary)
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")


def main() -> None:
    rows = {r["sku"]: r for r in csv.DictReader(
        (BP / "quantity_pilot_rows.csv").open(encoding="utf-8-sig"))}
    passed = {s for s, r in rows.items()
              if all(r.get(g) == "已证" for g in ("G1", "G2", "G3", "G4"))}
    dec = {r["SKU"]: r for r in csv.DictReader(
        (BP / "decision_v2.csv").open(encoding="utf-8-sig"))}

    con = duckdb.connect(str(DB), read_only=True)
    try:
        snap = con.execute(
            "SELECT sku, warehouse_raw, available FROM wx_inventory.canonical "
            "WHERE snapshot_date='2026-07-31' AND warehouse_scope='source_warehouse'"
        ).fetchall()
        out_skus = {r[0] for r in con.execute(
            "SELECT DISTINCT sku_tongtool FROM gs_orders "
            "WHERE despatch_date >= '2026-08-01' AND despatch_date < '2026-10-01'"
        ).fetchall()}
        tables = [t for (t,) in con.execute("SHOW TABLES").fetchall()]
    finally:
        con.close()

    sval = defaultdict(dict)
    for sku, wh, avail in snap:
        sval[sku][wh] = float(avail or 0)
    ws = {wh for d in sval.values() for wh in d}

    def suffix(s):
        return s.split("-", 1)[1] if "-" in s else s

    covered = [s for s in passed if sval.get(s)]
    s_pos = sum(1 for s in covered if any(v > 0 for v in sval[s].values()))
    s_zero = len(covered) - s_pos
    wh_ok = sum(1 for s in covered
                if suffix(dec[s]["仓"]) in sval[s] or dec[s]["仓"] in sval[s])
    wh_bad = len(covered) - wh_ok
    with_out = len(passed & out_skus)

    # flow tables actually available
    flow_tables = [t for t in tables
                   if any(k in t.lower() for k in
                          ("transfer", "return", "adjust", "receipt", "grn", "dn", "wo"))]

    verdicts = Counter()
    blockers = Counter()
    for s in passed:
        # C1 complete flows: inbound/transfer/return/adjustment records absent
        c1 = False
        # C2 bounded omissions: missing inflow => stock upper bound unbounded
        c2 = False
        # C3 unit + warehouse attribution
        c3 = bool(sval.get(s)) and (suffix(dec[s]["仓"]) in sval[s]
                                    or dec[s]["仓"] in sval[s])
        # C4 reconciliation can narrow: no warehouse ledger to reconcile against
        c4 = False
        if not (c1 and c2 and c3 and c4):
            verdicts["放弃"] += 1
            if not sval.get(s):
                blockers["无 7/31 快照值"] += 1
            if not c1:
                blockers["8/1–9/30 入库/调拨/退货/调整流水无记录"] += 1
            if not c2:
                blockers["漏记无界（入库未知→库存上界无界）"] += 1
            if not c3:
                blockers["仓归属歧义（如 美中-FZH-DANEEY 覆盖多个子仓）"] += 1
            if not c4:
                blockers["无可对账的仓账/日结"] += 1
        else:
            verdicts["可给区间"] += 1

    summary = dict(
        schema_version="oct_interval_rebuild/1",
        passed_skus=len(passed),
        snapshot_date="2026-07-31",
        coverage=dict(covered=len(covered), s_positive=s_pos, s_zero=s_zero),
        warehouse_label=dict(match=wh_ok, ambiguous=wh_bad,
                             note="决策仓标签如 美中-FZH-DANEEY 覆盖 皮壳仓+退货仓 两个子仓"),
        outbound=dict(skus_with_aug_sep_despatch=with_out,
                      note="仅渠道发货（gs_orders），不是仓内出库账；退货/调拨不在其中"),
        flow_tables_found=flow_tables,
        verdicts=dict(verdicts),
        blockers=dict(blockers),
        reconcile=f"{verdicts.get('可给区间',0)} + {verdicts.get('放弃',0)} = {sum(verdicts.values())} == {len(passed)}",
        reconcile_ok=(sum(verdicts.values()) == len(passed)),
    )
    (BP / "oct_interval_rebuild.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
