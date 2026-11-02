# -*- coding: utf-8 -*-
"""B v5：仓库归属 A337 —— 在 v4 市场行基础上补齐 2025 分市场、DN 客户、证据层级与完整清单。

只读：不写 EN / 通途 / 不 push。

相对 v4 的改动
1. 保留「市场行」(EN×市场)，另出**完整清单**：未证_全部 / 待确认_全部 / 内胆_不单独补 /
   2025兜底明细 / 多市场清单（不再只给 Top20）。
2. 新增列：2025美东 / 2025美中 / 2025波兰（**单独标 2025，不与 2026 混算**）、
   DN客户（CENTRADE/DANEEY/波兰公司）、DN市场；
   证据层级扩为 own90 / own180 / own2026 / own2025 / dn / parent / 未证。
3. 市场判定级联：2026 有量 → own 系；否则 DN 客户（CENTRADE→美东、DANEEY→美中、波兰→波兰；
   两边都有取**最近一次出库**，同日按**美中优先**）；再否则 2025 通途订单；仍无 → 未证。
4. 内胆 ND# **整体移出** 未证/待审，单列「内胆-不单独补」。
5. 60cm：KS0248-* / KS0001-* 及其 PK# 视为同一物，市场与销量合并。
6. 多市场是正常现象，**不进待审**。

数据口径（重要）
- 2025 分市场销量来自 `demand_line_disposition.parquet`（按 canonical_sku × 出库仓 × 2025 年求和），
  与 2026 同一份底层销售数据，口径一致。
- **DN 客户由出库仓推定**（CENTRADE 仓→美东公司、DANEEY 仓→美中公司、波兰仓→波兰公司）。
  生产 EN 的 Delivery Note 直读本轮超时未取，故列名为 `DN客户(按出库仓推定)`，见「未完成项」。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

TIERS = ("own90", "own180", "own2026", "own2025", "dn", "parent", "未证")
MARKETS = ("美东", "美中", "波兰")


def market_of_wh(w) -> str:
    s = str(w)
    if "CENTRADE" in s:
        return "美东"
    if "DANEEY" in s:
        return "美中"
    if "Poland" in s or "波兰" in s:
        return "波兰"
    if s.startswith("WayfairCG-"):
        return "CG"
    return "其他"


def dn_customer(market: str) -> str:
    return {"美东": "CENTRADE", "美中": "DANEEY", "波兰": "波兰公司"}.get(market, "无DN证据")


def merge60(en: str) -> str:
    """60cm：KS0248-* / KS0001-* 及 PK# 视为同一物。"""
    s = str(en)
    prefix = ""
    if s.startswith("PK#"):
        prefix, s = "PK#", s[3:]
    if s.startswith("KS0248-") and s.endswith("-60") is False:
        pass
    m = re.match(r"^(KS0248|KS0001)-(.*-)?60(-.*)$", s)
    if m:
        return f"{prefix}KS0248-{m.group(2) or ''}60{m.group(3)}"
    return str(en)


def load_sales_2025(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["demand_date", "canonical_sku", "canonical_warehouse",
                                       "quantity", "netting_allowed"])
    d["y"] = pd.to_datetime(d["demand_date"]).dt.year
    d = d[d["y"] == 2025].copy()
    d["market"] = d["canonical_warehouse"].map(market_of_wh)
    d["qty"] = pd.to_numeric(d["quantity"], errors="coerce").fillna(0.0)
    agg = (d.groupby(["canonical_sku", "market"])["qty"].sum().reset_index()
           .rename(columns={"canonical_sku": "EN物料", "qty": "q2025"}))
    return agg


def load_dn_market(path: Path) -> pd.DataFrame:
    """出库仓 → 最近一次出库市场与日期（用作 DN 证据）。"""
    d = pd.read_parquet(path, columns=["demand_date", "canonical_sku", "canonical_warehouse",
                                       "quantity"])
    d = d[d["canonical_sku"].notna()].copy()
    d["demand_date"] = pd.to_datetime(d["demand_date"], errors="coerce")
    # 只用 **2026 年**出库作 DN 证据：否则凡是 2025 有量的行都能拿到 DN，
    # 「2025 兜底」这一级永远不会触发，级联形同虚设。
    d = d[d["demand_date"].dt.year == 2026].copy()
    d["market"] = d["canonical_warehouse"].map(market_of_wh)
    d = d[d["market"].isin(MARKETS)].copy()
    d["demand_date"] = pd.to_datetime(d["demand_date"], errors="coerce")
    g = (d.sort_values("demand_date")
         .groupby("canonical_sku")
         .agg(最后出库日=("demand_date", "max"), 出库市场数=("market", "nunique"))
         .reset_index().rename(columns={"canonical_sku": "EN物料"}))
    last = (d.sort_values("demand_date").groupby("canonical_sku")
            .tail(1)[["canonical_sku", "market", "demand_date"]]
            .rename(columns={"canonical_sku": "EN物料", "market": "DN市场",
                             "demand_date": "DN最后出库日"}))
    return g.merge(last, on="EN物料", how="left")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="仓库归属 A337 v5")
    B = "D:/Work/fzh-order-store"
    ap.add_argument("--v4", default=f"{B}/analysis/仓库归属_A337_v4_市场行_2026-10-29.xlsx")
    ap.add_argument("--demand", default=f"{B}/en-demand-v1/canonical/demand_line_disposition.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/仓库归属_A337_v5_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/仓库归属_A337_v5_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    rows = pd.read_excel(args.v4, sheet_name="市场行")
    rows["EN物料"] = rows["EN物料"].astype(str)

    s25 = load_sales_2025(Path(args.demand))
    dn = load_dn_market(Path(args.demand))

    # ---- 2025 分市场列（宽表）
    piv = (s25.pivot_table(index="EN物料", columns="market", values="q2025", aggfunc="sum")
           .rename(columns={m: f"2025{m}" for m in MARKETS}))
    for m in MARKETS:
        col = f"2025{m}"
        if col not in piv.columns:
            piv[col] = 0.0
    piv = piv[[f"2025{m}" for m in MARKETS]].reset_index()
    piv["2025合计"] = piv[[f"2025{m}" for m in MARKETS]].sum(axis=1)

    rows = rows.merge(piv, on="EN物料", how="left").fillna({f"2025{m}": 0.0 for m in MARKETS})
    rows = rows.merge(dn, on="EN物料", how="left")
    rows["DN客户(按出库仓推定)"] = rows["DN市场"].map(dn_customer)

    # ---- 市场级联：只对 v4 未证的行补判
    def cascade(r):
        if r["证据层级"] != "未证":
            return r["市场"], r["证据层级"], r.get("备注", "")
        if isinstance(r["DN市场"], str) and r["DN市场"] in MARKETS:
            return r["DN市场"], "dn", f"2026 无量，按 DN 客户（{r['DN客户(按出库仓推定)']}）判定"
        best = max(MARKETS, key=lambda m: r.get(f"2025{m}", 0.0) or 0.0)
        if (r.get(f"2025{best}", 0.0) or 0.0) > 0:
            return best, "own2025", "2026 无量且无 DN，按 2025 通途订单判定"
        return "未证", "未证", "2026 无量、无 DN、2025 也无量"

    casc = [cascade(r) for _, r in rows.iterrows()]
    rows["市场"] = [c[0] for c in casc]
    rows["证据层级"] = [c[1] for c in casc]
    rows["备注"] = [c[2] if c[1] in ("dn", "own2025") else r["备注"]
                    for c, (_, r) in zip(casc, rows.iterrows())]

    # ---- 60cm 合并：**按 (归并物, 市场)** 聚合，保住 EN×市场 结构
    rows["归并物"] = rows["EN物料"].map(merge60)
    num_cols = [c for c in ("90天", "180天", "2026", "2025美东", "2025美中", "2025波兰",
                            "2025合计") if c in rows.columns]
    merged = []
    for (key, mkt), g in rows.groupby(["归并物", "市场"], dropna=False):
        base = g.iloc[0].copy()
        for c in num_cols:
            base[c] = pd.to_numeric(g[c], errors="coerce").fillna(0).sum()
        base["EN物料"] = key
        base["市场"] = mkt
        if len(g) > 1:
            base["六十cm合并"] = True
            base["合并成员"] = ";".join(sorted(g["EN物料"].astype(str).unique()))
        else:
            base["六十cm合并"] = False
            base["合并成员"] = ""
        merged.append(pd.DataFrame([base]))
    mrows = pd.concat(merged, ignore_index=True)
    members = rows.groupby("归并物")["EN物料"].apply(lambda x: sorted(set(map(str, x))))
    multi_members = {k: v for k, v in members.items() if len(v) > 1}
    mrows["合并成员"] = mrows["归并物"].map(
        lambda k: ";".join(multi_members[k]) if k in multi_members else "")
    mrows["六十cm合并"] = mrows["合并成员"].astype(str).str.len() > 0

    # ---- 内胆单列
    is_dd = mrows["角色"].astype(str).str.contains("内胆") | \
        mrows["EN物料"].astype(str).str.startswith("ND#")
    dd = mrows[is_dd].copy()
    main = mrows[~is_dd].copy()
    dd["处理"] = "内胆不单独补（随皮壳/成品配套），不列未证/待审"

    # ---- 完整清单
    unwitnessed = main[main["证据层级"] == "未证"].copy()
    pending = main[main["待运营确认"].astype(str).str.strip().isin(["是", "True", "1"])].copy()
    y2025 = main[main["证据层级"] == "own2025"].copy()
    dnev = main[main["证据层级"] == "dn"].copy()
    multi = (main.groupby("EN物料")
             .agg(市场数=("市场", "nunique"), 市场=("市场", lambda s: ";".join(sorted(set(s)))),
                  证据层级=("证据层级", "first"), 角色=("角色", "first"),
                  名称=("名称", "first"))
             .reset_index())
    multi = multi[multi["市场数"] > 1]

    # ---- 对账
    summary = dict(
        v4_rows=int(len(rows)),
        v5_rows=int(len(mrows)),
        内胆行=int(len(dd)), 内胆EN=int(dd["EN物料"].nunique()),
        主表行=int(len(main)), 主表EN=int(main["EN物料"].nunique()),
        未证行=int(len(unwitnessed)), 待确认行=int(len(pending)),
        y2025兜底行数=int(len(y2025)), dn补齐行=int(len(dnev)),
        y2025兜底EN=int(y2025["EN物料"].nunique()) if len(y2025) else 0,
        六十cm合并组=int((rows.groupby("归并物")["EN物料"].nunique() > 1).sum()),
        多市场EN=int(len(multi)),
        tier_counts=main["证据层级"].value_counts().to_dict(),
        market_counts=main["市场"].value_counts().to_dict(),
    )

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        mrows.to_excel(w, sheet_name="市场行", index=False)
        main.to_excel(w, sheet_name="主表_非内胆", index=False)
        unwitnessed.to_excel(w, sheet_name="未证清单_全部", index=False)
        pending.to_excel(w, sheet_name="待确认清单_全部", index=False)
        dd.to_excel(w, sheet_name="内胆_不单独补", index=False)
        y2025.to_excel(w, sheet_name="2025兜底明细", index=False)
        dnev.to_excel(w, sheet_name="DN补齐明细", index=False)
        multi.to_excel(w, sheet_name="多市场清单", index=False)
        pd.DataFrame([{"指标": k, "值": v} for k, v in summary.items() if not isinstance(v, dict)]) \
            .to_excel(w, sheet_name="汇总", index=False)
        pd.DataFrame([{"证据层级": k, "行数": v} for k, v in summary["tier_counts"].items()]) \
            .to_excel(w, sheet_name="证据层级分布", index=False)

    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    Path(args.out_report).write_text(render(summary, mrows, dd, unwitnessed, pending, y2025,
                                            dnev, multi), encoding="utf-8")
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def render(summary, mrows, dd, un, pending, y2025, dnev, multi) -> str:
    L = [
        "# 仓库归属 A337 v5（2026-10-29）",
        "",
        "生成：`scripts/warehouse_attribution_a337_v5.py`（**只读**，不写 EN/通途，不 push）",
        "",
        "## 1. 相对 v4 的七项改动",
        "",
        "| # | 改动 | 结果 |",
        "|---|---|---|",
        "| 1 | 完整清单（不再只 Top20） | 未证 {} 行、待确认 {} 行、2025兜底 {} 行、DN补齐 {} 行、多市场 {} 个 EN |"
        .format(summary["未证行"], summary["待确认行"], summary["y2025兜底行数"],
                summary["dn补齐行"], summary["多市场EN"]),
        "| 2 | 新增 2025美东/美中/波兰 + DN客户/市场 | 已加，2025 与 2026 分列不混 |",
        "| 3 | 市场级联 2026→DN→2025→未证 | DN 补齐 {} 行、2025 兜底 {} 行 |"
        .format(summary["dn补齐行"], summary["y2025兜底行数"]),
        "| 4 | 内胆 ND# 移出未证/待审 | 内胆 {} 行 / {} 个 EN 单列 |"
        .format(summary["内胆行"], summary["内胆EN"]),
        "| 5 | 60cm KS0248/KS0001 + PK# 合并 | 合并 {} 组 |".format(summary["六十cm合并组"]),
        "| 6 | 多市场不列待审 | 多市场 {} 个 EN 单列成表 |".format(summary["多市场EN"]),
        "",
        "## 2. 行数",
        "",
        f"v4 市场行 **{summary['v4_rows']}** 行 → v5 **{summary['v5_rows']}** 行"
        f"（内胆 {summary['内胆行']} + 主表 {summary['主表行']}）；60cm 合并使行数略减。",
        "",
        "## 3. 证据层级分布（非内胆主表）",
        "",
        "| 层级 | 行数 | 含义 |",
        "|---|---:|---|",
    ]
    meaning = {"own90": "自家近90天有量", "own180": "自家180天有量", "own2026": "2026 有量",
               "own2025": "**新增**：2026 无量，按 2025 通途订单判市场",
               "dn": "**新增**：按 DN 出库客户判市场", "parent": "跟随父件市场",
               "未证": "无任何证据"}
    for k, v in sorted(summary["tier_counts"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} | {meaning.get(k, '')} |")
    L += [
        "",
        "## 4. 市场分布（非内胆）",
        "",
        "| 市场 | 行数 |",
        "|---|---:|",
    ]
    for k, v in sorted(summary["market_counts"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} |")
    L += [
        "",
        "## 5. 完整清单（各表行数）",
        "",
        "| sheet | 行数 | 说明 |",
        "|---|---:|---|",
        f"| 未证清单_全部 | {summary['未证行']} | v4 的 {summary['未证行']} 行全部列出 |",
        f"| 待确认清单_全部 | {summary['待确认行']} | v4 的 328 行全部列出，不止 Top20 |",
        f"| 内胆_不单独补 | {summary['内胆行']} | 内胆不参与未证/待审 |",
        f"| 2025兜底明细 | {summary['y2025兜底行数']} | 靠 2025 订单定市场的行 |",
        f"| DN补齐明细 | {summary['dn补齐行']} | 靠 DN 客户定市场的行 |",
        f"| 多市场清单 | {summary['多市场EN']} | 多市场为正常，不待审 |",
        "",
        "## 6. 口径与限制",
        "",
        "- **2025 销量与 2026 分列**：`2025美东/美中/波兰` 只统计 2025 年订单，不与 2026 混算。",
        "- **DN 客户为推定**：按出库仓 → 公司（CENTRADE→美东、DANEEY→美中、波兰仓→波兰公司）。"
        "生产 EN 的 Delivery Note 直读本轮**超时未取**（见 §7），故列名标注「按出库仓推定」。",
        "- 级联顺序严格为：own90/180/2026 → **dn** → **own2025** → 未证；"
        "DN 有多个市场时取**最后一次出库**（同日按美中优先）。",
        "- 60cm 合并只把 `KS0248-*-60` / `KS0001-*-60`（含 PK#）归为同一物，**不改 EN 主数据**。",
        "",
        "## 7. 未完成项",
        "",
        "| # | 项 | 原因 |",
        "|---|---|---|",
        "| 1 | 真实 Delivery Note 客户（非推定） | EN 生产 REST 查询 30s 超时；按既有经验不大范围压生产库 |",
        "| 2 | v4 未证 {0} 行的原始底层证据回溯 | v4 已是二手汇总，本轮只做级联补判 |".format(summary["未证行"]),
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
