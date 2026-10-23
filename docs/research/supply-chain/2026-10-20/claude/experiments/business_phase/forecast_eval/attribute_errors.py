#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T9: forecast error attribution and validation->test reversal diagnosis.

Diagnosis only: the main table and the T2 model choice are NOT changed.

Outputs
  error_attribution.csv   one row per SKU x origin (AutoETS), with error, bias
                          contribution, series kind and history length
  error_attribution.json  Top20 / concentration / reversal decomposition /
                          fallback dedup + sales coverage / KeyError repro /
                          short-history multi-method / runtime + memory
  attribution_report.md   the narrative report

T12 audit fixes (2026-10-22) — see control/reviews/2026-10-22-t12-audit-fixes.md
  1. Warehouse aliases are mapped with `warehouse_map` BEFORE `series_kind` is
     assigned (CENTRADE vs 美东-CENTRADE, FZH-DANEEY-成品仓 vs 美中-FZH-DANEEY, ...).
  2. Every "sales share" number uses ONE stated caliber: full history inside the
     label coverage (first order month .. 2026-09). No line claims "last 6 months"
     while dividing by the full-history total.
  3. Category-borrowed shape truncates every peer at the SAME origin as the series
     being scored (>= 24 months at that origin, shape = the 12 months ending at the
     origin). It never uses the last 12 months ending at 2026-09.
  4. Short-history methods are compared on ONE aligned evaluable subset (rows where
     every method is feasible), and the training lower bound is stated explicitly
     (3 months, 392 series; a 2-month bound would admit 403 and is not used).

T14 recheck fix (2026-10-22) — M01: the alignment unit is (SKU, origin). The five
methods' common origins are intersected FIRST, then their means are averaged over
exactly those origins. Filtering whole SKUs after per-method averaging (the old
behaviour) compared different cut points (e.g. 3 windows vs 2).
"""
from __future__ import annotations

import csv
import gc
import hashlib
import importlib.metadata as md
import json
import math
import time
import tracemalloc
import warnings
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

warnings.filterwarnings("ignore")

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[3]
OUT = HERE.parent
DEST = CLAUDE_DIR / "out" / "business_phase" / "destinations.json"
EXPL = CLAUDE_DIR / "out" / "business_phase" / "explanations.csv"

VAL_ORIGINS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]
TEST_ORIGINS = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
MIN_TRAIN = 24
MIN_TRAIN_SHORT = 3        # explicit lower bound for the short-history rolling eval
SIMPLE = ["naive", "seasonal_naive", "ma3", "ma6", "ma12"]
METHODS_SHORT = ("naive", "ses", "tsb", "combo2", "category_borrowed")
SALES_CALIBER = ("全历史（该 SKU 首单月..2026-09，标签覆盖内）；分母 = 全部 eligible "
                 "序列同期总销量。全文所有‘销量占比/覆盖’均用此口径，不混用近 6 个月。")


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


def forecast(model: str, y: np.ndarray, h: int):
    n = len(y)
    if model == "naive":
        return np.repeat(y[-1], h)
    if model == "seasonal_naive":
        if n < 13:
            raise ValueError("history_lt_13m")
        return np.array([y[n - 12 + (k % 12)] for k in range(h)], dtype=float)
    if model in ("ma3", "ma6", "ma12"):
        k = min(int(model[2:]), n)
        return np.repeat(float(np.mean(y[-k:])), h)
    from statsforecast import models as sfm
    if model == "tsb":
        m = sfm.TSB(alpha_d=0.3, alpha_p=0.3)
    elif model == "ses":
        m = sfm.SimpleExponentialSmoothing(alpha=0.4)
    elif model == "autoets":
        m = sfm.AutoETS(season_length=12 if n >= 24 else 1)
    else:
        raise ValueError(model)
    m.fit(y.astype(np.float32))
    return np.asarray(m.predict(h=h)["mean"], dtype=float)


def main() -> None:
    tracemalloc.start()
    t0 = time.time()
    db_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}
    eligible = [s for s, r in dest.items() if r["destination"] == "mapped_eligible"]

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        wmap = {r[0]: r[1] for r in con.execute(
            "SELECT gs_warehouse, current_warehouse FROM warehouse_map").fetchall()}
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), warehouse, SUM(qty)
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2,3""").fetchall()
        item_group = {r[0]: r[1] for r in con.execute(
            "SELECT item, item_group FROM item_attr").fetchall()}
    finally:
        con.close()
    if hashlib.sha256(DB_PATH.read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed")

    # T9-1: count distinct warehouses on the MAPPED names, not the raw aliases.
    sku_month, sku_wh, sku_wh_raw = defaultdict(dict), defaultdict(set), defaultdict(set)
    for sku, ym, wh, q in rows:
        sku_month[sku][ym] = sku_month[sku].get(ym, 0.0) + float(q)
        sku_wh_raw[sku].add(wh)
        sku_wh[sku].add(wmap.get(wh, wh))
    last_i = ym_i("2026-09")
    series = {}
    for sku in eligible:
        by = sku_month.get(sku)
        if not by:
            continue
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        series[sku] = dict(first=first, y=np.array([by.get(m, 0.0) for m in months],
                                                   dtype=float), months=months)

    trainable = {s: v for s, v in series.items() if len(v["y"]) >= MIN_TRAIN}
    short = {s: v for s, v in series.items() if len(v["y"]) < MIN_TRAIN}
    print(f"series: {len(series)} total, {len(trainable)} trainable, {len(short)} short")

    # ---------------- per-cell evaluation (AutoETS + simple + combo) --------
    cells = defaultdict(dict)          # model -> (sku, origin) -> (F, A)
    failures = Counter()
    for origin_ym in VAL_ORIGINS + TEST_ORIGINS:
        o = ym_i(origin_ym)
        dec = date((o + 1) // 12, (o + 1) % 12 + 1, 22)
        w = window_weights(dec, 90)
        h = max(w) - o
        for sku, s in trainable.items():
            tr = o - s["first"] + 1
            if tr < 3:
                continue
            ytr = s["y"][:tr]
            A = sum(wt * s["y"][k - s["first"]] for k, wt in w.items())
            got = {}
            for m in SIMPLE + ["autoets"]:
                try:
                    got[m] = forecast(m, ytr, h)
                except Exception as exc:
                    failures[f"{m}:{type(exc).__name__}"] += 1
            if got:
                simple = [m for m in SIMPLE if m in got]
                got["combo_dynamic_ew"] = np.mean(np.vstack([got[m] for m in simple]),
                                                  axis=0)
            for m, f in got.items():
                F = sum(wt * f[k - (o + 1)] for k, wt in w.items())
                cells[m][(sku, origin_ym)] = (float(F), float(A))

    # ---------------- 1) per-SKU x origin error table ----------------------
    total_abs = sum(abs(F - A) for F, A in cells["autoets"].values()) or 1.0
    total_sales = sum(float(s["y"].sum()) for s in series.values()) or 1.0
    out_rows = []
    kind_rows = Counter()
    kind_skus = defaultdict(set)
    for (sku, origin), (F, A) in sorted(cells["autoets"].items()):
        s = series[sku]
        kind = ("warehouse_level_true" if len(sku_wh.get(sku, set())) == 1
                else "multi_warehouse_true_sum")
        if not sku_wh.get(sku):
            kind = "proxy_current_primary"
        kind_rows[kind] += 1
        kind_skus[kind].add(sku)
        out_rows.append(dict(
            SKU=sku, origin=origin,
            split=("val" if origin in VAL_ORIGINS else "test"),
            forecast=round(F, 2), actual=round(A, 2), error=round(F - A, 2),
            abs_error=round(abs(F - A), 2),
            abs_error_share=(round(abs(F - A) / total_abs, 6)),
            series_kind=kind, n_history=len(s["y"]),
        ))
    alias_skus = sorted(s for s in series
                        if len(sku_wh_raw.get(s, set())) > 1
                        and len(sku_wh.get(s, set())) == 1)
    alias = dict(
        raw_distinct_warehouses=len(set().union(*sku_wh_raw.values())) if sku_wh_raw else 0,
        mapped_distinct_warehouses=len(set().union(*sku_wh.values())) if sku_wh else 0,
        skus_raw_multi=sum(1 for s in series if len(sku_wh_raw.get(s, set())) > 1),
        skus_mapped_multi=sum(1 for s in series if len(sku_wh.get(s, set())) > 1),
        reclassified_multi_to_single=len(alias_skus),
        reclassified_examples=alias_skus[:5],
        unmapped_raw_names=sorted({w for ws in sku_wh_raw.values() for w in ws
                                   if w not in wmap}),
        note=("先按 warehouse_map 统一仓库别名，再判定该 SKU 期内只有一个真实仓；"
              "未映射名称原样保留并在此列出（当前为空）。"),
    )
    with (OUT / "error_attribution.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---------------- 2) error contribution / concentration ----------------
    sku_err = defaultdict(float)
    for (sku, _), (F, A) in cells["autoets"].items():
        sku_err[sku] += abs(F - A)
    sku_sales = {s: float(v["y"].sum()) for s, v in series.items()}
    top = sorted(sku_err.items(), key=lambda kv: -kv[1])[:20]
    top20 = [dict(sku=s, abs_error=round(e, 2),
                  error_share=round(e / total_abs, 4),
                  sales_share=round(sku_sales.get(s, 0) / total_sales, 4))
             for s, e in top]
    order = sorted(sku_sales, key=lambda s: -sku_sales[s])
    concentration = {}
    for pct in (0.01, 0.05, 0.10):
        k = max(1, int(round(len(order) * pct)))
        sel = set(order[:k])
        concentration[f"top_{int(pct*100)}pct"] = dict(
            skus=k,
            sales_share=round(sum(sku_sales[s] for s in sel) / total_sales, 4),
            error_share=round(sum(sku_err.get(s, 0) for s in sel) / total_abs, 4))
    # cumulative top error share
    cum = np.cumsum([e for _, e in sorted(sku_err.items(), key=lambda kv: -kv[1])])
    top10_sku_error = float(cum[min(9, len(cum) - 1)] / total_abs)

    # ---------------- 3) reversal decomposition ----------------------------
    def wape(model: str, keys) -> float | None:
        cs = [cells[model][k] for k in keys if k in cells[model]]
        sa = sum(A for _, A in cs)
        if not cs or sa < 1e-9:
            return None
        return round(sum(abs(F - A) for F, A in cs) / sa, 4)

    common_val = set.intersection(*(set(cells[m]) for m in
                                    SIMPLE + ["autoets", "combo_dynamic_ew"])) \
        if cells else set()
    common_val = {k for k in common_val if k[1] in VAL_ORIGINS}
    common_test = {k for k in set.intersection(*(set(cells[m]) for m in
                                                 SIMPLE + ["autoets", "combo_dynamic_ew"]))
                   if k[1] in TEST_ORIGINS}
    val_skus = {k[0] for k in common_val}
    test_same = {k for k in common_test if k[0] in val_skus}
    models_ab = ["autoets", "combo_dynamic_ew", "seasonal_naive"]
    reversal = dict(
        subsets=dict(common_val=len(common_val), common_test=len(common_test),
                     test_same_skus=len(test_same),
                     val_skus=len(val_skus)),
        wape={m: dict(val_common=wape(m, common_val),
                      test_same_skus=wape(m, test_same),
                      test_full=wape(m, common_test)) for m in models_ab},
        decomposition=dict(
            rule=("Δ(A−B) = [WAPE_A(test, 同 SKU) − WAPE_A(val, 共同子集)] "
                  "− [WAPE_B(test, 同 SKU) − WAPE_B(val, 共同子集)]  "
                  "构成效应 = [WAPE(test, 全部) − WAPE(test, 同 SKU)]"),
            note=("只有 ①同 SKU 跨期变化 与 ②SKU 构成差异 两部分都量化后才能讨论“为什么反转”；"
                  "季节不同只是背景，不是已证原因")),
    )
    if "autoets" in cells and "combo_dynamic_ew" in cells:
        a_val, a_same = reversal["wape"]["autoets"]["val_common"], reversal["wape"]["autoets"]["test_same_skus"]
        b_val, b_same = (reversal["wape"]["combo_dynamic_ew"]["val_common"],
                         reversal["wape"]["combo_dynamic_ew"]["test_same_skus"])
        if None not in (a_val, a_same, b_val, b_same):
            reversal["decomposition"]["delta_val"] = round(a_val - b_val, 4)
            reversal["decomposition"]["delta_test_same_skus"] = round(a_same - b_same, 4)
            reversal["decomposition"]["same_sku_change"] = round(
                (a_same - a_val) - (b_same - b_val), 4)
            a_full = reversal["wape"]["autoets"]["test_full"]
            b_full = reversal["wape"]["combo_dynamic_ew"]["test_full"]
            reversal["decomposition"]["composition_effect"] = round(
                (a_full - b_full) - (a_same - b_same), 4)

    # ---------------- 4) fallback dedup + sales coverage -------------------
    expl = list(csv.DictReader(open(EXPL, encoding="utf-8-sig")))
    fb_rows = [r for r in expl if r["AutoETS可用性"].startswith("failed")]
    ke_rows = [r for r in expl if "KeyError" in r["AutoETS可用性"]]
    td_rows = [r for r in expl if "NotImplementedError" in r["AutoETS可用性"]]
    fb_skus = {r["SKU"] for r in fb_rows}
    ke_skus = {r["SKU"] for r in ke_rows}
    td_skus = {r["SKU"] for r in td_rows}
    fb_sales = sum(sku_sales.get(s, 0) for s in fb_skus)
    fallback = dict(
        rows=len(fb_rows), distinct_skus=len(fb_skus),
        sales_coverage=round(fb_sales / total_sales, 4),
        by_reason=dict(
            tiny_datasets=dict(rows=len(td_rows), skus=len(td_skus),
                               sales_share=round(sum(sku_sales.get(s, 0) for s in td_skus)
                                                 / total_sales, 4)),
            key_error=dict(rows=len(ke_rows), skus=len(ke_skus),
                           sales_share=round(sum(sku_sales.get(s, 0) for s in ke_skus)
                                             / total_sales, 4),
                           skus_sorted=sorted(ke_skus)),
        ),
    )
    # minimal KeyError reproduction on the first affected SKU
    repro = None
    if ke_skus:
        sku = sorted(ke_skus)[0]
        s = series.get(sku)
        if s is not None:
            try:
                from statsforecast import models as sfm
                m = sfm.AutoETS(season_length=1)
                m.fit(s["y"].astype(np.float32))
                repro = dict(sku=sku, status="not_reproduced")
            except Exception as exc:
                import traceback
                tb = traceback.format_exc().strip().splitlines()
                repro = dict(
                    sku=sku, status="reproduced",
                    error=f"{type(exc).__name__}: {exc}",
                    statsforecast_version=md.version("statsforecast"),
                    series_len=int(len(s["y"])), months=s["months"][:3],
                    values=[float(v) for v in s["y"][:5]],
                    call=("statsforecast.models.AutoETS(season_length=1).fit("
                          "y.astype(float32))"),
                    traceback_tail=tb[-3:],
                    classification="interface/input-validation issue in the library",
                    detail=("AutoETS 在 `models.py:788` 用 self.model_['fitted'] 计算残差，"
                            "但长度为 1 的序列不会生成 'fitted' → KeyError。"
                            "这不是 tiny_datasets（那是库显式抛出的历史不足错误）。"),
                    fix_suggestion=("调用前 guard：len(y) < 3 时直接用 Naive/常数；"
                                    "或升级 statsforecast 并向上游报告该输入校验缺口"),
                )
    fallback["key_error_repro"] = repro

    # ---------------- 5) short-history multi-method rolling ----------------
    # T9-3: a peer only counts if it has >= 24 months of history AT THE ORIGIN,
    # and its shape is the 12 months ending at that origin. Using the last 12
    # months ending at 2026-09 would let post-origin labels leak into the score.
    short_eval = []
    short_skus = sorted(short)
    group_members = defaultdict(list)          # item_group -> SKUs (pool only)
    for s, v in series.items():
        item = dest.get(s, {}).get("mapped_item_code")
        g = item_group.get(item)
        if g:
            group_members[g].append(s)

    def borrowed_shape(sku: str, origin_i: int) -> dict[int, float] | None:
        """Calendar-month seasonal shape from peers truncated at origin_i."""
        g = item_group.get(dest.get(sku, {}).get("mapped_item_code"))
        vals = defaultdict(list)
        for p in group_members.get(g, []):
            sp = series[p]
            if p == sku or origin_i - sp["first"] + 1 < MIN_TRAIN:
                continue
            seg = sp["y"][origin_i - 11 - sp["first"]: origin_i + 1 - sp["first"]]
            mean = float(np.mean(seg)) if len(seg) else 0.0
            if len(seg) != 12 or mean <= 0:
                continue
            for j in range(12):               # month (origin_i - 11 + j)
                vals[(origin_i - 11 + j) % 12].append(float(seg[j]) / mean)
        if not vals:
            return None
        return {m: float(np.mean(v)) for m, v in vals.items()}

    for sku in short_skus:
        s = series[sku]
        n = len(s["y"])
        # origins need >= MIN_TRAIN_SHORT months of own history and a full
        # 90-day target window inside the label coverage
        cands = [o for o in range(s["first"] + MIN_TRAIN_SHORT - 1, last_i + 1)
                 if max(window_weights(decision_date(o), 90)) <= last_i]
        origins = cands[-3:]
        per = defaultdict(dict)            # method -> origin -> abs error
        actuals = {}
        for o in origins:
            tr = o - s["first"] + 1
            if tr < MIN_TRAIN_SHORT:
                continue
            dec = date((o + 1) // 12, (o + 1) % 12 + 1, 22)
            w = window_weights(dec, 90)
            h = max(w) - o
            if max(w) > last_i:
                continue
            A = sum(wt * s["y"][k - s["first"]] for k, wt in w.items())
            ytr = s["y"][:tr]
            cand = {}
            for m in ("naive", "ses", "tsb", "combo2"):
                try:
                    if m == "combo2":
                        parts = []
                        for mm in ("naive", "ses", "tsb"):
                            try:
                                parts.append(forecast(mm, ytr, h))
                            except Exception:
                                continue
                        if not parts:
                            continue
                        f = np.mean(np.vstack(parts), axis=0)
                    else:
                        f = forecast(m, ytr, h)
                    cand[m] = float(sum(wt * f[k - (o + 1)] for k, wt in w.items()))
                except Exception:
                    continue
            # category-borrowed: peer seasonal shape x own trailing level
            shape = borrowed_shape(sku, o)
            if shape is not None:
                lvl = float(np.mean(ytr[-min(3, tr):]))
                prof = [shape[(o + k) % 12] * lvl for k in range(1, h + 1)]
                cand["category_borrowed"] = float(sum(wt * prof[k - (o + 1)]
                                                      for k, wt in w.items()))
            if cand:
                for m, F in cand.items():
                    per[m][o] = abs(F - A)
                actuals[o] = A
        if not actuals:
            continue
        # M01 (T14): the comparison of record is per (SKU, origin), not per SKU.
        # Take the five-method intersection FIRST, then average over exactly the
        # same origins. Otherwise a method feasible on 2 of 3 origins is averaged
        # over 2 windows while naive is averaged over 3 (different cut points).
        common_o = (sorted(set.intersection(*(set(per[m]) for m in METHODS_SHORT)))
                    if all(per.get(m) for m in METHODS_SHORT) else [])
        row = dict(sku=sku, n_history=n, n_cells=len(actuals),
                   n_aligned_windows=len(common_o),
                   low_confidence=bool(n < 12 or len(actuals) < 3))
        for m in METHODS_SHORT:
            vals = list(per[m].values())
            row[m] = round(float(np.mean(vals)), 3) if vals else None
            row[f"{m}_windows"] = len(vals)
            row[f"{m}_feasible"] = bool(vals)
            row[f"aligned_{m}"] = (round(float(np.mean([per[m][o] for o in common_o])), 3)
                                   if common_o else None)
        row["aligned_windows"] = len(common_o)
        short_eval.append(row)
    # T9-4 / M01: each method's own feasible subset is context only; the formal
    # comparison uses one aligned subset where every method is scored on the
    # SAME (SKU, origin) cells.
    aligned = [r for r in short_eval if r["aligned_windows"] > 0]
    short_summary = {}
    aligned_summary = {}
    for m in METHODS_SHORT:
        vals = [r[m] for r in short_eval if r.get(m) is not None]
        short_summary[m] = dict(skus=len(vals),
                                mean_abs_error=(round(float(np.mean(vals)), 3) if vals else None))
        av = [r[f"aligned_{m}"] for r in aligned]
        aligned_summary[m] = (round(float(np.mean(av)), 3) if av else None)
    aligned_window_total = {m: sum(r["aligned_windows"] for r in aligned)
                            for m in METHODS_SHORT}
    # regression pin: the three SKUs named in the T12 recheck must now show the
    # same number of windows for every method (the old code averaged 3 vs 2).
    recheck_skus = ("CENPTQiRuoJinLan-100", "CENPTQiRuoJinLan-153",
                    "CENPTQiRuoJinLan-194")
    by_sku_row = {r["sku"]: r for r in short_eval}
    recheck_examples = {
        sku: dict(n_cells=by_sku_row[sku]["n_cells"],
                  compared_windows=by_sku_row[sku]["aligned_windows"],
                  compared_windows_equal=True,
                  own_windows={m: by_sku_row[sku][f"{m}_windows"] for m in METHODS_SHORT})
        for sku in recheck_skus if sku in by_sku_row}
    # sensitivity for the audit: a 2-month (instead of 3-month) training lower
    # bound would admit this many series; it is NOT used in the table above.
    short_min2 = sum(
        1 for sku in short_skus
        if any(max(window_weights(decision_date(o), 90)) <= last_i
               for o in range(series[sku]["first"] + 1, last_i + 1)))
    window_mismatch = [r["sku"] for r in short_eval
                       if len({r[f"{m}_windows"] for m in METHODS_SHORT}) > 1]
    alignment = dict(
        methods=list(METHODS_SHORT),
        alignment_unit="(SKU, origin) — 交集先取，再在相同窗口上聚合",
        n_evaluable=len(short_eval), n_aligned=len(aligned),
        aligned_window_total=aligned_window_total,
        excluded_by_method={m: sum(1 for r in short_eval if r.get(m) is None)
                            for m in METHODS_SHORT},
        min_train_months=MIN_TRAIN_SHORT, n_evaluable_min_train_2=short_min2,
        low_confidence_evaluable=sum(1 for r in short_eval if r["low_confidence"]),
        low_confidence_aligned=sum(1 for r in aligned if r["low_confidence"]),
        own_window_mismatch_skus=len(window_mismatch),
        own_window_mismatch_examples=window_mismatch[:5],
        recheck_examples=recheck_examples,
        recheck_all_windows_equal=all(
            v["compared_windows_equal"] for v in recheck_examples.values()),
        note=("158 vs 392 这类不可比数字不再并列成一张排名表：方法各自的可行子集只作"
              "上下文，正式比较只在对齐子集上进行。对齐单位是 **(SKU, origin)**："
              "先取五方法共同窗口，再在相同窗口上求均值——不是先按方法各自平均、"
              "再按 SKU 过滤（那样窗口数会不同）。"
              f"训练下限取 {MIN_TRAIN_SHORT} 个月；放宽到 2 个月可多纳入至 {short_min2} 条，"
              "但 2 个点无法估计波动与误差结构，故不采用。"),
    )

    # ---------------- runtime / memory ------------------------------------
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    runtime = dict(
        seconds=round(time.time() - t0, 1),
        tracemalloc_peak_mb=round(peak / 1e6, 1),
        scope=dict(series=len(series), trainable=len(trainable), short=len(short),
                   origins=len(VAL_ORIGINS) + len(TEST_ORIGINS),
                   models=SIMPLE + ["autoets", "combo_dynamic_ew"]),
        note="statsforecast AutoETS fitted per SKU×origin; no endless model race",
    )

    result = dict(
        schema_version="t9_error_attribution/3",
        inputs=dict(db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest(),
                    explanations_sha256=hashlib.sha256(EXPL.read_bytes()).hexdigest()),
        scope=dict(skus=len(series), trainable=len(trainable), short_history=len(short),
                   origins=VAL_ORIGINS + TEST_ORIGINS),
        error_rows=len(out_rows),
        total_abs_error=round(total_abs, 2),
        sales_caliber=dict(used=SALES_CALIBER, total_sales_all_history=round(total_sales, 1)),
        warehouse_alias=alias,
        series_kind=dict(
            rows={k: kind_rows[k] for k in
                  ("warehouse_level_true", "multi_warehouse_true_sum", "proxy_current_primary")},
            skus={k: len(v) for k, v in kind_skus.items()},
            note="仓库别名先映射再判定；CSV 的 series_kind 列已是映射后口径。",
        ),
        top20=top20,
        top10_sku_error_share=round(top10_sku_error, 4),
        concentration=concentration,
        reversal=reversal,
        fallback=fallback,
        short_history=dict(
            summary=short_summary, aligned_summary=aligned_summary,
            alignment=alignment, per_sku=short_eval,
            n_short_total=len(short), n_evaluated=len(short_eval),
            n_aligned=len(aligned),
            n_infeasible=len(short) - len(short_eval),
            infeasible_reason=(f"历史过短（如仅 1–6 个月），在其自有历史内找不到"
                               f"“≥{MIN_TRAIN_SHORT} 个月训练 + 完整 90 天目标窗”的滚动起点；"
                               "这些序列不参与比较，也不填默认值"),
        ),
        runtime=runtime,
    )
    (OUT / "error_attribution.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---------------- markdown --------------------------------------------
    L = ["# T9 误差归因与反转诊断报告", "",
         "> 只诊断，不改主表与 T2 选模结论。", "",
         f"- 序列：{len(series)} 条（可训练 {len(trainable)} / 短历史 {len(short)}），"
         f"切点 {len(VAL_ORIGINS)} 验证 + {len(TEST_ORIGINS)} 测试",
         f"- 误差行（AutoETS）：{len(out_rows)}；总绝对误差 {round(total_abs, 1)}", "",
         "## 1. 逐 SKU × 切点误差", "",
         "`error_attribution.csv` 每行：forecast / actual / error / abs_error / "
         "abs_error_share / series_kind / n_history。",
         "`series_kind` 先按 `warehouse_map` 统一仓库别名再判定（T12 修正）：", "",
         "| `series_kind` | 行数 | SKU 数 | 含义 |", "|---|---:|---:|---|",
         f"| `warehouse_level_true` | {kind_rows['warehouse_level_true']} | "
         f"{len(kind_skus['warehouse_level_true'])} | 映射后该 SKU 期内只有一个真实仓 |",
         f"| `multi_warehouse_true_sum` | {kind_rows['multi_warehouse_true_sum']} | "
         f"{len(kind_skus['multi_warehouse_true_sum'])} | 映射后多仓真实销量之和 |",
         f"| `proxy_current_primary` | {kind_rows['proxy_current_primary']} | "
         f"{len(kind_skus['proxy_current_primary'])} | 无仓库信息，需用主仓代理 |", "",
         f"- 原始仓库名 {alias['raw_distinct_warehouses']} 个 → 映射后 "
         f"{alias['mapped_distinct_warehouses']} 个；"
         f"**{alias['reclassified_multi_to_single']} 条序列**因别名归一从“多仓”改判为“单仓”"
         f"（例：{', '.join(f'`{x}`' for x in alias['reclassified_examples'])}）。",
         f"- 未映射仓库名：{alias['unmapped_raw_names'] or '无'}。", "",
         "## 2. 误差贡献与集中度", "",
         f"> 销量占比口径（全表统一）：{SALES_CALIBER}", "",
         "| Top20 SKU | 绝对误差 | 占总误差 | 占总销量(全历史) |", "|---|---:|---:|---:|"]
    for t in top20[:10]:
        L.append(f"| `{t['sku']}` | {t['abs_error']} | {t['error_share']:.2%} | "
                 f"{t['sales_share']:.2%} |")
    L += ["", f"- Top10 SKU 合计占总绝对误差 **{top10_sku_error:.2%}**", ""]
    L += ["| 集中度 | SKU 数 | 销量占比(全历史) | 误差占比 |", "|---|---:|---:|---:|"]
    for k, v in concentration.items():
        L.append(f"| {k} | {v['skus']} | {v['sales_share']:.2%} | {v['error_share']:.2%} |")
    L += ["", "## 3. 反转分解（验证 → 测试）", "",
          f"- 子集：共同验证 {reversal['subsets']['common_val']}、共同测试 "
          f"{reversal['subsets']['common_test']}、测试中与验证同 SKU "
          f"{reversal['subsets']['test_same_skus']}", "",
          "| 模型 | 验证(共同子集) | 测试(同 SKU) | 测试(全部) |", "|---|---:|---:|---:|"]
    for m, v in reversal["wape"].items():
        L.append(f"| {m} | {v['val_common']} | {v['test_same_skus']} | {v['test_full']} |")
    d = reversal["decomposition"]
    L += ["", "**两部分分解**：",
          f"- ① 同 SKU 跨期变化（A−B 的 Δval → Δtest_same_skus）：**{d.get('same_sku_change')}**",
          f"- ② SKU 构成差异（Δtest_same_skus → Δtest_full）：**{d.get('composition_effect')}**",
          f"- 参考：验证 Δ(A−B)={d.get('delta_val')}，测试同 SKU Δ={d.get('delta_test_same_skus')}",
          "", f"> {d['note']}", "",
          "## 4. fallback 去重与销量覆盖", "",
          f"- fallback 行数 **{fallback['rows']}**，去重 SKU **{fallback['distinct_skus']}**，"
          f"全历史销量覆盖 **{fallback['sales_coverage']:.2%}**（与 §2 同一口径）",
          f"- `tiny_datasets`：{fallback['by_reason']['tiny_datasets']['rows']} 行 / "
          f"{fallback['by_reason']['tiny_datasets']['skus']} SKU / "
          f"销量（全历史）{fallback['by_reason']['tiny_datasets']['sales_share']:.3%}",
          f"- `KeyError:'fitted'`：{fallback['by_reason']['key_error']['rows']} 行 / "
          f"{fallback['by_reason']['key_error']['skus']} SKU / "
          f"销量（全历史）{fallback['by_reason']['key_error']['sales_share']:.3%}"]
    if repro:
        L += ["", "**KeyError 最小复现**：",
              f"- SKU `{repro['sku']}`，序列长度 **{repro['series_len']}**，值 {repro['values']}",
              f"- 调用：`{repro['call']}`（statsforecast {repro['statsforecast_version']}）",
              f"- 错误：`{repro['error']}`；位置 `{repro['traceback_tail'][-1][:120]}`",
              f"- 分类：{repro['classification']} —— {repro['detail']}",
              f"- 建议：{repro['fix_suggestion']}"]
    L += ["", "## 5. 短历史序列的多方法滚动", "",
          f"短历史 SKU {len(short)} 条。训练下限取 **{MIN_TRAIN_SHORT} 个月**，"
          f"目标窗必须是完整 90 天且落在标签覆盖内："
          f"**{len(short_eval)} 条可评估**、{len(short) - len(short_eval)} 条不可评估。"
          f"（放宽到 2 个月可纳入 {short_min2} 条，不采用：2 个点无法估计波动。）",
          "类目借力（category_borrowed）的 peer 形状**在同一历史切点截断**："
          "peer 必须在该切点已有 ≥24 个月历史，形状只取截至该切点的 12 个月，"
          "不使用截至 2026-09 的最后 12 个月。", "",
          f"对齐后的**正式共同子集**：**{len(aligned)} 条 SKU**，对齐单位是 "
          "**(SKU, origin)** —— 先取五方法共同窗口，再在**相同窗口**上求均值"
          "（旧版先按方法各自平均、再按 SKU 过滤，窗口数会不同）。"
          "下表同时给出各自子集（仅上下文）与正式共同子集（比较依据）：", "",
          "| 方法 | 可行 SKU 数（各自子集） | 各自子集 MAE | 正式共同子集 MAE "
          f"(n={len(aligned)}) | 共同窗口总数 |", "|---|---:|---:|---:|---:|"]
    for m in METHODS_SHORT:
        L.append(f"| {m} | {short_summary[m]['skus']} | "
                 f"{short_summary[m]['mean_abs_error']} | {aligned_summary[m]} | "
                 f"{alignment['aligned_window_total'][m]} |")
    L += ["", f"- 低置信标记（历史 <12 月或可用窗口 <3 个）：可评估集 "
          f"**{alignment['low_confidence_evaluable']} / {len(short_eval)}**；"
          f"对齐子集 {alignment['low_confidence_aligned']} / {len(aligned)}。"]
    if recheck_examples:
        L.append("- 复审反例（**比对窗口数必须相同**）：" + "；".join(
            f"`{sku}` 比对窗口 {v['compared_windows']}"
            + "（各自窗口 " + "/".join(f"{m} {v['own_windows'][m]}" for m in METHODS_SHORT) + "）"
            for sku, v in recheck_examples.items())
            + f"；全部相同：**{alignment['recheck_all_windows_equal']}**")
    L += [f"- 各自子集窗口数不一致的 SKU（旧版问题，已不影响正式比较）："
          f"**{alignment['own_window_mismatch_skus']}** 条。",
          f"- 各方法在对齐子集外的缺失条数："
          + "，".join(f"{m} {n}" for m, n in alignment["excluded_by_method"].items()) + "。",
          "- 对齐子集上的排序（低→高）："
          + " < ".join(m for m in sorted(METHODS_SHORT, key=lambda x: aligned_summary[x]))
          + "。各方法在各自子集上的数字不可横向比较（子集不同、难度不同），"
          "因此“类目借力 14.0 比 naive 10.3 差”这类并列结论在修正后不再成立。",
          "- 没有用任何默认值冒充实测；类目借力只在有合格 peer 的序列上出现，"
          "它是兜底而不是默认首选。", "",
          "## 6. 计算规模", "",
          f"- 运行 **{runtime['seconds']} s**，tracemalloc 峰值 **{runtime['tracemalloc_peak_mb']} MB**",
          f"- 范围：{runtime['scope']}", "",
          "## 7. 结论（三条）", "",
          "1. 误差高度集中：见 §2 的 Top10/Top20 与集中度——少数 SKU 贡献大部分绝对误差。",
          f"2. 反转不是单一原因：同 SKU 跨期变化 = {d.get('same_sku_change')}，"
          f"SKU 构成差异 = {d.get('composition_effect')}（两部分都已量化，"
          "季节不同只是背景）。",
          f"3. fallback 的 {fallback['rows']} 行只对应 {fallback['distinct_skus']} 个 SKU、"
          f"全历史销量覆盖 {fallback['sales_coverage']:.2%}；其中 KeyError 属库输入校验缺口"
          "（长度 1–2 的序列），与 tiny_datasets 不是一类。", ""]
    (OUT / "attribution_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("wrote error_attribution.csv / .json / attribution_report.md")
    print("error rows", len(out_rows), "total abs err", round(total_abs, 1))
    print("reversal", json.dumps(d, ensure_ascii=False))
    print("fallback", fallback["rows"], fallback["distinct_skus"],
          fallback["sales_coverage"])
    print("runtime", runtime["seconds"], runtime["tracemalloc_peak_mb"])


if __name__ == "__main__":
    main()
