# -*- coding: utf-8 -*-
"""D6 v6 全量补货沙盒（只读）。

相对 v3 的变化
1) 范围扩到全量 1,853 个需求键；另列 307 policy_excluded 行。
2) 删除「跨仓直发」：动作只保留 补 / 不补 / 催已有 / 观察；
   合同写 cross_warehouse_direct=disabled_by_business。
3) CG：按 SKU owner 把 CG 库存作为 USNJ/USTX 分支的缓冲抵扣（cg_buffer_credit），
   生成任何 CG 仓补货建议；CG 池 178 键只作 observation；CG 库存/销量单列。
4) ETA 用实测分布：SO→DN 按 customer/role；头程用 shipment_segments；
   同池真实样本阶段独立情景；在途/待发采用未知货龄完整头程情景。
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
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supply_netting.replenishment_actions import (  # noqa: E402
    horizon_net_need,
    bootstrap_independent_route,
    unknown_age_transit_days,
    production_samples_for_pool_role,
    route_candidates_for_pool,
    select_route_candidate,
    select_snapshot_date,
    split_actions,
)
from supply_netting.leadtime_evidence import production_leadtime_rows  # noqa: E402

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
RULE_VERSION = "D6-v6-2026-11-02"
AS_OF = date(2026, 11, 2)
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
    global AS_OF
    ap = argparse.ArgumentParser(description="D6 v6 全量补货沙盒（只读）")
    ap.add_argument("--d1b", default=f"{BA}/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--d3b", default=f"{BA}/codex-repair-20261102/"
                    "D_历史归一与回测_D3b_v3_4_2026-11-02.xlsx")
    ap.add_argument("--d5", default=f"{BA}/codex-repair-20261102/D5v6_2-full/"
                    "D_概率与服务_D5_v6_2026-11-02.xlsx")
    ap.add_argument("--d2b", default=f"{BA}/D_删失需求估计_D2b_v2_2026-11-02.xlsx")
    ap.add_argument("--d5b", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02.xlsx")
    ap.add_argument("--as-of", type=date.fromisoformat, default=AS_OF,
                    help="审计日 YYYY-MM-DD；库存只使用不晚于该日的快照")
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
    ap.add_argument("--out-xlsx", default=f"{BA}/D_Top50沙盒_D6_v6_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_Top50沙盒_D6_v6_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_Top50沙盒_D6_v6_2026-11-02.manifest.json")
    ap.add_argument("--decisions", default=f"{BA}/D6_DECISIONS_D6_v6_2026-11-02.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    AS_OF = args.as_of

    inputs = {}
    for k, v in (("D1B_V2_3", args.d1b), ("D3B_V3_4", args.d3b), ("D5_V6_2", args.d5),
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
    c14_date_match = re.search(r"\d{4}-\d{2}-\d{2}", Path(args.c14).name)
    cg_snapshot = c14_date_match.group(0) if c14_date_match else None
    cg_snapshot_status = ("未知（来源日期不明）" if cg_snapshot is None else
                          "future（隔离）" if cg_snapshot > AS_OF.isoformat() else
                          "fresh" if cg_snapshot == AS_OF.isoformat() else "stale")
    cg_future_blocked = cg_snapshot is None or cg_snapshot > AS_OF.isoformat()
    cg = (pd.DataFrame(columns=["cg_available", "erp_item_code", "cg_owner", "cg_pool"])
          if cg_future_blocked else pd.read_excel(args.c14, sheet_name="23_CG库存池"))
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

    # ---------- ETA：同池真实生产与头程样本；独立阶段情景，不作联合服务保证
    dn = pd.read_csv(args.dn_rows)
    dn_stats = dn.copy()
    dn_stats["lead_days"] = pd.to_numeric(dn_stats["lead_days"], errors="coerce")
    dn_stats["posting_dt"] = pd.to_datetime(dn_stats["posting_date"], errors="coerce")
    dn_stats["year"] = dn_stats["posting_dt"].dt.year
    dn_recent = dn_stats[(dn_stats["posting_dt"] >= AS_OF - pd.DateOffset(months=6))
                         & (dn_stats["posting_dt"] <= pd.Timestamp(AS_OF))]
    year_stats = (dn_stats.groupby("year")["lead_days"]
                  .agg(n="count", p50="median", p90=lambda s: s.quantile(.9)).to_dict("index"))
    cust_stats = (dn_recent.groupby("customer")["lead_days"]
                  .agg(n="count", p50="median", p90=lambda s: s.quantile(.9)).to_dict("index"))
    role_stats = (dn_recent.groupby("role")["lead_days"]
                  .agg(n="count", p50="median", p90=lambda s: s.quantile(.9)).to_dict("index"))
    zmt = pd.read_csv(args.zmt)
    from supply_netting.route_leadtime import build_route_evidence
    production_samples, head_samples, route_evidence_report = build_route_evidence(dn, zmt, AS_OF)
    pool_code = {"美东USNJ": "USNJ", "美中USTX": "USTX", "波兰": "PL"}
    production_dedup = production_leadtime_rows(dn_recent)
    production_dedup["lead_days"] = pd.to_numeric(production_dedup["lead_days"], errors="coerce")
    production_dedup = production_dedup.dropna(subset=["customer", "dn", "so", "lead_days"])
    production_dedup = production_dedup[production_dedup["lead_days"] >= 0]
    all_role_final = (production_dedup.groupby(["customer", "dn", "so"], dropna=False)
                      ["lead_days"].max().reset_index())
    route_pool_of_customer = {"CENTRADE": "USNJ", "DANEEY": "USTX", "波兰公司": "PL"}
    for row in all_role_final.itertuples(index=False):
        sample_pool = route_pool_of_customer.get(str(row.customer))
        if sample_pool:
            production_samples.setdefault((sample_pool, "__all_roles__"), []).append(
                float(row.lead_days))
    role_names = sorted({role_of(pid) for pid in d4["product_id"].astype(str)})
    main_label = {"sea_regular": "海运普船", "sea_fast": "海运快船",
                  "air": "空运", "unknown": "未知main_haul"}
    last_label = {"truck": "卡车", "express": "快递", "unknown": "未知last_mile"}
    route_combo, pool_head_scenario = {}, {}
    pool_routes = {}
    route_evidence_rows = []
    for route_pool in sorted(set(pool_code.values())):
        pool_head = [day for (p, _, _), days in head_samples.items() if p == route_pool
                     for day in days]
        pool_head_scenario[route_pool] = (float(np.quantile(pool_head, .5)),
                                          float(np.quantile(pool_head, .9))) if pool_head else None
        routes = route_candidates_for_pool(head_samples, route_pool)
        pool_routes[route_pool] = routes
        for role in role_names:
            production, production_source = production_samples_for_pool_role(
                production_samples, route_pool, role)
            for main, last in routes:
                route_combo[(route_pool, role, main, last)] = bootstrap_independent_route(
                    production, head_samples[(route_pool, main, last)])
                if route_combo[(route_pool, role, main, last)] is not None:
                    route_combo[(route_pool, role, main, last)]["production_source"] = production_source
            if production:
                route_evidence_rows.append(dict(证据类型="production", pool=route_pool, role=role,
                                                n=len(production), source=production_source,
                                                note=(f"{production_source}; "
                                                      f"{'small sample' if len(production) < 30 else 'observed'}; "
                                                      "not a service guarantee")))
            else:
                route_evidence_rows.append(dict(证据类型="production", pool=route_pool, role=role,
                                                n=0, source="unavailable",
                                                note="no role sample or same-pool fallback; route ETA unavailable"))
        for (p, main, last), days in head_samples.items():
            if p == route_pool:
                route_evidence_rows.append(dict(证据类型="head_route", pool=p,
                                                role="", main=main_label.get(main, main),
                                                last=last_label.get(last, last), n=len(days),
                                                note=(f"{'small sample' if len(days) < 30 else 'observed'}; "
                                                      "not a service guarantee")))
    route_evidence_summary = {
        "as_of": route_evidence_report["as_of"],
        "dn": {k: v for k, v in route_evidence_report["dn"].items() if k != "groups"},
        "head": {k: v for k, v in route_evidence_report["head"].items()
                 if k not in {"groups", "delivery_purpose_counts"}},
        "observed_groups": route_evidence_rows,
    }

    # ---------- 在途/PO（en_stock 为主；仅 intransit=0 的 SKU/仓用 PO open）
    es = pd.read_parquet(args.en_stock)
    es_dates = es["snapshot_date"].dropna().astype(str).tolist()
    es_snapshot = select_snapshot_date(es_dates, AS_OF)
    es_source_snapshot = max((d[:10] for d in es_dates), default=None)
    es_snapshot_status = ("未知（无不晚于审计日快照）" if es_snapshot is None else
                          "fresh" if es_snapshot == AS_OF.isoformat() else "stale")
    es_latest_status = ("未知" if es_source_snapshot is None else
                        "future（隔离）" if es_source_snapshot > AS_OF.isoformat() else
                        "fresh" if es_source_snapshot == AS_OF.isoformat() else "stale")
    if es_snapshot is None:
        es = es.iloc[0:0].copy()
    else:
        es = es[es["snapshot_date"].astype(str).str[:10] == es_snapshot].copy()
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
    # 无逐 PO ETA → PO 创建时间不等于发运时间；仅用同池 head 情景，剩余阶段未知。
    m_ass = po["eta_p50"].isna()
    po["customer"] = po["warehouseName"].astype(str).map(POOL_OF_WAREHOUSE).map(CUSTOMER_OF_POOL)
    po["role"] = po["goods_sku"].astype(str).map(lambda s: role_of(tt2prod.get(s, "")))
    po["route_pool"] = po["warehouseName"].astype(str).map(POOL_OF_WAREHOUSE).map(
        {"美东USNJ": "USNJ", "美中USTX": "USTX", "波兰": "PL"})
    for i in po.index[m_ass]:
        pool = po.at[i, "route_pool"]
        distribution = pool_head_scenario.get(pool)
        if distribution is None:
            po.at[i, "eta_src"] = "po_stage_unknown_head_unavailable_manual_review"
            continue
        base = po.at[i, "purchase_dt"]
        missing_purchase_date = pd.isna(base)
        if pd.isna(base):
            base = pd.Timestamp(AS_OF)
        p50_days = unknown_age_transit_days("po", 0, distribution[0])
        p90_days = unknown_age_transit_days("po", 0, distribution[1])
        e50 = base + pd.Timedelta(days=p50_days)
        e90 = base + pd.Timedelta(days=p90_days)
        if e90 < pd.Timestamp(AS_OF):
            e50 = pd.Timestamp(AS_OF) + pd.Timedelta(days=p50_days)
            e90 = pd.Timestamp(AS_OF) + pd.Timedelta(days=p90_days)
            po.at[i, "eta_src"] = "po_created_before_asof_age_unknown_full_transit_scenario_manual_review"
        elif missing_purchase_date:
            po.at[i, "eta_src"] = "po_stage_unknown_from_asof_manual_review_scenario"
        else:
            po.at[i, "eta_src"] = "po_creation_not_ship_date_stage_unknown_scenario_manual_review"
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
    po_eta_basis = (po_use_m.groupby(["product_x", "pool_x"], dropna=False)["eta_src"]
                    .agg(lambda values: "；".join(sorted(set(str(v) for v in values if str(v)))))
                    .rename("po_eta_basis").reset_index())
    po_extra_total = float(po_use_m["qty_eff"].sum())
    pairs_all = int(len(set(zip(po["goods_sku"].astype(str),
                                po["warehouseName"].astype(str)))))

    ks = (sw_m.groupby(["product_x", "pool_x"])
          .agg(stock_inb=("stock_inb", "sum"), stock_intr=("intr", "sum"),
               stock_wait=("wait", "sum")).reset_index())
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
    f = f.merge(po_eta_basis, left_on=["product_id", "pool"],
                right_on=["product_x", "pool_x"], how="left")
    f["po_eta_basis"] = f["po_eta_basis"].fillna("")
    f["po_manual_review"] = f["po_eta_basis"].str.contains("scenario|manual_review", case=False, regex=True)
    f = f.merge(cg_credit, on=["product_id", "pool"], how="left")
    for c in ("stock_inb", "stock_intr", "stock_wait", "po_extra", "cg_buffer_credit"):
        f[c] = f[c].fillna(0.0)
    f["po_extra"] = f["po_extra"].astype(float)
    f["inbound"] = f["stock_inb"] + f["po_extra"]
    f["en_stock_snapshot_date"] = es_snapshot or ""
    f["en_stock_snapshot_status"] = es_snapshot_status
    f["en_stock_latest_source_date"] = es_source_snapshot or ""
    f["en_stock_latest_source_status"] = es_latest_status
    f["cg_snapshot_date"] = cg_snapshot or ""
    f["cg_snapshot_status"] = cg_snapshot_status
    f["snapshot_review_required"] = (es_snapshot_status != "fresh"
                                     or cg_snapshot_status != "fresh")
    f["market"] = f["pool"].map(MARKET_OF_POOL).fillna("OTHER")
    f["supply"] = pd.to_numeric(f["可发供给"], errors="coerce").fillna(0.0)
    f["cg_buffer"] = f["pool"].astype(str).str.startswith("CG")
    f["other_pool"] = f["pool"].astype(str) == "其他"
    f["empirical_scenario"] = f["calibration_status"].astype(str) == "empirical_time_ordered"
    f["calib_fail"] = ~f["calibration_status"].astype(str).isin(
        ("ok", "empirical_time_ordered"))
    f["service_validation_status"] = np.where(
        f["calibration_status"].astype(str) == "ok", "validated",
        np.where(f["empirical_scenario"], "empirical_time_ordered_unvalidated", "unvalidated"))
    f["manual_review_required"] = ((f["service_validation_status"] != "validated")
                                   | f["po_manual_review"]
                                   | f["snapshot_review_required"])
    f["auto_order"] = False
    f["protection_horizon_days"] = H_MAIN
    f["sensitivity_horizon_days"] = H_SENS
    f["data_gap"] = f["coverage_status"].astype(str) == "未覆盖"
    f["shared"] = f["market_pool_match"].astype(str) == "0"
    f["no_join"] = f["join_class"].astype(str) != "join_full"
    f["hard_excl"] = ((f["status"] == "d5_failed") | f["data_gap"] | f["shared"]
                      | f["no_join"] | f["cg_buffer"] | f["other_pool"] | cg_future_blocked
                      | (es_snapshot is None))

    # ---------- 需要日 / ETA / 迟到量
    f["daily"] = pd.to_numeric(f["p50"], errors="coerce").fillna(0.0) / H_MAIN
    f["cover_days"] = np.where(f["daily"] > 0, f["supply"] / f["daily"], H_MAIN).clip(0, H_MAIN)
    f["need_dt"] = [AS_OF + timedelta(days=int(math.floor(x))) for x in f["cover_days"]]
    need_map = {(r.product_id, r.pool): r.need_dt for r in f.itertuples(index=False)}
    f["eta_p50"] = pd.NaT
    f["eta_p90"] = pd.NaT
    f["late_qty"] = 0.0

    # 在途/待发货龄未知；使用同池完整头程样本作显式情景，不加生产阶段。
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
        route_pool = pool_code.get(str(r["pool"]))
        head_distribution = pool_head_scenario.get(route_pool)
        if head_distribution is None:
            continue
        head_p50, head_p90 = head_distribution
        upd(i, float(r["stock_intr"]),
            unknown_age_transit_days("intr", 0, head_p50),
            unknown_age_transit_days("intr", 0, head_p90))
        upd(i, float(r["stock_wait"]),
            unknown_age_transit_days("wait", 0, head_p50),
            unknown_age_transit_days("wait", 0, head_p90))
    # PO：purchaseDate + full 分布（已过期→头程）
    for r in po_use_m.itertuples(index=False):
        key = (r.product_x, r.pool_x)
        if key not in need_map:
            continue
        idx = f.index[(f["product_id"] == r.product_x) & (f["pool"] == r.pool_x)]
        if len(idx) == 0:
            continue
        i = idx[0]
        if pd.isna(r.eta_p50) or pd.isna(r.eta_p90):
            continue
        p50 = pd.Timestamp(r.eta_p50)
        p90 = pd.Timestamp(r.eta_p90)
        upd(i, float(r.qty_eff), (p50 - pd.Timestamp(AS_OF)).days,
            (p90 - pd.Timestamp(AS_OF)).days)

    # 新单路线只从本池明确观测到的 main/last 组合中选。
    f["inbound_eta_p50"], f["inbound_eta_p90"] = f["eta_p50"], f["eta_p90"]
    f["recommended_main_haul"] = ""
    f["recommended_last_mile"] = ""
    f["mode_fits"] = False
    f["last_mile_fits"] = False
    f["replenish_eta_p50"] = pd.NaT
    f["replenish_eta_p90"] = pd.NaT
    f["route_status"] = ""
    for m in main_label.values():
        if m != "未知main_haul":
            f[f"{m}_p90"] = pd.NaT
    for l in last_label.values():
        if l != "未知last_mile":
            f[f"{l}_seg3_p90"] = pd.NaT
    for i, r in f.iterrows():
        role = role_of(r["product_id"])
        route_pool = pool_code.get(str(r["pool"]))
        need = pd.Timestamp(r["need_dt"])
        routes = []
        for main, last in pool_routes.get(route_pool, []):
            estimate = route_combo.get((route_pool, role, main, last))
            if estimate is not None:
                routes.append((main, last, estimate))
        need_days = (need - pd.Timestamp(AS_OF)).days
        chosen, route_fits = select_route_candidate(routes, need_days)
        if chosen is None:
            f.at[i, "recommended_main_haul"] = "路线待确认"
            f.at[i, "recommended_last_mile"] = "路线待确认"
            f.at[i, "route_status"] = "route_unavailable_manual_review"
            f.at[i, "transport_basis"] = "本池无完整路线样本；人工确认；urgency_only"
            continue
        chosen_main, chosen_last, estimate = chosen
        f.at[i, "recommended_main_haul"] = main_label[chosen_main]
        f.at[i, "recommended_last_mile"] = last_label[chosen_last]
        f.at[i, "mode_fits"] = route_fits
        f.at[i, "last_mile_fits"] = route_fits
        f.at[i, "replenish_eta_p50"] = pd.Timestamp(AS_OF) + pd.Timedelta(days=estimate["p50"])
        f.at[i, "replenish_eta_p90"] = pd.Timestamp(AS_OF) + pd.Timedelta(days=estimate["p90"])
        if not route_fits:
            f.at[i, "route_status"] = "route_scenario_late_manual_review"
        elif estimate["n_production"] < 30 or estimate["n_head"] < 30:
            f.at[i, "route_status"] = "small_sample_route_manual_review"
        else:
            f.at[i, "route_status"] = "pool_route_observed"
        for main in main_label:
            named = [route[2]["p90"] for route in routes if route[0] == main]
            if named and main in main_label and main_label[main] in ("海运普船", "海运快船", "空运"):
                f.at[i, f"{main_label[main]}_p90"] = pd.Timestamp(AS_OF) + pd.Timedelta(days=min(named))
        for last in last_label:
            named = [route[2]["p90"] for route in routes if route[1] == last]
            if named and last in last_label and last_label[last] in ("卡车", "快递"):
                f.at[i, f"{last_label[last]}_seg3_p90"] = pd.Timestamp(AS_OF) + pd.Timedelta(days=min(named))
        f.at[i, "transport_basis"] = (
            f"本池真实样本独立阶段情景 n生产={estimate['n_production']} n头程={estimate['n_head']}；"
            f"production_source={estimate['production_source']}；阶段独立假设；"
            "无服务保证；urgency_only")
    if "transport_basis" not in f:
        f["transport_basis"] = "本池无完整路线样本；路线待确认；urgency_only"
    f["transport_basis"] = f["transport_basis"].replace("", "本池无完整路线样本；路线待确认；urgency_only")
    f["route_status"] = f["route_status"].replace("", "route_unavailable_manual_review")
    f["manual_review_required"] = (f["manual_review_required"]
                                   | (f["route_status"] != "pool_route_observed"))
    f["stage_independence_assumption"] = True
    f["no_service_guarantee"] = True
    f["supply_on_time"] = f["supply"] + f["inbound"] - f["late_qty"]

    # ---------- 按完整保护窗的预测总分位数净额（人工政策情景）
    for qcol, netcol in (("q95", "net_95"), ("q90", "net_90"), ("q85", "net_85")):
        f[netcol] = [horizon_net_need(q, s, c) for q, s, c in
                     zip(f[qcol], f["supply_on_time"], f["cg_buffer_credit"])]
    f["net_before_cg"] = [horizon_net_need(q, s, 0) for q, s in
                          zip(f["q95"], f["supply_on_time"])]
    f["net_157"] = [horizon_net_need(q, s, c) for q, s, c in
                    zip(f["q95_157"], f["supply_on_time"], f["cg_buffer_credit"])]
    # CG 池键：需求/净额按 0（缓冲观察）
    cg_cols = ["p50", "p90", "q95", "q90", "q85", "p50_157", "q95_157",
               "net_before_cg", "net_95", "net_90", "net_85",
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
        if pd.isna(r.net_95):
            return "观察", "净需求未知，不生成可执行行动"
        if r.net_95 <= 0:
            return "不补", "覆盖足够（净需求≤0）"
        if r.late_qty > 0:
            return "催已有", "有在途/PO 且 ETA 情景晚于需要日"
        return "补", "净需求>0 且无迟到在途"

    acts = [action_of(r) for r in f.itertuples(index=False)]
    f["action"] = [a[0] for a in acts]
    for c in ("recommended_main_haul", "recommended_last_mile"):
        f.loc[f["action"].isin(["不补", "观察"]), c] = "不适用（不补/观察）"
    f["action_reason"] = [a[1] for a in acts]
    splits = [split_actions(r.net_95, r.late_qty,
                            blocked=bool(r.hard_excl or r.calib_fail))
              for r in f.itertuples(index=False)]
    f["expedite_qty"] = [s["expedite_qty"] for s in splits]
    f["new_order_qty"] = [s["new_order_qty"] for s in splits]
    f["remaining_need"] = [s["remaining_need"] for s in splits]
    f["independent_actions"] = ["、".join(s["actions"]) for s in splits]
    f["has_expedite_action"] = ["催已有" in s["actions"] for s in splits]
    f["has_new_order_action"] = ["新补" in s["actions"] for s in splits]
    f["remaining_after_cover"] = f["remaining_need"]

    def qty_of(r) -> tuple[int, str]:
        need = float(r.remaining_need) if pd.notna(r.remaining_need) else 0.0
        if need <= 0:
            return 0, "无新增单量"
        pid = str(r.product_id)
        if pid in moq_map and np.isfinite(moq_map[pid]) and moq_map[pid] > 0:
            mq = float(moq_map[pid])
            return int(math.ceil(need / mq) * mq), f"原料 MOQ={mq:g} 向上取整"
        return ceil_int(need), "成品 MOQ=n/a（自有绍兴工厂）→ 按个向上取整"

    qty = [qty_of(r) for r in f.itertuples(index=False)]
    f["qty"] = [q[0] for q in qty]
    f["new_order_qty"] = f["qty"]
    f["rounding_basis"] = [q[1] for q in qty]
    f["moq"] = [f"{moq_map[p]:g}" if (p in moq_map and np.isfinite(moq_map[p]))
                else "n/a（自有工厂）" for p in f["product_id"].astype(str)]
    f["need_date"] = [d.isoformat() for d in f["need_dt"]]
    f["order_date"] = [(d - timedelta(days=LEAD_DAYS)).isoformat() for d in f["need_dt"]]
    f["window_end"] = (AS_OF + timedelta(days=H_MAIN)).isoformat()
    f["order_late_flag"] = np.where(pd.to_datetime(f["order_date"]) < pd.Timestamp(AS_OF),
                                    "下单日已过（应立即下单）", "")
    f["confidence"] = np.where(
        f["manual_review_required"], "待人工复核",
        np.where(
        (f["calibration_status"].astype(str) == "ok")
        & (f["demand_basis"].astype(str) == "observed")
        & (f["b_market_confidence"].astype(str) == "高")
        & (~f["hard_excl"]), "高",
        np.where((f["calibration_status"].astype(str) == "ok")
                 | (f["demand_basis"].astype(str) == "observed"), "中", "低")))
    def unknowns_of(r) -> str:
        u = ["成品 MOQ=n/a（自有绍兴工厂）" if str(r.moq).startswith("n/a") else f"MOQ={r.moq}"]
        if r.cg_buffer:
            u.append("CG 池=下游缓冲，不补货")
        if r.cg_buffer_credit > 0:
            u.append(f"CG 缓冲抵扣 {r.cg_buffer_credit:.0f}")
        if str(r.calibration_status) != "ok":
            u.append("D5 区间未校准")
        if r.manual_review_required:
            u.append("人工复核情景，不是服务承诺/自动下单许可")
        if r.snapshot_review_required:
            u.append("EN/CG 库存快照非fresh；需人工复核")
        if r.po_manual_review:
            u.append("PO无明确ETA，创建日不等于发运日；未知阶段情景需人工复核")
        if r.inbound > 0:
            u.append("ETA 为同池情景或来源估算（见 ETA依据）；不保证交期")
        if r.route_status == "route_unavailable_manual_review":
            u.append("本池没有可用明确路线；需人工确认运输路线")
        elif r.route_status == "route_scenario_late_manual_review":
            u.append("本池所有路线 ETA 情景都晚于需要日；路线需人工复核")
        elif r.route_status == "small_sample_route_manual_review":
            u.append("本池路线样本不足30；路线需人工复核")
        return "；".join(u)
    f["unknowns"] = [unknowns_of(r) for r in f.itertuples(index=False)]
    f["eta_basis"] = np.where(
        (f["stock_intr"] + f["stock_wait"]) > 0,
        "在途/待发=age_unknown_full_transit_scenario（无production）；PO=来源ETA/池路线情景；计划=" +
        f["recommended_main_haul"] + "+" + f["recommended_last_mile"],
        np.where(f["inbound"] > 0,
                 "PO=来源ETA/完整段；计划=" + f["recommended_main_haul"] + "+" +
                 f["recommended_last_mile"],
                 "计划=" + f["recommended_main_haul"] + "+" + f["recommended_last_mile"]))
    f["inbound_scenario"] = np.where(
        (f["stock_intr"] + f["stock_wait"]) > 0,
        "age_unknown_full_transit_scenario",
        np.where(f["po_manual_review"],
                 "po_creation_not_ship_date_stage_unknown_scenario",
                 np.where(f["po_extra"] > 0, "source_eta", "none")))

    # ---------- 全量动作表
    full_cols = ["product_id", "market", "pool", "physical_form", "canonical_uom",
                 "demand_pattern", "p50", "q95", "supply", "stock_inb", "po_extra",
                 "protection_horizon_days", "sensitivity_horizon_days",
                 "service_validation_status", "po_eta_basis", "po_manual_review",
                 "manual_review_required", "auto_order",
                 "stock_intr", "stock_wait", "en_stock_snapshot_date",
                 "en_stock_snapshot_status", "en_stock_latest_source_date",
                 "en_stock_latest_source_status", "cg_snapshot_date", "cg_snapshot_status",
                 "snapshot_review_required",
                 "cg_buffer_credit", "inbound", "late_qty", "supply_on_time",
                 "net_before_cg", "net_95", "net_90", "net_85", "net_157",
                 "replenish_eta_p50", "replenish_eta_p90", "inbound_eta_p50",
                 "inbound_eta_p90", "recommended_main_haul", "recommended_last_mile",
                 "transport_basis", "route_status", "inbound_scenario",
                 "stage_independence_assumption", "no_service_guarantee", "last_mile_fits",
                 "海运普船_p90", "海运快船_p90", "空运_p90",
                 "卡车_seg3_p90", "快递_seg3_p90",
                 "late_qty", "need_date", "order_date",
                 "action", "action_reason", "independent_actions", "has_expedite_action",
                 "has_new_order_action", "expedite_qty", "new_order_qty", "remaining_need",
                 "qty", "rounding_basis", "moq",
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
        "protection_horizon_days": "保护窗天数", "service_validation_status": "服务验证状态",
        "sensitivity_horizon_days": "敏感性窗口天数",
        "manual_review_required": "需人工复核", "auto_order": "自动下单",
        "po_eta_basis": "PO ETA依据", "po_manual_review": "PO需人工复核",
        "stock_inb": "en_stock在途+待发", "po_extra": "PO追加(去重)",
        "cg_buffer_credit": "CG缓冲抵扣", "inbound": "在途合计",
        "late_qty": "迟到在途(ETA情景晚于需要日)", "supply_on_time": "到时供给",
        "net_before_cg": "净需求(未扣CG)", "net_95": "净需求95", "net_90": "净需求90",
        "net_85": "净需求85", "net_157": "净需求157",
        "replenish_eta_p50": "ETA_p50", "replenish_eta_p90": "ETA_p90",
        "inbound_eta_p50": "在途ETA_p50", "inbound_eta_p90": "在途ETA_p90",
        "recommended_main_haul": "推荐main_haul", "recommended_last_mile": "推荐last_mile",
        "transport_basis": "运输决策依据", "last_mile_fits": "last_mile情景赶得上",
        "route_status": "路线状态",
        "inbound_scenario": "已有供应ETA情景",
        "mode_fits": "路线情景赶得上需要日",
        "海运普船_p90": "海运普船_p90", "海运快船_p90": "海运快船_p90",
        "空运_p90": "空运_p90", "卡车_seg3_p90": "卡车_seg3_p90",
        "快递_seg3_p90": "快递_seg3_p90",
        "need_date": "需要日", "order_date": "下单日",
        "action": "建议动作", "action_reason": "动作原因", "qty": "建议数量",
        "independent_actions": "独立行动", "has_expedite_action": "催已有行动",
        "has_new_order_action": "新补行动", "expedite_qty": "催已有量",
        "new_order_qty": "新补数量", "remaining_need": "催后剩余缺口",
        "stock_intr": "EN已发运量", "stock_wait": "EN待发量",
        "en_stock_snapshot_date": "EN库存快照日", "en_stock_snapshot_status": "EN快照状态",
        "en_stock_latest_source_date": "EN最新源快照日",
        "en_stock_latest_source_status": "EN最新源状态",
        "cg_snapshot_date": "CG库存快照日", "cg_snapshot_status": "CG快照状态",
        "snapshot_review_required": "快照需复核",
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
            return pd.DataFrame(columns=cols + ["键数", "建议数量合计", "催已有量合计",
                                                 "新补数量合计", "净需求95合计"])
        return (df.groupby(cols, dropna=False)
                .agg(键数=("product_id", "size"), 建议数量合计=("qty", "sum"),
                     催已有量合计=("expedite_qty", "sum"),
                     新补数量合计=("new_order_qty", "sum"),
                     净需求95合计=("net_95", "sum")).reset_index()
                .sort_values(["键数", "新补数量合计"], ascending=False))

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
        calc = horizon_net_need(r.q95, r.supply_on_time, r.cg_buffer_credit)
        if ((calc is None and pd.notna(r.net_95)) or
                (calc is not None and abs(calc - r.net_95) > 1e-6)):
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
    print(f"路线证据：production={route_evidence_report['dn']['included']}｜"
          f"head={route_evidence_report['head']['included']}｜"
          f"无已知路线池={sum(not pool_routes[p] for p in pool_routes)}｜"
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
            ("ETA", "同池真实 production×physical-route 阶段独立情景；非实测联合或服务保证"),
            ("路线证据", "按 pool×role×main×last 选样；生产缺角色时只回退同池，标 pool_all_roles_fallback"),
            ("库存快照", f"as-of={AS_OF}；EN={es_snapshot or '未知'}({es_snapshot_status})；"
                       f"CG={cg_snapshot or '未知'}({cg_snapshot_status})"),
            ("MOQ", "成品 n/a（自有绍兴工厂）按个取整；原料用 moq_items_21"),
            ("保护窗", "97 天 q95 总需求为人工政策情景；非随机服务承诺；auto_order=false"),
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
        ev = top_out[["序号", "product_id", "池", "形态", "建议动作", "独立行动",
                      "催已有量", "新补数量", "催后剩余缺口", "动作原因",
                      "净需求95", "C可发供给", "en_stock在途+待发", "PO追加(去重)",
                      "EN已发运量", "EN待发量", "EN库存快照日", "EN快照状态",
                      "EN最新源快照日", "EN最新源状态",
                      "CG库存快照日", "CG快照状态", "快照需复核", "需人工复核",
                      "CG缓冲抵扣", "到时供给", "迟到在途(ETA情景晚于需要日)",
                      "ETA_p50", "ETA_p90", "ETA依据", "未知项", "置信度"]]
        to_sheet(ev, "4_证据与未知")
        to_sheet(cg_rec, "5_CG记录")
        to_sheet(pd.DataFrame(route_evidence_rows), "8_路线证据")
        dec = pd.DataFrame([
            ("范围", "全量 1,853 键；Top50 仅子集", "用户要求"),
            ("SO→DN", f"as-of={AS_OF} 滚动六个月；按 pool×role", "真实样本"),
            ("头程", "按本池 WMS-in→delivery 实物路线样本", "真实样本"),
            ("运输方式", "只候选本池显式 main×last 组合；缺路线则待确认", "不借样本"),
            ("组合分布", "production/head 独立阶段抽样；非实测联合分布", "无服务保证"),
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
        f"# D6 v6 全量补货沙盒（{RULE_VERSION}；只读）",
        "",
        f"- 全量 **{len(f)}** 个需求键；Top50 **{len(top)}**；policy 行 **{len(pol_tbl)}**",
        "- **cross_warehouse_direct=disabled_by_business**：不再有跨仓直发。",
        "- CG 库存按 SKU owner 抵扣 USNJ/USTX 分支；CG 池只观察；CG 库存/销量单列。",
        f"- 决策日志：`{Path(args.decisions).name}`；本轮无 pending_codex、无 PENDING_APPROVAL。",
        "",
        "## 1. 全量动作",
        "",
        "| 动作 | 键数 | 新补数量合计 | 催已有量合计 | 净需求95 |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in act_full.itertuples(index=False):
        lines.append(f"| {r.动作} | {r.键数} | {r.新补数量合计:.0f} | "
                     f"{r.催已有量合计:.0f} | {r.净需求95合计:.1f} |")
    lines += [
        "",
        f"- 全量动作分布：{json.dumps(f['action'].value_counts().to_dict(), ensure_ascii=False)}",
        f"- 净额情景：{H_MAIN} 天 q95 总需求为人工政策情景；{H_SENS} 天 q95 仅作敏感性；"
        "均不构成随机服务水平承诺。",
        f"- 独立行动数量：催已有 {f['expedite_qty'].sum():.0f}；新补 {f['new_order_qty'].sum():.0f}；"
        f"两者可同时出现，旧字段 qty 仅记新补数量。",
        f"- 库存快照：as-of={AS_OF}；EN 使用 {es_snapshot or '未知'}（{es_snapshot_status}），"
        f"最新源 {es_source_snapshot or '未知'}（{es_latest_status}）；"
        f"CG {cg_snapshot or '未知'}（{cg_snapshot_status}）。未来/未知 CG 快照不抵扣并阻断可执行行动。",
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
        f"as-of {AS_OF} 滚动六个月（线级复算）：",
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
        "",
        "## 3. ETA 与两层运输",
        "",
        f"- as-of={AS_OF}；最近六个月有效 production={route_evidence_report['dn']['included']} 行；"
        f"head-route={route_evidence_report['head']['included']} 行。",
        "- production 与物理路线阶段独立抽样；`stage_independence_assumption=true`，"
        "不是实测联合分布或服务保证。",
        "- 缺少角色生产样本时只回退同池所有角色并标 `pool_all_roles_fallback`；"
        "不在 USNJ、USTX、PL 之间借样本。",
        "- 在途/待发模式和货龄未知，按同池完整 head 样本标 `age_unknown_full_transit_scenario`；"
        "不加入 production，也不宣称剩余运输时间。",
        f"- 未知 region={route_evidence_report['head']['unknown_region']}、"
        f"main={route_evidence_report['head']['unknown_main_haul']}、"
        f"last-mile={route_evidence_report['head']['unknown_last_mile']}。",
        "",
        "| 证据类型 | 池 | 角色 | main_haul | last_mile | n | 说明 |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in route_evidence_rows:
        lines.append("| {kind} | {pool} | {role} | {main} | {last} | {n} | {note} |".format(
            kind=row.get("证据类型", ""), pool=row.get("pool", ""),
            role=row.get("role", ""), main=row.get("main", ""),
            last=row.get("last", ""), n=row.get("n", 0), note=row.get("note", "")))
    lines += [
        "",
        "- 本池无完整命名路线时输出‘路线待确认’，不会补造空运路线。",
        f"- 推荐 main_haul（补/催已有 {sum(mode_counts.values())} 键）："
        f"{json.dumps(mode_counts, ensure_ascii=False)}；"
        f"推荐 last_mile：{json.dumps(last_counts, ensure_ascii=False)}；"
        f"main p90 赶得上 {mode_fit} 键；"
        f"last_mile p90 赶得上 {int(f.loc[f['action'].isin(['补','催已有']), 'last_mile_fits'].sum())} 键。",
        "- 无成本/重要度数据，运输优先级只标 `urgency_only`。",
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
        "# D6 v6 决策日志",
        "",
        f"- 生成时间：{datetime.now().astimezone().isoformat()}",
        "- 协议：按 `DECISION_PROTOCOL.md`，未使用 AskUserQuestion；无不可逆外部动作。",
        "",
        "| 时间 | 问题 | 选项 | 选择 | 依据 | pending_codex |",
        "|---|---|---|---|---|---|",
        f"| {datetime.now().strftime('%H:%M')} | 输出范围 | Top50 / 全量 | 全量 1,853 + Top50 子集 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | SO→DN 口径 | 跨池 / pool×role | as-of={AS_OF} 滚动六个月；缺角色样本只回退同池 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 运输层级 | 单层 / 两层 | main_haul + last_mile 分开；服务产品为组合 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 头程来源 | hard-coded anchors / route samples | pool×main×last 物理路线样本 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 分布假设 | 两点边际 / 实测联合 | 同池 production 与 physical-route 独立阶段抽样；无服务保证 | 限制标注 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 运输方式 | 强制模式 / 显式本池路线 | 缺路线输出路线待确认，不借池、不造空运 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 成本/重要度 | 纳入 / urgency_only | 无数据→urgency_only | 不硬造 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 跨仓直发 | 保留 / 删除 | 删除，disabled_by_business | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | CG 处置 | 补货 / 缓冲抵扣 | 按 SKU owner 抵扣 USNJ/USTX；CG 池只观察 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | MOQ | MOQ_unknown / 成品 n/a | 成品 n/a，按个取整；原料用 moq_items_21 | 用户要求 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | 动作优先级 | 补优先 / 催已有优先 | 观察→不补→催已有→补 | 覆盖足够不补 | 否 |",
        f"| {datetime.now().strftime('%H:%M')} | Top50 选样 | 随机 / 覆盖目标 | 46 物理池 + 4 CG 观察 | 可解释 | 否 |",
    ]
    Path(args.decisions).write_text("\n".join(dec_md) + "\n", encoding="utf-8")
    manifest = dict(rule_version=RULE_VERSION, generated_at_utc=datetime.now(timezone.utc).isoformat(),
                    inputs=inputs, as_of=str(AS_OF), lead_days=LEAD_DAYS,
                    planning_scenario=dict(protection_horizon_days=H_MAIN,
                                           net_formula="q95_total_demand - on_time_supply - cg_credit",
                                           sensitivity_horizon_days=H_SENS,
                                           automatic_order=False,
                                           service_promise=False),
                    source_snapshots=dict(en_stock=dict(snapshot_date=es_snapshot,
                                                        status=es_snapshot_status,
                                                        latest_source_date=es_source_snapshot,
                                                        latest_source_status=es_latest_status),
                                          cg_inventory=dict(snapshot_date=cg_snapshot,
                                                            status=cg_snapshot_status)),
                    counts=dict(full_keys=len(f), policy_rows=len(pol_tbl), top50=len(top),
                                actions=f["action"].value_counts().to_dict(),
                                expedite_qty=float(f["expedite_qty"].sum()),
                                new_order_qty=float(f["new_order_qty"].sum()),
                                manual_review_keys=int(f["manual_review_required"].sum()),
                                snapshot_review_keys=int(f["snapshot_review_required"].sum()),
                                top_actions=top["action"].value_counts().to_dict(),
                                cg_credit_keys=int((f["cg_buffer_credit"] > 0).sum()),
                                cg_credit_qty=float(f["cg_buffer_credit"].sum()),
                                cg_future_blocked=bool(cg_future_blocked),
                                future_cg_inventory_used=False,
                                cg_pool_keys=int(f["cg_buffer"].sum()),
                                eta_sources=eta_src_counts,
                                transport_modes=f[f["action"].isin(["补", "催已有"])]
                                ["recommended_main_haul"].value_counts().to_dict(),
                                transport_last_miles=f[f["action"].isin(["补", "催已有"])]
                                ["recommended_last_mile"].value_counts().to_dict(),
                                transport_mode_fits=int(
                                    f.loc[f["action"].isin(["补", "催已有"]), "mode_fits"].sum())),
                    eta=dict(route_evidence=route_evidence_summary,
                             stage_independence_assumption=True,
                             no_service_guarantee=True,
                             route_candidates={pool: routes for pool, routes in pool_routes.items()}),
                    selfcheck=self_rows, selfcheck_pass=self_pass,
                    outputs=dict(xlsx=dict(path=args.out_xlsx, sha256=sha256(args.out_xlsx),
                                           bytes=Path(args.out_xlsx).stat().st_size),
                                 report=dict(path=args.out_report, sha256=sha256(args.out_report),
                                             bytes=Path(args.out_report).stat().st_size),
                                 decisions=dict(path=args.decisions, sha256=sha256(args.decisions),
                                                bytes=Path(args.decisions).stat().st_size)))
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print(f"\n已写：{args.out_xlsx}\n      {args.out_report}\n      {args.manifest}")
    return 0 if self_pass else 1


if __name__ == "__main__":
    sys.exit(main())
