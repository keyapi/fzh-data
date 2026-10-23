#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Forward net demand from the 2026-10-22 snapshot (OFFLINE, READ-ONLY).

Horizon: remaining October (10/22-10/31) + November + December. The snapshot is
NOT "current stock": it is dated 2026-10-22 and the run is on 10/23, so one day
of consumption is already inside the demand bucket but not reflected in stock.

Primary intra-month split: remaining-October demand = monthly rate x 10/31
(days 22..31 inclusive). Sensitivity: daily average x 9 days (10/23..10/31).

SO deduction: `已承诺待发` (committed, not shipped) is subtracted from demand
once, earliest bucket first (no SO delivery dates exist, so the bucket order is
an explicit B assumption).

Supply dedupe: PO + in-transit are never double counted. `在途去重状态 =
suspected_same_batch_as_po` means the transit IS the PO batch -> counted once.
PO lines flagged `duplicate_lines` and transit flagged `no_line_key` are not
dedupe-proven -> they only enter the B scenario. WO is `work_order_not_in_snapshot`
for every row (zero known quantity, unknown existence).

Tiers: A = only proven fields + declared forecast (no non-on-hand supply, no SO);
       B = needs explicit assumptions (SO without date, PO/transit arrival,
           dedupe not proven); 不能算 = missing demand rate or on-hand.
No order quantity; MOQ/pack/budget are out of scope.

Outputs (row level stays local):
  out/business_phase/forward_net.json
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"
SNAPSHOT = "2026-10-22"
RUN_DATE = "2026-10-23"
OCT_REM_DAYS = 10          # 22..31 inclusive
OCT_REM_DAYS_SENS = 9      # 23..31


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def main() -> None:
    rows = list(csv.DictReader((BP / "decision_v2.csv").open(encoding="utf-8-sig")))
    replen = {(r["SKU"], r["仓"]): r for r in csv.DictReader(
        (BP / "replenishment_v2.csv").open(encoding="utf-8-sig"))}

    out_rows = []
    tiers = Counter()
    reasons = Counter()
    agg = defaultdict(lambda: dict(gross=0.0, so=0.0, on_hand=0.0, gap_a=0.0,
                                   gap_b=0.0, supp_b=0.0))
    for r in rows:
        sku, wh = r["SKU"], r["仓"]
        rate = num(r.get("月需求率"))
        on_hand = num(r.get("可用"))
        committed = num(r.get("已承诺待发")) or 0.0
        transit = num(r.get("在途")) or 0.0
        po = num(r.get("PO未结")) or 0.0
        po_state = r.get("PO去重状态", "")
        tr_state = r.get("在途去重状态", "")

        if r.get("状态") == "C" or rate is None or on_hand is None:
            tiers["不能算"] += 1
            reasons["无月需求率（状态 C）" if rate is None else "在手库存未取得"] += 1
            out_rows.append(dict(sku=sku, warehouse=wh, tier="不能算",
                                 reason=("状态 C / 无需求" if rate is None else "B_pending_inventory"),
                                 gross=None, so=None, on_hand=on_hand,
                                 gap_a=None, gap_b=None, assumptions=""))
            continue

        d_oct = rate * OCT_REM_DAYS / 31
        d_oct_sens = rate * OCT_REM_DAYS_SENS / 31
        gross = d_oct + rate + rate
        gross_sens = d_oct_sens + rate + rate

        # SO waterfall: earliest bucket first
        so = committed
        net = max(0.0, gross - so)
        gap_a = max(0.0, net - on_hand)

        # deduped non-on-hand supply
        po_ok = po_state in ("none_recorded", "lines_unique")
        tr_same_batch = tr_state == "suspected_same_batch_as_po"
        tr_ok = tr_state in ("none_recorded",) or tr_same_batch
        supply_excl = 0.0
        assumptions = []
        if po > 0:
            if po_ok:
                supply_excl += po
                assumptions.append("PO 未结计入（去重状态已证）")
            else:
                assumptions.append(f"PO 去重未证（{po_state}）→ 不计入 B 情景")
        if transit > 0:
            if tr_same_batch:
                assumptions.append("在途与 PO 同批 → 不重复计")
            elif tr_ok:
                supply_excl += transit
                assumptions.append("在途计入（无日期）")
            else:
                assumptions.append(f"在途无行键（{tr_state}）→ 不计入 B 情景")
        gap_b = max(0.0, net - on_hand - supply_excl)

        needs = (committed > 0 or po > 0 or transit > 0)
        tier = "B" if needs else "A"
        if committed > 0:
            assumptions.insert(0, "SO 无交期 → 按最早桶优先冲减")
        assumptions.append("需求= T5 AutoETS 平月率（假设，非真值）")
        assumptions.append(f"10/22→10/31 按 {OCT_REM_DAYS}/31 月率分摊")
        tiers[tier] += 1
        a = agg[tier]
        a["gross"] += gross
        a["so"] += so
        a["on_hand"] += on_hand
        a["gap_a"] += gap_a
        a["gap_b"] += gap_b
        a["supp_b"] += supply_excl
        out_rows.append(dict(sku=sku, warehouse=wh, tier=tier, reason="",
                             gross=round(gross, 3), gross_sens=round(gross_sens, 3),
                             so=round(so, 3), on_hand=round(on_hand, 3),
                             supply_b=round(supply_excl, 3),
                             gap_a=round(gap_a, 3), gap_b=round(gap_b, 3),
                             assumptions="；".join(assumptions)))

    with (BP / "forward_net_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---- SKU level coverage of all 1,328 destinations ----------------
    # SKU level uses the WORST row status (a SKU is "computable" only if every
    # warehouse row is); mixed SKUs are counted separately.
    sku_states = defaultdict(set)
    for r in out_rows:
        sku_states[r["sku"]].add(r["tier"])
    rank = {"A": 0, "B": 1, "不能算": 2}
    sku_tier = {s_: max(t_, key=lambda t: rank[t]) for s_, t_ in sku_states.items()}
    sku_dist = Counter(sku_tier.values())
    sku_mixed = sum(1 for t_ in sku_states.values() if len(t_) > 1)

    total_gross = sum(v["gross"] for v in agg.values())
    total_gross_sens = sum(r["gross_sens"] for r in out_rows if r.get("gross_sens"))
    summary = dict(
        schema_version="forward_net/1",
        snapshot=dict(date=SNAPSHOT, run_date=RUN_DATE,
                      note=("库存数据截至 2026-10-22，不是「当前库存」；"
                            "距运行日 1 天、距 11/1 10 天")),
        horizon=dict(oct_remaining_days=OCT_REM_DAYS,
                     primary="月率×10/31（22–31 含）",
                     sensitivity=f"月率×9/31（23–31）",
                     buckets=["2026-10 剩余", "2026-11", "2026-12"]),
        rows=len(out_rows), row_tiers=dict(tiers),
        reconcile=f"{tiers.get('A',0)} + {tiers.get('B',0)} + {tiers.get('不能算',0)} = {len(out_rows)}",
        reconcile_ok=(sum(tiers.values()) == len(out_rows)),
        sku_universe=len(sku_tier), sku_tiers=dict(sku_dist),
        sku_mixed_rows=sku_mixed,
        totals=dict(gross=round(total_gross, 1),
                    gross_sensitivity=round(total_gross_sens, 1),
                    so=round(sum(v["so"] for v in agg.values()), 1),
                    on_hand=round(sum(v["on_hand"] for v in agg.values()), 1),
                    gap_a=round(sum(v["gap_a"] for v in agg.values()), 1),
                    gap_b=round(sum(v["gap_b"] for v in agg.values()), 1),
                    by_tier={k: {kk: round(vv, 1) for kk, vv in v.items()}
                             for k, v in agg.items()}),
        reasons=dict(reasons),
        model_interface=dict(
            current="T5 AutoETS 平月率（T5 迭代版默认，SKU 级拟合 × 仓占比分配）",
            not_used="tree / combo / TSB 等新模型均未接入本口径",
            switch_point=("待 Codex2 裁定：何时把新预测接回前向净需求、以何种判据（嵌套重训 + "
                          "真未用留出）授权；本轮不替换")),
        boundary=("不给可下单量；MOQ/包装/预算另列；B 档假设逐行写在本地 CSV；"
                  "缺口是需求-供给的算术差，不是采购量"),
    )
    (BP / "forward_net.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(rows=summary["rows"], tiers=summary["row_tiers"],
                          sku=summary["sku_universe"], sku_tiers=summary["sku_tiers"],
                          totals=summary["totals"], reconcile_ok=summary["reconcile_ok"]),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
