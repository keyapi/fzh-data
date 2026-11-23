# -*- coding: utf-8 -*-
"""对比两版决策包：缺口与建议的变化（只读，不改任何数量）。

用途
- 新一轮库存快照后，回答「和上一版比，缺口/建议变了多少、为什么变」。
- 周节拍「周五演示」与「周四冻结」之间的差异核对也用这个。

口径
- 键 = `canonical_sku × canonical_warehouse × canonical_uom`（四列键的前三列；
  单位不同的键永不合并，这是硬边界）。
- **不重算任何数字**，只做逐键相减与分组计数。
- 一侧独有的键**单列**，不在合计里悄悄加减——新键（新到货 SKU）与消失的键
  含义完全不同，混在一起会把「新到 500 件」算成「缺口减少 500」。

输出
    compare_summary.json / compare_by_key.csv / compare_by_destination.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
NUMERIC = ("qty_current", "qty_higher", "gap_today", "horizon_demand", "opening",
           "protect_gap", "conditional_supply")


def _num(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame.columns:
        return pd.Series([0.0] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[col], errors="coerce")


def compare(old: pd.DataFrame, new: pd.DataFrame
            ) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    old = old.copy()
    new = new.copy()
    for col in NUMERIC:
        if col in old.columns:
            old[col] = _num(old, col)
        if col in new.columns:
            new[col] = _num(new, col)

    old_keys = set(map(tuple, old[KEY].astype(str).itertuples(index=False, name=None)))
    new_keys = set(map(tuple, new[KEY].astype(str).itertuples(index=False, name=None)))
    only_old = old_keys - new_keys
    only_new = new_keys - old_keys
    both = old_keys & new_keys

    def mark(frame: pd.DataFrame) -> pd.Series:
        keys = list(map(tuple, frame[KEY].astype(str).itertuples(index=False, name=None)))
        return pd.Series(["both" if k in both else ("only_old" if k in only_old else "only_new")
                          for k in keys], index=frame.index)

    old["_presence"] = mark(old)
    new["_presence"] = mark(new)

    merged = old[old["_presence"] == "both"].merge(
        new[new["_presence"] == "both"], on=KEY, how="inner", suffixes=("_old", "_new"))
    for col in NUMERIC:
        a, b = f"{col}_old", f"{col}_new"
        if a in merged.columns or b in merged.columns:
            merged[f"delta_{col}"] = merged.get(b, 0) - merged.get(a, 0)

    merged["destination_old"] = merged.get("destination_old", "")
    merged["destination_new"] = merged.get("destination_new", "")
    merged["destination_changed"] = merged["destination_old"] != merged["destination_new"]

    transitions = (merged[merged["destination_changed"]]
                   .groupby(["destination_old", "destination_new"]).size()
                   .reset_index(name="keys"))

    by_dest = (merged.groupby("destination_new")
               .agg(keys=("canonical_sku", "size"),
                    delta_qty_current=("delta_qty_current", "sum"),
                    delta_qty_higher=("delta_qty_higher", "sum"),
                    delta_gap_today=("delta_gap_today", "sum"),
                    delta_horizon_demand=("delta_horizon_demand", "sum"))
               .reset_index())

    def total(frame: pd.DataFrame, presence: str, col: str) -> float:
        sel = frame[frame["_presence"] == presence]
        return float(pd.to_numeric(sel.get(col), errors="coerce").fillna(0).sum()) if col in sel else 0.0

    summary = dict(
        keys_old=len(old_keys), keys_new=len(new_keys),
        keys_both=len(both), keys_only_old=len(only_old), keys_only_new=len(only_new),
        destinations_old={str(k): int(v) for k, v in old["destination"].value_counts().items()},
        destinations_new={str(k): int(v) for k, v in new["destination"].value_counts().items()},
        destination_changed_keys=int(merged["destination_changed"].sum()),
        transitions=[dict(source=r.destination_old, target=r.destination_new, keys=int(r.keys))
                     for r in transitions.itertuples()],
        totals=dict(
            qty_current=dict(old=float(old["qty_current"].fillna(0).sum()),
                             new=float(new["qty_current"].fillna(0).sum())),
            qty_higher=dict(old=float(old["qty_higher"].fillna(0).sum()),
                            new=float(new["qty_higher"].fillna(0).sum())),
            gap_today=dict(old=float(old["gap_today"].fillna(0).sum()),
                           new=float(new["gap_today"].fillna(0).sum())),
        ),
        only_old_supply_qty=dict(conditional_supply=total(old, "only_old", "conditional_supply"),
                                 qty_current=total(old, "only_old", "qty_current")),
        only_new_supply_qty=dict(conditional_supply=total(new, "only_new", "conditional_supply"),
                                 qty_current=total(new, "only_new", "qty_current")),
        note=("只对两侧都存在的键做相减；only_old / only_new 单列，不并进合计。"
              "单位不同（canonical_uom）永不合并。"),
    )
    one_sided = pd.concat([
        old[old["_presence"] == "only_old"].assign(_side="only_old"),
        new[new["_presence"] == "only_new"].assign(_side="only_new"),
    ], ignore_index=True)
    return summary, merged, by_dest, one_sided


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="对比两版决策包（只读）")
    ap.add_argument("--old", required=True, help="旧版 decision_pack_*.parquet")
    ap.add_argument("--new", required=True, help="新版 decision_pack_*.parquet")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args(argv)

    old = pd.read_parquet(args.old)
    new = pd.read_parquet(args.new)
    summary, merged, by_dest, one_sided = compare(old, new)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    merged.sort_values("delta_qty_current", key=lambda s: s.abs(), ascending=False) \
        .to_csv(out / "compare_by_key.csv", index=False, encoding="utf-8-sig")
    by_dest.to_csv(out / "compare_by_destination.csv", index=False, encoding="utf-8-sig")
    # 单侧键必须单独落盘：它们是「新到货 / 供应消失」，不能与缺口变化混谈
    if len(one_sided):
        cols = [c for c in ("_side",) + tuple(KEY) + ("destination", "qty_current",
                                                      "qty_higher", "gap_today",
                                                      "conditional_supply")
                if c in one_sided.columns]
        one_sided[cols].to_csv(out / "compare_one_sided.csv", index=False,
                               encoding="utf-8-sig")
    summary["one_sided_by_warehouse"] = (
        one_sided.groupby(["_side", "canonical_warehouse"]).size().reset_index(name="keys")
        .to_dict("records") if len(one_sided) else [])
    summary["top_movers"] = [
        dict(key="|".join(map(str, (r.canonical_sku, r.canonical_warehouse, r.canonical_uom))),
             destination_old=r.destination_old, destination_new=r.destination_new,
             delta_qty_current=round(float(r.delta_qty_current), 2),
             delta_gap_today=round(float(r.delta_gap_today or 0), 2))
        for r in merged.sort_values("delta_qty_current", key=lambda s: s.abs(), ascending=False)
        .head(args.top).itertuples()]
    (out / "compare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("keys_both", "keys_only_old", "keys_only_new",
                       "destinations_old", "destinations_new",
                       "destination_changed_keys", "totals")},
                     ensure_ascii=False, indent=1))
    print("输出：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
