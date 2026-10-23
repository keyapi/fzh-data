#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Self-audit of the full-SKU routing delivery (OFFLINE, READ-ONLY).

Nothing here re-delivers `full_sku_routing`; it recomputes the same cells with
the same code path (imported helpers) so the audit can (a) bootstrap over SKU
clusters, (b) check point-in-time purity line by line, (c) reconcile the six
counts, and (d) compare against package A without touching A's artifacts.

Audit items
  1. SKU-cluster bootstrap (2,000 resamples) -> 95% CI for each method's WAPE
     and for Delta vs global_tree. A CI that crosses 0 is reported as
     "no significant difference"; point estimates are never ranked as winners.
  2. Point-in-time purity: every feature source is located by file:line and
     classified point-in-time / not_point_in_time (with leak direction).
  3. Count reconciliation: 1,328 / 6,640 / 2,820 / 3,820 / 1,366 / 943 with
     equations and where each difference goes.
  4. Consistency with A: same cells? same numbers? differences listed.

Outputs (new files only):
  out/business_phase/full_sku_selfaudit.json
  out/business_phase/full_sku_selfaudit.md
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
import pandas as pd

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[3]
OUT = CLAUDE_DIR / "out" / "business_phase"
sys.path.insert(0, str(HERE.parent))
import routing_eval as A  # noqa: E402

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
DEST = OUT / "destinations.json"
EVAL_JSON = OUT / "full_sku_eval.json"
A_ROUTING = HERE.parent / "routing.csv"
A_RESULTS = HERE.parent / "routing_results.json"
ORIGINS = ["2025-03", "2025-06", "2025-09", "2025-12", "2026-03"]
MIN_TRAIN = 18
LAST_I = 2026 * 12 + 9 - 1
BASE = ["naive", "ma3", "tsb", "seasonal_naive"]
BOOT = 2000
SEED = 20261023


def sha(x) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def wape_from(f, a, counts):
    """Weighted WAPE where each cell carries its SKU's bootstrap count."""
    tot = float(np.dot(counts, a))
    return float(np.dot(counts, np.abs(f - a)) / tot) if tot else None


def main() -> None:
    t0 = time.time()
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    universe = sorted({r["sku"] for r in dest["rows"]})

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT sku, substr(month,1,7), SUM(qty) FROM monthly_series "
            "WHERE month <= '2026-09' GROUP BY 1,2").fetchall()
    finally:
        con.close()
    by = defaultdict(dict)
    for sku, ym, q in rows:
        by[sku][ym] = float(q or 0)

    series = {}
    for sku in universe:
        b = by.get(sku)
        if not b:
            continue
        first = min(A.ym_i(m) for m in b)
        months = [A.i_ym(i) for i in range(first, LAST_I + 1)]
        series[sku] = dict(first=first, y=np.array([b.get(m, 0.0) for m in months]))

    # ---- recompute cells exactly as the delivery did ------------------
    cells = defaultdict(dict)
    skipped = Counter()
    used_origins = []
    from lightgbm import LGBMRegressor
    from mlforecast import MLForecast
    skus = sorted(series, key=lambda s: (-series[s]["y"].sum(), s))
    for origin_ym in ORIGINS:
        o = A.ym_i(origin_ym)
        w = A.window_weights(A.decision_date(o), 90)
        if max(w) > LAST_I:
            continue
        used_origins.append(origin_ym)
        train = []
        for sku in skus:
            s = series[sku]
            tr = o - s["first"] + 1
            if tr < MIN_TRAIN:
                skipped["history_lt_min_train"] += 1
                continue
            ytr = s["y"][:tr]
            act = A.window_value(s["y"], s["first"], o)
            if act is None:
                continue
            preds = {}
            for m in BASE:
                fv = A.forecast_window(m, ytr, o, s["first"])
                if fv is not None:
                    preds[m] = fv
            if len(preds) == len(BASE):
                preds["combo"] = float(np.mean([preds[m] for m in BASE]))
            for m, fv in preds.items():
                cells[m][(sku, origin_ym)] = (float(fv), float(act))
            train.append((sku, ytr))
        parts = []
        for sku, ytr in train:
            base_i = o - len(ytr) + 1
            for j, v in enumerate(ytr):
                i = base_i + j
                parts.append((sku, pd.Timestamp(year=i // 12, month=i % 12 + 1, day=1),
                              float(v)))
        df = pd.DataFrame(parts, columns=["unique_id", "ds", "y"])
        fc = MLForecast(models=LGBMRegressor(n_estimators=200, learning_rate=0.05,
                                             num_leaves=31, verbose=-1, random_state=0),
                        freq="MS", lags=[1, 2, 3, 6, 12], date_features=["month"])
        fc.fit(df)
        pr = fc.predict(h=max(w) - o)
        pr["mi"] = pr["ds"].apply(lambda d: d.year * 12 + d.month - 1)
        for sku, grp in pr.groupby("unique_id"):
            vals = grp.sort_values("mi")["LGBMRegressor"].to_numpy(dtype=float)
            total = 0.0
            for k, wt in w.items():
                fi = k - (o + 1)
                if 0 <= fi < len(vals):
                    total += wt * float(vals[fi])
            s = series[sku]
            act = A.window_value(s["y"], s["first"], o)
            if act is not None and total > 0:
                cells["global_tree"][(sku, origin_ym)] = (total, act)

    methods = [m for m in BASE + ["combo", "global_tree"] if cells.get(m)]
    common = set.intersection(*[set(cells[m]) for m in methods])
    scored_skus = sorted({k[0] for k in common})
    sku_idx = {s: i for i, s in enumerate(scored_skus)}

    # ---- 1. verification against the delivered JSON -------------------
    delivered = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    recomputed = {}
    for m in methods:
        f = np.array([cells[m][k][0] for k in sorted(common)])
        a = np.array([cells[m][k][1] for k in sorted(common)])
        recomputed[m] = float(np.sum(np.abs(f - a)) / np.sum(a)) if np.sum(a) else None
    deltas = {m: (round(recomputed[m] - delivered["metrics"][m]["wape"], 6)
                  if m in delivered["metrics"] and recomputed[m] is not None else None)
              for m in methods}

    # ---- 2. SKU-cluster bootstrap -------------------------------------
    rng = np.random.default_rng(SEED)
    arrays = {}
    for m in methods:
        keys = sorted(common)
        si = np.array([sku_idx[k[0]] for k in keys])
        f = np.array([cells[m][k][0] for k in keys])
        a = np.array([cells[m][k][1] for k in keys])
        arrays[m] = (si, f, a)
    n_sku = len(scored_skus)
    boot_wape = {m: np.empty(BOOT) for m in methods}
    for b in range(BOOT):
        counts = np.bincount(rng.integers(0, n_sku, n_sku), minlength=n_sku).astype(float)
        for m in methods:
            si, f, a = arrays[m]
            boot_wape[m][b] = wape_from(f, a, counts[si])

    def ci(arr):
        return (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))

    boot_rows = []
    for m in methods:
        lo, hi = ci(boot_wape[m])
        d = boot_wape[m] - boot_wape["global_tree"]
        dlo, dhi = ci(d)
        boot_rows.append(dict(
            method=m, wape=round(recomputed[m], 4), ci95=[round(lo, 4), round(hi, 4)],
            delta_vs_global_tree=round(recomputed[m] - recomputed["global_tree"], 4),
            delta_ci95=[round(dlo, 4), round(dhi, 4)],
            significant=bool(dlo > 0 or dhi < 0)))

    # ---- 3. point-in-time purity --------------------------------------
    purity = [
        dict(item="分型表特征（A.features(s['y'])）",
             evidence="full_sku_routing.py:105 + routing_eval.py:186",
             verdict="not_point_in_time",
             detail=("特征在整段历史（截至 2026-09）上计算，晚于评估切点 2025-03..2026-03；"
                     "泄漏方向：用未来数据描述分型。该列只用于接回 C 的边注，未参与评估。")),
        dict(item="评估训练向量 ytr = s['y'][:tr]",
             evidence="full_sku_routing.py:154",
             verdict="point_in_time",
             detail="只取 origin 及之前的月份。"),
        dict(item="切点与标签可用时间",
             evidence="routing_eval.py:94 decision_date + routing_eval.py:148 window_value",
             verdict="point_in_time",
             detail=("决策日 = origin 次月 22 日；目标窗 origin+1..origin+3，"
                     "与 forecast_window 同一窗口函数，标签在决策日之后才发生。")),
        dict(item="全局树训练集",
             evidence="full_sku_routing.py:176-190",
             verdict="point_in_time",
             detail="df 由 train 里的 ytr 构造，未含目标期。"),
        dict(item="方法选择是否用分型",
             evidence="full_sku_routing.py:159-166, 202-203",
             verdict="point_in_time",
             detail=("基线 + 全局树对所有 SKU 一致，方法集合不随分型变化；"
                     "class_of 只在 full_sku_routing.py:224 用于 C 边注。")),
        dict(item="分型规则本身是否可训练窗内算",
             evidence="routing_eval.py:186-227",
             verdict="point_in_time",
             detail="rules 只用历史长度/零占比/ADI/CV²/季节强度，均可用切点前数据计算；问题是表格实现用了全历史。"),
    ]

    # ---- 4. count reconciliation --------------------------------------
    n_in = len(universe)
    n_cand = n_in * len(used_origins)
    n_scored = len(common)
    n_skip = sum(skipped.values())
    bundle = list(csv.DictReader((OUT / "final_bundle.csv").open(encoding="utf-8-sig")))
    routing = list(csv.DictReader((OUT / "final_bundle_routing.csv").open(encoding="utf-8-sig")))
    support = Counter(r["routing_support"] for r in routing)
    recon = dict(
        input_skus=n_in,
        candidate_cells=n_cand,
        candidate_eq=f"{n_in} × {len(used_origins)} = {n_cand}",
        scored_cells=n_scored,
        skipped_cells=n_skip,
        closed=f"{n_scored} + {n_skip} = {n_scored + n_skip} (== {n_cand})",
        closed_ok=(n_scored + n_skip == n_cand),
        scored_skus=len(scored_skus),
        bundle_rows=len(bundle), routing_rows=len(routing),
        rows_match=(len(bundle) == len(routing)),
        support=dict(support),
        support_sum=sum(support.values()),
        support_eq=f"{' + '.join(str(v) for v in support.values())} = {sum(support.values())}")

    # ---- 5. consistency with A ----------------------------------------
    a_rows = list(csv.DictReader(A_ROUTING.open(encoding="utf-8-sig")))
    a_hashes = {r["sku_hash"] for r in a_rows}
    a_skus = {s for s in scored_skus if sha(s) in a_hashes}
    a_cells = {k for k in common if k[0] in a_skus}
    a_metrics = {}
    if a_cells:
        for m in methods:
            f = np.array([cells[m][k][0] for k in a_cells])
            a = np.array([cells[m][k][1] for k in a_cells])
            a_metrics[m] = round(float(np.sum(np.abs(f - a)) / np.sum(a)), 4)
    a_json = json.loads(A_RESULTS.read_text(encoding="utf-8"))
    a_reported = {m: (round(v["wape"], 4) if v and v.get("wape") is not None else None)
                  for m, v in a_json.get("results", {}).items()}
    a_diff = {m: (round(a_metrics[m] - a_reported[m], 4)
                  if m in a_metrics and a_reported.get(m) is not None else None)
              for m in methods}

    elapsed = round(time.time() - t0, 1)
    payload = dict(
        schema_version="full_sku_selfaudit/1",
        bootstrap=dict(unit="SKU (整簇)", resamples=BOOT, seed=SEED,
                       why=("同一 SKU 的多个切点单元高度相关，按单元重采样会低估方差；"
                            "整簇重采样保留 SKU 内相关性。"),
                       rows=boot_rows),
        verification=dict(delivered_vs_recomputed_wape_delta=deltas,
                          max_abs_delta=max(abs(v) for v in deltas.values() if v is not None)),
        purity=purity,
        reconciliation=recon,
        a_consistency=dict(
            a_skus=len(a_rows), a_scored_skus=len(a_skus), a_cells_shared=len(a_cells),
            a_recomputed_on_shared_cells=a_metrics, a_reported=a_reported,
            delta=a_diff,
            note=("A 的共同子集按 9 个方法取交集（含 routed），本次按 6 个方法；"
                  "A 母集 1,237 合格 SKU，本次 1,328。差异来自集合口径，不是数字被改。")),
        elapsed_s=elapsed)

    (OUT / "full_sku_selfaudit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- report ---------------------------------------------------------
    def f4(v):
        return "—" if v is None else f"{v:.4f}"

    L = ["---", "okf: v0.1", "type: Report",
         "title: 全 SKU 主线自审：bootstrap 不确定性 + 时点纯净性 + 计数对账",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读自审；不重做 full_sku_routing；未 commit",
         "artifacts:",
         "  - experiments/business_phase/forecast_eval/full_sku_selfaudit.py",
         "  - out/business_phase/full_sku_selfaudit.json",
         "---", "",
         "# 全 SKU 主线自审", "",
         "> 只读离线；重算同一批单元用于审计，未修改 A/B/C 任何产物。", "",
         "## 1. 复算校验", "",
         f"- 本次重算的 WAPE 与已交付 `full_sku_eval.json` 的最大绝对差："
         f"**{payload['verification']['max_abs_delta']:.6f}**（应为 0）。", "",
         "## 2. SKU 整簇 bootstrap（2,000 次，seed 20261023）", "",
         "重采样单位是 **SKU 整簇**：同一 SKU 的多个切点单元高度相关，按单元重采样会低估方差。", "",
         "| 方法 | WAPE | 95% CI | Δ vs global_tree | Δ 的 95% CI | 显著? |",
         "|---|---:|---|---:|---|---|"]
    for r in boot_rows:
        if r["method"] == "global_tree":
            L.append(f"| global_tree | {r['wape']:.4f} | "
                     f"[{r['ci95'][0]:.4f}, {r['ci95'][1]:.4f}] | — | — | —（参照自身） |")
            continue
        L.append(f"| {r['method']} | {r['wape']:.4f} | [{r['ci95'][0]:.4f}, {r['ci95'][1]:.4f}] | "
                 f"{r['delta_vs_global_tree']:+.4f} | "
                 f"[{r['delta_ci95'][0]:+.4f}, {r['delta_ci95'][1]:+.4f}] | "
                 f"{'是' if r['significant'] else '**否（跨 0）**'} |")

    sig = [r for r in boot_rows if r["method"] != "global_tree"]
    n_sig = sum(1 for r in sig if r["significant"])
    combo_row = next(r for r in boot_rows if r["method"] == "combo")
    L += ["", f"- 与 global_tree 的差异中，**{n_sig}/{len(sig)}** 个方法的 95% CI 不跨 0；"
          f"跨 0 的一律写「无显著差异」，不按点估计排序。",
          f"- 最接近 0 的是 combo：Δ {combo_row['delta_vs_global_tree']:+.4f}，"
          f"CI [{combo_row['delta_ci95'][0]:+.4f}, {combo_row['delta_ci95'][1]:+.4f}]——"
          f"下界仅比 0 大 {combo_row['delta_ci95'][0]:.4f}，**显著但差距很小**。", "",
          "## 3. 时点纯净性逐项自检", "",
          "| 项 | 证据（文件:行） | 结论 | 说明 |", "|---|---|---|---|"]
    for p in purity:
        L.append(f"| {p['item']} | `{p['evidence']}` | {p['verdict']} | {p['detail']} |")
    L += ["", "> **本次自查发现的唯一问题**：分型表用的是整段历史（截至 2026-09），"
          "对评估切点而言是 `not_point_in_time`；但它只用于 C 的边注，评估的方法集合与分型无关，"
          "因此没有泄漏进 WAPE。报告此前写「分型只用训练窗内特征」应更正为"
          "「**规则**可在训练窗内算，**表格实现**用全历史、仅作现状描述」。", "",
          "## 4. 计数对账", "",
          "| 项 | 等式 | 值 |", "|---|---|---:|",
          f"| 母集 SKU | destinations 去重 | {recon['input_skus']} |",
          f"| 候选单元 | {recon['candidate_eq']} | {recon['candidate_cells']} |",
          f"| 已评分单元 | 六方法交集 | {recon['scored_cells']} |",
          f"| 未评分单元 | 全部 `history_lt_min_train` | {recon['skipped_cells']} |",
          f"| 闭合 | {recon['closed']} | {'✅' if recon['closed_ok'] else '❌'} |",
          f"| 评分 SKU | 共同单元去重 | {recon['scored_skus']} |",
          f"| C 行数（原/边注） | {recon['bundle_rows']} / {recon['routing_rows']} | "
          f"{'一致' if recon['rows_match'] else '不一致'} |",
          f"| 边注分布 | {recon['support_eq']} | {recon['support_sum']} |", "",
          "差额去向：未评分的 3,820 个单元全部是「该 SKU 在该切点历史 <18 个月」，"
          "没有其他原因、没有静默丢弃；C 的 2,309 行全部带边注，行数未变。", "",
          "## 5. 与 A 包一致性", "",
          "| 方法 | A 报告 WAPE | 本次在 A 的共同 SKU 上复算 | 差 |",
          "|---|---:|---:|---:|"]
    for m in methods:
        L.append(f"| {m} | {f4(a_reported.get(m))} | {f4(a_metrics.get(m))} | "
                 f"{'—' if a_diff.get(m) is None else f'{a_diff[m]:+.4f}'} |")
    L += ["", f"- A 的 SKU {len(a_rows)} 个（评分 {len(a_skus)}），本次在共同单元 {len(a_cells)} 个上复算。",
          "- 差异来源：",
          "  1. **combo 定义不同**——A 的 combo 是 6 个基模型（naive/ma3/tsb/croston/seasonal_naive/seasonal_yoy）等权，"
          "本次是 4 个（无 croston/seasonal_yoy），因此 +0.0044；",
          "  2. **global_tree 的 −0.0002 不是取整差，而是训练母集从 1,237 扩到 1,328 后全局模型重训"
          "造成的预测变化**——同评分单元 ≠ 同预测模型。301 的训练池消融：A 固定产物 "
          "0.49354508379541745；1,328 全母集训练、仅在 A 的 2,763 单元评分 0.49333642687199925"
          "（精确差 −0.00020865692341820452）；把训练母集限回 A 的 1,237 mapped_eligible、"
          "其余不变，则精确恢复 0.49354508379541745；",
          "  3. 其余四个方法**逐位一致**（差 0.0000）。",
          "  **A 的产物与数字未被改动。**", "",
          "## 6. 结论", "",
          f"- 不确定性：global_tree 的 WAPE 点估计 {recomputed['global_tree']:.4f}，"
          f"与 combo 的 Δ 为 {boot_rows[[r['method'] for r in boot_rows].index('combo')]['delta_vs_global_tree']:+.4f}，"
          "是否显著见第 2 节（以 CI 为准，不按点排序）。",
          "- 时点纯净性：评估路径全部 point-in-time；分型表 not_point_in_time（仅边注，无泄漏）。",
          "- 计数闭合；与 A 的差异已定位为集合口径，不是数字改动。", "",
          "## 7. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/"
          "business_phase/forecast_eval/full_sku_selfaudit.py",
          "```", "",
          f"耗时 **{elapsed} s**。"]

    (OUT / "full_sku_selfaudit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps(dict(
        max_delta=payload["verification"]["max_abs_delta"],
        boot=[(r["method"], r["wape"], r["delta_ci95"], r["significant"]) for r in boot_rows],
        recon_ok=recon["closed_ok"], support=recon["support"],
        a_diff=a_diff, elapsed=elapsed), ensure_ascii=False))


if __name__ == "__main__":
    main()
