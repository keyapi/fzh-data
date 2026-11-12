# -*- coding: utf-8 -*-
"""USNJ 试点对比：v6.22(q95) / v6.23(balance) / v6.24(balance|control|service)。"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
KEYS = ["product_id", "池", "形态", "UOM"]
AS_OF = pd.Timestamp("2026-11-11")


def load(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="1_全量动作")
    df = df[df["池"].astype(str) == "美东USNJ"].copy()
    for c in KEYS:
        df[c] = df[c].astype(str)
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="USNJ 试点对比（只读）")
    ap.add_argument("--v622", default=f"{BA}/D6v6_22-1111/"
                    "D_Top50沙盒_D6_v6_22_2026-11-11.xlsx")
    ap.add_argument("--v623", default=f"{BA}/D6v6_23-1112/"
                    "D_Top50沙盒_D6_v6_23_2026-11-12.xlsx")
    ap.add_argument("--v624", default=f"{BA}/D6v6_24-1112/"
                    "D_Top50沙盒_D6_v6_24_2026-11-12.xlsx")
    ap.add_argument("--v624-control", default=f"{BA}/D6v6_24-1112/control/"
                    "D_Top50沙盒_D6_v6_24_control_2026-11-12.xlsx")
    ap.add_argument("--v624-service", default=f"{BA}/D6v6_24-1112/service/"
                    "D_Top50沙盒_D6_v6_24_service_2026-11-12.xlsx")
    ap.add_argument("--out-csv", default=f"{BA}/D6v6_24-1112/"
                    "usnj_pilot_compare_20261112.csv")
    ap.add_argument("--out-report", default=f"{BA}/D6v6_24-1112/"
                    "usnj_pilot_compare_20261112.md")
    args = ap.parse_args(argv)

    v622, v623, v624 = load(args.v622), load(args.v623), load(args.v624)
    v624c, v624s = load(args.v624_control), load(args.v624_service)

    def _summ(df):
        cov = (pd.to_datetime(df["需要日"], errors="coerce") - AS_OF).dt.days
        _net = ("净需求(所选分位)" if "净需求(所选分位)" in df.columns else "净需求95")
        return dict(keys=len(df), action=df["建议动作"].value_counts().to_dict(),
                    qty=float(df["建议数量"].fillna(0).sum()),
                    new=float(df["新补数量"].fillna(0).sum()),
                    exp=float(df["催已有量"].fillna(0).sum()),
                    net=float(df[_net].fillna(0).sum()),
                    supply=float(df["C可发供给"].fillna(0).sum()),
                    cover_median=float(cov.median()) if len(cov) else np.nan,
                    cover_zero=int((cov <= 0).sum()))

    S = {"v622": _summ(v622), "v623": _summ(v623), "v624_balance": _summ(v624),
         "v624_control": _summ(v624c), "v624_service": _summ(v624s)}
    m = v622[KEYS + ["建议动作", "建议数量", "新补数量", "催已有量", "净需求95"]].merge(
        v623[KEYS + ["建议动作", "建议数量", "新补数量", "催已有量",
                     "净需求95", "服务档", "分位标签"]],
        on=KEYS, how="outer", suffixes=("_622", "_623"), indicator=True)
    for c in ("建议动作",):
        for suf in ("_622", "_623"):
            m[c + suf] = m[c + suf].fillna("—").astype(str)
    for c in ("建议数量", "新补数量", "催已有量", "净需求95"):
        for suf in ("_622", "_623"):
            m[c + suf] = pd.to_numeric(m[c + suf], errors="coerce")
    m["动作变化"] = m["建议动作_622"] != m["建议动作_623"]
    m["数量差"] = m["建议数量_623"].fillna(0) - m["建议数量_622"].fillna(0)
    m.to_csv(args.out_csv, index=False, encoding="utf-8-sig")

    both = m[m["_merge"] == "both"]
    trans = (both.groupby(["建议动作_622", "建议动作_623"]).size()
             .reset_index(name="键数").sort_values("键数", ascending=False))
    to_no = both[(both["建议动作_622"] == "补") & (both["建议动作_623"] == "不补")]
    by_cls = (to_no.groupby("服务档").size().reset_index(name="补→不补")
              .sort_values("补→不补", ascending=False))

    lines = ["# USNJ 试点对比（v6.22 → v6.24）", "",
             f"- as-of {AS_OF.date()}；仅 USNJ；v6.24 默认 balance",
             "- **成本**：D6 无单位成本列，本报告用数量代理；不做库存金额推断。",
             "", "## 1. 全量对比", "",
             "| 版本 | 键数 | 补 | 不补 | 催已有 | 观察 | 建议数量 | 新补 | 催已有量 | 净需求(所选) | C可发供给 | 覆盖天数中位* | 覆盖≤0 键 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, s in S.items():
        a = s["action"]
        lines.append(f"| {k} | {s['keys']} | {a.get('补',0)} | {a.get('不补',0)} | "
                     f"{a.get('催已有',0)} | {a.get('观察',0)} | {s['qty']:.0f} | "
                     f"{s['new']:.0f} | {s['exp']:.0f} | {s['net']:.0f} | "
                     f"{s['supply']:.0f} | {s['cover_median']:.0f} | {s['cover_zero']} |")
    lines += ["", "## 2. v6.22 → v6.23 动作转移（USNJ）", "",
              "| v6.22 | v6.23 | 键数 |", "|---|---|---:|"]
    for r in trans.itertuples(index=False):
        lines.append(f"| {r.建议动作_622} | {r.建议动作_623} | {r.键数} |")
    lines += ["", f"- 全公司 250 个「补→不补」中，**USNJ {len(to_no)} 个**；"
              f"按 v6.23 服务档：{by_cls.set_index('服务档')['补→不补'].to_dict()}。",
              "", "## 3. v6.23 → v6.24 预设", "",
              "| 版本 | 补 | 不补 | 建议数量 | 相对 v6.23 数量 |",
              "|---|---:|---:|---:|---:|"]
    for k, s in (("v6.24 balance", S["v624_balance"]), ("v6.24 control", S["v624_control"]),
                 ("v6.24 service", S["v624_service"])):
        lines.append(f"| {k} | {s['action'].get('补',0)} | {s['action'].get('不补',0)} | "
                     f"{s['qty']:.0f} | {s['qty']-S['v623']['qty']:+.0f} |")
    lines += ["", "- balance 与 v6.23 相同（设计如此）；control 压 B→q85，service 抬 B→q95/C→q90。",
              "- *覆盖天数用 D6 `需要日−as-of`，D6 需要日封顶 97 天；≤0 表示当前已无覆盖。",
              "- 无单位成本列，库存金额未估算；`C可发供给`/`建议数量` 为数量代理。", ""]
    Path(args.out_report).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:14]))
    print("CSV：", args.out_csv)
    print("报告：", args.out_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
