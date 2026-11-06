"""D5 v6.4 probability forecasts on current-owner demand (offline, read-only).

What changes vs v6.3 (external review F1)
- The prediction target for US is the **synchronized product total** across
  USNJ/USTX. Residual calibration now forecasts that same total at every
  rolling origin instead of concatenating per-pool residuals (which mixed two
  different targets and double-counted the same calendar window).
- Dual-history products no longer contribute two per-pool errors to the same
  current-owner key; one total-demand residual per origin is used.
- Non-US pools keep the per-pool/product calibration path.
- q95 still has one entry point: `1_预测.q95`; the 95% number remains
  retrospective historical coverage, not a service/future guarantee.
- All source series come from D3b v3.5 sidecar parquet files.

No EN/Tongtool writes, no ordering, no push.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from supply_netting.temporal_demand import (
    forecast_cache, choose_model, demand_quantiles, calendar_total,
    fast_ets, nonoverlapping_starts, available_residuals,
)

VERSION = "D5-v6.5-current-owner-60cm-short-history-2026-11-06"
KEY = ["product_id", "pool", "physical_form", "canonical_uom"]
DATA = Path("D:/Work/fzh-order-store")
BA = DATA / "analysis"
US_POOLS = ("美东USNJ", "美中USTX")
UNASSIGNED = "US_unassigned"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path):
    spec = importlib.util.spec_from_file_location("d3_repaired_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def market_of(pool: str) -> str:
    if pool in US_POOLS or pool == UNASSIGNED:
        return "US"
    if pool == "波兰":
        return "PL"
    if str(pool).startswith("CG"):
        return "CG"
    return "OTHER"


def us_total_inputs(asof_keys, monthly, daily):
    """Synchronized US product total series for residual calibration.

    One synthetic key per (product, form, uom) whose as-of history sits in
    USNJ and/or USTX. Pool label `US_total` never leaks into forecast keys.
    """
    total_keys = sorted({(pid, "US_total", form, uom)
                         for pid, pool, form, uom in asof_keys if pool in US_POOLS})
    total_monthly = defaultdict(float)
    for (key, month), qty in monthly.items():
        if key[1] in US_POOLS:
            total_monthly[((key[0], "US_total", key[2], key[3]), month)] += qty
    total_daily = {}
    for key in total_keys:
        parts = [k for k in asof_keys
                 if k[0] == key[0] and k[2] == key[2] and k[3] == key[3]
                 and k[1] in US_POOLS]
        series = None
        for part in parts:
            s = daily.get(part)
            if s is not None:
                series = s.copy() if series is None else series.add(s, fill_value=0)
        if series is not None:
            total_daily[key] = series.sort_index()
    return total_keys, dict(total_monthly), total_daily


def load_series(path: Path) -> tuple[dict, dict]:
    """monthly[(key, month_int)] and daily[key] = Series(date → qty)."""
    frame = pd.read_parquet(path)
    req = set(KEY + ["date", "month", "qty"])
    if req - set(frame.columns):
        raise ValueError(f"series missing columns: {sorted(req - set(frame.columns))}")
    frame["month"] = pd.to_numeric(frame["month"], errors="raise").astype(int)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date
    frame["_key"] = list(zip(frame["product_id"].astype(str), frame["pool"].astype(str),
                             frame["physical_form"].astype(str),
                             frame["canonical_uom"].astype(str)))
    monthly = frame.groupby(["_key", "month"], observed=True)["qty"].sum().to_dict()
    daily = {k: g.groupby("date")["qty"].sum().sort_index()
             for k, g in frame.groupby("_key", observed=True)}
    return monthly, daily


def load_inputs(args):
    d3b = pd.ExcelFile(args.d3b)
    cls_asof = pd.read_excel(d3b, sheet_name="3a_分类_asof")
    cls_cur = pd.read_excel(d3b, sheet_name="3_分类")
    for frame, name in ((cls_asof, "as-of"), (cls_cur, "current")):
        frame[KEY] = frame[KEY].astype(str)
        if frame.duplicated(KEY).any():
            raise ValueError(f"duplicate {name} target identity")
    asof_keys = sorted(set(map(tuple, cls_asof[KEY].values)))
    cur_keys = sorted(set(map(tuple, cls_cur[KEY].values)))
    monthly_asof, daily_asof = load_series(Path(args.series_asof))
    monthly_cur, daily_cur = load_series(Path(args.series_current))
    cens = pd.read_excel(args.censor, sheet_name="2_删失")
    cens_set = set(zip(cens["product_id"].astype(str),
                       cens["month"].astype(str).str.replace("-", "", regex=False)))
    return cls_asof, cls_cur, asof_keys, cur_keys, monthly_asof, daily_asof, \
        monthly_cur, daily_cur, cens_set


def rolling_validation(keys, monthly, daily, cens, months, last_complete,
                       models, funcs, horizon_days):
    """Chronological as-of validation: every outcome is available before use."""
    records = []
    for key_index, key in enumerate(keys):
        y = np.array([monthly.get((key, int(m)), 0.0) for m in months], dtype=float)
        positives = np.flatnonzero(y > 0)
        if not len(positives):
            continue
        y[:positives[0]] = np.nan
        for i, month in enumerate(months):
            if (key[0], month) in cens:
                y[i] = np.nan
        cache = forecast_cache(y, funcs)
        for cutoff in range(12, len(months)):
            start = date(int(months[cutoff][:4]), int(months[cutoff][4:]), 1)
            if start < date(2024, 1, 1):
                continue
            model, selection = choose_model(y, cache, cutoff)
            if model == "none":
                continue
            fc = cache[cutoff][model]
            for days in horizon_days:
                end = start + timedelta(days=days)
                if end > last_complete:
                    continue
                test_months = [i for i, month in enumerate(months)
                               if start <= date(int(month[:4]), int(month[4:]), 1) < end]
                if not all(np.isfinite(y[i]) for i in test_months):
                    continue  # censored outcome cannot be treated as observed truth
                point = calendar_total(fc, start, days)
                series = daily.get(key)
                actual = float(series.loc[start:end - timedelta(days=1)].sum()) \
                    if series is not None else 0.0
                naive_fc = cache[cutoff].get("naive")
                baseline = calendar_total(naive_fc, start, days) \
                    if naive_fc is not None else np.nan
                records.append(dict(
                    key=key, start=start, available_at=end, days=days,
                    point=point, actual=actual, model=model, baseline_point=baseline,
                    residual=(actual - point) / days,
                    selection_basis=selection["basis"]))
        if (key_index + 1) % 200 == 0:
            print(json.dumps({"phase": "validate", "keys": key_index + 1,
                              "total": len(keys)}), flush=True)
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--d3b", default=str(BA / "D_历史归一与回测_D3b_v3_7_2026-11-06.xlsx"))
    ap.add_argument("--series-asof", default=str(BA / "D3b_v3_7_series_asof_2026-11-06.parquet"))
    ap.add_argument("--series-current",
                    default=str(BA / "D3b_v3_7_series_current_2026-11-06.parquet"))
    ap.add_argument("--d3-script", default=str(Path(__file__).with_name(
        "d3b_history_backtest_v3_7_20261106.py")))
    ap.add_argument("--censor", default=str(BA / "D_销量清洗_v3_2026-11-02.xlsx"))
    ap.add_argument("--as-of", default="2026-11-02")
    ap.add_argument("--out-dir", default=str(BA / "D5v6_5-60cm"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    as_of = date.fromisoformat(args.as_of)
    models = load_module(args.d3_script)
    (cls_asof, cls_cur, asof_keys, cur_keys, monthly_asof, daily_asof,
     monthly_cur, daily_cur, cens) = load_inputs(args)
    # complete source months only
    last_complete = date(as_of.year, as_of.month, 1)
    months = [m for m in models.OBS_MONTHS
              if date(int(m[:4]), int(m[4:]), 1) < last_complete]
    if not months:
        raise ValueError("no complete history months")
    horizon_days = (97, 157)
    funcs = dict(models.BASELINES, **models.NEW_MODELS)
    funcs["ets_ann"] = fast_ets

    # ---------- 1) as-of chronological validation (historical truth only)
    eval_records = rolling_validation(asof_keys, monthly_asof, daily_asof, cens,
                                      months, last_complete, models, funcs, horizon_days)
    if not eval_records:
        raise ValueError("no as-of historical windows")
    key_banks = defaultdict(list)
    product_banks = defaultdict(list)
    market_banks = defaultdict(list)
    for r in eval_records:
        pid, pool, form, uom = r["key"]
        days = r["days"]
        key_banks[((pool, form, uom), days)].append(r)
        product_banks[(pid, form, uom, days)].append(r)
        market_banks[(market_of(pool), form, uom, days)].append(r)
    # backward-compatible alias used in messages
    banks = market_banks

    # F1: calibrate the same synchronized US total that current keys forecast.
    total_keys, total_monthly, total_daily = us_total_inputs(
        asof_keys, monthly_asof, daily_asof)
    total_records = rolling_validation(total_keys, total_monthly, total_daily, cens,
                                       months, last_complete, models, funcs, horizon_days)
    us_total_banks = defaultdict(list)
    us_total_market_banks = defaultdict(list)
    us_total_market_uom_banks = defaultdict(list)
    for r in total_records:
        pid, _, form, uom = r["key"]
        us_total_banks[(pid, form, uom, r["days"])].append(r)
        us_total_market_banks[("US", form, uom, r["days"])].append(r)
        us_total_market_uom_banks[("US", uom, r["days"])].append(r)
    print(json.dumps({"phase": "us_total_validation", "keys": len(total_keys),
                      "windows": len(total_records)}), flush=True)

    def residuals_asof(key, days, cutoff):
        pid, pool, form, uom = key
        own = available_residuals(key_banks[((pool, form, uom), days)], cutoff)
        if len(own) >= 30:
            return own, "asof_pool_form_uom", len(own)
        prod = available_residuals(product_banks[(pid, form, uom, days)], cutoff)
        if len(prod) >= 30:
            return prod, "asof_product_any_pool", len(prod)
        market = available_residuals(market_banks[(market_of(pool), form, uom, days)],
                                     cutoff)
        if len(market) >= 30:
            return market, "asof_market_form_uom", len(market)
        return [], "none", len(market)

    evaluation = []
    for row in eval_records:
        residuals, source, count = residuals_asof(row["key"], row["days"], row["start"])
        qs = demand_quantiles(row["point"], residuals, row["days"])
        evaluation.append(dict(
            zip(KEY, row["key"]), start=row["start"].isoformat(),
            outcome_available_at=row["available_at"].isoformat(),
            horizon=row["days"], model=row["model"], actual=row["actual"],
            point_forecast=row["point"], baseline_point=row["baseline_point"],
            calibration_source=source, calibration_n=count, **qs))
    ev = pd.DataFrame(evaluation, columns=KEY + [
        "start", "outcome_available_at", "horizon", "model", "actual",
        "point_forecast", "baseline_point", "calibration_source", "calibration_n",
        "q10", "q50", "q85", "q90", "q95"])

    # ---------- 2) current-owner forecasts (prediction target)
    def residuals_current(key, days):
        pid, pool, form, uom = key
        if pool in US_POOLS:
            total = available_residuals(us_total_banks[(pid, form, uom, days)], as_of)
            if len(total) >= 30:
                return total, "asof_us_total_product", len(total)
            total_market = available_residuals(
                us_total_market_banks[("US", form, uom, days)], as_of)
            if len(total_market) >= 30:
                return total_market, "asof_us_total_market_form_uom", len(total_market)
            uom_pool = available_residuals(
                us_total_market_uom_banks[("US", uom, days)], as_of)
            if len(uom_pool) >= 30:
                return uom_pool, "asof_us_total_market_uom_short_history", len(uom_pool)
            return [], "none", len(uom_pool)
        prod = available_residuals(product_banks[(pid, form, uom, days)], as_of)
        if len(prod) >= 30:
            return prod, "asof_product_any_pool", len(prod)
        market = available_residuals(
            market_banks[(market_of(pool), form, uom, days)], as_of)
        if len(market) >= 30:
            return market, "asof_market_form_uom", len(market)
        return [], "none", len(market)

    owner_meta = {(r.product_id, r.pool, r.physical_form, r.canonical_uom):
                  dict(owner_basis=str(getattr(r, "owner_basis", "")),
                       owner_reason=str(getattr(r, "owner_reason", "")),
                       demand_pattern=str(getattr(r, "demand_pattern", "")),
                       eligible=bool(getattr(r, "eligible", False)))
                  for r in cls_cur.itertuples(index=False)}
    predicted, service = [], []
    for key_index, key in enumerate(cur_keys):
        y = np.array([monthly_cur.get((key, int(m)), 0.0) for m in months], dtype=float)
        positives = np.flatnonzero(y > 0)
        if not len(positives):
            current = dict(model="none", predictions=None, reason="no_observed_history")
        else:
            y[:positives[0]] = np.nan
            for i, month in enumerate(months):
                if (key[0], month) in cens:
                    y[i] = np.nan
            cache = forecast_cache(y, funcs)
            model, selection = choose_model(y, cache, len(y))
            current = dict(model=model, predictions=cache[len(y)].get(model),
                           reason=selection["basis"])
        meta = owner_meta.get(key, {})
        for days in horizon_days:
            point = calendar_total(current["predictions"], as_of, days) \
                if current["predictions"] is not None else np.nan
            residuals, source, count = residuals_current(key, days)
            qs = demand_quantiles(point, residuals, days)
            base = dict(zip(KEY, key), key_version="D3b-v3.5-current-owner-2026-11-03",
                        horizon=days, horizon_days=days, point_forecast=point,
                        p10=qs["q10"], p50=qs["q50"] if np.isfinite(qs["q50"]) else point,
                        p90=qs["q90"], q85=qs["q85"], q90=qs["q90"], q95=qs["q95"],
                        model=current["model"], adopted_model=current["model"],
                        fallback_model="", demand_basis="current_owner_observed_no_censor_imputation",
                        interval_method="asof_chronological_horizon_residual",
                        interval_level=source, calibration_status=(
                            "empirical_time_ordered" if np.isfinite(qs["q95"])
                            else "interval_uncalibrated"),
                        calibration_n=count,
                        service_validation_status="retrospective_historical_coverage_not_future_guarantee",
                        q95_source="1_预测.q95",
                        owner_basis=meta.get("owner_basis", ""),
                        owner_status=("unassigned" if key[1] == UNASSIGNED else "owner_known"),
                        owner_reason=meta.get("owner_reason", ""),
                        demand_pattern=meta.get("demand_pattern", ""),
                        manual_review_required=True, auto_order=False,
                        seasonality_status="not_overridden", promo_status="unknown",
                        selection_basis=current["reason"])
            predicted.append(base)
            for level in (85, 90, 95):
                service.append(dict(zip(KEY, key), horizon=days,
                                    service_level=level / 100.,
                                    quantile=base[f"q{level}"],
                                    q95_source="1_预测.q95" if level == 95 else "",
                                    basis_level=source,
                                    calibrated="否：回溯历史覆盖，非服务承诺"))
        if (key_index + 1) % 200 == 0:
            print(json.dumps({"phase": "forecast", "keys": key_index + 1,
                              "total": len(cur_keys)}), flush=True)
    pred, svc = pd.DataFrame(predicted), pd.DataFrame(service)

    # ---------- 3) retrospective coverage (as-of only)
    coverage = []
    for days in horizon_days:
        frame = ev[ev.horizon == days]
        spaced = set(nonoverlapping_starts(
            [date.fromisoformat(x) for x in frame.start.unique()], days))
        for scope, part in (("all", frame),
                            ("nonoverlapping_dates",
                             frame[frame.start.isin([d.isoformat() for d in spaced])])):
            for level in (85, 90, 95):
                valid = part[part[f"q{level}"].notna()]
                if valid.empty:
                    continue
                delta = valid.actual - valid[f"q{level}"]
                positive = valid.actual > 0
                coverage.append(dict(
                    horizon=days, level=level / 100., scope=scope, n=len(valid),
                    keys=len(valid[KEY].drop_duplicates()),
                    coverage=float((delta <= 0).mean()),
                    coverage_positive=float((delta[positive] <= 0).mean())
                    if positive.any() else np.nan,
                    mean_shortfall=float(delta.clip(lower=0).mean()),
                    mean_excess=float((-delta).clip(lower=0).mean()),
                    point_mae=float((valid.actual - valid.point_forecast).abs().mean()),
                    naive_mae=float((valid.actual - valid.baseline_point).abs().mean()),
                    basis="as-of historical warehouse pool; retrospective only"))

    input_report = pd.DataFrame([
        dict(sheet="keys_asof_backtest", rows=len(asof_keys),
             note="历史仓库池；仅用于回测"),
        dict(sheet="keys_current_forecast", rows=len(cur_keys),
             note="current-owner 键；预测目标"),
        dict(sheet="series_asof_rows", rows=int(len(pd.read_parquet(args.series_asof))),
             note="D3b v3.5 as-of 侧车"),
        dict(sheet="series_current_rows", rows=int(len(pd.read_parquet(args.series_current))),
             note="D3b v3.5 current-owner 侧车"),
        dict(sheet="historical_windows", rows=len(ev), note="as-of 滚动窗"),
        dict(sheet="forecast_rows", rows=len(pred), note="current-owner 预测"),
    ])

    summary = dict(
        out=None, keys_asof=len(asof_keys), keys_current=len(cur_keys),
        forecast_rows=len(pred), historical_windows=len(ev),
        models=pred["model"].value_counts().to_dict(),
        owner_status=pred.drop_duplicates(KEY)["owner_status"].value_counts().to_dict(),
        q95_finite=int(pred["q95"].notna().sum()),
        no_observed_history=int((pred["model"] == "none").sum()),
        coverage=coverage, as_of=args.as_of,
        source_series="D3b-v3.5 current-owner (forecast) / as-of (validation)")

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
        print("DRY-RUN：未写 xlsx / 报告 / manifest")
        return 0

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    xlsx = out / "D_概率与服务_D5_v6_5_2026-11-06.xlsx"
    manifest = dict(
        schema_version="demand-forecast/v1", rule_version=VERSION,
        as_of=args.as_of, generated_at=datetime.now(timezone.utc).isoformat(),
        rows=len(pred), target_keys=len(cur_keys), asof_validation_keys=len(asof_keys),
        historical_windows=len(ev),
        demand_basis="current-owner restatement; as-of only for historical validation",
        q95_single_entry="1_预测.q95",
        no_service_guarantee=True,
        service_label="retrospective historical coverage, not a future service promise",
        minimum_key_calibration_samples=30, minimum_pool_calibration_samples=30,
        source_history_last_complete_month=months[-1],
        mapping_mode="current owner B r10; frozen D3b v3.5 identity bridge",
        calibration_target=("US: synchronized product total across USNJ/USTX "
                            f"({len(total_keys)} total keys, {len(total_records)} windows); "
                            "non-US: pool/product"),
        us_total_validation_keys=len(total_keys),
        us_total_validation_windows=len(total_records),
        inputs={name: dict(path=str(path), sha256=sha(path)) for name, path in (
            ("d3b", args.d3b), ("series_asof", args.series_asof),
            ("series_current", args.series_current), ("censor", args.censor))},
        code={str(p): sha(p) for p in (
            Path(__file__), Path(args.d3_script),
            Path(__file__).parents[1] / "supply_netting/temporal_demand.py")})
    summary["out"] = str(out)
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        pred.to_excel(writer, sheet_name="1_预测", index=False)
        svc.to_excel(writer, sheet_name="3_服务水平", index=False)
        pd.DataFrame(coverage).to_excel(writer, sheet_name="4_时间验证", index=False)
        input_report.to_excel(writer, sheet_name="5_输入去向", index=False)
    pred.to_parquet(out / "forecast.parquet", index=False)
    ev.to_parquet(out / "historical_windows.parquet", index=False)
    report = dict(**{k: v for k, v in manifest.items() if k not in ("inputs", "code")},
                  coverage=coverage, models=summary["models"])
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    manifest["outputs"] = {p.name: dict(sha256=sha(p), bytes=p.stat().st_size)
                           for p in out.iterdir() if p.is_file()}
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
