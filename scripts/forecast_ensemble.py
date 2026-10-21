# -*- coding: utf-8 -*-
"""销量预测（ens5）+ 滚动回测 —— 对齐 PR #300 E1 方法

方法：MA3 / MA6 / MA12 / Croston / TSB，ens5 = 五者中位数。
回测：滚动 origin，horizon=3 个月，指标 WAPE。
数据：gs_orders，按**发货月份**聚合到 SKU × 仓（对齐 E1 口径）。

输出（DuckDB）：
  monthly_series    (sku, warehouse, month, qty)
  forecast_sku_wh   (sku, warehouse, month, forecast_qty, method)
  backtest_summary  (method, wape, n_units)

用法：
  uv run python scripts/forecast_ensemble.py --horizon 3 --origins 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# 主发货仓（成品补货只针对这三家）
MAIN_WH = ("美东-CENTRADE", "美中-FZH-DANEEY", "波兰-FZHPoland-covers")


def ma(series, h):
    if len(series) < h:
        return float(np.mean(series)) if series else 0.0
    return float(np.mean(series[-h:]))


def croston(series, alpha=0.1):
    z = None
    p = None
    q = 1
    out = []
    for x in series:
        if x > 0:
            if z is None:
                z = float(x)
                p = 1.0
            else:
                z = alpha * x + (1 - alpha) * z
                p = alpha * q + (1 - alpha) * p
            q = 1
        else:
            q += 1
        out.append((z or 0.0) / (p or 1.0))
    return out


def tsb(series, alpha=0.1, beta=0.1):
    z = 0.0
    p = 0.0
    out = []
    first = True
    for x in series:
        if x > 0:
            z = float(x) if first else alpha * x + (1 - alpha) * z
            p = beta + (1 - beta) * p if not first else 1.0
            first = False
        else:
            p = (1 - beta) * p
        out.append(z * p)
    return out


def forecast_all(series):
    """返回 {method: [h1..hH]}，全部用整段历史拟合后外推 H=3 个月。"""
    s = list(series)
    return {
        "ma3": [ma(s, 3)] * 3,
        "ma6": [ma(s, 6)] * 3,
        "ma12": [ma(s, 12)] * 3,
        "croston": [croston(s)[-1]] * 3,
        "tsb": [tsb(s)[-1]] * 3,
    }


def ens(values):
    return float(np.median(values))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="D:/Work/fzh-order-store")
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--origins", type=int, default=6, help="回测用最近 N 个 origin")
    ap.add_argument("--min-months", type=int, default=3,
                    help="出预测所需最少历史月数；短史 SKU 用现有方法兜底")
    ap.add_argument("--backtest-min-months", type=int, default=12,
                    help="回测只跑历史 ≥N 月的序列，保证与 E1 结论可比")
    args = ap.parse_args()

    con = duckdb.connect(str(Path(args.out) / "order_store.duckdb"))

    # 0) 仓库改名映射：旧名 → 当前仓（精确 → 补前缀 → 原样）
    cur = [r[0] for r in con.execute(
        "SELECT warehouse_name FROM warehouse_dim WHERE CAST(status AS VARCHAR)='1'").fetchall()]
    cur_set = set(cur)
    gs_wh = [r[0] for r in con.execute(
        "SELECT DISTINCT warehouse FROM gs_orders WHERE IFNULL(warehouse,'')<>''").fetchall()]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from warehouse_map import classify
    mapping = []
    for w in gs_wh:
        target, cls = classify(w, cur_set)
        mapping.append({"gs_warehouse": w, "current_warehouse": target or w, "class": cls})
    con.register("_m", pd.DataFrame(mapping))
    con.execute("CREATE OR REPLACE TABLE warehouse_map AS SELECT * FROM _m")
    con.unregister("_m")

    con.execute("""
        CREATE OR REPLACE TABLE monthly_series AS
        SELECT g.sku_tongtool AS sku, m.current_warehouse AS warehouse,
               substr(COALESCE(NULLIF(g.despatch_date,''), g.sale_date), 1, 7) AS month,
               SUM(g.qty) AS qty
        FROM gs_orders g
        LEFT JOIN warehouse_map m ON g.warehouse = m.gs_warehouse
        WHERE IFNULL(g.sku_tongtool,'') <> ''
          AND COALESCE(NULLIF(g.despatch_date,''), g.sale_date) IS NOT NULL
        GROUP BY 1, 2, 3
    """)

    df = con.execute("SELECT sku, warehouse, month, qty FROM monthly_series").df()
    df = df[df["warehouse"].isin(MAIN_WH)]
    months_all = sorted(df["month"].dropna().unique())
    idx = {m: i for i, m in enumerate(months_all)}

    results = []       # 未来预测
    bt = []            # 回测误差
    groups = df.groupby(["sku", "warehouse"])
    n_series = 0
    for (sku, wh), g in groups:
        g = g.sort_values("month")
        # 补齐缺失月为 0（只在首末月之间）
        if len(g) < args.min_months:
            continue
        start, end = idx[g["month"].iloc[0]], idx[g["month"].iloc[-1]]
        series = [0.0] * (end - start + 1)
        for m, q in zip(g["month"], g["qty"]):
            series[idx[m] - start] = float(q) if pd.notna(q) else 0.0
        if sum(series) <= 0:
            continue
        n_series += 1

        # 预测未来 H 个月
        fc = forecast_all(series)
        last_month = g["month"].iloc[-1]
        y, mo = int(last_month[:4]), int(last_month[5:7])
        future = []
        for _ in range(args.horizon):
            mo += 1
            if mo == 13:
                y += 1
                mo = 1
            future.append(f"{y:04d}-{mo:02d}")
        for method, vals in fc.items():
            for m, v in zip(future, vals):
                results.append({"sku": sku, "warehouse": wh, "month": m,
                                "forecast_qty": max(0.0, v), "method": method})
        for i, m in enumerate(future):
            results.append({"sku": sku, "warehouse": wh, "month": m,
                            "forecast_qty": max(0.0, ens([fc[k][i] for k in fc])), "method": "ens5"})

        # 滚动回测（最近 N 个 origin，horizon=H）；只跑「有销售月数 ≥12」的序列，保持与 E1 可比
        n = len(series)
        if len(g) < args.backtest_min_months:
            continue
        for o in range(max(1, n - args.origins * args.horizon), n - args.horizon):
            train = series[:o]
            if sum(train) <= 0:
                continue
            f = forecast_all(train)
            actual = series[o:o + args.horizon]
            for method, vals in f.items():
                bt.append({"method": method, "actual": actual, "pred": vals})
            bt.append({"method": "ens5", "actual": actual,
                       "pred": [ens([f[k][i] for k in f]) for i in range(args.horizon)]})

    # 汇总 WAPE
    rows = []
    for method in ("ma3", "ma6", "ma12", "croston", "tsb", "ens5"):
        sel = [b for b in bt if b["method"] == method]
        if not sel:
            continue
        num = sum(abs(a - p) for b in sel for a, p in zip(b["actual"], b["pred"]))
        den = sum(abs(a) for b in sel for a in b["actual"])
        rows.append({"method": method, "wape": round(num / den, 3) if den else None,
                     "n_units": len(sel)})
    summary = pd.DataFrame(rows).sort_values("wape")

    con.register("_f", pd.DataFrame(results))
    con.register("_s", summary)
    con.execute("CREATE OR REPLACE TABLE forecast_sku_wh AS SELECT * FROM _f")
    con.execute("CREATE OR REPLACE TABLE backtest_summary AS SELECT * FROM _s")
    con.close()

    print(json.dumps({
        "series": n_series,
        "forecast_rows": len(results),
        "backtest": summary.to_dict("records"),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
