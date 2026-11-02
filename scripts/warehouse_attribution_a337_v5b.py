# -*- coding: utf-8 -*-
"""B v5b：用**真实 DN 客户**与**gs_orders 2025 段**重跑市场级联（只读）。

与 v5 的差别
- v5 的 DN 客户是「按出库仓推定」；v5b 改用本地
  `analysis/leadtime/dn_items_with_customer_code.csv`（2025-01..2026-10，含真实 customer 字段），
  **不再走生产 REST**。
- v5 的 2025 销量取 demand 明细；v5b 改用 `gs_orders.parquet` 的 **2025 段**（通途订单原文），
  与 2026 分列。
- 级联顺序不变：2026 有量 → DN 客户 → 2025 通途订单 → 未证。

不改 v5 产物；输出独立的 v5b 工作簿。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "wh_v5", ROOT / "scripts" / "warehouse_attribution_a337_v5.py")
assert _SPEC and _SPEC.loader
_v5 = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _v5
_SPEC.loader.exec_module(_v5)

market_of_wh = _v5.market_of_wh
merge60 = _v5.merge60
MARKETS = _v5.MARKETS

CUSTOMER_TO_MARKET = {"CENTRADE": "美东", "DANEEY": "美中", "波兰公司": "波兰"}
STRIP_PREFIXES = ("删除", "~", "?", "？")


def norm(code) -> str:
    c = str(code).strip()
    changed = True
    while changed:
        changed = False
        for p in STRIP_PREFIXES:
            if c.startswith(p):
                c = c[len(p):].strip()
                changed = True
    return c.casefold()


def build_code_index(a_final: Path, customer_codes: Path, sku_map: Path) -> dict[str, str]:
    """码 → EN。优先级：A来源码 > 客户码(活跃) > sku_map > 客户码(删除)。"""
    idx: dict[str, str] = {}
    keep = []

    def add(code, en):
        n = norm(code)
        if not n or n in ("nan", "none"):
            return
        if n not in idx and n not in keep:
            idx[n] = en

    universe = pd.read_excel(a_final, sheet_name="活跃宇宙")
    active = universe[universe["活跃分类"] != "不活跃"]
    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0])

    cc = pd.read_csv(customer_codes, dtype=str)
    deleted = []
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if not c:
                continue
            (deleted.append((c[2:], r.name)) if c.startswith("删除") else add(c, r.name))

    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en)
    for c, en in deleted:
        add(c, en)
    return idx


def load_dn(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(path, dtype=str)
    d["posting_date"] = pd.to_datetime(d["posting_date"], errors="coerce")
    d["qty"] = pd.to_numeric(d["qty"], errors="coerce").fillna(0.0)
    d["market"] = d["customer"].map(CUSTOMER_TO_MARKET)
    d = d[d["market"].notna() & d["item_code"].notna()].copy()
    # 每个 EN 的最近一次 DN（同日给「美中优先」一个确定的排序位）
    pri = {"美中": 0, "美东": 1, "波兰": 2}
    d["_pri"] = d["market"].map(pri).fillna(9)
    latest = (d.sort_values(["posting_date", "_pri"]).groupby("item_code").tail(1)
              [["item_code", "posting_date", "customer", "market"]]
              .rename(columns={"item_code": "EN物料", "posting_date": "DN最后日期",
                               "customer": "DN客户", "market": "DN市场"}))
    cnt = (d.groupby("item_code").agg(DN行数=("dn", "size"), DN客户数=("customer", "nunique"))
           .reset_index().rename(columns={"item_code": "EN物料"}))
    return latest.merge(cnt, on="EN物料", how="left"), d


def load_gs_2025(path: Path, idx: dict[str, str]) -> pd.DataFrame:
    g = pd.read_parquet(path, columns=["sku_tongtool", "qty", "sale_date", "warehouse", "month"])
    g = g[g["month"].astype(str).str.startswith("2025")].copy()
    g["qty"] = pd.to_numeric(g["qty"], errors="coerce").fillna(0.0)
    g["market"] = g["warehouse"].map(market_of_wh)
    g = g[g["market"].isin(MARKETS)].copy()
    g["EN物料"] = g["sku_tongtool"].map(lambda s: idx.get(norm(s)))
    g = g[g["EN物料"].notna()]
    return (g.groupby(["EN物料", "market"])["qty"].sum().reset_index()
            .rename(columns={"qty": "q2025"}))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="仓库归属 A337 v5b（真实 DN 客户 + gs 2025）")
    B = "D:/Work/fzh-order-store"
    ap.add_argument("--v4", default=f"{B}/analysis/仓库归属_A337_v4_市场行_2026-10-29.xlsx")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--dn", default=f"{B}/analysis/leadtime/dn_items_with_customer_code.csv")
    ap.add_argument("--gs", default=f"{B}/gs_orders.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/仓库归属_A337_v5b_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/仓库归属_A337_v5b_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    rows = pd.read_excel(args.v4, sheet_name="市场行")
    rows["EN物料"] = rows["EN物料"].astype(str)

    idx = build_code_index(Path(args.a_final), Path(args.customer_codes), Path(args.sku_map))
    dn_latest, dn_all = load_dn(Path(args.dn))
    g25 = load_gs_2025(Path(args.gs), idx)

    piv = (g25.pivot_table(index="EN物料", columns="market", values="q2025", aggfunc="sum")
           .rename(columns={m: f"2025{m}" for m in MARKETS}))
    for m in MARKETS:
        if f"2025{m}" not in piv.columns:
            piv[f"2025{m}"] = 0.0
    piv = piv[[f"2025{m}" for m in MARKETS]].reset_index()
    piv["2025合计"] = piv[[f"2025{m}" for m in MARKETS]].sum(axis=1)

    rows = rows.drop(columns=[c for c in rows.columns
                              if c.startswith("2025") or c.startswith("DN")], errors="ignore")
    rows = rows.merge(piv, on="EN物料", how="left").fillna({f"2025{m}": 0.0 for m in MARKETS})
    rows = rows.merge(dn_latest, on="EN物料", how="left")
    rows["DN客户(真实)"] = rows["DN客户"].fillna("无DN")

    def cascade(r):
        if r["证据层级"] != "未证":
            return r["市场"], r["证据层级"], r.get("备注", "")
        if isinstance(r["DN市场"], str) and r["DN市场"] in MARKETS:
            return r["DN市场"], "dn", f"2026 无量，按真实 DN 客户（{r['DN客户(真实)']}）判定"
        best = max(MARKETS, key=lambda m: r.get(f"2025{m}", 0.0) or 0.0)
        if (r.get(f"2025{best}", 0.0) or 0.0) > 0:
            return best, "own2025", "2026 无量且无 DN，按 2025 通途订单判定"
        return "未证", "未证", "2026 无量、无 DN、2025 也无量"

    casc = [cascade(r) for _, r in rows.iterrows()]
    rows["市场"] = [c[0] for c in casc]
    rows["证据层级"] = [c[1] for c in casc]
    rows["备注"] = [c[2] if c[1] in ("dn", "own2025") else r["备注"]
                    for c, (_, r) in zip(casc, rows.iterrows())]

    # 补证后释放「待运营确认」：v4 里这类行的唯一待确认原因就是「无任何证据」，
    # 现在有了 DN / 2025 证据，就不该继续挂在待确认里。
    released = (rows["待运营确认"].astype(str).str.strip().isin(["是", "True", "1"]) &
                rows["证据层级"].isin(["dn", "own2025"]))
    rows.loc[released, "待运营确认"] = ""
    rows.loc[released, "备注"] = rows.loc[released, "备注"].astype(str) + "；已补证释放待确认"

    # 60cm 合并（按 归并物 × 市场，保住市场维度）
    rows["归并物"] = rows["EN物料"].map(merge60)
    num_cols = [c for c in ("90天", "180天", "2026", "2025美东", "2025美中", "2025波兰",
                            "2025合计") if c in rows.columns]
    merged = []
    for (key, mkt), g in rows.groupby(["归并物", "市场"], dropna=False):
        base = g.iloc[0].copy()
        for c in num_cols:
            base[c] = pd.to_numeric(g[c], errors="coerce").fillna(0).sum()
        base["EN物料"], base["市场"] = key, mkt
        merged.append(pd.DataFrame([base]))
    mrows = pd.concat(merged, ignore_index=True)
    members = rows.groupby("归并物")["EN物料"].apply(lambda x: sorted(set(map(str, x))))
    mm = {k: v for k, v in members.items() if len(v) > 1}
    mrows["合并成员"] = mrows["归并物"].map(lambda k: ";".join(mm[k]) if k in mm else "")

    is_dd = mrows["角色"].astype(str).str.contains("内胆") | \
        mrows["EN物料"].astype(str).str.startswith("ND#")
    dd, main_tbl = mrows[is_dd].copy(), mrows[~is_dd].copy()
    dd["处理"] = "内胆不单独补（随皮壳/成品配套），不列未证/待审"

    un = main_tbl[main_tbl["证据层级"] == "未证"].copy()
    pend = main_tbl[main_tbl["待运营确认"].astype(str).str.strip().isin(["是", "True", "1"])].copy()
    y25 = main_tbl[main_tbl["证据层级"] == "own2025"].copy()
    dnev = main_tbl[main_tbl["证据层级"] == "dn"].copy()
    multi = (main_tbl.groupby("EN物料")
             .agg(市场数=("市场", "nunique"), 市场=("市场", lambda s: ";".join(sorted(set(s)))),
                  证据层级=("证据层级", "first"), 角色=("角色", "first"), 名称=("名称", "first"))
             .reset_index())
    multi = multi[multi["市场数"] > 1]

    summary = dict(
        v4_rows=int(len(rows)), v5b_rows=int(len(mrows)),
        内胆行=int(len(dd)), 内胆EN=int(dd["EN物料"].nunique()),
        主表行=int(len(main_tbl)), 主表EN=int(main_tbl["EN物料"].nunique()),
        未证行=int(len(un)), 待确认行=int(len(pend)),
        y2025兜底行=int(len(y25)), dn补齐行=int(len(dnev)),
        六十cm合并组=int(len(mm)), 多市场EN=int(len(multi)),
        DN覆盖EN=int(rows["DN市场"].notna().sum()),
        DN覆盖行=int(rows["DN客户(真实)"].ne("无DN").sum()),
        gs2025_EN=int((piv["2025合计"] > 0).sum()),
        tier_counts=main_tbl["证据层级"].value_counts().to_dict(),
        market_counts=main_tbl["市场"].value_counts().to_dict(),
    )

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        mrows.to_excel(w, sheet_name="市场行", index=False)
        main_tbl.to_excel(w, sheet_name="主表_非内胆", index=False)
        un.to_excel(w, sheet_name="未证清单_全部", index=False)
        pend.to_excel(w, sheet_name="待确认清单_全部", index=False)
        dd.to_excel(w, sheet_name="内胆_不单独补", index=False)
        y25.to_excel(w, sheet_name="2025兜底明细", index=False)
        dnev.to_excel(w, sheet_name="DN补齐明细", index=False)
        multi.to_excel(w, sheet_name="多市场清单", index=False)
        pd.DataFrame([{"指标": k, "值": v} for k, v in summary.items() if not isinstance(v, dict)]) \
            .to_excel(w, sheet_name="汇总", index=False)
        pd.DataFrame([{"证据层级": k, "行数": v} for k, v in summary["tier_counts"].items()]) \
            .to_excel(w, sheet_name="证据层级分布", index=False)

    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    Path(args.out_report).write_text(render(summary), encoding="utf-8")
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def render(s) -> str:
    L = [
        "# 仓库归属 A337 v5b（真实 DN 客户 + gs_orders 2025）",
        "",
        "生成：`scripts/warehouse_attribution_a337_v5b.py`（**只读**，不写 EN/通途，不 push）",
        "",
        "## 1. 相对 v5 的两处数据换源",
        "",
        "| 项 | v5 | **v5b** |",
        "|---|---|---|",
        "| DN 客户 | 按出库仓推定（生产 REST 超时） | **本地 DN 明细的真实 `customer` 字段** |",
        "| 2025 销量 | demand 明细 | **`gs_orders.parquet` 2025 段（通途订单原文）** |",
        "",
        f"DN 明细覆盖 **{s['DN覆盖EN']:,}** 个 EN（2025-01..2026-10）；"
        f"gs 2025 段覆盖 **{s['gs2025_EN']:,}** 个 EN 有 2025 销量。",
        "",
        "## 2. 市场级联结果（非内胆主表）",
        "",
        "| 层级 | 行数 | 含义 |",
        "|---|---:|---|",
        f"| own90 | {s['tier_counts'].get('own90', 0)} | 自家近90天有量 |",
        f"| parent | {s['tier_counts'].get('parent', 0)} | 跟随父件市场 |",
        f"| own180 | {s['tier_counts'].get('own180', 0)} | 自家180天有量 |",
        f"| own2026 | {s['tier_counts'].get('own2026', 0)} | 2026 有量 |",
        f"| **dn** | **{s['dn补齐行']}** | 2026 无量，按真实 DN 客户定市场 |",
        f"| **own2025** | **{s['y2025兜底行']}** | 无 DN，按 gs_orders 2025 通途订单定市场 |",
        f"| 未证 | {s['未证行']} | 三条证据都没有 |",
        "",
        "## 3. 完整清单",
        "",
        "| sheet | 行数 |",
        "|---|---:|",
        f"| 未证清单_全部 | {s['未证行']} |",
        f"| 待确认清单_全部 | {s['待确认行']} |",
        f"| 内胆_不单独补 | {s['内胆行']} |",
        f"| 2025兜底明细 | {s['y2025兜底行']} |",
        f"| DN补齐明细 | {s['dn补齐行']} |",
        f"| 多市场清单 | {s['多市场EN']} |",
        "",
        "## 4. 口径",
        "",
        "- DN 市场按 `customer` 映射：CENTRADE→美东、DANEEY→美中、波兰公司→波兰；"
        "同一 EN 多次 DN 取**最近一次**，同日按**美中优先**。",
        "- 2025 销量只取 `month` 以 `2025` 开头的通途订单，**与 2026 分列不相加**。",
        "- 级联顺序：2026 有量 → DN 客户 → 2025 通途订单 → 未证；内胆不参与，60cm 同物合并。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
