# -*- coding: utf-8 -*-
"""对比 D6 v6.22（全 q95）与 v6.23（服务分档）的动作变化（只读）。"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
KEYS = ["product_id", "池", "形态", "UOM"]
WALL = ("KS0211-KJB-60-BEIGE", "KS0211-KJB-90-BEIGE",
        "KS0211-KJB-90-DEEPGREY", "KS0211-DM-60-DEEPGREY")


def load(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="1_全量动作")
    df[KEYS] = df[KEYS].astype(str)
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D6 v6.22 vs v6.23 动作对比（只读）")
    ap.add_argument("--old", default=f"{BA}/D6v6_22-1111/"
                    "D_Top50沙盒_D6_v6_22_2026-11-11.xlsx")
    ap.add_argument("--new", default=f"{BA}/D6v6_23-1112/"
                    "D_Top50沙盒_D6_v6_23_2026-11-12.xlsx")
    ap.add_argument("--out-csv", default=f"{BA}/D6v6_23-1112/"
                    "action_diff_vs_v6_22.csv")
    ap.add_argument("--out-report", default=f"{BA}/D6v6_23-1112/"
                    "action_diff_vs_v6_22_报告.md")
    args = ap.parse_args(argv)

    old = load(args.old)
    new = load(args.new)
    old_cols = ["建议动作", "建议数量", "新补数量", "催已有量", "净需求95"]
    new_cols = old_cols + ["服务档", "分位标签", "净需求(所选分位)"]
    m = old[KEYS + old_cols].merge(
        new[KEYS + new_cols], on=KEYS, how="outer", indicator=True,
        suffixes=("_622", "_623"))
    m = m.rename(columns={"服务档": "服务档_623", "分位标签": "分位标签_623",
                          "净需求(所选分位)": "净需求(所选分位)_623"})
    for c in ("建议动作", "服务档", "分位标签"):
        for suf in ("_622", "_623"):
            col = f"{c}{suf}"
            if col in m:
                m[col] = m[col].fillna("—").astype(str)
    for c in ("建议数量", "新补数量", "催已有量", "净需求95",
              "净需求(所选分位)"):
        for suf in ("_622", "_623"):
            col = f"{c}{suf}"
            if col in m:
                m[col] = pd.to_numeric(m[col], errors="coerce")
    m["动作变化"] = m["建议动作_622"] != m["建议动作_623"]
    m["数量差"] = (m["建议数量_623"].fillna(0) - m["建议数量_622"].fillna(0))
    m["数量变化"] = m["数量差"].abs() > 0.5
    m.to_csv(args.out_csv, index=False, encoding="utf-8-sig")

    both = m[m["_merge"] == "both"]
    trans = (both.groupby(["建议动作_622", "建议动作_623"]).size()
             .reset_index(name="键数").sort_values("键数", ascending=False))
    by_cls = (both.groupby("服务档_623").agg(
        keys=("product_id", "size"),
        action_changed=("动作变化", "sum"),
        qty_delta=("数量差", "sum")).reset_index())
    wall = m[m["product_id"].isin(WALL)].copy()

    L = ["# D6 v6.22 → v6.23 动作变化（服务分档 P2a）", "",
         f"- v6.22：全 q95；v6.23：A q95 / B q90 / C q85 / D q85",
         f"- 共同键 **{len(both)}**；仅 v6.22 **{int((m['_merge']=='left_only').sum())}**；"
         f"仅 v6.23 **{int((m['_merge']=='right_only').sum())}**",
         f"- 动作变化 **{int(both['动作变化'].sum())}** 键；数量变化 **{int(both['数量变化'].sum())}** 键；"
         f"总建议数量 v6.22 **{both['建议数量_622'].sum():.0f}** → v6.23 "
         f"**{both['建议数量_623'].sum():.0f}**（差 **{both['数量差'].sum():+.0f}**）。",
         "", "## 1. 动作转移", "",
         "| v6.22 | v6.23 | 键数 |", "|---|---|---:|"]
    for r in trans.itertuples(index=False):
        L.append(f"| {r.建议动作_622} | {r.建议动作_623} | {r.键数} |")
    L += ["", "## 2. 按服务档", "",
          "| 服务档 | 键数 | 动作变化 | 数量差合计 |", "|---|---:|---:|---:|"]
    for r in by_cls.itertuples(index=False):
        L.append(f"| {r.服务档_623} | {r.keys} | {int(r.action_changed)} | {r.qty_delta:+.0f} |")
    L += ["", "## 3. 软包墙围 4 SKU", "",
          "| SKU | 池 | 服务档 | 分位 | 动作 622→623 | 数量 622→623 | 差 | 净需求95→所选 |",
          "|---|---|---|---|---|---:|---:|---:|"]
    for _, r in wall.sort_values(["product_id", "池"]).iterrows():
        _old_q = r["建议数量_622"]
        _new_q = r["建议数量_623"]
        _old_net = r["净需求95_622"]
        _new_net = r.get("净需求(所选分位)_623", np.nan)
        L.append(
            f"| {r['product_id']} | {r['池']} | {r['服务档_623']} | {r['分位标签_623']} | "
            f"{r['建议动作_622']}→{r['建议动作_623']} | "
            f"{_old_q if pd.notna(_old_q) else '—'}→"
            f"{_new_q if pd.notna(_new_q) else '—'} | "
            f"{r['数量差']:+.0f} | "
            f"{_old_net if pd.notna(_old_net) else '—'}→"
            f"{_new_net if pd.notna(_new_net) else '—'} |")
    Path(args.out_report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))
    print("CSV：", args.out_csv)
    print("报告：", args.out_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
