# -*- coding: utf-8 -*-
"""S2.11 unified daily trajectory v9: CNY batches + shutdown-safe schedule.

Changes vs v5:
- pre-haul fixed at 2 days; shelving 0 (both explicit, not folded into 55/30/14).
- per-key RNG derived from the key, so results do not depend on row order.
- explicit evaluation window per row (task window) + a common 180-day sensitivity.
- daily mean demand/stock/shortage exported for reproducibility.
- input hashes / seed / N written to the workbook.

Read-only for source data; writes one workbook.
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
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-11_v12.xlsx"
D6 = BASE / "D6v6_21-1111/D_Top50沙盒_D6_v6_21_2026-11-11.xlsx"
OUT = BASE / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-11_v12.xlsx"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
DECISION = pd.Timestamp("2026-11-11")
N = 1000
SEED = 42
H_SENS = 180
PREHAUL_DAYS = 2
SHELVING_DAYS = 0
MODE_DAYS = {"空运": 14, "快船": 30, "普船": 55, "专线": 60, "路线待确认": 60}


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
    daily = []
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
        daily.append((day, float(d.mean()), float(stock.mean()), float(short.mean())))
        stock = np.maximum(0.0, stock - d)
        stockout_days += (short > 0).astype(float)
    fill = 1.0 - float(shortage.sum()) / max(float(demand.sum()), 1e-9)
    return float(np.mean(stockout_days == 0)), float(fill), daily


def status_of(ns, fill, sigma, demand_flag=""):
    if demand_flag == "零中位数":
        return "模型异常-零中位数"
    if demand_flag == "无需求":
        return "无需求-不判定"
    if sigma > 2.0:
        return "模型异常"
    if ns >= 0.95:
        return "cycle95"
    if fill >= 0.95:
        return "fill95"
    return "fail"


def main() -> int:
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5.horizon.astype(str) == "97"][KEYS + ["p50", "q95"]].rename(
        columns={"p50": "p50d5", "q95": "q95d5"})
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    d6 = pd.read_excel(D6, sheet_name="1_全量动作").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    supply_cols = ["C可发供给", "en_stock在途+待发", "PO追加(去重)", "在途ETA_p50", "CG可调拨抵扣"]
    cny = cny.merge(d5, on=KEYS, how="left").merge(d6[KEYS + supply_cols], on=KEYS,
                                                   how="left", suffixes=("", "_d6"))
    new = d6[(d6["催已有行动"] == True) &  # noqa: E712
             (pd.to_numeric(d6["新补数量"], errors="coerce").fillna(0) > 0)].merge(
        d5, on=KEYS, how="left")

    rows, sens_rows, daily_rows = [], [], []

    def prep(r):
        p50 = float(r["p50d5"]) if pd.notna(r["p50d5"]) else 0.0
        q95 = float(r["q95d5"]) if pd.notna(r["q95d5"]) else 0.0
        d50 = p50 / 97 if p50 > 0 else 0.0
        d95 = q95 / 97 if q95 > 0 else d50
        demand_flag = "零中位数" if (p50 <= 0 and q95 > 0) else (
            "无需求" if (p50 <= 0 and q95 <= 0) else "")
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
        sigma = max(0.05, (math.log(d95) - math.log(d50)) / 1.645) if d50 > 0 and d95 > d50 else 0.0
        return d50, d95, on_hand + cg, receipts, sigma, demand_flag

    prod_map = {"美东USNJ": 30.0, "美中USTX": 35.2, "波兰": 43.6}

    for _, r in cny.iterrows():
        d50, d95, on_hand, receipts, sigma, demand_flag = prep(r)
        prod = prod_map.get(str(r["pool"]), 30.0)
        days = MODE_DAYS.get(str(r["建议运输"]), 30)
        lead = prod + PREHAUL_DAYS + days + SHELVING_DAYS
        total_qty = int(round(float(r["建议节前备货量"]))) if pd.notna(r["建议节前备货量"]) else 0
        q1 = int(r["首批数量"]) if pd.notna(r["首批数量"]) else 0
        q2 = int(r["第二批数量"]) if pd.notna(r["第二批数量"]) else total_qty - q1
        assert q1 + q2 == total_qty, (r["product_id"], q1, q2, total_qty)
        arr1 = pd.to_datetime(r.get("首批到仓"), errors="coerce")
        arr2 = pd.to_datetime(r.get("第二批到仓"), errors="coerce")
        if pd.isna(arr1):
            arr1 = DECISION + pd.Timedelta(days=lead)
        if pd.isna(arr2):
            cutoff = pd.to_datetime(r["最迟下单日"], errors="coerce")
            arr2 = (cutoff + pd.Timedelta(days=lead)) if pd.notna(cutoff) else arr1
        cov = pd.to_datetime(r["覆盖终点"], errors="coerce")
        Hh = max(90, int((cov - DECISION).days) + 7) if pd.notna(cov) else 97
        d1 = max(0, int((arr1 - DECISION).days)); d2 = max(0, int((arr2 - DECISION).days))
        key = (r["product_id"], r["pool"], r["physical_form"], r["canonical_uom"])
        if demand_flag:
            ns = fill = None
            daily = []
            st = status_of(ns, fill, sigma, demand_flag)
        else:
            ns, fill, daily = simulate(key_rng(key + ("cny",)), Hh, d50, d95, on_hand,
                                       receipts, [(d1, q1), (d2, q2)])
            st = status_of(ns, fill, sigma)
        rows.append(dict(类型="春节", product_id=r["product_id"], 物料名称=r.get("物料名称", ""),
                         池=r["pool"], 形态=r["physical_form"], UOM=r["canonical_uom"],
                         数量=total_qty, 首批数量=q1, 第二批数量=q2, 评估天数=Hh,
                         窗口起=DECISION.date().isoformat(),
                         窗口止=(DECISION + pd.Timedelta(days=Hh - 1)).date().isoformat(),
                         窗口依据="到覆盖终点+7天", 需求外推="97天日均外推到覆盖终点",
                         首批到仓=arr1.date().isoformat(), 第二批到仓=arr2.date().isoformat(),
                         第二批晚于覆盖终点=bool(pd.notna(cov) and arr2 > cov),
                         建议运输=r["建议运输"],
                         风险状态=r.get("风险状态", ""),
                         可换运输=r.get("可换运输", ""),
                         补救最快到仓=r.get("补救最快到仓", ""),
                         模型资格=r.get("模型资格", ""),
                         无断货概率=round(ns, 4) if ns is not None else None,
                         满足率=round(fill, 4) if fill is not None else None,
                         需求sigma=round(sigma, 2),
                         需求异常=(demand_flag != "" or sigma > 2.0),
                         需求异常类型=demand_flag, 状态=st))
        if demand_flag:
            sens_rows.append(dict(类型="春节", product_id=r["product_id"], 池=r["pool"],
                                  形态=r["physical_form"], UOM=r["canonical_uom"],
                                  数量=total_qty, 评估天数=H_SENS, 无断货概率=None,
                                  满足率=None, 状态=st))
        else:
            ns2, fill2, _ = simulate(key_rng(key + ("cny", "s180")), H_SENS, d50, d95, on_hand,
                                     receipts, [(d1, q1), (d2, q2)])
            sens_rows.append(dict(类型="春节", product_id=r["product_id"], 池=r["pool"],
                                  形态=r["physical_form"], UOM=r["canonical_uom"],
                                  数量=total_qty, 评估天数=H_SENS, 无断货概率=round(ns2, 4),
                                  满足率=round(fill2, 4), 状态=status_of(ns2, fill2, sigma)))
            for day, md, ms, msh in daily:
                daily_rows.append(dict(类型="春节", product_id=r["product_id"], 池=r["pool"],
                                       形态=r["physical_form"], UOM=r["canonical_uom"],
                                       日序=day + 1,
                                       日期=(DECISION + pd.Timedelta(days=day)).date().isoformat(),
                                       日均需求=round(md, 4), 日均库存=round(ms, 4),
                                       日均缺口=round(msh, 4)))

    for _, r in new.iterrows():
        d50, d95, on_hand, receipts, sigma, demand_flag = prep(r)
        mode = str(r.get("推荐main_haul", "空运")).replace("海运", "")
        days = MODE_DAYS.get(mode, 30)
        prod = prod_map.get(str(r["pool"]), 30.0)
        lead = int(prod + PREHAUL_DAYS + days + SHELVING_DAYS)
        qty = float(r["新补数量"])
        Hh = 97
        key = (r["product_id"], r["pool"], r["physical_form"], r["canonical_uom"])
        if demand_flag:
            ns = fill = None
            daily = []
            st = status_of(ns, fill, sigma, demand_flag)
        else:
            ns, fill, daily = simulate(key_rng(key + ("new",)), Hh, d50, d95, on_hand,
                                       receipts, [(lead, qty)])
            st = status_of(ns, fill, sigma)
        rows.append(dict(类型="新增", product_id=r["product_id"], 物料名称=r.get("物料名称", ""),
                         池=r["pool"], 形态=r["physical_form"], UOM=r["canonical_uom"],
                         数量=qty, 首批数量=qty, 第二批数量=0, 评估天数=Hh,
                         窗口起=DECISION.date().isoformat(),
                         窗口止=(DECISION + pd.Timedelta(days=Hh - 1)).date().isoformat(),
                         窗口依据="97天任务窗", 需求外推="不额外外推",
                         首批到仓=(DECISION + pd.Timedelta(days=lead)).date().isoformat(),
                         第二批到仓="", 第二批晚于覆盖终点=False,
                         建议运输=mode,
                         无断货概率=round(ns, 4) if ns is not None else None,
                         满足率=round(fill, 4) if fill is not None else None,
                         需求sigma=round(sigma, 2),
                         需求异常=(demand_flag != "" or sigma > 2.0),
                         需求异常类型=demand_flag, 状态=st))
        if demand_flag:
            sens_rows.append(dict(类型="新增", product_id=r["product_id"], 池=r["pool"],
                                  形态=r["physical_form"], UOM=r["canonical_uom"],
                                  数量=qty, 评估天数=H_SENS, 无断货概率=None,
                                  满足率=None, 状态=st))
        else:
            ns2, fill2, _ = simulate(key_rng(key + ("new", "s180")), H_SENS, d50, d95, on_hand,
                                     receipts, [(lead, qty)])
            sens_rows.append(dict(类型="新增", product_id=r["product_id"], 池=r["pool"],
                                  形态=r["physical_form"], UOM=r["canonical_uom"],
                                  数量=qty, 评估天数=H_SENS, 无断货概率=round(ns2, 4),
                                  满足率=round(fill2, 4), 状态=status_of(ns2, fill2, sigma)))
            for day, md, ms, msh in daily:
                daily_rows.append(dict(类型="新增", product_id=r["product_id"], 池=r["pool"],
                                       形态=r["physical_form"], UOM=r["canonical_uom"],
                                       日序=day + 1,
                                       日期=(DECISION + pd.Timedelta(days=day)).date().isoformat(),
                                       日均需求=round(md, 4), 日均库存=round(ms, 4),
                                       日均缺口=round(msh, 4)))

    rescue_rows = []
    for _, r in cny.iterrows():
        if str(r.get("风险状态", "")) != "选定方案失败-有补救候选":
            continue
        d50, d95, on_hand, receipts, sigma, demand_flag = prep(r)
        if demand_flag:
            continue
        mode = str(r["可换运输"])
        days = MODE_DAYS.get(mode, 30)
        prod = prod_map.get(str(r["pool"]), 30.0)
        lead = prod + PREHAUL_DAYS + days + SHELVING_DAYS
        arr = DECISION + pd.Timedelta(days=lead)
        q1 = int(r["首批数量"]); q2 = int(r["第二批数量"])
        arr2 = pd.to_datetime(r.get("第二批到仓"), errors="coerce")
        if pd.isna(arr2):
            arr2 = arr
        cov = pd.to_datetime(r["覆盖终点"], errors="coerce")
        Hh = max(90, int((cov - DECISION).days) + 7) if pd.notna(cov) else 97
        d1 = max(0, int((arr - DECISION).days)); d2 = max(0, int((arr2 - DECISION).days))
        key = (r["product_id"], r["pool"], r["physical_form"], r["canonical_uom"])
        ns, fill, _ = simulate(key_rng(key + ("rescue",)), Hh, d50, d95, on_hand,
                               receipts, [(d1, q1), (d2, q2)])
        second_order = pd.to_datetime(r.get("最迟下单日"), errors="coerce")
        past_second = bool(pd.notna(second_order) and second_order < DECISION)
        sim_status = status_of(ns, fill, sigma)
        rescue_rows.append(dict(
            product_id=r["product_id"], 池=r["pool"], 形态=r["physical_form"],
            UOM=r["canonical_uom"], 数量=q1 + q2,
            首批数量=q1, 第二批数量=q2,
            首批运输=mode, 第二批运输=r["建议运输"],
            原运输=r["建议运输"], 原首批到仓=r["首批到仓"],
            原第二批到仓=r.get("第二批到仓", ""),
            补救运输=mode, 补救首批到仓=arr.date().isoformat(),
            补救第二批到仓=arr2.date().isoformat() if hasattr(arr2, "date") else str(arr2),
            首批下单日=DECISION.date().isoformat(),
            第二批下单日=r.get("最迟下单日", ""),
            第二批下单日已过=past_second,
            运输方案=f"首批{mode}；第二批{r['建议运输']}",
            无断货概率=round(ns, 4), 满足率=round(fill, 4),
            状态=sim_status,
            可执行补救状态=("阻塞-第二批下单日已过" if past_second else sim_status)))
    rescue = pd.DataFrame(rescue_rows)

    out = pd.DataFrame(rows)
    sens = pd.DataFrame(sens_rows)
    detail = pd.DataFrame(daily_rows)
    summary = out.groupby(["类型", "状态"]).agg(
        键数=("product_id", "size"), 数量=("数量", "sum")).reset_index()
    sens_summary = sens.groupby(["类型", "状态"]).agg(
        键数=("product_id", "size"), 数量=("数量", "sum")).reset_index()
    params = pd.DataFrame([
        ("决策日", DECISION.date().isoformat()),
        ("随机种子", SEED),
        ("每次抽样", N),
        ("pre-haul 天数", PREHAUL_DAYS),
        ("上架天数", SHELVING_DAYS),
        ("主评估窗口", "春节=到覆盖终点+7天；新增=97天任务窗"),
        ("同窗口敏感性", f"两者都按 {H_SENS} 天重跑"),
        ("需求", "D5 v6.7 97天 p50/q95 转日均；Dirichlet 分日"),
        ("零中位数", "p50=0 且 q95>0：标“模型异常-零中位数”，不模拟、不进候选"),
        ("无需求", "p50=0 且 q95=0：标“无需求-不判定”"),
        ("整数批次", "春节首批取整，第二批=总量-首批；轨迹直接用批次数量"),
        ("运输补救", "选定方案晚于断货日、但更快运输可赶上的键，单独重模拟；不直接解禁"),
        ("到货", "C可发 + EN在途/待发 + PO追加 + CG；首批/第二批按生产+prehaul+运输+上架"),
        ("输入D5", sha(D5)), ("输入春节", sha(CNY)), ("输入D6", sha(D6)),
        ("脚本", "scripts/s2_22_trajectory_v8_20261109.py"),
    ], columns=["项", "值"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        params.to_excel(w, sheet_name="0_参数", index=False)
        summary.to_excel(w, sheet_name="1_汇总", index=False)
        out.to_excel(w, sheet_name="2_逐键", index=False)
        rescue.to_excel(w, sheet_name="3_运输补救", index=False)
        sens_summary.to_excel(w, sheet_name="3_同窗口180_汇总", index=False)
        sens.to_excel(w, sheet_name="3b_同窗口180_逐键", index=False)
        detail.to_excel(w, sheet_name="4_逐日均值", index=False)
    print(summary.to_string(index=False))
    print("\n[180天同窗]\n" + sens_summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
