# -*- coding: utf-8 -*-
"""需求预测『去历史库存影响』（只读分析）。

输入：active EN 物料清单、库存观测（PJ/WX/EN）、r4 与 conservative 删失 run。
输出：1,294 active EN 的 30/90/150/180/97/157 天需求、删失证据、置信度、
近零复核清单、与 r4 差异。

不写 EN/通途、不 push、不编造销量。
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import forecast as F

ACTIVE_XLSX = "D:/Work/fzh-order-store/analysis/美国与波兰仓库归属_2026-10-28_v5.xlsx"
R4_RUN = "D:/Work/fzh-order-store/en-demand-v1/forecast/forecast-20261027-r4"
CONS_RUN = "D:/Work/fzh-order-store/en-demand-v1/forecast/forecast-20261027-cens-cons"
FLAGS = "D:/Work/fzh-order-store/en-demand-v1/stockout-censoring-2026-10-28/stockout_monthly_flags.parquet"
CACHE = "D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet"
SKU_MAP = "D:/Work/fzh-order-store/sku_map.tsv"
SEP_CANDIDATES = "D:/Work/fzh-order-store/analysis/september_spike_candidates_20261027.csv"
OUT_XLSX = "D:/Work/fzh-order-store/analysis/需求预测_去库存影响_2026-10-29.xlsx"
OUT_REPORT = "D:/Work/fzh-order-store/analysis/需求预测_去库存影响_2026-10-29_报告.md"
DECISION = date(2026, 10, 29)
HORIZONS = (30, 90, 97, 150, 157, 180)
FORECAST_MONTHS = [F.index_ym(F.ym_index("2026-10") + k) for k in range(7)]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _split(x: Any) -> list[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    s = str(x).replace("，", ";").replace(",", ";")
    return [t.strip() for t in s.split(";") if t.strip()]


def load_active() -> pd.DataFrame:
    us = pd.read_excel(ACTIVE_XLSX, sheet_name="1_美国归属与补货")
    pl = pd.read_excel(ACTIVE_XLSX, sheet_name="2_波兰归属与补货")
    us["EN物料"] = us["EN物料"].astype(str)
    pl["EN物料"] = pl["EN物料"].astype(str)
    if us["EN物料"].duplicated().any() or pl["EN物料"].duplicated().any():
        raise SystemExit("active Excel EN 物料重复")
    pl_cols = {
        "EN物料": "EN物料",
        "近6月销售-波兰": "recent_pl",
        "当前库存-波兰": "stock_pl",
        "波兰补货建议": "suggest_pl",
        "参与计算的通途SKU": "sku_pl",
        "FBA SKU（不计入）": "fba_pl",
    }
    base = us.rename(
        columns={
            "近6月销售-美东": "recent_us_east",
            "近6月销售-美中": "recent_us_mid",
            "当前库存-美东USNJ": "stock_us_east",
            "当前库存-美中USTX": "stock_us_mid",
            "美国补货建议": "suggest_us",
            "参与计算的通途SKU": "sku_us",
            "FBA SKU（不计入）": "fba_us",
        }
    )[
        [
            "EN物料", "物料名称", "分组", "绍兴发货方式",
            "sku_us", "fba_us", "recent_us_east", "recent_us_mid",
            "stock_us_east", "stock_us_mid", "suggest_us",
        ]
    ].copy()
    base = base.merge(pl[list(pl_cols)].rename(columns=pl_cols), on="EN物料", how="left")
    for c in ["recent_us_east", "recent_us_mid", "stock_us_east", "stock_us_mid",
              "recent_pl", "stock_pl"]:
        base[c] = _num(base[c])
    base["recent_us"] = base["recent_us_east"] + base["recent_us_mid"]
    base["recent_total"] = base["recent_us"] + base["recent_pl"]
    base["stock_total"] = base["stock_us_east"] + base["stock_us_mid"] + base["stock_pl"]
    return base


def load_sku_sets(active: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    sm = pd.read_csv(
        SKU_MAP, sep="\t", header=None, dtype=str, quoting=3,
        names=["item_code", "tongtool_sku", "customer_name"],
    )
    sm["item_code"] = sm["item_code"].astype(str).str.strip()
    sm["tongtool_sku"] = sm["tongtool_sku"].astype(str).str.strip()
    reverse = sm[sm["item_code"] != ""].groupby("item_code")["tongtool_sku"].agg(
        lambda x: sorted(set(x))
    ).to_dict()
    sets: dict[str, list[str]] = {}
    for r in active.itertuples(index=False):
        skus = _split(getattr(r, "sku_us", ""))
        if not skus:
            skus = _split(getattr(r, "sku_pl", ""))
        if not skus:
            skus = list(reverse.get(str(r.EN物料), []))
        fba = set(_split(getattr(r, "fba_us", ""))) | set(_split(getattr(r, "fba_pl", "")))
        skus = [s for s in dict.fromkeys(skus) if s not in fba]
        sets[str(r.EN物料)] = skus
    return active, sets


def load_monthly(run: str) -> pd.DataFrame:
    m = pd.read_parquet(f"{run}/forecast_sku_monthly.parquet")
    m = m[m["forecast_month"].isin(FORECAST_MONTHS)]
    return m


def aggregate_forecast(
    skus: list[str],
    monthly: pd.DataFrame,
) -> tuple[dict[str, dict[str, float | None]], int]:
    """返回 {month: {p50,p10,p90}} 与有预测的 SKU 数。"""
    sub = monthly[monthly["tongtool_sku"].isin(skus)]
    out: dict[str, dict[str, float | None]] = {}
    n_fc = 0
    for m in FORECAST_MONTHS:
        g = sub[sub["forecast_month"] == m]
        p50 = g["p50"].dropna()
        if len(p50):
            n_fc = max(n_fc, len(set(g.loc[g["p50"].notna(), "tongtool_sku"])))
            out[m] = {
                "p50": float(p50.sum()),
                "p10": float(g["p10"].dropna().sum()) if g["p10"].notna().any() else None,
                "p90": float(g["p90"].dropna().sum()) if g["p90"].notna().any() else None,
            }
        else:
            out[m] = {"p50": None, "p10": None, "p90": None}
    return out, n_fc


def cumulative(
    months: dict[str, dict[str, float | None]], days: int
) -> dict[str, float | None]:
    w = F.window_weights(DECISION, days)
    start_i = F.ym_index("2026-10")
    totals = {"p50": 0.0, "p10": 0.0, "p90": 0.0}
    any_p50 = any_p10 = any_p90 = False
    for mi, wt in w.items():
        m = F.index_ym(mi)
        k = mi - start_i
        if 0 <= k < len(FORECAST_MONTHS) and m in months:
            v = months[m]
            if v["p50"] is not None:
                totals["p50"] += wt * v["p50"]
                any_p50 = True
            if v["p10"] is not None:
                totals["p10"] += wt * v["p10"]
                any_p10 = True
            if v["p90"] is not None:
                totals["p90"] += wt * v["p90"]
                any_p90 = True
    return {
        "p50": round(totals["p50"], 3) if any_p50 else None,
        "p10": round(totals["p10"], 3) if any_p10 else None,
        "p90": round(totals["p90"], 3) if any_p90 else None,
    }


def uom_of(active: pd.DataFrame, skus: dict[str, list[str]], r4: pd.DataFrame) -> pd.DataFrame:
    cache = pd.read_parquet(CACHE).set_index("item_code")
    r4s = r4.set_index("tongtool_sku")
    rows = []
    for r in active.itertuples(index=False):
        en = str(r.EN物料)
        item_uom = cache.at[en, "stock_uom"] if en in cache.index else None
        is_stock = cache.at[en, "is_stock_item"] if en in cache.index else None
        sku_uoms = {
            str(r4s.at[s, "uom_group"])
            for s in skus.get(en, [])
            if s in r4s.index and pd.notna(r4s.at[s, "uom_group"])
        }
        if pd.isna(item_uom) and len(sku_uoms) == 1:
            item_uom = next(iter(sku_uoms))
        u = "" if item_uom is None or pd.isna(item_uom) else str(item_uom)
        if u == "套":
            if str(en).startswith("TJ#") and is_stock is not None and int(is_stock) == 0:
                group = "套"
            else:
                group = "uom_conflict"
        elif u == "个":
            group = "个"
        else:
            group = "unknown"
        rows.append({"EN物料": en, "uom": u, "is_stock_item": is_stock, "uom_group": group})
    return pd.DataFrame(rows)


def inventory_evidence(skus: list[str], flags: pd.DataFrame) -> dict[str, Any]:
    f = flags[flags["sku"].isin(skus)]
    if not len(f):
        return {
            "inventory_evidence": "none",
            "evidence_skus": 0,
            "censored_months": 0,
            "zero_stock_months": 0,
            "positive_months": 0,
            "first_censored_month": "",
            "last_censored_month": "",
            "inventory_window": "",
            "high_zero_dates": 0,
        }
    cens = f[f["censored"].fillna(False).astype(bool)]
    zero = f[f["zero_dates"].fillna(0) > 0]
    pos = f[f["pos_dates"].fillna(0) > 0]
    return {
        "inventory_evidence": "yes",
        "evidence_skus": int(f["sku"].nunique()),
        "censored_months": int(cens["month"].nunique()),
        "zero_stock_months": int(zero["month"].nunique()),
        "positive_months": int(pos["month"].nunique()),
        "first_censored_month": str(cens["month"].min()) if len(cens) else "",
        "last_censored_month": str(cens["month"].max()) if len(cens) else "",
        "inventory_window": f"{f['month'].min()}..{f['month'].max()}",
        "high_zero_dates": int(f["high_zero_dates"].fillna(0).sum()) if "high_zero_dates" in f else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-xlsx", default=OUT_XLSX)
    ap.add_argument("--out-report", default=OUT_REPORT)
    args = ap.parse_args()

    active = load_active()
    active, sku_sets = load_sku_sets(active)
    uom = uom_of(active, sku_sets, pd.read_parquet(f"{R4_RUN}/forecast_sku_summary.parquet"))
    active = active.merge(uom, on="EN物料", how="left")

    r4_sum = pd.read_parquet(f"{R4_RUN}/forecast_sku_summary.parquet").set_index("tongtool_sku")
    cons_sum = pd.read_parquet(f"{CONS_RUN}/forecast_sku_summary.parquet").set_index("tongtool_sku")
    r4_mon = load_monthly(R4_RUN)
    cons_mon = load_monthly(CONS_RUN)
    flags = pd.read_parquet(FLAGS)
    sep = pd.read_csv(SEP_CANDIDATES).set_index("sku") if Path(SEP_CANDIDATES).exists() else pd.DataFrame()

    rows = []
    evidence_rows = []
    near_rows = []
    for r in active.itertuples(index=False):
        en = str(r.EN物料)
        skus = sku_sets.get(en, [])
        uom_group = str(r.uom_group)
        allowed = uom_group in ("个", "套")
        cons_month, n_cons = aggregate_forecast(skus, cons_mon)
        r4_month, n_r4 = aggregate_forecast(skus, r4_mon)
        cons_cum = {d: cumulative(cons_month, d) for d in HORIZONS}
        r4_cum = {d: cumulative(r4_month, d) for d in HORIZONS}

        # 历史与 SKU 级方法
        hist_months = [int(r4_sum.at[s, "history_months"]) for s in skus if s in r4_sum.index]
        hist_units = [float(r4_sum.at[s, "history_units_total"]) for s in skus if s in r4_sum.index]
        methods = [str(r4_sum.at[s, "forecast_method"]) for s in skus if s in r4_sum.index]
        statuses = [str(r4_sum.at[s, "forecast_status"]) for s in skus if s in r4_sum.index]
        backtests = [float(r4_sum.at[s, "backtest_wape"]) for s in skus if s in r4_sum.index and pd.notna(r4_sum.at[s, "backtest_wape"])]
        hist_m = max(hist_months) if hist_months else 0
        hist_u = sum(hist_units) if hist_units else 0.0

        inv = inventory_evidence(skus, flags)
        cens_share = (inv["censored_months"] / hist_m) if hist_m > 0 else None

        # 清仓/活动标记
        text = " ".join(str(getattr(r, c, "")) for c in ["EN物料", "物料名称", "sku_us", "sku_pl", "suggest_us", "suggest_pl"])
        clearance = ("#qc" in text.lower()) or ("清仓" in text)
        act_cls = ""
        for s in skus:
            if not sep.empty and s in sep.index:
                act_cls = str(sep.at[s, "cls"])
                break
        activity = bool(act_cls) and act_cls not in ("", "正常")

        # 预测不可算原因
        p50_90 = cons_cum[90]["p50"]
        reason = ""
        if uom_group == "unknown":
            p50_90 = None
            reason = "uom_unknown_no_total"
        elif uom_group == "uom_conflict":
            p50_90 = None
            reason = "uom_conflict_no_total"
        elif p50_90 is None:
            if r.recent_total > 0:
                # 无 SKU 级预测，但有近 6 月观测：run-rate 兜底（只给点值）
                rate = float(r.recent_total) / 6.0
                for d in HORIZONS:
                    cons_cum[d] = {"p50": round(rate * d / 30.4375, 3), "p10": None, "p90": None}
                p50_90 = cons_cum[90]["p50"]
                reason = "recent_6m_run_rate_no_sku_forecast"
            else:
                reason = "no_history_no_recent_sales"

        method = "none"
        if p50_90 is not None:
            if reason.startswith("recent_6m_run_rate"):
                method = "recent_6m_run_rate"
            else:
                uniq = sorted(set(methods))
                method = "+".join(uniq) if uniq else "unknown"

        # 置信度
        conf_reason = []
        if p50_90 is None:
            conf = "not_computable"
            conf_reason.append(reason or "no_forecast")
        else:
            conf = "high"
            if method == "recent_6m_run_rate":
                conf = "low"; conf_reason.append("run_rate")
            if hist_m < 24:
                conf = "medium" if conf == "high" else conf
                conf_reason.append(f"history_{hist_m}m")
            if hist_m < 7:
                conf = "low"; conf_reason.append("short_history")
            if cens_share is not None and cens_share > 0.1:
                conf = "medium" if conf == "high" else conf
                conf_reason.append(f"censored_{cens_share:.0%}")
            if cens_share is not None and cens_share > 0.3:
                conf = "low"; conf_reason.append("censored_gt30%")
            if inv["inventory_evidence"] == "none":
                conf = "low"; conf_reason.append("inventory_gap")
            if clearance or activity:
                conf = "low"; conf_reason.append("clearance_or_activity")
        conf_text = ";".join(conf_reason) or "ok"

        # 近零结论
        near_zero = p50_90 is not None and float(p50_90) <= 1.0
        stockout_explains = False
        if near_zero:
            if inv["censored_months"] > 0:
                nz = "stockout_censored"
                stockout_explains = True
            elif inv["zero_stock_months"] > 0 and inv["positive_months"] == 0:
                nz = "long_term_zero_stock"
                stockout_explains = True
            elif r.recent_total <= 0 and hist_u > 0:
                nz = "dormant_no_recent_sales"
            elif inv["inventory_evidence"] == "none":
                nz = "data_gap_inventory"
            elif r.recent_total > 0:
                nz = "genuine_low_demand"
            else:
                nz = "no_demand_evidence"
            near_rows.append(
                {
                    "EN物料": en, "物料名称": r.物料名称, "分组": r.分组,
                    "uom_group": uom_group, "p50_90": p50_90,
                    "p50_180": cons_cum[180]["p50"], "recent_total": r.recent_total,
                    "history_units": round(hist_u, 1), "history_months": hist_m,
                    "censored_months": inv["censored_months"],
                    "zero_stock_months": inv["zero_stock_months"],
                    "inventory_window": inv["inventory_window"],
                    "near_zero_conclusion": nz,
                    "stockout_explains_near_zero": stockout_explains,
                }
            )
        else:
            nz = ""

        # 区域拆分
        split_total = float(r.recent_us) + float(r.recent_pl)
        share_us = float(r.recent_us) / split_total if split_total > 1e-9 else None
        share_pl = float(r.recent_pl) / split_total if split_total > 1e-9 else None

        def region(v, share):
            return None if (v is None or share is None) else round(float(v) * share, 3)

        diff90 = None
        diff180 = None
        if cons_cum[90]["p50"] is not None and r4_cum[90]["p50"] is not None:
            diff90 = round(cons_cum[90]["p50"] - r4_cum[90]["p50"], 3)
        if cons_cum[180]["p50"] is not None and r4_cum[180]["p50"] is not None:
            diff180 = round(cons_cum[180]["p50"] - r4_cum[180]["p50"], 3)

        row = {
            "EN物料": en,
            "物料名称": r.物料名称,
            "分组": r.分组,
            "绍兴发货方式": r.绍兴发货方式,
            "uom": r.uom,
            "uom_group": uom_group,
            "uom_totals_allowed": allowed,
            "通途SKU": ";".join(skus),
            "n_skus": len(skus),
            "forecastable_skus": int(n_cons),
            "history_months": hist_m,
            "history_units": round(hist_u, 3),
            "recent_us": round(float(r.recent_us), 3),
            "recent_pl": round(float(r.recent_pl), 3),
            "recent_total": round(float(r.recent_total), 3),
            "stock_us_east": float(r.stock_us_east),
            "stock_us_mid": float(r.stock_us_mid),
            "stock_pl": float(r.stock_pl),
            "stock_total": float(r.stock_total),
            "inventory_evidence": inv["inventory_evidence"],
            "evidence_skus": inv["evidence_skus"],
            "inventory_window": inv["inventory_window"],
            "censored_months": inv["censored_months"],
            "zero_stock_months": inv["zero_stock_months"],
            "positive_stock_months": inv["positive_months"],
            "first_censored_month": inv["first_censored_month"],
            "last_censored_month": inv["last_censored_month"],
            "censored_share_of_history": None if cens_share is None else round(cens_share, 4),
            "clearance_flag": clearance,
            "activity_flag": activity,
            "activity_class": act_cls,
            "normal_demand_scope": ("clearance_tagged" if clearance else "activity_tagged" if activity else "normal"),
            "forecast_status": "ok" if p50_90 is not None else "not_computable",
            "forecast_method": method,
            "method_mix": ";".join(sorted(set(methods))),
            "confidence": conf,
            "confidence_reason": conf_text,
            "near_zero": near_zero,
            "near_zero_conclusion": nz,
            "stockout_explains_near_zero": stockout_explains,
            "diff_p50_90_vs_r4": diff90,
            "diff_p50_180_vs_r4": diff180,
            "share_us": None if share_us is None else round(share_us, 4),
            "share_pl": None if share_pl is None else round(share_pl, 4),
            "us_p50_90": region(cons_cum[90]["p50"], share_us),
            "us_p50_180": region(cons_cum[180]["p50"], share_us),
            "pl_p50_90": region(cons_cum[90]["p50"], share_pl),
            "pl_p50_180": region(cons_cum[180]["p50"], share_pl),
            "data_gap": ";".join(
                x for x in [
                    "no_sku_mapping" if not skus else "",
                    "no_history" if hist_m == 0 else "",
                    "no_forecast" if p50_90 is None else "",
                    "inventory_gap" if inv["inventory_evidence"] == "none" else "",
                    "uom_unknown" if uom_group == "unknown" else "",
                    "uom_conflict" if uom_group == "uom_conflict" else "",
                ] if x
            ),
        }
        for d in HORIZONS:
            row[f"p50_{d}"] = cons_cum[d]["p50"]
            row[f"p10_{d}"] = cons_cum[d]["p10"]
            row[f"p90_{d}"] = cons_cum[d]["p90"]
            row[f"r4_p50_{d}"] = r4_cum[d]["p50"]
        # 复核优先级
        score = 0.0
        if near_zero and hist_u > 0:
            score += 100
        if cens_share is not None:
            score += 60 * min(cens_share, 1)
        if inv["inventory_evidence"] == "none":
            score += 40
        if conf == "low":
            score += 30
        if clearance or activity:
            score += 20
        if diff90 is not None and abs(diff90) > 0.2 * max(1.0, abs(r4_cum[90]["p50"] or 0)):
            score += 20
        score += min(float(r.recent_total), 500) / 50.0
        row["review_score"] = round(score, 1)
        rows.append(row)

    main = pd.DataFrame(rows).sort_values("review_score", ascending=False).reset_index(drop=True)
    main["review_rank"] = main.index + 1

    # 删失证据行
    ev = flags[flags["sku"].isin({s for lst in sku_sets.values() for s in lst})].copy()
    en_by_sku = {s: en for en, lst in sku_sets.items() for s in lst}
    ev["EN物料"] = ev["sku"].map(en_by_sku)
    ev = ev[ev["EN物料"].notna()][
        ["EN物料", "sku", "month", "stockout_status", "censored", "zero_dates",
         "pos_dates", "high_zero_dates", "sales_units", "uom_group", "sources"]
    ].sort_values(["EN物料", "month"])
    evidence_rows = ev

    near = pd.DataFrame(near_rows).sort_values(
        ["stockout_explains_near_zero", "recent_total"], ascending=[False, False]
    )
    gaps = main[main["data_gap"] != ""][
        ["EN物料", "物料名称", "分组", "uom_group", "history_months", "recent_total",
         "inventory_evidence", "data_gap", "forecast_status", "confidence"]
    ].copy()

    summary = pd.DataFrame(
        [
            {"metric": "active_en", "value": len(main)},
            {"metric": "forecast_ok", "value": int((main["forecast_status"] == "ok").sum())},
            {"metric": "not_computable", "value": int((main["forecast_status"] != "ok").sum())},
            {"metric": "inventory_evidence_skus", "value": int((main["inventory_evidence"] == "yes").sum())},
            {"metric": "censored_en", "value": int((main["censored_months"] > 0).sum())},
            {"metric": "near_zero_en", "value": int(main["near_zero"].sum())},
            {"metric": "near_zero_stockout", "value": int(main["stockout_explains_near_zero"].sum())},
            {"metric": "uom_unknown", "value": int((main["uom_group"] == "unknown").sum())},
            {"metric": "uom_conflict", "value": int((main["uom_group"] == "uom_conflict").sum())},
            {"metric": "clearance_tagged", "value": int(main["clearance_flag"].sum())},
            {"metric": "activity_tagged", "value": int(main["activity_flag"].sum())},
        ]
    )
    method_counts = main["forecast_method"].value_counts().rename_axis("forecast_method").reset_index(name="count")
    conf_counts = main["confidence"].value_counts().rename_axis("confidence").reset_index(name="count")
    role_counts = main["绍兴发货方式"].value_counts().rename_axis("role").reset_index(name="count")
    nz_counts = main[main["near_zero"]]["near_zero_conclusion"].value_counts().rename_axis("near_zero_conclusion").reset_index(name="count")

    diff = main[main["diff_p50_90_vs_r4"].notna()][
        ["EN物料", "物料名称", "uom_group", "recent_total", "r4_p50_90", "p50_90",
         "diff_p50_90_vs_r4", "r4_p50_180", "p50_180", "diff_p50_180_vs_r4",
         "censored_months", "confidence"]
    ].copy()

    # 写 Excel
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="0_说明与汇总", index=False)
        main.to_excel(xw, sheet_name="1_需求预测", index=False)
        evidence_rows.to_excel(xw, sheet_name="2_删失证据", index=False)
        near.to_excel(xw, sheet_name="3_近零复核", index=False)
        gaps.to_excel(xw, sheet_name="4_数据缺口", index=False)
        diff.to_excel(xw, sheet_name="5_与r4差异", index=False)
        method_counts.to_excel(xw, sheet_name="6_方法与分档", index=False, startrow=0)
        conf_counts.to_excel(xw, sheet_name="6_方法与分档", index=False, startrow=len(method_counts) + 3)
        role_counts.to_excel(xw, sheet_name="6_方法与分档", index=False, startrow=len(method_counts) + len(conf_counts) + 6)
        nz_counts.to_excel(xw, sheet_name="6_方法与分档", index=False, startrow=len(method_counts) + len(conf_counts) + len(role_counts) + 9)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="DDEBF7")
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            for idx, col in enumerate(ws.columns, 1):
                width = min(42, max(10, max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2))
                ws.column_dimensions[get_column_letter(idx)].width = width
            if ws.max_row > 1:
                ws.auto_filter.ref = ws.dimensions

    # 报告
    top20 = main.head(20)[
        ["review_rank", "EN物料", "物料名称", "分组", "uom_group", "recent_total",
         "history_months", "censored_months", "p50_90", "p50_180", "near_zero_conclusion",
         "confidence", "diff_p50_90_vs_r4", "data_gap"]
    ]
    hlr = main[main["EN物料"].astype(str).str.contains("HLR-60-TAN", na=False)][
        ["EN物料", "p50_90", "p50_180", "recent_total", "history_units", "censored_months",
         "zero_stock_months", "inventory_window", "near_zero_conclusion", "confidence"]
    ]
    lines = [
        "# 需求预测：去历史库存影响（2026-10-29）",
        "",
        f"> 输入 active EN **{len(main):,}**；预测口径：conservative 删失 run；"
        "个/套分列，未知单位不合计；只读，不写 EN/通途。",
        "",
        "## 1. 汇总",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
    ]
    for r in summary.itertuples(index=False):
        lines.append(f"| {r.metric} | {r.value:,} |")
    lines += [
        "",
        "## 2. 方法与置信度",
        "",
        "| 方法 | SKU 数 |",
        "|---|---:|",
    ]
    for r in method_counts.itertuples(index=False):
        lines.append(f"| {r.forecast_method} | {r.count:,} |")
    lines += ["", "| 置信度 | SKU 数 |", "|---|---:|"]
    for r in conf_counts.itertuples(index=False):
        lines.append(f"| {r.confidence} | {r.count:,} |")
    lines += [
        "",
        "## 3. 断货删失证据",
        "",
        f"- 有库存证据的 active EN：**{int((main['inventory_evidence']=='yes').sum()):,}**；"
        f"其中至少 1 个删失月：**{int((main['censored_months']>0).sum()):,}**。",
        "- 删失定义：SKU×日所有已观测 primary_sellable 仓 available 合计 ≤0，且 SKU 同时有零/正观测；"
        "只覆盖 2026-04..10，早于该窗口的断货未知。",
        "",
        "## 4. 近零复核",
        "",
    ]
    for r in nz_counts.itertuples(index=False):
        lines.append(f"- `{r.near_zero_conclusion}`：{r.count:,}")
    lines += ["", "### HLR-60-TAN", "", "| EN | p50_90 | p50_180 | 近6月 | 历史量 | 删失月 | 零库存月 | 结论 |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in hlr.itertuples(index=False):
        lines.append(
            f"| {r.EN物料} | {r.p50_90} | {r.p50_180} | {r.recent_total} | {r.history_units} | "
            f"{r.censored_months} | {r.zero_stock_months} | {r.near_zero_conclusion} |"
        )
    lines += [
        "",
        "## 5. 与 r4 的差异",
        "",
        f"- 有可比 p50 的 EN：**{len(diff):,}**；L90 差异中位 "
        f"**{diff['diff_p50_90_vs_r4'].median():+.3f}**，L180 中位 "
        f"**{diff['diff_p50_180_vs_r4'].median():+.3f}**。",
        "- r4 为未去库存影响的生产预测；本表为 conservative 删失补值后的情景，不是已证真值。",
        "",
        "## 6. 最需人工复核 Top 20",
        "",
        "| # | EN | 分组 | 近6月 | 历史月 | 删失月 | p50_90 | p50_180 | 近零结论 | 置信 | 与r4差 | 数据缺口 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for r in top20.itertuples(index=False):
        lines.append(
            f"| {r.review_rank} | {r.EN物料} | {r.分组} | {r.recent_total:,.0f} | {r.history_months} | "
            f"{r.censored_months} | {'' if pd.isna(r.p50_90) else f'{r.p50_90:,.1f}'} | "
            f"{'' if pd.isna(r.p50_180) else f'{r.p50_180:,.1f}'} | {r.near_zero_conclusion} | "
            f"{r.confidence} | {'' if pd.isna(r.diff_p50_90_vs_r4) else f'{r.diff_p50_90_vs_r4:+.1f}'} | {r.data_gap} |"
        )
    lines += [
        "",
        "## 7. 数据缺口与限制",
        "",
        "- 库存观测是检查点（PJ 20+/WX 38/PB 0/EN 日快照），不是每日快照；2026-04 之前无历史库存点。",
        "- 零销量不一律当 0：删失月用 conservative 补值；补值是情景假设，不是损失销量。",
        "- 清仓/活动只能按 `#qc`/清仓字样与 9 月 spike 候选标记；没有促销日历，不能逐月剔除。",
        "- 未知单位 43 个、非 TJ# 套冲突 2 个：不产生总量；见数据缺口页。",
        "- 区域拆分按近 6 月销售占比，是假设；不是逐仓预测。",
        "",
        "## 8. 产物",
        "",
        f"- Excel：`{out}`",
        f"- 报告：`{Path(args.out_report)}`",
    ]
    Path(args.out_report).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "active": len(main),
        "forecast_ok": int((main["forecast_status"] == "ok").sum()),
        "not_computable": int((main["forecast_status"] != "ok").sum()),
        "inventory_evidence": int((main["inventory_evidence"] == "yes").sum()),
        "censored_en": int((main["censored_months"] > 0).sum()),
        "near_zero": int(main["near_zero"].sum()),
        "near_zero_stockout": int(main["stockout_explains_near_zero"].sum()),
        "uom_unknown": int((main["uom_group"] == "unknown").sum()),
        "uom_conflict": int((main["uom_group"] == "uom_conflict").sum()),
        "xlsx": str(out),
        "report": args.out_report,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
