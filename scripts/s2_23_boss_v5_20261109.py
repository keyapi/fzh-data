# -*- coding: utf-8 -*-
"""Boss/ops delivery v5.1 (2026-11-09): corrected quantiles, shutdown-safe schedule, remedy-bound plan."""
from __future__ import annotations
from pathlib import Path
import hashlib
import math
import pandas as pd
import numpy as np
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

BASE = Path("D:/Work/fzh-order-store/analysis")
D5 = BASE / "D5v6_7-novcast/D_概率与服务_D5_v6_7_2026-11-09.xlsx"
NC = BASE / "nov_nowcast_20261109.csv"
D6 = BASE / "D6v6_18-1109/D_Top50沙盒_D6_v6_18_2026-11-09.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-09_v9.xlsx"
TRAJ = BASE / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-09_v9.xlsx"
V15 = BASE / "S2_9-delivery-final-20261106/D_补货交付包_2026-11-06_final_v15.xlsx"
A = BASE / "SKU活跃宇宙_2026-10-29_FINAL.xlsx"
W3 = BASE / "round15_60cm_dnpo_audit.csv"
C14 = BASE / "C-refresh-20261109/通途库存_A337_v15_refresh_2026-11-09.xlsx"
EN_STOCK = BASE / "en_stock_20261109.parquet"
CG_STOCK = BASE / "cg_stock_20261109.parquet"
D2B = BASE / "D_删失需求估计_D2b_v2_2026-11-02.xlsx"
OUT = BASE / "D_老板版补货建议_2026-11-09_v5.1.xlsx"
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
                    "建议运输", "模型资格", "风险状态", "首批晚于停工",
                    "第二批需停工前插单", "第二批停工后到仓"]
    b = d6.merge(cny[ccols], on=KEYS, how="left", suffixes=("", "_cny"))
    b = b.merge(traj, on=KEYS, how="left")
    b = b.merge(v18[KEYS].assign(新增资格=True), on=KEYS, how="left")
    b = b.merge(names[["product_id", "名称"]], on="product_id", how="left")
    b = b[b["池"].isin(["美东USNJ", "美中USTX", "波兰"])].copy()
    b = b.merge(v16[KEYS + ["无断货概率", "满足率", "状态", "可执行补救状态",
                            "首批运输", "第二批运输", "补救首批到仓", "补救第二批到仓",
                            "首批下单日", "第二批下单日", "运输方案"]],
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

    def q0(r, c):
        return int(math.floor(num(r, c) + 0.5))

    def qty(r):
        if r["是否春节方案"]:
            return num(r, "建议节前备货量")
        if str(r.get("建议动作")) == "催已有":
            return num(r, "新补数量")
        return num(r, "建议数量")

    PROD_DAYS = {"美东USNJ": 30.0, "美中USTX": 35.2, "波兰": 43.6}
    MODE_DAYS = {"空运": 14, "快船": 30, "普船": 55, "专线": 60, "路线待确认": 50}

    def lead_days(r):
        mode = str(r.get("推荐main_haul", "")).replace("海运", "")
        return PROD_DAYS.get(str(r.get("池")), 30.0) + 2 + MODE_DAYS.get(mode, 50)

    def rem_pass(r):
        return bool(r["是否春节方案"]
                    and str(r.get("风险状态", "")) == "选定方案失败-有补救候选"
                    and r["原目标达到"])

    def first_transport(r):
        if r["是否春节方案"]:
            if rem_pass(r) and pd.notna(r.get("首批运输")):
                return str(r["首批运输"])
            return str(r.get("建议运输", ""))
        if str(r.get("建议动作")) == "催已有" and num(r, "新补数量") <= 0:
            return ""
        return str(r.get("推荐main_haul", ""))

    def second_transport(r):
        return str(r.get("建议运输", "")) if r["是否春节方案"] else ""

    def first_arrival(r):
        if r["是否春节方案"]:
            if rem_pass(r) and pd.notna(r.get("补救首批到仓")):
                return r["补救首批到仓"]
            return r.get("首批到仓", "")
        if str(r.get("建议动作")) == "补":
            if str(r.get("推荐main_haul", "")) == "路线待确认":
                return ""
            order = AS_OF if (pd.notna(r["下单日"]) and r["下单日"] < AS_OF) else r["下单日"]
            if pd.notna(order):
                return (pd.Timestamp(order) + pd.Timedelta(days=lead_days(r))).date().isoformat()
        if str(r.get("建议动作")) == "催已有":
            if num(r, "新补数量") <= 0:
                return ""
            if str(r.get("推荐main_haul", "")) == "路线待确认":
                return ""
            order = AS_OF
            if pd.notna(order):
                return (pd.Timestamp(order) + pd.Timedelta(days=lead_days(r))).date().isoformat()
        return r.get("需要日", "")

    def second_arrival(r):
        if not r["是否春节方案"]:
            return ""
        if rem_pass(r) and pd.notna(r.get("补救第二批到仓")):
            return r["补救第二批到仓"]
        return r.get("第二批到仓", "")

    def second_order(r):
        if not r["是否春节方案"]:
            return ""
        if rem_pass(r) and pd.notna(r.get("第二批下单日_补救")):
            return r["第二批下单日_补救"]
        return r.get("第二批下单日", "")

    def first_order(r):
        if r["是否春节方案"]:
            return "2026-11-09"
        if str(r.get("推荐main_haul", "")) == "路线待确认":
            return ""
        if str(r.get("建议动作")) == "催已有":
            return "2026-11-09" if num(r, "新补数量") > 0 else ""
        if pd.notna(r["下单日"]):
            return (AS_OF if r["下单日"] < AS_OF else r["下单日"]).date().isoformat() \
                if hasattr(r["下单日"], "date") else str(r["下单日"])
        return ""

    b["建议补量"] = b.apply(qty, axis=1)
    b["首批数量_展示"] = b.apply(
        lambda r: num(r, "首批数量") if r["是否春节方案"]
        else (num(r, "新补数量") if str(r.get("建议动作")) == "催已有" else num(r, "建议数量")), axis=1)
    b["第二批数量_展示"] = b.apply(lambda r: num(r, "第二批数量") if r["是否春节方案"] else 0, axis=1)
    b["催已有量_展示"] = b.apply(lambda r: num(r, "催已有量"), axis=1)
    b["新增量_展示"] = b.apply(
        lambda r: num(r, "新补数量") if str(r.get("建议动作")) == "催已有" else 0, axis=1)
    b["是否要催"] = b["催已有量_展示"].apply(lambda x: "是" if x > 0 else "")
    b["首批运输_展示"] = b.apply(first_transport, axis=1)
    b["第二批运输_展示"] = b.apply(second_transport, axis=1)
    b["首批下单日_展示"] = b.apply(first_order, axis=1)
    b["第二批下单日_展示"] = b.apply(second_order, axis=1)
    b["首批到仓_展示"] = b.apply(first_arrival, axis=1)
    b["第二批到仓_展示"] = b.apply(second_arrival, axis=1)
    b["要求到仓_展示"] = b.apply(
        lambda r: r.get("需要日", "") if not r["是否春节方案"] else r.get("覆盖终点", ""), axis=1)

    def reschedule(r):
        if r["是否春节方案"] or str(r.get("建议动作")) != "补":
            return ""
        if pd.isna(r["下单日"]) or r["下单日"] >= AS_OF:
            return ""
        need = pd.to_datetime(r.get("需要日"), errors="coerce")
        arr = pd.to_datetime(first_arrival(r), errors="coerce")
        if pd.notna(need) and pd.notna(arr):
            delta = int((arr - need).days)
            if delta <= 0:
                return f"原下单日已过；今天重下，预计 {arr.date()} 到仓，早于需要日 {-delta} 天"
            return f"原下单日已过；今天重下，预计 {arr.date()} 到仓，晚于需要日 {delta} 天，需空运或接受延后"
        return "原下单日已过；今天重下，到仓日待确认"
    b["重排结果"] = b.apply(reschedule, axis=1)

    def action(r):
        s = r["一句话建议"]
        if (not r["是否春节方案"]
                and str(r.get("推荐main_haul", "")) == "路线待确认"
                and s in ("补-待排期", "补-下单日已过-需重排", "催已有+新增", "催已有")):
            return "先确认路线"
        if s == "可以补-待确认":
            return "下单"
        if s == "先换运输-原目标已过":
            return "下单（首批改空运）"
        if s == "补-待排期":
            return "下单"
        if s == "补-下单日已过-需重排":
            return "今天重下"
        if s == "催已有+新增":
            return "催在途 + 下单"
        if s == "催已有":
            return "催在途"
        if s in ("可能断货-需拍板", "未达原目标-需调整", "换运输也不达原目标-需调整",
                 "需求看不清-先别补", "需求异常-不判定", "新增资格-待复审"):
            return "拍板"
        if s == "不用补":
            return "不下单"
        return "观察"
    b["动作"] = b.apply(action, axis=1)

    def priority(r):
        s = r["一句话建议"]
        if (not r["是否春节方案"]
                and str(r.get("推荐main_haul", "")) == "路线待确认"
                and s in ("补-待排期", "补-下单日已过-需重排", "催已有+新增", "催已有")):
            return "P0-先确认路线"
        if s in ("可以补-待确认", "先换运输-原目标已过", "补-下单日已过-需重排"):
            return "P1-本周必须"
        if s in ("催已有+新增", "催已有"):
            return "P1-本周必须"
        if s == "补-待排期":
            return "P2-可排期"
        if s in ("可能断货-需拍板", "未达原目标-需调整", "换运输也不达原目标-需调整",
                 "需求看不清-先别补", "需求异常-不判定", "新增资格-待复审"):
            return "P0-先拍板"
        return "P3-暂不处理"
    b["优先级"] = b.apply(priority, axis=1)

    def exec_plan(r):
        if (not r["是否春节方案"]
                and str(r.get("推荐main_haul", "")) == "路线待确认"):
            if str(r.get("建议动作")) == "催已有":
                return f"先催在途 {q0(r,'催已有量')} 件；新单等物流确认路线后再下"
            return "物流还没给出可用的运输路线；先确认运输方式和到仓日，不要按默认天数直接下单"
        if r["是否春节方案"]:
            if rem_pass(r):
                return (f"首批 {q0(r,'首批数量')} 件改空运，11-09 下单，"
                        f"{r.get('补救首批到仓','')} 到仓；第二批 {q0(r,'第二批数量')} 件"
                        f"仍走{str(r.get('建议运输',''))}，{r.get('第二批下单日','')} 前下单，"
                        f"{r.get('第二批到仓','')} 到仓")
            return (f"首批 {q0(r,'首批数量')} 件{str(r.get('建议运输',''))}，11-09 下单，"
                    f"{r.get('首批到仓','')} 到仓；第二批 {q0(r,'第二批数量')} 件，"
                    f"{r.get('第二批下单日','')} 前下单，{r.get('第二批到仓','')} 到仓")
        if str(r.get("建议动作")) == "催已有" and num(r, "新补数量") > 0:
            return (f"先催在途 {q0(r,'催已有量')} 件；同时新下 {q0(r,'新补数量')} 件"
                    f"（{str(r.get('推荐main_haul',''))}），今天下单")
        if str(r.get("建议动作")) == "催已有":
            return f"只催在途 {q0(r,'催已有量')} 件，不下新单"
        if str(r.get("建议动作")) == "补":
            return (f"下 {q0(r,'建议数量')} 件，{str(r.get('推荐main_haul',''))}，"
                    f"{first_order(r)} 下单，{first_arrival(r)} 到仓")
        return ""
    b["执行说明"] = b.apply(exec_plan, axis=1)

    def date_flag(r):
        if r["是否春节方案"]:
            if (bool(r.get("第二批需停工前插单", False))
                    and r["一句话建议"] in ("可以补-待确认", "先换运输-原目标已过")):
                return (f"第二批最晚 {r.get('第二批下单日','')} 前下单；"
                        f"不插单则 {r.get('第二批停工后到仓','')} 到仓，可能失去目标")
            return ""
        if r["一句话建议"] == "补-下单日已过-需重排":
            return r.get("重排结果", "")
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

    def plain_target(r):
        if str(r["放行等级"]).startswith("A"):
            return "A类：95%概率不断货"
        if str(r["放行等级"]).startswith("B"):
            return "B类：满足95%需求"
        return "—"
    b["业务目标"] = b.apply(plain_target, axis=1)
    b["目标结果"] = b.apply(
        lambda r: r["原目标达到"] if r["是否春节方案"] else None, axis=1
    ).map({True: "达到", False: "未达到", None: "—"})

    out = pd.DataFrame({
        "优先级": b["优先级"], "动作": b["动作"],
        "分公司": b["池"], "商品名称": b["物料名称"].fillna(b["名称"]).fillna(""),
        "商品编码": b["product_id"], "形态": b["形态"], "单位": b["UOM"],
        "业务目标": b["业务目标"], "目标结果": b["目标结果"],
        "一句话建议": b["一句话建议"],
        "建议补多少": b["建议补量"].round(0),
        "首批数量": b["首批数量_展示"].round(0),
        "首批运输": b["首批运输_展示"],
        "首批下单日": b["首批下单日_展示"],
        "首批到仓": b["首批到仓_展示"],
        "第二批数量": b["第二批数量_展示"].round(0),
        "第二批运输": b["第二批运输_展示"],
        "第二批下单日": b["第二批下单日_展示"],
        "第二批到仓": b["第二批到仓_展示"],
        "要求到仓/覆盖终点": b["要求到仓_展示"],
        "催已有量": b["催已有量_展示"].round(0),
        "新增补货量": b["新增量_展示"].round(0),
        "重排结果": b["重排结果"],
        "日期需重核": b["日期需重核"],
        "执行说明": b["执行说明"],
        "为什么": b["依据"],
        "谁决定": b["需要谁决定"],
        "风险/备注": b.apply(
            lambda r: str(r.get("风险状态", "") or "") or str(r.get("动作原因", "") or ""), axis=1),
        "方案类型": b["是否春节方案"].map({True: "春节方案", False: "日常补货"}),
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
    qual_mask = b["一句话建议"].eq("新增资格-待复审")
    qual = out[out["一句话建议"].eq("新增资格-待复审")].copy()
    qual_past = b[qual_mask & (b["下单日"] < AS_OF)]
    tgt_total = len(target31)
    tgt_yes = int((target31["原目标达到"] == "是").sum())
    rem_rows = out[out["一句话建议"].isin(
        ["先换运输-原目标已过", "换运输也不达原目标-需调整"])]
    rem_pass = int(out["一句话建议"].eq("先换运输-原目标已过").sum())
    rem_fail = int(out["一句话建议"].eq("换运输也不达原目标-需调整").sum())
    late = b[b["是否春节方案"] & b["首批晚于停工"].astype(bool)]
    late_a = int(late["放行等级"].astype(str).str.startswith("A").sum())
    late_b = int(late["放行等级"].astype(str).str.startswith("B").sum())

    summary = pd.DataFrame([
        ("覆盖范围", f"三个分公司全部 {len(out)} 个需求键；不是子集。"),
        ("数据日期", "预测基准 2026-11-02（叠加 11/1–8 同店修正）；库存/CG/EN 2026-11-09；"
                    "通途订单截至 11-08；PO 2026-11-05；动作重核 2026-11-09。"),
        ("春节方案", f"{len(cny_rows)} 键/{cny_rows['建议补多少'].sum():,.0f} 件；"
                  f"按 A/B 原目标重新判定；首批下单已按 11-09 重排。"),
        ("春节第二批停工", f"195 键需停工前插单（142 键有正第二批）；"
                      "14 个可确认里 6 个，风险情景 2 个失去目标。"),
        ("原目标核对", f"无断货/无补救/非零中位数 {tgt_total} 键：{tgt_yes} 达、"
                    f"{tgt_total - tgt_yes} 未达。"),
        ("可以补-待确认", f"{len(out[out['一句话建议'].eq('可以补-待确认')])} 键/"
                     f"{out.loc[out['一句话建议'].eq('可以补-待确认'),'建议补多少'].sum():,.0f} 件；A 看周期、B 看满足率。"),
        ("未达原目标", f"{len(out[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整'])])} 键/"
                    f"{out.loc[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整']),'建议补多少'].sum():,.0f} 件；不能按原目标通过。"),
        ("断货风险", f"{len(out[out['一句话建议'].eq('可能断货-需拍板')])} 键/"
                  f"{out.loc[out['一句话建议'].eq('可能断货-需拍板'),'建议补多少'].sum():,.0f} 件；所有已验证运输都晚于断货日。"),
        ("运输补救", f"{len(rem_rows)} 键/{rem_rows['建议补多少'].sum():,.0f} 件；"
                  f"按 A/B 严格目标 {rem_pass} 达/{rem_fail} 未达（旧轨迹口径 8 达/1 未达，"
                  "差异是 A 级不能用满足率替代周期）。"),
        ("催已有 + 新增", f"{len(expedite_rows)} 键；催已有 {expedite_rows['催已有量'].sum():,.0f} 件，"
                       f"新增 {expedite_rows['新增补货量'].sum():,.0f} 件；两种动作并列。"),
        ("日常补货", f"{len(daily_rows)} 键/{daily_rows['建议补多少'].sum():,.0f} 件；"
                  f"其中下单日已过 {len(past)} 键/{past['建议补多少'].sum():,.0f} 件。"),
        ("日期重核", f"日常 {len(past)} 键/{past['建议补多少'].sum():,.0f} 件下单日已过"
                  f"（其中 11-06 后新过期 {len(past6)} 键/{past6['建议量'].sum():,.0f} 件）；"
                  f"新增资格 {len(qual_past)} 键/{qual_past['建议补量'].sum():,.0f} 件原下单日已过。"),
    ], columns=["项", "说明"])

    sel = ["可以补-待确认", "先换运输-原目标已过", "未达原目标-需调整",
           "换运输也不达原目标-需调整", "可能断货-需拍板", "催已有+新增", "催已有",
           "补-待排期", "补-下单日已过-需重排", "需求看不清-先别补",
           "需求异常-不判定", "新增资格-待复审", "继续观察", "不用补"]
    pivot = out.pivot_table(index="分公司", columns="一句话建议", values="商品编码",
                            aggfunc="count", fill_value=0)
    pivot["需求键数"] = pivot.sum(axis=1)
    pivot = pivot.reindex(columns=["需求键数"] + sel, fill_value=0).reset_index()

    # ---------- 运营/老板可读层 ----------
    out["下单件数"] = out["首批数量"].fillna(0) + out["第二批数量"].fillna(0)
    out["到仓晚于需求天数"] = np.nan
    daily_mask = out["方案类型"].eq("日常补货") & out["首批数量"].gt(0)
    need_dt = pd.to_datetime(out["要求到仓/覆盖终点"], errors="coerce")
    arr_dt = pd.to_datetime(out["首批到仓"], errors="coerce")
    out.loc[daily_mask, "到仓晚于需求天数"] = (arr_dt[daily_mask] - need_dt[daily_mask]).dt.days
    late_text = out["到仓晚于需求天数"].between(1, 7)
    out.loc[late_text, "执行说明"] = (
        out.loc[late_text, "执行说明"].astype(str)
        + "；比需要日晚 "
        + out.loc[late_text, "到仓晚于需求天数"].astype(int).astype(str)
        + " 天")

    def late_reschedule(r):
        return "晚于需要日" in str(r.get("重排结果", ""))

    order_actions = ["下单", "下单（首批改空运）", "今天重下", "催在途 + 下单", "催在途"]
    late8 = out[out["动作"].isin(order_actions)
                & out["首批数量"].gt(0)
                & (out["到仓晚于需求天数"] >= 8)].copy()
    ops = out[out["动作"].isin(order_actions)
              & ~(out["首批数量"].gt(0) & (out["到仓晚于需求天数"] >= 8))].copy()
    ops = ops[~ops.apply(late_reschedule, axis=1)].copy()
    ops.insert(3, "目的客户/仓", ops["分公司"].map(
        {"美东USNJ": "CENTRADE", "美中USTX": "DANEEY", "波兰": "波兰公司"}))
    ops = ops.sort_values(["优先级", "分公司", "商品编码"])

    decision_status = ["可能断货-需拍板", "未达原目标-需调整", "换运输也不达原目标-需调整",
                       "需求看不清-先别补", "需求异常-不判定", "新增资格-待复审"]
    dec_boss = out[out["一句话建议"].isin(decision_status)].copy()
    dec_late = out[out["动作"].eq("今天重下") & out.apply(late_reschedule, axis=1)].copy()
    dec_late = pd.concat([dec_late, late8], ignore_index=True).drop_duplicates(
        ["分公司", "商品编码", "形态", "单位"])
    dec_route = out[out["动作"].eq("先确认路线")].copy()
    dec_boss = dec_boss.drop_duplicates(["分公司", "商品编码", "形态", "单位"])
    dec_late = dec_late.drop_duplicates(["分公司", "商品编码", "形态", "单位"])
    dec_route = dec_route.drop_duplicates(["分公司", "商品编码", "形态", "单位"])
    dec = pd.concat([dec_boss, dec_late, dec_route], ignore_index=True)

    def decision_text(r):
        s = r["一句话建议"]
        q = q0(r, "建议补多少")
        if r["动作"] == "先确认路线":
            return ("物流路线还没确认，无法给可信到仓日",
                    "让物流确认路线和到仓日，再下单", "先按空运/已知路线走",
                    "可能多花运费，但能锁定到仓日", "暂不下单", "不断货风险上升",
                    "先确认路线；如果 2 天内确认不了，按空运保供")
        if r["动作"] == "今天重下":
            return ("原计划下单日已过，按今天重下仍晚于需要日",
                    "今天重下，接受晚到", str(r.get("重排结果", "")),
                    "改空运/加急", "运费上升，可能赶上需要日", "不下单", "错过补货窗口",
                    "先算空运差价；能接受晚到就今天重下，不能就空运")
        if s == "可能断货-需拍板":
            return ("所有已验证运输都晚于预计断货日",
                    "空运加急/跨仓调拨", "仍可能晚于断货日，但缺口最小",
                    "接受断货", "断货期间不满足需求，客户体验受损",
                    "先确认空运和调拨；都不行就接受断货或改目标")
        if s == "未达原目标-需调整":
            return (f"按现方案补 {q} 件，模拟 1000 次仍达不到 A/B 目标",
                    "加量", "多备货，可能压库存", "接受较低服务", "A 类断货概率>5% 或 B 类缺货>5%",
                    "优先加量或换运输；不能加就明确接受较低服务")
        if s == "换运输也不达原目标-需调整":
            return ("换最快空运也达不到原目标",
                    "加量 + 空运", "成本最高，但有机会达标", "改目标/接受缺口",
                    "按较低服务执行", "先看加量成本；不接受就改目标")
        if s == "新增资格-待复审":
            return ("60cm 新并入的 SKU，资格还没确认",
                    "业务确认后补", "确认后才能进采购", "不补", "可能漏掉本可卖的 SKU",
                    "先让业务确认资格，确认后再补")
        if s == "需求看不清-先别补":
            return ("中位需求=0，只有 95 分位>0；不是没订单，是大多数天没订单",
                    "人工查最近订单/促销/停售", "查清后再定", "不补", "可能错过真实需求",
                    "先查最近 3 个月订单和促销，再决定")
        return ("需求波动过大，模型不可信",
                "查断货/促销/改价/一次性大单", "排除异常后再预测", "不补",
                "可能缺货也可能压库存", "先查异常原因，不要按当前预测下单")
    dec[["现在的情况", "选项A", "选项A后果", "选项B", "选项B后果",
         "建议"]] = dec.apply(lambda r: pd.Series(decision_text(r)[:6]), axis=1)
    dec["证据"] = dec["为什么"]
    dec["数量"] = dec["建议补多少"].round(0)
    decisions = dec[["优先级", "一句话建议", "分公司", "商品编码", "商品名称", "形态", "单位",
                     "数量", "现在的情况", "选项A", "选项A后果", "选项B", "选项B后果",
                     "建议", "谁决定", "证据"]].rename(columns={"一句话建议": "问题类型"})
    decisions = decisions.sort_values(["优先级", "问题类型", "分公司", "数量"],
                                      ascending=[True, True, True, False])

    noorder = out[out["一句话建议"].isin(["不用补", "继续观察"])].copy()
    noorder["原因"] = noorder["一句话建议"].map({
        "不用补": "库存 + 在途已经够覆盖；按当前预测不需要下单",
        "继续观察": "D6 还在观察，证据不足；暂不下单，等下一轮",
    })
    noorder = noorder[["分公司", "商品编码", "商品名称", "形态", "单位", "一句话建议", "原因"]]

    dict_rows = [
        ("A类", "服务目标：95% 的概率在整个窗口内不断货。", "看‘周期无断货概率’，不看满足率"),
        ("B类", "服务目标：满足 95% 的需求量（允许少量缺货）。", "看‘需求满足率’，不看周期"),
        ("q95", "需求的高位估计：95% 的情况下真实需求不超过这个数。", "补货量主要按 q95 算"),
        ("p50", "需求的中位估计：一半情况下不超过这个数。", "p50=0 且 q95>0 叫‘需求看不清’"),
        ("C / EN / PO", "C=国内可发；EN=EN 系统在途/待发；PO=已下采购单未到。", "三者按本池相加，不跨仓"),
        ("可以补-待确认", "按现方案模拟能达标，运营确认后可以下单。", "表里已给首批/第二批数量、运输、日期"),
        ("未达原目标", "按现方案模拟达不到 A/B 目标。", "需要加量、换运输或接受较低服务"),
        ("换运输也不达原目标", "换最快空运也达不到目标。", "只能加量或改目标"),
        ("可能断货-需拍板", "所有运输到仓都晚于预计断货日。", "要么空运/调拨，要么接受断货"),
        ("补-下单日已过-需重排", "原计划下单日已经过了；表里已按今天重算。", "看‘重排结果’：能赶上/晚几天"),
        ("催已有", "在途已经晚了，先催货，不新下单。", "催已有量列是催的件数"),
        ("催已有+新增", "先催在途，同时新下一部分。", "两个数量分开列"),
        ("需求看不清-先别补", "中位需求=0，只有高位>0；不是最近没订单，是大多数天没订单。", "先人工查，不自动下单"),
        ("需求异常-不判定", "需求波动过大（sigma>2），模型不可信。", "先查断货/促销/改价/大单"),
        ("新增资格-待复审", "60cm 新并入的 SKU，业务资格还没确认。", "确认后再补"),
        ("第二批需停工前插单", "春节工厂 1/24 停工；第二批必须在停工前做完，否则要等 2/22 复工。", "表里给最晚下单日；不插单会晚到"),
        ("路线待确认", "物流还没给出可用路线和到仓日。", "先确认路线，不要按默认天数下单"),
    ]
    dictionary = pd.DataFrame(dict_rows, columns=["名词", "白话解释", "怎么用"])

    data_notes = pd.DataFrame([
        ("库存/CG/EN", "2026-11-09", "已接入；C14 六桶对账仍未全绿，数值可用但保留瑕疵"),
        ("通途订单", "截至 2026-11-08 23:56", "已并入 orders_unified；11/1–8 同店修正只动 22 个需求键"),
        ("需求预测", "基准 2026-11-02 + 11/1–8 同店修正", "D5 v6.7；p10/p50/p90/q85/q90/q95 同乘因子，分位次序已校验"),
        ("PO", "2026-11-05", "通途采购单未收队列 po_open_receipt_queue_20261105.csv；不是 EN Purchase Order。去重后仅 22 件/2 键进入 D6；19+24 候选不依赖 PO"),
        ("60cm / DN-PO", "2026-11-05 审计", "逐键 11-09 覆盖未重跑；历史量不是当前采购量"),
        ("D5 模型对比", "2024/2025 回测", "使用 2026-11 选定的模型标签，存在前视；只能作回放诊断，不能证明当时生产流程胜出"),
        ("运输路线", f"{int((out['动作'].eq('先确认路线')).sum())} 个键路线待确认", "这些键没有可信到仓日，已从下单表移到拍板表"),
        ("春节第二批", f"195 个键需停工前插单（其中 142 个有正第二批）；14 个可确认里有 6 个", "不提前插单，6 个里 2 个会失去原目标"),
    ], columns=["项目", "时点/范围", "说明"])

    risk_path = BASE / "S2_9-delivery-final-20261106/D_春节第二批停工风险_2026-11-09.xlsx"
    risk_all = pd.read_excel(risk_path, sheet_name="2_逐键")
    cny_ok_keys = out.loc[out["一句话建议"].eq("可以补-待确认"), ["分公司", "商品编码"]]
    risk6 = cny_ok_keys.merge(risk_all, on=["分公司", "商品编码"], how="left")
    risk6 = risk6[risk6["方案A_第二批下单日"].notna()].copy()
    risk6 = risk6[["分公司", "商品编码", "物料名称", "放行等级", "第二批数量",
                   "方案A_第二批下单日", "方案A_第二批到仓",
                   "方案B_第二批下单日", "方案B_第二批到仓",
                   "方案A_达原目标", "方案B_达原目标", "停工后失去目标"]]

    p1 = ops[ops["优先级"].str.startswith("P1")]
    p2 = ops[ops["优先级"].str.startswith("P2")]
    p1_qty = int(p1["下单件数"].sum())
    p2_qty = int(p2["下单件数"].sum())
    late8_future = late8[late8["动作"].ne("今天重下")]
    late8_n = len(late8_future)
    late8_qty = int(late8_future["下单件数"].sum())
    late1_7 = out[out["动作"].isin(order_actions) & out["动作"].ne("今天重下")
                  & out["首批数量"].gt(0)
                  & out["到仓晚于需求天数"].between(1, 7)]
    exp_route = dec_route[dec_route["一句话建议"].eq("催已有+新增")]
    boss = pd.DataFrame([
        ("今天/本周要下的单", f"{len(p1)} 个商品，{p1_qty:,} 件"
                          f"（春节、补救、催货；其中 {int(p1['动作'].eq('催在途').sum())} 个只催不新下；"
                          f"{int(p1['到仓晚于需求天数'].between(1,7).sum())} 个新下单晚 1–7 天）",
         "按 1_运营下单表 的 P1 行执行；先看目的客户/仓、运输、下单日、到仓日"),
        ("可以排期的单", f"{len(p2)} 个商品，{p2_qty:,} 件",
         "按 1_运营下单表 的 P2 行排期；不要提前占用现金"),
        ("先催在途", f"{len(expedite_rows)} 个商品，催 {expedite_rows['催已有量'].sum():,.0f} 件；"
                   f"其中 {int((out['一句话建议'].eq('催已有+新增')).sum())} 个还要新下 "
                   f"{expedite_rows['新增补货量'].sum():,.0f} 件；"
                   f"{len(exp_route)} 个/ {exp_route['新增补货量'].sum():,.0f} 件在 2b 路线待确认",
         "让物流/采购先催；新下的部分看下单表，2b 的先确认路线"),
        ("要你拍板", f"{len(dec_boss)} 个商品；其中断货 {len(out[out['一句话建议'].eq('可能断货-需拍板')])} 个/"
                  f"{out.loc[out['一句话建议'].eq('可能断货-需拍板'),'建议补多少'].sum():,.0f} 件，"
                  f"未达目标 {len(out[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整'])])} 个/"
                  f"{out.loc[out['一句话建议'].isin(['未达原目标-需调整','换运输也不达原目标-需调整']),'建议补多少'].sum():,.0f} 件",
         "看 2_需要拍板，每行都写了选项 A/B 和后果"),
        ("物流先确认路线", f"{len(dec_route)} 个商品路线待确认", "转物流；没有路线就没有可信到仓日，先不要下单"),
        ("到仓晚 8 天以上", f"{late8_n} 行 / {late8_qty:,} 件，已从下单表移到 2c",
         "转运营/物流；能接受晚到就重下，不能就空运"),
        ("到仓晚 1–7 天", f"{len(late1_7)} 行，留在下单表但标了晚几天", "先核对提前期；能接受就下，不能就空运"),
        ("运营重排仍晚", f"{len(dec_late)} 个商品（含今天重下晚到 + 到仓晚 8 天以上）",
         "转运营/物流；能接受晚到就重下，不能就空运"),
        ("暂不下单", f"{len(noorder)} 个商品", "库存够或证据不足；看 3_暂不下单"),
        ("最大风险", "113 个商品/7,586 件所有运输都赶不上断货日；"
                  "54 个商品/2,696 件达不到原目标",
         "这两类不能靠运营自己决定，必须计划和业务拍板"),
        ("春节第二批", f"14 个可以补里，{len(risk6)} 个第二批必须停工前插单；不插单 {int(risk6['停工后失去目标'].sum())} 个会失去目标",
         "看 7_春节第二批停工风险；要工厂确认 12 月产能"),
        ("数据可信度", "库存/CG/EN 11-09；订单到 11-08；PO 仍 11-05；60cm 审计仍 11-05",
         "PO 和 60cm 不是最新；涉及这两项的结论要复核"),
        ("看表顺序", "老板看 0；运营下单看 1；要拍板看 2；物流看 2b；重排晚看 2c；"
                  "工厂看 7；8–13 是审计底稿，不用先看", "按角色分表，不要从 8_全量底稿 直接下单"),
    ], columns=["事项", "结论", "你要做什么"])

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
        ("审计时点", "round15 审计（截至 2026-11-05）；11-09 C/EN 已刷新，但 60cm 逐键覆盖未重跑。"),
        ("历史销量", f"{hist:,.0f} 件（20 键，不是当前采购量）"),
        ("C 覆盖", "20/20 exact_full，合计 239"),
        ("EN 覆盖", "20/20 exact_full，合计 239（同一物理池，不可相加）"),
        ("PO 无覆盖的历史量", f"{po_hist:,.0f} 件；只是历史规模，不是欠采购"),
        ("当前 D6 净需求", f"{net_now:,.2f} 件"),
        ("当前新补参考", f"{new_now:,.0f} 件"),
        ("DN/PO 阶段", "台账 11 DN/71 行/51 Shipment；EN 14 DN 中 3 缺失；arrive/warehouse_in 全空"),
    ], columns=["项", "结论"])

    corrections = pd.DataFrame([
        ("v2 / v3b / v4", "历史讨论版，已作废；不作为采购依据。"),
        ("v5.1 修 1", "同店修正改为对 point_forecast 与 p10/p50/p90/q85/q90/q95 同乘一个因子；"
                     "复算后分位次序 0 违反。"),
        ("v5.1 修 2", f"春节第二批按停工日历重排：{int(cny['第二批需停工前插单'].sum())} 个键改为停工前做完；"
                     "表里给出最晚下单日与停工后风险到仓日。"),
        ("v5.1 修 3", f"运输补救 5 个通过键改为展示补救方案（首批空运、补救到仓日），"
                     f"{rem_fail} 个未通过键不再写成可执行。"),
        ("v5.1 修 4", "新增 1_运营下单表（只放能执行的单）、2_需要拍板（选项+后果）、"
                     "3_暂不下单、4_名词解释；原全量底稿移到 8_全量底稿。"),
        ("v5.1 修 5", f"到仓晚于需要日 8 天以上的 {late8_n} 行从下单表移到 2c；"
                     f"晚 1–7 天的 {len(late1_7)} 行留在表内并标注天数。"),
        ("v5.1 数据", "库存/CG/EN 11-09；订单截至 11-08；PO 11-05；60cm 审计 11-05。"),
        ("v5.1 模型口径", "D5 回测使用 2026-11 选定的模型标签，存在前视；"
                        "不能据此证明历史当时 D5 胜出，只能作回放诊断。"),
    ], columns=["版本/变更", "说明"])

    # ---------- 断货/删失需求上界情景（不改主表） ----------
    d2 = pd.read_excel(D2B, sheet_name="1_键级估计")
    cens = d2[d2["censor_method"].ne("none")].copy()
    cens["ratio"] = cens.apply(
        lambda r: (float(r["estimated_demand"]) / float(r["observed_demand"]))
        if float(r["observed_demand"]) > 0 else np.nan, axis=1)
    cens = cens.rename(columns={"pool": "池", "physical_form": "形态",
                                "canonical_uom": "UOM"})
    cens = cens[KEYS + ["observed_demand", "estimated_demand", "ratio",
                        "n_censored_months", "censor_method"]]
    censor_cmp = b.merge(cens, on=KEYS, how="inner")
    censor_cmp["修正后q95"] = censor_cmp["q95"] * censor_cmp["ratio"]
    censor_cmp["估算新增净需求"] = (
        pd.to_numeric(censor_cmp["q95"], errors="coerce").fillna(0)
        * (censor_cmp["ratio"] - 1)).clip(lower=0)
    censor_cmp["物料名称"] = censor_cmp["物料名称"].fillna(censor_cmp["名称"])
    censor_cmp = censor_cmp[[
        "池", "product_id", "物料名称", "形态", "UOM", "一句话建议",
        "q95", "净需求95", "建议补量", "observed_demand", "estimated_demand",
        "ratio", "估算新增净需求", "n_censored_months", "censor_method",
    ]].rename(columns={
        "池": "分公司", "product_id": "商品编码", "物料名称": "商品名称",
        "UOM": "单位", "一句话建议": "当前建议", "q95": "当前q95",
        "净需求95": "当前净需求95", "建议补量": "当前建议量",
        "observed_demand": "D2b观测需求", "estimated_demand": "D2b估计需求",
        "ratio": "估计/观测", "估算新增净需求": "估算新增需求",
        "n_censored_months": "删失月数", "censor_method": "估计方法",
    }).sort_values("估算新增需求", ascending=False)
    tight = censor_cmp[
        (censor_cmp["估计/观测"] < 1.25)
        & (censor_cmp["删失月数"] <= 2)
        & censor_cmp["当前建议"].astype(str).str.startswith("补")]
    tail_ratio = censor_cmp[censor_cmp["估计/观测"] >= 2]
    tail_months = censor_cmp[censor_cmp["删失月数"] >= 5]
    tail_big = censor_cmp[
        (censor_cmp["当前建议量"].fillna(0) > 0)
        & (censor_cmp["估算新增需求"] > 0.5 * censor_cmp["当前建议量"].fillna(0))]
    cand43 = out[((out["方案类型"].eq("春节方案")) & (out["目标结果"].eq("达到")))
                 | out["动作"].eq("催在途")][
        ["分公司", "商品编码", "形态", "单位"]].merge(
        censor_cmp[["分公司", "商品编码", "形态", "单位", "估算新增需求"]],
        on=["分公司", "商品编码", "形态", "单位"], how="inner")
    censor_summary = pd.DataFrame([
        ("D2b 删失键", int(len(d2[d2["censor_method"].ne("none")])), "D2b v2；rate_upper 等方法"),
        ("匹配到 D6 当前键", int(len(censor_cmp)), "只匹配 product_id+池+形态+UOM"),
        ("估算新增需求合计", f"{censor_cmp['估算新增需求'].sum():,.0f} 件",
         "q95 × (D2b估计/观测 − 1)，是上界情景，不是点估计"),
        ("其中当前动作=补", int(censor_cmp["当前建议"].astype(str).str.startswith("补").sum()),
         "这些键最可能被低估"),
        ("是否进主表", "否", "不改 v5.1 下单量；先作为断货上界情景"),
        ("建议", "不按全量 3,196 件加", "43 行仅 8 行命中、+54 件；现有下单已覆盖上界净需求"),
        ("可选保守试点", f"{len(tight)} 键 / {tight['估算新增需求'].sum():,.0f} 件",
         "倍数<1.25、删失月≤2、当前动作=补；与 43 行交集 0；会后业务决定"),
        ("全量上界不采用原因",
         f"倍数≥2：{len(tail_ratio)} 键/+{tail_ratio['估算新增需求'].sum():,.0f}；"
         f"删失≥5月：{len(tail_months)} 键/+{tail_months['估算新增需求'].sum():,.0f}；"
         f"加量>当前50%：{len(tail_big)} 键/+{tail_big['估算新增需求'].sum():,.0f}",
         "rate_upper 是上界，不是点估计；尾部不适合直接下单"),
    ], columns=["项", "值", "说明"])
    boss = pd.concat([boss, pd.DataFrame([
        ("断货影响",
         f"D2b 上界 {len(censor_cmp)} 键/+{censor_cmp['估算新增需求'].sum():,.0f} 件；"
         f"建议不加全量。43 行仅 {len(cand43)} 行命中/+{cand43['估算新增需求'].sum():,.0f} 件",
         f"43 行现有下单已覆盖；可选保守试点 {len(tight)} 键/+{tight['估算新增需求'].sum():,.0f} 件，"
         "看 15 后由业务决定"),
    ], columns=["事项", "结论", "你要做什么"])], ignore_index=True)
    data_notes = pd.concat([data_notes, pd.DataFrame([
        ("断货/删失需求",
         f"D2b 删失键 {len(d2[d2['censor_method'].ne('none')])} 个；匹配 {len(censor_cmp)} 个；"
         f"估算新增 {censor_cmp['估算新增需求'].sum():,.0f} 件",
         "上界情景，未进主表；见 15_断货修正情景"),
    ], columns=["项目", "时点/范围", "说明"])], ignore_index=True)

    src = pd.DataFrame([
        ("D5 v6.7", str(D5), sha(D5)),
        ("11/1–8 同店修正", str(NC), sha(NC)),
        ("D6 v6.18", str(D6), sha(D6)),
        ("CNY v9", str(CNY), sha(CNY)),
        ("轨迹 v9", str(TRAJ), sha(TRAJ)),
        ("C14 11-09 刷新", str(C14), sha(C14)),
        ("EN 库存 11-09", str(EN_STOCK), sha(EN_STOCK)),
        ("CG 库存 11-09", str(CG_STOCK), sha(CG_STOCK)),
        ("D2b 删失需求", str(D2B), sha(D2B)),
        ("v15 历史交付包", str(V15), sha(V15)),
        ("A 活跃宇宙", str(A), sha(A)),
        ("60cm/DN-PO 审计", str(W3), sha(W3)),
    ], columns=["文件", "路径", "sha256"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        boss.to_excel(w, sheet_name="0_老板先看", index=False)
        ops.to_excel(w, sheet_name="1_运营下单表", index=False)
        dec_boss.rename(columns={"一句话建议": "问题类型"}).assign(
            现在的情况=dec_boss.apply(lambda r: decision_text(r)[0], axis=1),
            选项A=dec_boss.apply(lambda r: decision_text(r)[1], axis=1),
            选项A后果=dec_boss.apply(lambda r: decision_text(r)[2], axis=1),
            选项B=dec_boss.apply(lambda r: decision_text(r)[3], axis=1),
            选项B后果=dec_boss.apply(lambda r: decision_text(r)[4], axis=1),
            建议=dec_boss.apply(lambda r: decision_text(r)[5], axis=1),
            数量=dec_boss["建议补多少"].round(0),
            证据=dec_boss["为什么"],
        )[["优先级", "问题类型", "分公司", "商品编码", "商品名称", "形态", "单位", "数量",
           "现在的情况", "选项A", "选项A后果", "选项B", "选项B后果", "建议", "谁决定", "证据"]].to_excel(
            w, sheet_name="2_需要拍板", index=False)
        dec_route.rename(columns={"一句话建议": "原状态"}).to_excel(
            w, sheet_name="2b_物流确认路线", index=False)
        dec_late.rename(columns={"一句话建议": "原状态"}).to_excel(
            w, sheet_name="2c_重排晚于需要日", index=False)
        noorder.to_excel(w, sheet_name="3_暂不下单", index=False)
        dictionary.to_excel(w, sheet_name="4_名词解释", index=False)
        data_notes.to_excel(w, sheet_name="5_数据与口径", index=False)
        summary.to_excel(w, sheet_name="6_核对汇总（内部）", index=False)
        risk6.to_excel(w, sheet_name="7_春节第二批停工风险", index=False)
        out.to_excel(w, sheet_name="8_全量底稿（审计）", index=False)
        target31.to_excel(w, sheet_name="9_服务目标核对", index=False)
        past6.to_excel(w, sheet_name="10_新过期清单", index=False)
        src.to_excel(w, sheet_name="11_数据来源", index=False)
        corrections.to_excel(w, sheet_name="12_v5.1改了什么", index=False)
        po60.to_excel(w, sheet_name="13_60cm与DN-PO（审计）", index=False)
        keys60.to_excel(w, sheet_name="13b_60cm逐键", index=False)
        pivot.to_excel(w, sheet_name="14_分公司汇总", index=False)
        censor_summary.to_excel(w, sheet_name="15_断货修正情景", index=False)
        censor_cmp.to_excel(w, sheet_name="15b_断货修正逐键", index=False)

    wb = load_workbook(OUT)
    hf, hfont = PatternFill("solid", fgColor="1F4E78"), Font(color="FFFFFF", bold=True)
    fills = {"可以补-待确认": "C6EFCE", "先换运输-原目标已过": "FFF2CC",
             "催已有+新增": "DDEBF7", "催已有": "DDEBF7",
             "补-待排期": "DDEBF7", "补-下单日已过-需重排": "FCE4D6",
             "未达原目标-需调整": "FCE4D6", "换运输也不达原目标-需调整": "FCE4D6",
             "可能断货-需拍板": "F8CBAD", "需求看不清-先别补": "D9E1F2",
             "需求异常-不判定": "D9E1F2", "新增资格-待复审": "E4DFEC",
             "不用补": "EDEDED", "继续观察": "EDEDED"}
    action_fills = {"下单": "C6EFCE", "下单（首批改空运）": "FFF2CC",
                    "今天重下": "FCE4D6", "催在途 + 下单": "DDEBF7",
                    "催在途": "DDEBF7"}
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for c in ws[1]:
            c.fill, c.font = hf, hfont
            c.alignment = Alignment(wrap_text=True, vertical="center")
        widths = {}
        for row in ws.iter_rows(values_only=True):
            for i, v in enumerate(row, 1):
                widths[i] = min(52, max(widths.get(i, 10), len(str(v)) + 2))
        for i, wd in widths.items():
            ws.column_dimensions[get_column_letter(i)].width = wd
    ws = wb["8_全量底稿（审计）"]
    hdr = [c.value for c in ws[1]]
    if "一句话建议" in hdr:
        ci = hdr.index("一句话建议") + 1
        for row in range(2, ws.max_row + 1):
            v = ws.cell(row=row, column=ci).value
            if v in fills:
                ws.cell(row=row, column=ci).fill = PatternFill("solid", fgColor=fills[v])
    ws = wb["1_运营下单表"]
    hdr = [c.value for c in ws[1]]
    if "动作" in hdr:
        ci = hdr.index("动作") + 1
        for row in range(2, ws.max_row + 1):
            v = ws.cell(row=row, column=ci).value
            if v in action_fills:
                ws.cell(row=row, column=ci).fill = PatternFill("solid", fgColor=action_fills[v])
    wb.save(OUT)
    print("wrote", OUT)
    print(boss.to_string(index=False))
    print("\n运营下单表", len(ops), "行；老板拍板", len(dec_boss),
          "行；物流路线", len(dec_route), "行；重排晚", len(dec_late),
          "行；暂不下单", len(noorder), "行")
    print(out["一句话建议"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
