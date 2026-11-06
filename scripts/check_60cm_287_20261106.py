# -*- coding: utf-8 -*-
"""60cm 287-piece reconciliation (read-only).

Compares D3b v3.5 (pre-60cm) and v3.7 (post-60cm) current series:
for every KS0001-*-60 key, record old qty, expected KS0248 target,
whether the target exists, and the disposition.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
A = BASE / "D3b_v3_5_series_current_2026-11-03.parquet"
B = BASE / "D3b_v3_7_series_current_2026-11-06.parquet"
OUT = BASE / "60cm_287_reconciliation_20261106.csv"
OUT_JSON = BASE / "60cm_287_reconciliation_20261106.json"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]


def main() -> int:
    a = pd.read_parquet(A)
    b = pd.read_parquet(B)
    old = (a[a["product_id"].astype(str).str.startswith("KS0001-")
             & a["product_id"].astype(str).str.contains("-60-")]
           .groupby(KEYS, as_index=False)["qty"].sum().rename(columns={"qty": "qty_v3_5"}))
    new = (b.groupby(KEYS, as_index=False)["qty"].sum().rename(columns={"qty": "qty_v3_7"}))
    old["target"] = old["product_id"].str.replace("KS0001-", "KS0248-", n=1)
    m = old.merge(new, left_on=["target", "pool", "physical_form", "canonical_uom"],
                  right_on=KEYS, how="left", suffixes=("", "_target"))
    m["qty_v3_7"] = m["qty_v3_7"].fillna(0.0)
    orig = new.rename(columns={"product_id": "product_id_orig", "qty_v3_7": "qty_v3_7_orig"})
    m = m.merge(orig, left_on=["product_id", "pool", "physical_form", "canonical_uom"],
                right_on=["product_id_orig", "pool", "physical_form", "canonical_uom"],
                how="left")
    m["qty_v3_7_orig"] = m["qty_v3_7_orig"].fillna(0.0)
    m["status"] = [
        "merged" if q > 0
        else ("kept_no_target" if qo > 0 else "dropped_no_successor")
        for q, qo in zip(m["qty_v3_7"], m["qty_v3_7_orig"])
    ]
    m["disposition"] = [
        ("合并到 " + str(t)) if s == "merged"
        else ("保留原键 " + str(p) + "（无 KS0248 同规格目标）") if s == "kept_no_target"
        else "无活跃后继；退出预测母集，原始需求保留在桶对账"
        for s, t, p in zip(m["status"], m["target"], m["product_id"])
    ]
    m = m[["product_id", "target", "pool", "physical_form", "canonical_uom",
           "qty_v3_5", "qty_v3_7", "qty_v3_7_orig", "status", "disposition"]]
    m.to_csv(OUT, index=False, encoding="utf-8-sig")
    total_old = float(m["qty_v3_5"].sum())
    total_merged = float(m.loc[m["status"] == "merged", "qty_v3_5"].sum())
    total_kept = float(m.loc[m["status"] == "kept_no_target", "qty_v3_5"].sum())
    total_orphan = float(m.loc[m["status"] == "dropped_no_successor", "qty_v3_5"].sum())
    total_new = float(m["qty_v3_7"].sum() + m["qty_v3_7_orig"].sum())
    summary = {
        "old_ks0001_60_keys": int(len(m)),
        "old_qty": total_old,
        "merged_qty": total_merged,
        "kept_no_target_qty": total_kept,
        "dropped_no_successor_qty": total_orphan,
        "new_target_plus_kept_qty": total_new,
        "series_total_v3_5": float(a["qty"].sum()),
        "series_total_v3_7": float(b["qty"].sum()),
        "series_diff": float(a["qty"].sum() - b["qty"].sum()),
        "dropped_keys": m.loc[m["status"] == "dropped_no_successor",
                              ["product_id", "pool", "qty_v3_5"]].to_dict("records"),
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
