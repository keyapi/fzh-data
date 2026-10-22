#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T17: model sensitivity for the full 1,328-SKU scope.

One fixed inventory/supply reality, five demand calibers
--------------------------------------------------------
Everything except the DEMAND forecast is held identical to T3/T5:
  * the same `decision_v2.csv` rows (available / PO / in-transit / in-production
    dedupe status, L60/L90/L120 windows, shared pool NOT transferable by
    default, MOQ as a separate pending column);
  * the same warehouse allocation (SKU forecast x warehouse share of the SKU's
    last-3-month sales);
  * the same stress lift (MA3-residual quantile, clipped at 3x) for every
    caliber, so only the demand path changes;
  * the same conditional lower/upper formulas:
        lower = max(0, demand_P50_L90 - (available + deduped batch))
        upper = max(0, demand_stress_L90 - available)

Calibers (SKU level, monthly, forecast from 2026-10)
  MA3, naive, seasonal_naive, fixed equal-weight combo (MA3/naive/seasonal_naive),
  AutoETS. AutoETS is fitted exactly like T5; where it is unavailable it falls
  back to MA3 and the row says so (T16 conclusion). seasonal_naive falls back to
  MA3 for history <13 months and is marked.

Per SKU x warehouse the table lists, separately (no composite score, no
unfounded thresholds):
  * five conditional recommendation intervals [lower, upper];
  * direction (0 vs positive) per caliber;
  * direction consistency / interval overlap / quantity difference (absolute
    and relative to the median lower);
  * sales and sales coverage.

Three review lists
  1. zero/positive divergence (highest priority for manual review);
  2. same direction but the five intervals share no common point (review);
  3. all five calibers give the same lower value (a basis for review priority,
     NOT proof of correctness and NOT a purchase approval).
Rows that are same-direction with overlapping intervals but different values
are counted as a residual category, not silently dropped.

Wording: this is a sensitivity table under stated assumptions. It is not a
statistical proof, not a purchase approval, and agreement between calibers is
not "correctness".

Outputs: out/business_phase/model_sensitivity.csv, model_sensitivity.md
"""
from __future__ import annotations

import csv
import hashlib
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
from build_iteration_v2 import (  # noqa: E402  (same T3/T5 windows + helpers)
    DECISION_DATE, LEADS, WINDOW_LAST, conf_q, i_ym, window_weights, ym_i)

CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
DECISION = OUT / "decision_v2.csv"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
OUT_CSV = OUT / "model_sensitivity.csv"
OUT_MD = OUT / "model_sensitivity.md"

CALIBERS = ["MA3", "naive", "seasonal_naive", "combo_ew", "AutoETS"]
LAST_I = ym_i(WINDOW_LAST)
W = {d: window_weights(DECISION_DATE, d) for d in LEADS}
H = max(W[120]) - LAST_I
CAT_DIV = "①0/正量分歧"
CAT_GAP = "②同向·区间不重叠"
CAT_SAME = "③五口径一致"
CAT_OTHER = "④同向·区间重叠·有数量差"
CAT_C = "范围外(C)"
CAT_UNKNOWN = "库存未知"
CAT_NOHIST = "无历史"


def ym_series(y: np.ndarray, n: int) -> dict:
    """Five monthly forecast vectors starting at last_i+1 (length H)."""
    h = H
    k = min(3, n)
    ma3 = np.repeat(float(np.mean(y[-k:])), h) if k else np.zeros(h)
    naive = np.repeat(y[-1], h)
    out = {"MA3": (ma3, "ok"), "naive": (naive, "ok")}
    if n >= 13:
        sn = np.array([y[n - 12 + (j % 12)] for j in range(h)], dtype=float)
        out["seasonal_naive"] = (sn, "ok")
    else:
        sn = ma3.copy()
        out["seasonal_naive"] = (sn, "fallback_MA3(n<13)")
    out["combo_ew"] = (np.mean(np.vstack([ma3, naive, sn]), axis=0), "ok")
    try:
        from statsforecast import models as sfm
        m = sfm.AutoETS(season_length=12 if n >= 24 else 1)
        m.fit(y.astype(np.float32))
        f = np.asarray(m.predict(h=h)["mean"], dtype=float)
        out["AutoETS"] = (f, "ok")
    except Exception as exc:
        out["AutoETS"] = (ma3.copy(), f"fallback_MA3({type(exc).__name__})")
    return out


def main() -> None:
    last_i = LAST_I
    db_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    decision = list(csv.DictReader(open(DECISION, encoding="utf-8-sig")))

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), warehouse, SUM(qty)
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2,3""").fetchall()
        wmap = {r[0]: r[1] for r in con.execute(
            "SELECT gs_warehouse, current_warehouse FROM warehouse_map").fetchall()}
    finally:
        con.close()
    if hashlib.sha256(DB_PATH.read_bytes()).hexdigest() != db_hash:
        raise SystemExit("DB changed during the run")

    sku_month = defaultdict(dict)
    wh_month = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for sku, ym, wh_raw, q in rows:
        wh = wmap.get(wh_raw, wh_raw)
        sku_month[sku][ym] = sku_month[sku].get(ym, 0.0) + float(q)
        wh_month[sku][wh][ym] = wh_month[sku][wh].get(ym, 0.0) + float(q)

    last_i = ym_i(WINDOW_LAST)
    series = {}
    for sku, by in sku_month.items():
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        series[sku] = dict(first=first,
                           y=np.array([by.get(m, 0.0) for m in months], dtype=float))

    # same stress lift as T5: own residual quantile (>=10 windows) else pooled
    pooled_rel, sku_rel = [], {}
    for sku, s in series.items():
        y, first = s["y"], s["first"]
        rel_r = []
        for o in range(first + 3, last_i):
            dec = date((o + 1) // 12, (o + 1) % 12 + 1, 22)
            end = dec + timedelta(days=90)
            end_i = end.year * 12 + end.month - 1
            if end_i > last_i or date((end_i + 1) // 12, (end_i + 1) % 12 + 1, 1) > DECISION_DATE:
                continue
            tr = o - first + 1
            m3 = float(np.mean(y[max(0, tr - 3):tr]))
            ww = window_weights(dec, 90)
            F = m3 * sum(ww.values())
            A = sum(wt * y[k - first] for k, wt in ww.items())
            if abs(F) < 1e-9:
                continue
            rel_r.append((A - F) / F)
        sku_rel[sku] = rel_r
        pooled_rel.extend(rel_r)
    pooled_q = conf_q(pooled_rel) if len(pooled_rel) >= 3 else 0.0

    fc = {}
    for sku in {r["SKU"] for r in decision}:
        s = series.get(sku)
        fc[sku] = (ym_series(s["y"], len(s["y"])) if s is not None else None)

    total_sales_all = sum(float(series[s]["y"].sum())
                          for s in {r["SKU"] for r in decision} if s in series) or 1.0
    out = []
    for r in decision:
        sku, wh, status = r["SKU"], r["仓"], r["状态"]
        base = dict(SKU=sku, 仓=wh, 状态=status, MOQ=r["MOQ"], 包装倍数=r["包装倍数"],
                    可用=r["可用"], 在途=r["在途"], PO未结=r["PO未结"],
                    PO去重状态=r["PO去重状态"], 在途去重状态=r["在途去重状态"],
                    在产=r["在产"])
        s = series.get(sku)
        base["销量_全历史"] = round(float(s["y"].sum()), 2) if s is not None else None
        base["销量_近6月"] = (round(float(np.sum(s["y"][max(0, len(s["y"]) - 6):])), 2)
                              if s is not None else None)
        mine3 = sum(wh_month[sku].get(wh, {}).get(m, 0.0)
                    for m in ("2026-07", "2026-08", "2026-09"))
        tot3 = sum(wh_month[sku][w].get(m, 0.0) for w in wh_month[sku]
                   for m in ("2026-07", "2026-08", "2026-09"))
        base["该仓销量_近3月"] = round(mine3, 2)
        base["仓销量占比"] = round(mine3 / tot3, 4) if tot3 > 1e-9 else 0.0
        # every optional column exists on every row (null, never omitted)
        base["情景批"] = None
        for c in CALIBERS:
            base[f"建议下限_{c}"] = None
            base[f"建议上限_{c}"] = None
            base[f"标记_{c}"] = "na"
        base.update(方向一致性=None, 区间重叠=None, 数量差_绝对=None,
                    数量差_相对=None, 建议中位下限=None, 方向=None)
        if status == "C":
            cat, note = CAT_C, "范围外（UOM/未映射），不计算建议量"
        elif r["可用"] in ("", None):
            cat, note = CAT_UNKNOWN, "同仓库存未知 → 不计算建议量（未知不是 0）"
        elif fc.get(sku) is None:
            cat, note = CAT_NOHIST, "订单库无该 SKU 月度历史"
        else:
            cat, note = "", ""
        if not cat:
            avail = float(r["可用"])
            po_s = 0.0 if r["PO未结"] in ("", None) else float(r["PO未结"])
            intr_s = 0.0 if r["在途"] in ("", None) else float(r["在途"])
            if "duplicate" in (r["PO去重状态"] or ""):
                batch = po_s / 2 + intr_s
            elif (r["在途去重状态"] or "").startswith("suspected"):
                batch = max(po_s, intr_s)
            else:
                batch = po_s + intr_s
            base["情景批"] = round(batch, 2)
            rel_q = conf_q(sku_rel.get(sku, [])) if len(sku_rel.get(sku, [])) >= 10 else pooled_q
            rel_lift = min(3.0, max(0.0, rel_q))
            share = base["仓销量占比"]
            fset = fc[sku]
            for c in CALIBERS:
                f, mk = fset[c]
                base[f"标记_{c}"] = mk
                dem = {}
                for d in LEADS:
                    total = 0.0
                    for idx, wt in W[d].items():
                        k = idx - (last_i + 1)
                        if 0 <= k < len(f):
                            total += wt * float(f[k])
                    dem[d] = total * share
                lo = max(0.0, round(dem[90] - (avail + batch), 2))
                hi = max(0.0, round(dem[90] * (1.0 + rel_lift) - avail, 2))
                if hi < lo:
                    lo, hi = hi, lo
                base[f"建议下限_{c}"] = lo
                base[f"建议上限_{c}"] = hi

            lo_list = [base[f"建议下限_{c}"] for c in CALIBERS]
            hi_list = [base[f"建议上限_{c}"] for c in CALIBERS]
            zeros = sum(1 for v in lo_list if v <= 1e-9)
            positives = len(lo_list) - zeros
            if zeros == len(lo_list):
                direction = "全零"
            elif positives == len(lo_list):
                direction = "全正量"
            else:
                direction = "0/正量分歧"
            overlap = max(lo_list) <= min(hi_list) + 1e-9
            diff_abs = round(max(lo_list) - min(lo_list), 2)
            med = float(np.median(lo_list))
            diff_rel = (round(diff_abs / med, 4) if med > 1e-9
                        else (0.0 if diff_abs <= 1e-9 else None))
            identical = diff_abs <= 0.005
            if direction == "0/正量分歧":
                cat = CAT_DIV
            elif not overlap:
                cat = CAT_GAP
            elif identical:
                cat = CAT_SAME
            else:
                cat = CAT_OTHER
            base.update(方向一致性=direction, 区间重叠=bool(overlap),
                        数量差_绝对=diff_abs, 数量差_相对=diff_rel,
                        建议中位下限=round(med, 2), 方向=direction)
            note = ("五口径只改需求口径；库存/PO/在途去重、L60/L90/L120、"
                    "分配与压力系数与 T5 相同")
        base["分类"] = cat
        base["说明"] = note
        out.append(base)

    # ---------------- summary / lists --------------------------------------
    fields = (["SKU", "仓", "状态", "分类", "方向一致性", "区间重叠",
               "数量差_绝对", "数量差_相对", "建议中位下限", "销量_全历史",
               "销量_近6月", "该仓销量_近3月", "仓销量占比", "可用", "在途",
               "PO未结", "情景批", "MOQ", "包装倍数", "PO去重状态", "在途去重状态"]
              + [f"{p}_{c}" for c in CALIBERS for p in ("建议下限", "建议上限")]
              + [f"标记_{c}" for c in CALIBERS] + ["说明"])
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    def sales_of(rows):
        """Distinct-SKU full-history sales (a SKU may appear in several rows)."""
        return sum(float(series[s]["y"].sum()) for s in {r["SKU"] for r in rows}
                   if s in series)

    by_cat = defaultdict(list)
    for r in out:
        by_cat[r["分类"]].append(r)
    cat_stats = {k: dict(rows=len(v), skus=len({r["SKU"] for r in v}),
                         sales=round(sales_of(v), 1),
                         sales_share=round(sales_of(v) / total_sales_all, 4))
                 for k, v in by_cat.items()}
    mark_counts = {c: dict(Counter(r[f"标记_{c}"] for r in out)) for c in CALIBERS}

    list1 = sorted(by_cat[CAT_DIV],
                   key=lambda r: (-float(r["建议中位下限"] or 0), -float(r["销量_全历史"] or 0)))
    list2 = sorted(by_cat[CAT_GAP], key=lambda r: (-float(r["数量差_绝对"] or 0),
                                                  -float(r["销量_全历史"] or 0)))
    list3 = sorted(by_cat[CAT_SAME], key=lambda r: (-float(r["销量_全历史"] or 0), r["SKU"]))

    def fmt_list(rows, n=20):
        L = ["| SKU | 仓 | " + " | ".join(CALIBERS) + " | 区间重叠 | 数量差(绝对/相对) | 销量_全历史 |",
             "|---|---|" + "---:|" * len(CALIBERS) + "---|---:|---:|"]
        for r in rows[:n]:
            cells = " | ".join(
                (f"{r[f'建议下限_{c}']:.2f}" if r[f"建议下限_{c}"] is not None else "—")
                for c in CALIBERS)
            rel = "—" if r["数量差_相对"] is None else f"{r['数量差_相对']:.2f}"
            L.append(f"| `{r['SKU']}` | {r['仓']} | {cells} | "
                     f"{'是' if r['区间重叠'] else '否'} | "
                     f"{r['数量差_绝对']:.2f} / {rel} | {r['销量_全历史']:.1f} |")
        return L

    md = ["# T17 全范围模型敏感性表", "",
          "> **口径说明**：同一套已核实库存与供给假设下，只替换需求预测口径；"
          "本表**不是统计证明**、**不是采购批准**，五口径一致也**不等于正确**。",
          "> 库存/PO/在途/在产去重、L60/L90/L120 情景、共享池默认不跨仓、"
          "分配规则与压力系数均沿用 T3/T5；MOQ/包装未提供，单列不参与计算。", "",
          "## 0. 口径与假设", "",
          "| 项 | 内容 |", "|---|---|",
          "| 需求口径 | MA3 / naive / seasonal_naive / 固定等权组合 / AutoETS |",
          "| AutoETS 不可用 | 按 T16 结论回退 MA3，并在 `标记_AutoETS` 写明原因 |",
          "| seasonal_naive | 历史 <13 月时回退 MA3，`标记_seasonal_naive` 标注 |",
          "| 组合 | MA3/naive/seasonal_naive 固定等权 |",
          "| 库存/供给 | `decision_v2.csv` 的可用/PO/在途/去重状态；`在产` 不在快照 |",
          "| 建议下限 | `max(0, 需求P50_L90 − (可用 + 去重批))` |",
          "| 建议上限 | `max(0, 压力_L90 − 可用)`；压力 = 需求 × (1 + MA3 残差系数，截顶 3×) |",
          "| 方向 | 以建议下限判定：0 / 正量 |",
          "| 区间重叠 | 五口径 [下限, 上限] 存在共同交集 |",
          "| 数量差 | `max(下限) − min(下限)`；相对差 = 绝对差 / 五口径下限中位数 |",
          "| 判据 | 方向、区间、数量差**分别列示**，不合成评分，不设无依据阈值 |", "",
          "## 1. 覆盖", "",
          f"- 输出 **{len(out)} 行 / {len({r['SKU'] for r in out})} SKU**"
          f"（主表 2,309 行 / 1,328 SKU 全覆盖）。",
          f"- 状态：{dict(Counter(r['状态'] for r in out))}。",
          f"- 分类计数：" + "；".join(
              f"{k} {v['rows']} 行 / {v['skus']} SKU" for k, v in
              sorted(cat_stats.items())) + "。", "",
          "> 销量占比按**去重 SKU** 计算；同一 SKU 可跨分类，故各分类占比不可相加。", "",
          "| 分类 | 行数 | SKU | 全历史销量 | 销量占比(按 SKU，可重叠) |",
          "|---|---:|---:|---:|---:|"]
    for k in (CAT_DIV, CAT_GAP, CAT_SAME, CAT_OTHER, CAT_UNKNOWN, CAT_C, CAT_NOHIST):
        if k in cat_stats:
            v = cat_stats[k]
            md.append(f"| {k} | {v['rows']} | {v['skus']} | {v['sales']:.1f} | "
                      f"{v['sales_share']:.2%} |")
    md += ["", "标记计数（各口径）：", "",
           "| 口径 | 标记分布 |", "|---|---|"]
    for c in CALIBERS:
        md.append(f"| {c} | {mark_counts[c]} |")
    md += ["", f"## 2. 清单① 0/正量分歧（最高优先人工核查，{len(list1)} 行 / "
           f"{len({r['SKU'] for r in list1})} SKU）", "",
           "> 同一 (SKU, 仓) 下，至少一个口径给 0、另一个给正量。",
           "> 列为各口径**建议下限**；上限见 CSV。", ""]
    md += fmt_list(list1)
    md += ["", f"## 3. 清单② 同向但区间不重叠（复核，{len(list2)} 行 / "
           f"{len({r['SKU'] for r in list2})} SKU）", "",
           "> 五口径方向相同，但 [下限, 上限] 没有共同交集；判据是结构性的，"
           "不使用数量阈值。", ""]
    md += fmt_list(list2)
    md += ["", f"## 4. 清单③ 五口径一致（{len(list3)} 行 / "
           f"{len({r['SKU'] for r in list3})} SKU）", "",
           "> 五口径建议下限在 0.01 内相同。**全零 1536 行 = 在这组假设下无需动作**；"
           f"全正量 {sum(1 for r in list3 if r['方向一致性'] == '全正量')} 行——"
           "只有全正量行才适合作为优先核查依据；一致不等于正确，也不等于可采购。", ""]
    md += fmt_list(list3)
    md += ["", f"## 5. 残留类别④（同向、区间重叠但数量有差，{len(by_cat[CAT_OTHER])} 行）", "",
           "> 未进入三张清单，但数量差在 CSV 中逐行列示，可按 `数量差_绝对` 排序复核。", "",
           "## 6. 复算示例", ""]
    ex = next((r for r in (list1 + list2 + list3)
               if all(r[f"建议下限_{c}"] is not None for c in CALIBERS)
               and float(r["建议中位下限"] or 0) > 0), None)
    if ex:
        md += [f"- 行：`{ex['SKU']}` / `{ex['仓']}`（{ex['分类']}）",
               f"- 可用 {ex['可用']}，去重批 {ex.get('情景批')}，仓销量占比 {ex['仓销量占比']}",
               "- 五口径建议下限：" + "，".join(
                   f"{c} {ex[f'建议下限_{c}']:.2f}" for c in CALIBERS),
               f"- 数量差 {ex['数量差_绝对']:.2f}（相对 {ex['数量差_相对']}），"
               f"区间重叠 {'是' if ex['区间重叠'] else '否'}。", ""]
    md += ["## 7. 局限与措辞红线", "",
           "- 本表只做**敏感性**：五口径共享同一库存、同一供给假设、同一分配与压力系数；"
           "它回答“换需求口径会怎样”，不回答“哪个口径对”。",
           "- 不构成统计证明；不构成采购批准或下单依据；不改变主表默认（仍为 AutoETS）。",
           "- 五口径一致只说明在这组假设下结果不敏感，**不等于正确**，也不等于可采购。",
           "- MOQ/包装/成本仍缺失，未参与计算；共享池默认不跨仓调拨；在产不在快照。",
           "- 零需求单元格按 0 参与；未知库存写 null，不写 0。", "",
           "## 8. 复现", "",
           "```bash",
           "uv run python docs/research/supply-chain/2026-10-20/claude/"
           "experiments/business_phase/build_model_sensitivity.py",
           "uv run python scripts/check_secrets.py",
           "```", "",
           "DB 只读（前后 sha256 一致）；固定切点、固定参数，脚本确定性。", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("wrote", OUT_CSV.name, "and", OUT_MD.name)
    print("rows", len(out), "skus", len({r["SKU"] for r in out}),
          "categories", {k: len(v) for k, v in by_cat.items()})
    print("lists", len(list1), len(list2), len(list3))
    print("markers", mark_counts)


if __name__ == "__main__":
    main()
