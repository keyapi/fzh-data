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

Five-class partition (sums to 2,309)
  ① zero/positive divergence (highest priority for manual review);
  ③a all five calibers > 0 (priority manual review; inside it, ② = the five
     intervals share no common point, ④ = intervals overlap but quantities
     differ);
  ③b all five calibers = 0 (no replenishment recommended under these
     assumptions — conditional on the inventory/supply basis);
  unknown inventory; out-of-scope (C).
  ③a/③b split direction consistency; they are NOT a quality ranking. Agreement
  between calibers is not correctness and not a purchase approval.

T18 fix (2026-10-22)
  Direction consistency is the five-class partition that sums to 2,309:
  ① divergence 308 | ③a all-positive 214 | ③b all-zero 1,536 | unknown 160 | C 91.
  ③a is the priority review list; its interior is split into ② (no interval
  overlap, 74) and ④ (overlap with quantity difference, 140). ③b means "no
  replenishment recommended under these assumptions", not correctness.

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

# five-class partition (sums to 2,309) + a sub-label inside ③a
CAT_DIV = "①0/正量分歧"
CAT_POS = "③a全正量一致"
CAT_ZERO = "③b全零一致"
CAT_SUB_GAP = "②同向·区间不重叠"
CAT_SUB_OTHER = "④同向·区间重叠·有数量差"
CAT_C = "范围外(C)"
CAT_UNKNOWN = "库存未知"
CAT_NOHIST = "无历史"
MAIN_CATS = (CAT_DIV, CAT_POS, CAT_ZERO, CAT_UNKNOWN, CAT_C, CAT_NOHIST)


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
                    数量差_相对=None, 建议中位下限=None, 方向=None, 子类=None)
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
            sub = ""
            if direction == "0/正量分歧":
                cat = CAT_DIV
            elif direction == "全零":
                cat = CAT_ZERO                 # ③b: all five lower values are 0
            else:                              # 全正量 -> ③a, split ② / ④
                cat = CAT_POS
                sub = CAT_SUB_GAP if not overlap else CAT_SUB_OTHER
            base.update(方向一致性=direction, 区间重叠=bool(overlap),
                        数量差_绝对=diff_abs, 数量差_相对=diff_rel,
                        建议中位下限=round(med, 2), 方向=direction, 子类=sub)
            note = ("五口径只改需求口径；库存/PO/在途去重、L60/L90/L120、"
                    "分配与压力系数与 T5 相同")
        base["分类"] = cat
        base["说明"] = note
        out.append(base)

    # ---------------- T18 assertions: classes are a partition --------------
    n_div = sum(1 for r in out if r["分类"] == CAT_DIV)
    n_pos = sum(1 for r in out if r["分类"] == CAT_POS)
    n_zero = sum(1 for r in out if r["分类"] == CAT_ZERO)
    n_unknown = sum(1 for r in out if r["分类"] == CAT_UNKNOWN)
    n_c = sum(1 for r in out if r["分类"] == CAT_C)
    n_nohist = sum(1 for r in out if r["分类"] == CAT_NOHIST)
    assert len(out) == len(decision) == 2309, (len(out), len(decision))
    assert n_div + n_pos + n_zero + n_unknown + n_c + n_nohist == 2309
    assert n_unknown + n_c + n_nohist == 251, (n_unknown, n_c, n_nohist)
    for r in out:
        if r["分类"] == CAT_ZERO:
            assert all(r[f"建议下限_{c}"] == 0 for c in CALIBERS), r["SKU"]
        elif r["分类"] == CAT_POS:
            assert all(r[f"建议下限_{c}"] > 0 for c in CALIBERS), r["SKU"]
    # counts pinned to the reviewed dataset; a data refresh must update them
    assert (n_div, n_pos, n_zero) == (308, 214, 1536), (n_div, n_pos, n_zero)

    # ---------------- cross-check against the main table (T5) ---------------
    main = {(r["SKU"], r["仓"]): r
            for r in csv.DictReader(open(OUT / "replenishment_v2.csv",
                                         encoding="utf-8-sig"))}
    n_cmp = exact_rows = 0
    max_diff = 0.0
    for r in out:
        if r["状态"] != "B" or (r["SKU"], r["仓"]) not in main:
            continue
        m = main[(r["SKU"], r["仓"])]
        d = max(abs(r["建议下限_AutoETS"] - float(m["建议下限L90"])),
                abs(r["建议上限_AutoETS"] - float(m["建议上限L90(压力情景)"])))
        n_cmp += 1
        max_diff = max(max_diff, d)
        exact_rows += d <= 0.011
    assert n_cmp == 2058 and max_diff <= 0.1, (n_cmp, max_diff)

    # ---------------- summary / lists --------------------------------------
    fields = (["SKU", "仓", "状态", "分类", "子类", "方向一致性", "区间重叠",
               "数量差_绝对", "数量差_相对", "建议中位下限", "销量_全历史",
               "销量_近6月", "该仓销量_近3月", "仓销量占比", "可用", "在途",
               "PO未结", "情景批", "MOQ", "包装倍数", "PO去重状态", "在途去重状态"]
              + [f"{p}_{c}" for c in CALIBERS for p in ("建议下限", "建议上限")]
              + [f"标记_{c}" for c in CALIBERS] + ["说明"])
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    sku6 = {s: float(np.sum(v["y"][max(0, len(v["y"]) - 6):]))
            for s, v in series.items()}
    total_6m = sum(sku6.get(s, 0.0) for s in {r["SKU"] for r in decision}) or 1.0

    def sales6_of(rows):
        """Distinct-SKU last-6-month sales (a SKU may appear in several rows)."""
        return sum(sku6.get(s, 0.0) for s in {r["SKU"] for r in rows})

    by_cat = defaultdict(list)
    for r in out:
        by_cat[r["分类"]].append(r)
    cat_stats = {k: dict(rows=len(v), skus=len({r["SKU"] for r in v}),
                         sales6=round(sales6_of(v), 1),
                         share6=round(sales6_of(v) / total_6m, 4))
                 for k, v in by_cat.items()}
    mark_counts = {c: dict(Counter(r[f"标记_{c}"] for r in out)) for c in CALIBERS}
    pos_rows = by_cat[CAT_POS]
    sub_gap = [r for r in pos_rows if r["子类"] == CAT_SUB_GAP]
    sub_other = [r for r in pos_rows if r["子类"] == CAT_SUB_OTHER]
    assert len(sub_gap) + len(sub_other) == len(pos_rows)

    def by_median(rows):
        return sorted(rows, key=lambda r: (-float(r["建议中位下限"] or 0),
                                           -float(r["销量_全历史"] or 0)))

    list1 = by_median(by_cat[CAT_DIV])
    list_pos = by_median(pos_rows)
    list_zero = sorted(by_cat[CAT_ZERO],
                       key=lambda r: (-float(r["销量_全历史"] or 0), r["SKU"]))
    list_gap = sorted(sub_gap, key=lambda r: (-float(r["数量差_绝对"] or 0),
                                              -float(r["销量_全历史"] or 0)))
    list_other = sorted(sub_other, key=lambda r: (-float(r["数量差_绝对"] or 0),
                                                  -float(r["销量_全历史"] or 0)))

    def fmt_list(rows, n=20):
        L = ["| SKU | 仓 | " + " | ".join(CALIBERS)
             + " | 区间重叠 | 数量差(绝对/相对) | 销量_全历史 |",
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

    def head(k):
        v = cat_stats[k]
        return (f"行数 **{v['rows']}** / SKU **{v['skus']}**；"
                f"近 6 月销量覆盖 **{v['share6']:.2%}**")

    md = ["# T17/T18 全范围模型敏感性表", "",
          "> **口径说明**：同一套已核实库存与供给假设下，只替换需求预测口径；"
          "本表**不是统计证明**、**不是采购批准**，五口径一致也**不等于正确**。",
          "> 分类按**方向一致性**先分成五类（相加 = 2,309）："
          "①0/正量分歧、③a全正量一致、③b全零一致、库存未知、范围外(C)；"
          "③a 内部再按区间重叠拆成 ②/④ 两个复核子集。", "",
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
          "## 1. 覆盖与五类计数（相加 = 2,309）", "",
          f"- 输出 **{len(out)} 行 / {len({r['SKU'] for r in out})} SKU**"
          f"（主表 2,309 行 / 1,328 SKU 全覆盖）。",
          f"- 状态：{dict(Counter(r['状态'] for r in out))}。",
          "- 断言：全零类五口径下限均为 0；全正量类五口径下限均 >0；"
          f"五类相加 = {n_div}+{n_pos}+{n_zero}+{n_unknown}+{n_c} = "
          f"{n_div + n_pos + n_zero + n_unknown + n_c}（无历史 {n_nohist} 行）；"
          f"空值 {n_unknown}+{n_c}+{n_nohist} = {n_unknown + n_c + n_nohist}。", "",
          "> 销量覆盖按**近 6 月**、去重 SKU 计算；同一 SKU 可跨分类，占比不可相加。", "",
          "| 分类 | 行数 | SKU | 近 6 月销量 | 近 6 月销量覆盖 |",
          "|---|---:|---:|---:|---:|"]
    for k in MAIN_CATS:
        if k in cat_stats:
            v = cat_stats[k]
            md.append(f"| {k} | {v['rows']} | {v['skus']} | {v['sales6']:.1f} | "
                      f"{v['share6']:.2%} |")
    md += ["", "标记计数（各口径）：", "",
           "| 口径 | 标记分布 |", "|---|---|"]
    for c in CALIBERS:
        md.append(f"| {c} | {mark_counts[c]} |")
    md += ["", "## 2. 修订说明（T17 正文错误 → T18 更正）", "",
           "> **原文（错误）**：“清单③ 的 1,536 行全部是全零（全正量 0 行）……"
           "没有出现‘五口径一致且都为正量’的行”。",
           "> **更正**：1,536 行是**③b 全零一致**；另有 **214 行 ③a 全正量一致**"
           "（五口径下限都 >0），此前被并入 ②/④ 而未被计入“全正量”。"
           "五类合计 308+214+1536+160+91 = 2,309。", "",
           f"## 3. 清单① 0/正量分歧（最高优先复核）", "",
           f"{head(CAT_DIV)}。同一 (SKU, 仓) 下，至少一个口径给 0、另一个给正量；"
           "列为各口径**建议下限**，上限见 CSV。", ""]
    md += fmt_list(list1)
    md += ["", "## 4. 清单③a 全正量一致（优先人工核查）", "",
           f"{head(CAT_POS)}。五口径都 >0，但数量可能不同；"
           "内部再按区间是否重叠拆成 ②（不重叠，优先复核）与 ④（重叠但有数量差）。",
           "", f"- ② 同向·区间不重叠：**{len(sub_gap)} 行** / "
           f"{len({r['SKU'] for r in sub_gap})} SKU，近 6 月销量覆盖 "
           f"{sales6_of(sub_gap) / total_6m:.2%}",
           f"- ④ 同向·区间重叠·有数量差：**{len(sub_other)} 行** / "
           f"{len({r['SKU'] for r in sub_other})} SKU，近 6 月销量覆盖 "
           f"{sales6_of(sub_other) / total_6m:.2%}", ""]
    md += fmt_list(list_pos)
    md += ["", "## 5. 清单② 同向但区间不重叠（复核）", "",
           f"行数 **{len(list_gap)}** / SKU **{len({r['SKU'] for r in list_gap})}**；"
           f"近 6 月销量覆盖 **{sales6_of(list_gap) / total_6m:.2%}**（③a 子集）。"
           "五口径方向相同，但 [下限, 上限] 没有共同交集；判据是结构性的，不使用数量阈值。", ""]
    md += fmt_list(list_gap)
    md += ["", "## 6. 清单④ 同向·区间重叠·有数量差（复核）", "",
           f"行数 **{len(list_other)}** / SKU **{len({r['SKU'] for r in list_other})}**；"
           f"近 6 月销量覆盖 **{sales6_of(list_other) / total_6m:.2%}**（③a 子集）。"
           "区间有共同交集，但五口径数量不同；按 `数量差_绝对` 降序，"
           "不设“大/小”阈值。", ""]
    md += fmt_list(list_other)
    md += ["", "## 7. 清单③b 全零一致（五口径均不建议补，条件性）", "",
           f"{head(CAT_ZERO)}。五口径下限都为 0，表示**在这组库存/供给假设下**"
           "都不需要补；库存未知、在产不在快照、MOQ/成本缺失等前提若变化，结论需重跑。"
           "**一致 ≠ 正确，≠ 采购批准**。", "",
           "> 该清单行数较多（1,536），正文只列销量最高的 20 行，完整清单见 CSV"
           "（`分类=③b全零一致`）。", ""]
    md += fmt_list(list_zero)
    md += ["", "## 8. 与主表 B 行对拍（保留并复核）", "",
           f"- 可比 B 行 **{n_cmp}** 行：完全一致（差 ≤0.01）**{exact_rows}** 行，"
           f"其余差 ≤ **{max_diff:.2f}**（仅浮点拟合差）。",
           "- 结论：库存/供给/分配/压力系数与 T5 一致，敏感性只改变需求口径。", "",
           "## 9. 复算示例", ""]
    ex = next((r for r in (list1 + list_pos)
               if all(r[f"建议下限_{c}"] is not None for c in CALIBERS)), None)
    if ex:
        md += [f"- 行：`{ex['SKU']}` / `{ex['仓']}`（{ex['分类']}"
               + (f" / {ex['子类']}" if ex["子类"] else "") + "）",
               f"- 可用 {ex['可用']}，去重批 {ex.get('情景批')}，仓销量占比 {ex['仓销量占比']}",
               "- 五口径建议下限：" + "，".join(
                   f"{c} {ex[f'建议下限_{c}']:.2f}" for c in CALIBERS),
               f"- 数量差 {ex['数量差_绝对']:.2f}（相对 {ex['数量差_相对']}），"
               f"区间重叠 {'是' if ex['区间重叠'] else '否'}。", ""]
    md += ["## 10. 局限与措辞红线", "",
           "- 本表只做**敏感性**：五口径共享同一库存、同一供给假设、同一分配与压力系数；"
           "它回答“换需求口径会怎样”，不回答“哪个口径对”。",
           "- 不构成统计证明；不构成采购批准或下单依据；不改变主表默认（仍为 AutoETS）。",
           "- 五口径一致（无论全零还是全正量）只说明在这组假设下结果不敏感，"
           "**不等于正确**，也不等于可采购。",
           "- MOQ/包装/成本仍缺失，未参与计算；共享池默认不跨仓调拨；在产不在快照。",
           "- 零需求单元格按 0 参与；未知库存写 null，不写 0。", "",
           "## 11. 复现", "",
           "```bash",
           "uv run python docs/research/supply-chain/2026-10-20/claude/"
           "experiments/business_phase/build_model_sensitivity.py",
           "uv run python scripts/check_secrets.py",
           "```", "",
           "DB 只读（前后 sha256 一致）；固定切点、固定参数，脚本确定性；"
           "五类计数与全零/全正量断言在脚本内，失败即中止。", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("wrote", OUT_CSV.name, "and", OUT_MD.name)
    print("rows", len(out), "skus", len({r["SKU"] for r in out}),
          "classes", {k: len(v) for k, v in by_cat.items()})
    print("assert classes", n_div, n_pos, n_zero, n_unknown, n_c, n_nohist,
          "sum", n_div + n_pos + n_zero + n_unknown + n_c + n_nohist)
    print("subsets", len(sub_gap), len(sub_other), "pos", len(pos_rows))
    print("cross-check", exact_rows, "/", n_cmp, "max_diff", round(max_diff, 4))
    print("markers", mark_counts)


if __name__ == "__main__":
    main()
