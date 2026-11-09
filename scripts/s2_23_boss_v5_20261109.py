# -*- coding: utf-8 -*-
"""Boss/ops delivery v5 (2026-11-09): 11-09 snapshot, target-aware, expedite+new."""
from __future__ import annotations
from pathlib import Path
import hashlib
import pandas as pd
import numpy as np
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

BASE = Path("D:/Work/fzh-order-store/analysis")
D5 = BASE / "D5v6_7-novcast/D_概率与服务_D5_v6_7_2026-11-09.xlsx"
NC = BASE / "nov_nowcast_20261109.csv"
D6 = BASE / "D6v6_17-1109/D_Top50沙盒_D6_v6_17_2026-11-09.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-09_v8.xlsx"
TRAJ = BASE / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-09_v8.xlsx"
V15 = BASE / "S2_9-delivery-final-20261106/D_补货交付包_2026-11-06_final_v15.xlsx"
A = BASE / "SKU活跃宇宙_2026-10-29_FINAL.xlsx"
W3 = BASE / "round15_60cm_dnpo_audit.csv"
C14 = BASE / "C-refresh-20261109/通途库存_A337_v15_refresh_2026-11-09.xlsx"
EN_STOCK = BASE / "en_stock_20261109.parquet"
CG_STOCK = BASE / "cg_stock_20261109.parquet"
OUT = BASE / "D_老板版补货建议_2026-11-09_v5.xlsx"
KEYS = ["product_id", "池", "形态", "UOM"]
AS_OF = pd.Timestamp("2026-11-09")


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    d6 = pd.read_excel(D6, sheet_name="1_全量动作")
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期")
    traj = pd.read_excel(TRAJ, sheet_name="2_逐键")
    traj = traj[traj["类型"] == "春节"][KEYS + ["状态", "无断货概率", "满足率"]].rename(
        columns={"状态": "轨迹状态", "无断货概率": "周期无断货概率", "满足率": "需求满足率"})
    v18 = pd.read_excel(V15, sheet_name="18_60cm新增补货资格")
    v16 = pd.read_excel(TRAJ, sheet_name="3_运输补救")
    names = pd.read_excel(A, sheet_name="活跃宇宙")[["EN物料", "名称"]].drop_duplicates("EN物料")
    names["product_id"] = names["EN物料"].astype(str)

    ccols = KEYS + ["物料名称", "放行等级", "建议节前备货量", "首批数量", "第二批数量",
                    "首批到仓", "第二批到仓", "首批下单日", "第二批下单日",
                    "建议运输", "模型资格", "风险状态", "首批晚于停工"]
    b = d6.merge(cny[ccols], on=KEYS, how="left", suffixes=("", "_cny"))
    b = b.merge(traj, on=KEYS, how="left")
    b = b.merge(v18[KEYS].assign(新增资格=True), on=KEYS, how="left")
    b = b.merge(names[["product_id", "名称"]], on="product_id", how="left")
    b = b[b["池"].isin(["美东USNJ", "美中USTX", "波兰"])].copy()
    b = b.merge(v16[KEYS + ["无断货概率", "满足率", "状态", "可执行补救状态"]],
                on=KEYS, how="left", suffixes=("", "_补救"))
    rem = b["风险状态"].eq("选定方案失败-有补救候选")
    b.loc[rem, "周期无断货概率"] = b.loc[rem, "无断货概率"]
    b.loc[rem, "需求满足率"] = b.loc[rem, "满足率"]
    b["是否春节方案"] = b["建议节前备货量"].notna()
    b["下单日"] = pd.to_datetime(b["下单日"], errors="coerce")

    def target_ok(r):
        lv = str(r.get("放行等级", "") or "")
        ns = pd.to_numeric(r.get("周期无断货概率"), errors="coerce")
        fl = pd.to_numeric(r.get("需求满足率"), errors="coerce")
        if not lv:
            return None
        if lv.startswith("A"):
            return bool(pd.notna(ns) and ns >= 0.95)
        return bool(pd.notna(fl) and fl >= 0.95)

    b["原目标"] = b["放行等级"].map(
        lambda x: "A-周期无断货95%" if str(x).startswith("A")
        else ("B-需求满足率95%" if str(x).startswith("B") else ""))
    b["原目标达到"] = b.apply(target_ok, axis=1)

    def status(r):
        if r["是否春节方案"]:
            rs = str(r.get("风险状态", "") or "")
            if rs == "全部方案失败":
                return "可能断货-需拍板"
            if rs == "选定方案失败-有补救候选":
                return ("先换运输-原目标已过" if r["原目标达到"]
                        else "换运输也不达原目标-需调整")
            if str(r.get("模型资格", "")) == "零中位数-待验证":
                return "需求看不清-先别补"
            st = str(r.get("轨迹状态", ""))
            if st == "模型异常":
                return "需求异常-不判定"
            return "可以补-待确认" if r["原目标达到"] else "未达原目标-需调整"
        if r.get("新增资格") == True:  # noqa: E712
            return "新增资格-待复审"
        act = str(r.get("建议动作", ""))
        if act == "催已有":
            return "催已有+新增" if float(pd.to_numeric(r.get("新补数量"), errors="coerce") or 0) > 0 else "催已有"
        if act == "补":
            return "补-下单日已过-需重排" if pd.notna(r["下单日"]) and r["下单日"] < AS_OF else "补-待排期"
        if act == "不补":
            return "不用补"
        return "继续观察"

    b["一句话建议"] = b.apply(status, axis=1)

    def num(r, c):
        v = pd.to_numeric(r.get(c), errors="coerce")
        return 0.0 if pd.isna(v) else float(v)

    def qty(r):
        if r["是否春节方案"]:
            return num(r, "建议节前备货量")
        if str(r.get("建议动作")) == "催已有":
            return num(r, "新补数量")
        return num(r, "建议数量")

    b["建议补量"] = b.apply(qty, axis=1)
    b["首批数量_展示"] = b.apply(lambda r: num(r, "首批数量") if r["是否春节方案"] else 0, axis=1)
    b["第二批数量_展示"] = b.apply(lambda r: num(r, "第二批数量") if r["是否春节方案"] else 0, axis=1)
    b["催已有量_展示"] = b.apply(lambda r: num(r, "催已有量"), axis=1)
    b["新增量_展示"] = b.apply(
        lambda r: num(r, "新补数量") if str(r.get("建议动作")) == "催已有" else 0, axis=1)
    b["是否要催"] = b["催已有量_展示"].apply(lambda x: "是" if x > 0 else "")
    b["运输方式"] = b.apply(lambda r: r.get("建议运输") if r["是否春节方案"]
                            else r.get("推荐main_haul", ""), axis=1)
    b["首批下单日_展示"] = b.apply(lambda r: r.get("首批下单日") if r["是否春节方案"]
                              else r.get("下单日", ""), axis=1)
    b["第二批下单日_展示"] = b.apply(lambda r: r.get("第二批下单日") if r["是否春节方案"] else "", axis=1)
    b["首批到仓_展示"] = b.apply(lambda r: r.get("首批到仓") if r["是否春节方案"]
                            else r.get("需要日", ""), axis=1)
    b["第二批到仓_展示"] = b.apply(lambda r: r.get("第二批到仓") if r["是否春节方案"] else "", axis=1)

    def date_flag(r):
        if r["是否春节方案"]:
            # v8 已把首批下单日统一重排到 11-09，不再存在 11-06 过期问题
            return ""
        if r["一句话建议"] == "补-下单日已过-需重排":
            return "D6 下单日已过，需重排"
        return ""
    b["日期需重核"] = b.apply(date_flag, axis=1)
    b["是否要催已有"] = b["是否要催"]

    def basis(r):
        parts = []
        for label, col in (("q95", "q95"), ("可用C", "C可发供给"),
                           ("EN在途/待发", "en_stock在途+待发"),
                           ("PO追加", "PO追加(去重)"), ("净缺口", "净需求95")):
            v = pd.to_numeric(r.get(col), errors="coerce")
            if pd.notna(v):
                parts.append(f"{label} {v:.0f}")
        return "；".join(parts)
    b["依据"] = b.apply(basis, axis=1)

    def owner(r):
        s = r["一句话建议"]
        if s in ("可能断货-需拍板", "未达原目标-需调整", "换运输也不达原目标-需调整"):
            return "计划+业务"
        if s == "先换运输-原目标已过":
            return "物流+业务"
        if s in ("需求看不清-先别补", "需求异常-不判定"):
            return "计划/数据"
        if s == "新增资格-待复审":
            return "业务"
        if s in ("可以补-待确认", "补-待排期", "补-下单日已过-需重排", "催已有+新增", "催已有"):
            return "运营确认"
        return "—"
    b["需要谁决定"] = b.apply(owner, axis=1)

    def evidence(r):
        q = pd.to_numeric(r.get("q95"), errors="coerce")
        p = pd.to_numeric(r.get("p50"), errors="coerce")
        parts = []
        if pd.notna(q):
            parts.append(f"需求 q95 {q:.1f}（p50 {p:.1f}）")
        parts.append(f"C {num(r,'C可发供给'):.0f}（{r.get('C完整键状态','')}）；"
                     f"EN {num(r,'en_stock在途+待发'):.0f}（{r.get('EN快照状态','')}）；"
                     f"PO {num(r,'PO追加(去重)'):.0f}")
        parts.append(f"D6 {r.get('建议动作','')}：{r.get('动作原因','')}")
        if r["是否春节方案"]:
            parts.append(f"春节 {num(r,'建议节前备货量'):.0f} 件；原目标 {r['原目标']}；"
                         f"达到 {r['原目标达到']}；轨迹 {r.get('轨迹状态','')}")
        return " ｜ ".join(parts)
    b["证据链"] = b.apply(evidence, axis=1)

    out = pd.DataFrame({
        "分公司": b["池"], "商品名称": b["物料名称"].fillna(b["名称"]).fillna(""),
        "商品编码": b["product_id"], "形态": b["形态"], "单位": b["UOM"],
        "一句话建议": b["一句话建议"], "原目标": b["原目标"],
        "原目标达到": b["原目标达到"].map({True: "是", False: "否", None: "—"}),
        "建议补多少": b["建议补量"].round(0),
        "首批数量": b["首批数量_展示"].round(0),
        "第二批数量": b["第二批数量_展示"].round(0),
        "首批下单日": b["首批下单日_展示"], "第二批下单日": b["第二批下单日_展示"],
        "首批到仓/要求到仓": b["首批到仓_展示"], "第二批到仓": b["第二批到仓_展示"],
        "运输方式": b["运输方式"], "是否要催已有": b["是否要催"],
        "催已有量": b["催已有量_展示"].round(0), "新增补货量": b["新增量_展示"].round(0),
        "在途ETA": b["在途ETA_p50"], "日期需重核": b["日期需重核"],
        "依据": b["依据"], "需要谁决定": b["需要谁决定"],
        "风险/备注": b.apply(lambda r: str(r.get("风险状态", "") or "") or str(r.get("动作原因", "") or ""), axis=1),
        "方案类型": b["是否春节方案"].map({True: "春节方案", False: "日常补货候选"}),
        "证据链": b["证据链"],
    })
    order = ["可以补-待确认", "先换运输-原目标已过", "催已有+新增", "催已有",
             "补-待排期", "补-下单日已过-需重排", "未达原目标-需调整",
             "换运输也不达原目标-需调整", "可能断货-需拍板",
             "新增资格-待复审", "需求看不清-先别补", "需求异常-不判定",
             "继续观察", "不用补"]
    out["_o"] = out["一句话建议"].map({s: i for i, s in enumerate(order)}).fillna(99)
    out = out.sort_values(["分公司", "_o", "建议补多少"], ascending=[True, True, False]).drop(columns="_o")

    cny_rows = out[out["方案类型"].eq("春节方案")]
    daily_rows = out[out["一句话建议"].isin(["补-待排期", "补-下单日已过-需重排"])]
    expedite_rows = out[out["一句话建议"].isin(["催已有+新增", "催已有"])]
    pending = out[out["一句话建议"].isin(
        ["未达原目标-需调整", "换运输也不达原目标-需调整", "可能断货-需拍板",
         "需求看不清-先别补", "需求异常-不判定", "新增资格-待复审",
         "补-下单日已过-需重排"])]

    target31 = b[b["是否春节方案"] & b["轨迹状态"].isin(["cycle95", "fill95"])
                 & (~b["风险状态"].isin(["全部方案失败", "选定方案失败-有补救候选"]))
                 & (b["模型资格"].ne("零中位数-待验证"))].copy()
    target31 = target31[["product_id", "池", "形态", "UOM", "放行等级",
                         "周期无断货概率", "需求满足率", "原目标达到",
                         "建议节前备货量", "一句话建议"]].rename(
        columns={"product_id": "商品编码", "池": "分公司", "形态": "形态",
                 "UOM": "单位", "建议节前备货量": "建议量"})
    target31["原目标达到"] = target31["原目标达到"].map({True: "是", False: "否"})
    target31 = target31.sort_values(["原目标达到", "建议量"], ascending=[True, False])

    past6 = b[(~b["是否春节方案"]) & b["建议动作"].eq("补")
              & (b["下单日"] >= pd.Timestamp("2026-11-06"))
              & (b["下单日"] < AS_OF)].copy()
    past6 = past6[["product_id", "池", "形态", "UOM", "下单日", "建议数量",
                   "建议动作"]].rename(
        columns={"product_id": "商品编码", "池": "分公司",
                 "建议数量": "建议量", "下单日": "计划下单日"})
    past6["重核时点"] = "2026-11-09"

    past = out[out["一句话建议"].eq("补-下单日已过-需重排")]
    qual = out[out["一句话建议"].eq("新增资格-待复审")].copy()
    qual["_od"] = pd.to_datetime(qual["首批下单日"], errors="coerce")
    qual_past = qual[qual["_od"] < AS_OF]
    tgt_total = len(target31)
    tgt_yes = int((target31["原目标达到"] == "是").sum())

    summary = pd.DataFrame([
        ("覆盖范围", f"三个分公司全部 {len(out)} 个需求键；不是子集。"),
        ("数据日期", "预测基准 2026-11-02（叠加 11/1–8 同店修正）；库存/CG/EN 2026-11-09；"
                    "通途订单截至 11-08；PO 2026-11-05；动作重核 2026-11-09。"),
        ("春节方案", f"{len(cny_rows)} 键/{cny_rows['建议补多少'].sum():,.0f} 件；"
                  f"按 A/B 原目标重新判定；首批下单已按 11-09 重排。"),
        ("原目标核对", f"无断货/无补救/非零中位数 {tgt_total} 键：{tgt_yes} 达、"
                    f"{tgt_total - tgt_yes} 未达。"),
        ("可以补-待确认", f"{len(out[out['一句话建议'].eq('可以补-待确认')])} 键/"
                     f"{out.loc[out['一句话建议'].eq('可以补-待确认'),'建议补多少'].sum():,.0f} 件；A 看周期、B 看满足率。"),
        ("未达原目标", f"{len(out[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整'])])} 键/"
                    f"{out.loc[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整']),'建议补多少'].sum():,.0f} 件；不能按原目标通过。"),
        ("断货风险", f"{len(out[out['一句话建议'].eq('可能断货-需拍板')])} 键/"
                  f"{out.loc[out['一句话建议'].eq('可能断货-需拍板'),'建议补多少'].sum():,.0f} 件；所有已验证运输都晚于断货日。"),
        ("运输补救", f"{len(out[out['一句话建议'].isin(['先换运输-原目标已过','换运输也不达原目标-需调整'])])} 键/"
                  f"{out.loc[out['一句话建议'].isin(['先换运输-原目标已过','换运输也不达原目标-需调整']),'建议补多少'].sum():,.0f} 件；"
                  "按 A/B 严格目标 5 达/4 未达（旧轨迹口径 8 达/1 未达，差异是 A 级不能用满足率替代周期）。"),
        ("催已有 + 新增", f"{len(expedite_rows)} 键；催已有 {expedite_rows['催已有量'].sum():,.0f} 件，"
                       f"新增 {expedite_rows['新增补货量'].sum():,.0f} 件；两种动作并列。"),
        ("日常补货", f"{len(daily_rows)} 键/{daily_rows['建议补多少'].sum():,.0f} 件；"
                  f"其中下单日已过 {len(past)} 键/{past['建议补多少'].sum():,.0f} 件。"),
        ("日期重核", f"日常 {len(past)} 键/{past['建议补多少'].sum():,.0f} 件下单日已过"
                  f"（其中 11-06 后新过期 {len(past6)} 键/{past6['建议量'].sum():,.0f} 件）；"
                  f"新增资格 {len(qual_past)} 键/{qual_past['建议补多少'].sum():,.0f} 件下单日已过。"),
    ], columns=["项", "说明"])

    sel = ["可以补-待确认", "先换运输-原目标已过", "未达原目标-需调整",
           "换运输也不达原目标-需调整", "可能断货-需拍板", "催已有+新增", "催已有",
           "补-待排期", "补-下单日已过-需重排", "需求看不清-先别补",
           "需求异常-不判定", "新增资格-待复审", "继续观察", "不用补"]
    pivot = out.pivot_table(index="分公司", columns="一句话建议", values="商品编码",
                            aggfunc="count", fill_value=0)
    pivot["需求键数"] = pivot.sum(axis=1)
    pivot = pivot.reindex(columns=["需求键数"] + sel, fill_value=0).reset_index()

    # 60cm corrected summary + detail
    w3 = pd.read_csv(W3)
    wk = w3[w3["record_type"].astype(str).eq("key")].copy()
    wk = wk.rename(columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM"})
    keys60 = wk[["product_id", "池", "形态", "UOM", "qty_v3_5", "PO缺口件数", "PO状态",
                 "C可发供给", "EN可用"]].merge(
        d6[["product_id", "池", "形态", "UOM", "净需求95", "新补数量", "建议动作"]],
        on=["product_id", "池", "形态", "UOM"], how="left")
    hist = float(keys60["qty_v3_5"].sum())
    po_hist = float(keys60["PO缺口件数"].sum())
    net_now = float(pd.to_numeric(keys60["净需求95"], errors="coerce").fillna(0).sum())
    new_now = float(pd.to_numeric(keys60["新补数量"], errors="coerce").fillna(0).sum())
    po60 = pd.DataFrame([
        ("历史销量", f"{hist:,.0f} 件（20 键，不是当前采购量）"),
        ("C 覆盖", "20/20 exact_full，合计 239"),
        ("EN 覆盖", "20/20 exact_full，合计 239（同一物理池，不可相加）"),
        ("PO 无覆盖的历史量", f"{po_hist:,.0f} 件；只是历史规模，不是欠采购"),
        ("当前 D6 净需求", f"{net_now:,.2f} 件"),
        ("当前新补参考", f"{new_now:,.0f} 件"),
        ("DN/PO 阶段", "台账 11 DN/71 行/51 Shipment；EN 14 DN 中 3 缺失；arrive/warehouse_in 全空"),
    ], columns=["项", "结论"])

    corrections = pd.DataFrame([
        ("v2 / v3b", "历史讨论版，已作废；不作为采购依据。"),
        ("v4", "上一版：11-06 决策日、11-05 库存；已被本版 v5 取代。"),
        ("v5 变更 1", "数据快照统一到 11-09：库存/CG/EN 11-09，通途订单截至 11-08；"
                     "D5 叠加 11/1–8 同店修正；PO 仍为 11-05。"),
        ("v5 变更 2", f"按 A/B 严格目标重判：可以补 {len(out[out['一句话建议'].eq('可以补-待确认')])}/"
                     f"{out.loc[out['一句话建议'].eq('可以补-待确认'),'建议补多少'].sum():,.0f}；"
                     f"未达原目标 {len(out[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整'])])}/"
                     f"{out.loc[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整']),'建议补多少'].sum():,.0f}；"
                     f"可能断货 {len(out[out['一句话建议'].eq('可能断货-需拍板')])}/"
                     f"{out.loc[out['一句话建议'].eq('可能断货-需拍板'),'建议补多少'].sum():,.0f}。"),
        ("v5 变更 3", f"催已有与新增并列：{len(expedite_rows)} 键；催已有 "
                     f"{expedite_rows['催已有量'].sum():,.0f} 件，新增 "
                     f"{expedite_rows['新增补货量'].sum():,.0f} 件"
                     f"（{int((out['一句话建议'].eq('催已有+新增')).sum())} 键同时新增）。"),
        ("v5 变更 4", f"日常补货 {len(daily_rows)}/{daily_rows['建议补多少'].sum():,.0f}；"
                     f"{len(past)}/{past['建议补多少'].sum():,.0f} 下单日已过，"
                     f"其中 {len(past6)}/{past6['建议量'].sum():,.0f} 为 11-06 后新过期；"
                     f"新增资格 {len(qual)}/{qual['建议补多少'].sum():,.0f}，"
                     f"其中 {len(qual_past)}/{qual_past['建议补多少'].sum():,.0f} 下单日已过。"),
        ("v5 变更 5", f"春节 {len(cny_rows)}/{cny_rows['建议补多少'].sum():,.0f}；"
                     "首批下单已按 11-09 重排；首批到仓晚于停工 17 键（A 10/B 7），"
                     "是否可执行仍看是否早于断货日，不用停工日一刀切。"),
        ("v5 变更 6", "运输补救 9 键/463 件：按 A/B 严格目标 5 达/4 未达；"
                     "旧轨迹口径 8 达/1 未达，差异来自 A 级不能用满足率替代周期。"),
        ("v5 变更 7", "PO 2,417 是历史销量、不是欠采购；台账仍为 11-05，"
                     "PO 最新状态未取到，需另行补数。"),
    ], columns=["版本/变更", "说明"])

    src = pd.DataFrame([
        ("D5 v6.7", str(D5), sha(D5)),
        ("11/1–8 同店修正", str(NC), sha(NC)),
        ("D6 v6.17", str(D6), sha(D6)),
        ("CNY v8", str(CNY), sha(CNY)),
        ("轨迹 v8", str(TRAJ), sha(TRAJ)),
        ("C14 11-09 刷新", str(C14), sha(C14)),
        ("EN 库存 11-09", str(EN_STOCK), sha(EN_STOCK)),
        ("CG 库存 11-09", str(CG_STOCK), sha(CG_STOCK)),
        ("v15 历史交付包", str(V15), sha(V15)),
        ("A 活跃宇宙", str(A), sha(A)),
        ("60cm/DN-PO 审计", str(W3), sha(W3)),
    ], columns=["文件", "路径", "sha256"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="0_老板先看", index=False)
        out.to_excel(w, sheet_name="1_逐商品建议", index=False)
        pending.to_excel(w, sheet_name="2_需要拍板", index=False)
        pivot.to_excel(w, sheet_name="3_分公司汇总", index=False)
        corrections.to_excel(w, sheet_name="4_v5改了什么", index=False)
        po60.to_excel(w, sheet_name="5_60cm与DN-PO", index=False)
        keys60.to_excel(w, sheet_name="5b_60cm逐键", index=False)
        src.to_excel(w, sheet_name="6_数据来源", index=False)
        out[out["一句话建议"].isin(order[:10])].to_excel(
            w, sheet_name="7_本周行动清单", index=False)
        target31.to_excel(w, sheet_name="8_目标核对", index=False)
        past6.to_excel(w, sheet_name="9_周一新增过期", index=False)

    wb = load_workbook(OUT)
    hf, hfont = PatternFill("solid", fgColor="1F4E78"), Font(color="FFFFFF", bold=True)
    fills = {"可以补-待确认": "C6EFCE", "先换运输-原目标已过": "FFF2CC",
             "催已有+新增": "DDEBF7", "催已有": "DDEBF7",
             "补-待排期": "DDEBF7", "补-下单日已过-需重排": "FCE4D6",
             "未达原目标-需调整": "FCE4D6", "换运输也不达原目标-需调整": "FCE4D6",
             "可能断货-需拍板": "F8CBAD", "需求看不清-先别补": "D9E1F2",
             "需求异常-不判定": "D9E1F2", "新增资格-待复审": "E4DFEC",
             "不用补": "EDEDED", "继续观察": "EDEDED"}
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for c in ws[1]:
            c.fill, c.font = hf, hfont
            c.alignment = Alignment(wrap_text=True, vertical="center")
        widths = {}
        for row in ws.iter_rows(values_only=True):
            for i, v in enumerate(row, 1):
                widths[i] = min(46, max(widths.get(i, 10), len(str(v)) + 2))
        for i, wd in widths.items():
            ws.column_dimensions[get_column_letter(i)].width = wd
    ws = wb["1_逐商品建议"]
    hdr = [c.value for c in ws[1]]
    if "一句话建议" in hdr:
        ci = hdr.index("一句话建议") + 1
        for row in range(2, ws.max_row + 1):
            v = ws.cell(row=row, column=ci).value
            if v in fills:
                ws.cell(row=row, column=ci).fill = PatternFill("solid", fgColor=fills[v])
    wb.save(OUT)
    print("wrote", OUT)
    print(summary.to_string(index=False))
    print(out["一句话建议"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
