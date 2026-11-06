# -*- coding: utf-8 -*-
"""Build the 2026-11-06 human-review delivery package from S2.9 + D6 v6.6.

Three separated outputs, per the independent review:
1) service-qualified replenishment candidates (cycle95 / fill95),
2) expedite-existing list (ETA to be confirmed),
3) not-released list with the missing evidence and owner.

No EN/Tongtong writes; auto_order=false; quantities are candidates, not orders.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path("D:/Work/fzh-order-store/analysis")
S29 = BASE / "S2_9-fresh-20261106/S2_9每日服务验证_2026-11-06.xlsx"
D6 = BASE / "D6v6_6-fresh20261106/D_Top50沙盒_D6_v6_6_fresh_2026-11-06.xlsx"
D5 = BASE / "D5v6_4-full/D_概率与服务_D5_v6_4_2026-11-05.xlsx"
SERIES = BASE / "D3b_v3_5_series_current_2026-11-03.parquet"
B2 = BASE / "business_category_scope_20261103.csv"
OUTDIR = BASE / "S2_9-delivery-fresh-20261106"
OUT = OUTDIR / "D_补货交付包_2026-11-06_fresh.xlsx"
REPORT = OUTDIR / "D_补货交付包_2026-11-06_fresh_报告.md"
MANIFEST = OUTDIR / "D_补货交付包_2026-11-06_fresh.manifest.json"


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    OUTDIR.mkdir(exist_ok=True)
    s = pd.read_excel(S29, sheet_name="1_逐键服务")
    d6 = pd.read_excel(D6, sheet_name="1_全量动作")
    keys = ["product_id", "pool", "physical_form", "canonical_uom"]
    d6k = d6.rename(columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})[
        keys + ["需求形态", "C可发供给", "en_stock在途+待发", "PO追加(去重)",
                "在途ETA_p50", "净需求95", "需要日", "下单日", "推荐main_haul",
                "路线状态", "建议动作", "动作原因", "b2_scope"]]
    s = s.merge(d6k, on=keys, how="left", suffixes=("", "_d6"))

    # ---------- evidence chain: category, long-tail, sales, forecast method
    b2 = pd.read_csv(B2, encoding="utf-8-sig").rename(columns={"EN物料": "product_id"})
    b2 = b2[[c for c in ["product_id", "family", "fabric", "replenish_scope",
                          "A_active_class", "C_stock", "owner"] if c in b2.columns]]
    b2 = b2.drop_duplicates("product_id")
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5["horizon"].astype(str) == "97"].drop_duplicates(keys)[
        keys + ["model", "adopted_model", "interval_level", "calibration_n", "p50"]]
    cur = pd.read_parquet(SERIES)
    cur["date"] = pd.to_datetime(cur["date"], errors="coerce")
    end = pd.Timestamp("2026-11-02")
    cur = cur[(cur["date"] > end - pd.Timedelta(days=90)) & (cur["date"] <= end)].copy()
    sales90 = cur.groupby(keys, as_index=False)["qty"].sum().rename(columns={"qty": "近90天销量"})
    cur180 = pd.read_parquet(SERIES)
    cur180["date"] = pd.to_datetime(cur180["date"], errors="coerce")
    cur180 = cur180[(cur180["date"] > end - pd.Timedelta(days=180))
                    & (cur180["date"] <= end)]
    sales180 = cur180.groupby(keys, as_index=False)["qty"].sum().rename(
        columns={"qty": "近180天销量"})
    ev = s.merge(b2, on="product_id", how="left")
    ev = ev.merge(d5, on=keys, how="left")
    ev = ev.merge(sales90, on=keys, how="left").merge(sales180, on=keys, how="left")

    pattern_cn = {"smooth": "平稳", "intermittent": "间歇", "lumpy": "波动大",
                  "new": "新品", "obsolescent": "衰退"}
    calib_cn = {"asof_us_total_product": "同产品美国总需求历史误差",
                "asof_us_total_market_form_uom": "美国同形态/单位池历史误差",
                "asof_product_any_pool": "同产品历史误差",
                "asof_market_form_uom": "市场同形态历史误差",
                "none": "无足够历史样本"}

    def human_reason(r):
        q = pd.to_numeric(r.get("q95"), errors="coerce")
        sup = pd.to_numeric(r.get("C可发供给"), errors="coerce")
        inb = pd.to_numeric(r.get("en_stock在途+待发"), errors="coerce")
        po = pd.to_numeric(r.get("PO追加(去重)"), errors="coerce")
        net = pd.to_numeric(r.get("净需求95"), errors="coerce")
        parts = []
        if pd.notna(q):
            parts.append(f"97天需求95分位 {q:.0f}")
        if pd.notna(sup):
            parts.append(f"C可发 {sup:.0f}")
        if pd.notna(inb):
            parts.append(f"EN在途/待发 {inb:.0f}")
        if pd.notna(po) and po:
            parts.append(f"PO追加 {po:.0f}")
        if pd.notna(net):
            parts.append(f"净缺口 {net:.0f}")
        return "；".join(parts)

    def human_confirm(r):
        remedy = str(r.get("remedy") or "")
        if "提前下单" in remedy and "升舱" in remedy:
            return "确认今天可下单/排产，并确认升舱舱位与运价"
        if "提前下单" in remedy and "加量" in remedy:
            return "确认今天可下单/排产，并确认加量后的库存与资金"
        if "提前下单" in remedy:
            return "确认今天可下单/生产排期"
        if "升舱" in remedy:
            return "确认升舱舱位与运价"
        return "确认需求口径（促销/新品/渠道）与可下单时点"

    ev["品类"] = ev["family"].astype(str)
    ev["面料"] = ev["fabric"].astype(str)
    ev["B2范围"] = ev["replenish_scope"].astype(str)
    ev["活跃分类"] = ev["A_active_class"].astype(str)
    ev["需求形态_人话"] = ev["需求形态"].map(pattern_cn).fillna(ev["需求形态"].astype(str))
    ev["预测方法"] = ev["model"].astype(str) + "（采用 " + ev["adopted_model"].astype(str) + "）"
    ev["区间校准"] = ev["interval_level"].map(calib_cn).fillna(ev["interval_level"].astype(str))
    ev["同类历史误差样本数（池化）"] = ev["calibration_n"]
    ev["为什么补"] = [human_reason(r) for r in ev.to_dict("records")]
    ev["人工确认什么"] = [human_confirm(r) for r in ev.to_dict("records")]
    ev["历史销量"] = ("近90天 " + pd.to_numeric(ev["近90天销量"], errors="coerce")
                    .fillna(0).round(0).astype(int).astype(str)
                    + " / 近180天 " + pd.to_numeric(ev["近180天销量"], errors="coerce")
                    .fillna(0).round(0).astype(int).astype(str))
    ev["服务水平"] = np.where(ev["status"].eq("pass_cycle"),
                           "周期无断货≥95%", "需求满足率≥95%（周期<95%）")
    method_cn = {"snaive": "季节朴素（去年同月）", "sba": "间歇需求 SBA",
                 "tsb": "间歇需求 TSB", "ma3": "近3月均值",
                 "ets_ann": "年季节指数平滑", "naive": "上期值"}
    ev["方法说明"] = ev["adopted_model"].map(method_cn).fillna("见模型名")
    ev["建议运输方式"] = ev["chosen_mode"].astype(str)
    q180 = pd.to_numeric(ev["近180天销量"], errors="coerce").fillna(0)
    ev["销量档（长尾）"] = np.where(q180 <= 0, "无销量",
                             np.where(q180 <= 10, "极低量/长尾",
                                      np.where(q180 <= 50, "低量/长尾",
                                               np.where(q180 <= 200, "中量", "高量"))))
    inb_sum = (pd.to_numeric(ev["en_stock在途+待发"], errors="coerce").fillna(0)
               + pd.to_numeric(ev["PO追加(去重)"], errors="coerce").fillna(0))
    ev["在途/PO单据核实"] = np.where(inb_sum > 0, "是：需发运日/PO号/阶段", "无")
    ev["ETA来源"] = ev["eta_basis"].astype(str)
    no_hist_floor = (pd.to_numeric(ev["p50"], errors="coerce").fillna(0) <= 0) &                     ev["interval_level"].astype(str).str.startswith("asof_us_total")
    ev["需求依据"] = np.where(
        no_hist_floor,
        "无本品历史：按美国同形态池残差95分位作需求情景（政策，非本品实测）",
        np.where(pd.to_numeric(ev["p50"], errors="coerce").fillna(0) > 0,
                 "本品历史预测 + 同步总需求校准", "无足够历史"))

    pass_mask = s["status"].isin(["pass_cycle", "pass_fill"])
    cand = s[pass_mask].copy()
    cand["放行等级"] = np.where(cand["status"].eq("pass_cycle"),
                            "A级-周期95%", "B级-满足率95%")
    cand["建议动作"] = "补货"
    cand["建议下单时点"] = np.where(
        cand["remedy"].str.contains("提前下单", na=False), "今天（2026-11-06）", "按D6下单日")
    cand["建议下单日"] = np.where(
        cand["remedy"].str.contains("提前下单", na=False),
        "2026-11-06", cand["下单日"].astype(str))
    cand["是否需人工确认"] = "是"
    cand["自动下单"] = False
    cand["建议运输方式"] = cand["chosen_mode"].astype(str)
    cols = ["product_id", "pool", "physical_form", "canonical_uom", "需求形态",
            "放行等级", "建议动作", "建议下单时点", "建议下单日", "remedy",
            "q_sim", "q95", "净需求95", "C可发供给", "en_stock在途+待发",
            "PO追加(去重)", "在途ETA_p50", "需要日", "下单日", "mode",
            "建议运输方式", "route_status", "route_warning", "arrival_prob",
            "no_stockout_prob", "fill_rate", "mean_stockout_days",
            "mean_inventory", "production_basis", "headhaul_basis", "eta_basis",
            "是否需人工确认", "自动下单"]
    cand = cand[cols].rename(columns={
        "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
        "q_sim": "建议数量", "q95": "需求q95", "mode": "原运输方式",
        "route_warning": "路线小样本提示", "arrival_prob": "到货赶上概率",
        "no_stockout_prob": "周期无断货概率", "fill_rate": "需求满足率",
        "mean_stockout_days": "平均断货天数", "mean_inventory": "平均库存",
        "headhaul_basis": "交期依据"}).sort_values(
        ["放行等级", "建议数量"], ascending=[True, False])
    top50 = cand.head(50).copy()
    top50.insert(0, "优先级", range(1, len(top50) + 1))

    ev_cand = ev[ev["status"].isin(["pass_cycle", "pass_fill"])].copy()
    ev_cand["建议数量"] = ev_cand["q_sim"]
    ev_cand["建议下单日"] = np.where(
        ev_cand["remedy"].str.contains("提前下单", na=False),
        "2026-11-06", ev_cand["下单日"].astype(str))
    ev_cols = ["product_id", "pool", "physical_form", "canonical_uom",
               "品类", "面料", "B2范围", "活跃分类", "需求形态_人话",
               "销量档（长尾）", "历史销量", "需求依据", "预测方法", "方法说明", "区间校准",
               "同类历史误差样本数（池化）", "服务水平", "q95", "净需求95",
               "C可发供给", "en_stock在途+待发", "PO追加(去重)", "在途ETA_p50",
               "在途/PO单据核实", "ETA来源", "mode", "建议运输方式", "headhaul_basis",
               "建议数量", "建议下单日", "arrival_prob",
               "no_stockout_prob", "fill_rate", "为什么补", "人工确认什么"]
    ev_cand = ev_cand[[c for c in ev_cols if c in ev_cand.columns]].rename(columns={
        "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
        "q95": "需求q95", "mode": "原运输方式", "arrival_prob": "到货赶上概率",
        "no_stockout_prob": "周期无断货概率", "fill_rate": "需求满足率",
        "headhaul_basis": "交期依据"})
    ev_cand["数据截止"] = "2026-11-02"
    ev_cand["自动下单"] = False

    expedite = s[s["status"] == "expedite_pending"].copy()
    pl_cand = s[s["status"].isin(["pass_route_contract", "pass_air_scenario"])].copy()
    pl_cand["路线状态说明"] = np.where(
        pl_cand["status"].eq("pass_route_contract"),
        "专线经验可行，待承运商合同确认",
        "空运规划情景可行，待报价/合同确认")
    pl_cand["建议动作"] = "补货（时间可行，合同待确认）"
    expedite["待确认"] = "催后 ETA、对应单据、目的仓"
    expedite["建议动作"] = "催已有（不新增）"

    not_released = s[s["status"].isin(
        ["route_unknown", "supply_unknown", "fail_arrival", "fail_service"])].copy()
    not_released["缺什么证据"] = not_released["status"].map({
        "route_unknown": "运输路线/承运商合同；波兰三类映射",
        "supply_unknown": "C 完整供给键或已批形态适配",
        "fail_arrival": "空运仍赶不上：需提前下单或接受断货风险",
        "fail_service": "加量/提前下单/升舱组合仍不足：需复核需求与供给",
    })
    not_released["责任方"] = not_released["status"].map({
        "route_unknown": "物流/Jack", "supply_unknown": "计划/EN",
        "fail_arrival": "计划/业务", "fail_service": "计划/业务"})

    def humanize(frame, extra):
        keep = ["product_id", "pool", "physical_form", "canonical_uom", "action",
                "mode", "chosen_mode", "q_sim", "q95", "C可发供给", "en_stock在途+待发",
                "PO追加(去重)", "在途ETA_p50", "需要日", "下单日",
                "route_status", "route_basis", "status", "reason",
                "route_warning"] + extra
        keep = [c for c in keep if c in frame.columns]
        return frame[keep].rename(columns={
            "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
            "action": "D6动作", "mode": "原运输方式",
            "chosen_mode": "建议运输方式", "q_sim": "涉及数量",
            "q95": "需求q95", "route_warning": "路线小样本提示",
            "route_basis": "路线依据", "status": "状态", "reason": "原因"})

    expedite = humanize(expedite, ["建议动作", "待确认"])
    mode_days = {"空运": 14, "快船": 30, "普船": 55, "专线": 60}
    expedite["默认交期天数"] = expedite["建议运输方式"].map(mode_days).fillna(55).astype(int)
    expedite["按默认交期到仓"] = (
        pd.Timestamp("2026-11-06")
        + pd.to_timedelta(expedite["默认交期天数"], unit="D")).dt.date.astype(str)
    need = pd.to_datetime(expedite["需要日"], errors="coerce")
    arr = pd.to_datetime(expedite["按默认交期到仓"], errors="coerce")
    expedite["默认交期是否赶得上"] = np.where(
        need.notna() & arr.notna(),
        np.where(arr <= need, "赶得上", "赶不上"), "日期未知")
    pl_cand = humanize(pl_cand, ["建议动作", "路线状态说明"])
    not_released = humanize(not_released, ["缺什么证据", "责任方"])

    no_action = s[s["status"] == "not_action"].copy()
    no_action = no_action.merge(ev[keys + ["需求依据"]], on=keys, how="left")
    no_new = no_action[no_action["建议动作"] == "不补"].copy()
    observe = no_action[no_action["建议动作"] == "观察"].copy()

    def action_view(frame):
        keep = ["product_id", "pool", "physical_form", "canonical_uom",
                "建议动作", "动作原因", "b2_scope", "净需求95", "需求依据"]
        keep = [c for c in keep if c in frame.columns]
        out = frame[keep].rename(columns={
            "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
            "b2_scope": "B2范围"})
        out["责任方"] = "业务/计划（按动作原因确认）"
        return out

    no_new_out = action_view(no_new)
    observe_out = action_view(observe)
    observe_pos = observe_out[pd.to_numeric(observe_out["净需求95"], errors="coerce") > 0].copy()
    nonfinished = cand[cand["形态"].astype(str).isin(["皮壳", "成品+皮壳"])].copy()

    summary = pd.DataFrame([
        ("可批准候选（A 周期95%）", int((cand["放行等级"] == "A级-周期95%").sum()),
         float(cand.loc[cand["放行等级"] == "A级-周期95%", "建议数量"].sum())),
        ("可批准候选（B 满足率95%）", int((cand["放行等级"] == "B级-满足率95%").sum()),
         float(cand.loc[cand["放行等级"] == "B级-满足率95%", "建议数量"].sum())),
        ("波兰时间可行（待合同/报价）", len(pl_cand), float(pd.to_numeric(
            pl_cand["涉及数量"], errors="coerce").fillna(0).sum())),
        ("催已有（待 ETA）", len(expedite), float(pd.to_numeric(
            expedite["涉及数量"], errors="coerce").fillna(0).sum())),
        ("未放行（路线/供给/服务）", len(not_released),
         float(pd.to_numeric(not_released["涉及数量"], errors="coerce").fillna(0).sum())),
        ("不补（覆盖足够）", len(no_new), 0.0),
        ("观察（政策/数据/共享/CG）", len(observe), 0.0),
    ], columns=["类别", "键数", "数量"])
    summary["说明"] = [
        "P(全程无断货)>=95% 且 到货赶上>=95%",
        "需求满足率>=95% 且 到货赶上>=95%，周期无断货未达95%",
        "专线/空运情景下时间可行；承运商合同或报价待确认",
        "已有供给可催；ETA/单据需核实，不新增",
        "见逐项缺证与责任方",
        "净需求<=0；无需新增",
        "政策排除/数据未覆盖/共享/CG；逐行动作原因见 6_观察",
    ]

    notice = pd.DataFrame([
        ("交付日", "2026-11-06"),
        ("数据截止", "2026-11-02"),
        ("决策/下单日", "2026-11-06"),
        ("用途", "人工审核候选；不是下单指令"),
        ("自动下单", "false"),
        ("可批准候选", "A 级为周期服务 95%；B 级为满足率 95%，两者不可混同"),
        ("主要建议", "绝大多数候选需要“提前下单至今天”才能达到服务目标；D6 原下单日不足以覆盖交期尾部"),
        ("证据链", "2a 表逐行列出品类/需求形态/历史销量/预测方法/校准样本/库存/在途/为什么补/人工确认什么"),
        ("数据来源", "销量=D3b v3.5 当前owner日销量；预测=D5 v6.4；库存=C刷新4_可发供给；EN供给=EN库存快照2026-11-02；服务=S2.9模拟"),
        ("路线限制", "波兰 506 键已用 120 条完成运单建立“专线”经验情景；3 键时间可行待合同，其余经验尾部超出保护窗；美中 82 条快递派送 + 29 条空运尾程"),
        ("催已有兜底", "无 ETA 时按默认交期估算：空运14/快船30/普船55/专线60天；3_催已有列“默认交期是否赶得上”"),
        ("未放行", "缺路线/供给/服务证据；逐项列责任方，不当作 0 或已批准"),
        ("有净需求但暂不补", "6_观察中净需求>0 的行（约57）；原因是品类不在 Jing 清单/旧花色/共享/CG，详见 7 表"),
        ("B2 是什么", "Jing 确认的补货品类清单：USNJ_continue=可补，observe_*=观察，old_no_replenish=老品不补"),
        ("非成品候选", "8 表中的皮壳/成品+皮壳；下单前需确认按成品还是皮壳下单"),
        ("唯一键", "(product_id, 池, 形态, UOM)；不是仅 product_id（1,217 个产品对应 1,749 行）"),
        ("波兰口径", "全池 735：可动用 506（3 时间可行 + 12 催已有 + 491 到货失败），另 199 不补 + 30 观察"),
        ("非成品行", "246 个美国候选中 8 行为皮壳/成品+皮壳，需按下单/工单口径单独确认"),
        ("数量口径", "个；成品 MOQ=n/a（自有绍兴工厂）"),
    ], columns=["项", "内容"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        notice.to_excel(w, sheet_name="0_说明", index=False)
        summary.to_excel(w, sheet_name="1_汇总", index=False)
        cand.to_excel(w, sheet_name="2_可批准候选", index=False)
        ev_cand.to_excel(w, sheet_name="2a_候选证据链", index=False)
        top50.to_excel(w, sheet_name="2b_Top50优先", index=False)
        pl_cand.to_excel(w, sheet_name="2c_波兰路线候选", index=False)
        expedite.to_excel(w, sheet_name="3_催已有", index=False)
        not_released.to_excel(w, sheet_name="4_未放行", index=False)
        no_new_out.to_excel(w, sheet_name="5_无需新增", index=False)
        observe_out.to_excel(w, sheet_name="6_观察", index=False)
        observe_pos.to_excel(w, sheet_name="7_有净需求但暂不补", index=False)
        nonfinished.to_excel(w, sheet_name="8_非成品候选", index=False)

    lines = [
        "# 补货交付包（人工审核）2026-11-06", "",
        "- 数据截止 2026-11-02；auto_order=false；不是下单指令。", "",
        "## 汇总", "", summary.to_string(index=False), "",
        "## 口径", "",
        "- A：P(全程无断货)>=95% 且 P(到货<=需要日)>=95%。",
        "- B：需求满足率>=95% 且 P(到货<=需要日)>=95%，但周期无断货<95%。",
        "- 生产样本：2026-05 起去重 SO-DN 事件，保留真实尾部。",
        "- 头程：按目的区域分层；美中小样本已标注。",
        "- 建议时点：绝大多数为“提前下单至今天”；D6 原下单日不足以覆盖尾部。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "rule_version": "S2.9-delivery-2026-11-06",
        "inputs": {"s2_9": {"path": str(S29), "sha256": sha(S29)},
                   "d6": {"path": str(D6), "sha256": sha(D6)}},
        "outputs": {"xlsx": {"path": str(OUT), "sha256": sha(OUT)},
                    "report": {"path": str(REPORT), "sha256": sha(REPORT)}},
        "counts": summary.to_dict("records"), "auto_order": False,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
                        encoding="utf-8")
    print(json.dumps(summary.to_dict("records"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
