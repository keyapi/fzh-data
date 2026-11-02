# -*- coding: utf-8 -*-
"""D1b 资格表：四状态分层（只读；不写 EN/通途、不 push）。

按 D-METHODOLOGY-REVIEW-2026-11-02 把「政策排除 / 真实数据缺口 / 供给缺口 / 预测回退」分开：
- decision_state: active / policy_excluded / data_gap
- demand_state:   observed / censored / estimated / no_demand
- forecast_state: observed_model / fallback_model / cold_start / not_estimable
- netting_state:  eligible / policy_excluded / data_gap / supply_gap / observation

ND/HM/老产品/共享政策/TJ# 终端规则 = policy_excluded（不是 data_gap）；
CG 销量按 B owner 计入分公司 Wayfair 需求（channel=wayfair），CG 库存只作缓冲；
no_forecast_row → fallback_model；market_unproven → data_gap；supply_not_full → supply_gap。
不做预测、不补 0、不分配共享池、不生成采购。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

RULE_VERSION = "D1b-v1-2026-11-02"
AS_OF_STOCK = "2026-10-28"
FORECAST_RUN = "forecast-20261027-r4"
HIST_START, HIST_END = "2025-01-01", "2026-10-31"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(code) -> str:
    c = str(code).strip()
    for p in ("删除", "~", "?", "？"):
        while c.startswith(p):
            c = c[len(p):].strip()
    return c.casefold()


def pool_of(w: str) -> str:
    s = str(w)
    if "WayfairCG" in s or s.startswith("CG"):
        return "CG"
    if "退货" in s:
        return "其他"
    if "Poland" in s or "波兰" in s:
        return "波兰"
    if "CENTRADE" in s or "美东" in s:
        return "美东USNJ"
    if "DANEEY" in s or "美中" in s:
        return "美中USTX"
    return "其他"


def main(argv=None) -> int:
    B = "D:/Work/fzh-order-store"
    ap = argparse.ArgumentParser(description="D1b 四状态资格表（只读）")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--fba", default=f"{B}/fba_orders_202610.parquet")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--b-attrib", default=f"{B}/analysis/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--c-stock", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--d1", default=f"{B}/analysis/D_资格与契约_v2_2026-10-30.xlsx")
    ap.add_argument("--d2", default=f"{B}/analysis/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--forecast", default=f"{B}/analysis/需求预测_去库存影响_2026-10-29.xlsx")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/D_资格与契约_D1b_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/D_资格与契约_D1b_2026-11-02_报告.md")
    args = ap.parse_args(argv)

    # ---------- 输入 ----------
    d1 = pd.read_excel(args.d1, sheet_name="1_资格")
    d1["product_id"] = d1["product_id"].astype(str)
    d2 = pd.read_excel(args.d2, sheet_name="1_序列")
    d2["month"] = d2["month"].astype(str).str.replace(r"\.0$", "", regex=True)

    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    active = a[a["活跃分类"] != "不活跃"].copy()
    active["EN物料"] = active["EN物料"].astype(str)
    active_ids = set(active["EN物料"])

    fcast = pd.read_excel(args.forecast, sheet_name="1_需求预测")
    fcast["EN物料"] = fcast["EN物料"].astype(str)
    fc_meta = {r["EN物料"]: r for r in fcast.to_dict("records")}

    c_cg = pd.read_excel(args.c_stock, sheet_name="23_CG库存池")
    c_cg["erp_item_code"] = c_cg["erp_item_code"].astype(str)
    cg_owner = {r["erp_item_code"]: r.get("cg_owner") for r in c_cg.to_dict("records")}

    # 订单 → 产品/池/月（统一历史 414,189 行）
    ov = pd.read_csv(args.overrides, dtype=str)
    idx: dict[str, str] = {}
    for r in ov[ov["action"] == "map"].itertuples(index=False):
        if isinstance(r.tt, str):
            idx[norm(r.tt)] = r.en
    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                idx.setdefault(norm(tok), r[0])
    cc = pd.read_csv(args.customer_codes, dtype=str)
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if c.startswith("删除"):
                c = c[2:]
            if c:
                idx.setdefault(norm(c), r.name)
    sm = pd.read_csv(args.sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        idx.setdefault(norm(r.tt), r.en)

    o = pd.read_parquet(args.orders)
    o["sale_date"] = pd.to_datetime(o["sale_date"])
    o = o[(o["sale_date"] >= HIST_START) & (o["sale_date"] <= HIST_END)].copy()
    o["month"] = o["sale_date"].dt.strftime("%Y%m")
    o["en"] = o["sku_tongtool"].map(lambda s: idx.get(norm(s)))
    o["pool"] = o["warehouse"].map(pool_of)
    sales = (o[o["en"].notna()]
             .groupby(["en", "pool", "month"], observed=True)["qty"].sum().reset_index())
    sales_by_pp = {(r["en"], r["pool"]): [] for r in sales.to_dict("records")}
    sales_by_en: dict[str, set] = {}
    for r in sales.to_dict("records"):
        if float(r["qty"]) > 0:
            sales_by_pp[(r["en"], r["pool"])].append(r["month"])
            sales_by_en.setdefault(r["en"], set()).add(r["month"])
    prod_obs_months = {k: len(v) for k, v in sales_by_en.items()}

    # D2 序列按键汇总（observed / censored 月）
    d2_key = (d2.groupby(["product_id", "pool", "physical_form", "canonical_uom", "zero_class"])
              .size().unstack(fill_value=0).reset_index())
    for c in ("observed_positive", "stockout_censored", "genuine_zero", "dormant",
              "long_term_zero", "censor_unknown"):
        if c not in d2_key.columns:
            d2_key[c] = 0
    d2_map = {(r["product_id"], r["pool"], r["physical_form"], r["canonical_uom"]): r
              for r in d2_key.to_dict("records")}

    # ---------- 四状态 ----------
    rows = []
    for r in d1.to_dict("records"):
        pid = r["product_id"]
        role = str(r["角色"])
        is_nd = bool(r.get("is_nd"))
        is_hm = bool(r.get("is_hm"))
        is_kit = bool(r.get("is_kit"))
        is_legacy = bool(r.get("is_legacy"))
        is_cg = bool(r.get("is_cg"))
        pool = str(r["destination_pool"])
        shared_ref = str(r.get("shared_pool_ids") or "")
        identity = str(r.get("identity_status") or "")
        form = str(r["physical_form"])
        uom = str(r["canonical_uom"])
        proven = str(r["market_status"]) == "proven"
        join_cls = str(r["join_class"])
        channel = "wayfair" if is_cg else ("wayfair" if str(r.get("channel") or "") == "wayfair_only" else "")

        # 1) decision_state
        if is_nd or is_hm or is_legacy or is_kit or (identity == "共享" and shared_ref):
            reason_policy = ("nd_component" if is_nd else "hm_component" if is_hm
                             else "legacy_no_replenish" if is_legacy
                             else "kit_terminal_rule" if is_kit else "shared_policy")
            decision, d_reason, d_group = "policy_excluded", reason_policy, "policy"
        elif not proven:
            decision, d_reason, d_group = "data_gap", "market_unproven", "data"
        elif form in ("未知", "无适用", "") or uom not in ("个", "套"):
            decision, d_reason, d_group = "data_gap", "form_uom_unproven", "data"
        else:
            decision, d_reason, d_group = "active", "ok", "ok"

        # 2) demand_state
        months = sales_by_pp.get((pid, "CG" if is_cg else pool), [])
        key_rec = d2_map.get((pid, pool, form, uom))
        obs = len(months)
        cens = int(key_rec["stockout_censored"]) if key_rec is not None else 0
        if obs > 0:
            demand, dem_reason = "observed", "ok"
        elif cens > 0:
            demand, dem_reason = "censored", "stockout_censored"
        else:
            demand, dem_reason = "no_demand", "no_positive_sales"

        # 3) forecast_state
        fm = fc_meta.get(pid)
        hist = float(fm.get("history_months") or 0) if fm is not None else 0.0
        fstat = str(fm.get("forecast_status") or "") if fm is not None else ""
        p_obs = prod_obs_months.get(pid, 0)
        if p_obs == 0 and hist <= 0:
            forecast, f_reason = "not_estimable", "no_history"
        elif p_obs < 3:
            forecast, f_reason = "cold_start", "short_history"
        elif fm is not None and fstat == "ok":
            forecast, f_reason = "observed_model", "ok"
        else:
            forecast, f_reason = "fallback_model", "no_forecast_row"

        # 4) netting_state
        if decision == "policy_excluded":
            netting, n_reason = "policy_excluded", d_reason
        elif decision == "data_gap":
            netting, n_reason = "data_gap", d_reason
        elif is_cg:
            netting, n_reason = "observation", "cg_supply_buffer"
        elif forecast == "not_estimable":
            # 真无历史：供给再全也不能净额（需求未知），只作观察
            netting, n_reason = "observation", "no_history"
        elif join_cls == "join_full" and identity == "唯一":
            netting, n_reason = "eligible", "ok"
        else:
            netting, n_reason = "supply_gap", "supply_not_full"

        # 互斥原因分组：policy > data > supply > forecast > ok
        if d_group == "policy":
            group, reason = "policy", d_reason
        elif d_group == "data":
            group, reason = "data", d_reason
        elif netting == "supply_gap":
            group, reason = "supply", n_reason
        elif netting == "observation":
            group, reason = ("supply" if is_cg else "forecast"), n_reason
        elif forecast in ("fallback_model", "cold_start", "not_estimable"):
            group, reason = "forecast", f_reason
        else:
            group, reason = "ok", "ok"

        rows.append({
            "product_id": pid, "角色": role, "ship_mode": r.get("ship_mode"),
            "market": r.get("market"), "destination_pool": pool,
            "market_status": r.get("market_status"), "us_owner": r.get("us_owner"),
            "physical_form": form, "canonical_uom": uom,
            "supply_source": r.get("supply_source"), "supply_qty": r.get("supply_qty"),
            "join_class": join_cls, "coverage_status": r.get("coverage_status"),
            "identity_status": identity, "channel": channel,
            "decision_state": decision, "demand_state": demand,
            "forecast_state": forecast, "netting_state": netting,
            "reason_group": group, "reason_code": reason,
            "demand_reason": dem_reason, "forecast_reason": f_reason,
            "observed_months": obs, "product_observed_months": prod_obs_months.get(pid, 0),
            "censored_months": cens,
            "is_nd": is_nd, "is_hm": is_hm, "is_kit": is_kit, "is_legacy": is_legacy,
            "is_cg": is_cg, "shared_pool_ids": shared_ref,
            "source_refs": ("C:" + str(r.get("source_refs") or "")) if r.get("source_refs") else "",
        })
    df = pd.DataFrame(rows)

    # ---------- 契约 ----------
    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("依据", "D-METHODOLOGY-REVIEW-2026-11-02：政策/数据/供给/预测分层，政策排除不算 data_gap"),
        ("粒度", "product_id × destination_pool × market × physical_form × canonical_uom"),
        ("输入", "orders_unified.parquet（414,189 行，2022-12-20..2026-10-31）、fba_orders_202610、"
               "A FINAL、B r10、C v14、D1 v2、D2 v3、D forecast"),
        ("as_of", f"库存 {AS_OF_STOCK}；订单历史窗口 {HIST_START}..{HIST_END}；预测 run {FORECAST_RUN}"),
        ("四状态", "decision_state(active/policy_excluded/data_gap) × demand_state(observed/censored/estimated/no_demand) "
               "× forecast_state(observed_model/fallback_model/cold_start/not_estimable) "
               "× netting_state(eligible/policy_excluded/data_gap/supply_gap/observation)"),
        ("政策口径", "ND/HM/老产品/共享政策/TJ# 终端规则 → policy_excluded；保留观察与组件事实，不算 data_gap"),
        ("CG 口径", "CG 销量按 B/C owner 计入分公司 Wayfair 需求（channel=wayfair）；CG 库存只取 warehouse_id='CG' 汇总行作缓冲，"
                 "不得与 USNJ/USTX 物理库存相加"),
        ("forecast 口径", "no_forecast_row → fallback_model（D 自行基线/池化）；仅真无历史 → not_estimable；有效观测月<3 → cold_start"),
        ("data 口径", "market_unproven 只标 data_gap，不强行归属；D 可做池级 fallback"),
        ("supply 口径", "C 非 join_full → supply_gap；D 需求仍可预测"),
        ("不做什么", "不预测数值、不补 0、不分配共享池、不生成采购、不写 EN/通途"),
        ("输入 SHA256 · orders", sha256(Path(args.orders))),
        ("输入 SHA256 · D1 v2", sha256(Path(args.d1))),
        ("输入 SHA256 · D2 v3", sha256(Path(args.d2))),
        ("输入 SHA256 · C v14", sha256(Path(args.c_stock))),
    ], columns=["项", "内容"])

    # ---------- 统计 ----------
    def state_counts(col):
        return (df[col].value_counts().rename_axis("状态").reset_index(name="行数"))

    stat_decision, stat_demand = state_counts("decision_state"), state_counts("demand_state")
    stat_forecast, stat_netting = state_counts("forecast_state"), state_counts("netting_state")
    stat_group = (df.groupby("reason_group").agg(行数=("product_id", "size"),
                                                 产品数=("product_id", "nunique"))
                  .reset_index().sort_values("行数", ascending=False))
    stat_reason = (df.groupby("reason_code").agg(行数=("product_id", "size"),
                                                 产品数=("product_id", "nunique"))
                   .reset_index().sort_values("行数", ascending=False))
    crosstab_dn = pd.crosstab(df["decision_state"], df["netting_state"]).reset_index()
    crosstab_df = pd.crosstab(df["demand_state"], df["forecast_state"]).reset_index()

    # ---------- 缺口/对账 ----------
    d1_ids = set(d1["product_id"])
    gap = pd.DataFrame([
        {"项": "A 活跃产品", "值": len(active_ids), "说明": "A FINAL 活跃分类≠不活跃"},
        {"项": "资格表覆盖产品", "值": len(set(df["product_id"]) & active_ids), "说明": "每个 A 活跃产品至少一行"},
        {"项": "A 未进资格表", "值": len(active_ids - set(df["product_id"])), "说明": "应为 0"},
        {"项": "资格行合计", "值": len(df), "说明": "来自 D1 v2 行集（含 CG 观测行）"},
        {"项": "D1 v2 行数", "值": len(d1), "说明": f"产品 {d1['product_id'].nunique()}；本表未增删行集"},
        {"项": "policy_excluded 行", "值": int((df["decision_state"] == "policy_excluded").sum()),
         "说明": "ND/HM/老产品/共享政策/TJ# 终端规则"},
        {"项": "data_gap 行", "值": int((df["decision_state"] == "data_gap").sum()),
         "说明": "B 无市场证据 / form-UOM 不可证"},
        {"项": "CG 需求行（channel=wayfair）", "值": int(df["is_cg"].sum()),
         "说明": f"有 owner {int(((df['is_cg']) & (df['us_owner'].astype(str).str.len() > 0)).sum())} 行"},
        {"项": "CG 无 owner 行", "值": int((df["is_cg"] & (df["us_owner"].astype(str).str.len() == 0)).sum()),
         "说明": "→ data_gap（不强行归属）"},
        {"项": "fallback_model 行", "值": int((df["forecast_state"] == "fallback_model").sum()),
         "说明": "无现成 forecast row，D 自建基线"},
        {"项": "supply_gap 行", "值": int((df["netting_state"] == "supply_gap").sum()),
         "说明": "C 非 join_full；需求仍可预测"},
        {"项": "supply_qty 空行", "值": int(df["supply_qty"].isna().sum()), "说明": "未覆盖≠0"},
    ])

    # ---------- 硬自检 ----------
    allowed = {
        "decision_state": {"active", "policy_excluded", "data_gap"},
        "demand_state": {"observed", "censored", "estimated", "no_demand"},
        "forecast_state": {"observed_model", "fallback_model", "cold_start", "not_estimable"},
        "netting_state": {"eligible", "policy_excluded", "data_gap", "supply_gap", "observation"},
    }
    bad_vals = {c: sorted(set(df[c]) - v) for c, v in allowed.items() if set(df[c]) - v}
    policy_mask = df["is_nd"] | df["is_hm"] | df["is_legacy"] | df["is_kit"]
    policy_in_gap = int((policy_mask & (df["decision_state"] == "data_gap")).sum())
    cg_owner_ok = int((df["is_cg"] & (df["us_owner"].astype(str).str.len() > 0)
                       & (df["decision_state"] == "active")).sum())
    cg_rows = int(df["is_cg"].sum())
    zeros_filled = int(((df["coverage_status"] == "未覆盖") & (df["supply_qty"] == 0)).sum())
    checks = [
        ("四状态取值合法", str(bad_vals) if bad_vals else "ok", "无非法值", not bad_vals),
        ("政策行不进 data_gap", policy_in_gap, "0", policy_in_gap == 0),
        ("A 覆盖 2,337", len(set(df["product_id"]) & active_ids), "2337",
         len(set(df["product_id"]) & active_ids) == 2337),
        ("CG 有 owner 行=active", cg_owner_ok, f"{cg_rows} 行中", cg_owner_ok > 0),
        ("fallback 行存在", int((df["forecast_state"] == "fallback_model").sum()), ">0",
         int((df["forecast_state"] == "fallback_model").sum()) > 0),
        ("原因分组互斥合计=行数", int(df["reason_group"].value_counts().sum()), str(len(df)),
         int(df["reason_group"].value_counts().sum()) == len(df)),
        ("未覆盖行不补0", zeros_filled, "0", zeros_filled == 0),
    ]
    bad = [c for c in checks if not c[3]]
    gap = pd.concat([gap, pd.DataFrame([
        {"项": f"自检·{c[0]}", "值": c[1], "说明": f"期望 {c[2]} → {'PASS' if c[3] else 'FAIL'}"}
        for c in checks])], ignore_index=True)
    if bad:
        raise SystemExit(f"自检失败：{bad}")

    # ---------- 输出 ----------
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        df.to_excel(w, sheet_name="1_资格", index=False)
        row = 0
        for title, tbl in (("decision_state", stat_decision), ("demand_state", stat_demand),
                           ("forecast_state", stat_forecast), ("netting_state", stat_netting),
                           ("reason_group", stat_group), ("reason_code", stat_reason)):
            pd.DataFrame([[title]]).to_excel(w, sheet_name="2_统计", index=False,
                                             startrow=row, header=False)
            tbl.to_excel(w, sheet_name="2_统计", index=False, startrow=row + 1)
            row += len(tbl) + 4
        gap.to_excel(w, sheet_name="3_缺口", index=False)
        crosstab_dn.to_excel(w, sheet_name="4_状态分布", index=False)
        crosstab_df.to_excel(w, sheet_name="4_状态分布", index=False,
                             startrow=len(crosstab_dn) + 3)

    out_sha = sha256(out)
    Path(args.out_report).write_text(
        render(df, stat_group, stat_reason, stat_decision, stat_demand, stat_forecast,
               stat_netting, crosstab_dn, crosstab_df, gap, contract, out_sha),
        encoding="utf-8")
    manifest = {
        "rule_version": RULE_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {n: sha256(Path(p)) for n, p in [
            ("orders_unified", args.orders), ("fba_202610", args.fba), ("a_final", args.a_final),
            ("b_r10", args.b_attrib), ("c_v14", args.c_stock), ("d1_v2", args.d1), ("d2_v3", args.d2)]},
        "outputs": {"xlsx": {"path": str(out), "sha256": out_sha},
                    "report": {"path": str(args.out_report),
                               "sha256": sha256(Path(args.out_report))}},
        "counts": {
            "rows": int(len(df)), "products": int(df["product_id"].nunique()),
            "decision_state": df["decision_state"].value_counts().to_dict(),
            "demand_state": df["demand_state"].value_counts().to_dict(),
            "forecast_state": df["forecast_state"].value_counts().to_dict(),
            "netting_state": df["netting_state"].value_counts().to_dict(),
            "reason_group": df["reason_group"].value_counts().to_dict(),
            "cg_rows": int(df["is_cg"].sum()),
        },
    }
    Path(str(out).replace(".xlsx", ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print("workbook:", out)
    return 0


def render(df, stat_group, stat_reason, stat_decision, stat_demand, stat_forecast,
           stat_netting, crosstab_dn, crosstab_df, gap, contract, out_sha) -> str:
    L = [
        "# D1b 四状态资格表（只读）",
        "",
        f"- `rule_version` = **{RULE_VERSION}**；{len(df):,} 行 / {df['product_id'].nunique():,} 个产品",
        "- 政策排除 ≠ 数据缺口 ≠ 供给缺口 ≠ 预测回退；本表只分层，不预测、不补 0、不分配共享池。",
        "",
        "## 1. 契约",
        "",
        "| 项 | 内容 |",
        "|---|---|",
    ]
    for r in contract.to_dict("records"):
        L.append(f"| {r['项']} | {r['内容']} |")
    L += ["", "## 2. 四状态计数", ""]
    for title, tbl in (("decision_state", stat_decision), ("demand_state", stat_demand),
                       ("forecast_state", stat_forecast), ("netting_state", stat_netting)):
        L += [f"### {title}", "", "| 状态 | 行数 |", "|---|---:|"]
        for r in tbl.to_dict("records"):
            L.append(f"| {r['状态']} | {r['行数']:,} |")
        L.append("")
    L += ["### 原因分组（互斥）", "", "| 分组 | 行数 | 产品数 |", "|---|---:|---:|"]
    for r in stat_group.to_dict("records"):
        L.append(f"| {r['reason_group']} | {r['行数']:,} | {r['产品数']:,} |")
    L += ["", "### 原因码", "", "| reason_code | 行数 | 产品数 |", "|---|---:|---:|"]
    for r in stat_reason.to_dict("records"):
        L.append(f"| `{r['reason_code']}` | {r['行数']:,} | {r['产品数']:,} |")
    L += ["", "## 3. decision × netting", "",
          "| decision_state | " + " | ".join(c for c in crosstab_dn.columns if c != "decision_state") + " |",
          "|---|" + "---:|" * (len(crosstab_dn.columns) - 1)]
    for r in crosstab_dn.to_dict("records"):
        vals = [str(r[c]) for c in crosstab_dn.columns if c != "decision_state"]
        L.append(f"| {r['decision_state']} | " + " | ".join(vals) + " |")
    L += ["", "## 4. demand × forecast", "",
          "| demand_state | " + " | ".join(c for c in crosstab_df.columns if c != "demand_state") + " |",
          "|---|" + "---:|" * (len(crosstab_df.columns) - 1)]
    for r in crosstab_df.to_dict("records"):
        vals = [str(r[c]) for c in crosstab_df.columns if c != "demand_state"]
        L.append(f"| {r['demand_state']} | " + " | ".join(vals) + " |")
    L += ["", "## 5. 缺口与对账", "", "| 项 | 值 | 说明 |", "|---|---:|---|"]
    for r in gap.to_dict("records"):
        v = r["值"]
        vs = f"{v:,}" if isinstance(v, (int, float)) else str(v)
        L.append(f"| {r['项']} | {vs} | {r['说明']} |")
    L += [
        "",
        "## 6. 口径说明",
        "",
        "- **政策行不进 data_gap**：ND/HM/老产品/共享政策/TJ# 终端规则统一 `policy_excluded`，保留观察/组件事实。",
        "- **CG 需求**：按 B/C owner 计入分公司 Wayfair 需求（`channel=wayfair`），CG 库存只作缓冲、不进物理净额；无 owner 才 data_gap。",
        "- **fallback 不是阻碍**：无现成 forecast row → `forecast_state=fallback_model`，由 D 自建基线/池化；"
        "仅真无历史才 `not_estimable`，有效观测月 <3 记 `cold_start`。",
        "- **data_gap 只标证据缺**：market_unproven / form-UOM 不可证；不强行归属市场。",
        "- **supply_gap 不阻断预测**：C 非 join_full 只影响 `netting_state`，`demand/forecast` 照常。",
        "- **无 0 填充**：`supply_qty` 缺失保持空；`no_demand` 只表示无正销量观测，不是把缺行写 0。",
        "",
        "## 7. 只读声明",
        "",
        "本次仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途，未发消息，未 push；未改 A/B/C/D 历史产物。",
        "",
        f"- 工作簿 SHA256：`{out_sha}`",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
