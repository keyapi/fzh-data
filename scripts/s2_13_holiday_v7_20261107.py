# -*- coding: utf-8 -*-
"""CNY schedule v7: integer batches + pre-haul 2 + same-source quantities.

Rules:
- daily q95 = D5 97-day q95 / 97
- stock at Jan-24 = max(0, C + EN in-transit + PO - daily * 79)
- post-shutdown demand = daily * coverage_days (A=64, B=80)
- total = round(max(0, post_demand - stock_jan24))
- first = round(total * 0.6); second = total - first  (exact integers)
- first arrival = decision + prod + prehaul 2 + mode days
- latest order = Jan-24 - (pool p95 + prehaul 2)
"""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
D6 = BASE / "D6v6_15-final/D_Top50沙盒_D6_v6_15_2026-11-07.xlsx"
V6 = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v6.xlsx"
OUT = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v7.xlsx"
DECISION = pd.Timestamp("2026-11-06")
JAN24 = pd.Timestamp("2027-01-24")
PREHAUL = 2
MODE_DAYS = {"空运": 14, "快船": 30, "普船": 55, "专线": 60}
PROD = {"美东USNJ": 30.0, "美中USTX": 35.2, "波兰": 43.6}
P95 = {"美东USNJ": 38.65, "美中USTX": 54.15, "波兰": 83.6}
KEYS = ["product_id", "池", "形态", "UOM"]


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5["horizon"].astype(str) == "97"].rename(
        columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM"})
    d6 = pd.read_excel(D6, sheet_name="1_全量动作").rename(
        columns={"池": "池", "形态": "形态", "UOM": "UOM"})
    v6 = pd.read_excel(V6, sheet_name="2_逐键排期")
    base = v6[KEYS].copy()
    m = base.merge(d5[KEYS + ["p50", "q95"]], on=KEYS, how="left")
    m = m.merge(d6[KEYS + ["C可发供给", "en_stock在途+待发", "PO追加(去重)",
                           "建议动作", "净需求95"]], on=KEYS, how="left")
    m = m.merge(v6[KEYS + ["物料名称", "通途SKU/来源码（不含FBA）", "放行等级",
                           "建议运输", "覆盖终点"]], on=KEYS, how="left")
    rows = []
    for _, r in m.iterrows():
        pool = str(r["池"]); mode = str(r["建议运输"])
        q95 = float(r["q95"]) if pd.notna(r["q95"]) else 0.0
        p50 = float(r["p50"]) if pd.notna(r["p50"]) else 0.0
        daily = q95 / 97 if q95 > 0 else 0.0
        zero_median = (p50 <= 0 and q95 > 0)
        c = float(r["C可发供给"]) if pd.notna(r["C可发供给"]) else 0.0
        inb = ((float(r["en_stock在途+待发"]) if pd.notna(r["en_stock在途+待发"]) else 0.0)
               + (float(r["PO追加(去重)"]) if pd.notna(r["PO追加(去重)"]) else 0.0))
        supply = c + inb
        cov_end = pd.to_datetime(r["覆盖终点"], errors="coerce")
        days_cov = (cov_end - DECISION).days if pd.notna(cov_end) else 0
        total_raw = max(0.0, daily * days_cov - supply)
        total = 0 if zero_median else int(round(total_raw))
        first = 0 if zero_median else int(round(total * 0.6))
        second = total - first
        level = str(r["放行等级"])
        first = int(round(total * 0.6))
        second = total - first
        prod = PROD.get(pool, 30.0)
        days = MODE_DAYS.get(mode, 30)
        lead = prod + PREHAUL + days
        first_arr = DECISION + pd.Timedelta(days=lead)
        cutoff = JAN24 - pd.Timedelta(days=lead)
        second_arr = cutoff + pd.Timedelta(days=lead)
        stockout = (DECISION + pd.Timedelta(days=int(c / daily))
                    if daily > 0 and c > 0 else DECISION)
        risk = "" if zero_median else ("所有模式首批都晚于q95断货日" if first_arr > stockout else "")
        rows.append(dict(
            product_id=r["product_id"], 物料名称=r.get("物料名称", ""),
            **{"通途SKU/来源码（不含FBA）": r.get("通途SKU/来源码（不含FBA）", "")},
            池=pool, 形态=r["形态"], UOM=r["UOM"], 放行等级=level,
            日均q95需求=0 if zero_median else round(daily, 4), 当前可用=round(c, 2),
            预计q95断货日=stockout.date().isoformat(), 建议运输=mode,
            首批到仓=first_arr.date().isoformat(),
            第二批到仓=second_arr.date().isoformat(),
            覆盖终点=r["覆盖终点"],
            建议节前备货量=total, 首批数量=first, 第二批数量=second,
            最迟下单日=cutoff.date().isoformat(), 风险=risk,
            模型资格="零中位数-隔离" if zero_median else "正常",
            建议动作D6=r.get("建议动作", ""),
        ))
    out = pd.DataFrame(rows)
    out["批次合计"] = out["首批数量"] + out["第二批数量"]
    out["批次差"] = out["建议节前备货量"] - out["批次合计"]
    summary = pd.DataFrame([
        ("行数", len(out)),
        ("建议节前备货量", int(out["建议节前备货量"].sum())),
        ("首批合计", int(out["首批数量"].sum())),
        ("第二批合计", int(out["第二批数量"].sum())),
        ("批次差非零行", int((out["批次差"] != 0).sum())),
        ("首批晚于断货日", int((out["风险"] != "").sum())),
        ("零中位数隔离行", int((out["模型资格"] == "零中位数-隔离").sum())),
        ("prehaul天数", PREHAUL),
    ], columns=["项", "值"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="1_汇总", index=False)
        out.to_excel(w, sheet_name="2_逐键排期", index=False)
        out[out["批次差"] != 0][["product_id", "建议节前备货量", "首批数量",
                                 "第二批数量", "批次差"]].to_excel(
            w, sheet_name="3_整数校验", index=False)
    print(summary.to_string(index=False))
    print("inputs", sha(D5)[:12], sha(D6)[:12], sha(V6)[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
