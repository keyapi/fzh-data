#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T4: auditable explanation layer for every decision_v2 row.

For each SKU × warehouse row (2,218 eligible + 91 out-of-scope) this emits one
explanation row with the method actually used, the preferred method and its
per-SKU availability (AutoETS probed here), the history window, the demand and
supply components, the gap / quantity formulas, the assumptions, the anomaly
labels with a per-row reason, and the missing fields.

Anomaly label vocabulary (all eight are always represented in the coverage
table; each row carries only the labels that apply plus the reason):
  short_history / missing_inventory / zero_sales / returns_unobservable /
  duplicate_mapping / promo_spike / operational_change / stockout_censoring

Read-only inputs: decision_v2.csv, decision_v2.json, forecast_eval_results.json,
destinations.json, order_store.duckdb.
Output: explanations.csv
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata as md
import json
from collections import Counter, defaultdict
from pathlib import Path

import warnings

import duckdb
import numpy as np

warnings.filterwarnings("ignore")

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
DECISION = OUT / "decision_v2.csv"
DECISION_JSON = OUT / "decision_v2.json"
T2 = CLAUDE_DIR / "experiments" / "business_phase" / "forecast_eval" / "forecast_eval_results.json"
DEST = OUT / "destinations.json"
OUT_CSV = OUT / "explanations.csv"

MIN_TRAIN = 24
SPIKE_RATIO = 3.0
SHIFT_RATIO = 2.0

COLUMNS = [
    "SKU", "仓", "状态", "预测方法(实际使用)", "首选方法", "AutoETS可用性",
    "fallback理由", "方法版本", "历史窗口", "可用月数", "该序列验证表现",
    "需求P50(冲减前)", "需求P50(冲减后)", "需求P90", "供给分量(可用/PO/在途/在产)",
    "去重状态(PO/在途/在产)", "缺口公式", "建议量公式", "假设引用", "异常标签",
    "异常处理说明", "缺失字段", "需要时间",
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    db = DB_PATH
    db_hash = sha(db)
    decision = list(csv.DictReader(open(DECISION, encoding="utf-8-sig")))
    djson = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    t2 = json.loads(T2.read_text(encoding="utf-8"))
    dest = {r["sku"]: r for r in json.loads(DEST.read_text(encoding="utf-8"))["rows"]}

    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty)
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
              AND NOT regexp_matches(lower(platform_sku), '(^|[-_])test([-_]|$)')
            GROUP BY 1,2""").fetchall()
        stockout = {}
        for sku, n in con.execute("""
                SELECT goods_sku, COUNT(*) FROM v_stockout_observed
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM v_stockout_observed)
                GROUP BY 1""").fetchall():
            stockout[sku] = int(n)
        wmap_used = con.execute("SELECT COUNT(*) FROM warehouse_map").fetchone()[0]
    finally:
        con.close()
    if sha(db) != db_hash:
        raise SystemExit("DB changed during the run")

    wanted = {r["SKU"] for r in decision}
    monthly = defaultdict(dict)
    for sku, ym, q in rows:
        if sku in wanted:
            monthly[sku][ym] = float(q)
    last_i = int("2026-09"[:4]) * 12 + 9 - 1
    series = {}
    for sku, by in monthly.items():
        first = min(int(m[:4]) * 12 + int(m[5:7]) - 1 for m in by)
        months = [f"{(i)//12:04d}-{i%12+1:02d}" for i in range(first, last_i + 1)]
        series[sku] = dict(first=first, last=last_i, months=months,
                           y=np.array([by.get(m, 0.0) for m in months], dtype=float))

    # AutoETS availability probe (per SKU, on history up to 2026-09)
    from statsforecast import models as sfm
    sf_version = md.version("statsforecast")
    availability = {}
    for sku, s in series.items():
        n = len(s["y"])
        try:
            m = sfm.AutoETS(season_length=12 if n >= 24 else 1)
            m.fit(s["y"].astype(np.float32))
            m.predict(h=1)
            availability[sku] = dict(ok=True, reason="ok", n=n)
        except Exception as exc:
            availability[sku] = dict(ok=False,
                                     reason=f"{type(exc).__name__}:{str(exc)[:60]}", n=n)

    # T2 facts for the method column
    t2_full = next((r for r in t2["runs"] if r["run"] == "full"), None)
    t2_val = (t2_full or {}).get("validation_common", {})
    t2_autoets_wape = (t2_val.get("autoets") or {}).get("wape_keep_zero")
    t2_trainable = t2_full["n_series"] if t2_full else None

    out_rows = []
    tag_counts = Counter()
    for r in decision:
        sku, wh, status = r["SKU"], r["仓"], r["状态"]
        s = series.get(sku)
        d = dest.get(sku, {})
        n_months = len(s["y"]) if s else 0
        hist = (f"{s['months'][0]}..{s['months'][-1]}" if s else "无历史")
        avail_info = availability.get(sku)
        if status == "C":
            autoets = "not_applicable(out_of_scope)"
            fallback = "范围外，不做预测"
        elif avail_info is None:
            autoets = "no_history"
            fallback = "该 SKU 在订单库无月度历史 → 无预测，需求按 0 处理并标注（不是真实零需求）"
        elif avail_info["ok"]:
            autoets = "available(fit_ok)"
            fallback = ("AutoETS 可用，但 T3 的数量仍按 MA3 计算（T4 只解释，不改 T3 数值）；"
                        "切换到 AutoETS 需另行批准")
        else:
            autoets = f"failed({avail_info['reason']})"
            fallback = (f"AutoETS 失败（{avail_info['reason']}）→ fallback 到 MA3"
                        "（该仓近 3 月净销量均值）")

        # validation performance known at model level (per-SKU not stored in T2)
        if status == "C":
            val_perf = "N/A（范围外）"
        elif s is None:
            val_perf = "N/A（无历史，不在 T2 774 条可训练序列内）"
        elif n_months < MIN_TRAIN:
            val_perf = (f"N/A（历史 {n_months} 月 < 24，不在 T2 的 {t2_trainable} 条可训练序列内；"
                        "T2 另有 463 条短历史未评估）")
        else:
            val_perf = (f"模型级验证 WAPE(AutoETS, 共同子集)={t2_autoets_wape}；"
                        "T2 未在结果中存逐 SKU 指标")

        demand_p50 = r["需求P50(冲减前)"]
        qty_lo, qty_hi = r["建议下限L90"], r["建议上限L90"]
        supply = (f"可用={r['可用']}；PO={r['PO未结']}；在途={r['在途']}；"
                  f"在产={r['在产'] or 'null'}")
        dedup = f"PO:{r['PO去重状态']} / 在途:{r['在途去重状态']} / 在产:{r['在产状态']}"
        gap_formula = ("缺口_L = 需求_P50_L − (可用 + 去重情景批)；"
                       "去重情景批 = 重复PO按一笔 / 在途=PO按同批 / 否则两批相加")
        qty_formula = ("建议下限 = max(0, 需求_P50_L90 − (可用 + 去重批))；"
                       "建议上限 = max(0, 需求_P90_L90 − 可用)")
        assumptions_ref = r["assumptions"] or "（C 类不参与计算）"

        # ---------------- anomaly tags ------------------------------------
        tags, notes = [], []

        def tag(name: str, why: str):
            tags.append(name)
            notes.append(f"{name}:{why}")

        if s is not None and n_months < MIN_TRAIN:
            tag("short_history", f"历史仅 {n_months} 月；用 MA3/月度均值而非长周期模型")
        if status != "C" and (r["状态"] == "B_pending_inventory" or r["可用"] == ""):
            tag("missing_inventory", "该仓无库存行 → 库存未知，建议数量留空（未按 0 计算）")
        if r["月需求率"] not in ("", None) and float(r["月需求率"]) == 0.0:
            tag("zero_sales", "该仓近 3 月无销量 → 月需求率 0；这是观测事实，不是缺需求")
        tag("returns_unobservable",
            "gs_orders 无状态字段、窗口内 0 条负数量 → 净销量=已发货；退货/取消未校正")
        dc = (d.get("checks") or {}).get("duplicate_mapping") or {}
        if dc.get("state") == "flag":
            tag("duplicate_mapping", f"P1A 重复映射检查命中：{dc.get('detail')}")
        if s is not None and len(s["y"]) >= 6:
            pos = s["y"][s["y"] > 0]
            med = float(np.median(pos)) if len(pos) else 0.0
            mx = float(s["y"].max())
            if med > 0 and mx >= SPIKE_RATIO * med and mx >= 3 * float(np.mean(sorted(s["y"])[-6:-1] or [mx])):
                tag("promo_spike",
                    f"存在尖峰月 {mx:g} ≥ {SPIKE_RATIO}×正销量中位 {med:g}；"
                    "按观测值参与均值，未剔除（可能含促销/上新，未校正）")
            recent3 = float(np.mean(s["y"][-3:])) if len(s["y"]) >= 3 else 0.0
            prior3 = float(np.mean(s["y"][-6:-3])) if len(s["y"]) >= 6 else 0.0
            if prior3 > 0 and (recent3 / prior3 >= SHIFT_RATIO or recent3 / prior3 <= 1 / SHIFT_RATIO):
                tag("operational_change",
                    f"近 3 月均值/前 3 月均值={recent3 / prior3:.2f}（≥{SHIFT_RATIO}× 或 ≤1/{SHIFT_RATIO}×）；"
                    "可能为运营/渠道变化，按原样计入均值，未做结构突变校正")
        so = stockout.get(sku, 0)
        if so > 0 or (r["已承诺待发"] not in ("", None) and float(r["已承诺待发"]) > 0):
            tag("stockout_censoring",
                f"断货观测 {so} 行 / 待发 {r['已承诺待发']}；历史销量可能被压制，未校正")
        # duplicate mapping check for out-of-scope rows is n/a
        if status == "C" and not dc:
            notes.append("duplicate_mapping:n/a（范围外/未映射，无映射检查）")

        out_rows.append({
            "SKU": sku, "仓": wh, "状态": status,
            "预测方法(实际使用)": ("MA3（该仓近 3 月净销量均值）" if status != "C" else "n/a"),
            "首选方法": "AutoETS" if status != "C" else "n/a",
            "AutoETS可用性": autoets,
            "fallback理由": fallback,
            "方法版本": f"statsforecast {sf_version}（AutoETS 探针）；MA3 为本脚本实现",
            "历史窗口": hist, "可用月数": n_months,
            "该序列验证表现": val_perf,
            "需求P50(冲减前)": demand_p50, "需求P50(冲减后)": r["需求P50(冲减后)"],
            "需求P90": ("（P90 见 decision_v2 建议上限推导）" if status != "C" else None),
            "供给分量(可用/PO/在途/在产)": supply,
            "去重状态(PO/在途/在产)": dedup,
            "缺口公式": gap_formula, "建议量公式": qty_formula,
            "假设引用": assumptions_ref,
            "异常标签": "；".join(tags) if tags else "（无）",
            "异常处理说明": " | ".join(notes) if notes else "（无异常标签）",
            "缺失字段": r["缺失字段与证据"],
            "需要时间": r["需要时间"] or "",
        })
        for t in tags:
            tag_counts[t] += 1

    if len(out_rows) != len(decision):
        raise SystemExit(f"row count {len(out_rows)} != decision {len(decision)}")
    if len({(r['SKU'], r['仓']) for r in out_rows}) != len(out_rows):
        raise SystemExit("duplicate SKU×仓 row")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    print(f"wrote {OUT_CSV} ({OUT_CSV.stat().st_size:,} bytes)")
    print("rows", len(out_rows), "from decision", len(decision))
    print("tags", dict(tag_counts))
    print("autoets ok/fail:", Counter(v["ok"] for v in availability.values()))


if __name__ == "__main__":
    main()
