#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Facts for the 538 never-scored SKUs (OFFLINE, READ-ONLY, NO PREDICTION).

Scope: mother set = the 1,328 SKUs of `out/business_phase/destinations.json`, the same
base `full_sku_routing.py` (commit b9c9b4ed) used. This script does NOT forecast, does
NOT produce quantities, does NOT fill zeros and does NOT drop SKUs.

What it does
  1. reproduces 1,328 / 790 / 538 and 2,690 + 1,130 = 3,820 from the same rule
     (`tr = origin - first + 1 < MIN_TRAIN=18`) that produced full_sku_eval.json;
  2. reports per-SKU facts for the 538 (series rows, history months, zero share,
     any lifetime sales, mapping state, warehouse count);
  3. labels every one of them `validation_status = 本批未验证`, keeps
     "observed zero" and "no history" apart, and marks `candidate_short_history`
     strictly from the already-frozen classification field (`type == 新品短史`,
     which encodes the existing 12/24-month rule). No new threshold is invented.

Labels are labels. Nothing here says a SKU is predictable, verified, or zero-demand.

Outputs:
  out/business_phase/sku538_facts.csv   (row level — the report keeps aggregates only)
  out/business_phase/sku538_facts.json  (aggregates + reproduction identities)
"""
from __future__ import annotations

import csv
import json
import sys
import time
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
DEST = OUT / "destinations.json"
CLASS_CSV = OUT / "full_sku_classification.csv"
EVAL_JSON = OUT / "full_sku_eval.json"
ORIGINS = ["2025-03", "2025-06", "2025-09", "2025-12", "2026-03"]
MIN_TRAIN = 18
LAST_I = 2026 * 12 + 9 - 1


def bucket_months(n: int) -> str:
    """Descriptive histogram only — NOT a qualification threshold."""
    for lo, hi in ((1, 5), (6, 11), (12, 17), (18, 23), (24, 35), (36, 60)):
        if lo <= n <= hi:
            return f"{lo}-{hi}"
    return ">60"


def bucket_zero_share(z) -> str:
    if z is None:
        return "no_history"
    if z == 0:
        return "0%"
    if z <= 0.25:
        return "(0,25%]"
    if z <= 0.5:
        return "(25,50%]"
    if z <= 0.75:
        return "(50,75%]"
    if z < 1.0:
        return "(75,100%)"
    return "100%"


def main() -> None:
    t0 = time.time()
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    universe = sorted({r["sku"] for r in dest["rows"]})
    dest_map = {r["sku"]: r for r in dest["rows"]}
    eval_json = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    recon = eval_json["reconciliation"]

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # identical query to full_sku_routing.py:77 (mother-set series definition)
        rows = con.execute(
            "SELECT sku, substr(month,1,7), SUM(qty) FROM monthly_series "
            "WHERE month <= '2026-09' GROUP BY 1,2").fetchall()
        # per-SKU raw series facts (rows are warehouse x month, so they are counted
        # separately from the SKU-level aggregated series used for training)
        raw = con.execute("""
            SELECT sku, count(*) AS n_rows, count(DISTINCT substr(month,1,7)) AS n_months,
                   count(DISTINCT warehouse) AS n_warehouses,
                   min(substr(month,1,7)) AS first_month, max(substr(month,1,7)) AS last_month,
                   sum(qty) AS total_qty
            FROM monthly_series WHERE month <= '2026-09' GROUP BY 1""").fetchall()
        sku_item = con.execute("SELECT sku, count(DISTINCT item_code) FROM sku_item GROUP BY 1").fetchall()
    finally:
        con.close()

    by = defaultdict(dict)
    for sku, ym, q in rows:
        by[sku][ym] = float(q or 0)
    series = {}
    for sku in universe:
        b = by.get(sku)
        if not b:
            continue
        first = min(A.ym_i(m) for m in b)
        months = [A.i_ym(i) for i in range(first, LAST_I + 1)]
        series[sku] = dict(first=first, months=months,
                           y=np.array([b.get(m, 0.0) for m in months]))

    raw_facts = {r[0]: dict(n_rows=r[1], n_months=r[2], n_warehouses=r[3],
                            first_month=r[4], last_month=r[5], total_qty=float(r[6] or 0))
                 for r in raw}
    item_codes = {r[0]: r[1] for r in sku_item}

    cls = {r["sku"]: r for r in csv.DictReader(CLASS_CSV.open(encoding="utf-8-sig", newline=""))}

    # ---- 1. reproduce the scoring rule (same as full_sku_routing.py:141-153)
    skips = Counter()
    for origin in ORIGINS:
        o = A.ym_i(origin)
        for sku in universe:
            s = series.get(sku)
            if not s:
                continue
            tr = o - s["first"] + 1
            if tr < MIN_TRAIN:
                skips[sku] += 1
    never_scored = sorted(sku for sku in universe if skips[sku] == len(ORIGINS))
    partially = sorted(sku for sku in universe if 0 < skips[sku] < len(ORIGINS))
    all_origins_ok = sorted(sku for sku in universe if skips[sku] == 0)

    n_never_units = sum(skips[s] for s in never_scored)
    n_missing_from_scored = sum(skips[s] for s in partially) + sum(skips[s] for s in all_origins_ok)
    scored_like = len(partially) + len(all_origins_ok)

    identities = dict(
        mother_set=len(universe),
        with_monthly_series=len(series),
        without_series=len(universe) - len(series),
        scored_skus_reported=recon["scored_skus"],
        scored_skus_reproduced=scored_like,
        never_scored_reproduced=len(never_scored),
        never_scored_units=n_never_units,
        missing_cells_from_scored_reproduced=n_missing_from_scored,
        missing_cells_reported=recon["unscored_skips_sumi"],
        common_cells_reported=eval_json["common_cells"],
        check_mother=len(universe) == recon["input_skus"],
        check_scored=scored_like == recon["scored_skus"],
        check_never=len(never_scored) == recon["input_skus"] - recon["scored_skus"],
        check_units=n_never_units == len(never_scored) * len(ORIGINS),
        check_missing=n_never_units + n_missing_from_scored == recon["unscored_skips_sumi"],
        check_common=scored_like * len(ORIGINS) - n_missing_from_scored == eval_json["common_cells"],
    )

    # ---- 2/3. per-SKU facts + labels for the 538
    out_rows = []
    for sku in never_scored:
        s = series.get(sku)
        rf = raw_facts.get(sku, {})
        c = cls.get(sku, {})
        n_hist = int(c["n_hist"]) if c.get("n_hist") not in (None, "") else 0
        zero_share = float(c["zero_share"]) if c.get("zero_share") not in (None, "") else None
        total = float(c["total_qty"]) if c.get("total_qty") not in (None, "") else 0.0
        codes = item_codes.get(sku, 0)
        dest_state = dest_map.get(sku, {}).get("destination", "")
        if codes == 0:
            mapping = "未映射"
        elif codes == 1:
            mapping = "已映射"
        else:
            mapping = "歧义"
        # "observed zero" vs "no history": the mother set is built from SKUs that have
        # order records, so `no_history` can only appear if a SKU lost its series.
        if s is None:
            obs = "无历史（无观测）"
        elif total <= 0:
            obs = "有观测的零（整段全零）"
        else:
            obs = "有观测的非零"
        out_rows.append(dict(
            sku=sku,
            n_series_rows=rf.get("n_rows", 0),
            n_months_observed=rf.get("n_months", 0),
            n_warehouses=rf.get("n_warehouses", 0),
            first_month=rf.get("first_month", ""),
            last_month=rf.get("last_month", ""),
            history_len_months=n_hist,
            history_len_from_series=(LAST_I - s["first"] + 1) if s else 0,
            zero_share=("" if zero_share is None else round(zero_share, 4)),
            total_qty=round(total, 2),
            has_any_sales=("yes" if total > 0 else "no"),
            classification_type=c.get("type", ""),
            classification_reason=c.get("reason", ""),
            mapping_state=mapping,
            n_item_codes=codes,
            destinations_state=dest_state,
            observation_bucket=obs,
            candidate_short_history=("yes" if c.get("type") == "新品短史" else "no"),
            candidate_basis=("既有分类字段 type=新品短史（12–23 月）；未新增门槛" if c.get("type") == "新品短史"
                             else ("type=证据不足（<12 月），是否纳入候选需 Codex2 裁决"
                                   if c.get("type") == "证据不足" else f"type={c.get('type', '')}")),
            validation_status="本批未验证",
        ))

    csv_path = OUT / "sku538_facts.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---- aggregates (report uses these only)
    def dist(key):
        return dict(sorted(Counter(r[key] for r in out_rows).items()))

    agg = dict(
        n=len(out_rows),
        history_len_buckets=dict(sorted(Counter(
            bucket_months(r["history_len_months"]) for r in out_rows).items())),
        history_len_existing_split=dict(sorted(Counter(
            ("证据不足 <12 月" if r["history_len_months"] < 12 else
             "新品短史 12–23 月" if r["history_len_months"] < 24 else "≥24 月")
            for r in out_rows).items())),
        zero_share_buckets=dict(sorted(Counter(bucket_zero_share(
            None if r["zero_share"] == "" else float(r["zero_share"])) for r in out_rows).items())),
        mapping_states=dist("mapping_state"),
        destinations_states=dist("destinations_state"),
        observation_buckets=dist("observation_bucket"),
        has_any_sales=dist("has_any_sales"),
        classification_types=dist("classification_type"),
        candidate_short_history=dist("candidate_short_history"),
        validation_status=dist("validation_status"),
        warehouse_count=dict(sorted(Counter(r["n_warehouses"] for r in out_rows).items())),
        series_rows=dict(n_min=min(r["n_series_rows"] for r in out_rows),
                         n_median=float(np.median([r["n_series_rows"] for r in out_rows])),
                         n_max=max(r["n_series_rows"] for r in out_rows)),
        history_len_months=dict(n_min=min(r["history_len_months"] for r in out_rows),
                                n_median=float(np.median([r["history_len_months"] for r in out_rows])),
                                n_max=max(r["history_len_months"] for r in out_rows)),
        zero_share_median=float(np.median([float(r["zero_share"]) for r in out_rows
                                           if r["zero_share"] != ""])),
        all_zero_skus=sum(1 for r in out_rows if r["observation_bucket"].startswith("有观测的零")),
        no_history_skus=sum(1 for r in out_rows if r["observation_bucket"].startswith("无历史")),
        # a SKU can be non-zero in total yet contain observed zero months; keep the two apart
        skus_with_zero_months=sum(1 for r in out_rows
                                  if r["zero_share"] != "" and float(r["zero_share"]) > 0),
        skus_without_zero_months=sum(1 for r in out_rows
                                     if r["zero_share"] != "" and float(r["zero_share"]) == 0),
        total_qty_stats=dict(
            n_min=min(r["total_qty"] for r in out_rows),
            n_median=float(np.median([r["total_qty"] for r in out_rows])),
            n_max=max(r["total_qty"] for r in out_rows)),
        dest_state_crosscheck=dict(
            unmapped_in_538=sum(1 for r in out_rows if r["destinations_state"] == "unmapped"),
            mapped_in_538=sum(1 for r in out_rows if r["destinations_state"].startswith("mapped")),
            mother_unmapped=dest.get("counts", {}).get("unmapped"),
            mother_mapped_total=dest.get("counts", {}).get("mapped_total"),
            mother_mapping_error_codes=dest.get("counts", {}).get("reason_code_counts")),
        ambiguity_examples=[r["sku"] for r in out_rows if r["mapping_state"] == "歧义"][:20],
    )

    payload = dict(
        schema_version="sku538_facts/1",
        scope=dict(mother_set_source=str(DEST), classification_source=str(CLASS_CSV),
                   eval_source=str(EVAL_JSON), db=str(DB_PATH), db_read_only=True,
                   origins=ORIGINS, min_train=MIN_TRAIN, as_of="2026-09"),
        identities=identities,
        legacy=dict(reported=dict(input_skus=recon["input_skus"],
                                  with_monthly_series=recon["with_monthly_series"],
                                  scored_skus=recon["scored_skus"],
                                  unscored_skips=recon["unscored_skips_sumi"],
                                  common_cells=eval_json["common_cells"])),
        aggregates=agg,
        boundaries=[
            "只做事实与标签：无预测、无数量、未填 0、未删 SKU。",
            "本批未验证 ≠ 不可预测；历史短 ≠ 需求为零。",
            "母集来自 destinations.json（1,328 个有订单记录的 SKU），"
            "因此「无历史（无观测）」在本母集里结构性地不可能出现——不是业务上没有。",
            "candidate_short_history 只用既有分类字段 type=新品短史（12–23 月），未新增门槛；"
            "证据不足（<12 月）是否纳入候选需 Codex2 裁决。",
            "790 个已评分 SKU 的表现不得外推到这 538 个。",
        ],
        elapsed_s=round(time.time() - t0, 2),
    )
    (OUT / "sku538_facts.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(identities, ensure_ascii=False, indent=1))
    print(json.dumps({k: agg[k] for k in ("history_len_buckets", "history_len_existing_split",
                                          "zero_share_buckets", "mapping_states",
                                          "observation_buckets", "classification_types",
                                          "candidate_short_history", "warehouse_count")},
                     ensure_ascii=False, indent=1))
    print(json.dumps(dict(partial_skus=len(partially), all_ok=len(all_origins_ok),
                          elapsed_s=payload["elapsed_s"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
