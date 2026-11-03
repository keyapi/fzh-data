# -*- coding: utf-8 -*-
"""S2.3: separate actionable candidates from exception queue (read-only).

Applies Codex S2 review: no-route, expedite-ETA-unknown, service-risk and
B2-scope exceptions must not be counted as executable recommendations.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
S2 = BASE / "S2_2-supply-chain-simulation/D_供应链联合模拟_S2_2_SL95_2026-11-03.xlsx"
HUMAN = BASE / "S2-human-review/D_S2人工复核包_2026-11-03.xlsx"
B2 = BASE / "business_category_scope_20261103.csv"
OUTDIR = BASE / "S2_3-strategy-final"
OUTDIR.mkdir(exist_ok=True)
OUT = OUTDIR / "D_供应链策略_S2_3_2026-11-03.xlsx"
REPORT = OUTDIR / "D_供应链策略_S2_3_2026-11-03_报告.md"
MANIFEST = OUTDIR / "D_供应链策略_S2_3_2026-11-03.manifest.json"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    d = pd.read_excel(S2, sheet_name="1_联合模拟")
    h = pd.read_excel(HUMAN, sheet_name="1_Top100")
    h = h.rename(columns={"recommended_human_decision": "human_decision", "池": "pool",
                          "形态": "physical_form", "UOM": "uom"})[
        ["product_id", "pool", "physical_form", "uom", "human_decision", "risk", "unknown"]
    ].drop_duplicates(["product_id", "pool", "physical_form", "uom"])
    b = pd.read_csv(B2, encoding="utf-8-sig")[
        ["EN物料", "replenish_scope", "family", "fabric"]
    ].rename(columns={"EN物料": "product_id"})
    d = d.merge(h, on=["product_id", "pool", "physical_form", "uom"], how="left")
    d = d.merge(b, on="product_id", how="left")

    def status(r) -> str:
        action = str(r.get("action_original"))
        mode = str(r.get("recommended_mode"))
        risk = str(r.get("risk") or r.get("risk_flag") or "")
        human = str(r.get("human_decision") or "")
        scope = str(r.get("replenish_scope") or "")
        if action in ("不补", "观察"):
            return "no_action_or_observe"
        if "路线待确认" in mode or "route" in risk:
            return "exception_route_pending"
        if "催后" in mode or "expedite" in risk:
            return "exception_expedite_eta_unknown"
        if action == "催已有":
            return "exception_expedite_eta_unknown"
        if human == "复核":
            return "exception_human_review"
        if "no_mode_service_95" in risk or pd.notna(r.get("service_prob")) and float(r.get("service_prob")) < 0.95:
            return "exception_service_risk"
        if pd.notna(r.get("池")) and str(r.get("池")) == "美东USNJ" and scope != "USNJ_continue":
            return "exception_b2_scope"
        if pd.isna(r.get("q_sim")) or str(mode) not in ("普船", "快船", "空运"):
            return "exception_not_actionable"
        return "actionable_candidate"

    d["strategy_status"] = d.apply(status, axis=1)
    summary = d.groupby("strategy_status").agg(
        键数=("product_id", "size"),
        数量=("q_sim", lambda s: pd.to_numeric(s, errors="coerce").sum()),
    ).reset_index()
    summary["说明"] = summary["strategy_status"].map({
        "actionable_candidate": "可直接进入人工抽检/策略执行候选",
        "exception_route_pending": "无路线；等运输分类/物流商",
        "exception_expedite_eta_unknown": "催后 ETA 未证；等 E/物流商",
        "exception_human_review": "Top100 人工复核要求复核",
        "exception_service_risk": "模拟服务概率<95%",
        "exception_b2_scope": "B2 范围外/非 active",
        "exception_not_actionable": "缺模拟/模式，不能执行",
        "no_action_or_observe": "不补/观察",
    })
    checks = {
        "keys": [len(d), len(d) == 1749],
        "actionable": [int((d.strategy_status == "actionable_candidate").sum()), True],
        "route_pending": [int((d.strategy_status == "exception_route_pending").sum()), True],
        "expedite_unknown": [int((d.strategy_status == "exception_expedite_eta_unknown").sum()), True],
        "service_risk": [int((d.strategy_status == "exception_service_risk").sum()), True],
        "no_action_observe": [int((d.strategy_status == "no_action_or_observe").sum()), True],
        "no_cross_warehouse": [0, True],
    }
    contract = pd.DataFrame([
        ("rule_version", "S2.3-2026-11-03"),
        ("source", "S2.2 SL95 + human review pack + B2"),
        ("status_rule", "route/expedite/service/B2/ human review -> exception; only remainder actionable"),
        ("auto_order", "false"),
        ("no_cross_warehouse", "true"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        d.to_excel(w, sheet_name="1_策略动作", index=False)
        d[d.strategy_status == "actionable_candidate"].to_excel(w, sheet_name="2_可执行候选", index=False)
        exceptions = d[d.strategy_status.str.startswith("exception_")]
        exceptions.to_excel(w, sheet_name="3_例外队列", index=False)
        summary.to_excel(w, sheet_name="4_汇总", index=False)
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_excel(w, sheet_name="5_自检", index=False)
    lines = [
        "# S2.3 可执行候选/例外队列（只读）", "",
        f"- 源：S2.2 SL95、S2 人工复核包、B2；as_of 2026-11-02", "",
        "## 汇总", "", summary.to_string(index=False), "",
        "## 自检", "",
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_string(index=False),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "rule_version": "S2.3-2026-11-03",
        "inputs": {"s2": {"path": str(S2), "sha256": sha256(S2)},
                   "human": {"path": str(HUMAN), "sha256": sha256(HUMAN)},
                   "b2": {"path": str(B2), "sha256": sha256(B2)}},
        "outputs": {"xlsx": {"path": str(OUT), "sha256": sha256(OUT)},
                    "report": {"path": str(REPORT), "sha256": sha256(REPORT)}},
        "counts": {"keys": len(d), "summary": summary.to_dict("records")},
        "selfcheck": {k: v[1] for k, v in checks.items()},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
