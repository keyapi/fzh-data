#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Month-cell evidence audit for the 538 never-scored SKUs (OFFLINE, READ-ONLY).

No prediction, no quantities, no zero filling, no SKU removal.

Question this answers
  The previous pass reported a median zero share of 42.9% for the 538. That series was
  built by range-filling `b.get(month, 0.0)` over first..2026-09, so a month with no
  order row became 0. This script splits every month cell into
    positive      qty > 0
    proven_zero   the month is inside the SKU's observed span (bracketed by activity),
                  globally covered by the source, and carries no order
    unknown       outside the observed span (上架前 / 尾部无界) — NEVER counted as 0
  and recomputes the zero share on the proven-complete denominator only.

Source coverage evidence (not assumed):
  `monthly_series` is an exact aggregation of `gs_orders`: same 2,553 SKUs both ways,
  45 months (2023-01..2026-09), total qty diff = 0 for every month. Every month in the
  window carries orders, so a month is globally covered; absence of a row therefore
  means "no order line", not "missing source".

Tier thresholds are Codex2's (DECISIONS D36) and are NOT re-tuned here:
  >=12 usable closed months -> 可验证 (6 train + two non-overlapping 3-month windows)
  6-11                       -> 仅影子
  <6                         -> 不足

Outputs:
  out/business_phase/monthcell_sku.csv    (row level, local)
  out/business_phase/monthcell_audit.json (aggregates + tier counts + plan registration)
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
EVAL_DIR = HERE.parent
CLAUDE_DIR = HERE.parents[3]
OUT = CLAUDE_DIR / "out" / "business_phase"
sys.path.insert(0, str(EVAL_DIR))

import routing_eval as A                      # noqa: E402  (ym_i / i_ym only)

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
LAST_I = 2026 * 12 + 9 - 1
FACTS_CSV = OUT / "sku538_facts.csv"


def tier_of(usable: int) -> str:
    if usable >= 12:
        return "可验证(>=12)"
    if usable >= 6:
        return "仅影子(6-11)"
    return "不足(<6)"


def bucket_usable(n: int) -> str:
    for lo, hi in ((12, 14), (15, 17), (18, 20), (21, 23), (24, 29), (30, 100)):
        if lo <= n <= hi:
            return f"{lo}-{hi}"
    return "<12"


def main() -> None:
    facts = list(csv.DictReader(FACTS_CSV.open(encoding="utf-8-sig", newline="")))
    skus538 = [r["sku"] for r in facts]
    unmapped = {r["sku"] for r in facts if r["mapping_state"] == "未映射"}

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # coverage proof: monthly_series vs gs_orders, month by month
        cov = con.execute("""
            SELECT a.s, a.qty, b.qty FROM
              (SELECT substr(month,1,7) s, sum(qty) qty FROM monthly_series GROUP BY 1) a
            JOIN (SELECT substr(month,1,4)||'-'||substr(month,5,2) s, sum(qty) qty
                  FROM gs_orders WHERE month IS NOT NULL GROUP BY 1) b ON a.s=b.s
            ORDER BY 1""").fetchall()
        n_ms_sku = con.execute("SELECT count(DISTINCT sku) FROM monthly_series").fetchone()[0]
        n_gs_sku = con.execute("SELECT count(DISTINCT sku_tongtool) FROM gs_orders").fetchone()[0]
        ms_only = con.execute("""
            SELECT count(*) FROM (SELECT DISTINCT sku FROM monthly_series) m
            LEFT JOIN (SELECT DISTINCT sku_tongtool s FROM gs_orders) g ON m.sku=g.s
            WHERE g.s IS NULL""").fetchone()[0]
        # per-SKU months that actually carry orders
        rows = con.execute("""
            SELECT sku, substr(month,1,7) AS m, sum(qty) AS q
            FROM monthly_series WHERE month <= '2026-09' GROUP BY 1,2""").fetchall()
    finally:
        con.close()

    by = defaultdict(dict)
    for sku, m, q in rows:
        by[sku][m] = float(q or 0)
    coverage = dict(
        months_compared=len(cov),
        max_abs_qty_diff=(max(abs(float(a) - float(b)) for _, a, b in cov) if cov else None),
        monthly_series_skus=n_ms_sku, gs_orders_skus=n_gs_sku,
        skus_only_in_monthly_series=ms_only,
        window=[min(r[0] for r in cov), max(r[0] for r in cov)],
        every_month_has_orders=all(float(a) > 0 for _, a, _ in cov),
    )

    out_rows = []
    for r in facts:
        sku = r["sku"]
        b = by.get(sku, {})
        pos_months = sorted(m for m, q in b.items() if q > 0)
        if not pos_months:
            # no positive month at all: nothing is bracketed, everything is unknown
            out_rows.append(dict(
                sku=sku, mapped=("no" if sku in unmapped else "yes"),
                first_positive_month="", last_positive_month="",
                positive_months=0, proven_zero_months=0, usable_months=0,
                trailing_unknown_months=0, old_span_months=0,
                old_zero_months=0, old_zero_share="", new_zero_share="",
                tier="不足(<6)", window_placements=0,
                exclusion_reason="no_positive_month",
            ))
            continue
        first_i, last_i = A.ym_i(pos_months[0]), A.ym_i(pos_months[-1])
        usable = last_i - first_i + 1            # contiguous, bracketed -> closed months
        positive = len([m for m in pos_months
                        if first_i <= A.ym_i(m) <= last_i])
        proven_zero = usable - positive
        trailing = LAST_I - last_i               # unknown: after the last observed month
        old_span = LAST_I - first_i + 1          # what the previous pass used
        old_zero = old_span - positive
        out_rows.append(dict(
            sku=sku, mapped=("no" if sku in unmapped else "yes"),
            first_positive_month=pos_months[0], last_positive_month=pos_months[-1],
            positive_months=positive, proven_zero_months=proven_zero,
            usable_months=usable, trailing_unknown_months=trailing,
            old_span_months=old_span, old_zero_months=old_zero,
            old_zero_share=round(old_zero / old_span, 4) if old_span else "",
            new_zero_share=round(proven_zero / usable, 4) if usable else "",
            tier=tier_of(usable),
            window_placements=(max(0, usable - 12 + 1) if usable >= 12 else 0),
            exclusion_reason=("unmapped" if sku in unmapped else ""),
        ))

    with (OUT / "monthcell_sku.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # row-level month cells (local only; the report keeps aggregates)
    cell_rows = []
    for r in out_rows:
        if r["old_span_months"] == 0:
            continue
        b = by.get(r["sku"], {})
        fi = A.ym_i(r["first_positive_month"]) if r["first_positive_month"] else None
        li = A.ym_i(r["last_positive_month"]) if r["last_positive_month"] else None
        for i in range(fi, LAST_I + 1):
            m = A.i_ym(i)
            q = b.get(m, 0.0)
            state = ("positive" if q > 0 else
                     "proven_zero" if i <= li else "unknown")
            cell_rows.append(dict(sku=r["sku"], month=m, state=state,
                                  qty_observed=round(float(q), 2),
                                  inside_observed_span=("yes" if i <= li else "no")))
    with (OUT / "monthcell_cells.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cell_rows[0].keys()))
        w.writeheader()
        w.writerows(cell_rows)

    # ---------------------------------------------------------------- aggregates
    def agg(rows_):
        tot_m = sum(r["old_span_months"] for r in rows_)
        tot_pos = sum(r["positive_months"] for r in rows_)
        tot_pz = sum(r["proven_zero_months"] for r in rows_)
        tot_tr = sum(r["trailing_unknown_months"] for r in rows_)
        tot_use = sum(r["usable_months"] for r in rows_)
        tot_old_zero = sum(r["old_zero_months"] for r in rows_)
        return dict(
            skus=len(rows_),
            month_cells_old_span=tot_m,
            positive_months=tot_pos,
            proven_zero_months=tot_pz,
            unknown_months=tot_tr,
            usable_months=tot_use,
            old_zero_months=tot_old_zero,
            check_cells=tot_pos + tot_pz + tot_tr == tot_m,
            old_zero_share=(round(tot_old_zero / tot_m, 4) if tot_m else None),
            proven_zero_share_of_old_zero=(round(tot_pz / tot_old_zero, 4) if tot_old_zero else None),
            trailing_fill_share_of_old_zero=(round(tot_tr / tot_old_zero, 4) if tot_old_zero else None),
            new_zero_share=(round(tot_pz / tot_use, 4) if tot_use else None),
        )

    median_old = float(np.median([float(r["old_zero_share"]) for r in out_rows
                                  if r["old_zero_share"] != ""]))
    median_new = float(np.median([float(r["new_zero_share"]) for r in out_rows
                                 if r["new_zero_share"] != ""]))

    # tiers on the 481 mapped SKUs (the 57 unmapped are held out, §57 isolation)
    mapped_rows = [r for r in out_rows if r["mapped"] == "yes"]
    unmapped_rows = [r for r in out_rows if r["mapped"] == "no"]
    qty = {r["sku"]: float(r["total_qty"]) for r in facts}
    total_qty = sum(qty.values())

    tiers = {}
    for name in ("可验证(>=12)", "仅影子(6-11)", "不足(<6)"):
        rs = [r for r in mapped_rows if r["tier"] == name]
        q = sum(qty[r["sku"]] for r in rs)
        tiers[name] = dict(
            skus=len(rs),
            sales_qty=round(q, 2),
            sales_coverage_of_538=round(q / total_qty, 4) if total_qty else None,
            skus_with_two_windows=sum(1 for r in rs if r["window_placements"] > 0),
            window_placements_total=sum(r["window_placements"] for r in rs),
            usable_months_dist=dict(sorted(Counter(
                bucket_usable(r["usable_months"]) for r in rs).items())),
        )

    unmapped_summary = dict(
        skus=len(unmapped_rows),
        tiers=dict(Counter(r["tier"] for r in unmapped_rows)),
        sales_qty=round(sum(qty[r["sku"]] for r in unmapped_rows), 2),
        sales_coverage_of_538=round(sum(qty[r["sku"]] for r in unmapped_rows) / total_qty, 4),
        note="未映射 = sku_item 无 item_code；不进供需衔接、不进选模；仍计入 538 事实口径",
    )

    # ---------------------------------------------------------------- 缺证清单 (aggregate)
    short = [r for r in out_rows if r["tier"] == "不足(<6)"]
    shadow = [r for r in out_rows if r["tier"] == "仅影子(6-11)"]
    missing = dict(
        insufficient=dict(
            skus=len(short),
            months_to_6=dict(sorted(Counter(max(0, 6 - r["usable_months"]) for r in short).items())),
            months_to_12=dict(sorted(Counter(max(0, 12 - r["usable_months"]) for r in short).items())),
            with_zero_usable=sum(1 for r in short if r["usable_months"] == 0),
            never_sold_marker=sum(1 for r in short if r["exclusion_reason"] == "no_positive_month"),
            last_positive_before_2026_03=sum(1 for r in short if r["last_positive_month"]
                                             and r["last_positive_month"] < "2026-03"),
        ),
        shadow=dict(
            skus=len(shadow),
            months_to_12=dict(sorted(Counter(12 - r["usable_months"] for r in shadow).items())),
        ),
    )

    # old history-length bucket (sku538_facts) x new tier — shows what moved and why
    hist = {r["sku"]: int(r["history_len_months"]) for r in facts}
    crosstab = {}
    for name in ("可验证(>=12)", "仅影子(6-11)", "不足(<6)"):
        rs = [r for r in mapped_rows if r["tier"] == name]
        crosstab[name] = dict(sorted(Counter(
            ("1-5" if hist[r["sku"]] <= 5 else "6-11" if hist[r["sku"]] <= 11
             else "12-17" if hist[r["sku"]] <= 17 else "18-23")
            for r in rs).items()))

    payload = dict(
        schema_version="monthcell_audit/1",
        coverage_evidence=coverage,
        thresholds=dict(source="Codex2 DECISIONS D36（照用，未改）",
                        verifiable=">=12 usable closed months (6 train + 2x3 windows)",
                        shadow="6-11", insufficient="<6"),
        all_538=agg(out_rows),
        median_old_zero_share=round(median_old, 4),
        median_new_zero_share=round(median_new, 4),
        tiers_on_mapped_481=tiers,
        unmapped_isolation=unmapped_summary,
        reconciliation=dict(total_538=len(out_rows),
                            mapped=len(mapped_rows), unmapped=len(unmapped_rows),
                            tier_sum=sum(t["skus"] for t in tiers.values()),
                            equation=("538 = 481(三档) + 57(未映射)" if len(mapped_rows) == 481 else "check"),
                            ok=(len(mapped_rows) + len(unmapped_rows) == 538
                                and sum(t["skus"] for t in tiers.values()) == len(mapped_rows))),
        missing_evidence=missing,
        old_history_bucket_x_new_tier=crosstab,
        boundaries=[
            "只做证据分类与分档：无预测、无数量、未填 0、未删 SKU。",
            "proven_zero 的定义是「在已观测跨度内、源覆盖已证、且无订单」；跨度外一律 unknown。",
            "unknown 不是 0，也未被计入任何分母。",
            "538 的零占比旧值（中位 42.9%）包含尾部补零，本轮拆开并重算。",
            "57 个未映射 SKU 单独隔离，不参与分档分子之外的任何衔接或选模。",
            "TSB 仅限间歇候选；<=23 月序列不准入年度季节结论（登记，未执行）。",
        ],
    )
    (OUT / "monthcell_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(coverage, ensure_ascii=False))
    print(json.dumps({k: payload[k] for k in ("all_538", "median_old_zero_share",
                                              "median_new_zero_share")}, ensure_ascii=False, indent=1))
    print(json.dumps(tiers, ensure_ascii=False, indent=1))
    print(json.dumps(unmapped_summary, ensure_ascii=False, indent=1))
    print(json.dumps(missing, ensure_ascii=False, indent=1))
    print(json.dumps(payload["reconciliation"], ensure_ascii=False))


if __name__ == "__main__":
    main()
