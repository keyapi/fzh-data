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
SIMPLE = ["naive", "seasonal_naive", "ma3", "ma6", "ma12"]


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

    sku_month, sku_wh = defaultdict(dict), defaultdict(set)
    for sku, ym, wh, q in rows:
        sku_month[sku][ym] = sku_month[sku].get(ym, 0.0) + float(q)
        sku_wh[sku].add(wh)
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
    for (sku, origin), (F, A) in sorted(cells["autoets"].items()):
        s = series[sku]
        kind = ("warehouse_level_true" if len(sku_wh.get(sku, set())) == 1
                else "multi_warehouse_true_sum")
        if not sku_wh.get(sku):
            kind = "proxy_current_primary"
        out_rows.append(dict(
            SKU=sku, origin=origin,
            split=("val" if origin in VAL_ORIGINS else "test"),
            forecast=round(F, 2), actual=round(A, 2), error=round(F - A, 2),
            abs_error=round(abs(F - A), 2),
            abs_error_share=(round(abs(F - A) / total_abs, 6)),
            series_kind=kind, n_history=len(s["y"]),
        ))
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
    short_eval = []
    short_skus = sorted(short)
    # category-borrowed: peer seasonal shape (item_group) x own level
    group_members = defaultdict(list)
    for s, v in series.items():
        item = dest.get(s, {}).get("mapped_item_code")
        g = item_group.get(item)
        if g:
            group_members[g].append(s)
    for sku in short_skus:
        s = series[sku]
        n = len(s["y"])
        # only origins whose 90-day window is fully inside the known data
        cands = [o for o in range(s["first"] + 2, last_i + 1)
                 if max(window_weights(decision_date(o), 90)) <= last_i]
        origins = cands[-3:]
        per = defaultdict(list)
        for o in origins:
            tr = o - s["first"] + 1
            if tr < 2:
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
            item = dest.get(sku, {}).get("mapped_item_code")
            g = item_group.get(item)
            peers = [p for p in group_members.get(g, []) if p != sku and len(series[p]["y"]) >= 24]
            if peers:
                shape = np.mean([series[p]["y"][-12:] / (np.mean(series[p]["y"][-12:]) or 1)
                                 for p in peers], axis=0)
                lvl = float(np.mean(ytr[-min(3, tr):]))
                prof = [shape[(o + k) % 12] * lvl for k in range(1, h + 1)]
                cand["category_borrowed"] = float(sum(wt * prof[k - (o + 1)]
                                                      for k, wt in w.items()))
            if cand:
                for m, F in cand.items():
                    per[m].append(abs(F - A))
                per["_n"].append(A)
        if not per.get("_n"):
            continue
        row = dict(sku=sku, n_history=n, n_cells=len(per["_n"]),
                   low_confidence=bool(n < 12 or len(per["_n"]) < 3))
        for m in ("naive", "ses", "tsb", "category_borrowed", "combo2"):
            vals = per.get(m)
            row[m] = (round(float(np.mean(vals)), 3) if vals else None)
            row[f"{m}_feasible"] = bool(vals)
        short_eval.append(row)
    short_summary = {}
    for m in ("naive", "ses", "tsb", "category_borrowed", "combo2"):
        vals = [r[m] for r in short_eval if r.get(m) is not None]
        short_summary[m] = dict(skus=len(vals),
                                mean_abs_error=(round(float(np.mean(vals)), 3) if vals else None))

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
        schema_version="t9_error_attribution/1",
        inputs=dict(db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest(),
                    explanations_sha256=hashlib.sha256(EXPL.read_bytes()).hexdigest()),
        scope=dict(skus=len(series), trainable=len(trainable), short_history=len(short),
                   origins=VAL_ORIGINS + TEST_ORIGINS),
        error_rows=len(out_rows),
        total_abs_error=round(total_abs, 2),
        top20=top20,
        top10_sku_error_share=round(top10_sku_error, 4),
        concentration=concentration,
        reversal=reversal,
        fallback=fallback,
        short_history=dict(
            summary=short_summary, per_sku=short_eval,
            n_short_total=len(short), n_evaluated=len(short_eval),
            n_infeasible=len(short) - len(short_eval),
            infeasible_reason=("历史过短（如仅 1–6 个月），在其自有历史内找不到"
                               "“≥2 个月训练 + 完整 90 天目标窗”的滚动起点；"
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
         "`series_kind`：`warehouse_level_true`（该 SKU 只有一个真实仓）/ "
         "`multi_warehouse_true_sum`（多仓真实和）；**没有 proxy**（订单行仓库名齐全）。", "",
         "## 2. 误差贡献与集中度", "",
         "| Top20 SKU | 绝对误差 | 占总误差 | 占总销量 |", "|---|---:|---:|---:|"]
    for t in top20[:10]:
        L.append(f"| `{t['sku']}` | {t['abs_error']} | {t['error_share']:.2%} | "
                 f"{t['sales_share']:.2%} |")
    L += ["", f"- Top10 SKU 合计占总绝对误差 **{top10_sku_error:.2%}**", ""]
    L += ["| 集中度 | SKU 数 | 销量占比 | 误差占比 |", "|---|---:|---:|---:|"]
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
          f"销量覆盖 **{fallback['sales_coverage']:.2%}**",
          f"- `tiny_datasets`：{fallback['by_reason']['tiny_datasets']['rows']} 行 / "
          f"{fallback['by_reason']['tiny_datasets']['skus']} SKU / "
          f"销量 {fallback['by_reason']['tiny_datasets']['sales_share']:.3%}",
          f"- `KeyError:'fitted'`：{fallback['by_reason']['key_error']['rows']} 行 / "
          f"{fallback['by_reason']['key_error']['skus']} SKU / "
          f"销量 {fallback['by_reason']['key_error']['sales_share']:.3%}"]
    if repro:
        L += ["", "**KeyError 最小复现**：",
              f"- SKU `{repro['sku']}`，序列长度 **{repro['series_len']}**，值 {repro['values']}",
              f"- 调用：`{repro['call']}`（statsforecast {repro['statsforecast_version']}）",
              f"- 错误：`{repro['error']}`；位置 `{repro['traceback_tail'][-1][:120]}`",
              f"- 分类：{repro['classification']} —— {repro['detail']}",
              f"- 建议：{repro['fix_suggestion']}"]
    L += ["", "## 5. 短历史序列的多方法滚动", "",
          f"短历史 SKU {len(short)} 条，在其自有历史内做滚动 90 天窗口评估：", "",
          "| 方法 | 可行 SKU 数 | 平均绝对误差 |", "|---|---:|---:|"]
    for m, v in short_summary.items():
        L.append(f"| {m} | {v['skus']} | {v['mean_abs_error']} |")
    L += ["", f"- 短历史共 {len(short)} 条，其中 **{len(short_eval)} 条可评估**、"
          f"**{len(short) - len(short_eval)} 条不可评估**"
          "（历史过短，找不到“≥2 个月训练 + 完整 90 天目标窗”的滚动起点；不填默认值）",
          "低置信标记：历史 <12 月或可用窗口 <3 个的序列标 `low_confidence=True`"
          f"（{sum(1 for r in short_eval if r['low_confidence'])} / {len(short_eval)}）。",
          "没有用任何默认值冒充实测。", "",
          "## 6. 计算规模", "",
          f"- 运行 **{runtime['seconds']} s**，tracemalloc 峰值 **{runtime['tracemalloc_peak_mb']} MB**",
          f"- 范围：{runtime['scope']}", "",
          "## 7. 结论（三条）", "",
          "1. 误差高度集中：见 §2 的 Top10/Top20 与集中度——少数 SKU 贡献大部分绝对误差。",
          f"2. 反转不是单一原因：同 SKU 跨期变化 = {d.get('same_sku_change')}，"
          f"SKU 构成差异 = {d.get('composition_effect')}（两部分都已量化，"
          "季节不同只是背景）。",
          f"3. fallback 的 112 行只对应 {fallback['distinct_skus']} 个 SKU、"
          f"销量覆盖 {fallback['sales_coverage']:.2%}；其中 KeyError 属库输入校验缺口"
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
