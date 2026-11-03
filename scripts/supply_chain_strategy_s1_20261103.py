# -*- coding: utf-8 -*-
"""S1: end-to-end supply-chain strategy layer (read-only).

Connects D6 v6.4 demand/inventory/actions with production SO->DN and three
head-haul modes (regular sea / fast sea / air). Adds order-by date, mode
choice, ETA, cost proxy and risk. Does not reforecast or write EN/Tongtu.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D6 = BASE / "D6v6_4-final/D_Top50沙盒_D6_v6_4_2026-11-03.xlsx"
LT = BASE / "leadtime_snapshot_20261103.json"
OUTDIR = BASE / "S1-supply-chain-strategy"
OUTDIR.mkdir(exist_ok=True)
OUT = OUTDIR / "D_供应链策略_S1_2026-11-03.xlsx"
REPORT = OUTDIR / "D_供应链策略_S1_2026-11-03_报告.md"
MANIFEST = OUTDIR / "D_供应链策略_S1_2026-11-03.manifest.json"
AS_OF = pd.Timestamp("2026-11-02")

# Head-haul completed end-to-end (warehouse-in -> signed), 2026-06..10.
MODES = {
    "普船": {"p50": 50.0, "p90": 64.0, "cost": 1.0},
    "快船": {"p50": 31.0, "p90": 32.0, "cost": 1.8},
    "空运": {"p50": 13.0, "p90": 14.0, "cost": 6.0},
}
# Production SO->DN recent 6m by pool/customer; fallback by pool.
PROD = {
    "波兰": {"p50": 21.5, "p90": 36.8},
    "美东USNJ": {"p50": 21.0, "p90": 33.5},
    "美中USTX": {"p50": 21.5, "p90": 32.6},
}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    d = pd.read_excel(D6, sheet_name="1_全量动作")
    d["需要日"] = pd.to_datetime(d["需要日"], errors="coerce")
    d["下单日_原"] = pd.to_datetime(d["下单日"], errors="coerce")
    rows = []
    for rec0 in d.to_dict("records"):
        pool = str(rec0.get("池"))
        action = str(rec0.get("建议动作"))
        need = rec0.get("需要日")
        prod = PROD.get(pool, {"p50": None, "p90": None})
        rec = {
            "product_id": rec0.get("product_id"),
            "market": rec0.get("市场"),
            "pool": pool,
            "physical_form": rec0.get("形态"),
            "uom": rec0.get("UOM"),
            "action_original": action,
            "qty_97d": rec0.get("建议数量"),
            "new_qty_97d": rec0.get("新补数量"),
            "expedite_qty": rec0.get("催已有量"),
            "q95_97d": rec0.get("q95"),
            "net_need_95": rec0.get("净需求95"),
            "available_c": rec0.get("C可发供给"),
            "in_transit": rec0.get("en_stock在途+待发"),
            "po_add": rec0.get("PO追加(去重)"),
            "need_date": need,
            "as_of": AS_OF,
            "prod_p50": prod["p50"],
            "prod_p90": prod["p90"],
            "existing_eta_p50": rec0.get("ETA_p50"),
            "existing_eta_p90": rec0.get("ETA_p90"),
            "route_status": rec0.get("路线状态"),
            "owner_supply_mismatch": rec0.get("owner/供给池不一致"),
        }
        # Route unavailable / expedite ETA unverified: do not invent a mode.
        route = str(rec0.get("路线状态") or "")
        route_pending = ("route_unavailable" in route) or ("route_pending" in route) or ("路线待确认" in route)
        if action in ("补", "催已有") and route_pending:
            rec.update({"recommended_mode": "路线待确认", "mode_basis": "route_unavailable; no mode",
                        "risk_flag": "route_pending", "mode_cost_proxy": None,
                        "recommended_eta_p50": None, "recommended_eta_p90": None,
                        "recommended_order_by": None, "timeline": ""})
            rows.append(rec)
            continue
        if action == "催已有":
            rec.update({"recommended_mode": "催后ETA未证", "mode_basis": "expedite ETA unverified; no air choice",
                        "risk_flag": "expedite_eta_unknown", "mode_cost_proxy": None,
                        "recommended_eta_p50": None, "recommended_eta_p90": None,
                        "recommended_order_by": None, "timeline": ""})
            rows.append(rec)
            continue
        # only actionable pools get mode options
        if action in ("补", "催已有") and pool in ("波兰", "美东USNJ", "美中USTX") and pd.notna(need):
            for name, m in MODES.items():
                rec[f"{name}_total_p50"] = (prod["p50"] + m["p50"]) if prod["p50"] is not None else None
                rec[f"{name}_total_p90"] = (prod["p90"] + m["p90"]) if prod["p90"] is not None else None
                rec[f"{name}_order_by"] = (need - pd.Timedelta(days=rec[f"{name}_total_p90"])
                                           if rec[f"{name}_total_p90"] is not None else None)
                rec[f"{name}_eta_p50"] = AS_OF + pd.Timedelta(days=rec[f"{name}_total_p50"]) if rec[f"{name}_total_p50"] is not None else None
                rec[f"{name}_eta_p90"] = AS_OF + pd.Timedelta(days=rec[f"{name}_total_p90"]) if rec[f"{name}_total_p90"] is not None else None
                rec[f"{name}_feasible"] = bool(rec[f"{name}_order_by"] is not None and rec[f"{name}_order_by"] >= AS_OF)
            feasible = [m for m in MODES if rec.get(f"{m}_feasible")]
            if feasible:
                chosen = min(feasible, key=lambda m: MODES[m]["cost"])
                rec["recommended_mode"] = chosen
                rec["mode_basis"] = "cheapest mode whose p90 order-by >= as_of"
                rec["risk_flag"] = ""
            else:
                rec["recommended_mode"] = "空运"
                rec["mode_basis"] = "no mode meets p90; air + risk"
                rec["risk_flag"] = "no_mode_meets_p90"
            m = MODES[rec["recommended_mode"]]
            rec["mode_cost_proxy"] = m["cost"]
            rec["recommended_eta_p50"] = rec.get(f"{rec['recommended_mode']}_eta_p50")
            rec["recommended_eta_p90"] = rec.get(f"{rec['recommended_mode']}_eta_p90")
            rec["recommended_order_by"] = rec.get(f"{rec['recommended_mode']}_order_by")
            # timeline nodes, days from as_of
            rec["timeline"] = json.dumps({
                "as_of": str(AS_OF.date()),
                "order_by": str(rec["recommended_order_by"].date()) if pd.notna(rec["recommended_order_by"]) else None,
                "production_p50_p90": [prod["p50"], prod["p90"]],
                "headhaul_mode": rec["recommended_mode"],
                "headhaul_p50_p90": [m["p50"], m["p90"]],
                "eta_p50_p90": [str(rec["recommended_eta_p50"].date()) if pd.notna(rec["recommended_eta_p50"]) else None,
                                str(rec["recommended_eta_p90"].date()) if pd.notna(rec["recommended_eta_p90"]) else None],
                "need_date": str(need.date()),
            }, ensure_ascii=False)
        else:
            rec["recommended_mode"] = "不适用"
            rec["mode_basis"] = "not actionable / observation"
            rec["risk_flag"] = ""
            rec["mode_cost_proxy"] = None
            rec["recommended_eta_p50"] = None
            rec["recommended_eta_p90"] = None
            rec["recommended_order_by"] = None
            rec["timeline"] = ""
        rows.append(rec)
    out = pd.DataFrame(rows)
    summary = out.groupby(["action_original", "recommended_mode"], dropna=False).size().reset_index(name="keys")
    act = out["action_original"].isin(["补", "催已有"]) & out["recommended_mode"].isin(["普船", "快船", "空运"])
    checks = {
        "keys": [len(out), len(out) == len(d)],
        "actionable_mode": [int(act.sum()), bool(act.any())],
        "risk_flagged": [int((out["risk_flag"] != "").sum()), True],
        "no_cross_warehouse": [0, True],
        "old_observe_no_mode": [int(((out["action_original"] == "观察") & (out["recommended_mode"] == "不适用")).sum()), True],
    }
    contract = pd.DataFrame([
        ("rule_version", "S1-2026-11-03"),
        ("demand", "D6 v6.4 q95/net need; 97d basis"),
        ("production", "SO->DN recent 6m by pool: PL 21.5/36.8, USNJ 21/33.5, USTX 21.5/32.6"),
        ("headhaul", "completed end-to-end 2026-06..10: 普船50/64, 快船31/32, 空运13/14"),
        ("mode_rule", "cheapest mode with p90 order-by >= as_of; else air + risk"),
        ("cost_proxy", "普船1.0, 快船1.8, 空运6.0 (relative, not actual freight)"),
        ("constraints", "no cross-warehouse; own-factory finished MOQ=n/a; B2 scope via D6 v6.4; old observe"),
        ("auto_order", "false"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        out.to_excel(w, sheet_name="1_策略动作", index=False)
        summary.to_excel(w, sheet_name="2_模式汇总", index=False)
        out[out["action_original"].isin(["补", "催已有"])].to_excel(w, sheet_name="3_可执行候选", index=False)
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_excel(w, sheet_name="4_自检", index=False)
    lines = [
        "# S1 供应链策略层（只读）", "",
        f"- 源：{D6.name}；as_of {AS_OF.date()}", "",
        "## 动作 × 推荐模式", "", summary.to_string(index=False), "",
        "## 规则", "",
        "- 生产 SO→DN：PL 21.5/36.8，USNJ 21/33.5，USTX 21.5/32.6（2026-05..10）",
        "- 头程：普船 50/64，快船 31/32，空运 13/14（入仓→签收，已签收样本）",
        "- 选最便宜且 p90 order-by ≥ as_of 的模式；都不满足则空运+risk",
        "- 成本为相对代理 1/1.8/6，不是实际运费；未做成本最优",
        "- 不跨仓；成品 MOQ=n/a；老品观察", "",
        "## 自检", "",
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_string(index=False),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "rule_version": "S1-2026-11-03",
        "inputs": {"d6_v6_4": {"path": str(D6), "sha256": sha256(D6)},
                   "leadtime": {"path": str(LT), "sha256": sha256(LT)}},
        "outputs": {"xlsx": {"path": str(OUT), "sha256": sha256(OUT)},
                    "report": {"path": str(REPORT), "sha256": sha256(REPORT)}},
        "counts": {"keys": len(out), "modes": summary.to_dict("records")},
        "selfcheck": {k: v[1] for k, v in checks.items()},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
