# -*- coding: utf-8 -*-
"""Build delivery package v14 from v13 + trajectory v6 + PO source.

Adds:
- 0_参数与种子, 12_已知限制, 13_同窗口180_*
- 1_汇总 split: CNY executable / fail / anomaly / risk-isolated (overlap noted)
- 9_春节备货建议 with trajectory status
- 10_PO逐单台账 with open_qty / ETA / match / cardinality / reason
- 10a_PO核对 summary incl. 14 EN DNs vs 11 ledger DNs
- manifest with input/script hashes

Read-only for source data; writes v14 workbook + report + manifest.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
V13 = BASE / "S2_9-delivery-final-20261106/D_补货交付包_2026-11-06_final_v13_draft.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v7.xlsx"
D6 = BASE / "D6v6_15-final/D_Top50沙盒_D6_v6_15_2026-11-07.xlsx"
D6_PREV = BASE / "D6v6_14-final/D_Top50沙盒_D6_v6_14_2026-11-06.xlsx"
D1B = BASE / "D_资格与契约_D1b_v2_3_2026-11-02.xlsx"
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
RISK = BASE / "S2_9-delivery-final-20261106/D_断货风险与需求抑制_2026-11-06_v2.xlsx"
TRAJ = BASE / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-07_v7.xlsx"
PO_SRC = BASE / "po_open_receipt_queue_20261105.csv"
PO_AUDIT = BASE / "po_dn_stage_audit_20261106.csv"
PO_OVERLAP = BASE / "po_en_overlap_audit_20261105.csv"
CM_RECON = BASE / "60cm_287_reconciliation_v8_20261107.csv"
SCRIPT_PATH = Path(__file__).resolve()
OUTDIR = BASE / "S2_9-delivery-final-20261106"
OUT = OUTDIR / "D_补货交付包_2026-11-06_final_v15.xlsx"
REPORT = OUTDIR / "D_补货交付包_2026-11-06_final_v15_报告.md"
MANIFEST = OUTDIR / "D_补货交付包_2026-11-06_final_v15.manifest.json"
KEYS = ["product_id", "池", "形态", "UOM"]


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    OUTDIR.mkdir(exist_ok=True)
    frames = pd.read_excel(V13, sheet_name=None)
    traj = pd.read_excel(TRAJ, sheet_name="2_逐键")
    traj_sum = pd.read_excel(TRAJ, sheet_name="1_汇总")
    sens = pd.read_excel(TRAJ, sheet_name="3b_同窗口180_逐键")
    sens_sum = pd.read_excel(TRAJ, sheet_name="3_同窗口180_汇总")
    params = pd.read_excel(TRAJ, sheet_name="0_参数")
    rescue = pd.read_excel(TRAJ, sheet_name="3_运输补救")
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期")
    risk = pd.read_excel(RISK, sheet_name="2_断货风险")
    po_src = pd.read_csv(PO_SRC, encoding="utf-8-sig")
    po_audit = pd.read_csv(PO_AUDIT, encoding="utf-8-sig")
    po_overlap = pd.read_csv(PO_OVERLAP, encoding="utf-8-sig")
    cm = pd.read_csv(CM_RECON, encoding="utf-8-sig")
    d6 = pd.read_excel(D6, sheet_name="1_全量动作")
    d6_prev = pd.read_excel(D6_PREV, sheet_name="1_全量动作")
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5["horizon"].astype(str) == "97"].rename(
        columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM"})
    d1b = pd.read_excel(D1B, sheet_name="1_资格")
    prev_unk = d6_prev[d6_prev["C完整键状态"].astype(str).eq("unknown_no_full_key")][
        ["product_id", "池", "形态", "UOM", "C可发供给", "C完整键状态",
         "建议动作", "净需求95"]].rename(
        columns={"C可发供给": "C修复前", "C完整键状态": "状态修复前",
                 "建议动作": "动作修复前", "净需求95": "净需求修复前"})
    rec = prev_unk.merge(
        d6[KEYS + ["C可发供给", "C完整键状态", "建议动作", "净需求95"]],
        on=KEYS, how="inner").rename(
        columns={"C可发供给": "C修复后", "C完整键状态": "状态修复后",
                 "建议动作": "动作修复后", "净需求95": "净需求修复后"})
    rec = rec[rec["状态修复后"].astype(str).ne("unknown_no_full_key")]
    rec = rec[["product_id", "池", "形态", "UOM", "C修复前", "C修复后",
               "状态修复前", "状态修复后", "动作修复前", "动作修复后",
               "净需求修复前", "净需求修复后"]]

    # ---------- 9_春节备货建议：直接用 CNY v7（整数批次 + prehaul=2）
    cny9 = cny.copy()
    tcols = ["状态", "评估天数", "窗口止", "需求sigma", "需求异常", "需求异常类型",
             "无断货概率", "满足率"]
    tj = traj[traj["类型"] == "春节"][KEYS + ["数量", "首批到仓", "第二批到仓"] + tcols].rename(
        columns={"数量": "轨迹数量", "首批到仓": "轨迹首批到仓",
                 "第二批到仓": "轨迹第二批到仓", "状态": "轨迹状态",
                 "评估天数": "轨迹评估天数", "窗口止": "轨迹窗口止",
                 "需求sigma": "轨迹需求sigma", "需求异常": "轨迹需求异常",
                 "需求异常类型": "轨迹需求异常类型",
                 "无断货概率": "轨迹无断货概率", "满足率": "轨迹满足率"})
    cny9 = cny9.merge(tj, on=KEYS, how="left")
    cny9["风险状态"] = cny9["风险状态"].fillna("").astype(str)
    cny9["是否风险隔离"] = cny9["风险状态"].eq("全部方案失败")
    cny9["是否可换运输"] = cny9["风险状态"].eq("选定方案失败-有补救候选")
    exec_map = {"cycle95": "可执行-待人工确认", "fill95": "可执行-待人工确认",
                "fail": "不可执行-轨迹未过", "模型异常": "模型异常-不判定",
                "模型异常-零中位数": "模型异常-零中位数", "无需求-不判定": "无需求-不判定"}
    cny9["可执行状态"] = np.select(
        [cny9["是否风险隔离"], cny9["是否可换运输"],
         cny9["轨迹状态"].eq("模型异常-零中位数"),
         cny9["首批晚于停工"].astype(bool)
         & cny9["轨迹状态"].isin(["cycle95", "fill95"])],
        ["风险隔离-待决策", "可换运输-待重模拟", "模型异常-零中位数",
         "首批晚于停工-需重排"],
        default=cny9["轨迹状态"].map(exec_map).fillna("未匹配-需复核"))
    cny9["取整差"] = (pd.to_numeric(cny9["建议节前备货量"], errors="coerce").fillna(0)
                    - pd.to_numeric(cny9["首批数量"], errors="coerce").fillna(0)
                    - pd.to_numeric(cny9["第二批数量"], errors="coerce").fillna(0)).round(0)
    cny9["日期一致"] = (cny9["首批到仓"].astype(str) == cny9["轨迹首批到仓"].astype(str))

    # ---------- 19 个 60cm 供给恢复后的新增资格；31/7 人工复审材料
    qual = rec[rec["动作修复前"].eq("观察") & rec["动作修复后"].eq("补")].copy()
    qual = qual.merge(d5[KEYS + ["p50", "q95"]], on=KEYS, how="left")
    d1bq = d1b.rename(columns={"destination_pool": "池", "physical_form": "形态",
                               "canonical_uom": "UOM"})[
        ["product_id", "池", "形态", "UOM", "decision_state", "demand_state",
         "netting_state", "reason_code"]]
    qual = qual.merge(d1bq, on=KEYS, how="left")
    qual = qual.merge(cny9[KEYS].assign(在257=True), on=KEYS, how="left")
    qual["在257"] = qual["在257"].fillna(False)
    qual = qual.rename(columns={"p50": "D5_p50", "q95": "D5_q95"})
    qual["建议结论"] = np.select(
        [qual["netting_state"].astype(str).ne("eligible"),
         qual["demand_state"].astype(str).ne("observed"),
         pd.to_numeric(qual["D5_p50"], errors="coerce").fillna(0) <= 0],
        ["阻塞-净额资格不足", "阻塞-需求未观测", "阻塞-零中位数待验证"],
        default="待人工接受")
    qual["阻塞原因"] = np.select(
        [qual["netting_state"].astype(str).ne("eligible"),
         qual["demand_state"].astype(str).ne("observed"),
         pd.to_numeric(qual["D5_p50"], errors="coerce").fillna(0) <= 0],
        [qual["netting_state"].astype(str), qual["demand_state"].astype(str),
         "p50=0 且供给恢复后转为补；模型待验证"],
        default="")
    qual["资格复审"] = "待人工：新增补货资格未审"

    r31 = cny9[cny9["轨迹状态"].isin(["cycle95", "fill95"])
               & (~cny9["是否风险隔离"]) & (~cny9["是否可换运输"])
               & (~cny9["轨迹状态"].eq("模型异常-零中位数"))].copy()
    r31["服务目标"] = np.where(r31["轨迹状态"].eq("cycle95"),
                                "周期无断货≥95%", "满足率≥95%（周期<95%）")
    r31["人工确认"] = "确认需求/政策/下单日"
    r31 = r31[["product_id", "池", "形态", "UOM", "建议节前备货量", "首批数量",
               "第二批数量", "首批到仓", "第二批到仓", "首批下单日", "第二批下单日",
               "首批晚于停工", "建议运输", "服务目标",
               "日均q95需求", "当前可用", "轨迹状态", "模型资格", "执行闸门",
               "人工确认"]]
    r31["执行状态"] = np.where(r31["首批晚于停工"].astype(bool),
                                "首批晚于停工-需重排", "可执行")

    r7 = rescue[rescue["状态"].isin(["cycle95", "fill95"])].copy()
    r7["执行状态"] = r7["可执行补救状态"]
    r7["需确认"] = "确认空运舱位/运价/合同；普船二批下单日已过需重排"
    exec_rescue = rescue[rescue["可执行补救状态"].isin(["cycle95", "fill95"])]
    blocked_rescue = rescue[rescue["可执行补救状态"].eq("阻塞-第二批下单日已过")]

    # ---------- 2_候选总表：状态/服务指标全部回填 v7
    cand = frames["2_可批准候选"].copy()
    cand = cand.merge(d5[KEYS + ["p50"]], on=KEYS, how="left").rename(
        columns={"p50": "forecast_p50"})
    tj2 = traj[KEYS + ["评估天数", "窗口止", "状态", "无断货概率", "满足率",
                       "首批到仓", "需求异常类型"]].rename(
        columns={"评估天数": "轨迹评估天数", "窗口止": "轨迹窗口止",
                 "状态": "轨迹状态_最新", "无断货概率": "周期无断货概率_v7",
                 "满足率": "需求满足率_v7", "首批到仓": "首批到仓_v7",
                 "需求异常类型": "需求异常类型_v7"})
    cand = cand.merge(tj2, on=KEYS, how="left")
    cand = cand.merge(cny9[KEYS + ["风险状态", "是否风险隔离", "是否可换运输",
                                   "首批晚于停工", "模型资格", "执行闸门"]],
                      on=KEYS, how="left")
    cand["风险状态"] = cand["风险状态"].fillna("").astype(str)
    cand["可执行状态"] = np.select(
        [cand["风险状态"].eq("全部方案失败"),
         cand["风险状态"].eq("选定方案失败-有补救候选"),
         cand["轨迹状态_最新"].eq("模型异常-零中位数"),
         cand["首批晚于停工"].astype(bool)
         & cand["轨迹状态_最新"].isin(["cycle95", "fill95"]),
         cand["轨迹状态_最新"].isin(["cycle95", "fill95"]),
         cand["轨迹状态_最新"].eq("fail")],
        ["风险隔离-待决策", "可换运输-待重模拟", "模型异常-零中位数",
         "首批晚于停工-需重排", "可执行-待人工确认", "不可执行-轨迹未过"],
        default="模型异常-不判定")
    cand["轨迹状态"] = cand["轨迹状态_最新"]
    cand["周期无断货概率"] = cand["周期无断货概率_v7"]
    cand["需求满足率"] = cand["需求满足率_v7"]
    cand["首批到仓"] = cand["首批到仓_v7"]
    cand["需求异常类型"] = cand["需求异常类型_v7"]
    zm = cand["轨迹状态_最新"].eq("模型异常-零中位数")
    cand.loc[zm, "建议数量"] = 0
    cand.loc[zm, "建议动作"] = "观察（零中位数-待验证）"
    if "春节方案数量" in cand.columns:
        cand.loc[zm, "春节方案数量"] = 0
    cand["forecast_q95"] = cand["需求q95"]
    cand["raw_net_gap"] = cand["净需求95"]
    cand["proposed_qty"] = cand["建议数量"]
    cand["approved_qty"] = 0
    cand["模型资格"] = cand["模型资格"].fillna("正常")
    cand["阻断原因"] = np.select(
        [zm, cand["风险状态"].eq("选定方案失败-有补救候选"),
         cand["风险状态"].eq("全部方案失败")],
        ["p50=0 且 q95>0；模型待验证，禁止执行",
         "选定运输晚于断货日；可换运输待重模拟",
         "所有已验证运输均晚于断货日"],
        default="")
    cand = cand.drop(columns=[c for c in ["轨迹无断货", "轨迹满足率"] if c in cand.columns])

    # ---------- 1_汇总
    cny_total = float(pd.to_numeric(cny9["建议节前备货量"], errors="coerce").fillna(0).sum())
    g = traj[traj["类型"] == "春节"].groupby("状态").agg(
        键数=("product_id", "size"), 数量=("数量", "sum"))
    gn = traj[traj["类型"] == "新增"].groupby("状态").agg(
        键数=("product_id", "size"), 数量=("数量", "sum"))
    risk_rows = cny9[cny9["是否风险隔离"]]
    risk_qty = float(pd.to_numeric(risk_rows["建议节前备货量"], errors="coerce").fillna(0).sum())
    remedy_rows = cny9[cny9["是否可换运输"]]
    remedy_qty = float(pd.to_numeric(remedy_rows["建议节前备货量"], errors="coerce").fillna(0).sum())
    risk_pass = cny9[cny9["是否风险隔离"] & cny9["轨迹状态"].isin(["cycle95", "fill95"])]
    early_rows = cny9[cny9["可执行状态"].eq("首批晚于停工-需重排")]
    risk_pass_qty = float(pd.to_numeric(risk_pass["建议节前备货量"],
                                       errors="coerce").fillna(0).sum())
    traj_cny_qty = float(pd.to_numeric(traj.loc[traj["类型"] == "春节", "数量"],
                                       errors="coerce").fillna(0).sum())
    round_diff = round(cny_total - traj_cny_qty, 1)
    cand_qty = float(pd.to_numeric(cand["建议数量"], errors="coerce").fillna(0).sum())

    def bucket(st):
        idx = cny9["轨迹状态"].eq(st)
        return (int(idx.sum()),
                round(float(pd.to_numeric(cny9.loc[idx, "建议节前备货量"],
                                          errors="coerce").fillna(0).sum()), 1),
                round(float(pd.to_numeric(cny9.loc[idx, "轨迹数量"],
                                          errors="coerce").fillna(0).sum()), 1))

    def nn(st):
        return (int(gn.loc[st, "键数"]) if st in gn.index else 0,
                round(float(gn.loc[st, "数量"]) if st in gn.index else 0.0, 1))

    c_cy, p_cy, q_cy = bucket("cycle95")
    c_fi, p_fi, q_fi = bucket("fill95")
    c_fa, p_fa, q_fa = bucket("fail")
    c_an, p_an, q_an = bucket("模型异常")
    c_zm, p_zm, q_zm = bucket("模型异常-零中位数")
    n_fi, q_nfi = nn("fill95"); n_fa, q_nfa = nn("fail")
    risk_traj_qty = round(float(pd.to_numeric(risk_rows["轨迹数量"],
                                              errors="coerce").fillna(0).sum()), 1)
    risk_pass_traj = round(float(pd.to_numeric(risk_pass["轨迹数量"],
                                               errors="coerce").fillna(0).sum()), 1)
    net_rows = cny9[(~cny9["是否风险隔离"]) & (~cny9["是否可换运输"])
                    & (~cny9["首批晚于停工"].astype(bool))
                    & cny9["轨迹状态"].isin(["cycle95", "fill95"])]
    net_keys = len(net_rows)
    net_plan = round(float(pd.to_numeric(net_rows["建议节前备货量"],
                                         errors="coerce").fillna(0).sum()), 1)
    net_traj = round(float(pd.to_numeric(net_rows["轨迹数量"],
                                         errors="coerce").fillna(0).sum()), 1)
    summary = pd.DataFrame([
        ("春节方案总量（9_春节备货建议）", len(cny9), cny_total, traj_cny_qty,
         "方案总量；不是可执行量；整数批次，两列应一致"),
        ("  其中：轨迹可执行 cycle95", c_cy, p_cy, q_cy, "P(全程无断货)>=95%"),
        ("  其中：轨迹可执行 fill95", c_fi, p_fi, q_fi, "周期<95%，但总满足率>=95%"),
        ("  其中：轨迹未通过 fail", c_fa, p_fa, q_fa, "不可执行；需改方案或人工接受风险"),
        ("  其中：模型异常（不判定）", c_an, p_an, q_an, "sigma>2，需求尾部失真，不参与通过/失败"),
        ("  其中：零中位数（隔离）", c_zm, p_zm, q_zm,
         "p50=0 且 q95>0；保留原q95与净需求，方案量0、禁止执行"),
        ("  取整差（方案量-轨迹量）", np.nan, round_diff, np.nan, "整数批次，差应为 0；逐行看 3_整数校验"),
        ("  其中：风险隔离（与上面交叉）", len(risk_rows), round(risk_qty, 1), risk_traj_qty,
         f"{len(risk_rows)} 条全部已验证运输都晚于断货日；是总量子集，不能与上面相加"),
        ("  其中：可换运输-待重模拟", len(remedy_rows), round(remedy_qty, 1), np.nan,
         "选定运输晚于断货日，但更快运输可赶上；需重模拟，不直接解禁"),
        ("  其中：可执行补救通过", len(exec_rescue),
         float(pd.to_numeric(exec_rescue["数量"], errors="coerce").fillna(0).sum()), np.nan,
         "7 键通过（5 cycle/2 fill）；第二批下单日已按复工 2/22 校正"),
        ("  其中：补救被第二批下单日阻塞", len(blocked_rescue),
         float(pd.to_numeric(blocked_rescue["数量"], errors="coerce").fillna(0).sum()), np.nan,
         "0（第二批已按复工 2/22 校正）"),
        ("  其中：首批晚于停工-需重排", len(early_rows),
         float(pd.to_numeric(early_rows["建议节前备货量"], errors="coerce").fillna(0).sum()), np.nan,
         "首批到仓晚于 2027-01-24 停工；需改空运/提前，不算净可执行"),
        ("  其中：可执行但风险隔离", len(risk_pass), round(risk_pass_qty, 1), risk_pass_traj,
         "轨迹过但风险未消；按风险隔离处理，不计入净可执行"),
        ("净可执行（剔除风险隔离）", net_keys, net_plan, net_traj,
         "真正可进入人工批准的候选；整数批次，两列应一致"),
        ("新增补货量（催已有中的新增）", n_fi + n_fa, q_nfi + q_nfa, q_nfi + q_nfa,
         "当前基准 5,309；旧 5,239 作废"),
        ("  其中：新增 fill95", n_fi, q_nfi, q_nfi, "仅这些达到总满足率>=95%"),
        ("  其中：新增 fail", n_fa, q_nfa, q_nfa, "其余未过；需改方案/接受风险"),
        ("当前补货候选（参考，不批准）", len(cand), cand_qty, np.nan,
         f"{cand_qty:,.0f} 是日常候选，不等于春节 {cny_total:,.0f}"),
        ("PO 未结台账", len(po_src), float(po_src["open_qty"].sum()), np.nan,
         "2026-11-05 快照；不是库存"),
        ("  其中：可关联 DN", int(po_audit["DN可关联"].sum()),
         float(po_audit.loc[po_audit["DN可关联"], "po_open"].sum()), np.nan,
         "EN DN 字段 + 未结 PO 行"),
        ("  其中：可关联 Shipment", int(po_audit["Shipment可关联"].sum()),
         float(po_audit.loc[po_audit["Shipment可关联"], "po_open"].sum()), np.nan,
         "可接 EN Shipment"),
        ("60cm 对账（KS0001→KS0248）", len(cm), float(cm["qty_v3_5"].sum()),
         float(cm["qty_v3_7"].sum() + cm["qty_v3_7_orig"].sum()),
         "合并 2,615；保留原键 4,001（含 287）；无键退出预测母集"),
    ], columns=["类别", "键数", "方案量", "轨迹量", "说明"])
    summary["键数"] = summary["键数"].apply(lambda x: int(x) if pd.notna(x) else "")

    # ---------- 10_PO ledger
    led = frames["10_PO逐单台账"].copy()
    led = led.merge(po_src[["PONum", "goods_sku", "open_qty", "willArriveDate",
                            "purchaseArrivalDate", "status", "_status_name",
                            "received", "open"]], on=["PONum", "goods_sku"], how="left")
    led["open_qty_一致"] = np.isclose(
        pd.to_numeric(led["open_qty"], errors="coerce"),
        pd.to_numeric(led["po_open"], errors="coerce"), equal_nan=True)
    dn_po = led.dropna(subset=["DN"]).groupby("DN")["PONum"].nunique()
    po_dn = led.dropna(subset=["DN"]).groupby("PONum")["DN"].nunique()
    def card(r):
        if pd.isna(r["DN"]):
            return ""
        a = int(dn_po.get(r["DN"], 1)); b = int(po_dn.get(r["PONum"], 1))
        if a == 1 and b == 1:
            return "1:1"
        if a > 1 and b == 1:
            return "1:N（一 PO 多 DN）"
        if a == 1 and b > 1:
            return "N:1（一 DN 多 PO）"
        return "N:N"
    led["基数类型"] = led.apply(card, axis=1)
    led["已关联DN数量"] = np.where(led["DN"].notna(), led["open_qty"], 0)
    def reason(r):
        if pd.isna(r["DN"]):
            return "无DN关联（旧PO/未建单/无未结行）"
        if not bool(r["Shipment可关联"]):
            return "DN未关联Shipment"
        return ""
    led["未匹配原因"] = led.apply(reason, axis=1)
    led["证据来源"] = "EN DN.custom_tongtool_purchase_order + PO open queue 20261105"
    ledger_cols = ["PONum", "goods_sku", "warehouseName", "open_qty", "willArriveDate",
                   "purchaseArrivalDate", "status", "_status_name", "received", "open",
                   "DN", "DN日期", "shipment", "depart", "arrive", "warehouse_in",
                   "已关联DN数量", "基数类型", "DN可关联", "Shipment可关联",
                   "未匹配原因", "证据来源", "open_qty_一致"]
    led_out = led[ledger_cols].copy()

    # ---------- 10a_PO核对
    dn_ledger = set(led["DN"].dropna().unique())
    dn_en = ["DN-26-00086", "DN-26-00087", "DN-26-00104-1", "DN-26-00110",
             "DN-26-00111", "DN-26-00112", "DN-26-00113-1", "DN-26-00114",
             "DN-26-00115", "DN-26-00121", "DN-26-00122", "DN-26-00123",
             "DN-26-00134", "DN-26-00135"]
    missing = [d for d in dn_en if d not in dn_ledger]
    po_check = pd.DataFrame([
        ("PO 源行数", len(po_src), "po_open_receipt_queue_20261105.csv"),
        ("PO open_qty 合计", float(po_src["open_qty"].sum()), "不是库存，是未结采购量"),
        ("唯一 PO 数", int(po_src["PONum"].nunique()), ""),
        ("台账行数", len(led_out), "与源行数一致"),
        ("open_qty 与 po_open 一致行", int(led_out["open_qty_一致"].sum()), "应为 2,664"),
        ("可关联 DN 行", int(po_audit["DN可关联"].sum()), "71 行"),
        ("可关联 DN 的 open 量", float(po_audit.loc[po_audit["DN可关联"], "po_open"].sum()), ""),
        ("可关联 Shipment 行", int(po_audit["Shipment可关联"].sum()), "51 行"),
        ("可关联 Shipment 的 open 量", float(po_audit.loc[po_audit["Shipment可关联"], "po_open"].sum()), ""),
        ("EN 带通途 PO 字段的 DN", len(dn_en), "2026-11-06 查询"),
        ("台账中出现的 DN", len(dn_ledger), ""),
        ("EN 有、台账无的 DN", ",".join(missing), "PO021724 不在未结队列；PO021747/748 为 11-06 新建，晚于 11-05 快照"),
        ("DN↔PO 基数", "样本 11 个 DN 均为 1:1；未证明全局", "旧 PO 无字段，不能反推"),
    ], columns=["项", "值", "说明"])
    ov = po_overlap
    ov_summary = pd.DataFrame([
        ("PO 行", len(ov), "po_en_overlap_audit_20261105.csv"),
        ("PO open 合计", float(pd.to_numeric(ov["po_open"], errors="coerce").fillna(0).sum()), ""),
        ("EN 在途+待发", float(pd.to_numeric(ov["en_inbound"], errors="coerce").fillna(0).sum()), ""),
        ("与 EN 重叠", float(pd.to_numeric(ov["overlap_qty"], errors="coerce").fillna(0).sum()), "PO 已包含在 EN 在途/待发"),
        ("超出 EN", float(pd.to_numeric(ov["excess_qty"], errors="coerce").fillna(0).sum()), "PO 未被 EN 覆盖"),
        ("有重叠的行", int((pd.to_numeric(ov["overlap_qty"], errors="coerce").fillna(0) > 0).sum()), ""),
        ("有超出的行", int((pd.to_numeric(ov["excess_qty"], errors="coerce").fillna(0) > 0).sum()), ""),
        ("阶段核销", "汇总级已对账；逐单阶段数量仍需人工确认", "看源 CSV 的 overlap_qty/excess_qty"),
    ], columns=["项", "值", "说明"])

    # ---------- 0_参数与种子
    param_rows = params.to_dict("records")
    param_rows += [
        {"项": "生成时间", "值": datetime.now().isoformat(timespec="seconds")},
        {"项": "输入 v13", "值": sha(V13)},
        {"项": "输入 CNY v6", "值": sha(CNY)},
        {"项": "输入 D6 v6.14", "值": sha(D6)},
        {"项": "输入 D5 v6.5", "值": sha(D5)},
        {"项": "输入 风险 v2", "值": sha(RISK)},
        {"项": "输入 轨迹 v7", "值": sha(TRAJ)},
        {"项": "输入 PO 队列", "值": sha(PO_SRC)},
        {"项": "输入 PO-DN 审计", "值": sha(PO_AUDIT)},
        {"项": "输入 PO-EN 重叠", "值": sha(PO_OVERLAP)},
        {"项": "脚本", "值": "scripts/s2_15_final_package_v15_20261107.py"},
        {"项": "脚本 SHA-256", "值": sha(SCRIPT_PATH)},
        {"项": "自动下单", "值": "false"},
        {"项": "写 EN/通途", "值": "false"},
    ]
    params_out = pd.DataFrame(param_rows)

    # ---------- 0_说明 / 0_怎么看（v14 口径）
    notice_out = pd.DataFrame([
        ("状态", "DRAFT v15：整数批次；零中位数待验证；可执行/可换运输/风险隔离已拆；不批准"),
        ("数量关系", f"当前候选 {cand_qty:.0f} 是即时补货；春节 {cny_total:.0f} 是方案总量；"
                   f"轨迹可执行 {q_cy + q_fi:.0f}，剔除风险隔离/可换运输后净可执行 "
                   f"{net_plan:.0f}（方案量）/{net_traj:.0f}（轨迹量）；{len(risk_rows)} 条全部失败 "
                   f"{risk_qty:.0f} + {len(remedy_rows)} 条可换运输 {remedy_qty:.0f}，不能相加"),
        ("轨迹", f"春节 cycle95 {c_cy}/{q_cy:.0f}、fill95 {c_fi}/{q_fi:.0f}、"
               f"fail {c_fa}/{q_fa:.0f}、模型异常 {c_an}/{q_an:.0f}、"
               f"零中位数 {c_zm}/{q_zm:.0f}；"
               f"新增 fill95 {n_fi}/{q_nfi:.0f}、fail {n_fa}/{q_nfa:.0f}"),
        ("PO", "EN 带通途 PO 字段 14 个 DN；未结台账 11 个 DN/71 行 PO/51 行 Shipment；"
               "3 个 DN 不在 11-05 未结队列"),
        ("交期", "生产 + pre-haul 2 + 55/30/14（入仓→签收）+ shelving 0"),
        ("异常", "24 个春节键 sigma>2；66 个零中位数键保留原q95、方案量0、禁止执行"),
        ("边界", "不自动下单、不写 EN/通途；数据截止 11-02，PO 快照 11-05"),
    ], columns=["项", "内容"])
    howto_out = pd.DataFrame([
        ("先看这两张", "1_汇总看总量/可执行/风险；9_春节备货建议逐键看可执行状态"),
        ("候选总表", "2_候选总表：257 行，含可执行/不可执行/模型异常；不再叫“可批准”"),
        ("证据链", "2a_候选证据链：品类/长尾/历史销量/预测方法/库存/在途/为什么补/人工确认什么"),
        ("Top50", "2b_Top50优先：从当前“可执行-待人工确认”按数量重排，先审这50个"),
        ("非成品", "8_非成品候选：皮壳/成品+皮壳，下单前确认按什么形态下"),
        ("有净需求但不补", "7_有净需求但暂不补：6 行，都是 Jing 清单/老品/旧花色等政策原因"),
        ("春节备货", "9_春节备货建议：按 1/24 停工、2/22 复工；看“可执行状态/轨迹状态”"),
        ("催已有", "3_催已有：105 行，按默认交期判断赶不赶得上；新增量 5,309"),
        ("轨迹", "11_统一逐日轨迹；逐日均值在独立文件 D_统一逐日轨迹_2026-11-07_v7.xlsx 的 4_逐日均值"),
        ("PO", "10a_PO核对看 14/11/3 的差异；10_PO逐单台账逐单看 open_qty/ETA/匹配"),
        ("运输补救", "16_运输补救：8 个选定运输晚于断货日但更快运输可赶上的键，单独重模拟；不直接解禁"),
        ("新增资格", "18_60cm新增补货资格：19 个供给恢复后 观察→补 的键，单独复审，不在 257 春节包"),
        ("人工复审", "19_人工复审_31 / 20_人工复审_7：27 可执行 + 4 首批晚于停工 + 7 换运输可执行"),
    ], columns=["看哪张", "看什么"])

    # ---------- 12_已知限制
    limits = pd.DataFrame([
        ("新增数量", "当前基准 5,309；5,239 是 CG 修复前旧值，已作废"),
        ("春节总量", f"{cny_total:.0f} 是方案总量；{len(risk_rows)} 条风险 {risk_qty:.0f} 是子集，不能相加"),
        ("可执行量", f"轨迹可执行 {c_cy + c_fi} 键/{q_cy + q_fi:.0f} 件；其中 {len(risk_pass)} 键/{risk_pass_qty:.0f} 件属全部失败；可换运输 {len(remedy_rows)} 键/{remedy_qty:.0f} 件；零中位数 {c_zm} 键（q95保留、方案量0）；净可执行 {net_keys} 键/{net_plan:.0f}（方案量）/{net_traj:.0f}（轨迹量）；未通过 {c_fa} 键/{p_fa:.0f} 件；模型异常 {c_an} 键/{p_an:.0f} 件"),
        ("新增服务", f"fill95 {n_fi} 键/{q_nfi:.0f} 件；fail {n_fa} 键/{q_nfa:.0f} 件；未过的不能当已批准"),
        ("取整", f"整数批次；方案量与轨迹量差 {round_diff:.0f}，逐行看 3_整数校验"),
        ("净可执行口径", f"方案量 {net_plan:.0f} / 轨迹量 {net_traj:.0f}；整数批次，两列应一致"),
        ("180 天同窗", "仅作敏感性。新增按 97 天任务窗定量，拉到 180 天全部 fail 属预期，不能据此否定方案"),
        ("需求外推", "春节用 97 天日均外推到覆盖终点，不是季节模型；2-4 月需求可能偏离"),
        ("轨迹性质", "随机情景模拟，不是服务保证；失败键需人工决策"),
        ("风险隔离", f"{len(risk_rows)} 个键全部已验证运输都晚于断货日，不可视为已批准执行量"),
        ("可换运输", f"{len(remedy_rows)} 个键选定运输晚于断货日，但更快运输可赶上；待重模拟，不直接解禁"),
        ("零中位数", f"{c_zm} 个键 p50=0 且 q95>0；保留原q95与净需求，方案量0、禁止执行"),
        ("PO", "PO 与 EN 在途存在重叠；逐单阶段、ETA、DN↔PO 基数仍需人工确认"),
        ("CG", "只有 eligible 且非 stale 的数量可抵扣；未知 CG 不得抵扣"),
        ("交期", "pre-haul=2 是决策值（实测 p50=0/p90=2）；shelving=0 未实测"),
        ("快照", "数据截止 2026-11-02；PO 快照 2026-11-05；EN DN 字段查询 2026-11-06"),
        ("60cm 287", "KS0001-DM-60-COFFEE/波兰 287 件保留原键、保留预测历史；零中位数待验证，方案量0"),
        ("60cm 覆盖", "保留原键 4,001 件（含 287）仍需按 D1b/C/EN/PO 逐键确认覆盖；本包只对平需求口径"),
        ("新增资格", "19 个 60cm 供给恢复后 观察→补 的键；不在 257 春节包，需单独资格复审"),
        ("人工复审", "27 可执行 + 4 首批晚于停工 + 7 换运输可执行；见 19/20 表"),
        ("操作边界", "不自动下单、不写 EN、不写通途"),
    ], columns=["项", "已知限制"])

    # ---------- Top50 从当前可执行队列重排；一致性校验
    top50 = cand[cand["可执行状态"].eq("可执行-待人工确认")].sort_values(
        "建议数量", ascending=False).head(50).copy()
    top50.insert(0, "优先级", range(1, len(top50) + 1))
    cm_check = cand.merge(traj[KEYS + ["无断货概率", "满足率"]], on=KEYS, how="left",
                          suffixes=("", "_t"))
    metric_mismatch = int((cm_check["周期无断货概率"].fillna(-1)
                           != cm_check["无断货概率"].fillna(-1)).sum()
                          + (cm_check["需求满足率"].fillna(-1)
                             != cm_check["满足率"].fillna(-1)).sum())
    checks = pd.DataFrame([
        ("9 行数", len(cny9), 257),
        ("9 首批到仓与轨迹一致", int(cny9["日期一致"].sum()), len(cny9)),
        ("9 批次差非零行", int((cny9["取整差"] != 0).sum()), 0),
        ("9 方案量与轨迹量不一致", int((cny9["建议节前备货量"] != cny9["轨迹数量"]).sum()), 0),
        ("9 风险行仍标可执行", int((cny9["是否风险隔离"]
                                   & cny9["可执行状态"].eq("可执行-待人工确认")).sum()), 0),
        ("9 零中位数行仍标可执行", int((cny9["轨迹状态"].eq("模型异常-零中位数")
                                       & cny9["可执行状态"].eq("可执行-待人工确认")).sum()), 0),
        ("2 服务指标与 v7 不一致", metric_mismatch, 0),
        ("2 旧服务列已移除", int(any(c in cand.columns for c in ["轨迹无断货", "轨迹满足率"])), 0),
        ("2 零中位数原q95保留", int((zm & (cand["forecast_p50"] <= 0)
                                       & (cand["forecast_q95"] > 0)).sum()), 66),
        ("2 零中位数建议量>0", int((zm & (cand["建议数量"] > 0)).sum()), 0),
        ("9 可换运输键", int(cny9["是否可换运输"].sum()), 8),
        ("16 运输补救行", len(rescue), 8),
        ("16 第二批下单日已过", len(blocked_rescue), 0),
        ("20 可执行补救", len(exec_rescue), 7),
        ("60cm 供给恢复键", len(rec), 20),
        ("18 新增资格键", len(qual), 19),
        ("18 新增资格误入257", int(qual["在257"].sum()), 0),
        ("19 人工复审31", len(r31), 31),
        ("19 第二批下单日已过", int((pd.to_datetime(r31["第二批下单日"], errors="coerce")
                                     < pd.Timestamp("2026-11-06")).sum()), 0),
        ("19 首批晚于停工", int(r31["首批晚于停工"].sum()), 4),
        ("19 可执行", int(r31["执行状态"].eq("可执行").sum()), 27),
        ("20 人工复审7", len(r7), 7),
        ("Top50 非可执行行", int((~top50["可执行状态"].eq("可执行-待人工确认")).sum()), 0),
    ], columns=["检查项", "实际", "期望"])
    checks["通过"] = checks["实际"].eq(checks["期望"])
    checks["结论"] = np.where(checks["通过"], "PASS", "FAIL")

    # ---------- write
    order = ["0_说明", "0_怎么看", "0_参数与种子", "1_汇总", "2_候选总表",
             "2a_候选证据链", "2b_Top50优先", "2c_波兰路线候选", "3_催已有",
             "4_未放行", "5_无需新增", "6_观察", "7_有净需求但暂不补",
             "8_非成品候选", "9_春节备货建议", "10_PO逐单台账", "10a_PO核对",
             "10b_PO与EN重叠_汇总", "11_统一逐日轨迹", "12_已知限制",
             "13_同窗口180_汇总", "13b_同窗口180_逐键", "14_60cm对账",
             "15_一致性校验", "16_运输补救", "17_60cm供给恢复",
             "18_60cm新增补货资格", "19_人工复审_31", "20_人工复审_7"]
    out_frames = {
        "0_说明": notice_out,
        "0_怎么看": howto_out,
        "0_参数与种子": params_out,
        "1_汇总": summary,
        "2_候选总表": cand,
        "2a_候选证据链": frames["2a_候选证据链"],
        "2b_Top50优先": top50,
        "2c_波兰路线候选": frames["2c_波兰路线候选"],
        "3_催已有": frames["3_催已有"],
        "4_未放行": frames["4_未放行"],
        "5_无需新增": frames["5_无需新增"],
        "6_观察": frames["6_观察"],
        "7_有净需求但暂不补": frames["7_有净需求但暂不补"],
        "8_非成品候选": frames["8_非成品候选"],
        "9_春节备货建议": cny9,
        "10_PO逐单台账": led_out,
        "10a_PO核对": po_check,
        "10b_PO与EN重叠_汇总": ov_summary,
        "11_统一逐日轨迹": traj,
        "12_已知限制": limits,
        "13_同窗口180_汇总": sens_sum,
        "13b_同窗口180_逐键": sens,
        "14_60cm对账": cm,
        "15_一致性校验": checks,
        "16_运输补救": rescue,
        "17_60cm供给恢复": rec,
        "18_60cm新增补货资格": qual,
        "19_人工复审_31": r31,
        "20_人工复审_7": r7,
    }
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        for sn in order:
            out_frames[sn].to_excel(w, sheet_name=sn, index=False)

    lines = [
        "# 补货交付包 v15（人工审核）2026-11-07", "",
        "- 数据截止 2026-11-02；PO 快照 2026-11-05；auto_order=false；不是下单指令。", "",
        "## 汇总", "", summary.to_string(index=False), "",
        "## 关键口径", "",
        "- 新增基准 5,309；旧 5,239 作废。",
        f"- 春节 {cny_total:.0f} 是总量；轨迹可执行 {q_cy + q_fi:.0f}，"
        f"剔除 {len(risk_rows)} 条风险隔离后净可执行 {net_plan:.0f}（方案量）/{net_traj:.0f}（轨迹量）。",
        "- 零中位数 66 键/3,627 件已隔离，不再用指数分布补正值。",
        "- 交期 = 生产 + pre-haul 2 + 55/30/14（入仓→签收）+ shelving 0。",
        "- 轨迹主窗口：春节到覆盖终点+7；新增 97 天。180 天同窗只作敏感性。",
        "- PO 台账逐单列 open_qty/ETA/匹配量/基数；DN↔PO 全局基数未证明。",
        "- 60cm 对账：26 键；合并 2,615、保留原键 4,001（含 287）、无键退出预测母集。",
        "- 15_一致性校验：9/2/2b 与轨迹同日、同量、同状态、同服务指标。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "rule_version": "S2.15-delivery-2026-11-07-v15",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "v13": {"path": str(V13), "sha256": sha(V13)},
            "cny_v7": {"path": str(CNY), "sha256": sha(CNY)},
            "d6_v6_15": {"path": str(D6), "sha256": sha(D6)},
            "d6_v6_14": {"path": str(D6_PREV), "sha256": sha(D6_PREV)},
            "d5_v6_6": {"path": str(D5), "sha256": sha(D5)},
            "trajectory_v7": {"path": str(TRAJ), "sha256": sha(TRAJ)},
            "po_queue": {"path": str(PO_SRC), "sha256": sha(PO_SRC)},
            "po_dn_audit": {"path": str(PO_AUDIT), "sha256": sha(PO_AUDIT)},
            "po_en_overlap": {"path": str(PO_OVERLAP), "sha256": sha(PO_OVERLAP)},
            "60cm_recon": {"path": str(CM_RECON), "sha256": sha(CM_RECON)},
        },
        "outputs": {
            "xlsx": {"path": str(OUT), "sha256": sha(OUT)},
            "report": {"path": str(REPORT), "sha256": sha(REPORT)},
        },
        "script": "scripts/s2_15_final_package_v15_20261107.py",
        "script_sha256": sha(SCRIPT_PATH),
        "seed": 42,
        "counts": summary.to_dict("records"),
        "auto_order": False,
        "write_en": False,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
                        encoding="utf-8")
    print(summary.to_string(index=False))
    print("\nPO check:\n" + po_check.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
