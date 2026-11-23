# -*- coding: utf-8 -*-
"""断货删失分析（只读、离线）：标记零库存月，量化对预测训练的影响。

背景（`2026-10-28-frepple-conversation-digest.md`）
- 零库存时销量更低：零库存月不能当真实需求 0 训练。
- 库存观测是检查点（PJ 22 / WX 38 / EN 7 天），不是每日快照。

本模块
1. 把 primary_sellable 库存观测按 SKU×日期聚合：所有观测仓合计 available<=0 → 零库存。
2. 只对**同时有零/有库存观测**的 SKU 标记删失月（永久零库存的 SKU 不硬造需求）。
3. 用生产同一套 forecast.py 规则，对比「原样零」与「删失月按近期非删失月均值补」的
   样本量与 L90/L180 预测差异（子样本，不重训全量）。
4. 输出字段建议与接入建议；不改生产预测、不写 CURRENT、不下单。

UOM 口径：`UOM-CANONICAL.md`（2026-10-28）。主表只算已证「个」；
「套」单列（仅 TJ# bundle）；PK# 按皮壳 1:1 不是套；未知单位不合计。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from . import forecast as F
from .store import now_iso

SCHEMA_VERSION = "en-demand-stockout-censoring-v1"
DEFAULT_STOCK = "D:/Work/fzh-order-store/en-demand-v1/stockout-censoring-2026-10-28/input_stock_status_daily.parquet"
DEFAULT_OUT = "D:/Work/fzh-order-store/en-demand-v1/stockout-censoring-2026-10-28"
DEFAULT_UOM_CACHE = "D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet"
DECISION_DATE = date(2026, 10, 29)
HORIZON_MONTHS = 7


@dataclass(frozen=True)
class Config:
    min_history: int = 7
    decision_date: date = DECISION_DATE
    horizon_months: int = HORIZON_MONTHS

    def to_json(self) -> dict[str, Any]:
        return {
            "min_history_months": self.min_history,
            "decision_date": self.decision_date.isoformat(),
            "horizon_months": self.horizon_months,
            "uom_main_group": "个",
            "uom_rule_ref": "UOM-CANONICAL.md (2026-10-28)",
        }


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def _git_head() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _git_dirty() -> bool | None:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


def resolve_uom(c: pd.Series | None, cache: pd.DataFrame) -> tuple[str, str, str, bool]:
    """按 UOM-CANONICAL 分组。

    - 个：已证件类
    - 套：仅 TJ# bundle（stock_uom=套 且 is_stock_item=0）
    - uom_conflict：stock_uom=套 但不是 TJ# bundle（主数据冲突）
    - unknown：未证单位（不合计）
    """
    if c is None:
        return "", "netting_evidence_missing", "unknown", False
    raw_uom = c.get("uom")
    raw_status = c.get("uom_status")
    uom = "" if raw_uom is None or pd.isna(raw_uom) else str(raw_uom).strip()
    status = "" if raw_status is None or pd.isna(raw_status) else str(raw_status).strip()
    item = c.get("canonical_sku")
    item = "" if item is None or pd.isna(item) else str(item)
    if status == "known_piece" and uom == "个":
        return uom, status, "个", True
    if status == "known_piece" and uom == "套":
        row = cache.loc[item] if item in cache.index else None
        is_stock = None if row is None else row.get("is_stock_item")
        if item.startswith("TJ#") and is_stock is not None and int(is_stock) == 0:
            return uom, status, "套", True
        return uom, status, "uom_conflict", False
    if status == "not_piece":
        return uom, status, "not_piece", False
    return uom, status or "unknown", "unknown", False


def build_flags(stock: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """SKU×日 → SKU×月 的零库存/删失标记。"""
    stock = stock.copy()
    stock["d"] = pd.to_datetime(stock["d"])
    stock["is_zero"] = stock["stock_state"].eq("present_zero")
    stock["is_pos"] = stock["stock_state"].eq("present_positive")
    stock["high"] = stock["source"].isin(["en_daily", "pj_checkpoint"])
    sday = (
        stock.groupby(["sku", "d"], as_index=False)
        .agg(
            n_avail=("available", "count"),
            avail_sum=("available", "sum"),
            n_zero=("is_zero", "sum"),
            n_pos=("is_pos", "sum"),
            high=("high", "any"),
            sources=("source", lambda x: ",".join(sorted(set(x)))),
        )
    )
    sday["state"] = np.where(
        (sday["n_avail"] > 0) & (sday["avail_sum"] <= 0),
        "zero",
        np.where(sday["avail_sum"] > 0, "positive", "unknown"),
    )
    sday = sday[sday["state"] != "unknown"].copy()
    sday["month"] = sday["d"].dt.strftime("%Y-%m")
    sday["high_zero"] = sday["high"] & sday["state"].eq("zero")

    states = sday.groupby("sku")["state"].agg(set)
    both = set(states[states.apply(lambda x: "zero" in x and "positive" in x)].index)

    monthly = (
        sday.groupby(["sku", "month"], as_index=False)
        .agg(
            obs_dates=("d", "nunique"),
            zero_dates=("state", lambda x: int((x == "zero").sum())),
            pos_dates=("state", lambda x: int((x == "positive").sum())),
            min_avail=("avail_sum", "min"),
            max_avail=("avail_sum", "max"),
            high_zero_dates=("high_zero", "sum"),
            sources=("sources", lambda x: ",".join(sorted(set(",".join(x).split(","))))),
        )
    )
    monthly["stockout_status"] = np.select(
        [monthly["zero_dates"] == 0, monthly["pos_dates"] == 0],
        ["observed_positive_only", "observed_zero_only"],
        default="observed_mixed",
    )
    monthly["both_states_sku"] = monthly["sku"].isin(both)
    monthly["censored"] = monthly["both_states_sku"] & (monthly["zero_dates"] > 0)
    meta = {
        "observation_rows": int(len(stock)),
        "sku_date_rows": int(len(sday)),
        "skus_observed": int(sday["sku"].nunique()),
        "skus_both_zero_positive": int(len(both)),
        "sku_months": int(len(monthly)),
        "censored_sku_months": int(monthly["censored"].sum()),
        "censored_skus": int(monthly.loc[monthly["censored"], "sku"].nunique()),
        "dates": int(sday["d"].nunique()),
        "date_min": str(sday["d"].min().date()),
        "date_max": str(sday["d"].max().date()),
    }
    return sday, monthly, meta


def thirty_day_check(sday: pd.DataFrame, daily_sales: pd.DataFrame) -> pd.DataFrame:
    """SKU×日观测的未来 30 天销量（精确日窗口，SKU 级）。

    与 digest 的 696/455 是 observation-row 口径不同；这里按 SKU×日聚合，
    且只用 2026-10-26 之前可观测的完整窗口。
    """
    obs = sday[["sku", "d", "state", "high"]].reset_index(drop=True)
    obs["obs_id"] = obs.index
    sales = daily_sales.sort_values(["sku", "demand_date"]).copy()
    sales["cum"] = sales.groupby("sku")["quantity"].cumsum()
    right = sales[["sku", "demand_date", "cum"]].sort_values("demand_date")
    a = pd.merge_asof(
        obs.sort_values("d"),
        right.rename(columns={"demand_date": "d"}),
        on="d",
        by="sku",
        direction="backward",
    ).set_index("obs_id")
    obs30 = obs.assign(d30=obs["d"] + pd.Timedelta(days=30))
    b = pd.merge_asof(
        obs30.sort_values("d30"),
        right.rename(columns={"demand_date": "d30"}),
        on="d30",
        by="sku",
        direction="backward",
    ).set_index("obs_id")
    obs["cum"] = obs["obs_id"].map(a["cum"])
    obs["cum30"] = obs["obs_id"].map(b["cum"])
    obs["fwd30"] = obs["cum30"].fillna(0.0) - obs["cum"].fillna(0.0)
    means = obs.groupby(["sku", "state"])["fwd30"].mean().unstack()
    means = means.dropna(subset=["zero", "positive"])
    high = obs[obs["high"]].groupby(["sku", "state"])["fwd30"].mean().unstack().dropna(subset=["zero", "positive"])
    if not len(means):
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "scope": "all_observations_sku_level",
                "skus_both": int(len(means)),
                "zero_lower_skus": int((means["zero"] < means["positive"]).sum()),
                "zero_lower_share": round(float((means["zero"] < means["positive"]).mean()), 4),
                "mean_zero_30d": round(float(means["zero"].mean()), 3),
                "mean_positive_30d": round(float(means["positive"].mean()), 3),
            },
            {
                "scope": "high_confidence_only",
                "skus_both": int(len(high)),
                "zero_lower_skus": int((high["zero"] < high["positive"]).sum()) if len(high) else 0,
                "zero_lower_share": round(float((high["zero"] < high["positive"]).mean()), 4) if len(high) else None,
                "mean_zero_30d": round(float(high["zero"].mean()), 3) if len(high) else None,
                "mean_positive_30d": round(float(high["positive"].mean()), 3) if len(high) else None,
            },
        ]
    )


def impute_conservative(y: np.ndarray, censored: np.ndarray, i: int) -> float:
    """保守补值：只用于「删失且销量=0」的月。

    取最近 6 个非删失月的中位数（含 0）；中位为 0 则不补。
    上限取该 SKU 非删失正值月的 P90，避免单月峰值放大。
    """
    idx = [j for j in range(max(0, i - 6), i) if not censored[j]]
    if not idx:
        return 0.0
    med = float(np.median(y[idx]))
    if med <= 0:
        return 0.0
    pos = [float(v) for j, v in enumerate(y[:i]) if (not censored[j]) and v > 0]
    cap = float(np.percentile(pos, 90)) if pos else med
    return min(med, cap)


def impute_aggressive(y: np.ndarray, censored: np.ndarray, i: int) -> float:
    """敏感性对照：所有删失月都补，取最近 3/6 个非删失月均值（不设上限）。"""
    for k in (3, 6):
        idx = [j for j in range(max(0, i - k), i) if not censored[j]]
        if idx:
            return float(np.mean(y[idx]))
    pos = [float(v) for j, v in enumerate(y[:i]) if not censored[j] and v > 0]
    return float(np.mean(pos)) if pos else 0.0


def cumulative(pred: np.ndarray, days: int, decision: date) -> float:
    w = F.window_weights(decision, days)
    # 训练止于最近完整月；预测 index 0 = 决策日所在月（与生产 forecast.py 一致）
    start_i = F.ym_index(decision.strftime("%Y-%m"))
    total = 0.0
    missing = []
    for mi, wt in w.items():
        k = mi - start_i
        if 0 <= k < len(pred):
            total += wt * float(pred[k])
        else:
            missing.append(F.index_ym(mi))
    if missing:
        raise ValueError(f"L{days} 窗口缺预测月 {missing}，拒绝静默截断")
    return total


def run(
    stock_path: str | Path = DEFAULT_STOCK,
    out_dir: str | Path = DEFAULT_OUT,
    uom_cache_path: str | Path = DEFAULT_UOM_CACHE,
    cfg: Config | None = None,
    backend: F.Backend | None | object = ...,
) -> Path:
    cfg = cfg or Config()
    if backend is ...:
        backend = F.load_backend()
    stock_path, out_dir, uom_cache_path = map(Path, (stock_path, out_dir, uom_cache_path))
    out_dir.mkdir(parents=True, exist_ok=True)

    stock = pd.read_parquet(stock_path)
    sday, monthly, meta = build_flags(stock)

    df, input_meta = F.load_disposition(F.DEFAULT_DISPOSITION)
    boundary = F.resolve_month_boundary(df)
    series, _, _, series_meta = F.build_series(df, boundary)
    coverage = pd.read_parquet(F.DEFAULT_COVERAGE).set_index("tongtool_sku", drop=False)
    cache = pd.read_parquet(uom_cache_path).set_index("item_code")

    uom: dict[str, tuple[str, str, str, bool]] = {}
    for sku in series:
        c = coverage.loc[sku] if sku in coverage.index else None
        uom[sku] = resolve_uom(c, cache)

    # UOM 口径审计（UOM-CANONICAL）
    audit_rows = []
    for sku in series:
        c = coverage.loc[sku] if sku in coverage.index else None
        item = "" if c is None or pd.isna(c.get("canonical_sku")) else str(c.get("canonical_sku"))
        cache_row = cache.loc[item] if item in cache.index else None
        stock_uom = "" if cache_row is None or pd.isna(cache_row.get("stock_uom")) else str(cache_row.get("stock_uom"))
        is_stock = None if cache_row is None or pd.isna(cache_row.get("is_stock_item")) else int(cache_row.get("is_stock_item"))
        uom_group = uom[sku][2]
        reason = ""
        if uom_group == "uom_conflict":
            reason = "stock_uom=套 但不是 TJ# bundle（is_stock_item != 0）"
        elif uom_group == "套":
            reason = "TJ# bundle（stock_uom=套, is_stock_item=0）"
        elif uom_group == "unknown":
            reason = "未映射/未证单位，不合计"
        audit_rows.append(
            {
                "tongtool_sku": sku,
                "canonical_sku": item,
                "stock_uom": stock_uom,
                "is_stock_item": is_stock,
                "uom_group": uom_group,
                "reason": reason,
            }
        )
    uom_audit = pd.DataFrame(audit_rows)

    # 月度销量（series 已完成 first..last 补零）
    sales_rows = []
    for sku, s in series.items():
        for m, v in zip(s.months, s.y):
            sales_rows.append((sku, m, float(v)))
    sales = pd.DataFrame(sales_rows, columns=["sku", "month", "sales_units"])
    monthly = monthly.merge(sales, on=["sku", "month"], how="left")
    monthly["uom_group"] = monthly["sku"].map(lambda s: uom.get(s, ("", "", "unknown", False))[2])

    # 30 天相关性复算（SKU 级；与 digest 的 observation 口径不同）
    daily_sales = df.groupby(['tongtool_sku', 'demand_date']).quantity.sum().reset_index()
    daily_sales = daily_sales.rename(columns={'tongtool_sku': 'sku'})
    daily_sales['demand_date'] = pd.to_datetime(daily_sales['demand_date'])
    check = thirty_day_check(sday, daily_sales)

    # 候选：删失月落在完整月内、历史 >=7、已证「个」
    complete_months = set(boundary["complete_months"])
    cand_months = monthly[monthly["censored"] & monthly["month"].isin(complete_months)].copy()
    hist = {sku: len(s.months) for sku, s in series.items()}
    cand_months = cand_months[cand_months["sku"].isin(series)]
    cand_months["history_months"] = cand_months["sku"].map(hist)
    cand = cand_months[cand_months["history_months"] >= cfg.min_history].copy()

    impact_rows: list[dict[str, Any]] = []
    for sku, g in cand.groupby("sku"):
        if uom.get(sku, ("", "", "unknown", False))[2] != "个":
            continue
        s = series[sku]
        months = s.months
        y = s.y.astype(float).copy()
        cens = np.zeros(len(months), dtype=bool)
        for m in g["month"]:
            if m in months:
                cens[months.index(m)] = True
        if not cens.any():
            continue

        # 保守：只补「删失且销量=0」的月，近期中位数 + P90 截顶
        y_cons = y.copy()
        cons_replaced, cons_added = 0, 0.0
        for i in np.where(cens)[0]:
            if y[i] > 1e-9:
                continue
            imp = impute_conservative(y, cens, i)
            if imp > 1e-9:
                y_cons[i] = imp
                cons_replaced += 1
                cons_added += imp
        # 敏感性：所有删失月都补，近期均值，无截顶
        y_aggr = y.copy()
        aggr_replaced, aggr_added = 0, 0.0
        for i in np.where(cens)[0]:
            imp = impute_aggressive(y, cens, i)
            new = max(float(y[i]), imp)
            if new > float(y[i]) + 1e-9:
                aggr_replaced += 1
                aggr_added += new - float(y[i])
            y_aggr[i] = new

        pred_b, method_b, _, _ = F.fit_predict_rule(y, cfg.horizon_months, backend, F.ForecastConfig())
        pred_c, method_c, _, _ = F.fit_predict_rule(y_cons, cfg.horizon_months, backend, F.ForecastConfig())
        pred_g, method_g, _, _ = F.fit_predict_rule(y_aggr, cfg.horizon_months, backend, F.ForecastConfig())
        if pred_b is None or pred_c is None or pred_g is None:
            continue
        rec: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "tongtool_sku": sku,
            "uom_group": "个",
            "history_months": len(months),
            "censored_months": int(cens.sum()),
            "censored_zero_months": int(((y == 0) & cens).sum()),
            "method_baseline": method_b,
            "method_conservative": method_c,
            "method_aggressive": method_g,
            "conservative_replaced_months": cons_replaced,
            "conservative_added_units": round(cons_added, 3),
            "aggressive_replaced_months": aggr_replaced,
            "aggressive_added_units": round(aggr_added, 3),
        }
        for d in (90, 180):
            b = cumulative(pred_b, d, cfg.decision_date)
            c = cumulative(pred_c, d, cfg.decision_date)
            a = cumulative(pred_g, d, cfg.decision_date)
            rec[f"p50_l{d}_baseline"] = round(b, 3)
            rec[f"p50_l{d}_conservative"] = round(c, 3)
            rec[f"p50_l{d}_aggressive"] = round(a, 3)
            rec[f"diff_l{d}_conservative"] = round(c - b, 3)
            rec[f"diff_l{d}_aggressive"] = round(a - b, 3)
            rec[f"pct_l{d}_conservative"] = None if b <= 1e-9 else round((c - b) / b, 4)
            rec[f"pct_l{d}_aggressive"] = None if b <= 1e-9 else round((a - b) / b, 4)
        impact_rows.append(rec)
    impact = pd.DataFrame(impact_rows)

    # 汇总（个组，两个补值方案）
    summary_rows: list[dict[str, Any]] = []
    if len(impact):
        for variant in ("conservative", "aggressive"):
            for d in (90, 180):
                b = impact[f"p50_l{d}_baseline"]
                a = impact[f"p50_l{d}_{variant}"]
                pct = impact[f"pct_l{d}_{variant}"].dropna()
                summary_rows.append(
                    {
                        "variant": variant,
                        "horizon_days": d,
                        "n_skus": int(len(impact)),
                        "sum_baseline": round(float(b.sum()), 3),
                        "sum_adjusted": round(float(a.sum()), 3),
                        "diff": round(float((a - b).sum()), 3),
                        "pct_of_baseline": None if b.sum() <= 1e-9 else round(float((a - b).sum() / b.sum()), 4),
                        "share_increased": round(float((a > b + 1e-9).mean()), 4),
                        "median_pct": None if not len(pct) else round(float(pct.median()), 4),
                        "p90_pct": None if not len(pct) else round(float(pct.quantile(0.9)), 4),
                    }
                )
    summary = pd.DataFrame(summary_rows)

    # 训练样本影响
    sample_rows = []
    if len(impact):
        total_months = int(impact["history_months"].sum())
        cens_months = int(impact["censored_months"].sum())
        cens_zero = int(impact["censored_zero_months"].sum())
        for variant in ("conservative", "aggressive"):
            sample_rows.append(
                {
                    "variant": variant,
                    "skus": int(len(impact)),
                    "history_months_total": total_months,
                    "censored_months": cens_months,
                    "censored_zero_months": cens_zero,
                    "censored_share_of_history": round(cens_months / total_months, 4) if total_months else None,
                    "replaced_months": int(impact[f"{variant}_replaced_months"].sum()),
                    "added_units": round(float(impact[f"{variant}_added_units"].sum()), 3),
                }
            )
    sample = pd.DataFrame(sample_rows)

    # 月度标记表：只保留观测覆盖月 + 有销量的 SKU；全部观测 SKU 的标记另存
    flag_out = monthly[
        [
            "sku", "month", "obs_dates", "zero_dates", "pos_dates", "min_avail", "max_avail",
            "high_zero_dates", "stockout_status", "both_states_sku", "censored", "sources",
            "sales_units", "uom_group",
        ]
    ].copy()

    # 写出
    flag_out.to_parquet(out_dir / "stockout_monthly_flags.parquet", index=False)
    impact.to_parquet(out_dir / "forecast_impact.parquet", index=False)
    impact.to_csv(out_dir / "forecast_impact.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "impact_summary.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(out_dir / "training_sample_impact.csv", index=False, encoding="utf-8-sig")
    check.to_csv(out_dir / "thirty_day_check.csv", index=False, encoding="utf-8-sig")
    uom_audit.to_csv(out_dir / "uom_audit.csv", index=False, encoding="utf-8-sig")

    outputs = []
    for name in (
        "stockout_monthly_flags.parquet",
        "forecast_impact.parquet",
        "forecast_impact.csv",
        "impact_summary.csv",
        "training_sample_impact.csv",
        "thirty_day_check.csv",
        "uom_audit.csv",
    ):
        p = out_dir / name
        outputs.append({"file": name, "sha256": _sha(p)})

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "output_dir": str(out_dir),
        "config": cfg.to_json(),
        "inputs": {
            "stock_observations": {"path": str(stock_path), "sha256": _sha(stock_path)},
            "disposition": {"path": str(F.DEFAULT_DISPOSITION), "sha256": _sha(Path(F.DEFAULT_DISPOSITION))},
            "coverage": {"path": str(F.DEFAULT_COVERAGE), "sha256": _sha(Path(F.DEFAULT_COVERAGE))},
            "uom_cache": {"path": str(uom_cache_path), "sha256": _sha(uom_cache_path)},
        },
        "stock_filter": {
            "warehouse_role": "primary_sellable",
            "zero_definition": "所有已观测 primary_sellable 仓 available 合计 <=0",
            "both_states_required": True,
        },
        "counts": meta | {
            "uom_groups": uom_audit["uom_group"].value_counts().to_dict(),
            "uom_conflict_skus": int((uom_audit["uom_group"] == "uom_conflict").sum()),
            "impact_skus": int(len(impact)),
            "censored_zero_months_in_sample": int(impact["censored_zero_months"].sum()) if len(impact) else 0,
        },
        "uom_policy": {
            "ref": "UOM-CANONICAL.md (2026-10-28)",
            "confirmed": "个/套分列；TJ#按套(stock_uom=套,is_stock_item=0)；PK#按皮壳1:1不是套；未知单位不合计",
            "main_group": "个",
            "excluded_from_aggregate": ["unknown", "uom_conflict", "套（单列）"],
        },
        "leakage": {
            "note": "只用截至 2026-09 的完整月做训练；库存观测 2026-04..10 仅用于标记；无未来销量进入训练。",
        },
        "code": {
            "git_head": _git_head(),
            "git_dirty": _git_dirty(),
            "module_sha256": _sha(Path(__file__)),
        },
        "versions": {
            "python": platform.python_version(),
            "numpy": F._version_of("numpy"),
            "pandas": F._version_of("pandas"),
            "statsforecast": F._version_of("statsforecast"),
        },
        "outputs": outputs,
        "caveats": [
            "库存是检查点（PJ 22 / WX 38 / EN 7 天），不是每日快照；标记是观察到的零库存，不是完整断货区间。",
            "只对同时有零/有库存观测的 SKU 标记删失；永久零库存 SKU 不硬造需求。",
            "补值方法：保守=只补删失零月、近期中位数+P90 截顶；敏感性=所有删失月均值无截顶；两者都是情景，不是需求恢复的已证估计。",
            "只比较训练输入与预测差异，没有 2026-10 以后的真实值，不能证明补值更准。",
            "未知 UOM 不合计；套组单列。",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 产物内报告
    lines = [
        "# 断货删失：标记与预测影响",
        "",
        f"> 生成：{manifest['generated_at']}　库存观测：{meta['date_min']}..{meta['date_max']}　"
        f"数据截止：{boundary['last_date']}",
        "",
        "## 口径确认",
        "",
        "已读 `UOM-CANONICAL.md`：**个/套分列；TJ# 按套（stock_uom=套、is_stock_item=0）；"
        "PK# 按皮壳 1:1 不是套；未知单位不合计。** 主表只算已证「个」。",
        "",
        "## UOM 口径审计",
        "",
    ]
    counts = uom_audit["uom_group"].value_counts().to_dict()
    conflicts = uom_audit[uom_audit["uom_group"] == "uom_conflict"]
    lines += [
        f"- 分组：{counts}。",
        f"- TJ# 套件：{int((uom_audit['uom_group'] == '套').sum())} 个（stock_uom=套, is_stock_item=0）→ 套。",
        f"- PK#：0 个销售 SKU；未把任何 PK# 计入套。",
        f"- 非 TJ# 但 stock_uom=套：**{len(conflicts)}** 个 → `uom_conflict`，不进入 套/个 合计"
        + ("：" + "、".join(conflicts["tongtool_sku"].tolist()) if len(conflicts) else "。"),
        f"- unknown：{int((uom_audit['uom_group'] == 'unknown').sum())} 个 → 不合计；本次影响样本只取已证「个」。",
        "",
    ]
    lines += [
        "## 标记",
        "",
        f"- primary_sellable 观测 {meta['observation_rows']:,} 行 / {meta['skus_observed']:,} SKU / "
        f"{meta['dates']} 个日期。",
        f"- 同时有零/有库存观测的 SKU：**{meta['skus_both_zero_positive']:,}**；"
        f"删失 SKU×月 **{meta['censored_sku_months']:,}**（{meta['censored_skus']:,} SKU）。",
        "- 零库存定义：该 SKU×日所有已观测 primary_sellable 仓 available 合计 <=0。",
        "",
        "## 样本影响（个组）",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
    ]
    if len(sample):
        r = sample.iloc[0]
        lines += [
            f"| 候选 SKU | {r.skus:,} |",
            f"| 历史完整月合计 | {r.history_months_total:,} |",
            f"| 其中删失月 | {r.censored_months:,}（{r.censored_share_of_history:.1%}） |",
            f"| 删失且销量=0 | {r.censored_zero_months:,} |",
        ]
        for srow in sample.itertuples(index=False):
            label = "保守（只补零月，中位+P90 截顶）" if srow.variant == "conservative" else "敏感性（所有删失月，均值无截顶）"
            lines.append(
                f"| {label}：补值月 / 增加量 | {srow.replaced_months:,} / {srow.added_units:,.1f} |"
            )
    lines += ["", "## 预测差异（L90/L180，个组）", "", "| 方案 | horizon | SKU | Σ基准 | Σ补值 | 差 | 差/基准 | 上升占比 | 中位涨幅 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary.itertuples(index=False):
        label = "保守" if r.variant == "conservative" else "敏感性"
        lines.append(
            f"| {label} | L{r.horizon_days} | {r.n_skus:,} | {r.sum_baseline:,.1f} | {r.sum_adjusted:,.1f} | "
            f"{r.diff:+,.1f} | {r.pct_of_baseline:+.2%} | {r.share_increased:.1%} | "
            f"{'—' if r.median_pct is None else f'{r.median_pct:+.1%}'} |"
        )
    lines += [
        "",
        "## 读法",
        "",
        "- 保守方案：只补「删失且销量=0」的月，用最近非删失月中位数并做 P90 截顶；",
        "  敏感性方案：所有删失月都按近期均值补、无截顶，用来展示方法依赖。",
        "- 这是**敏感性分析**，不是已证的需求恢复；没有 2026-10 以后真实值，不能证明补值更准。",
        "- 库存观测是检查点，标记的是「观察到的零库存月」，不是完整断货区间。",
        "- 未知 UOM 不合计；套组单列；不跨 UOM 相加。",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_dir


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="断货删失标记与预测影响")
    ap.add_argument("--stock", default=DEFAULT_STOCK)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--uom-cache", default=DEFAULT_UOM_CACHE)
    ap.add_argument("--min-history", type=int, default=7)
    args = ap.parse_args(argv)
    out = run(args.stock, args.out, args.uom_cache, Config(min_history=args.min_history))
    print(f"stockout censoring -> {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
