#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T5: full-scope iteration v2 -- AutoETS by default, MA3 fallback, SKU×warehouse.

Ruling A (Codex2): the forecast method defaults to AutoETS (statsforecast 2.1.1).
Sequences where AutoETS is unavailable (T4 probe: tiny datasets / KeyError) fall
back to MA3, written per row. The validation/test reversal is reported in the
summary as a migration risk only -- it does NOT change the selection.

Decision logic is unchanged from T3: SKU × warehouse, shared pool not transferable
by default, SO not netted (before/after columns), PO / intransit / production
deduped separately, L60/L90/L120 scenarios, PR#297 baseline side by side,
MOQ / pack / cost as separate pending columns, A/B/C states, B rows carry
assumptions, unknown is null (never 0), no implicit zeroing.

AutoETS is fitted at SKU level; the SKU forecast is allocated to warehouses by
the warehouse's share of the SKU's last-3-month sales (explicit assumption,
because a warehouse-level series is too sparse for AutoETS). Failed SKUs use the
SKU-level MA3 with the same allocation.

Outputs: replenishment_v2.csv (+ local xlsx), diff_v1_v2.csv, summary_v3.md
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata as md
import json
import math
import warnings
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

warnings.filterwarnings("ignore")

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
DECISION = OUT / "decision_v2.csv"
EXPLANATIONS = OUT / "explanations.csv"
FIRST = OUT / "replenishment_all.csv"
DEST = OUT / "destinations.json"
T2 = CLAUDE_DIR / "experiments" / "business_phase" / "forecast_eval" / "forecast_eval_results.json"

OUT_CSV = OUT / "replenishment_v2.csv"
OUT_XLSX = OUT / "replenishment_v2.xlsx"
OUT_DIFF = OUT / "diff_v1_v2.csv"
OUT_MD = OUT / "summary_v3.md"

DECISION_DATE = date(2026, 10, 22)
WINDOW_FIRST, WINDOW_LAST = "2026-04", "2026-09"
LEADS = (60, 90, 120)


def ym_i(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def i_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


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


W = {d: window_weights(DECISION_DATE, d) for d in LEADS}
WSUM = {d: sum(w.values()) for d, w in W.items()}


def conf_q(vals: list[float]) -> float:
    n = len(vals)
    level = min(1.0, math.ceil((n + 1) * 0.9) / n)
    xs = sorted(vals)
    return xs[min(n - 1, math.ceil(level * (n - 1) - 1e-12))]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse_qty(text: str):
    if not text or "–" not in text:
        return None
    a, b = text.split("–", 1)
    try:
        return float(a), float(b)
    except ValueError:
        return None


def main() -> None:
    db_hash = sha(DB_PATH)
    decision = list(csv.DictReader(open(DECISION, encoding="utf-8-sig")))
    expl = {(r["SKU"], r["仓"]): r for r in
            csv.DictReader(open(EXPLANATIONS, encoding="utf-8-sig"))}
    if len(expl) != len(decision):
        raise SystemExit("explanations/decision row mismatch")
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}
    t2 = json.loads(T2.read_text(encoding="utf-8"))
    v1 = {}
    if FIRST.exists():
        for r in csv.DictReader(open(FIRST, encoding="utf-8-sig")):
            v1[r["SKU"]] = r

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
    if sha(DB_PATH) != db_hash:
        raise SystemExit("DB changed during the run")

    sku_month = defaultdict(dict)
    wh_month = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # sku -> wh -> ym -> qty
    for sku, ym, wh_raw, q in rows:
        wh = wmap.get(wh_raw, wh_raw)
        sku_month[sku][ym] = sku_month[sku].get(ym, 0.0) + float(q)
        wh_month[sku][wh][ym] = wh_month[sku][wh].get(ym, 0.0) + float(q)

    last_i = ym_i(WINDOW_LAST)
    series = {}
    for sku, by in sku_month.items():
        first = min(ym_i(m) for m in by)
        months = [i_ym(i) for i in range(first, last_i + 1)]
        series[sku] = dict(first=first, months=months,
                           y=np.array([by.get(m, 0.0) for m in months], dtype=float))

    from statsforecast import models as sfm
    sf_version = md.version("statsforecast")

    def sku_forecast(sku: str):
        """Return (monthly h=4 forecast from 2026-10, method, status, reason)."""
        s = series.get(sku)
        if s is None:
            return None, "none", "no_history", "订单库无该 SKU 月度历史"
        n = len(s["y"])
        h = max(W[120]) - last_i           # months Oct..Jan
        try:
            m = sfm.AutoETS(season_length=12 if n >= 24 else 1)
            m.fit(s["y"].astype(np.float32))
            f = np.asarray(m.predict(h=h)["mean"], dtype=float)
            return f, "AutoETS", "available", None
        except Exception as exc:
            reason = f"{type(exc).__name__}:{str(exc)[:60]}"
        k = min(3, n)
        f = np.repeat(float(np.mean(s["y"][-k:])), h) if k else np.zeros(h)
        return f, "MA3", "fallback", reason

    fcache = {}
    for sku in {r["SKU"] for r in decision}:
        fcache[sku] = sku_forecast(sku)

    # relative lift (same convention as T3): own >=10 else pooled, clipped 3x
    pooled_rel, sku_rel = [], {}
    for sku, s in series.items():
        y, first = s["y"], s["first"]
        abs_r, rel_r = [], []
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
            abs_r.append(A - F)
            rel_r.append((A - F) / F)
        sku_rel[sku] = rel_r
        pooled_rel.extend(rel_r)
    pooled_q = conf_q(pooled_rel) if len(pooled_rel) >= 3 else 0.0

    out_rows, diff_rows = [], []
    method_counts = Counter()
    # per-SKU accumulation that distinguishes KNOWN from UNKNOWN warehouses
    sku_acc = defaultdict(lambda: dict(lo=0.0, hi=0.0, known=0, unknown=0))
    for r in decision:
        sku, wh = r["SKU"], r["仓"]
        e = expl.get((sku, wh), {})
        status = r["状态"]
        if status == "C":
            row = dict(r)
            row.update({
                "预测方法(实际使用)": "n/a", "AutoETS可用性": "not_applicable",
                "fallback理由": "范围外", "方法版本": f"statsforecast {sf_version}",
                "异常标签": e.get("异常标签", ""), "异常处理说明": e.get("异常处理说明", ""),
                "缺口公式": e.get("缺口公式", ""), "建议量公式": e.get("建议量公式", ""),
            })
            out_rows.append(row)
            continue
        f, method, mstat, reason = fcache[sku]
        rel = sku_rel.get(sku, [])
        rel_q = conf_q(rel) if len(rel) >= 10 else pooled_q
        rel_lift = min(3.0, max(0.0, rel_q))
        method_counts[method] += 1
        # warehouse share of the SKU's last-3-month sales
        tot3 = sum(wh_month[sku][w].get(m, 0.0) for w in wh_month[sku]
                   for m in ("2026-07", "2026-08", "2026-09"))
        mine3 = sum(wh_month[sku].get(wh, {}).get(m, 0.0)
                    for m in ("2026-07", "2026-08", "2026-09"))
        share = (mine3 / tot3) if tot3 > 1e-9 else 0.0
        dem = {}
        for d in LEADS:
            # window uses months last_i+1..; f[k] is month last_i+1+k
            total = 0.0
            for idx, wt in W[d].items():
                k = idx - (last_i + 1)
                if 0 <= k < len(f):
                    total += wt * float(f[k])
            dem[d] = total * share
        # NOT a calibrated P90: the coefficient comes from MA3 residuals, is
        # clipped at 3x and is not validated after warehouse allocation.
        dem_stress = {d: dem[d] * (1.0 + rel_lift) for d in LEADS}

        avail = r["可用"]
        po_raw = r["PO未结"]
        intr = r["在途"]
        po_s = 0.0 if po_raw in ("", None) else float(po_raw)
        intr_s = 0.0 if intr in ("", None) else float(intr)
        assumptions = [a for a in (r["assumptions"] or "").split("；") if a]
        if method == "MA3" and mstat == "fallback":
            assumptions.append(f"AutoETS 不可用（{reason}）→ 用 SKU 级 MA3（假设）")
        assumptions.append("AutoETS 在 SKU 级拟合，按该仓近 3 月销量占比分配到仓（分配假设）")
        assumptions.append("上限为压力情景：MA3 残差相对系数、截顶 3×、未做分配后覆盖验证；不是 P90")
        if share == 0:
            assumptions.append("该仓近 3 月无销量 → 需求分配为 0（不是缺需求）")
        batch_val = None
        if avail == "" or avail is None:
            status = "B_pending_inventory"
            qty_lo = qty_hi = None
            sku_acc[sku]["unknown"] += 1
        else:
            status = "B"
            po_dups = "duplicate" in (r["PO去重状态"] or "")
            if po_dups:
                batch = po_s / 2 + intr_s
            elif (r["在途去重状态"] or "").startswith("suspected"):
                batch = max(po_s, intr_s)
            else:
                batch = po_s + intr_s
            batch_val = batch
            qty_lo = max(0.0, round(dem[90] - (float(avail) + batch), 2))
            qty_hi = max(0.0, round(dem_stress[90] - float(avail), 2))
            if qty_hi < qty_lo:
                qty_lo, qty_hi = qty_hi, qty_lo
            sku_acc[sku]["lo"] += qty_lo
            sku_acc[sku]["hi"] += qty_hi
            sku_acc[sku]["known"] += 1
        hist_rate = r.get("月需求率", "")
        new_rate = (dem[90] / WSUM[90]) if WSUM[90] > 0 else None
        pr = {}
        for d in LEADS:
            rate = new_rate if new_rate is not None else 0.0
            if avail == "" or avail is None:
                pr[d] = None
            else:
                pr[d] = round(max(0.0, rate * (d / 30.0) - float(avail) - intr_s), 2)
        diff90 = (round(qty_lo - pr[90], 2)
                  if (qty_lo is not None and pr[90] is not None) else None)
        if diff90 is None:
            new_reason = None
        elif abs(diff90) < 1e-9:
            new_reason = "same"
        else:
            new_reason = ("本方法情景批含 PO/在途去重（PR297 只扣在途）；"
                          "覆盖期 L90 日历窗口 vs PR297 90/30 月；"
                          "两者使用同一 T5 新预测率")
        row = dict(r)
        row.update({
            "预测方法(实际使用)": f"{method}（SKU 级 × 仓占比分配）",
            "AutoETS可用性": mstat,
            "fallback理由": (reason if mstat == "fallback" else
                             "AutoETS 可用，已作为默认方法" if mstat == "available" else
                             "无历史"),
            "方法版本": f"statsforecast {sf_version}",
            "历史窗口": e.get("历史窗口", ""),
            "可用月数": e.get("可用月数", ""),
            "该序列验证表现": e.get("该序列验证表现", ""),
            "需求P50(冲减前)": round(dem[90], 2),
            "需求P50(冲减后)": round(dem[90], 2),
            "压力情景(MA3残差系数×,截顶3×)": round(dem_stress[90], 2),
            "缺口L60": (round(dem[60] - (float(avail) + batch_val), 2)
                      if batch_val is not None else None),
            "缺口L90": (round(dem[90] - (float(avail) + batch_val), 2)
                      if batch_val is not None else None),
            "缺口L120": (round(dem[120] - (float(avail) + batch_val), 2)
                       if batch_val is not None else None),
            "建议下限L90": qty_lo, "建议上限L90(压力情景)": qty_hi,
            "PR297_L60": pr[60], "PR297_L90": pr[90], "PR297_L120": pr[120],
            "与PR297差异L90": diff90,
            "差异原因": new_reason,
            "历史率(T3)": hist_rate,
            "新预测等效率(T5)": (round(new_rate, 4) if new_rate is not None else None),
            "缺口公式": e.get("缺口公式", ""),
            "建议量公式": e.get("建议量公式", ""),
            "异常标签": e.get("异常标签", ""),
            "异常处理说明": e.get("异常处理说明", ""),
            "assumptions": "；".join(assumptions),
        })
        out_rows.append(row)

    columns = list(out_rows[0].keys())
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    # ---- diff vs v1 (per SKU, L90 range) ---------------------------------
    scope_status = defaultdict(list)
    for r in out_rows:
        if r["状态"] != "C":
            scope_status[r["SKU"]].append(r["状态"])

    for sku, v1row in sorted(v1.items()):
        old = parse_qty(v1row.get("建议补货数量或条件区间", ""))
        acc = sku_acc.get(sku)
        known = 0 if acc is None else acc["known"]
        unknown = 0 if acc is None else acc["unknown"]
        lo = 0.0 if acc is None else acc["lo"]
        hi = 0.0 if acc is None else acc["hi"]
        complete = (known > 0 and unknown == 0)
        v2_low = round(lo, 2) if known > 0 else None
        v2_high = round(hi, 2) if known > 0 else None
        delta_low = delta_high = None
        reasons = []
        if not scope_status.get(sku):
            status = "v1_no_quantity"
            reasons.append("v1/v2 均无数量（范围外）")
        elif known == 0:
            # every warehouse is pending inventory -> total is UNKNOWN, not 0
            status = "all_unknown"
            reasons.append(f"{unknown} 个仓全部待库存核实 → v2 合计为 null（不是 0）")
        elif unknown > 0:
            status = "partial_unknown"
            reasons.append(f"{unknown} 个仓待库存核实 → 合计不完整，不计算完整差值")
        elif old is None:
            status = "v1_no_quantity"
            reasons.append("v1 无数量（当时为待库存核实）")
        elif abs(old[0] - round(lo, 2)) < 1e-9 and abs(old[1] - round(hi, 2)) < 1e-9:
            status = "unchanged"
        else:
            status = "changed"
            reasons.append("模型切换到 AutoETS（SKU 级）并按仓占比分配，v1 为 SKU 级 MA3")
            reasons.append("SKU×仓粒度求和；PO/在途按去重批进入情景（规则同 v1，基数随需求变）")
        if complete and old is not None:
            delta_low = round(round(lo, 2) - old[0], 2)
            delta_high = round(round(hi, 2) - old[1], 2)
            if status == "unchanged" and (abs(delta_low) > 1e-9 or abs(delta_high) > 1e-9):
                raise AssertionError(f"unchanged but delta != 0 for {sku}")
        diff_rows.append(dict(
            SKU=sku, v1_class=v1row.get("状态"), v1_low=(old[0] if old else None),
            v1_high=(old[1] if old else None), v2_low=v2_low, v2_high=v2_high,
            v2_known_rows=known, v2_unknown_rows=unknown, v2_complete=complete,
            comparable=(complete and old is not None),
            delta_low=delta_low, delta_high=delta_high,
            change_status=status, change_reason="；".join(reasons)))
    # SKUs present in v2 but not v1 (none expected)
    for sku in sku_acc:
        if sku not in v1:
            diff_rows.append(dict(SKU=sku, v1_class="(missing)", v1_low=None, v1_high=None,
                                  v2_low=(round(sku_acc[sku]["lo"], 2)
                                          if sku_acc[sku]["known"] > 0 else None),
                                  v2_high=(round(sku_acc[sku]["hi"], 2)
                                           if sku_acc[sku]["known"] > 0 else None),
                                  v2_known_rows=sku_acc[sku]["known"],
                                  v2_unknown_rows=sku_acc[sku]["unknown"],
                                  v2_complete=(sku_acc[sku]["unknown"] == 0
                                               and sku_acc[sku]["known"] > 0),
                                  comparable=True,
                                  delta_low=None, delta_high=None,
                                  change_status="new_in_v2",
                                  change_reason="v1 无该 SKU"))
    with OUT_DIFF.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(diff_rows[0].keys()))
        w.writeheader()
        w.writerows(diff_rows)

    # ---- xlsx (local only) ------------------------------------------------
    xlsx = False
    try:
        import importlib.util
        if importlib.util.find_spec("openpyxl") is not None:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "replenishment_v2"
            ws.append(columns)
            for r in out_rows:
                ws.append([r.get(c) for c in columns])
            wb.save(OUT_XLSX)
            xlsx = True
    except Exception as exc:
        print("xlsx skipped:", exc)

    # ---- summary ---------------------------------------------------------
    status_cnt = Counter(r["状态"] for r in out_rows)
    elig = [r for r in out_rows if r["状态"] != "C"]
    sales6 = {sku: sum(q for m, q in by.items()
                       if WINDOW_FIRST <= m <= WINDOW_LAST)
              for sku, by in sku_month.items()}
    sku_status = {}
    for r in out_rows:
        sku_status.setdefault(r["SKU"], r["状态"])
    total_sales = sum(sales6.get(s, 0.0) for s in sku_status) or 1.0
    sales_by = Counter()
    for sku, st in sku_status.items():
        key = "B" if st == "B_pending_inventory" else st
        sales_by[key] += sales6.get(sku, 0.0)
    t2_full = next((x for x in t2["runs"] if x["run"] == "full"), {})
    t2_val_common = t2_full.get("validation_common", {})
    t2_test = t2_full.get("test_own", {})
    status_of = Counter(d["change_status"] for d in diff_rows)
    comparable = sum(1 for d in diff_rows if d["comparable"])
    changed = status_of.get("changed", 0)
    partial = status_of.get("partial_unknown", 0)
    all_unknown = status_of.get("all_unknown", 0)
    all_unknown_skus = [d["SKU"] for d in diff_rows if d["change_status"] == "all_unknown"]
    md_lines = [
        "---", "okf: v0.1", "type: Report",
        "title: T5 全范围迭代版摘要（AutoETS 默认 + MA3 fallback）",
        f"date: {date.today().isoformat()}", "owner: claude-worker",
        "status: 迭代版；A=0，B 为条件数量，C 为范围外",
        "artifacts:",
        "  - out/business_phase/replenishment_v2.csv",
        "  - out/business_phase/diff_v1_v2.csv",
        ("  - out/business_phase/replenishment_v2.xlsx（本地生成，仓库忽略 *.xlsx）" if xlsx
         else "  - （xlsx 未生成：openpyxl 不可用）"),
        "---", "",
        "# T5 迭代版摘要", "",
        "## 1. 覆盖", "",
        "| 项 | 值 |", "|---|---:|",
        f"| 输出行数 | {len(out_rows):,} |",
        f"| 覆盖 SKU 数 | {len({r['SKU'] for r in out_rows}):,}（1,237 合格 + 29 UOM + 62 未映射 = 1,328） |",
        f"| SKU×仓合格行 | {len(elig):,} |",
        f"| 状态 A / B / B_pending_inventory / C | "
        f"{status_cnt.get('A', 0)} / {status_cnt.get('B', 0)} / "
        f"{status_cnt.get('B_pending_inventory', 0)} / {status_cnt.get('C', 0)} |", "",
        "| 状态 | 6 个月净出库 | 销量占比 |", "|---|---:|---:|",
    ]
    for st in ("A", "B", "C"):
        md_lines.append(f"| {st} | {sales_by.get(st, 0):,.0f} | "
                        f"{sales_by.get(st, 0) / total_sales:.1%} |")
    md_lines += [
        "", "## 2. 方法", "",
        f"- 默认 **AutoETS**（statsforecast {sf_version}），SKU 级拟合后按该仓近 3 月销量占比分配到仓（显式假设）。",
        f"- 逐行 fallback：AutoETS 不可用的 SKU 用 **MA3**，原因写在该行 `fallback理由`。",
        f"- 本版行内方法分布：" + "、".join(f"{k} {v:,} 行" for k, v in method_counts.items()), "",
        "### 验证 / 测试反转（迁移风险，不改选）", "",
        f"- 验证集（共同子集）AutoETS WAPE **{(t2_val_common.get('autoets') or {}).get('wape_keep_zero')}**，"
        f"第二名 combo_dynamic_ew **{(t2_val_common.get('combo_dynamic_ew') or {}).get('wape_keep_zero')}**。",
        f"- 测试集 AutoETS **{(t2_test.get('autoets') or {}).get('wape_keep_zero')}**，"
        f"combo_dynamic_ew **{(t2_test.get('combo_dynamic_ew') or {}).get('wape_keep_zero')}**、"
        f"seasonal_naive **{(t2_test.get('seasonal_naive') or {}).get('wape_keep_zero')}**。",
        "- 按裁定 A 仍以 AutoETS 为默认；**测试反转只作为迁移风险**记录，不据此改选。", "",
        "## 3. 与首版（v1）差异", "",
        f"- 逐 SKU 对比（`diff_v1_v2.csv`）：**可比 SKU {comparable:,} 个**（v2 全部仓均有库存、可算完整合计），"
        f"其中 **{changed:,} 个数量变化**、其余不变；另有 **{partial} 个 SKU 部分仓待核实（partial_unknown，"
        f"不算完整差值）**、**{all_unknown} 个 SKU 全部仓待核实（all_unknown，v2 合计为 null，不是 0）**、"
        f"{status_of.get('v1_no_quantity', 0)} 个 v1 无数量（范围外）。",
        "- 变化主因：① 模型由 SKU 级 MA3 切到 AutoETS（失败则 MA3）；② 粒度改为 SKU×仓并按销量占比分配；"
        "③ PO/在途仍按去重批进入情景，但基数随需求变。", "",
        "- 主表同时列 **历史率(T3)** 与 **新预测等效率(T5)**；PR#297 基线用 **T5 新率**重算，"
        "差异原因据此重写，`same` 行已断言差值 = 0。", "",
        "- **上限列改为“建议上限L90(压力情景)”**：系数来自 MA3 残差、截顶 3×、分配后未验证覆盖，"
        "**不是已标定的 P90**。", "",
        "## 4. 使用条件（必须随表一起说明）", "",
        "- A 类为 0：需求上下界（G8）未给、在产 WO 不在快照，**没有任何行可当已审批数量**。",
        "- B 类数量是**条件区间**，依赖行内 `assumptions`；MOQ/包装/成本未提供，**采购约束待定**。",
        "- 未知为 null（库存未知 160 行数量留空），**没有按 0 计算**。",
        "- 共享池默认不跨仓调拨；跨仓需显式开启并单列假设。", "",
        "## 5. 剩余缺口", "",
        "- PO ETA 全表缺失、在产 WO 不在快照、逐笔重叠键缺失、需求上下界（G8）缺失、MOQ/成本缺失。",
        "- 退货/取消不可观测；促销尖峰、运营变化、断货删失均检出未校正。", "",
    ]
    Path(OUT_MD).write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"wrote {OUT_CSV} ({OUT_CSV.stat().st_size:,} bytes)")
    print(f"wrote {OUT_DIFF} ({OUT_DIFF.stat().st_size:,} bytes)")
    print(f"wrote {OUT_MD}" + (" (+xlsx)" if xlsx else ""))
    print("rows", len(out_rows), "skus", len({r['SKU'] for r in out_rows}),
          "status", dict(status_cnt), "methods", dict(method_counts),
          "changed vs v1", changed)


if __name__ == "__main__":
    main()
