#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full-SKU routing + global LightGBM vs baselines, mapped back to bundle C (OFFLINE).

Scope (mother set = the 1,328 SKUs in `destinations.json`, the same base C uses):
  1. classify every SKU with rules that are computable inside the training window
     (平滑 / 间歇 / 季节 / 新品短史 / 证据不足) — never from outer evaluation results;
  2. compare a global tree model (MLForecast + LightGBM, already present in the
     venv — nothing is installed) against the baselines on the SAME (SKU, origin)
     cells and the SAME 90-day windows that package A used;
  3. map the classification back onto C's 2,309 rows as an annotation only —
     C's numbers are copied verbatim, never changed.

Reuse, not rerun: A's `routing_eval.py` helpers are imported (no re-execution),
B's `linkage_audit_v2.csv` and C's `final_bundle.csv` are read-only inputs.

Hard constraints honoured here: DB read_only, no production access, no package
install, no commit/push, no claim that one model is best.

Outputs (all new files):
  out/business_phase/full_sku_classification.csv
  out/business_phase/full_sku_eval.json
  out/business_phase/final_bundle_routing.csv
  out/business_phase/full_sku_routing.md
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
import routing_eval as A  # noqa: E402  (reuse A's forecasting + window helpers)

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
DEST = OUT / "destinations.json"
BUNDLE = OUT / "final_bundle.csv"
ORIGINS = ["2025-03", "2025-06", "2025-09", "2025-12", "2026-03"]
MIN_TRAIN = 18
LAST_I = 2026 * 12 + 9 - 1
BASE = ["naive", "ma3", "tsb", "seasonal_naive"]


def sha(x) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def pct(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def num(v, nd=3):
    return "—" if v is None else f"{v:.{nd}f}"


def main() -> None:
    t0 = time.time()
    dest = json.loads(DEST.read_text(encoding="utf-8"))
    universe = sorted({r["sku"] for r in dest["rows"]})
    dest_map = {r["sku"]: r for r in dest["rows"]}

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
        series[sku] = dict(first=first, y=np.array([b.get(m, 0.0) for m in months]),
                           months=months)

    # ---- 1. classification (training-window features only) ------------
    class_rows, class_of = [], {}
    for sku in universe:
        s = series.get(sku)
        if not s:
            typ = "证据不足"
            f = dict(n_hist=0, zero_share=None, adi=None, cv2=None,
                     seasonal_strength=None, total_qty=0.0)
            reason = "no_monthly_series"
        else:
            f = A.features(s["y"])
            if f["n_hist"] < 12:
                typ, reason = "证据不足", "history_lt_12m"
            elif f["n_hist"] < 24:
                typ, reason = "新品短史", "history_12_23m"
            else:
                typ = {"intermittent": "间歇", "seasonal": "季节",
                       "simple": "平滑", "short": "新品短史"}[A.route_type(f)]
                reason = ""
        class_of[sku] = typ
        class_rows.append(dict(
            sku_hash=sha(sku), sku=sku, type=typ, reason=reason,
            n_hist=f["n_hist"], zero_share=f["zero_share"], adi=f["adi"],
            cv2=f["cv2"], seasonal_strength=f["seasonal_strength"],
            total_qty=round(f["total_qty"], 2),
            destination=dest_map.get(sku, {}).get("destination", "")))

    csv_path = OUT / "full_sku_classification.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(class_rows[0].keys()))
        w.writeheader()
        w.writerows(class_rows)

    # ---- 2. evaluation on A's cells -----------------------------------
    skus = sorted(series, key=lambda s: (-series[s]["y"].sum(), s))
    cells = defaultdict(dict)
    unscored = Counter()
    used_origins = []
    tree_ok, tree_note = False, ""
    try:
        from lightgbm import LGBMRegressor
        from mlforecast import MLForecast
        tree_ok = True
    except Exception as exc:                     # noqa: BLE001
        tree_note = f"unavailable: {type(exc).__name__}: {exc}"

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
                unscored["history_lt_min_train"] += 1
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

        if tree_ok:
            try:
                parts = []
                for sku, ytr in train:
                    base_i = o - len(ytr) + 1
                    for j, v in enumerate(ytr):
                        i = base_i + j
                        parts.append((sku, pd.Timestamp(year=i // 12, month=i % 12 + 1,
                                                        day=1), float(v)))
                df = pd.DataFrame(parts, columns=["unique_id", "ds", "y"])
                fc = MLForecast(models=LGBMRegressor(n_estimators=200, learning_rate=0.05,
                                                     num_leaves=31, verbose=-1,
                                                     random_state=0),
                                freq="MS", lags=[1, 2, 3, 6, 12], date_features=["month"])
                fc.fit(df)
                h = max(w) - o
                pr = fc.predict(h=h)
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
            except Exception as exc:             # noqa: BLE001
                tree_ok = False
                tree_note = f"fit failed at {origin_ym}: {type(exc).__name__}: {exc}"

    methods = [m for m in BASE + ["combo", "global_tree"] if cells.get(m)]
    common = set.intersection(*[set(cells[m]) for m in methods]) if methods else set()

    def metric(m):
        vals = [cells[m][k] for k in common]
        if not vals:
            return dict(n=0, wape=None, bias=None, mae=None)
        ae = sum(abs(F - A2) for F, A2 in vals)
        tot = sum(A2 for _F, A2 in vals)
        return dict(n=len(vals), wape=(ae / tot if tot else None),
                    bias=(sum(F - A2 for F, A2 in vals) / tot if tot else None),
                    mae=ae / len(vals))

    metrics = {m: metric(m) for m in methods}

    # ---- 3. map back onto C (annotation only) -------------------------
    bundle = list(csv.DictReader(BUNDLE.open(encoding="utf-8-sig", newline="")))
    scored_skus = {k[0] for k in common}
    c_rows = []
    m = Counter()
    for r in bundle:
        sku = r["SKU"]
        typ = class_of.get(sku, "证据不足")
        if sku not in series:
            support = "无月度序列"
        elif sku in scored_skus:
            support = "支持充足（本批已评分）" if typ != "证据不足" else "支持不足（证据不足型）"
        else:
            support = "支持不足（未进入共同单元）"
        m[support] += 1
        r2 = dict(r)
        r2["routing_type"] = typ
        r2["routing_support"] = support
        c_rows.append(r2)
    with (OUT / "final_bundle_routing.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(c_rows[0].keys()))
        w.writeheader()
        w.writerows(c_rows)

    elapsed = round(time.time() - t0, 1)

    # ---- reconciliation ------------------------------------------------
    n_in = len(universe)
    n_series = len(series)
    n_scored = len(scored_skus)
    recon = dict(
        input_skus=n_in,
        with_monthly_series=n_series,
        without_series=n_in - n_series,
        classified=sum(1 for c in class_rows if c["type"] != "证据不足"),
        insufficient_evidence=n_in - sum(1 for c in class_rows if c["type"] != "证据不足"),
        scored_skus=n_scored,
        unscored_skips_sumi=sum(unscored.values()),
        unscored_reasons=dict(unscored),
        c_rows=len(c_rows),
        c_support=dict(m))

    payload = dict(
        schema_version="full_sku_routing/1",
        inputs=dict(db=str(DB_PATH), destinations=str(DEST), bundle=str(BUNDLE),
                    origins=used_origins, min_train=MIN_TRAIN, methods=methods),
        tree=dict(available=tree_ok, note=tree_note),
        classes=dict(Counter(c["type"] for c in class_rows)),
        metrics=metrics,
        common_cells=len(common),
        reconciliation=recon,
        elapsed_s=elapsed,
        boundaries=[
            "分型只用训练窗内特征，未用外层评估结果反定型",
            "全局树使用同一批单元与同一 90 天窗口；不宣称单一最优模型",
            "C 的数字原样复制，只新增 routing_type / routing_support 两列",
            "证据不足型（<12 个月）不进入评估，也不被外推",
        ])
    (OUT / "full_sku_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- report --------------------------------------------------------
    L = ["---", "okf: v0.1", "type: Report",
         "title: 全 SKU 分型 + 全局 LightGBM 对照 + 接回 C",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读离线；复用 A/B/C；未 commit",
         "artifacts:",
         "  - experiments/business_phase/forecast_eval/full_sku_routing.py",
         "  - out/business_phase/full_sku_classification.csv",
         "  - out/business_phase/full_sku_eval.json",
         "  - out/business_phase/final_bundle_routing.csv",
         "---", "",
         "# 全 SKU 分型 + 全局 LightGBM 对照 + 接回 C", "",
         "> 只读离线：DB `read_only`，复用 A（`routing_eval.py` 助手函数）、B、C 的产物，不重跑；"
         "未安装任何新依赖（mlforecast / lightgbm 已在环境里）。", "",
         "## 1. 分型表（母集 1,328 SKU）", "",
         "规则（训练窗内可算，绝不用外层结果定型）：",
         "`<12 月` → 证据不足；`12–23 月` → 新品短史；`零占比≥0.4 或 ADI≥2.0` → 间歇；"
         "`季节强度≥0.3` → 季节；其余 → 平滑。", "",
         "> 分型表是**截至 2026-09 的现状描述**（用全历史算特征）；"
         "下面的评估是滚动切点、与分型表独立，不用分型结果选模型。", "",
         "| 类型 | SKU 数 |", "|---|---:|"]
    for k, v in sorted(payload["classes"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} |")

    L += ["", "## 2. 同单元同指标对照（共同子集）", "",
          f"- 切点：{', '.join(used_origins)}；最少训练 {MIN_TRAIN} 个月；90 天窗口；"
          f"共同单元 **{len(common)}** 个、**{n_scored}** 个 SKU。", "",
          "| 方法 | n | WAPE | Bias | MAE |", "|---|---:|---:|---:|---:|"]
    for m in methods:
        r = metrics[m]
        L.append(f"| {m} | {r['n']} | {num(r['wape'])} | {num(r['bias'])} | {num(r['mae'], 2)} |")
    L += ["", f"> 全局树可用：**{tree_ok}**{('；' + tree_note) if tree_note else ''}。"
          "本表只作同口径对照，不宣称单一最优模型。", ""]

    L += ["## 3. 覆盖对账（入 N 出 M）", "",
          "| 项 | 数 |", "|---|---:|",
          f"| 入：母集 SKU | {recon['input_skus']} |",
          f"| 有月度序列 | {recon['with_monthly_series']} |",
          f"| 无月度序列 → 证据不足 | {recon['without_series']} |",
          f"| 已判型（非证据不足） | {recon['classified']} |",
          f"| 证据不足 | {recon['insufficient_evidence']} |",
          f"| 评估评分 SKU | {recon['scored_skus']} |",
          f"| 候选单元 SKU×切点 | {recon['input_skus'] * len(used_origins)} |",
          f"| 已评分单元 | {len(common)} |",
          f"| 未评分跳过（SKU×切点） | {recon['unscored_skips_sumi']}（{recon['unscored_reasons']}） |",
          f"| 出：C 行数（带边注） | {recon['c_rows']} |", ""]

    L += ["## 4. 接回 C 的映射统计（只加边注，不改数字）", "",
          "| routing_support | 行数 |", "|---|---:|"]
    for k, v in sorted(recon["c_support"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} |")
    L += ["", "> `final_bundle_routing.csv` = C 的 `final_bundle.csv` 全列原样 + `routing_type` / "
          "`routing_support` 两列；C 的任何数字都未被修改。", "",
          "## 5. 可外推边界", "",
          "- 分型只描述**训练窗内**的可观测形态，不预测未来是否有促销/改款。",
          "- 证据不足（<12 月）的 SKU 不进入评估，映射到 C 时标「支持不足」，不外推。",
          "- 全局树与基线在同一批单元上比较，结论限于本批 SKU 与切点。", "",
          "## 6. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/"
          "business_phase/forecast_eval/full_sku_routing.py",
          "```", "",
          f"耗时 **{elapsed} s**。"]

    (OUT / "full_sku_routing.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps(recon, ensure_ascii=False))
    print("metrics", json.dumps({k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                                     for kk, vv in v.items()} for k, v in metrics.items()},
                                ensure_ascii=False))
    print(f"elapsed={elapsed}s tree_ok={tree_ok}")


if __name__ == "__main__":
    main()
