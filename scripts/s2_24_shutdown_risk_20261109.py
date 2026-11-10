# -*- coding: utf-8 -*-
"""S2.12 春节第二批停工风险：同一需求路径，对比“停工前插单”与“复工后生产”。

只读 CNY v9 / D5 v6.7 / D6 v6.18，输出一张风险表，不改变主方案。
"""
from __future__ import annotations
import hashlib
import math
import zlib
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D5 = BASE / "D5v6_7-novcast/D_概率与服务_D5_v6_7_2026-11-09.xlsx"
D6 = BASE / "D6v6_20-1110/D_Top50沙盒_D6_v6_20_2026-11-10.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-10_v11.xlsx"
OUT = BASE / "S2_9-delivery-final-20261106/D_春节第二批停工风险_2026-11-10_v11.xlsx"
KEYS = ["product_id", "池", "形态", "UOM"]
DECISION = pd.Timestamp("2026-11-10")
N = 1000
SEED = 42


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def key_rng(key) -> np.random.Generator:
    token = "|".join(str(x) for x in key)
    return np.random.default_rng(SEED + zlib.crc32(token.encode("utf-8")) % 1_000_000)


def simulate(rng, H, d50, d95, on_hand, receipts, batch_arrivals):
    if d50 > 0:
        sigma = max(0.05, (math.log(d95) - math.log(d50)) / 1.645) if d95 > d50 else 0.05
        total = rng.lognormal(math.log(d50 * H), sigma, N)
        total = np.minimum(total, math.exp(math.log(d50 * H) + 3.09 * sigma))
    else:
        total = np.zeros(N)
    shares = rng.dirichlet(np.full(H, 10.0), size=N)
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
    fill = 1.0 - float(shortage.sum()) / max(float(demand.sum()), 1e-9)
    return float(np.mean(stockout_days == 0)), float(fill)


def main() -> int:
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5.horizon.astype(str) == "97"][
        ["product_id", "pool", "physical_form", "canonical_uom", "p50", "q95"]].rename(
        columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
                 "p50": "p50d5", "q95": "q95d5"})
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期")
    d6 = pd.read_excel(D6, sheet_name="1_全量动作")
    supply_cols = ["C可发供给", "en_stock在途+待发", "PO追加(去重)", "在途ETA_p50", "CG可调拨抵扣"]
    cny = cny.merge(d5, on=KEYS, how="left").merge(
        d6[KEYS + supply_cols], on=KEYS, how="left", suffixes=("", "_d6"))

    rows = []
    for _, r in cny.iterrows():
        if not bool(r["第二批需停工前插单"]):
            continue
        p50 = float(r["p50d5"]) if pd.notna(r["p50d5"]) else 0.0
        q95 = float(r["q95d5"]) if pd.notna(r["q95d5"]) else 0.0
        if q95 <= 0:
            continue
        d50 = p50 / 97
        d95 = q95 / 97 if q95 > 0 else d50
        if p50 <= 0:
            continue
        on_hand = float(r["C可发供给"]) if pd.notna(r["C可发供给"]) else 0.0
        inb = ((float(r["en_stock在途+待发"]) if pd.notna(r["en_stock在途+待发"]) else 0.0)
               + (float(r["PO追加(去重)"]) if pd.notna(r["PO追加(去重)"]) else 0.0))
        eta = pd.to_datetime(r.get("在途ETA_p50"), errors="coerce")
        receipts = []
        if inb > 0 and pd.notna(eta):
            day = max(0, int((eta - DECISION).days))
            if day < 365:
                receipts.append((day, inb))
        cg = float(r.get("CG可调拨抵扣", 0) or 0) if pd.notna(r.get("CG可调拨抵扣")) else 0.0
        cov = pd.to_datetime(r["覆盖终点"], errors="coerce")
        Hh = max(90, int((cov - DECISION).days) + 7) if pd.notna(cov) else 97
        q1 = int(r["首批数量"]) if pd.notna(r["首批数量"]) else 0
        q2 = int(r["第二批数量"]) if pd.notna(r["第二批数量"]) else 0
        arr1 = pd.to_datetime(r["首批到仓"], errors="coerce")
        arr2a = pd.to_datetime(r["第二批到仓"], errors="coerce")
        # 方案 B：不提前插单，仍按原连续排期下单（1/1 或 1/7），
        # 生产到 1/24 停工，2/22 复工后补完剩余生产天数，再运输。
        prod = {"美东USNJ": 30.0, "美中USTX": 35.2, "波兰": 43.6}.get(str(r["池"]), 30.0)
        trans = {"空运": 16, "快船": 32, "普船": 57, "专线": 62}.get(str(r["建议运输"]), 32)
        orig_order = pd.Timestamp("2027-02-22") - pd.Timedelta(days=prod + trans)
        worked = max(0.0, (pd.Timestamp("2027-01-24") - orig_order).days)
        remaining = max(0.0, prod - worked)
        b_finish = pd.Timestamp("2027-02-22") + pd.Timedelta(days=remaining)
        arr2b = b_finish + pd.Timedelta(days=trans)
        d1 = max(0, int((arr1 - DECISION).days)) if pd.notna(arr1) else 0
        d2a = max(0, int((arr2a - DECISION).days)) if pd.notna(arr2a) else d1
        d2b = max(0, int((arr2b - DECISION).days)) if pd.notna(arr2b) else d1
        key = (r["product_id"], r["池"], r["形态"], r["UOM"])
        ns_a, fl_a = simulate(key_rng(key + ("cny",)), Hh, d50, d95, on_hand + cg,
                              receipts, [(d1, q1), (d2a, q2)])
        ns_b, fl_b = simulate(key_rng(key + ("cny",)), Hh, d50, d95, on_hand + cg,
                              receipts, [(d1, q1), (d2b, q2)])
        lv = str(r["放行等级"])
        if lv.startswith("A"):
            ok_a, ok_b = ns_a >= 0.95, ns_b >= 0.95
        elif lv.startswith("B"):
            ok_a, ok_b = fl_a >= 0.95, fl_b >= 0.95
        else:
            ok_a = ok_b = False
        rows.append(dict(
            商品编码=r["product_id"], 物料名称=r.get("物料名称", ""), 分公司=r["池"],
            形态=r["形态"], 单位=r["UOM"], 放行等级=lv,
            第二批数量=q2,
            方案A_第二批下单日=r["第二批下单日"],
            方案A_第二批到仓=r["第二批到仓"],
            方案B_第二批下单日=orig_order.date().isoformat(),
            方案B_第二批到仓=arr2b.date().isoformat(),
            方案A_无断货概率=round(ns_a, 4), 方案A_满足率=round(fl_a, 4),
            方案B_无断货概率=round(ns_b, 4), 方案B_满足率=round(fl_b, 4),
            方案A_达原目标=ok_a, 方案B_达原目标=ok_b,
            停工后失去目标=(ok_a and not ok_b),
        ))
    out = pd.DataFrame(rows)
    out = out.sort_values(["停工后失去目标", "第二批数量"], ascending=[False, False])
    summary = pd.DataFrame([
        ("需停工前插单键数", len(out)),
        ("涉及第二批件数", int(out["第二批数量"].sum())),
        ("方案A达原目标", int(out["方案A_达原目标"].sum())),
        ("方案B达原目标", int(out["方案B_达原目标"].sum())),
        ("停工后失去目标", int(out["停工后失去目标"].sum())),
    ], columns=["项", "值"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="1_汇总", index=False)
        out.to_excel(w, sheet_name="2_逐键", index=False)
        out[out["停工后失去目标"]].to_excel(w, sheet_name="3_失去目标", index=False)
    print(summary.to_string(index=False))
    print("\n失去目标：")
    print(out[out["停工后失去目标"]][["商品编码", "分公司", "放行等级", "第二批数量"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
