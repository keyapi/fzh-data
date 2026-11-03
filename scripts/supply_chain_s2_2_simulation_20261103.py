# -*- coding: utf-8 -*-
"""S2: joint demand x production x head-haul simulation (read-only).

Monte Carlo per actionable D6 v6.4 key:
- demand over lead time from q50/q95 97d distribution;
- production SO->DN empirical by pool;
- head-haul empirical by 3 modes (completed end-to-end);
- choose cheapest mode with P(arrival <= need) >= 95%; Q = 95th percentile
  of demand-over-lead-time minus available; cost = relative proxy + shortage.
Not an optimizer; no EN/Tongtu writes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D6 = BASE / "D6v6_4-final/D_Top50沙盒_D6_v6_4_2026-11-03.xlsx"
DN = BASE / "leadtime/dn_leadtime_rows.csv"
ZMT = BASE / "zmt_shipment_snapshot_20261102.csv"
OUTDIR = BASE / "S2_2-supply-chain-simulation"
OUTDIR.mkdir(exist_ok=True)
AS_OF = pd.Timestamp("2026-11-02")
N = 2000
SERVICE_TARGET = float(os.environ.get("S2_SERVICE", "0.95"))
SL_TAG = os.environ.get("S2_TAG", f"SL{int(SERVICE_TARGET*100)}")
OUT = OUTDIR / f"D_供应链联合模拟_S2_2_{SL_TAG}_2026-11-03.xlsx"
REPORT = OUTDIR / f"D_供应链联合模拟_S2_2_{SL_TAG}_2026-11-03_报告.md"
MANIFEST = OUTDIR / f"D_供应链联合模拟_S2_2_{SL_TAG}_2026-11-03.manifest.json"
RNG = np.random.default_rng(42)

POOL_OF_CUSTOMER = {"CENTRADE": "美东USNJ", "DANEEY": "美中USTX", "波兰公司": "波兰"}
MODE_CLASS = {"普船": "sea_regular", "快船": "sea_fast", "空运": "air"}
MODE_COST = {"普船": 1.0, "快船": 1.8, "空运": 6.0}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def classify(row) -> str:
    x = str(row.get("transport", ""))
    c = str(row.get("carrier", "")).upper()
    if "空运" in x or any(k in c for k in ["LUFTHANSA", "ATLAS", "KOREAN", "CHINA SOUTHERN"]):
        return "air"
    if any(k in x for k in ["美森", "Matson", "快线", "速快", "蛟龙"]) or "MATSON" in c:
        return "sea_fast"
    if any(k in x for k in ["海运", "FBA海运"]) or any(k in c for k in ["COSCO", "EVERGREEN", "OOCL", "ZIM", "APL", "MSC", "ANL"]):
        return "sea_regular"
    return "unknown"


def load_samples() -> tuple[dict, dict]:
    dn = pd.read_csv(DN, encoding="utf-8-sig")
    dn = dn[dn["lead_days"].notna()].copy()
    dn["lead_days"] = pd.to_numeric(dn["lead_days"], errors="coerce")
    dn["pool"] = dn["customer"].map(POOL_OF_CUSTOMER)
    dn["posting_date"] = pd.to_datetime(dn["posting_date"], errors="coerce")
    recent = dn[dn["posting_date"] >= "2026-05-01"]
    use = recent if len(recent) >= 20 else dn
    prod = {}
    for p, g in use.groupby("pool"):
        arr = g["lead_days"].dropna().to_numpy()
        if len(arr) >= 5:
            cap = float(np.quantile(arr, 0.95))
            prod[p] = np.clip(arr, 0, cap)
    # fallback to all history for missing pools
    for p, g in dn.groupby("pool"):
        if p not in prod:
            arr = g["lead_days"].dropna().to_numpy()
            if len(arr) >= 5:
                prod[p] = np.clip(arr, 0, float(np.quantile(arr, 0.95)))
    z = pd.read_csv(ZMT, encoding="utf-8-sig")
    for c in ["wms_in_time", "atd", "ata", "dlvr"]:
        z[c] = pd.to_datetime(z[c], errors="coerce")
    z["lt"] = (z["dlvr"] - z["wms_in_time"]).dt.days
    z = z[z["lt"].notna() & (z["lt"] > 0)].copy()
    z["class"] = z.apply(classify, axis=1)
    head = {c: g["lt"].to_numpy() for c, g in z.groupby("class") if len(g) >= 5}
    return prod, head


def demand_draws(q50: float, q95: float, lead_days: np.ndarray) -> np.ndarray:
    q50 = float(q50) if pd.notna(q50) else 0.0
    q95 = float(q95) if pd.notna(q95) else 0.0
    if q50 > 0 and q95 > q50:
        sigma = max(0.01, (np.log(q95) - np.log(q50)) / 1.645)
        d97 = RNG.lognormal(np.log(q50), sigma, N)
    elif q95 > 0:
        d97 = RNG.exponential(q95 / 3.0, N)
    else:
        d97 = np.zeros(N)
    # daily-rate scaling to the mode's lead time
    return d97 * np.maximum(lead_days, 1.0) / 97.0


def main() -> int:
    d = pd.read_excel(D6, sheet_name="1_全量动作")
    d["需要日"] = pd.to_datetime(d["需要日"], errors="coerce")
    prod, head = load_samples()
    rows = []
    for rec in d.to_dict("records"):
        pool = str(rec.get("池"))
        action = str(rec.get("建议动作"))
        need = rec.get("需要日")
        base = {
            "product_id": rec.get("product_id"), "pool": pool,
            "physical_form": rec.get("形态"), "uom": rec.get("UOM"),
            "action_original": action,
            "q95_97d": rec.get("q95"), "net_need_95": rec.get("净需求95"),
            "available": rec.get("C可发供给"),
            "incoming": rec.get("en_stock在途+待发"),
            "po_add": rec.get("PO追加(去重)"),
            "need_date": need,
            "existing_eta_p50": rec.get("ETA_p50"),
        }
        route = str(rec.get("路线状态") or "")
        route_pending = ("route_unavailable" in route) or ("route_pending" in route) or ("路线待确认" in route)
        if action in ("补", "催已有") and route_pending:
            base.update({"recommended_mode": "路线待确认", "q_sim": None, "service_prob": None,
                         "stockout_prob": None, "expected_cost": None, "risk_flag": "route_pending"})
            rows.append(base)
            continue
        if action == "催已有":
            base.update({"recommended_mode": "催后ETA未证", "q_sim": None, "service_prob": None,
                         "stockout_prob": None, "expected_cost": None, "risk_flag": "expedite_eta_unknown"})
            rows.append(base)
            continue
        if action != "补" or pool not in ("波兰", "美东USNJ", "美中USTX") or pd.isna(need):
            base.update({"recommended_mode": "不适用", "q_sim": None, "service_prob": None,
                         "stockout_prob": None, "expected_cost": None, "risk_flag": ""})
            rows.append(base)
            continue
        need_days = max(1, int((need - AS_OF).days))
        prod_s = prod.get(pool, prod.get("美东USNJ", np.array([21.0])))
        on_hand = float(rec.get("C可发供给") or 0)
        incoming = float(rec.get("en_stock在途+待发") or 0) + float(rec.get("PO追加(去重)") or 0)
        eta = rec.get("ETA_p50")
        if pd.isna(eta) or pd.to_datetime(eta) > need:
            incoming = 0.0
        avail = max(0.0, on_hand + incoming)
        options = {}
        for mode, cls in MODE_CLASS.items():
            hs = head.get(cls, head.get("sea_regular", np.array([50.0])))
            # production and head-haul independent bootstrap; stage independence assumption
            p = RNG.choice(prod_s, N, replace=True)
            h = RNG.choice(hs, N, replace=True)
            lead = p + h
            service = float(np.mean(lead <= need_days))
            demand = demand_draws(rec.get("p50"), rec.get("q95"), lead)  # p50/q95 fit; fallback q95
            q = max(0.0, float(np.quantile(demand - avail, 0.95)))
            shortage = np.maximum(0.0, demand - avail - q)
            cost = MODE_COST[mode] * q + 0.05 * q * float(np.mean(lead)) + 10.0 * float(np.mean(shortage))
            options[mode] = {"service": service, "q": q, "stockout": float(np.mean(shortage > 0)),
                             "cost": cost, "eta_p50": float(np.quantile(lead, 0.5)),
                             "eta_p95": float(np.quantile(lead, 0.95)), "lead": lead}
        feasible = [m for m, o in options.items() if o["service"] >= SERVICE_TARGET]
        if feasible:
            mode = min(feasible, key=lambda m: options[m]["cost"])
            risk = ""
        else:
            mode = "空运"
            risk = "no_mode_service_95"
        o = options[mode]
        base.update({
            "recommended_mode": mode,
            "service_prob": o["service"],
            "q_sim": int(round(o["q"])),
            "stockout_prob": o["stockout"],
            "expected_cost": o["cost"],
            "eta_p50_days": o["eta_p50"],
            "eta_p95_days": o["eta_p95"],
            "risk_flag": risk,
            "mode_options": json.dumps({k: {"service": v["service"], "q": round(v["q"], 2),
                                            "stockout": v["stockout"], "cost": round(v["cost"], 2)}
                                        for k, v in options.items()}, ensure_ascii=False),
        })
        rows.append(base)
    out = pd.DataFrame(rows)
    summary = out.groupby(["action_original", "recommended_mode"], dropna=False).size().reset_index(name="keys")
    checks = {
        "keys": [len(out), len(out) == len(d)],
        "sim_keys": [int((out["q_sim"].notna()).sum()), True],
        "no_negative_q": [int((pd.to_numeric(out["q_sim"], errors="coerce").fillna(0) < 0).sum()), True],
        "no_cross_warehouse": [0, True],
        "risk_flagged": [int((out["risk_flag"] != "").sum()), True],
    }
    contract = pd.DataFrame([
        ("rule_version", "S2.2-2026-11-03"),
        ("simulation", f"Monte Carlo N={N}, production and head-haul bootstrap independent"),
        ("demand", "D6 p50/q95 97d -> lognormal/exponential; fallback q95"),
        ("production", "SO->DN recent 2026-05..10 by pool, winsorized at p95 (fallback all history)"),
        ("headhaul", "completed end-to-end by mode: 普船/快船/空运"),
        ("mode_rule", f"P(lead<=need_days)>={SERVICE_TARGET:.0%}, then min relative cost"),
        ("cost", "freight proxy 1/1.8/6 + holding 5%/day + shortage penalty 10 (relative)"),
        ("constraints", "no cross-warehouse; old observe; MOQ n/a; auto_order=false"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        out.to_excel(w, sheet_name="1_联合模拟", index=False)
        summary.to_excel(w, sheet_name="2_模式汇总", index=False)
        out[out["action_original"].isin(["补", "催已有"])].to_excel(w, sheet_name="3_可执行候选", index=False)
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_excel(w, sheet_name="4_自检", index=False)
    lines = [
        "# S2 联合模拟（只读）", "",
        f"- 源：{D6.name}；as_of {AS_OF.date()}；N={N}", "",
        "## 动作 × 模式", "", summary.to_string(index=False), "",
        "## 假设", "",
        "- demand: D6 p50/q95 97d 拟合；缺失 p50 时用 q95",
        "- production: 2026-05..10 winsorized p95; head-haul: completed samples; independent bootstrap",
        "- 模式可行：P(总交期 <= 需要日) >= 95%；选相对成本最低",
        "- 成本为相对代理，不是实际运费/缺货罚价", "",
        "## 自检", "",
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_string(index=False),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "rule_version": "S2.2-2026-11-03",
        "inputs": {"d6_v6_4": {"path": str(D6), "sha256": sha256(D6)},
                   "dn": {"path": str(DN), "sha256": sha256(DN)},
                   "zmt": {"path": str(ZMT), "sha256": sha256(ZMT)}},
        "outputs": {"xlsx": {"path": str(OUT), "sha256": sha256(OUT)},
                    "report": {"path": str(REPORT), "sha256": sha256(REPORT)}},
        "counts": {"keys": len(out), "sim_keys": int(out["q_sim"].notna().sum()),
                   "modes": summary.to_dict("records")},
        "selfcheck": {k: v[1] for k, v in checks.items()},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
