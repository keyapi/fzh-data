#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T16: short-history method comparison (DEVELOPMENT VALIDATION, not a holdout).

Scope
  * every eligible SKU whose observed history inside the label coverage
    (first order month .. 2026-09) is shorter than 24 months;
  * the fallback sub-samples are called out separately: n<3 and 3<=n<13.

Pre-registered rolling scheme (fixed before looking at any result)
  * target: cumulative h=3 calendar months (origin+1 .. origin+3);
  * origins: every 3rd month starting at the first origin that has
    >=3 months of training history, and only where the whole target window
    is inside the label coverage (<=2026-09);
  * every window refits; only labels available at that origin are used;
  * category-borrowed peers are truncated at the SAME origin
    (>=24 months of peer history at that origin; shape = the 12 months
    ending at the origin), never the last 12 months ending at 2026-09;
  * the fixed equal-weight combo is the mean of naive/SES/TSB forecasts;
  * metrics are aggregated only on the FIVE-METHOD COMMON INTERSECTION of
    (SKU, origin) cells, never on per-method subsets.

Metrics
  MAE = mean |F−A|; WAPE = Σ|F−A| / ΣA; Bias = Σ(F−A) / ΣA.
  Zero-demand cells stay in the WAPE numerator and add 0 to the denominator;
  a group whose total actual is 0 is undefined and listed separately.

Wording: this is development validation on ALREADY-SEEN data. It is NOT an
independent hold-out and must not be described as proven improvement.

Outputs: short_history_eval.json / short_history_eval.csv / short_history_report.md
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
from attribute_errors import forecast, i_ym, ym_i   # noqa: E402  (shared model code)

CLAUDE_DIR = HERE.parents[3]
OUT = HERE.parent
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
DEST = CLAUDE_DIR / "out" / "business_phase" / "destinations.json"

LABEL_END = "2026-09"
SHORT_MAX = 24
MIN_TRAIN = 3
H = 3
STEP = 3
METHODS = ["naive", "ses", "tsb", "category_borrowed", "combo_ew"]
RULES = ["rule_current", "rule_tsb", "rule_ses", "rule_naive"]

# T20 pre-registered guard threshold.
# Evidence in statsforecast 2.1.1: AutoETS(season_length=1) raises
# KeyError('fitted') at len=1 and NotImplementedError('tiny datasets') at
# len=2..6; len>=7 fits. So len<7 must never attempt AutoETS. len<3 → naive
# (no meaningful MA3 window), 3<=len<7 → MA3. Lengths >=7 keep the previous
# behaviour (attempt AutoETS, fall back to MA3 on any exception).
MIN_AUTOETS_LEN = 7


def autoets_with_guard(y: np.ndarray, h: int) -> tuple[np.ndarray, str]:
    """AutoETS with the pre-registered len<7 guard; returns (forecast, status)."""
    n = len(y)
    if n < 3:
        return np.asarray(forecast("naive", y, h), dtype=float), "fallback_naive(len<3)"
    if n < MIN_AUTOETS_LEN:
        return np.asarray(forecast("ma3", y, h), dtype=float), "fallback_MA3(3<=len<7)"
    try:
        return np.asarray(forecast("autoets", y, h), dtype=float), "ok"
    except Exception as exc:
        return (np.asarray(forecast("ma3", y, h), dtype=float),
                f"fallback_MA3({type(exc).__name__})")


def bucket(n: int) -> str:
    if n < 3:
        return "n<3"
    if n < 13:
        return "3<=n<13"
    return "13<=n<24"


def load() -> tuple[dict, dict, str]:
    db_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}
    eligible = {s for s, r in dest.items() if r["destination"] == "mapped_eligible"}
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2""").fetchall()
        item_group = {r[0]: r[1] for r in con.execute(
            "SELECT item, item_group FROM item_attr").fetchall()}
    finally:
        con.close()
    if hashlib.sha256(DB_PATH.read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed")
    by_sku = defaultdict(dict)
    for sku, ym, q in rows:
        if sku in eligible:
            by_sku[sku][ym] = by_sku[sku].get(ym, 0.0) + float(q)
    last_i = ym_i(LABEL_END)
    series = {}
    for sku, by in by_sku.items():
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        series[sku] = dict(first=first,
                           y=np.array([by.get(m, 0.0) for m in months], dtype=float))
    return series, item_group, db_hash


def main() -> None:
    t0 = time.time()
    series, item_group, db_hash = load()
    last_i = ym_i(LABEL_END)
    short = {s: v for s, v in series.items() if len(v["y"]) < SHORT_MAX}
    print(f"series {len(series)}; short (<{SHORT_MAX}m) {len(short)}; "
          f"buckets {dict(Counter(bucket(len(v['y'])) for v in short.values()))}")

    group_members = defaultdict(list)
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}
    for s in series:
        g = item_group.get(dest.get(s, {}).get("mapped_item_code"))
        if g:
            group_members[g].append(s)
    # deterministic peer order (DB GROUP BY order is not guaranteed)
    for _v in group_members.values():
        _v.sort()

    def borrowed(sku: str, origin_i: int) -> dict[int, float] | None:
        g = item_group.get(dest.get(sku, {}).get("mapped_item_code"))
        vals = defaultdict(list)
        for p in group_members.get(g, []):
            sp = series[p]
            if p == sku or origin_i - sp["first"] + 1 < 24:
                continue
            seg = sp["y"][origin_i - 11 - sp["first"]: origin_i + 1 - sp["first"]]
            mean = float(np.mean(seg)) if len(seg) else 0.0
            if len(seg) != 12 or mean <= 0:
                continue
            for j in range(12):
                vals[(origin_i - 11 + j) % 12].append(float(seg[j]) / mean)
        return {m: float(np.mean(v)) for m, v in vals.items()} if vals else None

    cells = []
    autoets_fail = Counter()
    for sku in sorted(short):
        s = series[sku]
        n = len(s["y"])
        first_origin = s["first"] + MIN_TRAIN - 1
        origins = [o for o in range(first_origin, last_i - H + 1)
                   if (o - first_origin) % STEP == 0]
        for o in origins:
            tr = o - s["first"] + 1
            ytr = s["y"][:tr]
            actual = float(np.sum(s["y"][o + 1 - s["first"]: o + 1 - s["first"] + H]))
            pred = {}
            for m in ("naive", "ses", "tsb"):
                pred[m] = float(np.sum(forecast(m, ytr, H)))
            pred["combo_ew"] = float(np.mean([pred["naive"], pred["ses"], pred["tsb"]]))
            shape = borrowed(sku, o)
            if shape is not None:
                lvl = float(np.mean(ytr[-min(3, tr):]))
                pred["category_borrowed"] = float(np.sum(
                    [shape[(o + k) % 12] * lvl for k in range(1, H + 1)]))
            # AutoETS via the T20 guard: len<7 never attempts AutoETS.
            f_auto_vec, auto_status = autoets_with_guard(ytr, H)
            if auto_status == "ok":
                f_auto, rule_val = float(np.sum(f_auto_vec)), float(np.sum(f_auto_vec))
            else:
                f_auto, rule_val = None, float(np.sum(f_auto_vec))
                autoets_fail[auto_status] += 1
            cells.append(dict(
                sku=sku, n_history=n, bucket=bucket(n), origin=i_ym(o),
                target_months=f"{i_ym(o+1)}..{i_ym(o+H)}", tr=tr, actual=actual,
                **{m: pred.get(m) for m in METHODS},
                autoets=f_auto, autoets_status=auto_status,
                rule_current=rule_val,
                rule_tsb=pred["tsb"], rule_ses=pred["ses"], rule_naive=pred["naive"],
                zero_actual=bool(abs(actual) < 1e-9),
            ))

    def metrics(rows, fields):
        den = sum(r["actual"] for r in rows)
        out = dict(n_cells=len(rows), n_skus=len({r["sku"] for r in rows}),
                   denominator=round(den, 2))
        for f in fields:
            if not rows:
                out[f] = dict(mae=None, wape=None, bias=None)
                continue
            err = [abs(r[f] - r["actual"]) for r in rows]
            out[f] = dict(
                mae=round(float(np.mean(err)), 3),
                wape=(round(sum(err) / den, 4) if den > 1e-9 else None),
                bias=(round(sum(r[f] - r["actual"] for r in rows) / den, 4)
                      if den > 1e-9 else None))
        return out

    aligned = [r for r in cells if all(r.get(m) is not None for m in METHODS)]
    by_bucket = {b: [r for r in aligned if r["bucket"] == b]
                 for b in ("3<=n<13", "13<=n<24")}
    method_table = dict(total=metrics(aligned, METHODS),
                        **{b: metrics(v, METHODS) for b, v in by_bucket.items()})

    # ---- fallback reliability: cells where AutoETS failed -------------------
    fb_cells = [r for r in aligned if r["autoets_status"] != "ok"]
    fb_status = Counter(r["autoets_status"] for r in fb_cells)
    fb_by_tr = {"tr<7": [r for r in fb_cells if r["tr"] < 7],
                "tr>=7": [r for r in fb_cells if r["tr"] >= 7]}
    fallback = dict(
        current_rule="AutoETS 成功则用 AutoETS，失败（KeyError / tiny_datasets）则用 MA3",
        autoets_failures=dict(fb_status.most_common()),
        autoets_failures_all_cells=dict(autoets_fail.most_common()),
        n_fallback_cells=len(fb_cells),
        n_fallback_sku=len({r["sku"] for r in fb_cells}),
        by_tr={k: metrics(v, RULES) for k, v in fb_by_tr.items()},
        all_aligned=metrics(aligned, RULES),
        deltas={},
    )
    m = fallback["by_tr"]["tr<7"]
    if m["n_cells"]:
        fallback["deltas"] = {
            f"{alt}_minus_current_mae": round(m[alt]["mae"] - m["rule_current"]["mae"], 3)
            for alt in ("rule_tsb", "rule_ses", "rule_naive")}

        def boot_delta(rows, alt, iters=300, seed=20261022):
            """Resample SKUs; interval of MAE(alt) − MAE(current)."""
            rng = np.random.default_rng(seed)
            by = defaultdict(list)
            for r in rows:
                by[r["sku"]].append(r)
            skus = sorted(by)
            vals = []
            for _ in range(iters):
                pick = [skus[rng.integers(0, len(skus))] for _ in range(len(skus))]
                rs = [r for s in pick for r in by[s]]
                if not rs:
                    continue
                cur = float(np.mean([abs(r["rule_current"] - r["actual"]) for r in rs]))
                x = float(np.mean([abs(r[alt] - r["actual"]) for r in rs]))
                vals.append(x - cur)
            return dict(iterations=iters, mean=round(float(np.mean(vals)), 3),
                        p5=round(float(np.percentile(vals, 5)), 3),
                        p95=round(float(np.percentile(vals, 95)), 3))

        fallback["bootstrap_deltas"] = {
            alt: boot_delta(fb_cells, alt)
            for alt in ("rule_tsb", "rule_ses", "rule_naive")}

    # ---- KeyError / tiny-dataset guard: raw AutoETS vs guarded ------------
    guard = dict(
        guard_rule=(f"len(y) < {MIN_AUTOETS_LEN} → 不尝试 AutoETS，直接 fallback"
                    "（len<3→naive，3<=len<7→MA3）；len>=7 才尝试 AutoETS"),
        threshold_basis=("statsforecast 2.1.1 实测：len=1 抛 KeyError('fitted')；"
                         "len=2..6 抛 NotImplementedError('tiny datasets')；len=7 起可拟合。"
                         "阈值 7 由此预先注册，未按评估效果调参。"),
        before={}, after={}, notes=[],
    )
    for b in ("n<3", "3<=n<13", "13<=n<24"):
        skus = [s for s in short if bucket(len(short[s]["y"])) == b]
        raw = Counter()
        after_ok = Counter()
        for s in skus:
            y = short[s]["y"]
            try:
                forecast("autoets", y, H)
                raw["ok"] += 1
            except Exception as exc:
                raw[type(exc).__name__] += 1
            try:
                _f, status = autoets_with_guard(y, H)
                after_ok[status] += 1
            except Exception as exc:
                after_ok[f"still_{type(exc).__name__}"] += 1
        guard["before"][b] = dict(n=len(skus), status=dict(raw))
        guard["after"][b] = dict(n=len(skus), status=dict(after_ok))
    len1 = [s for s in short if len(short[s]["y"]) == 1]
    len2 = [s for s in short if len(short[s]["y"]) == 2]
    by_length = {}
    for L in range(1, 8):
        skus_l = [s for s in short if len(short[s]["y"]) == L]
        if not skus_l:
            continue
        raw_l, after_l = Counter(), Counter()
        for s in skus_l:
            y = short[s]["y"]
            try:
                forecast("autoets", y, H)
                raw_l["ok"] += 1
            except Exception as exc:
                raw_l[type(exc).__name__] += 1
            try:
                _f, status = autoets_with_guard(y, H)
                after_l[status] += 1
            except Exception as exc:
                after_l[f"still_{type(exc).__name__}"] += 1
        by_length[L] = dict(n=len(skus_l), before=dict(raw_l), after=dict(after_l))
    guard["by_length"] = by_length
    # T20 assertions: every len<7 series falls back, forecasts are finite, and
    # no exception escapes the guard.
    n_lt7 = 0
    for s in short:
        y = short[s]["y"]
        f, status = autoets_with_guard(y, H)
        if len(y) < MIN_AUTOETS_LEN:
            n_lt7 += 1
            assert status.startswith("fallback_"), (s, len(y), status)
        assert len(f) == H and bool(np.all(np.isfinite(f))), (s, status)
    guard["assertions"] = dict(
        n_short=len(short), n_lt7=n_lt7, all_lt7_fallback=True,
        uncaught_exceptions=0,
        note="len<7 全部走 fallback 且预测有限；guard 内无未捕获异常")
    guard["notes"] = [
        "len<7 全部走 fallback：len=1–2 用 naive，len=3–6 用 MA3；不再尝试 AutoETS，"
        "因此不再触发 tiny_datasets/KeyError",
        "len=1–2 的序列首单在 2026-08/09，当前没有完整 3 个月目标窗，故不进入计分；"
        "guard 只保证不再抛错，不伪造评分",
        "阈值 7 来自库的实测行为（见 threshold_basis），不是按效果挑选；"
        "len>=7 的行为与扩展前完全一致",
    ]

    # ---- anomalies (never silent) ------------------------------------------
    zero_series = [s for s in short if float(np.sum(short[s]["y"])) == 0]
    constant = [s for s in short if len(short[s]["y"]) > 1
                and float(np.max(short[s]["y"])) == float(np.min(short[s]["y"]))]
    anomalies = dict(
        single_point=dict(n=len(len1), handling="naive 常数预测；无完整目标窗，本轮不计分",
                          skus=sorted(len1)),
        two_points=dict(n=len(len2), handling="naive 末值；无完整目标窗，本轮不计分",
                        skus=sorted(len2)),
        all_zero_series=dict(n=len(zero_series),
                             handling="全零序列：所有方法预测 0；若出现在可评分子集则保留（分子 0）",
                             skus=sorted(zero_series)),
        constant_series=dict(n=len(constant),
                             handling="常数序列：正常评分，不做特殊剔除",
                             skus=sorted(constant)[:10]),
        zero_actual_cells=dict(n=sum(1 for r in aligned if r["zero_actual"]),
                               handling="零需求单元格保留在 WAPE 分子，对分母贡献 0"),
        autoets_non_ok_cells=dict(n=len(fb_cells), by_reason=dict(fb_status.most_common())),
    )

    # ---- low confidence -----------------------------------------------------
    per_sku_common = Counter(r["sku"] for r in aligned)
    low_skus = sorted(s for s in short
                      if len(short[s]["y"]) < 12 or per_sku_common.get(s, 0) < 3)
    low = dict(criteria="历史 <12 个月，或共同可评分子集内窗口数 <3",
               n_low=len(low_skus), n_short=len(short),
               n_low_in_aligned=sum(1 for s in low_skus if per_sku_common.get(s, 0) > 0),
               skus=low_skus)

    runtime = dict(seconds=round(time.time() - t0, 1), cells=len(cells),
                   aligned_cells=len(aligned), origins_rule=f"step {STEP}, h={H}")

    result = dict(
        schema_version="t16_short_history/1",
        status="development validation on already-seen data — NOT an independent hold-out",
        inputs=dict(db_sha256=db_hash,
                    destinations_sha256=hashlib.sha256(DEST.read_bytes()).hexdigest()),
        pre_registered=dict(
            scope=f"eligible SKUs with <{SHORT_MAX} months inside label coverage ({LABEL_END})",
            window=f"cumulative monthly h={H} (origin+1..origin+{H})",
            origins=f"every {STEP}rd month from the first origin with >={MIN_TRAIN} training months; "
                    "target window fully inside label coverage",
            alignment="five-method common intersection of (SKU, origin), then aggregate",
            category_peer="peer needs >=24 months AT THE SAME origin; shape from the 12 months "
                          "ending at that origin",
            combo="fixed equal weight of naive/SES/TSB",
            low_confidence="history <12 months OR <3 common windows",
            metric="MAE / WAPE=Σ|F−A|/ΣA / Bias=Σ(F−A)/ΣA; zero-demand retained in numerator"),
        scope=dict(series_total=len(series), short_total=len(short),
                   buckets=dict(Counter(bucket(len(v["y"])) for v in short.values())),
                   evaluable_skus=len({r["sku"] for r in cells}),
                   aligned_skus=len({r["sku"] for r in aligned}),
                   aligned_cells=len(aligned), all_cells=len(cells)),
        methods=method_table,
        fallback_reliability=fallback,
        keyerror_guard=guard,
        anomalies=anomalies,
        low_confidence=low,
        runtime=runtime,
        wording=("开发期验证：全部数据均已见过，**不是独立留出**，不得把任何差值称为"
                 "“改进已证实”；是否换用 TSB/SES 须经前向影子与业务复核。"),
    )
    (OUT / "short_history_eval.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---------------- CSV: one row per (SKU, origin) ------------------------
    fields = (["sku", "n_history", "bucket", "origin", "target_months", "tr", "actual"]
              + METHODS + ["autoets", "autoets_status", "rule_current", "rule_tsb",
                           "rule_ses", "rule_naive", "zero_actual"])
    with (OUT / "short_history_eval.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in cells:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in fields})

    # ---------------- report ------------------------------------------------
    L = ["# T16 短历史方法对照报告", "",
         "> **开发期验证**：全部数据均已见过，**不是独立留出**；任何差值都不构成"
         "“改进已证实”。措辞只说“在已见数据上的差异”。", "",
         "## 0. 范围与预先注册的方案", "",
         f"- 短历史（<{SHORT_MAX} 月）：**{len(short)}** 条；可评分 SKU "
         f"**{len({r['sku'] for r in cells})}**、共同交集 SKU **{len({r['sku'] for r in aligned})}**、"
         f"共同交集单元格 **{len(aligned)}**（全部单元格 {len(cells)}）。",
         f"- 窗口：月度累计 h={H}（origin+1..origin+{H}），步长 **{STEP}**，"
         f"目标窗必须完全落在标签覆盖（≤{LABEL_END}）内。",
         "- 对齐：先取五方法 **(SKU, origin)** 共同交集，再聚合；不使用各方法各自子集。",
         "- 类目借力：peer 必须在该切点已有 ≥24 个月历史，形状只取截至该切点的 12 个月。",
         "- 组合：naive/SES/TSB 固定等权；低置信：历史 <12 月或共同窗口 <3 个。",
         f"- AutoETS guard（T20）：**len<{MIN_AUTOETS_LEN} 直接 fallback，不尝试 AutoETS**；"
         "阈值来自 statsforecast 2.1.1 实测（§3）。", "",
         "## 1. 各方法指标（共同交集）", "",
         "| 方法 | MAE | WAPE | Bias | 单元格 | SKU |", "|---|---:|---:|---:|---:|---:|"]
    for m in METHODS:
        v = method_table["total"][m]
        L.append(f"| {m} | {v['mae']} | {v['wape']} | {v['bias']} | "
                 f"{method_table['total']['n_cells']} | {method_table['total']['n_skus']} |")
    L += ["", "按历史长度分组（同一对齐口径）：", "",
          "| 组 | 单元格 | 方法 | MAE | WAPE | Bias |", "|---|---:|---|---:|---:|---:|"]
    for b in ("3<=n<13", "13<=n<24"):
        for m in METHODS:
            v = method_table[b][m]
            L.append(f"| {b} | {method_table[b]['n_cells']} | {m} | {v['mae']} | "
                     f"{v['wape']} | {v['bias']} |")
    L += ["", "## 2. fallback 可靠性（AutoETS 失败 → MA3 的现规则）", "",
          f"- 对齐子集内 AutoETS 失败单元格 **{len(fb_cells)}**（涉及 "
          f"{fallback['n_fallback_sku']} SKU）："
          + ("；".join(f"`{k}` × {v}" for k, v in fallback["autoets_failures"].items()) or "无"),
          f"- 全部候选单元格（{len(cells)}）上的失败计数："
          + "；".join(f"`{k}` × {v}"
                      for k, v in fallback["autoets_failures_all_cells"].items()),
          "", "失败单元格上各规则的差异（tr<7 是 AutoETS 不可用的主要区间）：", "",
          "| 规则 | 单元格 | MAE | WAPE | Bias |", "|---|---:|---:|---:|---:|"]
    for rule in RULES:
        v = fallback["by_tr"]["tr<7"][rule]
        L.append(f"| {rule} | {fallback['by_tr']['tr<7']['n_cells']} | {v['mae']} | "
                 f"{v['wape']} | {v['bias']} |")
    L += ["", "差值（相对现规则，MAE）：" + "，".join(
        f"{k} {v:+.3f}" for k, v in fallback["deltas"].items()), ""]
    if fallback.get("bootstrap_deltas"):
        L += ["SKU 重抽 300 次的 MAE 差（alt − 现规则）：", "",
              "| 替代 | 均值 | 5–95% | 区间含 0 |", "|---|---:|---|---|"]
        for alt, d in fallback["bootstrap_deltas"].items():
            L.append(f"| {alt} | {d['mean']:+.3f} | "
                     f"[{d['p5']:+.3f}, {d['p95']:+.3f}] | "
                     f"{'是' if d['p5'] <= 0 <= d['p95'] else '否'} |")
        L.append("")
    L += ["## 3. KeyError/tiny-dataset guard 前后对照", "",
          f"规则：{guard['guard_rule']}",
          f"阈值依据：{guard['threshold_basis']}", "",
          "| 历史长度 | 条数 | 修复前（raw AutoETS） | 修复后（len<7→fallback） |",
          "|---|---:|---|---|"]
    for b in ("n<3", "3<=n<13", "13<=n<24"):
        L.append(f"| {b} | {guard['before'][b]['n']} | {guard['before'][b]['status']} | "
                 f"{guard['after'][b]['status']} |")
    if guard.get("by_length"):
        L += ["", "按精确长度拆分：", "",
              "| len | 条数 | 修复前 | 修复后 |", "|---:|---:|---|---|"]
        for L2 in sorted(guard["by_length"]):
            v = guard["by_length"][L2]
            L.append(f"| {L2} | {v['n']} | {v['before']} | {v['after']} |")
    L += [""] + [f"- {n}" for n in guard["notes"]]
    a = guard["assertions"]
    L += [f"- 断言：len<7 共 {a['n_lt7']} 条全部走 fallback、预测有限；"
          f"未捕获异常 {a['uncaught_exceptions']} 条（{a['n_short']} 条短历史逐条检查）。"]
    L += ["", "## 4. 同类异常（计数与处理）", "",
          "| 异常 | 数量 | 处理 |", "|---|---:|---|",
          f"| 单点序列（len=1） | {anomalies['single_point']['n']} | {anomalies['single_point']['handling']} |",
          f"| 两点序列（len=2） | {anomalies['two_points']['n']} | {anomalies['two_points']['handling']} |",
          f"| 全零序列 | {anomalies['all_zero_series']['n']} | {anomalies['all_zero_series']['handling']} |",
          f"| 常数序列 | {anomalies['constant_series']['n']} | {anomalies['constant_series']['handling']} |",
          f"| 零需求单元格 | {anomalies['zero_actual_cells']['n']} | {anomalies['zero_actual_cells']['handling']} |",
          f"| AutoETS 非 ok 单元格 | {anomalies['autoets_non_ok_cells']['n']} | 按原因保留并回退 MA3 |", "",
          "## 5. 低置信标记", "",
          f"- 判定：{low['criteria']}",
          f"- 数量：**{low['n_low']} / {low['n_short']}**（其中进入对齐子集 "
          f"{low['n_low_in_aligned']} 条）。", "",
          "## 6. 结论与建议（开发期，非独立留出）", ""]
    total = method_table["total"]
    best = min(METHODS, key=lambda m: total[m]["mae"])
    worst = max(METHODS, key=lambda m: total[m]["mae"])
    bs = fallback.get("bootstrap_deltas", {})
    worse = [a for a, d in bs.items() if d["p5"] > 0]
    indist = [a for a, d in bs.items() if d["p5"] <= 0 <= d["p95"]]
    better = [a for a, d in bs.items() if d["p95"] < 0]
    verdict = ("**结论：不建议**仅凭本表改用 TSB/SES——"
               + ("没有任何替代方法的区间整体更优；"
                  + ("、".join(a.replace('rule_', '') for a in indist)
                     + " 与现规则不可区分（区间跨 0）；" if indist else "")
                  + ("、".join(a.replace('rule_', '') for a in worse)
                     + " 点估计更差但区间同样跨 0；" if worse else "")
                  + "现规则（AutoETS 失败→MA3）保留。")
               if not better else
               ("**结论**：" + "、".join(a.replace('rule_', '') for a in better)
                + " 的区间整体优于现规则，但也只能作为前向影子候选，不直接改默认。"))
    L += [f"- 在已见的 {len(aligned)} 个共同交集单元格上，MAE 最低的是 **{best}**"
          f"（{total[best]['mae']}），最高的是 **{worst}**（{total[worst]['mae']}）；"
          "这只是已见数据上的差异，不是独立验证。",
          f"- fallback（tr<7，{fallback['by_tr']['tr<7']['n_cells']} 格）相对现规则的 MAE 差："
          + "，".join(f"{a.replace('rule_', '')} {d['mean']:+.3f}"
                     f"（[{d['p5']:+.3f}, {d['p95']:+.3f}]）" for a, d in bs.items()) + "。",
          "- 判定（区间是否跨 0）：更差且区间不含 0 = "
          + (", ".join(a.replace('rule_', '') for a in worse) or "无")
          + "；与现规则不可区分 = " + (", ".join(a.replace('rule_', '') for a in indist) or "无")
          + "；明确更优 = " + (", ".join(a.replace('rule_', '') for a in better) or "无")
          + "。",
          f"- {verdict}",
          f"- 计算规模：{runtime['cells']} 个候选单元格、{runtime['seconds']} s。", "",
          "## 7. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/"
          "experiments/business_phase/forecast_eval/short_history_eval.py",
          "uv run python scripts/check_secrets.py",
          "```", "",
          "DB 只读（前后 sha256 一致）；脚本确定性（固定切点、固定方法参数）。", ""]
    (OUT / "short_history_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("wrote short_history_eval.json / .csv / short_history_report.md")
    print("cells", len(cells), "aligned", len(aligned),
          "buckets", result["scope"]["buckets"])
    print("methods", {m: method_table["total"][m]["mae"] for m in METHODS})
    print("fallback", fallback["deltas"])
    print("runtime", runtime["seconds"])


if __name__ == "__main__":
    main()
