# -*- coding: utf-8 -*-
"""USNJ recent-demand family/fabric analysis (read-only).

Classifies USNJ order lines by product family and fabric using EN active
universe names/item groups, then compares last 90d, last 180d and 2026.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
A_FILE = BASE / "SKU活跃宇宙_2026-10-29_FINAL.xlsx"
BRIDGE = BASE / "codex-repair-20261102/D_历史归一与回测_D3b_v3_4_2026-11-02.xlsx"
B_FILE = BASE / "仓库归属_A337_v6r10_2026-10-30.xlsx"
ORDERS = Path("D:/Work/fzh-order-store/orders_unified.parquet")
OUT_SUM = BASE / "usnj_family_fabric_20261103_v2.csv"
OUT_PROD = BASE / "usnj_recent_products_20261103_v2.csv"
OUT_MD = BASE / "usnj_family_fabric_report_20261103_v2.md"

USNJ_WAREHOUSES = {"CENTRADE", "美东-CENTRADE", "北美之路-NJ02"}


def family_of(group: str, name: str) -> str:
    x = f"{group} {name}"
    if "碎海绵" in x:
        return "三角靠枕(碎海绵)"
    if "弧形PP棉印花靠枕" in x:
        return "弧形PP棉印花靠枕"
    if "星球抱枕" in x:
        return "星球抱枕"
    if "印花石头抱枕" in x:
        return "印花石头抱枕"
    if "泰迪熊" in x:
        return "泰迪熊"
    if "三角靠枕" in x:
        return "三角靠枕"
    if "平条靠枕" in x:
        return "平条靠枕"
    if "麻将" in x:
        return "麻将沙发"
    if "主体骨架" in x or "L形支架" in x:
        return "铁架子/骨架"
    return "其他"


def fabric_of(name: str) -> str:
    # EN naming differs by family: 三角靠枕 uses 平绒, 平条 uses 纯棉平绒.
    # Treat both as 纯棉平绒; 新棉麻本色/HEMP is confirmed as 纯棉麻 by Jing (2026-11-03).
    if "新棉麻" in name:
        return "纯棉麻"
    if "贡缎提花" in name:
        return "贡缎提花(非Jing清单)"
    for f in ["纯棉宽条绒", "纯棉印花", "纯棉麻", "契若金兰", "纯棉平绒", "平绒", "宽条绒", "条绒", "荷兰绒", "涤麻"]:
        if f in name:
            return "纯棉平绒" if f in ("平绒", "纯棉平绒") else f
    return "其他/未标"


def main() -> int:
    a = pd.read_excel(A_FILE, sheet_name="活跃宇宙")
    a = a[["EN物料", "名称", "角色", "物料组", "当前库存", "2026销量", "近6月销量"]].copy()
    a["EN物料"] = a["EN物料"].astype(str)
    br = pd.read_excel(BRIDGE, sheet_name="1_映射桥")
    sku_map = dict(zip(br["sku_tongtool"].astype(str).str.lower(), br["product"].astype(str)))
    b = pd.read_excel(B_FILE, sheet_name="主表")
    bd = b[b["是否需求行"] == "Y"].copy()
    owner = bd.groupby("产品键")["美国责任方"].agg(
        lambda s: next((str(v) for v in s if pd.notna(v)), None)
    ).to_dict()

    o = pd.read_parquet(ORDERS)
    o["sale_date"] = pd.to_datetime(o["sale_date"], errors="coerce")
    o = o[o["warehouse"].isin(USNJ_WAREHOUSES)].copy()
    o["product"] = o["sku_tongtool"].astype(str).str.lower().map(sku_map)
    o = o[o["product"].notna()].copy()
    o = o.merge(a, left_on="product", right_on="EN物料", how="left")
    o["family"] = [family_of(str(g), str(n)) for g, n in zip(o["物料组"].fillna(""), o["名称"].fillna(""))]
    o["fabric"] = o["名称"].fillna("").map(fabric_of)
    o["owner"] = o["product"].map(owner)
    o["is_finished"] = o["角色"].astype(str).str.contains("成品") | o["角色"].astype(str).str.contains("皮壳")
    end = pd.Timestamp("2026-10-31")
    o["d90"] = o["sale_date"] >= end - pd.Timedelta(days=90)
    o["d180"] = o["sale_date"] >= end - pd.Timedelta(days=180)
    o["y2026"] = o["sale_date"].dt.year == 2026

    def agg(mask_col: str) -> pd.DataFrame:
        s = o[o[mask_col]]
        return (s.groupby(["family", "fabric"])["qty"]
                .agg(["sum", "count"]).reset_index()
                .rename(columns={"sum": f"qty_{mask_col}", "count": f"lines_{mask_col}"}))

    out = agg("y2026").merge(agg("d180"), on=["family", "fabric"], how="outer")
    out = out.merge(agg("d90"), on=["family", "fabric"], how="outer").fillna(0)
    out = out.rename(columns={"qty_y2026": "qty_2026", "lines_y2026": "lines_2026"})
    out["qty_d90_annualized"] = out["qty_d90"] * 4
    out["d90_vs_d180_annualized"] = (out["qty_d90_annualized"] / out["qty_d180"].replace(0, pd.NA) * 2 - 1)
    out.sort_values(["family", "qty_d90"], ascending=[True, False]).to_csv(OUT_SUM, index=False, encoding="utf-8-sig")

    # product-level
    p = (o.groupby(["product", "名称", "物料组", "角色", "family", "fabric", "owner"], dropna=False)
         .agg(qty_2026=("qty", lambda s: s[o.loc[s.index, "y2026"]].sum()),
              qty_d180=("qty", lambda s: s[o.loc[s.index, "d180"]].sum()),
              qty_d90=("qty", lambda s: s[o.loc[s.index, "d90"]].sum()),
              lines_d90=("qty", lambda s: int(o.loc[s.index, "d90"].sum())))
         .reset_index())
    # simpler recompute to avoid index confusion
    p = (o[o["d90"]].groupby(["product", "名称", "物料组", "角色", "family", "fabric", "owner"], dropna=False)
         .agg(qty_d90=("qty", "sum"), lines_d90=("qty", "size")).reset_index())
    p180 = (o[o["d180"]].groupby("product")["qty"].sum().rename("qty_d180"))
    p2026 = (o[o["y2026"]].groupby("product")["qty"].sum().rename("qty_2026"))
    p = p.merge(p180, on="product", how="left").merge(p2026, on="product", how="left")
    p["qty_d180"] = p["qty_d180"].fillna(0)
    p["qty_2026"] = p["qty_2026"].fillna(0)
    p["d90_annualized"] = p["qty_d90"] * 4
    p["trend_90_vs_180"] = p["d90_annualized"] / p["qty_d180"].replace(0, pd.NA) - 1
    p = p.merge(a[["EN物料", "当前库存", "2026销量", "近6月销量"]], left_on="product", right_on="EN物料", how="left")
    p = p.sort_values(["family", "qty_d90"], ascending=[True, False])
    p.to_csv(OUT_PROD, index=False, encoding="utf-8-sig")

    # Full category universe (A active), not just products with recent sales.
    au = a.drop_duplicates("EN物料").copy()
    au["family"] = [family_of(str(g), str(n)) for g, n in zip(au["物料组"].fillna(""), au["名称"].fillna(""))]
    au["fabric"] = au["名称"].fillna("").map(fabric_of)
    sales = {}
    for label, mask in [
        ("d90", o["d90"]), ("d180", o["d180"]), ("y2026", o["y2026"]),
        ("y2025", o["sale_date"].dt.year == 2025),
    ]:
        sales[label] = o[mask].groupby("product")["qty"].sum()
    for label, series in sales.items():
        au[f"qty_{label}"] = au["EN物料"].map(series).fillna(0)
    au["has_stock"] = pd.to_numeric(au["当前库存"], errors="coerce").fillna(0) > 0
    au["owner"] = au["EN物料"].map(owner)
    au.to_csv(BASE / "usnj_category_universe_20261103_v2.csv", index=False, encoding="utf-8-sig")

    uni = (au.groupby(["family", "fabric"])
           .agg(products=("EN物料", "nunique"),
                products_d90=("qty_d90", lambda s: (s > 0).sum()),
                products_d180=("qty_d180", lambda s: (s > 0).sum()),
                products_2026=("qty_y2026", lambda s: (s > 0).sum()),
                products_2025=("qty_y2025", lambda s: (s > 0).sum()),
                products_stock=("has_stock", "sum"),
                qty_d90=("qty_d90", "sum"),
                qty_d180=("qty_d180", "sum"))
           .reset_index())
    uni["no_90_but_2026_or_2025"] = (
        (uni["products_2026"] + uni["products_2025"]) - uni["products_d90"]
    ).clip(lower=0)
    uni.sort_values("qty_d90", ascending=False).to_csv(
        BASE / "usnj_category_universe_summary_20261103_v2.csv", index=False, encoding="utf-8-sig")

    lines = ["# USNJ 最近需求与品类/面料汇总（2026-11-03）", "",
             "- 数据：orders_unified，USNJ 仓（CENTRADE/美东-CENTRADE/北美之路-NJ02）",
             f"- 90 天窗口：{end - pd.Timedelta(days=90):%Y-%m-%d}..{end:%Y-%m-%d}",
             f"- 180 天窗口：{end - pd.Timedelta(days=180):%Y-%m-%d}..{end:%Y-%m-%d}",
             f"- 2026 窗口：2026-01-01..{end:%Y-%m-%d}", ""]
    lines += ["## 品类 × 面料（90 天）", "",
              "| 品类 | 面料 | 90天件数 | 180天件数 | 2026件数 | 90天年化 vs 180天 |",
              "|---|---|---:|---:|---:|---:|"]
    for _, r in out.sort_values("qty_d90", ascending=False).head(40).iterrows():
        trend = "" if pd.isna(r["d90_vs_d180_annualized"]) else f"{r['d90_vs_d180_annualized']*100:+.0f}%"
        lines.append(f"| {r['family']} | {r['fabric']} | {r['qty_d90']:.0f} | {r['qty_d180']:.0f} | {r['qty_2026']:.0f} | {trend} |")
    lines += ["", "## 近 90 天 USNJ 产品（前 40）", "",
              "| 产品 | 品类 | 面料 | 90天 | 180天 | 2026 | 当前owner | 库存 |",
              "|---|---|---|---:|---:|---:|---|---:|"]
    for _, r in p.head(40).iterrows():
        lines.append(f"| {r['product']} | {r['family']} | {r['fabric']} | {r['qty_d90']:.0f} | {r['qty_d180']:.0f} | {r['qty_2026']:.0f} | {r['owner']} | {r['当前库存']} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summary_rows": len(out), "products_90d": len(p), "out": [str(OUT_SUM), str(OUT_PROD), str(OUT_MD)]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
