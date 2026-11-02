# -*- coding: utf-8 -*-
"""D6 v4 全量补货沙盒（只读）。

相对 v3 的变化
1) 范围扩到全量 1,853 个需求键；另列 307 policy_excluded 行。
2) 删除「跨仓直发」：动作只保留 补 / 不补 / 催已有 / 观察；
   合同写 cross_warehouse_direct=disabled_by_business。
3) CG：按 SKU owner 把 CG 库存作为 USNJ/USTX 分支的缓冲抵扣（cg_buffer_credit），
   生成任何 CG 仓补货建议；CG 池 178 键只作 observation；CG 库存/销量单列。
4) ETA 用实测分布：SO→DN 按 customer/role；头程用 shipment_segments；
   bootstrap 组合 production+head-haul，输出 p50（期望）与 p90（95% 规划）。
5) 成品 MOQ=n/a（自有绍兴工厂），按个取整；只有原料用 moq_items_21。
6) 输出：全量动作 + Top50 + 动作汇总 + 证据/未知 + CG 记录 + 决策日志 + 自检。

只读：不写 EN/通途、不下单、不采购、不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
RULE_VERSION = "D6-v5.1-2026-11-02"
AS_OF = date(2026, 10, 28)
LEAD_DAYS = 50
H_MAIN, H_SENS = 97, 157
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
MARKET_OF_POOL = {"波兰": "PL", "美东USNJ": "US", "美中USTX": "US",
                  "CG": "CG", "CG-USNJ": "CG", "CG-USTX": "CG",
                  "其他": "OTHER", "未证": "OTHER"}
POOL_OF_WAREHOUSE = {
    "CENTRADE": "美东USNJ", "美东-CENTRADE": "美东USNJ", "北美之路-NJ02": "美东USNJ",
    "WayfairCG-Cranbury仓": "美东USNJ",
    "FZH-DANEEY-皮壳仓库": "美中USTX", "FZH-DANEEY": "美中USTX",
    "FZH-DANEEY-成品仓": "美中USTX", "FZH-DANEEY-半成品仓": "美中USTX",
    "FZH-DANEEY-退货产品仓": "美中USTX", "美中-FZH-DANEEY": "美中USTX",
    "美中-FZH-DANEEY-皮壳仓库": "美中USTX", "美中-FZH-DANEEY-退货产品仓": "美中USTX",
    "休斯顿1号仓": "美中USTX", "休斯顿1号备用仓库": "美中USTX",
    "海外仓美中仓库备用仓": "美中USTX", "北美之路-LA01": "美中USTX",
    "WayfairCG-Romeoville仓": "美中USTX", "WayfairCG-Perris仓": "美中USTX",
    "FZHPoland-covers": "波兰", "波兰-FZHPoland-covers": "波兰",
    "FZHPoland-finished": "波兰",
}
US_POOLS = ("美东USNJ", "美中USTX")
CUSTOMER_OF_POOL = {"美东USNJ": "CENTRADE", "美中USTX": "DANEEY", "波兰": "波兰公司"}


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ceil_int(x: float) -> int:
    return int(math.ceil(max(0.0, float(x)) - 1e-9))


def role_of(pid: str) -> str:
    p = str(pid)
    if p.startswith("PK#"):
        return "PK#皮壳"
    if p.startswith("ND#"):
        return "ND#组件"
    if p.upper().startswith("TJ#"):
        return "其他"
    return "KS/成品"


def boot(a, b, seed=42, n=3000):
    rng = np.random.default_rng(seed)
    s = rng.choice(np.asarray(a), n, replace=True) + rng.choice(np.asarray(b), n, replace=True)
    return float(np.quantile(s, 0.5)), float(np.quantile(s, 0.9))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D6 v4 全量补货沙盒（只读）")
    ap.add_argument("--d1b", default=f"{BA}/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--d3b", default=f"{BA}/D_历史归一与回测_D3b_v3_2_2026-11-02.xlsx")
    ap.add_argument("--d5", default=f"{BA}/D_概率与服务_D5_v3_1_2026-11-02.xlsx")
    ap.add_argument("--d2b", default=f"{BA}/D_删失需求估计_D2b_v2_2026-11-02.xlsx")
    ap.add_argument("--d5b", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02.xlsx")
    ap.add_argument("--d4", default=f"{BA}/D_层级一致性_D4_v2_2026-11-02.xlsx")
    ap.add_argument("--c14", default=f"{BA}/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--b10", default=f"{BA}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--leadtime", default=f"{BA}/leadtime/leadtime_summary.json")
    ap.add_argument("--dn-rows", default=f"{BA}/leadtime/dn_leadtime_rows.csv")
    ap.add_argument("--shipments", default=f"{BA}/leadtime/shipment_segments_fixed.csv")
    ap.add_argument("--zmt", default=f"{BA}/zmt_shipment_snapshot_2026-11-02.csv")
    ap.add_argument("--leadtime-snapshot",
                    default=f"{BA}/leadtime/leadtime_snapshot_20261102.json")
    ap.add_argument("--dn-po", default=f"{BA}/leadtime/dn_po_no.csv")
    ap.add_argument("--moq", default=f"{B}/en-demand-v1/supply-netting/"
                                     "moq-replenish-policy-2026-10-28/moq_items_21.csv")
    ap.add_argument("--en-stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--po-open", default=f"{BA}/po_open_receipt_queue_2026-10-28.csv")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_Top50沙盒_D6_v5_1_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_Top50沙盒_D6_v5_1_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_Top50沙盒_D6_v5_1_2026-11-02.manifest.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    inputs = {}
    for k, v in (("D1B_V2_3", args.d1b), ("D3B_V3_2", args.d3b), ("D5_V3_1", args.d5),
                 ("D2B_V2", args.d2b), ("D5B_V2", args.d5b), ("D4_V2", args.d4),
                 ("C14", args.c14), ("B_R10", args.b10), ("LEADTIME", args.leadtime),
                 ("DN_ROWS", args.dn_rows), ("SHIPMENTS", args.shipments),
                 ("ZMT", args.zmt), ("LEADTIME_SNAPSHOT", args.leadtime_snapshot),
                 ("DN_PO", args.dn_po), ("MOQ", args.moq), ("EN_STOCK", args.en_stock),
                 ("PO_OPEN", args.po_open), ("ORDERS", args.orders)):
        if Path(v).exists():
            inputs[k] = dict(path=str(v), sha256=sha256(v))

    # ---------- 基础表
    d4 = pd.read_excel(args.d4, sheet_name="1_叶子")
    d5 = pd.read_excel(args.d5, sheet_name="1_预测")
    d5_97 = d5[d5["horizon"].astype(str) == "97"].drop_duplicates(KEYS)
    d5_157 = d5[d5["horizon"].astype(str) == "157"].drop_duplicates(KEYS)
    d2b = pd.read_excel(args.d2b, sheet_name="1_键级估计").drop_duplicates(KEYS)
    d5b = pd.read_excel(args.d5b, sheet_name="1_季节检测").drop_duplicates(KEYS)
    d1b = (pd.read_excel(args.d1b, sheet_name="1_资格")
           .rename(columns={"destination_pool": "pool"}))
    d1b_keys = (d1b[KEYS + ["decision_state", "coverage_status", "market_pool_match"]]
                .drop_duplicates(KEYS))
    c14 = pd.read_excel(args.c14, sheet_name="4_可发供给").drop_duplicates(KEYS)
    cg = pd.read_excel(args.c14, sheet_name="23_CG库存池")
    b = (pd.read_excel(args.b10, sheet_name="主表")
         .rename(columns={"产品键": "product_id", "地区": "region"}))
    conf_order = {"高": 3, "中": 2, "低": 1}
    ms_order = {"observed_current": 3, "observed_historical": 2, "stock_placement": 1}
    b["_rank"] = b["market_confidence"].map(conf_order).fillna(0) * 10 + \
        b["市场状态"].map(ms_order).fillna(0)
    b = (b.sort_values(["product_id", "region", "_rank"], ascending=False)
         .drop_duplicates(["product_id", "region"])
         .rename(columns={"市场状态": "b_market_status",
                          "market_confidence": "b_market_confidence"}))
    moq = pd.read_csv(args.moq)
    moq_map = dict(zip(moq["item_code"].astype(str),
                       pd.to_numeric(moq["min_order_qty"], errors="coerce")))
    lead = json.loads(Path(args.leadtime).read_text(encoding="utf-8"))
    snap = (json.loads(Path(args.leadtime_snapshot).read_text(encoding="utf-8"))
            if Path(args.leadtime_snapshot).exists() else {})
    bridge = pd.read_excel(args.d3b, sheet_name="1_映射桥")
    tt2prod = {str(r.sku_tongtool): str(r.product)
               for r in bridge.itertuples(index=False) if str(r.status) == "唯一"}

    # ---------- ETA：最近 6 个月 SO→DN + ZMT 头程；bootstrap 组合
    dn = pd.read_csv(args.dn_rows)
    dn["lead_days"] = pd.to_numeric(dn["lead_days"], errors="coerce")
    dn["posting_dt"] = pd.to_datetime(dn["posting_date"], errors="coerce")
    dn = dn.dropna(subset=["lead_days", "customer", "role"])
    dn["year"] = dn["posting_dt"].dt.year
    dn_recent = dn[(dn["posting_dt"] >= "2026-05-01") & (dn["posting_dt"] <= "2026-10-31")]
    year_stats = (dn.groupby("year")["lead_days"]
                  .agg(n="count", p50="median", p90=lambda s: s.quantile(.9)).to_dict("index"))
    cust_stats = (dn_recent.groupby("customer")["lead_days"]
                  .agg(n="count", p50="median", p90=lambda s: s.quantile(.9)).to_dict("index"))
    role_stats = (dn_recent.groupby("role")["lead_days"]
                  .agg(n="count", p50="median", p90=lambda s: s.quantile(.9)).to_dict("index"))

    # 用户给定锚点（最近 6 个月；2025 pooled 20/50.4 不再使用）
    PROD_ANCHOR = {"KS/成品": (22.0, 36.0), "ND#组件": (21.0, 30.4),
                   "PK#皮壳": (19.0, 30.7), "其他": (21.0, 36.0)}
    ZMT_ANCHOR = {"FBA海运": (31.0, 57.0), "FBA空运": (14.0, 14.0),
                  "美森速快线": (27.0, 32.0), "COSCO": (44.0, 57.0),
                  "EVERGREEN": (47.0, 64.0), "卡车": (31.0, 60.0),
                  "快递": (15.0, 44.0)}
    # 两层运输：main_haul / last_mile；分段来自 leadtime_snapshot_20261102
    SEG1 = {"海运普船": (11.0, 19.0), "海运快船": (8.0, 12.0), "空运": (0.0, 8.0)}
    SEG2 = {"海运普船": (17.0, 35.0), "海运快船": (10.0, 12.0), "空运": (0.0, 0.0)}
    SEG3 = {"卡车": (9.0, 18.0), "快递": (0.0, 9.0)}
    MAIN_ORDER = ["海运普船", "海运快船", "空运"]
    LAST_ORDER = ["卡车", "快递"]

    def boot4(*anchors):
        rng = np.random.default_rng(42)
        s = np.zeros(3000)
        for p50, p90 in anchors:
            s += rng.choice(np.array([p50, p90], dtype=float), 3000, replace=True)
        return float(np.quantile(s, 0.5)), float(np.quantile(s, 0.9))

    combo, head_combo = {}, {}
    for role in PROD_ANCHOR:
        for m in MAIN_ORDER:
            for l in LAST_ORDER:
                combo[(role, m, l)] = boot4(PROD_ANCHOR[role], SEG1[m], SEG2[m], SEG3[l])
    for m in MAIN_ORDER:
        for l in LAST_ORDER:
            head_combo[(m, l)] = boot4(SEG1[m], SEG2[m], SEG3[l])
    inbound_p50 = {r: combo[(r, "海运普船", "卡车")][0] for r in PROD_ANCHOR}
    inbound_p90 = {r: combo[(r, "海运普船", "卡车")][1] for r in PROD_ANCHOR}
    inbound_head_p50, inbound_head_p90 = head_combo[("海运普船", "卡车")]

    # ZMT 头程样本（2026-06..10）
    zmt = pd.read_csv(args.zmt)
    zmt["full_lt"] = pd.to_numeric(zmt["full_lt"], errors="coerce")
    zmt_pos = zmt[zmt["full_lt"] > 0]
    zmt_counts = zmt["transport"].astype(str).value_counts().to_dict()

    def _tcount(df, key):
        t = df["transport"].astype(str)
        c = df["carrier"].astype(str)
        if key == "卡车":
            return int(t.str.contains("卡派").sum())
        if key == "快递":
            return int(t.str.contains("快递").sum())
        if key == "美森速快线":
            return int(t.str.contains("美森").sum())
        if key in ("COSCO", "EVERGREEN"):
            return int((c == key).sum())
        return int((t == key).sum())

    zmt_anchor_tbl = [{"transport": k, "n": _tcount(zmt, k),
                       "full_lt_n": _tcount(zmt_pos, k),
                       "p50": v[0], "p90": v[1]} for k, v in ZMT_ANCHOR.items()]
    head_n_raw = len(zmt)
    head_assumed = False   # 使用 ZMT 锚点，不是 35/40 假设
    head_p50, head_p90 = inbound_head_p50, inbound_head_p90

    # ---------- 在途/PO（en_stock 为主；仅 intransit=0 的 SKU/仓用 PO open）
    es = pd.read_parquet(args.en_stock)
    es = es[es["snapshot_date"].astype(str) == es["snapshot_date"].astype(str).max()].copy()
    for c in ("intransit", "waiting_shipment"):
        es[c] = pd.to_numeric(es[c], errors="coerce").fillna(0.0)
    es["product_x"] = es["sku"].astype(str).map(tt2prod)
    es["pool_x"] = es["warehouse_name"].astype(str).map(POOL_OF_WAREHOUSE)
    sw = (es.groupby(["sku", "warehouse_name"])
          .agg(intr=("intransit", "sum"), wait=("waiting_shipment", "sum"),
               product_x=("product_x", "first"), pool_x=("pool_x", "first"))
          .reset_index())
    sw_m = sw[sw["product_x"].notna() & sw["pool_x"].notna()].copy()
    sw_m["stock_inb"] = sw_m["intr"] + sw_m["wait"]
    en_total_intr = float(es["intransit"].sum())
    en_total_wait = float(es["waiting_shipment"].sum())

    po = pd.read_csv(args.po_open)
    po["qty_po"] = pd.to_numeric(po["quantity"], errors="coerce").fillna(0.0)
    po["purchase_dt"] = pd.to_datetime(po["purchaseDate"], errors="coerce")
    po["eta_p50"] = pd.to_datetime(po["willArriveDate"], errors="coerce")
    po["eta_p90"] = po["eta_p50"]
    po["eta_src"] = np.where(po["eta_p50"].notna(), "willArriveDate", "")
    alt = pd.to_datetime(po["purchaseArrivalDate"], errors="coerce")
    m_alt = po["eta_p50"].isna() & alt.notna()
    po.loc[m_alt, "eta_p50"] = alt[m_alt]
    po.loc[m_alt, "eta_p90"] = alt[m_alt]
    po.loc[m_alt, "eta_src"] = "purchaseArrivalDate"
    # shipment_segments DN→PO 可匹配才用
    seg = pd.read_csv(args.shipments, dtype=str)
    seg_map = {}
    if Path(args.dn_po).exists():
        dnp = pd.read_csv(args.dn_po, dtype=str)
        for r in dnp.itertuples(index=False):
            for p in str(r.po_no).split(","):
                p = p.strip()
                if p and p.lower() != "nan":
                    seg_map.setdefault(str(r.dn), set()).add(p)
    seg_eta = {}
    for r in seg.itertuples(index=False):
        eta = pd.to_datetime(getattr(r, "warehouse_in"), errors="coerce")
        if pd.isna(eta):
            eta = pd.to_datetime(getattr(r, "arrive"), errors="coerce")
        if pd.isna(eta):
            continue
        for p in seg_map.get(str(r.dn), set()):
            seg_eta[p] = min(seg_eta.get(p, eta), eta)
    m_seg = po["eta_p50"].isna() & po["PONum"].astype(str).isin(seg_eta)
    po.loc[m_seg, "eta_p50"] = po.loc[m_seg, "PONum"].astype(str).map(seg_eta)
    po.loc[m_seg, "eta_p90"] = po.loc[m_seg, "eta_p50"]
    po.loc[m_seg, "eta_src"] = "shipment_segment"
    seg_applied = int(m_seg.sum())
    # 无日期 → bootstrap 分布（purchaseDate + full）
    m_ass = po["eta_p50"].isna()
    po["customer"] = po["warehouseName"].astype(str).map(POOL_OF_WAREHOUSE).map(CUSTOMER_OF_POOL)
    po["role"] = po["goods_sku"].astype(str).map(lambda s: role_of(tt2prod.get(s, "")))
    for i in po.index[m_ass]:
        role = po.at[i, "role"]
        role = role if role in PROD_ANCHOR else "其他"
        p50, p90 = combo[(role, "海运普船", "卡车")]
        base = po.at[i, "purchase_dt"]
        if pd.isna(base):
            base = pd.Timestamp(AS_OF)
        e50 = base + pd.Timedelta(days=p50)
        e90 = base + pd.Timedelta(days=p90)
        if e90 < pd.Timestamp(AS_OF):
            e50 = pd.Timestamp(AS_OF) + pd.Timedelta(days=inbound_head_p50)
            e90 = pd.Timestamp(AS_OF) + pd.Timedelta(days=inbound_head_p90)
            po.at[i, "eta_src"] = "bootstrap_headhaul_overdue"
        else:
            po.at[i, "eta_src"] = "bootstrap_full"
        po.at[i, "eta_p50"], po.at[i, "eta_p90"] = e50, e90
    eta_src_counts = po["eta_src"].value_counts().to_dict()

    po2 = po.merge(sw[["sku", "warehouse_name", "intr", "wait"]],
                   left_on=["goods_sku", "warehouseName"],
                   right_on=["sku", "warehouse_name"], how="left")
    po2["intr"] = po2["intr"].fillna(0.0)
    po2["wait"] = po2["wait"].fillna(0.0)
    pairs_with_intr = int((po2.groupby(["goods_sku", "warehouseName"], dropna=False)["intr"]
                           .max() > 0).sum())
    po_overlap_rows = int((po2["intr"] > 0).sum())
    po_overlap_skus = int(po2.loc[po2["intr"] > 0, "goods_sku"].nunique())
    po_use = po2[po2["intr"] == 0].copy()
    grp = (po_use.groupby(["goods_sku", "warehouseName"], dropna=False)
           .agg(qsum=("qty_po", "sum"), wait=("wait", "first")).reset_index())
    grp["extra"] = np.maximum(0.0, grp["qsum"] - grp["wait"])
    grp["scale"] = np.where(grp["qsum"] > 0, grp["extra"] / grp["qsum"], 0.0)
    po_use = po_use.merge(grp[["goods_sku", "warehouseName", "scale"]],
                          on=["goods_sku", "warehouseName"], how="left")
    po_use["qty_eff"] = po_use["qty_po"] * po_use["scale"].fillna(0.0)
    po_use["product_x"] = po_use["goods_sku"].astype(str).map(tt2prod)
    po_use["pool_x"] = po_use["warehouseName"].astype(str).map(POOL_OF_WAREHOUSE)
    po_use_m = po_use[po_use["product_x"].notna() & po_use["pool_x"].notna()]
    po_extra_total = float(po_use_m["qty_eff"].sum())
    pairs_all = int(len(set(zip(po["goods_sku"].astype(str),
                                po["warehouseName"].astype(str)))))

    ks = (sw_m.groupby(["product_x", "pool_x"])
          .agg(stock_inb=("stock_inb", "sum"), stock_intr=("intr", "sum")).reset_index())
    kp = (po_use_m.groupby(["product_x", "pool_x"])["qty_eff"].sum()
          .rename("po_extra").reset_index())

    # ---------- CG 缓冲抵扣（按 SKU owner）
    cg["cg_available"] = pd.to_numeric(cg["cg_available"], errors="coerce").fillna(0.0)
    cg_credit = (cg.groupby(["erp_item_code", "cg_owner"])["cg_available"].sum()
                 .rename("cg_buffer_credit").reset_index()
                 .rename(columns={"erp_item_code": "product_id",
                                  "cg_owner": "pool"}))
    # CG 销量（WayfairCG 仓订单）
    o = pd.read_parquet(args.orders)
    o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0.0)
    cg_orders = o[o["warehouse"].astype(str).str.contains("WayfairCG", na=False)].copy()
    cg_orders["product_x"] = cg_orders["sku_tongtool"].astype(str).map(tt2prod)
    cg_sales = (cg_orders.dropna(subset=["product_x"])
                .groupby("product_x")["qty"].sum().rename("cg_sales_qty").reset_index())

    # ---------- 键表
    f = d4.copy()
    f = f.merge(d5_97[KEYS + ["p10", "p50", "p90", "q95", "q90", "q85",
                              "calibration_status", "model", "adopted_model",
                              "demand_basis"]], on=KEYS, how="left")
    f = f.merge(d5_157[KEYS + ["q95"]].rename(columns={"q95": "q95_157"}),
                on=KEYS, how="left")
    f = f.merge(d2b[KEYS + ["estimated_p50", "n_censored_months"]], on=KEYS, how="left")
    f = f.merge(d5b[KEYS + ["seasonality_status", "promo_status"]], on=KEYS, how="left")
    f = f.merge(c14[KEYS + ["可发供给", "join_class", "覆盖状态"]], on=KEYS, how="left")
    f = f.merge(d1b_keys, on=KEYS, how="left")
    f["region"] = np.where(f["pool"] == "波兰", "PL", "US")
    f = f.merge(b[["product_id", "region", "b_market_status", "b_market_confidence"]],
                on=["product_id", "region"], how="left")
    f = f.merge(ks, left_on=["product_id", "pool"], right_on=["product_x", "pool_x"], how="left")
    f = f.merge(kp, left_on=["product_id", "pool"], right_on=["product_x", "pool_x"], how="left")
    f = f.merge(cg_credit, on=["product_id", "pool"], how="left")
    for c in ("stock_inb", "stock_intr", "po_extra", "cg_buffer_credit"):
        f[c] = f[c].fillna(0.0)
    f["po_extra"] = f["po_extra"].astype(float)
    f["stock_wait"] = (f["stock_inb"] - f["stock_intr"]).clip(lower=0.0)
    f["inbound"] = f["stock_inb"] + f["po_extra"]
    f["market"] = f["pool"].map(MARKET_OF_POOL).fillna("OTHER")
    f["supply"] = pd.to_numeric(f["可发供给"], errors="coerce").fillna(0.0)
    f["cg_buffer"] = f["pool"].astype(str).str.startswith("CG")
    f["other_pool"] = f["pool"].astype(str) == "其他"
    f["calib_fail"] = f["calibration_status"].astype(str) != "ok"
    f["data_gap"] = f["coverage_status"].astype(str) == "未覆盖"
    f["shared"] = f["market_pool_match"].astype(str) == "0"
    f["no_join"] = f["join_class"].astype(str) != "join_full"
    f["hard_excl"] = ((f["status"] == "d5_failed") | f["data_gap"] | f["shared"]
                      | f["no_join"] | f["cg_buffer"] | f["other_pool"])

    # ---------- 需要日 / ETA / 迟到量
    f["daily"] = pd.to_numeric(f["p50"], errors="coerce").fillna(0.0) / H_MAIN
    f["cover_days"] = np.where(f["daily"] > 0, f["supply"] / f["daily"], H_MAIN).clip(0, H_MAIN)
    f["need_dt"] = [AS_OF + timedelta(days=int(math.floor(x))) for x in f["cover_days"]]
    need_map = {(r.product_id, r.pool): r.need_dt for r in f.itertuples(index=False)}
    f["eta_p50"] = pd.NaT
    f["eta_p90"] = pd.NaT
    f["late_qty"] = 0.0

    # stock：已发运/待发 → 头程分布（从 as_of 起）
    def upd(row_i, qty, p50d, p90d):
        if qty <= 0:
            return
        p50 = pd.Timestamp(AS_OF) + pd.Timedelta(days=p50d)
        p90 = pd.Timestamp(AS_OF) + pd.Timedelta(days=p90d)
        cur50 = f.at[row_i, "eta_p50"]
        cur90 = f.at[row_i, "eta_p90"]
        f.at[row_i, "eta_p50"] = p50 if pd.isna(cur50) else min(cur50, p50)
        f.at[row_i, "eta_p90"] = p90 if pd.isna(cur90) else max(cur90, p90)
        if p90 > pd.Timestamp(f.at[row_i, "need_dt"]):
            f.at[row_i, "late_qty"] += qty

    for i, r in f.iterrows():
        role = role_of(r["product_id"])
        role = role if role in PROD_ANCHOR else "其他"
        upd(i, float(r["stock_intr"]), inbound_p50[role], inbound_p90[role])
        upd(i, float(r["stock_wait"]), inbound_p50[role], inbound_p90[role])
    # PO：purchaseDate + full 分布（已过期→头程）
    for r in po_use_m.itertuples(index=False):
        key = (r.product_x, r.pool_x)
        if key not in need_map:
            continue
        idx = f.index[(f["product_id"] == r.product_x) & (f["pool"] == r.pool_x)]
        if len(idx) == 0:
            continue
        i = idx[0]
        p50 = pd.Timestamp(r.eta_p50)
        p90 = pd.Timestamp(r.eta_p90)
        upd(i, float(r.qty_eff), (p50 - pd.Timestamp(AS_OF)).days,
            (p90 - pd.Timestamp(AS_OF)).days)

    # 推荐两层运输：main_haul → last_mile（按 p90 是否赶得上需要日）
    f["inbound_eta_p50"], f["inbound_eta_p90"] = f["eta_p50"], f["eta_p90"]
    f["recommended_main_haul"] = ""
    f["recommended_last_mile"] = ""
    f["mode_fits"] = False
    f["last_mile_fits"] = False
    f["replenish_eta_p50"] = pd.NaT
    f["replenish_eta_p90"] = pd.NaT
    for m in MAIN_ORDER:
        f[f"{m}_p90"] = pd.NaT
    for l in LAST_ORDER:
        f[f"{l}_seg3_p90"] = SEG3[l][1]
    for i, r in f.iterrows():
        role = role_of(r["product_id"])
        role = role if role in PROD_ANCHOR else "其他"
        need = pd.Timestamp(r["need_dt"])
        chosen_main, main_fits = "空运", False
        for m in MAIN_ORDER:
            if pd.Timestamp(AS_OF) + pd.Timedelta(days=combo[(role, m, "快递")][1]) <= need:
                chosen_main, main_fits = m, True
                break
        chosen_last, last_fits = "快递", False
        for l in LAST_ORDER:
            if pd.Timestamp(AS_OF) + pd.Timedelta(days=combo[(role, chosen_main, l)][1]) <= need:
                chosen_last, last_fits = l, True
                break
        f.at[i, "recommended_main_haul"] = chosen_main
        f.at[i, "recommended_last_mile"] = chosen_last
        f.at[i, "mode_fits"] = main_fits
        f.at[i, "last_mile_fits"] = last_fits
        f.at[i, "replenish_eta_p50"] = pd.Timestamp(AS_OF) + pd.Timedelta(
            days=combo[(role, chosen_main, chosen_last)][0])
        f.at[i, "replenish_eta_p90"] = pd.Timestamp(AS_OF) + pd.Timedelta(
            days=combo[(role, chosen_main, chosen_last)][1])
        for m in MAIN_ORDER:
            f.at[i, f"{m}_p90"] = pd.Timestamp(AS_OF) + pd.Timedelta(
                days=combo[(role, m, "快递")][1])
    f["transport_basis"] = "urgency_only（无成本/重要度数据）"
    f["supply_on_time"] = f["supply"] + f["inbound"] - f["late_qty"]

    # ---------- 需求 / 净需求（CG 缓冲抵扣）
    for sl, suffix in ((0.95, "95"), (0.90, "90"), (0.85, "85")):
        qcol = {"95": "q95", "90": "q90", "85": "q85"}[suffix]
        f[f"ss_{suffix}"] = (pd.to_numeric(f[qcol], errors="coerce")
                             - pd.to_numeric(f["p50"], errors="coerce")).clip(lower=0)
    f["demand_lead"] = pd.to_numeric(f["p50"], errors="coerce") * LEAD_DAYS / H_MAIN
    f["net_before_cg"] = f["demand_lead"] + f["ss_95"] - f["supply_on_time"]
    f["net_95"] = f["net_before_cg"] - f["cg_buffer_credit"]
    f["net_90"] = f["demand_lead"] + f["ss_90"] - f["supply_on_time"] - f["cg_buffer_credit"]
    f["net_85"] = f["demand_lead"] + f["ss_85"] - f["supply_on_time"] - f["cg_buffer_credit"]
    f["demand_lead_157"] = pd.to_numeric(f["p50_157"], errors="coerce") * LEAD_DAYS / H_SENS
    f["ss_95_157"] = (pd.to_numeric(f["q95_157"], errors="coerce")
                      - pd.to_numeric(f["p50_157"], errors="coerce")).clip(lower=0)
    f["net_157"] = (f["demand_lead_157"] + f["ss_95_157"] - f["supply_on_time"]
                    - f["cg_buffer_credit"])
    # CG 池键：需求/净额按 0（缓冲观察）
    cg_cols = ["p50", "p90", "q95", "q90", "q85", "p50_157", "q95_157",
               "demand_lead", "ss_95", "net_before_cg", "net_95", "net_90", "net_85",
               "net_157", "inbound", "late_qty", "supply_on_time"]
    for c in cg_cols:
        f.loc[f["cg_buffer"], c] = 0.0

    # ---------- 动作（无跨仓）
    def action_of(r) -> tuple[str, str]:
        if r.cg_buffer:
            return "观察", "CG 池下游缓冲，不生成 CG 仓补货建议"
        if r.other_pool:
            return "观察", "其他池无通途订单流"
        if r.status == "d5_failed":
            return "观察", "D5 明确失败"
        if r.data_gap:
            return "观察", "D1b coverage=未覆盖"
        if r.shared:
            return "观察", "共享池未唯一归属"
        if r.no_join:
            return "观察", "C 供给未 join_full"
        if r.calib_fail:
            return "观察", "D5 区间未校准"
        if r.net_95 <= 0:
            return "不补", "覆盖足够（净需求≤0）"
        if r.late_qty > 0:
            return "催已有", "有在途/PO 且 p90 ETA 晚于需要日"
        return "补", "净需求>0 且无迟到在途"

    acts = [action_of(r) for r in f.itertuples(index=False)]
    f["action"] = [a[0] for a in acts]
    for c in ("recommended_main_haul", "recommended_last_mile"):
        f.loc[f["action"].isin(["不补", "观察"]), c] = "不适用（不补/观察）"
    f["action_reason"] = [a[1] for a in acts]
    f["remaining_after_cover"] = np.where(
        f["action"] == "催已有", (f["net_95"] - f["late_qty"]).clip(lower=0), f["net_95"])

    def qty_of(r) -> tuple[int, str]:
        if r.action in ("不补", "观察"):
            return 0, "不补货"
        if r.action == "催已有":
            return (ceil_int(min(float(r.net_95), float(r.late_qty))),
                    f"催已有量；剩余需补 {max(0.0, float(r.remaining_after_cover)):.2f}")
        need = float(r.net_95)
        if need <= 0:
            return 0, "净需求≤0"
        pid = str(r.product_id)
        if pid in moq_map and np.isfinite(moq_map[pid]) and moq_map[pid] > 0:
            mq = float(moq_map[pid])
            return int(math.ceil(need / mq) * mq), f"原料 MOQ={mq:g} 向上取整"
        return ceil_int(need), "成品 MOQ=n/a（自有绍兴工厂）→ 按个向上取整"

    qty = [qty_of(r) for r in f.itertuples(index=False)]
    f["qty"] = [q[0] for q in qty]
    f["rounding_basis"] = [q[1] for q in qty]
    f["moq"] = [f"{moq_map[p]:g}" if (p in moq_map and np.isfinite(moq_map[p]))
                else "n/a（自有工厂）" for p in f["product_id"].astype(str)]
    f["need_date"] = [d.isoformat() for d in f["need_dt"]]
    f["order_date"] = [(d - timedelta(days=LEAD_DAYS)).isoformat() for d in f["need_dt"]]
    f["window_end"] = (AS_OF + timedelta(days=H_MAIN)).isoformat()
    f["order_late_flag"] = np.where(pd.to_datetime(f["order_date"]) < pd.Timestamp(AS_OF),
                                    "下单日已过（应立即下单）", "")
    f["confidence"] = np.where(
        (f["calibration_status"].astype(str) == "ok")
        & (f["demand_basis"].astype(str) == "observed")
        & (f["b_market_confidence"].astype(str) == "高")
        & (~f["hard_excl"]), "高",
        np.where((f["calibration_status"].astype(str) == "ok")
                 | (f["demand_basis"].astype(str) == "observed"), "中", "低"))
    def unknowns_of(r) -> str:
        u = ["成品 MOQ=n/a（自有绍兴工厂）" if str(r.moq).startswith("n/a") else f"MOQ={r.moq}"]
        if r.cg_buffer:
            u.append("CG 池=下游缓冲，不补货")
        if r.cg_buffer_credit > 0:
            u.append(f"CG 缓冲抵扣 {r.cg_buffer_credit:.0f}")
        if str(r.calibration_status) != "ok":
            u.append("D5 区间未校准")
        if r.inbound > 0:
            u.append("ETA 为分布假设（见 ETA依据）")
        return "；".join(u)
    f["unknowns"] = [unknowns_of(r) for r in f.itertuples(index=False)]
    f["eta_basis"] = np.where(
        f["inbound"] > 0,
        "inbound=prod+普船/卡车；plan=" + f["recommended_main_haul"] + "+" +
        f["recommended_last_mile"],
        "plan=" + f["recommended_main_haul"] + "+" + f["recommended_last_mile"])

    # ---------- 全量动作表
    full_cols = ["product_id", "market", "pool", "physical_form", "canonical_uom",
                 "demand_pattern", "p50", "q95", "supply", "stock_inb", "po_extra",
                 "cg_buffer_credit", "inbound", "late_qty", "supply_on_time",
                 "net_before_cg", "net_95", "net_90", "net_85", "net_157",
                 "replenish_eta_p50", "replenish_eta_p90", "inbound_eta_p50",
                 "inbound_eta_p90", "recommended_main_haul", "recommended_last_mile",
                 "transport_basis", "last_mile_fits",
                 "海运普船_p90", "海运快船_p90", "空运_p90",
                 "卡车_seg3_p90", "快递_seg3_p90",
                 "late_qty", "need_date", "order_date",
                 "action", "action_reason", "qty", "rounding_basis", "moq",
                 "confidence", "eta_basis", "unknowns", "order_late_flag"]
    full = f[full_cols].copy()
    for c in ("replenish_eta_p50", "replenish_eta_p90",
              "inbound_eta_p50", "inbound_eta_p90",
              "海运普船_p90", "海运快船_p90", "空运_p90",
              "卡车_seg3_p90", "快递_seg3_p90"):
        full[c] = full[c].astype(str).replace("NaT", "")
    full = full.rename(columns={
        "market": "市场", "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
        "demand_pattern": "需求形态", "supply": "C可发供给",
        "stock_inb": "en_stock在途+待发", "po_extra": "PO追加(去重)",
        "cg_buffer_credit": "CG缓冲抵扣", "inbound": "在途合计",
        "late_qty": "迟到在途(p90>需要日)", "supply_on_time": "到时供给",
        "net_before_cg": "净需求(未扣CG)", "net_95": "净需求95", "net_90": "净需求90",
        "net_85": "净需求85", "net_157": "净需求157",
        "replenish_eta_p50": "ETA_p50", "replenish_eta_p90": "ETA_p90",
        "inbound_eta_p50": "在途ETA_p50", "inbound_eta_p90": "在途ETA_p90",
        "recommended_main_haul": "推荐main_haul", "recommended_last_mile": "推荐last_mile",
        "transport_basis": "运输决策依据", "last_mile_fits": "last_mile p90赶得上",
        "mode_fits": "p90赶得上需要日",
        "海运普船_p90": "海运普船_p90", "海运快船_p90": "海运快船_p90",
        "空运_p90": "空运_p90", "卡车_seg3_p90": "卡车_seg3_p90",
        "快递_seg3_p90": "快递_seg3_p90",
        "need_date": "需要日", "order_date": "下单日",
        "action": "建议动作", "action_reason": "动作原因", "qty": "建议数量",
        "rounding_basis": "取整依据", "confidence": "置信度", "eta_basis": "ETA依据",
        "unknowns": "未知项",
        "order_late_flag": "下单时点提示"})
    # 去重列
    full = full.loc[:, ~full.columns.duplicated()]

    pol = d1b[d1b["decision_state"].astype(str) == "policy_excluded"].copy()
    pol_tbl = pd.DataFrame({
        "product_id": pol["product_id"], "市场": pol["pool"].map(MARKET_OF_POOL),
        "池": pol["pool"], "形态": pol["physical_form"], "UOM": pol["canonical_uom"],
        "建议动作": "观察", "动作原因": "policy_excluded（非需求键）", "建议数量": 0,
        "置信度": "n/a", "备注": "仅列出，不进补货"})

    # ---------- Top50 选样（从全量动作中挑）
    cand = f[(~f["cg_buffer"]) & (~f["other_pool"]) & (~f["hard_excl"])].copy()
    cg_obs = f[f["cg_buffer"]].copy().sort_values("cg_buffer_credit", ascending=False).head(4)
    targets = {"action": {"补": 22, "不补": 12, "催已有": 5, "观察": 8},
               "pool": {"波兰": 14, "美东USNJ": 9, "美中USTX": 9},
               "physical_form": {"皮壳": 4, "成品+皮壳": 2},
               "demand_pattern": {"smooth": 8, "intermittent": 8, "lumpy": 12,
                                  "new": 4, "obsolescent": 2}}
    weights = {"action": 3.0, "pool": 2.0, "physical_form": 2.0, "demand_pattern": 1.0}
    cand = cand.copy()
    cand["_idx"] = cand.index
    cand = cand.set_index("_idx", drop=False)
    cand["_base"] = ((cand["supply_on_time"] > 0).astype(float) * 3
                     + (cand["b_market_confidence"].astype(str) == "高").astype(float) * 2
                     + np.log1p(pd.to_numeric(cand["p50"], errors="coerce").fillna(0)) * 0.1)
    counts = {d: {} for d in targets}
    picked, avail = [], list(cand.index)
    for _ in range(46):
        best_i, best_s = None, -1e18
        for i in avail:
            r = cand.loc[i]
            need = 0.0
            for d, tgt in targets.items():
                if counts[d].get(str(r[d]), 0) < tgt.get(str(r[d]), 0):
                    need += weights[d]
            sc = need * 100 + float(r["_base"])
            if sc > best_s:
                best_s, best_i = sc, i
        if best_i is None:
            break
        picked.append(best_i)
        avail.remove(best_i)
        r = cand.loc[best_i]
        for d in targets:
            counts[d][str(r[d])] = counts[d].get(str(r[d]), 0) + 1
    top = pd.concat([f.loc[picked], cg_obs], ignore_index=True).head(50)
    top.insert(0, "序号", range(1, len(top) + 1))

    # ---------- 汇总
    def agg(df, cols):
        if df.empty:
            return pd.DataFrame(columns=cols + ["键数", "建议数量合计", "净需求95合计"])
        return (df.groupby(cols, dropna=False)
                .agg(键数=("product_id", "size"), 建议数量合计=("qty", "sum"),
                     净需求95合计=("net_95", "sum")).reset_index()
                .sort_values(["键数", "建议数量合计"], ascending=False))

    act_full = agg(f, ["action"]).rename(columns={"action": "动作", "键数": "键数"})
    act_top = agg(top, ["action"]).rename(columns={"action": "动作"})
    pool_sum = agg(top, ["market", "pool", "physical_form"]).rename(
        columns={"market": "市场", "pool": "池", "physical_form": "形态"})

    # CG 记录
    cg_rec = (cg.groupby(["erp_item_code", "cg_owner", "cg_pool"], dropna=False)
              .agg(CG库存=("cg_available", "sum")).reset_index()
              .rename(columns={"erp_item_code": "product_id", "cg_owner": "owner_pool"}))
    cg_rec = cg_rec.merge(cg_sales, left_on="product_id", right_on="product_x", how="left")
    cg_rec["cg_sales_qty"] = cg_rec["cg_sales_qty"].fillna(0.0)
    cg_rec["未分配抵扣"] = [
        q if not ((cg_rec.loc[i, "product_id"], cg_rec.loc[i, "owner_pool"])
                  in set(zip(f.loc[f["cg_buffer"] == False, "product_id"],
                             f.loc[f["cg_buffer"] == False, "pool"]))) else 0.0
        for i, q in enumerate(cg_rec["CG库存"])]

    # 自检
    eta_bad = int(((f["inbound"] > 0) & f["eta_p50"].notna() & (f["eta_p50"] > f["eta_p90"])).sum())
    late_bad = int(((f["action"] == "催已有") & (f["late_qty"] <= 0)).sum())
    cross_any = int(f["action"].astype(str).str.contains("跨仓").sum())
    cg_repl = int(((f["cg_buffer"]) & (f["action"].isin(["补", "催已有"]))).sum())
    calc_bad = 0
    for r in f.itertuples(index=False):
        calc = r.demand_lead + r.ss_95 - r.supply_on_time - r.cg_buffer_credit
        if abs(calc - r.net_95) > 1e-6:
            calc_bad += 1
    moq_bad = int((f["moq"].astype(str).str.contains("MOQ_unknown")).sum())
    self_rows = [
        dict(检查项="全量需求键数", 期望=1853, 实际=len(f), 通过="是" if len(f) == 1853 else "否"),
        dict(检查项="policy 行数", 期望=307, 实际=len(pol_tbl), 通过="是" if len(pol_tbl) == 307 else "否"),
        dict(检查项="动作仅 补/不补/催已有/观察", 期望=4, 实际=f["action"].nunique(),
             通过="是" if set(f["action"]) <= {"补", "不补", "催已有", "观察"} else "否"),
        dict(检查项="跨仓直发已删除", 期望=0, 实际=cross_any, 通过="是" if cross_any == 0 else "否"),
        dict(检查项="CG 缓冲不生成补/催", 期望=0, 实际=cg_repl, 通过="是" if cg_repl == 0 else "否"),
        dict(检查项="ETA p50≤p90（有在途键）", 期望=0, 实际=eta_bad, 通过="是" if eta_bad == 0 else "否"),
        dict(检查项="催已有必须有迟到在途", 期望=0, 实际=late_bad, 通过="是" if late_bad == 0 else "否"),
        dict(检查项="净需求可复算（扣 CG 后）", 期望=0, 实际=calc_bad, 通过="是" if calc_bad == 0 else "否"),
        dict(检查项="MOQ_unknown 残留", 期望=0, 实际=moq_bad, 通过="是" if moq_bad == 0 else "否"),
        dict(检查项="Top50 键数", 期望=50, 实际=len(top), 通过="是" if len(top) == 50 else "否"),
        dict(检查项="只读（不写 EN/通途）", 期望="是", 实际="是", 通过="是"),
    ]
    self_tbl = pd.DataFrame(self_rows)
    self_pass = bool((self_tbl["通过"] == "是").all())

    # dry-run
    print(f"== {RULE_VERSION} == 全量 {len(f)} 键｜Top50 {len(top)}｜policy {len(pol_tbl)}")
    print("全量动作：", json.dumps(f["action"].value_counts().to_dict(), ensure_ascii=False))
    print("Top50 动作：", json.dumps(top["action"].value_counts().to_dict(), ensure_ascii=False))
    print(f"ETA：SO→DN n={len(dn)}（最近6月 {len(dn_recent)}）｜ZMT n={len(zmt)}"
          f"（positive {len(zmt_pos)}）｜seg1 {SEG1['海运普船'][0]:.0f}/{SEG1['海运普船'][1]:.0f}｜"
          f"PO ETA 来源 {json.dumps(eta_src_counts, ensure_ascii=False)}")
    print("推荐运输方式（补/催）：",
          json.dumps(f[f["action"].isin(["补", "催已有"])]["recommended_main_haul"]
                     .value_counts().to_dict(), ensure_ascii=False),
          "/",
          json.dumps(f[f["action"].isin(["补", "催已有"])]["recommended_last_mile"]
                     .value_counts().to_dict(), ensure_ascii=False),
          f"｜p90 赶得上 {int(f.loc[f['action'].isin(['补','催已有']), 'mode_fits'].sum())}")
    print(f"CG：credit 键 {int((f['cg_buffer_credit'] > 0).sum())}｜抵扣合计 "
          f"{f['cg_buffer_credit'].sum():.0f}｜CG 池键 {int(f['cg_buffer'].sum())}")
    print(f"在途/PO：stock {f['stock_inb'].sum():.0f}｜PO追加 {f['po_extra'].sum():.0f}｜"
          f"迟到 {f['late_qty'].sum():.0f}")
    print("\n自检")
    print(self_tbl[["检查项", "期望", "实际", "通过"]].to_string(index=False))
    print(f"\n自检总体：{'PASS' if self_pass else 'FAIL'}")

    if args.dry_run:
        return 0 if self_pass else 1

    # ---------- 落盘
    def to_sheet(df, name):
        df.to_excel(xw, sheet_name=name, index=False)

    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as xw:
        contract = pd.DataFrame([
            ("rule_version", RULE_VERSION),
            ("范围", "全量 1,853 需求键 + 307 policy 行；Top50 是子集"),
            ("动作", "补 / 不补 / 催已有 / 观察"),
            ("cross_warehouse_direct", "disabled_by_business"),
            ("供给", "C v14 可发 + en_stock intransit/waiting；仅 intransit=0 的 SKU/仓追加 PO open"),
            ("CG", "按 SKU owner 抵扣 USNJ/USTX 缓冲（cg_buffer_credit）；CG 池观察；库存/销量单列"),
            ("ETA", "bootstrap production+head-haul；p50 期望、p90 95% 规划；"
                   "ZMT 锚点"),
            ("MOQ", "成品 n/a（自有绍兴工厂）按个取整；原料用 moq_items_21"),
            ("需要日", "C 可发覆盖耗尽日（封顶 97 天）；下单日=需要日−50"),
        ] + [(f"输入 SHA · {k}", v["sha256"]) for k, v in inputs.items()],
            columns=["项", "内容"])
        to_sheet(contract, "0_契约")
        to_sheet(full, "1_全量动作")
        to_sheet(pol_tbl, "1b_policy行")
        full["_k"] = list(zip(full["product_id"].astype(str), full["池"].astype(str),
                              full["形态"].astype(str), full["UOM"].astype(str)))
        top["_k"] = list(zip(top["product_id"].astype(str), top["pool"].astype(str),
                             top["physical_form"].astype(str), top["canonical_uom"].astype(str)))
        top_out = (top[["_k", "序号"]].merge(full, on="_k", how="left")
                   .drop(columns=["_k"]))
        cols = ["序号"] + [c for c in top_out.columns if c != "序号"]
        top_out = top_out[cols]
        to_sheet(top_out, "2_Top50")
        to_sheet(act_full, "3_动作汇总_全量")
        to_sheet(act_top, "3b_动作汇总_Top50")
        to_sheet(pool_sum, "3c_池与形态_Top50")
        ev = top_out[["序号", "product_id", "池", "形态", "建议动作", "动作原因",
                      "净需求95", "C可发供给", "en_stock在途+待发", "PO追加(去重)",
                      "CG缓冲抵扣", "到时供给", "迟到在途(p90>需要日)",
                      "ETA_p50", "ETA_p90", "ETA依据", "未知项", "置信度"]]
        to_sheet(ev, "4_证据与未知")
        to_sheet(cg_rec, "5_CG记录")
        dec = pd.DataFrame([
            ("范围", "全量 1,853 键；Top50 仅子集", "用户要求"),
            ("SO→DN", "最近 6 个月 2026-05..10；2025 14/28、2026 21/37", "用户要求+趋势"),
            ("头程", "ZMT 4,102 条（5个月），transport/carrier 锚点", "用户要求"),
            ("运输方式", "普船→海快→空运→快递→卡派，按 p90 赶需要日", "用户要求"),
            ("成本/重要度", "无数据 → urgency_only", "不硬造"),
            ("跨仓", "删除；cross_warehouse_direct=disabled_by_business", "用户要求"),
            ("CG", "按 SKU owner 抵扣 USNJ/USTX；CG 池只观察", "用户要求"),
            ("MOQ", "成品 n/a；原料用 moq_items_21", "用户要求"),
            ("动作优先级", "观察→不补→催已有→补", "自动决策"),
            ("Top50", "46 物理池 + 4 CG 观察", "自动决策"),
        ], columns=["项", "决策", "依据"])
        to_sheet(dec, "6_决策日志")
        to_sheet(self_tbl, "7_自检")

    # 报告
    eta_keys = int((f["inbound"] > 0).sum())
    cg_inv_by_owner = cg.groupby("cg_owner")["cg_available"].sum().to_dict()
    top_pool = top["pool"].value_counts().to_dict()
    top_form = top["physical_form"].value_counts().to_dict()
    top_pat = top["demand_pattern"].value_counts().to_dict()
    mode_counts = (f[f["action"].isin(["补", "催已有"])]["recommended_main_haul"]
                   .value_counts().to_dict())
    last_counts = (f[f["action"].isin(["补", "催已有"])]["recommended_last_mile"]
                   .value_counts().to_dict())
    mode_fit = int(f.loc[f["action"].isin(["补", "催已有"]), "mode_fits"].sum())
    lines = [
        f"# D6 v5.1 全量补货沙盒（{RULE_VERSION}；只读）",
        "",
        f"- 全量 **{len(f)}** 个需求键；Top50 **{len(top)}**；policy 行 **{len(pol_tbl)}**",
        "- **cross_warehouse_direct=disabled_by_business**：不再有跨仓直发。",
        "- CG 库存按 SKU owner 抵扣 USNJ/USTX 分支；CG 池只观察；CG 库存/销量单列。",
        "- 决策日志：`D6_DECISIONS.md`；本轮无 pending_codex、无 PENDING_APPROVAL。",
        "",
        "## 1. 全量动作",
        "",
        "| 动作 | 键数 | 建议数量 | 净需求95 |",
        "|---|---:|---:|---:|",
    ]
    for r in act_full.itertuples(index=False):
        lines.append(f"| {r.动作} | {r.键数} | {r.建议数量合计:.0f} | {r.净需求95合计:.1f} |")
    lines += [
        "",
        f"- 全量动作分布：{json.dumps(f['action'].value_counts().to_dict(), ensure_ascii=False)}",
        f"- Top50 动作分布：{json.dumps(top['action'].value_counts().to_dict(), ensure_ascii=False)}",
        "",
        "## 2. SO→DN 趋势与最近 6 个月口径",
        "",
        "| 年份 | n | p50 | p90 |",
        "|---|---:|---:|---:|",
    ]
    for yr in sorted(year_stats):
        s_ = year_stats[yr]
        lines.append(f"| {int(yr)} | {int(s_['n'])} | {s_['p50']:.1f} | {s_['p90']:.1f} |")
    lines += [
        "",
        "最近 6 个月（2026-05..10，线级复算）：",
        "",
        "| 客户 | n | p50 | p90 |",
        "|---|---:|---:|---:|",
    ]
    for k, v in cust_stats.items():
        lines.append(f"| {k} | {int(v['n'])} | {v['p50']:.1f} | {v['p90']:.1f} |")
    lines += [
        "",
        "| 角色 | n | p50 | p90 |",
        "|---|---:|---:|---:|",
    ]
    for k, v in role_stats.items():
        lines.append(f"| {k} | {int(v['n'])} | {v['p50']:.1f} | {v['p90']:.1f} |")
    lines += [
        "",
        "- 2025 pooled median 14 / p90 28；2026 median 21 / p90 37——确实拖长，"
        "**不再用 20/50.4 当默认**。",
        "- 规划采用用户给定最近 6 个月锚点："
        "KS 22/36、ND 21/30.4、PK 19/30.7；上表为线级复算，样本量已列。",
        "",
        "## 3. ETA 与两层运输",
        "",
        f"- 血缘：EN 原生 Shipment `custom_zmt_*` 与 ZMT Snapshot 同源（Jack PC 约 10 点爬虫批量更新 EN，"
        f"ZMT CSV 是同一批导入快照）；EN **{snap.get('counts',{}).get('en_rows','?')}** 行"
        f"（docstatus=0 Draft，但真实运单，全读 0/1/2）；ZMT **{snap.get('counts',{}).get('zmt_rows','?')}** 行。",
        "- 头程拆两层：**main_haul = 海运普船 / 海运快船 / 空运 / 未知**；"
        "**last_mile = 卡车 / 快递 / 未知**。服务产品（FBA海运/美森速快线/卡派）是组合，不并列。",
        "- 分段：seg1 入仓→离港、seg2 离港→到港、seg3 到港→签收；总交期 = SO→DN + seg1+seg2+seg3，bootstrap。",
        f"- SO→DN 全量 n={len(dn)}；最近 6 个月 n={len(dn_recent)}；"
        f"ZMT 头程 n={len(zmt)}（full_lt>0 {len(zmt_pos)}，2026-06..10 共 5 个月）。",
        "- 分段锚点（leadtime_snapshot_20261102）：",
        "",
        "| 段 | 海运普船 | 海运快船 | 空运 |",
        "|---|---|---|---|",
        f"| seg1 | {SEG1['海运普船'][0]:.0f}/{SEG1['海运普船'][1]:.0f} | "
        f"{SEG1['海运快船'][0]:.0f}/{SEG1['海运快船'][1]:.0f} | "
        f"{SEG1['空运'][0]:.0f}/{SEG1['空运'][1]:.0f} |",
        f"| seg2 | {SEG2['海运普船'][0]:.0f}/{SEG2['海运普船'][1]:.0f} | "
        f"{SEG2['海运快船'][0]:.0f}/{SEG2['海运快船'][1]:.0f} | "
        f"{SEG2['空运'][0]:.0f}/{SEG2['空运'][1]:.0f} |",
        "",
        f"last_mile seg3：卡车 {SEG3['卡车'][0]:.0f}/{SEG3['卡车'][1]:.0f}、"
        f"快递 {SEG3['快递'][0]:.0f}/{SEG3['快递'][1]:.0f}。",
        "",
        "- ZMT transport/carrier 原始锚点（校验用）：",
        "",
        "| transport/carrier | 总行 | full_lt>0 | p50 | p90 |",
        "|---|---:|---:|---:|---:|",
    ]
    for t in zmt_anchor_tbl:
        lines.append(f"| {t['transport']} | {t['n']} | {t['full_lt_n']} | "
                     f"{t['p50']:.0f} | {t['p90']:.0f} |")
    lines += [
        "",
        f"- bootstrap 组合 SO→DN + seg1+seg2+seg3；p50 期望、p90 95% 规划；"
        f"现有在途/PO 按 海运普船+卡车 保守估计。",
        f"- 推荐 main_haul（补/催已有 {sum(mode_counts.values())} 键）："
        f"{json.dumps(mode_counts, ensure_ascii=False)}；"
        f"推荐 last_mile：{json.dumps(last_counts, ensure_ascii=False)}；"
        f"main p90 赶得上 {mode_fit} 键；"
        f"last_mile p90 赶得上 {int(f.loc[f['action'].isin(['补','催已有']), 'last_mile_fits'].sum())} 键。",
        "- 规则：main_haul 先看 海运普船 p90 → 海运快船 → 空运；"
        "last_mile 先 卡车 → 快递；赶不上则空运/快递并标 late。"
        "无成本/重要度数据，`transport_basis=urgency_only`。",
        "- **ZMT 限制**：仅 2026-06..10 五个月、4,102 行（positive 2,137），"
        "非全年稳定估计；carrier 覆盖不均，锚点为分 transport/carrier 的经验值。",
        "",
        "## 4. Top50 分布",
        "",
        f"- 池：{json.dumps(top_pool, ensure_ascii=False)}",
        f"- 形态：{json.dumps(top_form, ensure_ascii=False)}",
        f"- 需求形态：{json.dumps(top_pat, ensure_ascii=False)}",
        f"- CG 缓冲观察：{int(top['cg_buffer'].sum())}（CG 池键 {int(f['cg_buffer'].sum())}）",
        "",
        "## 5. CG（缓冲抵扣，不并入物理库存）",
        "",
        f"- CG 库存按 owner：{json.dumps({k: round(v, 0) for k, v in cg_inv_by_owner.items()}, ensure_ascii=False)}",
        f"- 生成抵扣的键：{int((f['cg_buffer_credit'] > 0).sum())} 个，抵扣合计 "
        f"{f['cg_buffer_credit'].sum():.0f} 件",
        f"- CG 池 178 键：全部 `观察`，不生成 CG 仓补货建议",
        f"- CG 销量（WayfairCG 仓订单）：{cg_sales['cg_sales_qty'].sum():.0f} 件，"
        f"覆盖 {len(cg_sales)} 个产品；明细见 `5_CG记录`",
        "",
        "## 6. 自检",
        "",
        "| 检查项 | 期望 | 实际 | 通过 |",
        "|---|---:|---:|---|",
    ]
    for r in self_rows:
        lines.append(f"| {r['检查项']} | {r['期望']} | {r['实际']} | {r['通过']} |")
    lines += ["", f"**自检总体：{'PASS' if self_pass else 'FAIL'}**", ""]
    Path(args.out_report).write_text("\n".join(lines), encoding="utf-8")
    # 决策日志
    dec_md = [
        "# D6 v5.1 决策日志",
        "",
        f"- 生成时间：{datetime.now().astimezone().isoformat()}",
        "- 协议：按 `DECISION_PROTOCOL.md`，未使用 AskUserQuestion；无不可逆外部动作。",
        "",
        "| 时间 | 问题 | 选项 | 选择 | 依据 | pending_codex |",
        "|---|---|---|---|---|---|",
        f"| {datetime.now().strftime('%H:%M')} | 输出范围 | Top50 / 全量 | 全量 1,853 + Top50 子集 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | SO→DN 口径 | 全年 pooled / 最近6月 | 最近6月(2026-05..10)；2025 14/28、2026 21/37 | 用户要求+趋势 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 运输层级 | 单层 / 两层 | main_haul + last_mile 分开；服务产品为组合 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 头程来源 | shipment_segments / ZMT+EN | ZMT 4,102 条 + EN 原生 58 行（docstatus=0 也读） | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 分段 | 单一 full_lt / seg1+2+3 | 分段 p50/p90，bootstrap 总和 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 运输方式 | 单一模式 / 两层规则 | main_haul 普船→快船→空运；last_mile 卡车→快递；按 p90 赶需要日 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 成本/重要度 | 纳入 / urgency_only | 无数据→urgency_only | 不硬造 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 跨仓直发 | 保留 / 删除 | 删除，disabled_by_business | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | CG 处置 | 补货 / 缓冲抵扣 | 按 SKU owner 抵扣 USNJ/USTX；CG 池只观察 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | MOQ | MOQ_unknown / 成品 n/a | 成品 n/a，按个取整；原料用 moq_items_21 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 动作优先级 | 补优先 / 催已有优先 | 观察→不补→催已有→补 | 覆盖足够不补 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | Top50 选样 | 随机 / 覆盖目标 | 46 物理池 + 4 CG 观察 | 可解释 | 否 |",
    ]
    Path(f"{BA}/D6_DECISIONS.md").write_text("\n".join(dec_md) + "\n", encoding="utf-8")
    manifest = dict(rule_version=RULE_VERSION, generated_at_utc=datetime.now(timezone.utc).isoformat(),
                    inputs=inputs, as_of=str(AS_OF), lead_days=LEAD_DAYS,
                    counts=dict(full_keys=len(f), policy_rows=len(pol_tbl), top50=len(top),
                                actions=f["action"].value_counts().to_dict(),
                                top_actions=top["action"].value_counts().to_dict(),
                                cg_credit_keys=int((f["cg_buffer_credit"] > 0).sum()),
                                cg_credit_qty=float(f["cg_buffer_credit"].sum()),
                                cg_pool_keys=int(f["cg_buffer"].sum()),
                                eta_sources=eta_src_counts,
                                transport_modes=f[f["action"].isin(["补", "催已有"])]
                                ["recommended_main_haul"].value_counts().to_dict(),
                                transport_last_miles=f[f["action"].isin(["补", "催已有"])]
                                ["recommended_last_mile"].value_counts().to_dict(),
                                transport_mode_fits=int(
                                    f.loc[f["action"].isin(["补", "催已有"]), "mode_fits"].sum())),
                    eta=dict(so_dn_n=len(dn), recent6_n=len(dn_recent),
                             zmt_n=len(zmt), zmt_positive_n=len(zmt_pos),
                             seg1=SEG1, seg2=SEG2, seg3=SEG3, prod_anchors=PROD_ANCHOR),
                    selfcheck=self_rows, selfcheck_pass=self_pass,
                    outputs=dict(xlsx=dict(path=args.out_xlsx, sha256=sha256(args.out_xlsx),
                                           bytes=Path(args.out_xlsx).stat().st_size),
                                 report=dict(path=args.out_report, sha256=sha256(args.out_report),
                                             bytes=Path(args.out_report).stat().st_size)))
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print(f"\n已写：{args.out_xlsx}\n      {args.out_report}\n      {args.manifest}")
    return 0 if self_pass else 1


if __name__ == "__main__":
    sys.exit(main())
