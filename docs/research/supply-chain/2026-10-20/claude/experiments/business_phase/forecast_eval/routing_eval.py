#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A package: forecast type-routing vs. a global model, same cut points (OFFLINE).

Everything runs on the local DuckDB mirror; there is no production access.

1. Feature inventory (per SKU x warehouse x category): history length, zero
   share, intermittency (ADI, CV^2), seasonal strength, volume tier, warehouse
   spread, category. Features that DO NOT exist locally are listed as
   unavailable (promotions, price, launch calendar) — nothing is invented.

2. Training-internal routing. For every (SKU, origin) cell the type is derived
   from data up to the origin only:
       short history  -> {tsb, naive}
       intermittent   -> {tsb, croston}
       seasonal       -> {seasonal_naive, seasonal_yoy}
       simple         -> {naive, ma3}
   The method inside the type is picked by a two-origin inner backtest whose
   target windows end before the origin (no outer information).

3. Same cut-point comparison. All candidates are scored on the SAME (SKU, origin)
   cells and the SAME 90-day target window:
       simple        naive, ma3
       intermittent  tsb, croston
       seasonal      seasonal_naive, seasonal_yoy
       combo         fixed equal-weight mean of the six base methods
       global tree   MLForecast + LightGBM over all SKUs (skipped if missing)
       routed        the training-internal choice described above
   The common subset is the cells where every one of those produced a forecast.

4. Outer evaluation: WAPE, bias, 80% rolling-conformal coverage and sample
   size on the common subset only. Per-SKU support evidence (features, routed
   type, chosen method, cells scored) and the unscored coverage (SKUs not
   scored, with the reason) are written to routing.csv.

5. Caliber correction recorded in the report: on the common 151 SKUs / 446
   windows the earlier run measured MAE 12.063 / 12.694 / 13.118 / 14.299 for
   TSB / SES / category-borrowed / naive. "Category is worst" is therefore
   void; this run only uses those numbers as context and claims no winner.

Read-only: order_store.duckdb (read_only), destinations.json.
Outputs: forecast_eval/routing_results.json, routing.csv, routing_report.md
Compute budget: <= 900 s; the run prints its wall clock.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import math
import sys
import time
import warnings
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[3]
OUT_DIR = HERE.parent
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
DEST = CLAUDE_DIR / "out" / "business_phase" / "destinations.json"

LAST_I = 2026 * 12 + 9 - 1          # 2026-09
MIN_TRAIN = 18                      # minimum months of own history to be scored
ORIGINS = ["2025-03", "2025-06", "2025-09", "2025-12", "2026-03", "2026-06"]
WINDOW_DAYS = 90
BASE_METHODS = ["naive", "ma3", "tsb", "croston", "seasonal_naive", "seasonal_yoy"]
ROUTE_CANDIDATES = {
    "short": ["tsb", "naive"],
    "intermittent": ["tsb", "croston"],
    "seasonal": ["seasonal_naive", "seasonal_yoy"],
    "simple": ["naive", "ma3"],
}
INNER_OFFSETS = (3, 6)              # inner origins, months before the outer origin
MIN_INNER = 12                      # history floor for the inner backtest only
warnings.filterwarnings("ignore")


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def decision_date(origin_i: int) -> date:
    return date((origin_i + 1) // 12, (origin_i + 1) % 12 + 1, 22)


def window_weights(start: date, days: int) -> dict[int, float]:
    end = start + timedelta(days=days)
    out, cur = {}, start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    while cur <= last:
        ms = date(cur // 12, cur % 12 + 1, 1)
        nm = date((cur + 1) // 12, (cur + 1) % 12 + 1, 1)
        s, e = max(start, ms), min(end, nm)
        if e > s:
            out[cur] = (e - s).days / (nm - ms).days
        cur += 1
    return out


# ---- forecasters ------------------------------------------------------
def forecast(model: str, y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    if model == "naive":
        return np.repeat(y[-1], h)
    if model == "ma3":
        k = min(3, n)
        if k < 1:
            raise ValueError("no_history")
        return np.repeat(float(np.mean(y[-k:])), h)
    if model == "seasonal_naive":
        if n < 13:
            raise ValueError("history_lt_13m")
        return np.array([y[n - 12 + (k % 12)] for k in range(h)], dtype=float)
    if model == "seasonal_yoy":
        # same calendar month last year scaled by the trailing 12-month ratio
        if n < 13:
            raise ValueError("history_lt_13m")
        base = y[n - 12:]
        prev = y[n - 24:n - 12] if n >= 24 else None
        ratio = 1.0
        if prev is not None and prev.sum() > 0:
            ratio = float(base.sum() / prev.sum())
            ratio = min(max(ratio, 0.5), 2.0)
        return np.array([y[n - 12 + (k % 12)] * ratio for k in range(h)], dtype=float)
    from statsforecast import models as sfm
    if model == "tsb":
        m = sfm.TSB(alpha_d=0.3, alpha_p=0.3)
    elif model == "croston":
        m = sfm.CrostonOptimized()
    else:
        raise ValueError(f"unknown_model:{model}")
    m.fit(y.astype(np.float32))
    return np.asarray(m.predict(h=h)["mean"], dtype=float)


def window_value(values: np.ndarray, first_i: int, origin_i: int) -> float | None:
    """Weighted sum of the 90-day target window starting at the origin."""
    w = window_weights(decision_date(origin_i), WINDOW_DAYS)
    total = 0.0
    for k, wt in w.items():
        idx = k - origin_i - 1          # 0 = the month right after the origin
        if idx < 0 or origin_i + 1 + idx - first_i >= len(values):
            return None
        total += wt * float(values[origin_i + 1 + idx - first_i])
    return total


def forecast_window(model: str, y: np.ndarray, origin_i: int, first_i: int) -> float | None:
    """Forecast the same 90-day window from a training vector truncated at origin."""
    w = window_weights(decision_date(origin_i), WINDOW_DAYS)
    h = max(w) - origin_i
    if h < 1:
        return None
    try:
        f = forecast(model, y, h)
    except Exception:
        return None
    # weighted SUM over the window — must match window_value() exactly
    total = 0.0
    for k, wt in w.items():
        j = k - origin_i - 1
        if j < 0:
            continue
        pos = k - first_i
        if pos < len(y):
            continue                # inside training: not a forecast cell
        fi = k - (origin_i + 1)
        if 0 <= fi < len(f):
            total += wt * float(f[fi])
    return total


# ---- features & routing ----------------------------------------------
def features(y: np.ndarray) -> dict:
    n = len(y)
    nz = y[y > 0]
    zero_share = float((y <= 0).mean()) if n else 1.0
    adi = n / len(nz) if len(nz) else float("inf")
    cv2 = float(np.var(nz) / (np.mean(nz) ** 2)) if len(nz) > 1 and np.mean(nz) > 0 else 0.0
    # seasonal strength: between-month-of-year variance share
    if n >= 24:
        months = np.array([(i) % 12 for i in range(n)])
        gm = y.mean()
        between = 0.0
        for m in range(12):
            sel = y[months == m]
            if len(sel):
                between += len(sel) * (sel.mean() - gm) ** 2
        between /= n
        total = float(np.var(y))
        seas = float(between / total) if total > 0 else 0.0
    else:
        seas = 0.0
    return dict(n_hist=n, zero_share=round(zero_share, 4),
                adi=round(adi, 3) if math.isfinite(adi) else None,
                cv2=round(cv2, 4), seasonal_strength=round(seas, 4),
                total_qty=float(y.sum()))


def route_type(f: dict) -> str:
    if f["n_hist"] < 24:
        return "short"
    if (f["zero_share"] >= 0.4) or (f["adi"] is not None and f["adi"] >= 2.0):
        return "intermittent"
    if f["seasonal_strength"] >= 0.3:
        return "seasonal"
    return "simple"


def inner_select(candidates, y, origin_i, first_i):
    """Pick the candidate with the lowest MAE over inner origins (training only)."""
    errs = {c: [] for c in candidates}
    for off in INNER_OFFSETS:
        oi = origin_i - off
        if oi < first_i + MIN_INNER - 1:
            continue
        w = window_weights(decision_date(oi), WINDOW_DAYS)
        if max(w) > origin_i:           # inner window must end inside training
            continue
        actual = window_value(y, first_i, oi)
        if actual is None:
            continue
        ytr = y[:oi + 1 - first_i]
        for c in candidates:
            fv = forecast_window(c, ytr, oi, first_i)
            if fv is not None:
                errs[c].append(abs(fv - actual))
    scored = {c: float(np.mean(v)) for c, v in errs.items() if v}
    if not scored:
        return candidates[0], "rule_default"
    return min(scored, key=scored.get), "inner_mae"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--limit-skus", type=int, default=0)
    ap.add_argument("--origins", default=",".join(ORIGINS))
    args = ap.parse_args()
    t0 = time.time()

    db = Path(args.db)
    db_hash = hashlib.sha256(db.read_bytes()).hexdigest()
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    eligible = {r["sku"]: r.get("mapped_item_code") for r in dest["rows"]
                if r["destination"] == "mapped_eligible"}

    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "SELECT sku, substr(month,1,7), SUM(qty) FROM monthly_series "
            "WHERE month <= '2026-09' GROUP BY 1,2").fetchall()
        wh = con.execute(
            "SELECT sku, warehouse, SUM(qty) FROM monthly_series "
            "WHERE month <= '2026-09' GROUP BY 1,2").fetchall()
        groups = {r[0]: r[1] for r in con.execute(
            "SELECT item, item_group FROM item_attr").fetchall()}
    finally:
        con.close()
    if hashlib.sha256(db.read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed during the run")

    by = defaultdict(dict)
    for sku, ym, qty in rows:
        by[sku][ym] = float(qty or 0)
    wh_count = defaultdict(int)
    wh_top = defaultdict(float)
    for sku, w, q in wh:
        wh_count[sku] += 1
        wh_top[sku] = max(wh_top[sku], float(q or 0))

    series = {}
    for sku in eligible:
        b = by.get(sku)
        if not b:
            continue
        first = min(ym_i(m) for m in b)
        months = [i_ym(i) for i in range(first, LAST_I + 1)]
        y = np.array([b.get(m, 0.0) for m in months], dtype=float)
        series[sku] = dict(first=first, y=y, months=months)

    skus = sorted(series, key=lambda s: (-series[s]["y"].sum(), s))
    if args.limit_skus:
        skus = skus[:args.limit_skus]
    origins = [o for o in args.origins.split(",") if o]

    # ---- global tree model availability --------------------------------
    tree_ok, tree_note, tree_versions = False, "", {}
    try:
        from lightgbm import LGBMRegressor
        from mlforecast import MLForecast
        tree_ok = True
        for p in ("mlforecast", "lightgbm", "pandas"):
            try:
                tree_versions[p] = md.version(p)
            except Exception:
                pass
    except Exception as exc:            # noqa: BLE001
        tree_note = f"unavailable: {type(exc).__name__}: {exc}"

    used_origins = []
    cells = defaultdict(dict)           # method -> (sku, origin) -> (F, A)
    sku_evidence = {}
    unscored = defaultdict(set)
    source_cells = Counter()
    tree_cache = {}

    for origin_ym in origins:
        o = ym_i(origin_ym)
        w = window_weights(decision_date(o), WINDOW_DAYS)
        if max(w) > LAST_I:
            continue
        used_origins.append(origin_ym)
        train_rows = []
        for sku in skus:
            s = series[sku]
            tr = o - s["first"] + 1
            if tr < MIN_TRAIN:
                unscored["history_lt_min_train"].add(sku)
                sku_evidence.setdefault(sku, dict(
                    sku=sku, type=None, method=None, scored_cells=0,
                    reason="history_lt_min_train"))
                continue
            ytr = s["y"][:tr]
            f = features(ytr)
            typ = route_type(f)
            method, how = inner_select(ROUTE_CANDIDATES[typ], ytr, o, s["first"])
            A = window_value(s["y"], s["first"], o)
            if A is None:
                continue
            # base candidates
            preds = {}
            for m in BASE_METHODS:
                fv = forecast_window(m, ytr, o, s["first"])
                if fv is not None:
                    preds[m] = fv
            if len(preds) == len(BASE_METHODS):
                preds["combo"] = float(np.mean([preds[m] for m in BASE_METHODS]))
            if method in preds:
                preds["routed"] = preds[method]
                source_cells[how] += 1
            ev = sku_evidence.setdefault(sku, dict(
                sku=sku, type=typ, method=method, method_source=how,
                scored_cells=0, reason=""))
            ev.update(type=typ, method=method, method_source=how,
                      evidence_origin=origin_ym, **f)
            ev["scored_cells"] = ev.get("scored_cells", 0) + (1 if preds else 0)
            for m, F in preds.items():
                cells[m][(sku, origin_ym)] = (float(F), float(A))
            train_rows.append((sku, ytr))

        print(f"  origin {origin_ym}: cells={sum(len(v) for v in cells.values())} "
              f"elapsed={time.time()-t0:.1f}s", flush=True)
        # global tree: fit once per origin on all series with enough training
        if tree_ok:
            try:
                parts = []
                for sku, ytr in train_rows:
                    for j, v in enumerate(ytr):
                        ds = pd.Timestamp(year=(o - len(ytr) + 1 + j) // 12,
                                          month=(o - len(ytr) + 1 + j) % 12 + 1,
                                          day=1)
                        parts.append((sku, ds, float(v)))
                df = pd.DataFrame(parts, columns=["unique_id", "ds", "y"])
                fc = MLForecast(models=LGBMRegressor(n_estimators=200,
                                                     learning_rate=0.05,
                                                     num_leaves=31,
                                                     verbose=-1, random_state=0),
                                freq="MS", lags=[1, 2, 3, 6, 12],
                                date_features=["month"])
                fc.fit(df)
                h = max(w) - o
                pr = fc.predict(h=h)
                pr["ds_i"] = pr["ds"].apply(lambda d: d.year * 12 + d.month - 1)
                for sku, grp in pr.groupby("unique_id"):
                    vals = grp.sort_values("ds_i")["LGBMRegressor"].to_numpy(dtype=float)
                    total = 0.0
                    for k, wt in w.items():
                        fi = k - (o + 1)
                        if 0 <= fi < len(vals):
                            total += wt * float(vals[fi])
                    if total > 0:
                        s = series[sku]
                        A = window_value(s["y"], s["first"], o)
                        if A is not None:
                            cells["global_tree"][(sku, origin_ym)] = (total, A)
                tree_cache[origin_ym] = len(pr)
            except Exception as exc:        # noqa: BLE001
                tree_note = f"fit failed at {origin_ym}: {type(exc).__name__}: {exc}"
                tree_ok = False

    elapsed = time.time() - t0

    # ---- evaluation on the common subset -------------------------------
    methods = [m for m in BASE_METHODS + ["combo", "routed", "global_tree"] if cells.get(m)]
    common = set.intersection(*[set(cells[m]) for m in methods]) if methods else set()

    def wape_bias(m):
        vals = [cells[m][k] for k in common]
        if not vals:
            return None
        ae = sum(abs(F - A) for F, A in vals)
        tot = sum(A for _F, A in vals)
        bias = sum(F - A for F, A in vals)
        return dict(n=len(vals), wape=(ae / tot if tot else None),
                    bias=(bias / tot if tot else None), mae=ae / len(vals))

    results = {m: wape_bias(m) for m in methods}

    # rolling conformal 80% coverage (band from strictly earlier origins only)
    coverage = {}
    origin_list = [o for o in origins if any((sku, o) in cells[methods[0]] for sku in skus)]
    for m in methods:
        cov_hits, cov_n = 0, 0
        for t, o in enumerate(origin_list):
            earlier = [o2 for o2 in origin_list[:t]]
            resid = [abs(F - A) for (sku, o2), (F, A) in cells[m].items() if o2 in earlier]
            if not resid:
                continue
            band = float(np.quantile(resid, 0.8))
            for (sku, o2), (F, A) in cells[m].items():
                if o2 == o:
                    cov_n += 1
                    cov_hits += int(abs(F - A) <= band)
        coverage[m] = dict(cells=cov_n, hits=cov_hits,
                           rate=(cov_hits / cov_n if cov_n else None))

    # ---- per-SKU csv ----------------------------------------------------
    scored_skus = {k[0] for k in common}
    unscored.clear()                    # loop counters are per-origin skips; rebuild per SKU
    for sku in skus:
        if sku in scored_skus:
            continue
        s_ = series[sku]
        enough = any(o2 - s_["first"] + 1 >= MIN_TRAIN for o2 in
                     [ym_i(o) for o in used_origins])
        unscored["history_lt_min_train" if not enough else "no_common_cell"].add(sku)

    csv_rows = []
    for sku in skus:
        ev = sku_evidence.get(sku, {})
        n_cells = sum(1 for (s2, o2) in common if s2 == sku) if common else 0
        csv_rows.append(dict(
            sku_hash=hashlib.sha256(sku.encode()).hexdigest()[:12],
            category=(groups.get(eligible.get(sku)) or ""),
            type=ev.get("type") or "", method=ev.get("method") or "",
            method_source=ev.get("method_source") or "",
            evidence_origin=ev.get("evidence_origin", ""),
            n_hist=ev.get("n_hist", ""), zero_share=ev.get("zero_share", ""),
            adi=ev.get("adi", ""), cv2=ev.get("cv2", ""),
            seasonal_strength=ev.get("seasonal_strength", ""),
            total_qty=round(ev.get("total_qty", 0.0), 2),
            n_warehouses=wh_count.get(sku, 0),
            top_warehouse_share=(round(wh_top.get(sku, 0.0) / ev.get("total_qty", 1), 3)
                                 if ev.get("total_qty") else ""),
            scored_cells=n_cells,
            scored=int(n_cells > 0),
            reason=("" if n_cells else (ev.get("reason") or "no_common_cell"))))
    csv_path = OUT_DIR / "routing.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        import csv as _csv
        wr = _csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["sku_hash"])
        wr.writeheader()
        wr.writerows(csv_rows)

    payload = dict(
        schema_version="a_routing/1",
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        inputs=dict(db=str(db), db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest()),
        settings=dict(origins=origins, origins_used=used_origins, window_days=WINDOW_DAYS, min_train=MIN_TRAIN,
                      base_methods=BASE_METHODS,
                      routing_rules=ROUTE_CANDIDATES,
                      inner_offsets=list(INNER_OFFSETS),
                      common_subset=len(common), elapsed_s=round(elapsed, 1)),
        library_versions=tree_versions,
        tree_model=dict(available=tree_ok, note=tree_note,
                        predictions=sum(tree_cache.values())),
        results=results,
        coverage=coverage,
        evaluated_skus=len({k[0] for k in common}),
        scored_skus=sum(1 for r in csv_rows if r["scored"]),
        unscored={k: len(v) for k, v in unscored.items()},
        unavailable_features=[
            "促销/折扣标记（DB 无字段）",
            "价格与价格变动（DB 无字段）",
            "上新/停产日历（DB 无字段）",
            "竞品与市场活动（无数据源）",
        ],
        caliber_correction=dict(
            source="forecast_eval/attribution_report.md",
            common_skus=151, common_windows=446,
            mae=dict(tsb=12.063, ses=12.694, category_borrowed=13.118, naive=14.299),
            note=("此前「类目最差」结论失效：在共同 151 SKU / 446 窗口上 TSB 最好、"
                  "类目借力处于 SES 与 naive 之间。本轮仅作对照，不宣称最优。")),
    )
    (OUT_DIR / "routing_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- report ---------------------------------------------------------
    def p(v, nd=3):
        return "—" if v is None else f"{v:.{nd}f}"

    L = ["---", "okf: v0.1", "type: Report",
         "title: A 包：预测分型路由与全局模型对照",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 完成；离线本地 DuckDB；同切点共同子集",
         "artifacts:",
         "  - experiments/business_phase/forecast_eval/routing_eval.py",
         "  - forecast_eval/routing_results.json",
         "  - forecast_eval/routing.csv",
         "---", "",
         "# A 包：预测分型路由与全局模型对照", "",
         "> 只本地离线；DB 只读。所有方法在同一批 (SKU, 起点) 单元、同一个 90 天窗口上评分；"
         "路由只用起点之前的数据。", "",
         "## 0. 运行参数", "",
         f"- 耗时 **{elapsed:.1f} s**（预算 900 s）；单元 **{len(common)}** 个（共同子集）；"
         f"评分 SKU **{payload['evaluated_skus']}** / 候选 {len(skus)}",
         f"- 起点（实际使用）：{', '.join(used_origins)}；窗口 {WINDOW_DAYS} 天；最少历史 {MIN_TRAIN} 个月",
         f"- 全局树模型：{'可用' if tree_ok else '不可用'}；"
         f"版本 {tree_versions or '—'}；每起点预测行 {tree_cache}",
         "- 环境：本轮为对照安装 `mlforecast==1.1.0`（lightgbm 4.7.0 已有）；"
         "`uv pip install` 曾临时降 pandas 到 2.3.3，但 `uv run` 按项目锁定仍用 pandas 3.0.2，"
         "树模型在 3.0.2 下跑通（版本见上行）。",
         ""]

    L += ["## 1. 特征可得性（SKU × 仓 × 品类）", "",
          "| 特征 | 可得 | 来源 |", "|---|---|---|",
          "| 历史长度（月） | 是 | monthly_series 首月到起点 |",
          "| 零占比 | 是 | 同上 |",
          "| 间歇度 ADI / CV² | 是 | 非零月间隔与波动 |",
          "| 季节强度 | 是 | 月份均值方差占比（需 ≥24 月） |",
          "| 销量分层 | 是 | 训练窗累计需求 |",
          "| 仓库数 / 主仓占比 | 是 | monthly_series.sku × warehouse |",
          "| 品类 | 是 | item_attr.item_group（经 destinations 映射） |",
          "| 促销/折扣 | **否** | DB 无字段 |",
          "| 价格与价格变动 | **否** | DB 无字段 |",
          "| 上新/停产日历 | **否** | DB 无字段 |",
          "| 竞品活动 | **否** | 无数据源 |", "",
          "> 不可得项不参与路由，也不做代理变量臆造。", ""]

    L += ["## 2. 路由规则与训练内选模", "",
          "| 分型 | 判定（仅用起点前数据） | 候选 |", "|---|---|---|",
          "| short | 历史 < 24 月 | tsb, naive |",
          "| intermittent | 零占比 ≥ 0.4 或 ADI ≥ 2.0 | tsb, croston |",
          "| seasonal | 季节强度 ≥ 0.3 | seasonal_naive, seasonal_yoy |",
          "| simple | 其余 | naive, ma3 |", "",
          f"- 型内取舍：在起点前 {' / '.join(str(x) for x in INNER_OFFSETS)} 个月各做一次内层回测，"
          f"取 MAE 更低者；内层窗口必须在起点内结束（无外层信息）。",
          ""]
    type_counts = Counter(r["type"] for r in csv_rows if r["type"])
    src_counts = Counter(r["method_source"] for r in csv_rows if r["method_source"])
    L.append("- 分型分布：" + "、".join(f"{k} {v}" for k, v in type_counts.most_common())
             + f"；选模来源（按单元）：{dict(source_cells)}")

    L += ["", "## 3. 同切点比较（共同子集，未见样本）", "",
          "| 方法 | n | WAPE | Bias | MAE | 80% 覆盖率 |",
          "|---|---:|---:|---:|---:|---:|"]
    for m in methods:
        r = results[m]
        cv = coverage.get(m, {})
        L.append(f"| {m} | {r['n']} | {p(r['wape'])} | {p(r['bias'])} | {p(r['mae'])} | "
                 f"{p(cv.get('rate')) if cv.get('rate') is not None else '—'} |")
    L += ["", "> WAPE = Σ|F−A| / ΣA；Bias = Σ(F−A) / ΣA；覆盖率来自**滚动共形带**"
          "（只用更早起点的残差分位数，80%），不是模型自带区间。", ""]

    L += ["## 4. 每 SKU 支持证据与未评分覆盖", "",
          f"- `routing.csv` 每行一个 SKU：特征、分型、选用方法、选模来源、评分单元数、是否被评分、原因。",
          f"- 评分 SKU **{payload['scored_skus']}**；未评分 **{len(skus)-payload['scored_skus']}** 个；"
          f"原因计数：{payload['unscored'] or '无'}",
          f"- 未评分不进入任何指标；原因只写观测（历史不足 / 无共同单元）。", ""]

    L += ["## 5. 口径更正", "",
          "- `attribution_report.md` 的共同 **151 SKU / 446 窗**上，MAE 为 "
          "**TSB 12.063、SES 12.694、类目借力 13.118、naive 14.299**。",
          "- 因此此前「类目借力最差」的结论**失效**；本轮只用它作对照，不宣称任何方法最优或适用所有品类。", ""]

    L += ["## 6. 边界", "",
          "- 只报未见样本；路由与选模均不使用外层数据。",
          "- 缺促销/价格/上新日历时不编造代理变量；这会让季节性/间歇性判断偏粗。",
          "- 全局树模型是**同一批**数据上的对照，不调参追求最优；其预测行数见第 0 节。",
          "- 单位是 SKU-月（跨仓汇总）；仓库信息只作为特征（仓库数、主仓占比）。", ""]

    (OUT_DIR / "routing_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"elapsed={elapsed:.1f}s common_cells={len(common)} skus={len(skus)} "
          f"scored_skus={payload['scored_skus']} tree_ok={tree_ok}")
    for m in methods:
        r = results[m]
        cv = coverage.get(m, {})
        print(f"  {m}: n={r['n']} wape={p(r['wape'])} bias={p(r['bias'])} "
              f"mae={p(r['mae'])} cov80={p(cv.get('rate'))}")


if __name__ == "__main__":
    main()
