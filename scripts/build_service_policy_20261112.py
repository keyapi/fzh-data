# -*- coding: utf-8 -*-
"""生成 service_policy（P2a）：D3b v3.11 分类 + 2026 销量 → ABC×XYZ → A/B/C/D。

只读：不写 EN/通途、不预测、不下单。
输出 CSV 列：sku,pool,physical_form,canonical_uom,class,abc_class,xyz_class,
service_level_prior,quantile,quantile_label,basis,sales_2026,sales_share,cum_share,
demand_pattern,sbc_class,adi,cv2,n_obs_train,n_pos_train。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supply_netting.service_policy import (
    CLASS_QUANTILE, DEFAULT_PRESET, PRESETS, SERVICE_CLASSES, apply_overrides,
    assign_abc, assign_service_class, assign_xyz, class_quantile,
)

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
RULE_VERSION = "SERVICE-POLICY-v1-2026-11-12"


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_policy(d3b_cls: pd.DataFrame, series: pd.DataFrame,
                 preset: str = DEFAULT_PRESET,
                 overrides: pd.DataFrame | None = None) -> pd.DataFrame:
    """纯计算：分类 + 2026 销量 → service policy 行。"""
    df = d3b_cls.copy()
    for c in KEYS:
        df[c] = df[c].astype(str)
    s = series.copy()
    s["month"] = s["month"].astype(str)
    s = s[(s["month"] >= "202601") & (s["month"] <= "202610")]
    for c in KEYS:
        s[c] = s[c].astype(str)
    sales = (s.groupby(KEYS)["qty"].sum().rename("sales_2026").reset_index())
    df = df.merge(sales, on=KEYS, how="left")
    df["sales_2026"] = pd.to_numeric(df["sales_2026"], errors="coerce").fillna(0.0)
    total = float(df["sales_2026"].sum())

    # ABC：按销量降序 + 键 tie-break，累计 80/15/5
    df = df.sort_values(["sales_2026"] + KEYS,
                        ascending=[False] + [True] * len(KEYS)).reset_index(drop=True)
    df["abc_class"] = assign_abc(df["sales_2026"]).values
    df["sales_share"] = (df["sales_2026"] / total) if total > 0 else 0.0
    df["cum_share"] = (df["sales_2026"].cumsum() / total) if total > 0 else 0.0

    sbc = (df["sbc_class_train"] if "sbc_class_train" in df.columns
           else df.get("sbc_class", pd.Series("", index=df.index)))
    dp = (df["demand_pattern_train"] if "demand_pattern_train" in df.columns
          else df.get("demand_pattern", pd.Series("", index=df.index)))
    df["xyz_class"] = [assign_xyz(a, b) for a, b in zip(sbc, dp)]
    df["class"] = [assign_service_class(a, x, d, s)
                   for a, x, d, s in zip(df["abc_class"], df["xyz_class"], dp,
                                         df["sales_2026"])]
    df = apply_overrides(df, overrides=overrides, preset=preset)
    df["demand_pattern"] = dp.astype(str)
    df["sbc_class"] = sbc.astype(str)
    for c in ("adi", "cv2", "n_obs_train", "n_pos_train"):
        if c not in df.columns:
            df[c] = np.nan
    return df.sort_values(KEYS).reset_index(drop=True)


def run_selftests() -> list[tuple[str, bool, str]]:
    t = []
    abc = assign_abc(pd.Series([50.0, 30.0, 15.0, 5.0]))
    t.append(("ABC 80/15/5（跨 80 的件留 A）",
              list(abc) == ["A", "A", "B", "C"], list(abc)))
    t.append(("XYZ：smooth/intermittent/lumpy/new",
              (assign_xyz("smooth", "smooth") == "X"
               and assign_xyz("intermittent", "intermittent") == "Y"
               and assign_xyz("lumpy", "lumpy") == "Z"
               and assign_xyz("smooth", "new") == "Z"),
              "X/Y/Z/Z"))
    t.append(("服务档矩阵 A(X/Y)→A、A(Z)→B、B(Z)→C、C(Z)→D",
              (assign_service_class("A", "X", "smooth", 10) == "A"
               and assign_service_class("A", "Z", "lumpy", 10) == "B"
               and assign_service_class("B", "Y", "intermittent", 10) == "B"
               and assign_service_class("B", "Z", "lumpy", 10) == "C"
               and assign_service_class("C", "X", "smooth", 10) == "C"
               and assign_service_class("C", "Z", "lumpy", 10) == "D"),
              "A/B/B/C/C/D"))
    t.append(("零销量/新品/淘汰 → D",
              (assign_service_class("A", "X", "new", 10) == "D"
               and assign_service_class("A", "X", "obsolescent", 10) == "D"
               and assign_service_class("A", "X", "smooth", 0) == "D"),
              "D/D/D"))
    t.append(("class→quantile A95/B90/C85/D85",
              [class_quantile(c)["quantile"] for c in SERVICE_CLASSES]
              == [0.95, 0.90, 0.85, 0.85],
              str([class_quantile(c)["quantile"] for c in SERVICE_CLASSES])))
    try:
        class_quantile("Z")
        unknown_ok = False
    except ValueError:
        unknown_ok = True
    t.append(("未知 class 不自动补", unknown_ok, "ValueError"))
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 service_policy（P2a，只读）")
    ap.add_argument("--d3b", default=f"{BA}/D3b-v3_11-20261112/"
                    "D_历史归一与回测_D3b_v3_11_2026-11-12.xlsx")
    ap.add_argument("--series", default=f"{BA}/D3b-v3_11-20261112/"
                    "D3b_v3_11_series_current_2026-11-12.parquet")
    ap.add_argument("--out-csv", default=f"{BA}/service-policy-20261112/"
                    "service_policy_20261112.csv")
    ap.add_argument("--out-report", default=f"{BA}/service-policy-20261112/"
                    "service_policy_20261112_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/service-policy-20261112/"
                    "service_policy_20261112.manifest.json")
    ap.add_argument("--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS),
                    help="服务预设：balance/control/service")
    ap.add_argument("--overrides", default="",
                    help="例外覆盖 CSV：sku,pool,preset_or_quantile,reason,owner,as_of")
    ap.add_argument("--out-overrides-audit", default=f"{BA}/service-policy-20261112/"
                    "service_policy_overrides_audit_20261112.csv")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        tests = run_selftests()
        for name, ok, detail in tests:
            print(f"[{'PASS' if ok else 'FAIL'}] {name}｜{detail}")
        print(f"\n{sum(ok for _, ok, _ in tests)}/{len(tests)} 通过")
        return 0 if all(ok for _, ok, _ in tests) else 1

    d3b_cls = pd.read_excel(args.d3b, sheet_name="3_分类")
    series = pd.read_parquet(args.series)
    if args.overrides and not Path(args.overrides).exists():
        raise FileNotFoundError(f"overrides 文件不存在：{args.overrides}")
    overrides = (pd.read_csv(args.overrides, dtype=str) if args.overrides else None)
    pol = build_policy(d3b_cls, series, preset=args.preset, overrides=overrides)

    missing = int((~pol["class"].isin(SERVICE_CLASSES)).sum())
    qbad = 0
    for _, r in pol.iterrows():
        if r["preset"] in PRESETS:
            if r["quantile"] != PRESETS[r["preset"]][r["class"]]["quantile"]:
                qbad += 1
        elif r["preset"] == "custom":
            if abs(float(r["quantile"]) - float(r["service_level_prior"])) > 1e-9:
                qbad += 1
        else:
            qbad += 1
    conv = [("键数", len(pol)),
            ("preset", args.preset),
            ("2026 销量", round(float(pol["sales_2026"].sum()), 3)),
            ("class 分布", json.dumps(pol["class"].value_counts().to_dict(),
                                    ensure_ascii=False)),
            ("ABC×XYZ", json.dumps(
                pd.crosstab(pol["abc_class"], pol["xyz_class"]).to_dict(),
                ensure_ascii=False)),
            ("overrides", int(pol["override_applied"].sum())),
            ("未知 class 行", missing),
            ("class→quantile 不一致", qbad)]
    if missing or qbad:
        print("SELF-CHECK FAILED：", conv)
        return 1

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
    out_cols = ["sku", "pool", "physical_form", "canonical_uom", "class",
                "abc_class", "xyz_class", "preset", "service_level_prior", "quantile",
                "quantile_label", "basis", "sales_2026", "sales_share", "cum_share",
                "demand_pattern", "sbc_class", "adi", "cv2", "n_obs_train", "n_pos_train",
                "override_applied", "override_value", "override_reason",
                "override_owner", "override_as_of", "override_status"]
    pol_out = pol.rename(columns={"product_id": "sku"})[out_cols]
    pol_out.to_csv(args.out_csv, index=False, encoding="utf-8-sig")
    audit = pol_out[pol_out["override_applied"].astype(bool)].copy()
    audit.to_csv(args.out_overrides_audit, index=False, encoding="utf-8-sig")

    cls_tbl = (pol.groupby("class").agg(keys=("product_id", "size"),
                                        sales=("sales_2026", "sum"))
               .reindex(list(SERVICE_CLASSES)).fillna(0).reset_index()
               .rename(columns={"class": "service_class"}))
    total_sales = float(pol["sales_2026"].sum())
    cls_tbl["sales_share"] = (cls_tbl["sales"] / total_sales) if total_sales > 0 else 0.0
    cls_tbl["quantile"] = [PRESETS[args.preset][c]["quantile"]
                           for c in cls_tbl["service_class"]]
    cls_tbl["prior"] = [PRESETS[args.preset][c]["service_level_prior"]
                        for c in cls_tbl["service_class"]]
    cls_tbl["basis"] = [PRESETS[args.preset][c]["basis"]
                        for c in cls_tbl["service_class"]]

    L = ["# 服务分档政策（P2c，2026-11-12）", "",
         f"- 规则版本：`{RULE_VERSION}`；预设 **{args.preset}**",
         f"- 输入：D3b v3.11 `3_分类` + 2026-01..10 当前 owner 销量",
         f"- 键数 **{len(pol)}**；2026 销量 **{total_sales:.0f}**；"
         f"覆盖 **{int(pol['override_applied'].sum())}** 行",
         "", "## 1. 方法", "",
         "- **ABC**：2026 销量降序累计 **80/15/5**；跨过 80% 的那一件留在 A（A 可略超 80%）。",
         "- **XYZ**：X=`smooth`；Y=`intermittent`；Z=`lumpy/erratic/n/a` 或 "
         "`obsolescent/new/short/no_demand`（用 `sbc_class_train`/`demand_pattern_train`）。",
         "- **A/B/C/D**：A(X/Y)=A；A(Z)/B(X/Y)=B；B(Z)/C(X/Y)=C；"
         "C(Z)、零销量、新品、淘汰、短史=D。",
         f"- **预设**：`{args.preset}` → {json.dumps(
             {c: PRESETS[args.preset][c]['quantile_label'] for c in SERVICE_CLASSES},
             ensure_ascii=False)}；D 为 fill-rate 代理。",
         "- 覆盖 CSV：`sku,pool,preset_or_quantile,reason,owner,as_of`；未知键/空 reason/非法值直接报错。",
         "- 不是服务承诺；未知 class 不自动补，D6 遇到 missing/unknown 会转“观察”。",
         "", "## 2. 各类键数/销量", "",
         "| class | 键数 | 2026 销量 | 销量占比 | quantile | prior | basis |",
         "|---|---:|---:|---:|---:|---:|---|"]
    for r in cls_tbl.itertuples(index=False):
        L.append(f"| {r.service_class} | {int(r.keys)} | {r.sales:.0f} | "
                 f"{r.sales_share:.1%} | {r.quantile:.2f} | {r.prior:.2f} | {r.basis} |")
    L += ["", "## 3. ABC × XYZ 键数", "",
          "| ABC | X | Y | Z |", "|---|---:|---:|---:|"]
    ct = pd.crosstab(pol["abc_class"], pol["xyz_class"]).reindex(
        index=["A", "B", "C"], columns=["X", "Y", "Z"]).fillna(0).astype(int)
    for abc in ("A", "B", "C"):
        L.append(f"| {abc} | {ct.loc[abc, 'X']} | {ct.loc[abc, 'Y']} | {ct.loc[abc, 'Z']} |")
    L += ["", "## 4. 软包墙围 4 SKU", "",
          "| sku | pool | ABC | XYZ | class | quantile | 2026 销量 |",
          "|---|---|---|---|---|---:|---:|"]
    for _, r in pol[pol["product_id"].isin(
            ["KS0211-KJB-60-BEIGE", "KS0211-KJB-90-BEIGE",
             "KS0211-KJB-90-DEEPGREY", "KS0211-DM-60-DEEPGREY"])].iterrows():
        L.append(f"| {r['product_id']} | {r['pool']} | {r['abc_class']} | {r['xyz_class']} | "
                 f"{r['class']} | {r['quantile']:.2f} | {r['sales_2026']:.0f} |")
    if len(audit):
        L += ["", "## 5. 覆盖审计", "",
              "| sku | pool | class | preset | quantile | 覆盖值 | reason | owner | as_of |",
              "|---|---|---|---|---:|---|---|---|---|"]
        for _, r in audit.iterrows():
            L.append(f"| {r['sku']} | {r['pool']} | {r['class']} | {r['preset']} | "
                     f"{r['quantile']:.2f} | {r['override_value']} | "
                     f"{r['override_reason']} | {r['override_owner']} | {r['override_as_of']} |")
    else:
        L += ["", "## 5. 覆盖审计", "", "- 本轮无覆盖。"]
    Path(args.out_report).write_text("\n".join(L) + "\n", encoding="utf-8")

    manifest = dict(
        rule_version=RULE_VERSION,
        preset=args.preset,
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        inputs=dict(d3b=dict(path=args.d3b, sha256=sha256(args.d3b)),
                    series=dict(path=args.series, sha256=sha256(args.series)),
                    overrides=(dict(path=args.overrides, sha256=sha256(args.overrides))
                               if args.overrides and Path(args.overrides).exists() else None)),
        outputs=dict(csv=dict(path=args.out_csv, sha256=sha256(args.out_csv),
                              rows=len(pol_out)),
                     report=dict(path=args.out_report, sha256=sha256(args.out_report)),
                     overrides_audit=dict(path=args.out_overrides_audit,
                                          sha256=sha256(args.out_overrides_audit),
                                          rows=len(audit))),
        counts=dict(keys=len(pol), total_sales_2026=total_sales,
                    class_counts=pol["class"].value_counts().to_dict(),
                    class_sales=pol.groupby("class")["sales_2026"].sum().to_dict(),
                    overrides=int(pol["override_applied"].sum())),
        selfcheck=dict(unknown_class_rows=missing, class_quantile_mismatch=qbad),
    )
    Path(args.manifest).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(conv, ensure_ascii=False))
    print("CSV：", args.out_csv)
    print("报告：", args.out_report)
    print("manifest：", args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
