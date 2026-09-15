# -*- coding: utf-8 -*-
"""门槛敏感性扫掠：样本门槛 × 月份门槛，两个独立时间窗都看。"""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tongtool_order_cost.history_last_leg_analysis import (
    add_outlier_flags, build_package_observations, legacy_predict_fee_faithful,
    load_legacy_items, prepare_order_rows)
from tongtool_order_cost.model_variants import (
    MODERN_LEVELS, build_variant_tiers, error_metrics, predict_with_variant)

raw = pd.read_csv(ROOT/"out"/"monthly_orders_full.csv.gz", dtype=str)
rows = pd.concat([prepare_order_rows(f,m) for m,f in raw.groupby("月份")], ignore_index=True)
obs = add_outlier_flags(build_package_observations(rows))
legacy = load_legacy_items(ROOT/"out"/"hlf0001_items.csv.gz")
elig = obs[obs["建模状态"]=="可建模"].copy()

SPLITS = [("窗A 训≤2602 验03-04", "202602", ["202603","202604"]),
          ("窗B 训≤2604 验05-06", "202604", ["202605","202606"])]
recs = []
for label, cut, vals in SPLITS:
    tr = elig[elig["月份"].astype(str) <= cut]
    va = elig[elig["月份"].astype(str).isin(vals)].copy()
    va["HLF"] = va.apply(lambda r: legacy_predict_fee_faithful(
        legacy, r["国家"], r["通途SKU"], r["观察重量_kg"])[0], axis=1)
    recs.append({"窗": label, "门槛": "HLF0001", "层数": 0,
                 **error_metrics(va["观察费用"], va["HLF"])})
    for ms in (5, 10, 20, 30):
        for mm in (1, 2):
            if ms == 30 and mm == 1:
                continue
            tiers, _ = build_variant_tiers(tr, levels=MODERN_LEVELS, exclusive=False,
                                           min_samples=ms, min_months=mm)
            pred = predict_with_variant(va, tiers, scheme="zone_first")
            recs.append({"窗": label, "门槛": f"{ms}样本/{mm}月", "层数": len(tiers),
                         **error_metrics(va["观察费用"], pred)})
df = pd.DataFrame(recs)
for label, _, _ in SPLITS:
    print(f"\n== {label} ==")
    print(df[df["窗"]==label][["门槛","层数","覆盖率%","MAE","MdAE","偏差","P90","相对误差中位%"]]
          .to_string(index=False))
