# -*- coding: utf-8 -*-
"""CNY schedule v9: integer batches + pre-haul 2 + shutdown-safe production calendar.

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
D5 = BASE / "D5v6_7-novcast/D_概率与服务_D5_v6_7_2026-11-09.xlsx"
D6 = BASE / "D6v6_19-1110/D_Top50沙盒_D6_v6_19_2026-11-10.xlsx"
V6 = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v6.xlsx"
OUT = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-10_v10.xlsx"
DECISION = pd.Timestamp("2026-11-10")
JAN24 = pd.Timestamp("2027-01-24")
RESTART = pd.Timestamp("2027-02-22")
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
        prod = PROD.get(pool, 30.0)
        days = MODE_DAYS.get(mode, 30)
        trans = PREHAUL + days
        lead = prod + trans
        first_arr = DECISION + pd.Timedelta(days=lead)
        first_prod_finish = DECISION + pd.Timedelta(days=prod)

        # 第二批必须避开 2027-01-24 ~ 2027-02-22 工厂停工。
        # 方案 A（可执行）：若按 2/22 倒推会在停工期内生产，则改为停工前做完，
        # 下单日 = 1/24 - 生产天数；到仓 = max(2/22, 1/24 + 运输天数)。
        # 方案 B（风险情景）：不在停工前插单，2/22 复工后才生产，到仓顺延。
        finish_for_restart = RESTART - pd.Timedelta(days=trans)
        early_needed = bool(finish_for_restart > JAN24)
        if early_needed:
            second_order = JAN24 - pd.Timedelta(days=prod)
            second_prod_finish = JAN24
            second_arr = max(RESTART, JAN24 + pd.Timedelta(days=trans))
        else:
            second_order = finish_for_restart - pd.Timedelta(days=prod)
            second_prod_finish = finish_for_restart
            second_arr = RESTART
        # 方案 B：不提前插单，仍按原连续排期下单；1/24 停工、2/22 复工后
        # 只补完剩余生产天数，再加运输。不是 2/22 重新从头生产。
        orig_order_b = RESTART - pd.Timedelta(days=lead)
        worked_before_shutdown = max(0.0, (JAN24 - orig_order_b).days)
        remaining_prod = max(0.0, prod - worked_before_shutdown)
        second_order_b = orig_order_b
        second_prod_finish_b = RESTART + pd.Timedelta(days=remaining_prod)
        second_arr_b = second_prod_finish_b + pd.Timedelta(days=trans)
        cutoff = second_order
        if first_prod_finish > JAN24 and first_prod_finish < RESTART:
            raise ValueError(f"首批生产跨停工：{r['product_id']} {pool} {first_prod_finish.date()}")
        if second_prod_finish > JAN24 and second_prod_finish < RESTART:
            raise ValueError(f"第二批生产跨停工：{r['product_id']} {pool} {second_prod_finish.date()}")
        stockout = (DECISION + pd.Timedelta(days=int(c / daily))
                    if daily > 0 and c > 0 else DECISION)
        alt = []
        for alt_mode in ("空运", "快船", "普船"):
            alt_arr = DECISION + pd.Timedelta(days=prod + PREHAUL + MODE_DAYS[alt_mode])
            if alt_arr <= stockout:
                alt.append((alt_mode, alt_arr))
        if zero_median or first_arr <= stockout:
            risk_state, remedy_mode, remedy_arr = "", "", ""
        elif alt:
            risk_state = "选定方案失败-有补救候选"
            remedy_mode, _ra = min(alt, key=lambda x: x[1])
            remedy_arr = _ra.date().isoformat()
        else:
            risk_state, remedy_mode, remedy_arr = "全部方案失败", "", ""
        rows.append(dict(
            product_id=r["product_id"], 物料名称=r.get("物料名称", ""),
            **{"通途SKU/来源码（不含FBA）": r.get("通途SKU/来源码（不含FBA）", "")},
            池=pool, 形态=r["形态"], UOM=r["UOM"], 放行等级=level,
            日均q95需求=round(daily, 4), 当前可用=round(c, 2),
            预计q95断货日=stockout.date().isoformat(), 建议运输=mode,
            首批到仓=first_arr.date().isoformat(),
            首批生产完成=first_prod_finish.date().isoformat(),
            第二批到仓=second_arr.date().isoformat(),
            第二批生产开始=second_order.date().isoformat(),
            第二批生产完成=second_prod_finish.date().isoformat(),
            第二批需停工前插单=early_needed,
            第二批停工后到仓=second_arr_b.date().isoformat(),
            覆盖终点=r["覆盖终点"],
            建议节前备货量=total, 首批数量=first, 第二批数量=second,
            最迟下单日=cutoff.date().isoformat(), 风险=risk_state,
            首批下单日=DECISION.date().isoformat(),
            第二批下单日=second_order.date().isoformat(),
            第二批下单日_停工后=second_order_b.date().isoformat(),
            首批晚于停工=bool(first_arr > JAN24),
            风险状态=risk_state, 可换运输=remedy_mode, 补救最快到仓=remedy_arr,
            模型资格="零中位数-待验证" if zero_median else "正常",
            建议量状态="待核" if zero_median else "已计算",
            执行闸门="禁止执行" if zero_median else "待人工确认",
            批准量=0,
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
        ("首批晚于断货日", int((out["风险状态"] != "").sum())),
        ("可换运输-待重模拟", int((out["风险状态"] == "选定方案失败-有补救候选").sum())),
        ("全部方案失败", int((out["风险状态"] == "全部方案失败").sum())),
        ("零中位数待验证行", int((out["模型资格"] == "零中位数-待验证").sum())),
        ("第二批需停工前插单", int(out["第二批需停工前插单"].sum())),
        ("第二批需停工前插单件数", int(out.loc[out["第二批需停工前插单"], "第二批数量"].sum())),
        ("第二批提前排产最早下单日",
         str(out.loc[out["第二批需停工前插单"], "第二批下单日"].min())),
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
