# -*- coding: utf-8 -*-
"""S2.10 unified daily trajectory: CNY batches + 5,239 new orders.

Reads CNY v6, D6 v6.14 and D5 v6.5; simulates 180 days with p50/q95-matched
demand, current stock, ETA receipts, and two CNY batches / one new order.
Read-only; writes a workbook with pass/fail per action.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D5 = BASE / "D5v6_5-60cm/D_概率与服务_D5_v6_5_2026-11-06.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v6.xlsx"
D6 = BASE / "D6v6_14-final/D_Top50沙盒_D6_v6_14_2026-11-06.xlsx"
OUT = BASE / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-06.xlsx"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
DECISION = pd.Timestamp("2026-11-06")
H, N = 180, 1000
RNG = np.random.default_rng(42)
MODE_DAYS = {"空运": 14, "快船": 30, "普船": 55, "专线": 60, "路线待确认": 60}


def simulate(d50, d95, on_hand, receipts, batch_arrivals):
    if d50 > 0 and d95 > d50:
        sigma = max(0.05, (math.log(d95) - math.log(d50)) / 1.645)
        total = RNG.lognormal(math.log(d50 * H), sigma, N)
    elif d95 > 0:
        total = RNG.exponential(d95 * H / 3.0, N)
    else:
        total = np.zeros(N)
    shares = RNG.dirichlet(np.full(H, 10.0), size=N)
    demand = total[:, None] * shares
    stock = np.full(N, max(0.0, float(on_hand)))
    shortage = np.zeros(N)
    stockout_days = np.zeros(N)
    for day in range(H):
        for rday, qty in receipts:
            if rday == day:
                stock += qty
        for rday, qty in batch_arrivals:
            if int(rday) == day:
                stock += qty
        d = demand[:, day]
        short = np.maximum(0.0, d - stock)
        shortage += short
        stock = np.maximum(0.0, stock - d)
        stockout_days += (short > 0).astype(float)
    total_demand = demand.sum(axis=1)
    fill = np.where(total_demand > 0, 1 - shortage / np.maximum(total_demand, 1e-9), 1.0)
    return float(np.mean(stockout_days == 0)), float(np.mean(fill))


def main() -> int:
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5.horizon.astype(str) == "97"][KEYS + ["p50", "q95"]].rename(
        columns={"p50": "p50d5", "q95": "q95d5"})
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    d6 = pd.read_excel(D6, sheet_name="1_全量动作").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    supply_cols = ["C可发供给", "en_stock在途+待发", "PO追加(去重)", "在途ETA_p50"]
    cny = cny.merge(d5, on=KEYS, how="left").merge(d6[KEYS + supply_cols], on=KEYS,
                                                   how="left", suffixes=("", "_d6"))
    new = d6[(d6["催已有行动"] == True) &  # noqa: E712
             (pd.to_numeric(d6["新补数量"], errors="coerce").fillna(0) > 0)].merge(
        d5, on=KEYS, how="left")
    rows = []
    for _, r in cny.iterrows():
        p50 = float(r["p50d5"]) if pd.notna(r["p50d5"]) else 0.0
        q95 = float(r["q95d5"]) if pd.notna(r["q95d5"]) else 0.0
        d50 = p50 / 97 if p50 > 0 else (q95 / 97 if q95 > 0 else 0.0)
        d95 = q95 / 97 if q95 > 0 else d50
        on_hand = float(r["C可发供给"]) if pd.notna(r["C可发供给"]) else 0.0
        inb = ((float(r["en_stock在途+待发"]) if pd.notna(r["en_stock在途+待发"]) else 0.0)
               + (float(r["PO追加(去重)"]) if pd.notna(r["PO追加(去重)"]) else 0.0))
        eta = pd.to_datetime(r.get("在途ETA_p50"), errors="coerce")
        receipts = []
        if inb > 0 and pd.notna(eta):
            day = max(0, int((eta - DECISION).days))
            if day < H:
                receipts.append((day, inb))
        arr = pd.to_datetime(r["首批到仓"], errors="coerce")
        d1 = max(0, int((arr - DECISION).days)) if pd.notna(arr) else 0
        q1 = float(r["首批数量"]) if pd.notna(r["首批数量"]) else 0.0
        q2 = float(r["第二批数量"]) if pd.notna(r["第二批数量"]) else 0.0
        ns, fill = simulate(d50, d95, on_hand, receipts, [(d1, q1), (d1 + 7, q2)])
        rows.append(dict(类型="春节", product_id=r["product_id"], 物料名称=r.get("物料名称", ""),
                         池=r["pool"], 形态=r["physical_form"], UOM=r["canonical_uom"],
                         数量=q1 + q2, 首批到仓=arr.date().isoformat() if pd.notna(arr) else "",
                         建议运输=r["建议运输"], 无断货概率=round(ns, 4),
                         满足率=round(fill, 4),
                         状态="通过" if ns >= .95 and fill >= .95 else "未通过"))
    for _, r in new.iterrows():
        p50 = float(r["p50d5"]) if pd.notna(r["p50d5"]) else 0.0
        q95 = float(r["q95d5"]) if pd.notna(r["q95d5"]) else 0.0
        d50 = p50 / 97 if p50 > 0 else (q95 / 97 if q95 > 0 else 0.0)
        d95 = q95 / 97 if q95 > 0 else d50
        on_hand = float(r["C可发供给"]) if pd.notna(r["C可发供给"]) else 0.0
        inb = ((float(r["en_stock在途+待发"]) if pd.notna(r["en_stock在途+待发"]) else 0.0)
               + (float(r["PO追加(去重)"]) if pd.notna(r["PO追加(去重)"]) else 0.0))
        eta = pd.to_datetime(r.get("在途ETA_p50"), errors="coerce")
        receipts = []
        if inb > 0 and pd.notna(eta):
            day = max(0, int((eta - DECISION).days))
            if day < H:
                receipts.append((day, inb))
        mode = str(r.get("推荐main_haul", "空运")).replace("海运", "")
        days = MODE_DAYS.get(mode, 30)
        qty = float(r["新补数量"])
        ns, fill = simulate(d50, d95, on_hand, receipts, [(min(H - 1, days), qty)])
        rows.append(dict(类型="新增", product_id=r["product_id"], 物料名称=r.get("物料名称", ""),
                         池=r["pool"], 形态=r["physical_form"], UOM=r["canonical_uom"],
                         数量=qty, 首批到仓=(DECISION + pd.Timedelta(days=days)).date().isoformat(),
                         建议运输=mode, 无断货概率=round(ns, 4), 满足率=round(fill, 4),
                         状态="通过" if ns >= .95 and fill >= .95 else "未通过"))
    out = pd.DataFrame(rows)
    summary = out.groupby(["类型", "状态"]).agg(
        键数=("product_id", "size"), 数量=("数量", "sum")).reset_index()
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        pd.DataFrame([("规则", "H=180,N=1000；需求总对齐p50/q95再Dirichlet分日；C库存+ETA在途+两批到货")],
                     columns=["项", "内容"]).to_excel(w, sheet_name="0_说明", index=False)
        summary.to_excel(w, sheet_name="1_汇总", index=False)
        out.to_excel(w, sheet_name="2_逐键", index=False)
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
