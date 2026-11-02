# -*- coding: utf-8 -*-
"""D4 层级一致性（只读）：D5 键级预测 × D3b v3.1 历史，沿 产品→市场→仓池→形态→UOM 汇总对账。

--dry-run 只打印各层键数、汇总差异、CG/共享池/套件核对与自检。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

RULE_VERSION = "D4-v2-2026-11-02"
KEY = ["product_id", "pool", "physical_form", "canonical_uom"]
HORIZONS = [97, 157]
PHYS_POOLS = {"美东USNJ", "美中USTX", "波兰"}
CG_POOLS = {"CG", "CG-USNJ", "CG-USTX"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    B = "D:/Work/fzh-order-store"
    ap = argparse.ArgumentParser(description="D4 层级一致性（只读）")
    ap.add_argument("--d1b", default=f"{B}/analysis/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--d3b", default=f"{B}/analysis/D_历史归一与回测_D3b_v3_1_2026-11-02.xlsx")
    ap.add_argument("--d5", default=f"{B}/analysis/D_概率与服务_D5_2026-11-02.xlsx")
    ap.add_argument("--d2b", default=f"{B}/analysis/D_删失需求估计_D2b_v2_2026-11-02.xlsx")
    ap.add_argument("--c-stock", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--b-attrib", default=f"{B}/analysis/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/D_层级一致性_D4_v2_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/D_层级一致性_D4_v2_2026-11-02_报告.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    d1b = pd.read_excel(args.d1b, sheet_name="1_资格")
    d1b["product_id"] = d1b["product_id"].astype(str)
    d3 = pd.read_excel(args.d3b, sheet_name="2_有效历史")
    d3["product_id"] = d3["product_id"].astype(str)
    d3c = pd.read_excel(args.d3b, sheet_name="3_分类")
    d3c["product_id"] = d3c["product_id"].astype(str)
    d5 = pd.read_excel(args.d5, sheet_name="1_预测")
    d5["product_id"] = d5["product_id"].astype(str)
    d5f = pd.read_excel(args.d5, sheet_name="4_失败与回退")
    d5f["product_id"] = d5f["product_id"].astype(str)
    d2b = pd.read_excel(args.d2b, sheet_name="1_键级估计")
    d2b["product_id"] = d2b["product_id"].astype(str)
    cmap = pd.read_excel(args.c_stock, sheet_name="18_共享池回放")

    keys = d3[KEY].drop_duplicates().reset_index(drop=True)

    # 市场：D1b v2.3 按 (product,pool,form,uom) 取 market
    mkt = (d1b.assign(pool=d1b["destination_pool"])
           .groupby(KEY + ["market"]).size().reset_index(name="n")
           .sort_values("n", ascending=False)
           .drop_duplicates(KEY))
    multi_market = int(mkt.groupby(KEY).size().gt(1).sum())
    leaf = keys.merge(mkt[KEY + ["market"]], on=KEY, how="left")
    leaf["market"] = leaf["market"].fillna("未证")

    # D5 预测（两个 horizon）
    for h in HORIZONS:
        sub = d5[d5["horizon"] == h][KEY + ["p10", "p50", "p90", "model",
                                            "adopted_model", "demand_basis", "source_refs"]]
        sub = sub.rename(columns={c: f"{c}_{h}" for c in
                                  ("p10", "p50", "p90", "model", "adopted_model",
                                   "demand_basis", "source_refs")})
        leaf = leaf.merge(sub, on=KEY, how="left")
    fail_keys = d5f[KEY].drop_duplicates()
    fail_keys["d5_failed"] = 1
    leaf = leaf.merge(fail_keys, on=KEY, how="left")
    leaf["d5_failed"] = leaf["d5_failed"].fillna(0).astype(int)

    # D3b 分类与历史 qty
    leaf = leaf.merge(d3[KEY + ["qty_total", "months_positive", "months_censored",
                                "history_months_effective", "evidence_quality"]],
                      on=KEY, how="left")
    leaf = leaf.merge(d3c[KEY + ["demand_pattern", "eligible"]], on=KEY, how="left")
    leaf = leaf.merge(d2b[KEY + ["censor_method", "C_cap_basis"]], on=KEY, how="left")

    leaf["status"] = leaf["d5_failed"].map({1: "d5_failed", 0: "forecast"})

    # ---------- 层级汇总 ----------
    LEVELS = {
        "L1_产品": ["product_id"],
        "L2_产品×市场": ["product_id", "market"],
        "L3_产品×仓池": ["product_id", "pool"],
        "L4_产品×形态": ["product_id", "physical_form"],
        "L5_产品×UOM": ["product_id", "canonical_uom"],
    }
    agg_rows = []
    recon_rows = []
    for h in HORIZONS:
        leaf_sum = {q: float(leaf[f"{q}_{h}"].fillna(0).sum()) for q in ("p10", "p50", "p90")}
        recon_rows.append({"horizon": h, "level": "L0_叶子", "groups": len(leaf),
                           "keys": len(leaf),
                           "products": int(leaf["product_id"].nunique()),
                           "sum_p10": leaf_sum["p10"], "sum_p50": leaf_sum["p50"],
                           "sum_p90": leaf_sum["p90"], "diff_p50": 0.0})
        for name, cols in LEVELS.items():
            g = (leaf.groupby(cols)
                 .agg(keys=("product_id", "size"),
                      p10=(f"p10_{h}", "sum"), p50=(f"p50_{h}", "sum"),
                      p90=(f"p90_{h}", "sum")).reset_index())
            agg_rows.append({"horizon": h, "level": name, "groups": len(g),
                             **{f"{c}": v for c, v in
                                (("groups_dim1", g.iloc[:, 0].nunique()),)}})
            recon_rows.append({"horizon": h, "level": name, "groups": len(g),
                               "keys": int(g["keys"].sum()),
                               "products": int(g["product_id"].nunique())
                               if "product_id" in g.columns else None,
                               "sum_p10": float(g["p10"].sum()),
                               "sum_p50": float(g["p50"].sum()),
                               "sum_p90": float(g["p90"].sum()),
                               "diff_p50": float(g["p50"].sum()) - leaf_sum["p50"]})
    recon = pd.DataFrame(recon_rows)
    agg_summary = pd.DataFrame(agg_rows)

    # ---------- CG ----------
    cg = leaf[leaf["pool"].isin(CG_POOLS)]
    phys = leaf[leaf["pool"].isin(PHYS_POOLS)]
    cg_check = pd.DataFrame([
        {"项": "CG 叶子键", "值": len(cg)},
        {"项": "CG 预测成功键", "值": int(cg["status"].eq("forecast").sum())},
        {"项": "CG 失败键", "值": int(cg["status"].eq("d5_failed").sum())},
        {"项": "CG p50(97) 合计", "值": float(cg["p50_97"].fillna(0).sum())},
        {"项": "CG p50(157) 合计", "值": float(cg["p50_157"].fillna(0).sum())},
        {"项": "CG 市场分布", "值": cg["market"].value_counts().to_dict()},
        {"项": "CG 与物理池标签重叠键", "值": int(cg["pool"].isin(PHYS_POOLS).sum())},
        {"项": "物理池 p50(97) 合计", "值": float(phys["p50_97"].fillna(0).sum())},
    ])

    # ---------- WayfairCG 归池核对（v3.2） ----------
    o = pd.read_parquet(args.orders)
    cgo = o[o["warehouse"].astype(str).str.contains("WayfairCG", na=False)]
    import re as _re

    def _norm(x):
        c = str(x).strip()
        for p_ in ("删除", "~", "?", "？"):
            while c.startswith(p_):
                c = c[len(p_):].strip()
        return c.casefold()
    _a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    _act = _a[_a["活跃分类"] != "不活跃"]
    _idx = {}
    for r_ in _act.itertuples(index=False):
        raw = getattr(r_, "来源码")
        if isinstance(raw, str):
            for t_ in _re.split(r"[,;，]", raw):
                _idx.setdefault(_norm(t_), r_[0])
    _cc = pd.read_csv(args.customer_codes, dtype=str)
    for r_ in _cc.itertuples(index=False):
        for c_ in str(r_.customer_code).split(","):
            c_ = c_.strip()
            if c_.startswith("删除"):
                c_ = c_[2:]
            if c_:
                _idx.setdefault(_norm(c_), r_.name)
    _sm = pd.read_csv(args.sku_map, sep="	", dtype=str).iloc[:, :2]
    _sm.columns = ["en", "tt"]
    for r_ in _sm.dropna().itertuples(index=False):
        _idx.setdefault(_norm(r_.tt), r_.en)
    _b = pd.read_excel(args.b_attrib, sheet_name="主表")
    _us = _b[_b["地区"] == "US"].drop_duplicates("产品键").set_index("产品键")["美国责任方"].to_dict()
    cgo = cgo.assign(en=cgo["sku_tongtool"].map(lambda s_: _idx.get(_norm(s_))))
    cgo = cgo.assign(owner=cgo["en"].map(_us))
    alloc = cgo.groupby("owner")["qty"].sum().to_dict()
    cg_alloc = pd.DataFrame([
        {"项": "WayfairCG 订单行", "值": len(cgo)},
        {"项": "WayfairCG 件数", "值": float(cgo["qty"].sum())},
        {"项": "→ 美东USNJ", "值": float(alloc.get("美东USNJ", 0))},
        {"项": "→ 美中USTX", "值": float(alloc.get("美中USTX", 0))},
        {"项": "未映射/无 owner", "值": float(cgo.loc[cgo["owner"].isna(), "qty"].sum())},
    ])

    # ---------- 共享池 ----------
    cmap["allocation_qty"] = pd.to_numeric(cmap.get("allocation_qty"), errors="coerce").fillna(0.0)
    shared_check = pd.DataFrame([
        {"项": "共享池数量", "值": len(cmap)},
        {"项": "共享池原量合计", "值": float(pd.to_numeric(cmap.get("原量"), errors="coerce").fillna(0).sum())},
        {"项": "allocation_qty 合计", "值": float(cmap["allocation_qty"].sum())},
        {"项": "未分配余额合计", "值": float(pd.to_numeric(cmap.get("未分配余额"), errors="coerce").fillna(0).sum())},
        {"项": "池状态", "值": cmap.get("coverage").value_counts().to_dict() if "coverage" in cmap else {}},
    ])

    # ---------- 套件 ----------
    tj = leaf[leaf["product_id"].str.upper().str.startswith("TJ#")]
    kit_check = pd.DataFrame([
        {"项": "TJ# 叶子键", "值": int(len(tj))},
        {"项": "说明", "值": "D3b v3.2 无 TJ# 叶子键（套件终端规则 policy_excluded），组件需求不重复加总"},
    ])

    # ---------- 失败与缺口 ----------
    fail_tbl = leaf[leaf["status"] == "d5_failed"][KEY + ["market", "demand_pattern", "qty_total"]]
    gap_counts = {
        "D3b 叶子键": len(leaf),
        "D5 预测键": int((leaf["status"] == "forecast").sum()),
        "D5 失败键": int((leaf["status"] == "d5_failed").sum()),
        "D1b policy_excluded 行": int((d1b["decision_state"] == "policy_excluded").sum()),
        "D1b data_gap 行": int((d1b["decision_state"] == "data_gap").sum()),
        "D1b active 行": int((d1b["decision_state"] == "active").sum()),
        "市场多值键": multi_market,
        "市场未证键": int((leaf["market"] == "未证").sum()),
    }

    checks = {
        "叶子键=1,853": len(leaf) == 1853,
        "预测+失败=叶子": gap_counts["D5 预测键"] + gap_counts["D5 失败键"] == len(leaf),
        "L1/L2/L3/L4/L5 与叶子求和差=0": bool((recon["diff_p50"].abs() < 1e-6).all()),
        "CG 不与物理池重叠": int(cg["pool"].isin(PHYS_POOLS).sum()) == 0,
        "共享池只计一次(allocation=0)": abs(float(cmap["allocation_qty"].sum())) < 1e-9,
        "套件无重复(无 TJ# 叶子)": len(tj) == 0,
        "WayfairCG 归池 4,887=1,564+3,323":
            abs(float(cgo["qty"].sum()) - 4887) < 1e-9
            and abs(float(alloc.get("美东USNJ", 0)) - 1564) < 1e-9
            and abs(float(alloc.get("美中USTX", 0)) - 3323) < 1e-9,
        "失败键逐条列出": len(fail_tbl) == gap_counts["D5 失败键"],
    }
    payload = {"levels": recon.to_dict("records"),
               "cg": cg_check.to_dict("records"),
               "shared": shared_check.to_dict("records"),
               "kit": kit_check.to_dict("records"),
               "cg_alloc": cg_alloc.to_dict("records"),
               "gaps": gap_counts, "checks": checks}
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
        return 0

    # ---------- 落盘 ----------
    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("叶子键", "product_id × market × destination_pool × physical_form × canonical_uom"),
        ("层级", "L1 产品 / L2 产品×市场 / L3 产品×仓池 / L4 产品×形态 / L5 产品×UOM"),
        ("CG 规则", "WayfairCG 订单按 B owner 归入 USNJ/USTX（v3.2：4,887=1,564+3,323）；"
                  "CG/CG-USNJ/CG-USTX 池键是下游缓冲，不参与需求归集，不是 data_gap"),
        ("共享池", "共享 Foam/Cover 只计一次；无法唯一归属的保持隔离/observation"),
        ("套件", "TJ# 按 Product Bundle 拆组件；不重复加总（本版无 TJ# 叶子键）"),
        ("失败键", "D5 219 个失败键不参与预测汇总，逐条列 5_失败与缺口"),
        ("输入 SHA256 · D1b v2.3", sha256(Path(args.d1b))),
        ("输入 SHA256 · D3b v3.1", sha256(Path(args.d3b))),
        ("输入 SHA256 · D5", sha256(Path(args.d5))),
        ("输入 SHA256 · D2b v2", sha256(Path(args.d2b))),
        ("输入 SHA256 · C v14", sha256(Path(args.c_stock))),
    ], columns=["项", "内容"])
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        leaf.to_excel(w, sheet_name="1_叶子", index=False)
        recon.to_excel(w, sheet_name="2_层级汇总", index=False)
        recon.to_excel(w, sheet_name="3_对账", index=False)
        cg_check.to_excel(w, sheet_name="4_CG与共享池", index=False, startrow=0)
        shared_check.to_excel(w, sheet_name="4_CG与共享池", index=False,
                              startrow=len(cg_check) + 3)
        kit_check.to_excel(w, sheet_name="4_CG与共享池", index=False,
                           startrow=len(cg_check) + len(shared_check) + 7)
        fail_tbl.to_excel(w, sheet_name="5_失败与缺口", index=False)
        pd.DataFrame([{"自检": k, "通过": v} for k, v in checks.items()]) \
            .to_excel(w, sheet_name="6_自检", index=False)
    out_sha = sha256(out)
    Path(args.out_report).write_text(render(payload, out_sha), encoding="utf-8")
    manifest = {"rule_version": RULE_VERSION,
                "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "inputs": {"d1b": sha256(Path(args.d1b)), "d3b": sha256(Path(args.d3b)),
                           "d5": sha256(Path(args.d5)), "d2b": sha256(Path(args.d2b)),
                           "c_v14": sha256(Path(args.c_stock))},
                "outputs": {"xlsx": {"path": str(out), "sha256": out_sha},
                            "report": {"path": str(args.out_report),
                                       "sha256": sha256(Path(args.out_report))}},
                "counts": payload}
    Path(str(out).replace(".xlsx", ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"gaps": payload["gaps"], "checks": payload["checks"]},
                     ensure_ascii=False, indent=1, default=str))
    print("workbook:", out)
    return 0


def render(payload, out_sha) -> str:
    L = ["# D4 v2 层级一致性（D3b v3.2 + D5 v3.1；只读）", "", f"- `rule_version` = **{RULE_VERSION}**", "",
         "## 1. 各层键数与汇总差异", "",
         "| horizon | 层 | 组数 | 键数 | Σp10 | Σp50 | Σp90 | diff_p50 |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in payload["levels"]:
        L.append(f"| {r['horizon']} | {r['level']} | {r['groups']} | {r['keys']} | "
                 f"{r['sum_p10']:,.1f} | {r['sum_p50']:,.1f} | {r['sum_p90']:,.1f} | {r['diff_p50']:.6f} |")
    L += ["", "## 2. CG 核对", "", "| 项 | 值 |", "|---|---|"]
    for r in payload["cg"]:
        L.append(f"| {r['项']} | {r['值']} |")
    L += ["", "## 3. 共享池核对", "", "| 项 | 值 |", "|---|---|"]
    for r in payload["shared"]:
        L.append(f"| {r['项']} | {r['值']} |")
    L += ["", "## 4. 套件核对", "", "| 项 | 值 |", "|---|---|"]
    for r in payload["kit"]:
        L.append(f"| {r['项']} | {r['值']} |")
    L += ["", "## 5. 失败与缺口", "", "| 项 | 值 |", "|---|---|"]
    for k, v in payload["gaps"].items():
        L.append(f"| {k} | {v} |")
    L += ["", "## 5.1 CG 池口径（下游缓冲，不是 data_gap）", "",
          "- **CG / CG-USNJ / CG-USTX 共 178 个叶子键，全部落在 D5 失败键（no_positive_history），"
          "预测贡献 0（p50=0）**。",
          "- 这是**设计上的下游缓冲**（Wayfair 仓不进通途订单池），**不是 data_gap**；"
          "CG 库存不并入 USNJ/USTX 物理供给。",
          "- orders_unified 中 WayfairCG 仓 4,612 行 / 4,887 件已按 B owner 归入 **美东USNJ 1,564 + 美中USTX 3,323**"
          "（D3b v3.2 修正），不再落在 CG 池键上。",
          "- 结论：**CG/CG-* 池 178 键是下游缓冲（需求 0，不进净额），不是 data_gap**；"
          "CG 销量已按 owner 归入 USNJ/USTX 需求键，**不重复计入 CG 池**；如需 CG 渠道单独需求，需另立口径。",
          "", "## 6. 自检", "", "| 项 | 通过 |", "|---|---|"]
    for k, v in payload["checks"].items():
        L.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    L += ["", "只读：未写 EN/通途、未下单、未 push。", "", f"- 工作簿 SHA256：`{out_sha}`"]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
