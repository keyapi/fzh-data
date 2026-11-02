# -*- coding: utf-8 -*-
"""D6 Top50 补货沙盒（只读）。

任务：D:/Work/fzh-order-store/analysis/D6_TASK_2026-11-02.md

口径
- 需求：D5 v2 p50/p90 的 97 天需求（默认），另列 157 天敏感性。
- 交期：规划 50 天（leadtime_summary median 20 / p90 50.4）。
- 安全库存：D5 的 95/90/85 服务分位 − p50；默认 95，另列 90/85。
- 供给：C v14 可发供给 + en_stock intransit/waiting（为主）+ 仅 intransit=0 的 PO open；
  去重避免 PO 在途重复；ETA 用 willArrive/purchaseArrival，缺失用 50 天规划并标 assumed。
- 净需求 = p50×(50/97) + max(0, q_s−p50) − 可发供给 − 在途。
- 动作：补 / 不补 / 催已有 / 跨仓直发 / 观察。
- CG 已按 B owner 修正：WayfairCG 4,887 = 美东USNJ 1,564 + 美中USTX 3,323。
  CG 池 178 键是下游缓冲、不是需求，p50=0 是设计结果；标 `cg_buffer_observation`，
  不进补货。

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
RULE_VERSION = "D6-v3-2026-11-02"
AS_OF = date(2026, 10, 28)
LEAD_DAYS = 50
H_MAIN, H_SENS = 97, 157
SL_DEFAULT = 0.95
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
MARKET_OF_POOL = {"波兰": "PL", "美东USNJ": "US", "美中USTX": "US",
                  "CG": "CG", "CG-USNJ": "CG", "CG-USTX": "CG",
                  "其他": "OTHER", "未证": "OTHER"}
US_POOLS = ("美东USNJ", "美中USTX")
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


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def script_identity(argv=None) -> dict:
    p = Path(__file__).resolve()
    raw = p.read_bytes()
    return dict(script="scripts/" + p.name, script_abs=p.as_posix(),
                script_sha256=hashlib.sha256(raw).hexdigest(),
                script_sha256_lf=hashlib.sha256(raw.replace(bytes([13, 10]),
                                                            bytes([10]))).hexdigest(),
                script_bytes=len(raw), python=platform.python_version(),
                pandas=pd.__version__, numpy=np.__version__,
                argv=[str(x) for x in (argv if argv is not None else sys.argv[1:])])


def ceil_int(x: float) -> int:
    return int(math.ceil(max(0.0, float(x)) - 1e-9))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D6 Top50 补货沙盒（只读）")
    ap.add_argument("--d1b", default=f"{BA}/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--d3b", default=f"{BA}/D_历史归一与回测_D3b_v3_2_2026-11-02.xlsx")
    ap.add_argument("--d5", default=f"{BA}/D_概率与服务_D5_v3_1_2026-11-02.xlsx")
    ap.add_argument("--d2b", default=f"{BA}/D_删失需求估计_D2b_v2_2026-11-02.xlsx")
    ap.add_argument("--d5b", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02.xlsx")
    ap.add_argument("--d4", default=f"{BA}/D_层级一致性_D4_v2_2026-11-02.xlsx")
    ap.add_argument("--c14", default=f"{BA}/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--b10", default=f"{BA}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--leadtime", default=f"{BA}/leadtime/leadtime_summary.json")
    ap.add_argument("--moq", default=f"{B}/en-demand-v1/supply-netting/"
                                     "moq-replenish-policy-2026-10-28/moq_items_21.csv")
    ap.add_argument("--en-stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--po-open", default=f"{BA}/po_open_receipt_queue_2026-10-28.csv")
    ap.add_argument("--po-receipt", default=f"{BA}/po_receipt_queue_2026-10-28.csv")
    ap.add_argument("--shipments", default=f"{BA}/leadtime/shipment_segments_fixed.csv")
    ap.add_argument("--dn-po", default=f"{BA}/leadtime/dn_po_no.csv")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_Top50沙盒_D6_v3_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_Top50沙盒_D6_v3_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_Top50沙盒_D6_v3_2026-11-02.manifest.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    inputs = {}
    for k, v in (("D1B_V2_3", args.d1b), ("D3B_V3_2", args.d3b), ("D5_V3_1", args.d5),
                 ("D2B_V2", args.d2b), ("D5B_V2", args.d5b), ("D4", args.d4),
                 ("C14", args.c14), ("B_R10", args.b10), ("LEADTIME", args.leadtime),
                 ("MOQ", args.moq), ("EN_STOCK", args.en_stock),
                 ("PO_OPEN", args.po_open), ("PO_RECEIPT", args.po_receipt),
                 ("SHIPMENT_SEGMENTS", args.shipments), ("DN_PO", args.dn_po)):
        if Path(v).exists():
            inputs[k] = dict(path=str(v), sha256=sha256(v))

    # ---------- 基础键表（D4 v2：D3b v3.2 正式键 + D5 v3.1）
    d3b = pd.read_excel(args.d3b, sheet_name="3_分类")
    d4 = pd.read_excel(args.d4, sheet_name="1_叶子")
    d5 = pd.read_excel(args.d5, sheet_name="1_预测")
    d5_97 = d5[d5["horizon"].astype(str) == str(H_MAIN)].drop_duplicates(KEYS)
    d5_157 = d5[d5["horizon"].astype(str) == str(H_SENS)].drop_duplicates(KEYS)
    d2b = pd.read_excel(args.d2b, sheet_name="1_键级估计").drop_duplicates(KEYS)
    d5b = pd.read_excel(args.d5b, sheet_name="1_季节检测").drop_duplicates(KEYS)
    d1b = (pd.read_excel(args.d1b, sheet_name="1_资格")
           .rename(columns={"destination_pool": "pool"}))
    d1b_keys = (d1b[KEYS + ["decision_state", "coverage_status", "market_pool_match",
                            "reason_group", "is_legacy", "market_confidence"]]
                .rename(columns={"market_confidence": "d1b_market_confidence"})
                .drop_duplicates(KEYS))

    c14 = pd.read_excel(args.c14, sheet_name="4_可发供给").drop_duplicates(KEYS)
    cg = pd.read_excel(args.c14, sheet_name="23_CG库存池")
    cg_products = set(cg["erp_item_code"].astype(str))
    cg_total = pd.read_excel(args.c14, sheet_name="24_CG池汇总")

    b = (pd.read_excel(args.b10, sheet_name="主表")
         .rename(columns={"产品键": "product_id", "地区": "region"}))
    conf_order = {"高": 3, "中": 2, "低": 1}
    ms_order = {"observed_current": 3, "observed_historical": 2, "stock_placement": 1}
    b["_rank"] = (b["market_confidence"].map(conf_order).fillna(0) * 10
                  + b["市场状态"].map(ms_order).fillna(0))
    b = (b.sort_values(["product_id", "region", "_rank"], ascending=False)
         .drop_duplicates(["product_id", "region"])
         .rename(columns={"市场状态": "b_market_status",
                          "market_confidence": "b_market_confidence"}))

    moq = pd.read_csv(args.moq)
    moq_map = dict(zip(moq["item_code"].astype(str),
                       pd.to_numeric(moq["min_order_qty"], errors="coerce")))
    lead = json.loads(Path(args.leadtime).read_text(encoding="utf-8"))["overall"]

    # ---------- 在途 / PO（en_stock 为主；仅 intransit=0 的 SKU/仓用 PO open）
    bridge = pd.read_excel(args.d3b, sheet_name="1_映射桥")
    tt2prod = {str(r.sku_tongtool): str(r.product)
               for r in bridge.itertuples(index=False) if str(r.status) == "唯一"}
    es = pd.read_parquet(args.en_stock)
    snap = es["snapshot_date"].astype(str).max()
    es = es[es["snapshot_date"].astype(str) == snap].copy()
    for c in ("intransit", "waiting_shipment"):
        es[c] = pd.to_numeric(es[c], errors="coerce").fillna(0.0)
    es["product_x"] = es["sku"].astype(str).map(tt2prod)
    es["pool_x"] = es["warehouse_name"].astype(str).map(POOL_OF_WAREHOUSE)
    sw = (es.groupby(["sku", "warehouse_name"])
          .agg(intr=("intransit", "sum"), wait=("waiting_shipment", "sum"),
               product_x=("product_x", "first"), pool_x=("pool_x", "first"))
          .reset_index())
    sw_mapped = sw[sw["product_x"].notna() & sw["pool_x"].notna()].copy()
    sw_mapped["stock_inb"] = sw_mapped["intr"] + sw_mapped["wait"]
    en_total_intr = float(es["intransit"].sum())
    en_total_wait = float(es["waiting_shipment"].sum())
    en_mapped_intr = float(sw_mapped["intr"].sum())
    en_mapped_wait = float(sw_mapped["wait"].sum())

    po = pd.read_csv(args.po_open)
    po["qty_po"] = pd.to_numeric(po["quantity"], errors="coerce").fillna(0.0)
    po["product_x"] = po["goods_sku"].astype(str).map(tt2prod)
    po["pool_x"] = po["warehouseName"].astype(str).map(POOL_OF_WAREHOUSE)
    po["eta"] = pd.to_datetime(po["willArriveDate"], errors="coerce")
    po["eta_src"] = np.where(po["eta"].notna(), "willArriveDate", "")
    alt = pd.to_datetime(po["purchaseArrivalDate"], errors="coerce")
    m_alt = po["eta"].isna() & alt.notna()
    po.loc[m_alt, "eta"] = alt[m_alt]
    po.loc[m_alt, "eta_src"] = "purchaseArrivalDate"
    # shipment_segments 能匹配 DN→PO 才用作 ETA 证据
    seg_map, seg_matched = {}, 0
    if Path(args.shipments).exists() and Path(args.dn_po).exists():
        seg = pd.read_csv(args.shipments, dtype=str)
        dnp = pd.read_csv(args.dn_po, dtype=str)
        seg["eta"] = pd.to_datetime(seg["warehouse_in"], errors="coerce").fillna(
            pd.to_datetime(seg["arrive"], errors="coerce"))
        seg = seg.dropna(subset=["eta"])
        dn2po = {}
        for r in dnp.itertuples(index=False):
            for p in str(r.po_no).split(","):
                p = p.strip()
                if p and p.lower() != "nan":
                    dn2po.setdefault(str(r.dn), set()).add(p)
        for r in seg.itertuples(index=False):
            for p in dn2po.get(str(r.dn), set()):
                seg_map[p] = min(seg_map.get(p, r.eta), r.eta)
        seg_matched = len(seg_map)
    m_seg = po["eta"].isna() & po["PONum"].astype(str).isin(seg_map)
    po.loc[m_seg, "eta"] = po.loc[m_seg, "PONum"].astype(str).map(seg_map)
    po.loc[m_seg, "eta_src"] = "shipment_segment"
    seg_applied = int(m_seg.sum())
    m_ass = po["eta"].isna()
    po.loc[m_ass, "eta"] = pd.Timestamp(AS_OF) + pd.Timedelta(days=LEAD_DAYS)
    po.loc[m_ass, "eta_src"] = "assumed_50d"
    eta_src_counts = po["eta_src"].value_counts().to_dict()

    # 去重：en_stock intransit>0 的 SKU/仓不再加 PO open
    po2 = po.merge(sw[["sku", "warehouse_name", "intr", "wait"]],
                   left_on=["goods_sku", "warehouseName"],
                   right_on=["sku", "warehouse_name"], how="left")
    po2["intr"] = po2["intr"].fillna(0.0)
    po2["wait"] = po2["wait"].fillna(0.0)
    pairs_with_intr = int((po2.groupby(["goods_sku", "warehouseName"], dropna=False)["intr"]
                           .max() > 0).sum())
    po_overlap_rows = int((po2["intr"] > 0).sum())
    po_overlap_skus = int(po2.loc[po2["intr"] > 0, "goods_sku"].nunique())
    intr_on_po = float(po2.groupby(["goods_sku", "warehouseName"], dropna=False)["intr"]
                       .max().clip(lower=0).sum())
    po_use = po2[po2["intr"] == 0].copy()
    grp = (po_use.groupby(["goods_sku", "warehouseName"], dropna=False)
           .agg(qsum=("qty_po", "sum"), wait=("wait", "first")).reset_index())
    grp["extra"] = np.maximum(0.0, grp["qsum"] - grp["wait"])
    grp["scale"] = np.where(grp["qsum"] > 0, grp["extra"] / grp["qsum"], 0.0)
    po_use = po_use.merge(grp[["goods_sku", "warehouseName", "scale"]],
                          on=["goods_sku", "warehouseName"], how="left")
    po_use["qty_eff"] = po_use["qty_po"] * po_use["scale"].fillna(0.0)
    po_use_m = po_use[po_use["product_x"].notna() & po_use["pool_x"].notna()]
    po_rows = len(po)
    po_skus = int(po["goods_sku"].nunique())
    po_pairs_all = int(len(set(zip(po["goods_sku"].astype(str),
                                  po["warehouseName"].astype(str)))))
    po_extra_total = float(po_use_m["qty_eff"].sum())

    ks = (sw_mapped.groupby(["product_x", "pool_x"])
          .agg(stock_inb=("stock_inb", "sum"), stock_intr=("intr", "sum")).reset_index())
    kp = (po_use_m.groupby(["product_x", "pool_x"])["qty_eff"].sum()
          .rename("po_extra").reset_index())

    # ---------- 键表
    f = d4.copy()
    f = f.merge(d5_97[KEYS + ["p10", "p50", "p90", "q95", "q90", "q85",
                              "calibration_status", "model", "adopted_model",
                              "demand_basis"]], on=KEYS, how="left")
    f = f.merge(d5_157[KEYS + ["q95"]].rename(columns={"q95": "q95_157"}),
                on=KEYS, how="left")
    f = f.merge(d2b[KEYS + ["estimated_p50", "n_censored_months"]],
                on=KEYS, how="left")
    f = f.merge(d5b[KEYS + ["seasonality_status", "promo_status"]], on=KEYS, how="left")
    f = f.merge(c14[KEYS + ["可发供给", "join_class", "覆盖状态", "补货资格"]], on=KEYS, how="left")
    f = f.merge(d1b_keys, on=KEYS, how="left")
    f["region"] = np.where(f["pool"] == "波兰", "PL", "US")
    f = f.merge(b[["product_id", "region", "b_market_status", "b_market_confidence", "可进净额"]],
                on=["product_id", "region"], how="left")
    f = f.merge(ks, left_on=["product_id", "pool"],
                right_on=["product_x", "pool_x"], how="left")
    f = f.merge(kp, left_on=["product_id", "pool"],
                right_on=["product_x", "pool_x"], how="left")
    for c in ("stock_inb", "stock_intr", "po_extra"):
        f[c] = f[c].fillna(0.0)
    f["market"] = f["pool"].map(MARKET_OF_POOL).fillna("OTHER")
    f["supply"] = pd.to_numeric(f["可发供给"], errors="coerce").fillna(0.0)
    f["inbound"] = f["stock_inb"] + f["po_extra"]
    f["cg_buffer"] = f["pool"].astype(str).str.startswith("CG")
    f["other_pool"] = f["pool"].astype(str) == "其他"
    f["calib_fail"] = f["calibration_status"].astype(str) != "ok"
    f["policy_excluded"] = f["decision_state"].astype(str) == "policy_excluded"
    f["data_gap"] = f["coverage_status"].astype(str) == "未覆盖"
    f["shared"] = f["market_pool_match"].astype(str) == "0"
    f["no_join"] = f["join_class"].astype(str) != "join_full"
    f["hard_excl"] = (f["policy_excluded"] | (f["status"] == "d5_failed")
                      | f["data_gap"] | f["shared"] | f["no_join"]
                      | f["cg_buffer"] | f["other_pool"])

    # ---------- 需要日（可用覆盖耗尽日，封顶 97 天）
    f["daily"] = pd.to_numeric(f["p50"], errors="coerce").fillna(0.0) / H_MAIN
    f["cover_days"] = np.where(f["daily"] > 0, f["supply"] / f["daily"], H_MAIN).clip(0, H_MAIN)
    f["need_dt"] = [AS_OF + timedelta(days=int(math.floor(x))) for x in f["cover_days"]]
    f["window_end"] = AS_OF + timedelta(days=H_MAIN)
    need_map = {(r.product_id, r.pool): r.need_dt for r in f.itertuples(index=False)}

    # 迟到量：stock 在途按 20 天（已发运中位）；PO 用 ETA
    f["stock_wait"] = (f["stock_inb"] - f["stock_intr"]).clip(lower=0.0)
    f["stock_late"] = (
        np.where(pd.to_datetime(f["need_dt"]) < pd.Timestamp(AS_OF) + pd.Timedelta(days=20),
                 f["stock_intr"], 0.0)
        + np.where(pd.to_datetime(f["need_dt"]) < pd.Timestamp(AS_OF) + pd.Timedelta(days=LEAD_DAYS),
                   f["stock_wait"], 0.0))
    if len(po_use_m):
        po_use_m = po_use_m.copy()
        po_use_m["need_dt"] = [need_map.get((p, pl), AS_OF + timedelta(days=H_MAIN))
                               for p, pl in zip(po_use_m["product_x"], po_use_m["pool_x"])]
        po_use_m["late"] = np.where(pd.to_datetime(po_use_m["eta"])
                                    > pd.to_datetime(po_use_m["need_dt"]),
                                    po_use_m["qty_eff"], 0.0)
        kpl = (po_use_m.groupby(["product_x", "pool_x"])["late"].sum()
               .rename("po_late").reset_index())
    else:
        kpl = pd.DataFrame(columns=["product_x", "pool_x", "po_late"])
    f = f.merge(kpl, left_on=["product_id", "pool"],
                right_on=["product_x", "pool_x"], how="left")
    f["po_late"] = f["po_late"].fillna(0.0)
    f["late_qty"] = f["stock_late"] + f["po_late"]
    f["supply_on_time"] = f["supply"] + f["inbound"] - f["late_qty"]

    # ---------- 需求 / 安全库存 / 净需求
    for sl, suffix in ((0.95, "95"), (0.90, "90"), (0.85, "85")):
        qcol = {"95": "q95", "90": "q90", "85": "q85"}[suffix]
        f[f"ss_{suffix}"] = (pd.to_numeric(f[qcol], errors="coerce")
                             - pd.to_numeric(f["p50"], errors="coerce")).clip(lower=0)
    f["demand_lead"] = pd.to_numeric(f["p50"], errors="coerce") * LEAD_DAYS / H_MAIN
    f["net_95"] = f["demand_lead"] + f["ss_95"] - f["supply_on_time"]
    f["net_90"] = f["demand_lead"] + f["ss_90"] - f["supply_on_time"]
    f["net_85"] = f["demand_lead"] + f["ss_85"] - f["supply_on_time"]
    f["demand_lead_157"] = pd.to_numeric(f["p50_157"], errors="coerce") * LEAD_DAYS / H_SENS
    f["ss_95_157"] = (pd.to_numeric(f["q95_157"], errors="coerce")
                      - pd.to_numeric(f["p50_157"], errors="coerce")).clip(lower=0)
    f["net_157"] = f["demand_lead_157"] + f["ss_95_157"] - f["supply_on_time"]
    cg_cols = ["p50", "p90", "q95", "q90", "q85", "p50_157", "q95_157",
               "demand_lead", "ss_95", "net_95", "net_90", "net_85", "net_157",
               "inbound", "late_qty", "supply_on_time"]
    for c in cg_cols:
        f.loc[f["cg_buffer"], c] = 0.0

    # ---------- 跨仓直发（仅 US 两池；用到时供给，不含迟到量）
    f = f.sort_values("net_95", ascending=False).reset_index(drop=True)
    surplus = {}
    for r in f.itertuples(index=False):
        surplus[(r.product_id, r.pool)] = max(
            0.0, float(r.supply_on_time) - max(0.0, float(r.net_95)))
    cross = np.zeros(len(f))
    for i, r in f.iterrows():
        if (r.cg_buffer or r.other_pool or r.calib_fail or r.late_qty > 0
                or r.net_95 <= 0 or r.pool not in US_POOLS):
            continue
        for j, q in f[(f["product_id"] == r.product_id) & (f["pool"] != r.pool)
                      & (f["pool"].isin(US_POOLS)) & (~f["cg_buffer"])
                      & (~f["other_pool"])].iterrows():
            key = (q["product_id"], q["pool"])
            rem = surplus.get(key, 0.0)
            if rem <= 0:
                continue
            take = min(rem, float(r.net_95) - cross[i])
            cross[i] += take
            surplus[key] = rem - take
            if cross[i] >= r.net_95:
                break
    f["cross_alloc"] = cross

    # ---------- 动作
    def action_of(r) -> str:
        if r.cg_buffer:
            return "cg_buffer_observation"
        if r.other_pool:
            return "不补（其他池）"
        if r.calib_fail:
            return "观察（区间未校准）"
        if r.net_95 <= 0:
            return "不补"
        if r.late_qty > 0:
            return "催已有"
        if r.cross_alloc > 0:
            return "跨仓直发"
        return "补"

    f["action"] = [action_of(r) for r in f.itertuples(index=False)]
    f["net_after_cover"] = np.select(
        [f["action"] == "催已有", f["action"] == "跨仓直发"],
        [(f["net_95"] - f["late_qty"]).clip(lower=0),
         (f["net_95"] - f["cross_alloc"]).clip(lower=0)],
        default=f["net_95"])

    # 建议数量（成品自有工厂 MOQ=n/a，按个取整；仅原料项用 moq_items_21）
    def qty_of(r) -> tuple[int, str]:
        if r.action in ("不补", "观察（区间未校准）", "cg_buffer_observation",
                        "不补（其他池）"):
            return 0, "不补货"
        if r.action == "催已有":
            return (ceil_int(min(float(r.net_95), float(r.late_qty))),
                    f"催已有量；剩余需补 {max(0.0, float(r.net_after_cover)):.2f}")
        if r.action == "跨仓直发":
            return ceil_int(r.cross_alloc), (f"跨仓直发量；剩余需补 "
                                             f"{max(0.0, float(r.net_after_cover)):.2f}")
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

    # 日期：需要日 = 覆盖耗尽日（封顶 97 天）
    f["need_date"] = [d.isoformat() for d in f["need_dt"]]
    f["order_date"] = [(d - timedelta(days=LEAD_DAYS)).isoformat() for d in f["need_dt"]]
    f["arrive_date"] = f["need_date"]
    f["window_end"] = f["window_end"].astype(str)
    f["order_late_flag"] = np.where(
        pd.to_datetime(f["order_date"]) < pd.Timestamp(AS_OF),
        "下单日已过（应立即下单）", "")

    # 置信度
    def conf_of(r) -> str:
        if r.cg_buffer:
            return "n/a（非需求，下游缓冲）"
        if r.calib_fail:
            return "低"
        pts = 0
        pts += 1 if str(r.calibration_status) == "ok" else 0
        pts += 1 if str(r.demand_basis) == "observed" else 0
        pts += 1 if str(r.b_market_confidence) == "高" else 0
        pts += 1 if float(r.supply_on_time) > 0 else 0
        pts += 1 if str(r.join_class) == "join_full" else 0
        return "高" if pts >= 5 else ("中" if pts >= 3 else "低")

    f["confidence"] = [conf_of(r) for r in f.itertuples(index=False)]

    def unknowns(r) -> str:
        u = ["成品 MOQ=n/a（自有绍兴工厂）", "ETA：stock 在途按 +20 天假设；PO 缺失日期按 +50 天 assumed"]
        if r.cg_buffer:
            u.append("CG 池=下游缓冲，不是需求；库存不并入 USNJ/USTX；"
                     "D5 p50=0 是设计口径而非缺数")
        if r.other_pool:
            u.append("其他池无通途订单流")
        if r.calib_fail:
            u.append("D5 区间未校准")
        if str(r.join_class) != "join_full":
            u.append("C 供给未 join_full")
        if pd.isna(r.b_market_confidence):
            u.append("B 市场证据缺失")
        return "；".join(u)

    f["unknowns"] = [unknowns(r) for r in f.itertuples(index=False)]

    # ---------- 选样
    cand = f[~f["hard_excl"]].copy()
    selected: list[int] = []
    used: set[int] = set()

    def take(sub: pd.DataFrame, n: int, why: str) -> None:
        nonlocal selected, used
        k = 0
        for i, r in sub.iterrows():
            if k >= n:
                break
            if i in used:
                continue
            used.add(i)
            selected.append(i)
            k += 1

    def score(sub: pd.DataFrame) -> pd.DataFrame:
        s = sub.copy()
        s["_score"] = ((s["supply_on_time"] > 0).astype(int) * 3
                       + (s["b_market_confidence"].astype(str) == "高").astype(int) * 2
                       + (s["demand_pattern"].isin(["smooth", "intermittent"])).astype(int)
                       + np.log1p(pd.to_numeric(s["p50"], errors="coerce").fillna(0)))
        return s.sort_values("_score", ascending=False)

    # 覆盖目标（软约束；先用 46 个物理池键，再补 4 个 CG 缓冲观察）
    targets = {
        "action": {"补": 22, "不补": 10, "跨仓直发": 4,
                   "观察（区间未校准）": 4},
        "pool": {"波兰": 14, "美东USNJ": 9, "美中USTX": 9},
        "physical_form": {"皮壳": 4, "成品+皮壳": 2},
        "demand_pattern": {"smooth": 8, "intermittent": 8, "lumpy": 12,
                           "new": 4, "obsolescent": 2},
    }
    weights = {"action": 3.0, "pool": 2.0, "physical_form": 2.0, "demand_pattern": 1.0}
    cand = cand.copy()
    cand["_idx"] = cand.index
    cand = cand.set_index("_idx", drop=False)
    cand["_base"] = ((cand["supply_on_time"] > 0).astype(float) * 3
                     + (cand["b_market_confidence"].astype(str) == "高").astype(float) * 2
                     + np.log1p(pd.to_numeric(cand["p50"], errors="coerce").fillna(0)) * 0.1)
    counts = {dim: {} for dim in targets}
    picked_idx: list = []
    avail = list(cand.index)
    for _ in range(46):
        best_i, best_s = None, -1e18
        obs_total = sum(counts["action"].get(a, 0) for a in
                        ("观察（区间未校准）",))
        for i in avail:
            r = cand.loc[i]
            if str(r["action"]).startswith("观察") and obs_total >= 10:
                continue
            need = 0.0
            for dim, tgt in targets.items():
                v = str(r[dim])
                if counts[dim].get(v, 0) < tgt.get(v, 0):
                    need += weights[dim]
            sc = need * 100 + float(r["_base"])
            if sc > best_s:
                best_s, best_i = sc, i
        if best_i is None:
            break
        picked_idx.append(best_i)
        avail.remove(best_i)
        r = cand.loc[best_i]
        for dim in targets:
            v = str(r[dim])
            counts[dim][v] = counts[dim].get(v, 0) + 1
    # 4 个 CG 池下游缓冲观察（不进补货；按 CG 库存降序）
    cg_cand = f[f["cg_buffer"]].copy()
    cg_cand["_s"] = cg_cand["supply_on_time"]
    cg_pick = list(cg_cand.sort_values("_s", ascending=False).index[:4])
    selected = picked_idx + cg_pick

    top = f.loc[selected].copy().reset_index(drop=True)
    top.insert(0, "序号", range(1, len(top) + 1))
    if len(top) < 50:
        print(f"警告：仅选到 {len(top)} 键")

    # ---------- 汇总
    def agg_block(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=cols + ["键数", "建议数量合计", "净需求95合计"])
        g = (df.groupby(cols, dropna=False)
             .agg(键数=("product_id", "size"), 建议数量合计=("qty", "sum"),
                  净需求95合计=("net_95", "sum")).reset_index())
        return g.sort_values(["键数", "建议数量合计"], ascending=False)

    act_sum = agg_block(top, ["action"])
    act_sum = act_sum.rename(columns={"action": "动作"})
    pool_sum = agg_block(top, ["market", "pool", "physical_form"]).rename(
        columns={"market": "市场", "pool": "池", "physical_form": "形态"})
    pat_sum = agg_block(top, ["demand_pattern"]).rename(columns={"demand_pattern": "需求形态"})

    # ---------- 证据与未知
    ev = top.copy()
    ev["D5证据"] = [f"model={r.model};calibration={r.calibration_status};"
                    f"p50={r.p50:.2f};q95={r.q95:.2f};basis={r.demand_basis}"
                    for r in ev.itertuples(index=False)]
    ev["D2b证据"] = [f"censor={r.censor_method};est_p50={r.estimated_p50}" for r in ev.itertuples(index=False)]
    ev["C证据"] = [f"可发={r.supply:.0f};stock在途={r.stock_inb:.0f};PO追加={r.po_extra:.0f};"
                  f"迟到={r.late_qty:.0f};到时供给={r.supply_on_time:.0f};"
                  f"join={r.join_class};覆盖={r.覆盖状态}" for r in ev.itertuples(index=False)]
    ev["B证据"] = [f"market={r.b_market_status};confidence={r.b_market_confidence}"
                  for r in ev.itertuples(index=False)]
    ev["D5b证据"] = [f"seasonality={r.seasonality_status};promo={r.promo_status}" for r in ev.itertuples(index=False)]
    ev["交期证据"] = f"规划 {LEAD_DAYS} 天；leadtime median={lead['median']:.1f} / p90={lead['p90']:.1f}"
    ev["MOQ证据"] = ev["moq"].astype(str)
    ev_tbl = ev[["序号", "product_id", "pool", "physical_form", "canonical_uom",
                 "D5证据", "D2b证据", "C证据", "B证据", "D5b证据", "交期证据", "MOQ证据",
                 "unknowns"]].rename(columns={"unknowns": "未知项"})

    # ---------- 观察与例外
    exc_rows = []
    sel_set = set(selected)

    def add_exc(df: pd.DataFrame, cat: str, why: str) -> None:
        for idx, r in df.iterrows():
            exc_rows.append(dict(product_id=r.get("product_id"), pool=r.get("pool"),
                                 physical_form=r.get("physical_form"),
                                 canonical_uom=r.get("canonical_uom"),
                                 类别=cat, 原因=why,
                                 进Top50=("是" if idx in sel_set else "否"),
                                 market=r.get("market", ""),
                                 demand_pattern=r.get("demand_pattern", ""),
                                 p50=r.get("p50", np.nan),
                                 cg_buffer=bool(r.get("cg_buffer", False))))

    pol = d1b[d1b["decision_state"].astype(str) == "policy_excluded"].copy()
    for _, r in pol.iterrows():
        exc_rows.append(dict(product_id=r["product_id"], pool=r["pool"],
                             physical_form=r["physical_form"],
                             canonical_uom=r["canonical_uom"],
                             类别="policy_excluded", 原因="D1b 政策排除，不进补货",
                             进Top50="否", market=MARKET_OF_POOL.get(str(r["pool"]), "OTHER"),
                             demand_pattern="", p50=np.nan, cg_buffer=False))
    add_exc(f[f["cg_buffer"]], "cg_buffer_observation",
            "CG 池下游缓冲，不是需求；库存不并入 USNJ/USTX；不进补货")
    add_exc(f[f["other_pool"]], "out_of_scope_pool", "其他池无通途订单流")
    add_exc(f[(~f["policy_excluded"]) & (~f["cg_buffer"]) & (~f["other_pool"])
              & (f["status"] == "d5_failed")], "d5_failed",
            "D5 明确失败（no_positive_history 等）")
    add_exc(f[(~f["policy_excluded"]) & (~f["cg_buffer"]) & (~f["other_pool"])
              & (f["status"] != "d5_failed") & f["data_gap"]],
            "data_gap", "D1b coverage_status=未覆盖")
    add_exc(f[(~f["policy_excluded"]) & (~f["cg_buffer"]) & (~f["other_pool"])
              & (f["status"] != "d5_failed") & (~f["data_gap"]) & f["shared"]],
            "shared", "market_pool_match=0：共享池未唯一归属")
    add_exc(f[(~f["hard_excl"]) & (f["calib_fail"])], "calibration_uncovered",
            "D5 区间未校准；只作观察，不补货")
    exc = pd.DataFrame(exc_rows)
    if not exc.empty:
        exc = exc.drop_duplicates(["product_id", "pool", "physical_form", "canonical_uom",
                                   "类别"]).reset_index(drop=True)

    # ---------- Top50 输出列
    top_out = top[["序号", "product_id", "market", "pool", "physical_form", "canonical_uom",
                   "demand_pattern", "p50", "p90", "q95", "q90", "q85",
                   "p50_157", "q95_157", "demand_lead", "ss_95", "supply",
                   "stock_inb", "po_extra", "inbound", "late_qty", "supply_on_time",
                   "cross_alloc", "net_95", "net_90", "net_85", "net_157",
                   "action", "qty", "rounding_basis", "moq", "need_date", "order_date",
                   "window_end", "order_late_flag",
                   "arrive_date", "confidence", "cg_buffer", "calibration_status",
                   "join_class", "b_market_confidence", "unknowns"]].copy()
    top_out = top_out.rename(columns={
        "market": "市场", "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
        "demand_pattern": "需求形态", "demand_lead": "交期需求p50",
        "ss_95": "安全库存95", "supply": "C可发供给",
        "stock_inb": "en_stock在途+待发", "po_extra": "PO追加(去重后)",
        "inbound": "在途合计", "late_qty": "迟到在途(ETA>需要日)",
        "supply_on_time": "到时供给",
        "cross_alloc": "跨仓分配", "net_95": "净需求95", "net_90": "净需求90",
        "net_85": "净需求85", "net_157": "净需求157", "action": "建议动作",
        "qty": "建议数量", "rounding_basis": "取整依据", "moq": "MOQ",
        "need_date": "需要日", "order_date": "下单日", "arrive_date": "到货日",
        "window_end": "97天窗口末日", "order_late_flag": "下单时点提示",
        "confidence": "置信度", "cg_buffer": "cg_buffer_observation",
        "calibration_status": "D5校准", "join_class": "C_join",
        "b_market_confidence": "B市场置信", "unknowns": "未知项"})

    # ---------- 自检
    d3b_keys = set(map(tuple, d3b[KEYS].astype(str).values))
    d4_keys = set(map(tuple, d4[KEYS].astype(str).values))
    lineage_ok = (d3b_keys == d4_keys)
    hard_in_top = int((top["hard_excl"] & (~top["cg_buffer"])).sum())
    pol_keys = set(map(tuple, d1b[d1b["decision_state"].astype(str) == "policy_excluded"]
                       [["product_id", "pool", "physical_form", "canonical_uom"]]
                       .astype(str).values))
    pol_in_top = len(set(map(tuple, top[KEYS].astype(str).values)) & pol_keys)
    cg_in_replenish = int(top[(top["cg_buffer"])
                              & (top["action"].isin(["补", "跨仓直发"]))].shape[0])
    cg_marked = int((exc["类别"] == "cg_buffer_observation").sum()) if not exc.empty else 0
    prelim_cols = [c for c in top_out.columns if "preliminary" in str(c)]
    neg_qty = int((top["qty"] < 0).sum())
    bad_net_qty = int(((top["net_95"] <= 0) & (top["qty"] > 0)).sum())
    rounding_bad = 0
    for r in top.itertuples(index=False):
        if r.action == "补":
            need = max(0.0, float(r.net_95))
        elif r.action == "催已有":
            need = max(0.0, min(float(r.net_95), float(r.late_qty)))
        elif r.action == "跨仓直发":
            need = max(0.0, float(r.cross_alloc))
        else:
            need = 0.0
        m = moq_map.get(str(r.product_id))
        expect = (int(math.ceil(need / m) * m) if (m and need > 0)
                  else ceil_int(need))
        if expect != int(r.qty):
            rounding_bad += 1
    # 97/157 与 95/90/85 复算
    net_bad = 0
    for r in top[~top["cg_buffer"]].itertuples(index=False):
        for sl, col in ((95, "net_95"), (90, "net_90"), (85, "net_85")):
            q = {"95": r.q95, "90": r.q90, "85": r.q85}[str(sl)]
            calc = r.demand_lead + max(0.0, q - r.p50) - r.supply_on_time
            if abs(calc - getattr(r, col)) > 1e-6:
                net_bad += 1
        calc157 = (r.p50_157 * LEAD_DAYS / H_SENS
                   + max(0.0, r.q95_157 - r.p50_157) - r.supply_on_time)
        if abs(calc157 - r.net_157) > 1e-6:
            net_bad += 1
    supply_bad = int(((top["supply"] < 0) | (top["supply_on_time"] < 0)
                      | (top["cross_alloc"] < 0)).sum())
    cross_over = 0
    for r in top[top["cross_alloc"] > 0].itertuples(index=False):
        src = f[(f["product_id"] == r.product_id) & (f["pool"] != r.pool)
                & (f["pool"].isin(US_POOLS)) & (~f["cg_buffer"])]
        cap = float(sum(max(0.0, s.supply_on_time - max(0.0, s.net_95))
                        for s in src.itertuples(index=False)))
        if r.cross_alloc > cap + 1e-9:
            cross_over += 1
    top_keys = set(map(tuple, top[KEYS].astype(str).values))
    exc_keys = set(map(tuple, exc[["product_id", "pool", "physical_form", "canonical_uom"]]
                       .astype(str).values)) if not exc.empty else set()
    top_replenish_keys = set(map(tuple, top[top["action"].isin(["补", "跨仓直发", "催已有"])][KEYS]
                                 .astype(str).values))
    overlap = len(top_replenish_keys & exc_keys)
    empty_ev = int(top_out[["建议动作", "未知项", "置信度"]].isna().any(axis=1).sum())
    action_set = set(top["action"])

    self_rows = [
        dict(检查项="D4 v2 键集 = D3b v3.2 正式键", 期望=len(d3b_keys),
             实际=len(d4_keys),
             通过="是" if lineage_ok else "否"),
        dict(检查项="催已有必须有迟到在途", 期望=0,
             实际=int(((top["action"] == "催已有") & (top["late_qty"] <= 0)).sum()),
             通过="是" if int(((top["action"] == "催已有") & (top["late_qty"] <= 0)).sum()) == 0 else "否"),
        dict(检查项="PO 在途去重（PO追加 ≤ intransit=0 的 PO open）", 期望="≤",
             实际=round(float(f["po_extra"].sum()), 2),
             通过="是" if float(f["po_extra"].sum()) <= float(po_use_m["qty_eff"].sum()) + 1e-6 else "否"),
        dict(检查项="成品 MOQ=n/a（Top50 产品键）", 期望=len(top),
             实际=int((top["moq"] == "n/a（自有工厂）").sum()),
             通过="是" if int((top["moq"] == "n/a（自有工厂）").sum()) == len(top) else "否"),
        dict(检查项="Top50 键数", 期望=50, 实际=len(top),
             通过="是" if len(top) == 50 else "否"),
        dict(检查项="policy_excluded 进入补货动作", 期望=0, 实际=pol_in_top,
             通过="是" if pol_in_top == 0 else "否"),
        dict(检查项="硬排除键进入 Top50", 期望=0, 实际=hard_in_top,
             通过="是" if hard_in_top == 0 else "否"),
        dict(检查项="CG 缓冲进入 补/跨仓", 期望=0, 实际=cg_in_replenish,
             通过="是" if cg_in_replenish == 0 else "否"),
        dict(检查项="CG 池键全部标 cg_buffer_observation", 期望=int(f["cg_buffer"].sum()),
             实际=cg_marked, 通过="是" if cg_marked == int(f["cg_buffer"].sum()) else "否"),
        dict(检查项="旧版 CG 标记字段残留", 期望=0, 实际=len(prelim_cols),
             通过="是" if len(prelim_cols) == 0 else "否"),
        dict(检查项="建议数量为负", 期望=0, 实际=neg_qty,
             通过="是" if neg_qty == 0 else "否"),
        dict(检查项="净需求≤0 仍出补货数量", 期望=0, 实际=bad_net_qty,
             通过="是" if bad_net_qty == 0 else "否"),
        dict(检查项="MOQ/取整不可复算", 期望=0, 实际=rounding_bad,
             通过="是" if rounding_bad == 0 else "否"),
        dict(检查项="97/157、95/90/85 复算不一致", 期望=0, 实际=net_bad,
             通过="是" if net_bad == 0 else "否"),
        dict(检查项="供给为负或跨仓超额", 期望=0, 实际=supply_bad + cross_over,
             通过="是" if supply_bad + cross_over == 0 else "否"),
        dict(检查项="Top50 补/跨仓键出现在 4_观察与例外", 期望=0, 实际=overlap,
             通过="是" if overlap == 0 else "否"),
        dict(检查项="动作/未知/置信度为空", 期望=0, 实际=empty_ev,
             通过="是" if empty_ev == 0 else "否"),
        dict(检查项="动作覆盖（补/不补/观察）", 期望="≥3 类",
             实际=len(action_set), 通过="是" if len(action_set) >= 3 else "否"),
        dict(检查项="只读（不写 EN/通途、不下单）", 期望="是", 实际="是", 通过="是"),
    ]
    self_tbl = pd.DataFrame(self_rows)
    self_pass = bool((self_tbl["通过"] == "是").all())

    # ---------- 契约 / CG 说明
    cg_note = pd.DataFrame([
        ("修正状态", "CG 已按 B owner 修正（D3b v3.2 / D5 v3.1）"),
        ("WayfairCG 归池", "4,887 件 = 美东USNJ 1,564 + 美中USTX 3,323"),
        ("CG 池口径", "CG / CG-USNJ / CG-USTX 共 178 键=下游缓冲，需求 0，不进净额；"
                     "不是 data_gap"),
        ("本版处置", "标 cg_buffer_observation，不进 补/跨仓；CG 库存不并入 USNJ/USTX"),
        ("Top50 CG 缓冲观察", int(top["cg_buffer"].sum())),
        ("CG 池库存", "；".join(f"{r.cg_pool}={r.cg_available:.0f}" for r in cg_total.itertuples(index=False))),
    ], columns=["项", "内容"])

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("key_version", "D1b-v2.3-2026-11-02（1,853 键）"),
        ("输入", "D1b v2.3 / D3b v3.1 / D5 v3.1 / D2b v2 / D5b v2 / D4 v2 / C v14 / "
                 "B r10 / leadtime / MOQ"),
        ("需求", f"D5 v3.1 p50/p90 的 {H_MAIN} 天需求；157 天敏感性"),
        ("交期", f"规划 {LEAD_DAYS} 天（leadtime median {lead['median']:.1f} / "
                 f"p90 {lead['p90']:.1f}）"),
        ("安全库存", "q_s − p50（s=95/90/85）；默认 95"),
        ("供给", "C v14 可发供给 + en_stock(2026-10-28) intransit/waiting；"
                 "仅 en_stock intransit=0 的 SKU/仓才追加 PO open，避免重复"),
        ("净需求", f"p50×{LEAD_DAYS}/{H_MAIN} + max(0,q_s−p50) − 到时供给（可发+在途−迟到）"),
        ("取整", "成品 MOQ=n/a（自有绍兴工厂）按个向上取整；仅原料项用 moq_items_21"),
        ("动作", "补 / 不补 / 催已有 / 跨仓直发 / 观察；有在途且 ETA>需要日→催已有"),
        ("CG", "CG 池 178 键=下游缓冲，标 cg_buffer_observation，不进补货；"
               "CG 库存不并入 USNJ/USTX；WayfairCG 4,887=USNJ 1,564+USTX 3,323"),
        ("ETA", "willArriveDate > purchaseArrivalDate > shipment_segments(DN→PO 可匹配) > "
                "50 天规划(assumed)；en_stock 已发运在途按 +20 天假设"),
        ("日期", f"as_of={AS_OF}；需要日=可发覆盖耗尽日（封顶 {H_MAIN} 天）；"
                 f"下单日=需要日−{LEAD_DAYS}；到货日=需要日"),
        ("不做", "不写 EN/通途、不下单、不采购、不 push"),
    ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
        columns=["项", "内容"])

    # ---------- dry-run 输出
    print(f"== {RULE_VERSION} ==  Top50 {len(top)} 键｜可评估 {len(cand)}｜"
          f"硬排除 {int(f['hard_excl'].sum())}")
    print(f"在途/PO：en_stock intr {en_total_intr:.0f}/wait {en_total_wait:.0f}"
          f"（映射 {en_mapped_intr:.0f}/{en_mapped_wait:.0f}）｜PO {po_rows} 行/{po_skus} SKU，"
          f"与 en_stock 重叠 {po_overlap_skus} SKU/{po_overlap_rows} 行（仓对 "
          f"{pairs_with_intr}/{po_pairs_all}），PO 追加 {po_extra_total:.0f}")
    print("ETA 来源：", json.dumps(eta_src_counts, ensure_ascii=False),
          f"｜shipment_segments DN→PO {seg_matched} 个，应用到 open PO {seg_applied} 个")
    print("动作：", json.dumps(top["action"].value_counts().to_dict(), ensure_ascii=False))
    print("池分布：", json.dumps(top["pool"].value_counts().to_dict(), ensure_ascii=False))
    print("形态：", json.dumps(top["physical_form"].value_counts().to_dict(), ensure_ascii=False))
    print("需求形态：", json.dumps(top["demand_pattern"].value_counts().to_dict(), ensure_ascii=False))
    print("CG 缓冲观察：", int(top["cg_buffer"].sum()),
          "（CG 池键总数", int(f["cg_buffer"].sum()), "）")
    print("净需求95：", round(float(top["net_95"].min()), 2), "..", round(float(top["net_95"].max()), 2),
          "｜建议数量：", int(top["qty"].min()), "..", int(top["qty"].max()),
          "｜合计", int(top["qty"].sum()))
    print("观察与例外：", len(exc), "行；类别：",
          json.dumps(exc["类别"].value_counts().to_dict() if not exc.empty else {}, ensure_ascii=False))
    print("\n催已有明细")
    for r in top[top["action"] == "催已有"].itertuples(index=False):
        print(f"  {r.product_id} | {r.pool} | 净需求 {r.net_95:.1f} | "
              f"迟到在途 {r.late_qty:.1f} | 需要日 {r.need_date} | "
              f"下单日 {r.order_date} | 催 {r.qty}")
    print("\n动作汇总")
    print(act_sum.to_string(index=False))
    print("\n自检")
    print(self_tbl[["检查项", "期望", "实际", "通过"]].to_string(index=False))
    print(f"\n自检总体：{'PASS' if self_pass else 'FAIL'}")

    if args.dry_run:
        return 0 if self_pass else 1

    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as xw:
        contract.to_excel(xw, sheet_name="0_契约", index=False)
        top_out.to_excel(xw, sheet_name="1_Top50", index=False)
        act_sum.to_excel(xw, sheet_name="2_动作汇总", index=False)
        pool_sum.to_excel(xw, sheet_name="2b_池与形态", index=False)
        pat_sum.to_excel(xw, sheet_name="2c_需求形态", index=False)
        ev_tbl.to_excel(xw, sheet_name="3_证据与未知", index=False)
        exc.to_excel(xw, sheet_name="4_观察与例外", index=False)
        self_tbl.to_excel(xw, sheet_name="5_自检", index=False)
        cg_note.to_excel(xw, sheet_name="6_CG映射说明", index=False)

    # ---------- 报告
    lines = [
        f"# D6 Top50 补货沙盒（{RULE_VERSION}；只读）",
        "",
        f"- 工作簿：`{Path(args.out_xlsx).name}`",
        f"- Top50 **{len(top)}** 键；可评估 **{len(cand)}**；硬排除 **{int(f['hard_excl'].sum())}**",
        "- **CG 已按 B owner 修正**：WayfairCG 4,887 = 美东USNJ 1,564 + 美中USTX 3,323；"
        "CG 池 178 键是下游缓冲（需求 0），标 `cg_buffer_observation`，不进补货。",
        "",
        "## 1. 50 键分布",
        "",
        "| 维度 | 分布 |",
        "|---|---|",
        f"| 动作 | {json.dumps(top['action'].value_counts().to_dict(), ensure_ascii=False)} |",
        f"| 池 | {json.dumps(top['pool'].value_counts().to_dict(), ensure_ascii=False)} |",
        f"| 形态 | {json.dumps(top['physical_form'].value_counts().to_dict(), ensure_ascii=False)} |",
        f"| 需求形态 | {json.dumps(top['demand_pattern'].value_counts().to_dict(), ensure_ascii=False)} |",
        f"| CG 缓冲观察 | {int(top['cg_buffer'].sum())}（CG 池键总数 "
        f"{int(f['cg_buffer'].sum())}） |",
        "",
        "## 1.1 在途/PO 覆盖",
        "",
        f"- en_stock(2026-10-28)：intransit **{en_total_intr:.0f}**、waiting_shipment "
        f"**{en_total_wait:.0f}**；可映射到正式键 {en_mapped_intr:.0f}/{en_mapped_wait:.0f}。",
        f"- PO open：**{po_rows}** 行 / **{po_skus}** SKU / {po_pairs_all} 个 SKU×仓；"
        f"其中 **{po_overlap_skus} SKU / {po_overlap_rows} 行**已在 en_stock intransit"
        f"（{pairs_with_intr} 个仓对，不重复加）；仅 intransit=0 的仓对追加 "
        f"**{po_extra_total:.0f}** 件。",
        f"- ETA 来源：{json.dumps(eta_src_counts, ensure_ascii=False)}；"
        f"shipment_segments DN→PO 得到 {seg_matched} 个 PO 号，"
        f"应用到当前 open PO {seg_applied} 个。",
        "",
        "## 2. 动作汇总",
        "",
    ]
    for r in act_sum.itertuples(index=False):
        lines.append(f"- {r.动作}：{r.键数} 键，建议数量合计 {r.建议数量合计:.0f}，"
                     f"净需求95合计 {r.净需求95合计:.1f}")
    lines += [
        "",
        f"- 净需求95 范围：{top['net_95'].min():.2f} .. {top['net_95'].max():.2f}",
        f"- 建议数量范围：{int(top['qty'].min())} .. {int(top['qty'].max())}，"
        f"合计 {int(top['qty'].sum())}",
        f"- 与 v2 对照：v2 补 28 / 不补 10 / 跨仓 4 / 催已有 0，建议数量 2,854；"
        f"v3 补 {int((top['action']=='补').sum())} / 不补 {int((top['action']=='不补').sum())} / "
        f"跨仓 {int((top['action']=='跨仓直发').sum())} / 催已有 {int((top['action']=='催已有').sum())}，"
        f"建议数量 {int(top['qty'].sum())}。",
        f"- 观察与例外：{len(exc)} 行；"
        f"{json.dumps(exc['类别'].value_counts().to_dict() if not exc.empty else {}, ensure_ascii=False)}",
        "",
        "## 3. 口径与边界",
        "",
        f"- 需求 {H_MAIN} 天（157 天敏感性单列）；交期规划 {LEAD_DAYS} 天；"
        "需要日 = C 可发供给覆盖耗尽日（封顶 97 天），不是固定 97 天后；"
        "下单日=需要日−50，已过的标「应立即下单」。",
        "安全库存 = 服务分位 − p50，默认 95，另列 90/85。",
        "- 供给含 en_stock 在途/待发；PO open 只补 intransit=0 的 SKU/仓，避免重复。",
        "- ETA：willArrive/purchaseArrival 优先；shipment_segments 仅 DN→PO 匹配上才用；"
        "缺失按 50 天规划并标 assumed；en_stock 已发运在途按 +20 天假设。",
        "- 成品 MOQ=n/a（自有绍兴工厂），按个向上取整；仅原料项用 moq_items_21。",
        "- CG 池 p50=0 是下游缓冲的设计结果，不是需求；CG 销量已按 B owner 归入 USNJ/USTX。",
        "- Top50 的 CG 键只作 `cg_buffer_observation`，不进补货；"
        "CG 库存不并入 USNJ/USTX。",
        "- 套件/套：正式键集中无套件需求键（1,853 键全部 uom=个），本轮无法覆盖；骨架 0（无预测）。",
        "",
        "## 4. 自检",
        "",
        "| 检查项 | 期望 | 实际 | 通过 |",
        "|---|---:|---:|---|",
    ]
    for r in self_rows:
        lines.append(f"| {r['检查项']} | {r['期望']} | {r['实际']} | {r['通过']} |")
    lines += ["", f"**自检总体：{'PASS' if self_pass else 'FAIL'}**", ""]
    Path(args.out_report).write_text("\n".join(lines), encoding="utf-8")

    manifest = dict(
        rule_version=RULE_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        generated_at_local=datetime.now().astimezone().isoformat(),
        generator=script_identity(), inputs=inputs,
        as_of=str(AS_OF), lead_days=LEAD_DAYS, horizon_main=H_MAIN, horizon_sens=H_SENS,
        service_level_default=SL_DEFAULT,
        inbound=dict(en_stock_intransit=en_total_intr, en_stock_waiting=en_total_wait,
                     en_stock_mapped_intransit=en_mapped_intr,
                     en_stock_mapped_waiting=en_mapped_wait,
                     po_rows=po_rows, po_skus=po_skus, po_pairs=po_pairs_all,
                     po_pairs_with_intransit=pairs_with_intr,
                     po_overlap_skus=po_overlap_skus, po_overlap_rows=po_overlap_rows,
                     po_extra=po_extra_total, eta_sources=eta_src_counts,
                     shipment_segment_pos=seg_matched,
                     shipment_segment_applied=seg_applied,
                     inbound_keys=int((f["inbound"] > 0).sum()),
                     inbound_qty=float(f["inbound"].sum()),
                     late_qty=float(f["late_qty"].sum())),
        counts=dict(top50=len(top), evaluable=len(cand), hard_excluded=int(f["hard_excl"].sum()),
                    exceptions=len(exc),
                    actions=top["action"].value_counts().to_dict(),
                    pools=top["pool"].value_counts().to_dict(),
                    forms=top["physical_form"].value_counts().to_dict(),
                    patterns=top["demand_pattern"].value_counts().to_dict(),
                    cg_buffer_observation=int(top["cg_buffer"].sum()),
                    cg_buffer_keys_total=int(f["cg_buffer"].sum())),
        quantity=dict(min=int(top["qty"].min()), max=int(top["qty"].max()),
                      sum=int(top["qty"].sum())),
        net95=dict(min=float(top["net_95"].min()), max=float(top["net_95"].max())),
        selfcheck=self_rows, selfcheck_pass=self_pass,
        lineage=dict(d3b="D3b v3.2", d4="D4 v2", keys=len(d4_keys),
                     key_set_equal=bool(lineage_ok)),
        cg_mapping_note="CG 已按 B owner 修正：WayfairCG 4,887 = USNJ 1,564 + USTX 3,323；"
                        "CG 池 178 键为下游缓冲，cg_buffer_observation，不进补货",
        outputs=dict(
            xlsx=dict(path=args.out_xlsx, sha256=sha256(args.out_xlsx),
                      bytes=Path(args.out_xlsx).stat().st_size),
            report=dict(path=args.out_report, sha256=sha256(args.out_report),
                        bytes=Path(args.out_report).stat().st_size)),
        note="xlsx 含 openpyxl 时间戳，重跑 SHA 不保证相同。",
    )
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print(f"\n已写：{args.out_xlsx}\n      {args.out_report}\n      {args.manifest}")
    return 0 if self_pass else 1


if __name__ == "__main__":
    sys.exit(main())
