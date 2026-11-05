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
S29 = BASE / "S2_9-daily-service-20261105/S2_9每日服务验证_2026-11-05.xlsx"
D6 = BASE / "D6v6_6-final/D_Top50沙盒_D6_v6_6_2026-11-05.xlsx"
OUTDIR = BASE / "S2_9-delivery-20261106"
OUT = OUTDIR / "D_补货交付包_2026-11-06.xlsx"
REPORT = OUTDIR / "D_补货交付包_2026-11-06_报告.md"
MANIFEST = OUTDIR / "D_补货交付包_2026-11-06.manifest.json"


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
                "路线状态", "建议动作"]]
    s = s.merge(d6k, on=keys, how="left", suffixes=("", "_d6"))

    pass_mask = s["status"].isin(["pass_cycle", "pass_fill"])
    cand = s[pass_mask].copy()
    cand["放行等级"] = np.where(cand["status"].eq("pass_cycle"),
                            "A级-周期95%", "B级-满足率95%")
    cand["建议动作"] = "补货"
    cand["建议下单时点"] = np.where(
        cand["remedy"].str.contains("提前下单", na=False), "今天（as_of）", "按D6下单日")
    cand["建议下单日"] = np.where(
        cand["remedy"].str.contains("提前下单", na=False),
        "2026-11-02", cand["下单日"].astype(str))
    cand["是否需人工确认"] = "是"
    cand["自动下单"] = False
    cols = ["product_id", "pool", "physical_form", "canonical_uom", "需求形态",
            "放行等级", "建议动作", "建议下单时点", "建议下单日", "remedy",
            "q_sim", "q95", "净需求95", "C可发供给", "en_stock在途+待发",
            "PO追加(去重)", "在途ETA_p50", "需要日", "下单日", "mode",
            "route_status", "route_warning", "arrival_prob", "no_stockout_prob",
            "fill_rate", "mean_stockout_days", "mean_inventory", "production_basis",
            "headhaul_basis", "eta_basis", "是否需人工确认", "自动下单"]
    cand = cand[cols].rename(columns={
        "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
        "q_sim": "建议数量", "q95": "需求q95", "mode": "运输方式",
        "route_warning": "路线小样本提示", "arrival_prob": "到货赶上概率",
        "no_stockout_prob": "周期无断货概率", "fill_rate": "需求满足率",
        "mean_stockout_days": "平均断货天数", "mean_inventory": "平均库存"}).sort_values(
        ["放行等级", "建议数量"], ascending=[True, False])

    expedite = s[s["status"] == "expedite_pending"].copy()
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
                "mode", "q_sim", "q95", "C可发供给", "en_stock在途+待发",
                "PO追加(去重)", "在途ETA_p50", "需要日", "下单日",
                "route_status", "status", "reason", "route_warning"] + extra
        keep = [c for c in keep if c in frame.columns]
        return frame[keep].rename(columns={
            "pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
            "action": "D6动作", "mode": "运输方式", "q_sim": "涉及数量",
            "q95": "需求q95", "route_warning": "路线小样本提示",
            "status": "状态", "reason": "原因"})

    expedite = humanize(expedite, ["建议动作", "待确认"])
    not_released = humanize(not_released, ["缺什么证据", "责任方"])

    no_action = s[s["status"] == "not_action"].copy()
    no_new = no_action[no_action["建议动作"] == "不补"].copy()
    observe = no_action[no_action["建议动作"] == "观察"].copy()

    summary = pd.DataFrame([
        ("可批准候选（A 周期95%）", int((cand["放行等级"] == "A级-周期95%").sum()),
         float(cand.loc[cand["放行等级"] == "A级-周期95%", "建议数量"].sum())),
        ("可批准候选（B 满足率95%）", int((cand["放行等级"] == "B级-满足率95%").sum()),
         float(cand.loc[cand["放行等级"] == "B级-满足率95%", "建议数量"].sum())),
        ("催已有（待 ETA）", len(expedite), float(pd.to_numeric(
            expedite["涉及数量"], errors="coerce").fillna(0).sum())),
        ("未放行（路线/供给/服务）", len(not_released),
         float(pd.to_numeric(not_released["涉及数量"], errors="coerce").fillna(0).sum())),
        ("不补（覆盖足够）", len(no_new), 0.0),
        ("观察（政策/范围外）", len(observe), 0.0),
    ], columns=["类别", "键数", "数量"])
    summary["说明"] = [
        "P(全程无断货)>=95% 且 到货赶上>=95%",
        "需求满足率>=95% 且 到货赶上>=95%，周期无断货未达95%",
        "已有供给可催；ETA/单据需核实，不新增",
        "见逐项缺证与责任方",
        "净需求<=0；无需新增",
        "政策排除/范围外/共享/CG；不进入本次补货",
    ]

    notice = pd.DataFrame([
        ("交付日", "2026-11-06"),
        ("数据截止", "2026-11-02"),
        ("用途", "人工审核候选；不是下单指令"),
        ("自动下单", "false"),
        ("可批准候选", "A 级为周期服务 95%；B 级为满足率 95%，两者不可混同"),
        ("主要建议", "绝大多数候选需要“提前下单至今天”才能达到服务目标；D6 原下单日不足以覆盖交期尾部"),
        ("路线限制", "波兰 506 键路线未确认；美中小样本已用本目的地样本模拟并标注"),
        ("未放行", "缺路线/供给/服务证据；逐项列责任方，不当作 0 或已批准"),
        ("数量口径", "个；成品 MOQ=n/a（自有绍兴工厂）"),
    ], columns=["项", "内容"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        notice.to_excel(w, sheet_name="0_说明", index=False)
        summary.to_excel(w, sheet_name="1_汇总", index=False)
        cand.to_excel(w, sheet_name="2_可批准候选", index=False)
        expedite.to_excel(w, sheet_name="3_催已有", index=False)
        not_released.to_excel(w, sheet_name="4_未放行", index=False)
        no_new.to_excel(w, sheet_name="5_无需新增", index=False)
        observe.to_excel(w, sheet_name="6_观察", index=False)

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
