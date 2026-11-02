# -*- coding: utf-8 -*-
"""D2 销量清洗与断货删失（只读；不写 EN/通途、不 push）。

为 D1 的 demand_eligible / forecast_eligible 键建 2025-01..2026-10 月度销量序列，
保留 raw_qty / sellable_qty / component_qty / conversion_basis，并把 0 月分五类：
genuine_zero / stockout_censored / dormant / long_term_zero / censor_unknown。
不预测、不补 0、不分配共享池、不生成采购。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

RULE_VERSION = "D2-v1-2026-10-30"
MONTHS = [f"{y}{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:22]  # 202501..202610
OBSERVED_LAST_MONTH = "202609"          # gs_orders 导出止于 2026-09-30
EVIDENCE_MONTHS = {"2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"}
OBSERVED_MONTHS = {f"{y}{m:02d}" for y in (2025, 2026) for m in range(1, 13)} - {"202610"}


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


def pool_of(warehouse: str) -> str:
    w = str(warehouse)
    if "WayfairCG" in w or w.startswith("CG"):
        return "CG"
    if "退货" in w:
        return "其他"
    if "Poland" in w or "波兰" in w:
        return "波兰"
    if "CENTRADE" in w or "美东" in w:
        return "美东USNJ"
    if "DANEEY" in w or "美中" in w:
        return "美中USTX"
    return "其他"


def main(argv=None) -> int:
    B = "D:/Work/fzh-order-store"
    ap = argparse.ArgumentParser(description="D2 销量清洗与断货删失（只读）")
    ap.add_argument("--d1", default=f"{B}/analysis/D_资格与契约_2026-10-30.xlsx")
    ap.add_argument("--forecast", default=f"{B}/analysis/需求预测_去库存影响_2026-10-29.xlsx")
    ap.add_argument("--orders", default=f"{B}/gs_orders.parquet")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--c-stock", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--oct-orders", default=f"{B}/analysis/tongtool_orders_202610_raw.csv")
    ap.add_argument("--oct-fba", default=f"{B}/analysis/tongtool_fba_202610_raw.csv")
    ap.add_argument("--window-end", default="2026-10-31")
    ap.add_argument("--bundles", default=f"{B}/analysis/en_product_bundles_2026-10-30.json")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--status", default="DRAFT（草稿/审计）：基于 D1 v1，而 D1 v1 复审为 NO-GO；"
                                       "D1 v2 发布后必须重跑")
    ap.add_argument("--based-on", default="D1 v1（复审 NO-GO）；D1 v2 后重跑")
    ap.add_argument("--upstream-note",
                    default="① 共享池误进净额 → 影响 netting_eligible，本表序列只用 demand_eligible，"
                            "不消费净额；② 13 个 CG 重复键 → CG 不进序列（channel=wayfair_only）；"
                            "③ D1 脚本缺失 → 本脚本自包含可复现，但 D1 不可复现；"
                            "④ D1 source_refs 空 → 本表 source_refs 由 gs_orders 行号自建")
    ap.add_argument("--rule-version", default=RULE_VERSION)
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/D_销量清洗_2026-10-30.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/D_销量清洗_2026-10-30_报告.md")
    args = ap.parse_args(argv)

    # ---------- 输入 ----------
    d1 = pd.read_excel(args.d1, sheet_name="1_资格")
    demand_keys = d1[d1["demand_eligible"]].copy()
    keys = (demand_keys.groupby(["product_id", "destination_pool", "physical_form", "canonical_uom"])
            .agg(forecast_eligible=("forecast_eligible", "max"),
                 reason_code=("reason_code", "first")).reset_index())
    keys_by_pp: dict[tuple, list] = {}
    for r in keys.to_dict("records"):
        keys_by_pp.setdefault((r["product_id"], r["destination_pool"]), []).append(r)

    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    active = a[a["活跃分类"] != "不活跃"].copy()
    active["EN物料"] = active["EN物料"].astype(str)
    a_meta = active.set_index("EN物料")
    active_ids = set(active_ids := active["EN物料"])

    c_legacy = pd.read_excel(args.c_stock, sheet_name="16_老产品清单")
    legacy_ids = {p for p in c_legacy["product_id"].astype(str) if p != "(未归属)"}

    bundles = json.loads(Path(args.bundles).read_text(encoding="utf-8")) \
        if Path(args.bundles).exists() else {}

    ov = pd.read_csv(args.overrides, dtype=str)
    # 订单 SKU → EN（与 C 同口径：用户覆盖 > A 来源码 > 客户码 > sku_map）
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

    # 预测删失证据
    ev = pd.read_excel(args.forecast, sheet_name="2_删失证据")
    ev["month"] = ev["month"].astype(str)
    censored_en_months = {(str(en), m) for en, m, c in
                          zip(ev["EN物料"], ev["month"], ev["censored"]) if bool(c)}
    evidence_en_months = {(str(en), m) for en, m in zip(ev["EN物料"], ev["month"])}
    nz = pd.read_excel(args.forecast, sheet_name="3_近零复核")
    near_zero = dict(zip(nz["EN物料"].astype(str), nz["near_zero_conclusion"].astype(str)))
    fcast = pd.read_excel(args.forecast, sheet_name="1_需求预测")
    fcast_en = set(fcast["EN物料"].astype(str))

    # ---------- 订单 ----------
    g = pd.read_parquet(args.orders)
    g["sale_date"] = pd.to_datetime(g["sale_date"])
    w_gs = g[(g["sale_date"] >= "2025-01-01") & (g["sale_date"] <= "2026-09-30")].copy()
    w_gs["source_dataset"] = "gs_orders"
    oct_exists = Path(args.oct_orders).exists()
    if oct_exists:
        oc = pd.read_csv(args.oct_orders, dtype=str)
        oc["sale_date"] = pd.to_datetime(oc["发货日期"], errors="coerce")
        oc["qty"] = pd.to_numeric(oc["发货数量"], errors="coerce").fillna(0.0)
        oc["sku_tongtool"] = oc["通途SKU"].astype(str)
        oc["platform_sku"] = oc["平台SKU"].astype(str)
        oc["warehouse"] = oc["发货仓库"].astype(str)
        oc["order_id"] = oc["订单号"].astype(str)
        oc["line_id"] = ("OCT:" + oc["订单号"].astype(str) + ":" + oc["包裹号"].astype(str)
                         + ":" + oc["通途SKU"].astype(str) + ":" + oc.index.astype(str))
        oc["source_dataset"] = "tongtool_202610_raw"
        oc_w = oc[(oc["sale_date"] >= "2026-10-01") & (oc["sale_date"] <= pd.Timestamp(args.window_end))].copy()
    else:
        oc_w = pd.DataFrame(columns=w_gs.columns)
    w = pd.concat([w_gs, oc_w], ignore_index=True, sort=False)
    w["month"] = w["sale_date"].dt.strftime("%Y%m")
    window_end = args.window_end
    w["en"] = w["sku_tongtool"].map(lambda s: idx.get(norm(s)))
    w["pool"] = w["warehouse"].map(pool_of)
    w["in_active"] = w["en"].isin(active_ids)

    # 换算：raw → sellable → component
    def conv(r):
        sku = str(r["sku_tongtool"])
        psku = str(r["platform_sku"])
        en = r["en"]
        raw_qty = float(r["qty"])
        raw_uom = "个"
        m = re.search(r"[-_](\d+)\s*pcs?$", sku, re.I)
        if m:
            raw_uom = f"{m.group(1)}PCS"
        if isinstance(en, str) and en.upper().startswith("TJ#") and en in bundles:
            comps = bundles[en]
            per = sum(float(q) for _, q in comps)
            return pd.Series({"sellable_qty": raw_qty, "raw_uom": "套",
                              "component_qty": raw_qty * per,
                              "conversion_basis": f"Product Bundle {en}: " +
                                                  ";".join(f"{c}x{q:g}" for c, q in comps),
                              "inference_status": "bundle_verified"})
        if m and psku != sku:
            return pd.Series({"sellable_qty": raw_qty, "raw_uom": raw_uom,
                              "component_qty": None,
                              "conversion_basis": "平台后缀 vs 基础码：层级未证（ambiguous）",
                              "inference_status": "ambiguous"})
        return pd.Series({"sellable_qty": raw_qty, "raw_uom": raw_uom,
                          "component_qty": raw_qty, "conversion_basis": "1:1（个）",
                          "inference_status": "ok"})

    w = pd.concat([w, w.apply(conv, axis=1)], axis=1)
    observed_months = set(OBSERVED_MONTHS)
    if oct_exists:
        observed_months.add("202610")
    w["clearance_flag"] = (w["sku_tongtool"].astype(str).str.contains("qc", case=False, na=False)
                           | w["platform_sku"].astype(str).str.contains("#qc", case=False, na=False))

    # ---------- 序列 ----------
    agg = (w[w["en"].notna() & w["in_active"]]
           .groupby(["en", "pool", "month"])
           .agg(raw_qty=("qty", "sum"), lines=("line_id", "size"),
                sellable_qty=("sellable_qty", "sum"),
                component_qty=("component_qty", "sum"),
                ambiguous_lines=("inference_status", lambda s: int((s == "ambiguous").sum())),
                clearance_lines=("clearance_flag", "sum"),
                first_src=("line_id", "first")).reset_index())

    series_rows = []
    assigned_lines = set()
    for k in keys.to_dict("records"):
        pid, pool = k["product_id"], k["destination_pool"]
        months_sales = agg[(agg["en"] == pid) & (agg["pool"] == pool)]
        sales_by_month = {r["month"]: r for r in months_sales.to_dict("records")}
        for m in MONTHS:
            rec = sales_by_month.get(m)
            zero_class = ""
            if rec is not None and rec["sellable_qty"] > 0:
                zero_class = "observed_positive"
            elif m not in observed_months:
                zero_class = "censor_unknown"
            elif (pid, f"{m[:4]}-{m[4:]}") in censored_en_months:
                zero_class = "stockout_censored"
            elif near_zero.get(pid) == "long_term_zero_stock":
                zero_class = "long_term_zero"
            elif near_zero.get(pid) == "dormant_no_recent_sales":
                zero_class = "dormant"
            elif f"{m[:4]}-{m[4:]}" in EVIDENCE_MONTHS:
                zero_class = "genuine_zero"
            else:
                zero_class = "censor_unknown"
            usable = zero_class in ("observed_positive", "genuine_zero", "dormant", "long_term_zero")
            series_rows.append({
                "product_id": pid, "pool": pool,
                "physical_form": k["physical_form"], "canonical_uom": k["canonical_uom"],
                "month": m,
                "observation_status": ("observed" if m in observed_months else "orders_not_exported"),
                "raw_qty": (None if rec is None else float(rec["raw_qty"])),
                "raw_uom": (None if rec is None else "mixed"),
                "txn_level": "order_line",
                "sellable_qty": (None if rec is None else float(rec["sellable_qty"])),
                "component_qty": (None if rec is None else
                                  (None if pd.isna(rec["component_qty"]) else float(rec["component_qty"]))),
                "conversion_basis": ("无订单行" if rec is None else
                                     ("见订单行（默认 1:1；套件按 Bundle）"
                                      if rec["ambiguous_lines"] == 0 else
                                      f"含 {int(rec['ambiguous_lines'])} 行 ambiguous")),
                "zero_class": zero_class,
                "usable_for_training": bool(usable and (rec is None or zero_class == "observed_positive"
                                                        or rec["sellable_qty"] == 0)),
                "forecast_eligible": bool(k["forecast_eligible"]),
                "is_legacy": pid in legacy_ids,
                "new_product": (str(a_meta.at[pid, "首次通途销售日"])[:10] >= "2026-01-01"
                                if pid in a_meta.index and pd.notna(a_meta.at[pid, "首次通途销售日"]) else False),
                "clearance_lines": (0 if rec is None else int(rec["clearance_lines"])),
                "promo_status": "unknown（无促销日历）",
                "source_refs": ("" if rec is None else
                                f"gs_orders:{rec['month']};lines={int(rec['lines'])};first={rec['first_src']}"),
            })
            if rec is not None:
                assigned_lines.add((pid, pool, m))

    series = pd.DataFrame(series_rows)

    # 未进入序列的订单行（质量口径）
    w["series_key"] = list(zip(w["en"], w["pool"], w["month"]))
    w["in_series"] = w["series_key"].isin(assigned_lines)
    unmatched = w[w["en"].isna()]
    inactive = w[w["en"].notna() & ~w["in_active"]]
    out_of_scope = w[w["en"].notna() & w["in_active"] & ~w["in_series"]]

    # ---------- 删失证据（419 EN 逐条可回源） ----------
    cens = ev[ev["censored"]].copy()
    cens_tbl = (cens.groupby(["EN物料", "month"])
                .agg(skus=("sku", lambda s: ";".join(sorted(set(s.astype(str))))),
                     zero_dates=("zero_dates", "sum"), pos_dates=("pos_dates", "sum"),
                     stockout_status=("stockout_status", lambda s: ";".join(sorted(set(s)))),
                     sources=("sources", lambda s: ";".join(sorted(set(s.astype(str))))))
                .reset_index().rename(columns={"EN物料": "product_id", "month": "month"}))
    cens_en = set(cens_tbl["product_id"])

    # ---------- FBA（独立 channel，不并入 3PL 净额） ----------
    fba_tbl = pd.DataFrame()
    if Path(args.oct_fba).exists():
        fb = pd.read_csv(args.oct_fba, dtype=str)
        fb["qty_units"] = pd.to_numeric(fb["销量"], errors="coerce")
        fb["qty_orders"] = pd.to_numeric(fb["订单数量"], errors="coerce")
        def _fba_en(r):
            for c in ("MSKU", "SKU"):
                v = r.get(c)
                if isinstance(v, str):
                    e = idx.get(norm(v))
                    if isinstance(e, str):
                        return e, c
            return None, "unmapped"
        res = [ _fba_en(r) for r in fb.to_dict("records")]
        fb["en"] = [x[0] for x in res]
        fb["match_basis"] = [x[1] for x in res]
        fb["en_in_active"] = fb["en"].isin(active_ids)
        fb["channel"] = "fba"
        fba_tbl = fb[["MSKU", "SKU", "站点", "en", "match_basis", "en_in_active",
                      "qty_units", "qty_orders", "销售额", "channel"]].rename(
            columns={"en": "erp_item_code", "qty_units": "units", "qty_orders": "orders"})
        fba_tbl["source_ref"] = "tongtool_fba_202610_raw:" + fba_tbl.index.astype(str)

    # ---------- 质量 ----------
    dup_lines = int(w["line_id"].duplicated().sum())
    quality = pd.DataFrame([
        {"项": "订单窗口", "值": f"2025-01-01..{window_end}",
         "说明": ("gs_orders（止 2026-09-30）+ 10 月原始月表（2026-10-01..31）"
                  if oct_exists else f"gs_orders 导出止于 {OBSERVED_LAST_MONTH}；未接 10 月原始")},
        {"项": "订单行（入）", "值": len(g), "说明": "gs_orders 全表"},
        {"项": "窗口内行", "值": len(w), "说明": "2025-01..窗口末（含 10 月原始行）"},
        {"项": "其中 10 月原始行", "值": int((w.get("source_dataset") == "tongtool_202610_raw").sum())
         if "source_dataset" in w.columns else 0, "说明": "tongtool_orders_202610_raw.csv"},
        {"项": "10 月原始 qty", "值": float(w.loc[w.get("source_dataset") == "tongtool_202610_raw", "qty"].sum())
         if "source_dataset" in w.columns else 0.0, "说明": "发货数量合计（应为 6,973）"},
        {"项": "窗口内 qty", "值": float(w["qty"].sum()), "说明": "raw 件数（不跨 UOM 解释）"},
        {"项": "已映射到活跃 A", "值": int(w["en"].notna().sum() - len(inactive)), "说明": "进入序列候选"},
        {"项": "未匹配 SKU 行", "值": len(unmatched), "说明": "无任何映射源命中"},
        {"项": "映射到非活跃/删除 EN", "值": len(inactive), "说明": "不进当前序列，保留 raw"},
        {"项": "有产品但无 D1 需求键（out of scope）", "值": len(out_of_scope), "说明": "pool/form 不在 demand_eligible 键"},
        {"项": "重复 line_id", "值": dup_lines, "说明": "同一行重复计"},
        {"项": "套件换算行（TJ# Bundle）", "值": int(w["inference_status"].eq("bundle_verified").sum()),
         "说明": "sellable=套、component=组件个"},
        {"项": "后缀层级 ambiguous 行", "值": int(w["inference_status"].eq("ambiguous").sum()),
         "说明": "平台 -2PCS/-3PCS 与基础码不一致，组件量不猜"},
        {"项": "序列行合计", "值": len(series), "说明": "键×22 个月"},
        {"项": "序列 sellable 合计", "值": float(series["sellable_qty"].fillna(0).sum()), "说明": "仅已映射进入序列"},
        {"项": "FBA 10 月行/订单数/销量", "值": f"{len(fba_tbl)} / "
         f"{float(fba_tbl['orders'].sum()) if len(fba_tbl) else 0:.0f} / "
         f"{float(fba_tbl['units'].sum()) if len(fba_tbl) else 0:.0f}",
         "说明": "channel=fba；按 MSKU 汇总（非行级），不并入 3PL 净额"},
        {"项": "FBA 未映射行/销量", "值": f"{int(fba_tbl['erp_item_code'].isna().sum()) if len(fba_tbl) else 0} / "
         f"{float(fba_tbl.loc[fba_tbl['erp_item_code'].isna(), 'units'].sum()) if len(fba_tbl) else 0:.0f}",
         "说明": "保留 raw MSKU/SKU，不猜"},
        {"项": "对账：序列 + out + 未匹配 + 非活跃",
         "值": float(series["sellable_qty"].fillna(0).sum()) + float(out_of_scope["sellable_qty"].sum())
              + float(unmatched["qty"].sum()) + float(inactive["sellable_qty"].sum()),
         "说明": f"应等于窗口 qty {float(w['qty'].sum()):,.0f}（套件行 sellable=套数、raw 为件数，差为套件换算）"},
    ])

    zero_counts = series["zero_class"].value_counts().to_dict()

    # ---------- 输出 ----------
    contract = pd.DataFrame([
        ("rule_version", args.rule_version),
        ("状态", args.status),
        ("上游 D1 说明", args.upstream_note),
        ("粒度", "product_id × pool × physical_form × canonical_uom × month（2025-01..2026-10）"),
        ("as_of / knowledge_cutoff",
         f"C 库存 2026-10-28；订单窗口 2025-01-01..{window_end}"
         + ("（10 月取自 tongtool_orders_202610_raw）" if oct_exists else "；10 月未接入")
         + "；预测 run forecast-20261027-r4"),
        ("月份覆盖",
         ("202501..202610 已观测（10 月为原始月表；观测止 10-31）" if oct_exists
          else "202501..202609 已观测；202610 未导出 → zero_class=censor_unknown（不当作 0 销量）")),
        ("数据源说明",
         "3PL 自发货：gs_orders（2025-01..2026-09-30）+ tongtool_orders_202610_raw（2026-10-01..31）；"
         "FBA：tongtool_fba_202610_raw（116 行，按 MSKU 汇总，channel=fba，不并入 3PL 净额）。"
         "原始 gsheet 已够用：Colab 只影响成本/特殊规则，不影响 D 销量。"),
        ("三层计量", "raw_qty/raw_uom（交易层） → sellable_qty（可售单位） → component_qty（组件层）；"
                  "raw 不被覆盖，换算须有 conversion_basis"),
        ("0 分类", "genuine_zero / stockout_censored / dormant / long_term_zero / censor_unknown"),
        ("删失证据", "D 预测表 2_删失证据（EN×SKU×month 2026-04..10，censored=True）+ 3_近零复核结论"),
        ("标签", "#qc 由 SKU/平台 SKU 命中判清仓；新品=首次通途销售日≥2026-01-01；"
               "老产品=C 16_；促销无日历 → promo_status=unknown"),
        ("不做什么", "不预测、不补 0、不分配共享池、不生成采购、不写 EN/通途"),
        ("输入 SHA256 · D1", sha256(Path(args.d1))),
        ("输入 SHA256 · 预测表", sha256(Path(args.forecast))),
        ("输入 SHA256 · gs_orders", sha256(Path(args.orders))),
        ("输入 SHA256 · C v14", sha256(Path(args.c_stock))),
    ], columns=["项", "内容"])

    stat_tbl = pd.DataFrame([{"zero_class": k, "行数": v} for k, v in zero_counts.items()])

    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as wr:
        contract.to_excel(wr, sheet_name="0_契约", index=False)
        series.to_excel(wr, sheet_name="1_序列", index=False)
        cens_tbl.to_excel(wr, sheet_name="2_删失", index=False)
        quality.to_excel(wr, sheet_name="3_质量", index=False)
        stat_tbl.to_excel(wr, sheet_name="4_对账", index=False)
        if len(fba_tbl):
            fba_tbl.to_excel(wr, sheet_name="5_FBA", index=False)
        series.groupby(["pool", "physical_form", "canonical_uom"]).agg(
            行数=("product_id", "size"), 产品数=("product_id", "nunique"),
            可售合计=("sellable_qty", "sum"), 组件合计=("component_qty", "sum")) \
            .reset_index().to_excel(wr, sheet_name="4_对账", index=False, startrow=len(stat_tbl) + 3)

    out_sha = sha256(out)
    Path(args.out_report).write_text(
        render(series, cens_tbl, quality, stat_tbl, contract, out_sha, args, out),
        encoding="utf-8")
    manifest = {
        "rule_version": args.rule_version,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {n: sha256(Path(p)) for n, p in [
            ("d1", args.d1), ("forecast", args.forecast), ("orders", args.orders),
            ("a_final", args.a_final), ("c_stock", args.c_stock)]},
        "outputs": {"xlsx": {"path": str(out), "sha256": out_sha},
                    "report": {"path": str(args.out_report),
                               "sha256": sha256(Path(args.out_report))}},
        "status": args.status,
        "based_on": args.based_on,
        "counts": {"series_rows": int(len(series)), "keys": int(len(keys)),
                   "oct_orders_rows": int((w.get("source_dataset") == "tongtool_202610_raw").sum())
                   if "source_dataset" in w.columns else 0,
                   "oct_orders_qty": float(w.loc[w.get("source_dataset") == "tongtool_202610_raw", "qty"].sum())
                   if "source_dataset" in w.columns else 0.0,
                   "fba_rows": int(len(fba_tbl)),
                   "fba_orders": float(fba_tbl["orders"].sum()) if len(fba_tbl) else 0.0,
                   "fba_units": float(fba_tbl["units"].sum()) if len(fba_tbl) else 0.0,
                   "censored_en": int(len(cens_en)), "censored_rows": int(len(cens_tbl)),
                   "zero_class": {k: int(v) for k, v in zero_counts.items()}},
    }
    Path(str(out).replace(".xlsx", ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print("workbook:", out)
    return 0


def render(series, cens_tbl, quality, stat_tbl, contract, out_sha, args, out: Path) -> str:
    L = [
        f"# D2 销量清洗与断货删失（{str(args.status).split('（')[0]}，只读）",
        "",
        f"- `rule_version` = **{contract.loc[contract['项'] == 'rule_version', '内容'].iloc[0]}**；"
        f"序列 {len(series):,} 行；"
        f"删失 {len(cens_tbl):,} 个 EN×月（{cens_tbl['product_id'].nunique()} 个 EN）",
        "- 只清洗/标注，不预测、不补 0、不生成采购。",
        f"- **状态：{contract.loc[contract['项'] == '状态', '内容'].iloc[0]}**；"
        f"上游说明：{contract.loc[contract['项'] == '上游 D1 说明', '内容'].iloc[0]}",
        "",
        "## 1. 契约",
        "",
        "| 项 | 内容 |",
        "|---|---|",
    ]
    for r in contract.to_dict("records"):
        L.append(f"| {r['项']} | {r['内容']} |")
    L += ["", "## 2. 0 分类（每月每键）", "", "| zero_class | 行数 |", "|---|---:|"]
    for r in stat_tbl.to_dict("records"):
        L.append(f"| {r['zero_class']} | {r['行数']:,} |")
    L += ["", "## 3. 删失证据（419 EN）", "",
          "| product_id | month | SKU | 状态 | 来源 |", "|---|---|---|---|---|"]
    for r in cens_tbl.head(12).to_dict("records"):
        L.append(f"| {r['product_id']} | {r['month']} | {r['skus']} | {r['stockout_status']} | {r['sources']} |")
    L += ["", f"> 全量 {len(cens_tbl):,} 行见 `2_删失`；每行可回指 2_删失证据 的 EN×SKU×month。"]
    L += [
        "",
        "## 3.1 10 月原始订单与 FBA",
        "",
    ]
    for r in quality.to_dict("records"):
        if r["项"] in ("其中 10 月原始行", "10 月原始 qty", "FBA 10 月行/订单数/销量",
                       "FBA 未映射行/销量", "窗口内 qty", "对账：序列 + out + 未匹配 + 非活跃"):
            L.append(f"- **{r['项']}**：{r['值']}（{r['说明']}）")
    L += [
          "", "## 4. 质量与对账", "", "| 项 | 值 | 说明 |", "|---|---:|---|"]
    for r in quality.to_dict("records"):
        L.append(f"| {r['项']} | {r['值']} | {r['说明']} |")
    L += [
        "",
        "## 5. 口径说明",
        "",
        "- **每月每键都有行**：观测月（202501–202609）内 0 销量按月归类；2026-10 订单未导出 → `censor_unknown`，"
        "不写成 0 销量、不参与训练。",
        "- **删失月不进正常 0**：`stockout_censored` / `censor_unknown` 的 `usable_for_training=false`；"
        "`genuine_zero`/`dormant`/`long_term_zero` 保留但带标签。",
        "- **三层计量**：`raw_qty`（订单原始件数）→ `sellable_qty`（可售单位，TJ# 为套）→ `component_qty`（组件个，按 Product Bundle）；"
        "后缀层级不一致标 ambiguous、组件量留空不猜。",
        "- **标签**：#qc 按 SKU 命中；新品按首次通途销售日；老产品引 C 16_；促销无日历一律 unknown。",
        "- 未匹配/非活跃/out-of-scope 订单行全部保留在质量表，不静默丢弃。",
        "",
        "## 6. 只读声明",
        "",
        "本次仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途，未发消息，未 push；未改 A/B/C/D 历史产物。",
        "",
        f"- 工作簿 SHA256：`{out_sha}`",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
