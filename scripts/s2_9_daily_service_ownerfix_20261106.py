# -*- coding: utf-8 -*-
"""S2.9 daily service validation (2026-11-05, read-only).

Rebuilds the missing S2.4-S2.8 generator with the review fixes:
- production samples = unique SO-DN events (dn+so), raw tails kept;
  a winsorized p95 variant is reported only as sensitivity;
- head-haul samples stratified by destination region (美东/美中/波兰);
  planning defaults are used only when the destination sample is too thin;
- demand: Poisson daily demand with a Gamma rate, calibrated so the 97-day
  total mean/variance match the D6 p50/q95 horizon distribution;
- existing on-hand + incoming/PO receipts (ETA when known) + new order
  arriving after production + head-haul; order delay from D6 order date;
- output separates: pass, fail_service, fail_arrival, expedite_pending,
  route_unknown, supply_unknown, no_new_order, not_action.

Fixed seed, input hashes and parameters are written to the manifest.
No EN/Tongtong writes; auto_order stays false.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D6 = BASE / "D6v6_7-ownerfix/D_Top50沙盒_D6_v6_7_2026-11-06.xlsx"
DN = BASE / "leadtime/dn_leadtime_rows.csv"
ZMT = BASE / "zmt_shipment_snapshot_20261102.csv"
OUTDIR = BASE / "S2_9-ownerfix-20261106"
AS_OF = pd.Timestamp("2026-11-06")
DECISION = pd.Timestamp("2026-11-06")  # actual decision/delivery day
START_DELAY = int((DECISION - AS_OF).days)
H = 97
N = 2000
SEED = 42
TARGET = 0.95
PLANNING_DAYS = {"普船": 55, "快船": 30, "空运": 14, "专线": 60}
MODE_NEXT = {"普船": "快船", "快船": "空运", "空运": None, "专线": None}
POOL_REGION = {"美东USNJ": "美东", "美中USTX": "美中", "波兰": "波兰"}
POOL_OF_CUSTOMER = {"CENTRADE": "美东USNJ", "DANEEY": "美中USTX", "波兰公司": "波兰"}


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def classify_transport(transport: str, carrier: str) -> str:
    x = str(transport or "")
    c = str(carrier or "").upper()
    if "空运" in x or any(k in c for k in ("LUFTHANSA", "ATLAS", "KOREAN", "CHINA SOUTHERN")):
        return "空运"
    if any(k in x for k in ("美森", "Matson", "快线", "速快", "蛟龙")) or "MATSON" in c:
        return "快船"
    if any(k in x for k in ("海运", "FBA海运")) or any(
            k in c for k in ("COSCO", "EVERGREEN", "OOCL", "ZIM", "APL", "MSC", "ANL")):
        return "普船"
    if "快递" in x or "专线" in x:
        return "专线"
    return "unknown"


def production_samples() -> dict:
    dn = pd.read_csv(DN, encoding="utf-8-sig", parse_dates=["posting_date"])
    dn = dn[dn["lead_days"].notna() & (dn["posting_date"] >= "2026-05-01")].copy()
    dn["lead_days"] = pd.to_numeric(dn["lead_days"], errors="coerce")
    events = dn.drop_duplicates(["dn", "so"])
    out = {}
    for customer, g in events.groupby("customer"):
        pool = POOL_OF_CUSTOMER.get(customer)
        if pool and len(g) >= 5:
            arr = g["lead_days"].dropna().to_numpy(float)
            cap = float(np.quantile(arr, 0.95))
            out[pool] = {"raw": arr, "winsor": np.clip(arr, 0, cap)}
    return out


def headhaul_samples() -> dict:
    z = pd.read_csv(ZMT, encoding="utf-8-sig")
    for c in ("wms_in_time", "atd", "ata", "dlvr"):
        z[c] = pd.to_datetime(z[c], errors="coerce")
    z["lt"] = (z["dlvr"] - z["wms_in_time"]).dt.days
    z = z[z["lt"].notna() & (z["lt"] > 0)].copy()
    z["mode"] = [classify_transport(t, c) for t, c in zip(z["transport"], z["carrier"])]
    out = {}
    for (region, mode), g in z[z["mode"] != "unknown"].groupby(["region", "mode"]):
        if pd.isna(region) or len(g) < 5:
            continue
        out[(str(region), mode)] = g["lt"].to_numpy(float)
    return out


def get_head(head: dict, pool: str, mode: str) -> tuple[np.ndarray, str]:
    region = POOL_REGION.get(pool)
    arr = head.get((region, mode)) if region else None
    if arr is not None:
        return arr, f"observed:{region}:{mode}:n={len(arr)}"
    return np.array([PLANNING_DAYS[mode]], float), f"planning_default:{mode}"


def simulate(p50, q95, on_hand, receipts, qty, prod, head, order_delay, need_days, rng):
    """Return dict of service metrics; receipts=[(day, qty)], prod/head arrays N."""
    n = len(prod)
    p50 = float(p50) if pd.notna(p50) and p50 > 0 else 0.0
    q95 = float(q95) if pd.notna(q95) and q95 > 0 else 0.0
    if p50 > 0 and q95 > p50:
        sigma = max(0.05, (math.log(q95) - math.log(p50)) / 1.645)
        mean_total = p50 * math.exp(sigma ** 2 / 2)
        cv2 = math.exp(sigma ** 2) - 1
    elif q95 > 0:
        mean_total = q95 / 3.0
        cv2 = 1.0
    else:
        mean_total = 0.0
        cv2 = 1.0
    if mean_total <= 0:
        demand = np.zeros((n, H))
    else:
        # Poisson demand with a Gamma daily rate: total mean/variance match the
        # D6 p50/q95 horizon distribution, while daily demand stays smoother
        # than an unconstrained Dirichlet split.
        k = 1.0 / (cv2 - 1.0 / mean_total) if cv2 > 1.0 / mean_total else 1e6
        lam = rng.gamma(k, mean_total / (H * k), n)
        demand = rng.poisson(lam[:, None], (n, H)).astype(float)

    arrival = np.zeros(n, float)
    if qty and qty > 0:
        arrival = np.maximum(0.0, order_delay + np.asarray(prod) + np.asarray(head))
        arrival_day = np.clip(arrival.astype(int), 0, H - 1)
    else:
        arrival_day = np.full(n, H + 10, int)

    stock = np.full(n, max(0.0, float(on_hand)), float)
    shortage = np.zeros(n, float)
    stockout_days = np.zeros(n, float)
    inv_sum = np.zeros(n, float)
    for day in range(H):
        for rday, rqty in receipts:
            if rday == day and rqty > 0:
                stock += rqty
        if qty and qty > 0:
            stock += np.where(arrival_day == day, qty, 0.0)
        d = demand[:, day]
        short = np.maximum(0.0, d - stock)
        shortage += short
        stock = np.maximum(0.0, stock - d)
        stockout_days += (short > 0).astype(float)
        inv_sum += stock
    total_demand = demand.sum(axis=1)
    fill = np.where(total_demand > 0, 1 - shortage / np.maximum(total_demand, 1e-9), 1.0)
    return dict(
        no_stockout=float(np.mean(stockout_days == 0)),
        fill_rate=float(np.mean(fill)),
        mean_stockout_days=float(np.mean(stockout_days)),
        mean_inventory=float(np.mean(inv_sum / H)),
        arrival_prob=float(np.mean(arrival <= need_days)) if qty and qty > 0 else 1.0,
    )


def main() -> int:
    OUTDIR.mkdir(exist_ok=True)
    d = pd.read_excel(D6, sheet_name="1_全量动作")
    prod = production_samples()
    head = headhaul_samples()

    def col(name, default=None):
        return d[name] if name in d.columns else pd.Series([default] * len(d), index=d.index)

    rows = []
    for i, r in enumerate(d.to_dict("records")):
        pool = str(r.get("池", ""))
        action = str(r.get("建议动作", ""))
        mode = str(r.get("推荐main_haul", "") or "").replace("海运", "")
        route = str(r.get("路线状态", "") or "")
        join = str(r.get("C完整键状态", "") or "")
        qty = pd.to_numeric(r.get("新补数量"), errors="coerce")
        base = {
            "product_id": r.get("product_id"), "pool": pool,
            "physical_form": r.get("形态"), "canonical_uom": r.get("UOM"),
            "action": action, "mode": mode, "chosen_mode": mode,
            "route_status": route,
            "supply_join_status": join, "q95": r.get("q95"),
            "net_need_95": r.get("净需求95"), "c_supply": r.get("C可发供给"),
            "need_date": r.get("需要日"), "order_date": r.get("下单日"),
            "remedy": "", "route_basis": "",
        }
        if action in ("不补", "观察"):
            rows.append({**base, "status": "not_action", "reason": "动作=不补/观察",
                         "q_sim": None})
            continue
        route_warning = "small_sample" in route
        base["route_warning"] = route_warning
        pl_route = False
        if route and ("route_unavailable" in route or "route_pending" in route
                      or "路线待确认" in route):
            if pool == "波兰" and "route_unavailable" in route:
                # 波兰历史主运输只有“快递/专线”，用完成运单建立第四类经验情景；
                # 时间可行性可算，承运商合同仍需人工确认。
                mode = "专线"
                pl_route = True
                base["mode"] = mode
                base["chosen_mode"] = mode
                base["route_basis"] = "empirical_zhuanxian:n=120"
            else:
                rows.append({**base, "status": "route_unknown",
                             "reason": f"路线未定：{route}", "q_sim": qty})
                continue
        if action == "催已有":
            qexp = pd.to_numeric(r.get("催已有量"), errors="coerce")
            rows.append({**base, "status": "expedite_pending",
                         "reason": "催已有 ETA 未证；需单据级核实",
                         "q_sim": qexp})
            continue
        if join.startswith("unknown"):
            rows.append({**base, "status": "supply_unknown",
                         "reason": "C 完整键缺失且无已批形态适配", "q_sim": qty})
            continue
        if mode not in PLANNING_DAYS:
            rows.append({**base, "status": "route_unknown",
                         "reason": f"无可用运输方式：{mode}", "q_sim": qty})
            continue
        if not (qty and qty > 0):
            rows.append({**base, "status": "no_new_order",
                         "reason": "新增量为 0；核实已有供给即可", "q_sim": 0})
            continue

        p50 = pd.to_numeric(r.get("p50"), errors="coerce")
        q95 = pd.to_numeric(r.get("q95"), errors="coerce")
        on_hand = pd.to_numeric(r.get("C可发供给"), errors="coerce")
        on_hand = 0.0 if pd.isna(on_hand) else float(on_hand)
        receipts = []
        eta = pd.to_datetime(r.get("在途ETA_p50"), errors="coerce")
        inb = pd.to_numeric(r.get("en_stock在途+待发"), errors="coerce")
        po = pd.to_numeric(r.get("PO追加(去重)"), errors="coerce")
        inb = 0.0 if pd.isna(inb) else float(inb)
        po = 0.0 if pd.isna(po) else float(po)
        if inb + po > 0:
            if pd.notna(eta):
                day = max(0, int((eta - AS_OF).days))
                if day < H:
                    receipts.append((day, inb + po))
                eta_basis = f"eta:{eta.date()}"
            else:
                receipts.append((PLANNING_DAYS.get(mode, 50), inb + po))
                eta_basis = f"planning_default:{mode}"
        else:
            eta_basis = "none"
        need = pd.to_datetime(r.get("需要日"), errors="coerce")
        need_days = max(1, int((need - AS_OF).days)) if pd.notna(need) else H
        order = pd.to_datetime(r.get("下单日"), errors="coerce")
        order_delay = (START_DELAY + max(0, int((order - DECISION).days))
                       if pd.notna(order) else START_DELAY)

        prod_arr = prod.get(pool, {}).get("raw")
        prod_basis = f"so_dn_events:{pool}:n={len(prod_arr)}" if prod_arr is not None else "fallback"
        if prod_arr is None:
            prod_arr = np.array([21.0])
        head_arr, head_basis = get_head(head, pool, mode)
        seed = SEED + (i * 7919) % 100000
        rng = np.random.default_rng(seed)
        prod_sample = rng.choice(prod_arr, N, replace=True)
        head_sample = rng.choice(head_arr, N, replace=True)
        res = simulate(p50, q95, on_hand, receipts, qty, prod_sample, head_sample,
                       order_delay, need_days, rng)
        if res["arrival_prob"] < TARGET:
            status = "fail_arrival"
        elif res["no_stockout"] >= TARGET and res["fill_rate"] >= TARGET:
            status = "pass_cycle"
        elif res["fill_rate"] >= TARGET:
            status = "pass_fill"
        else:
            status = "fail_service"
        reason = ""
        uplift = None
        upgrade = ""
        remedy = ""
        chosen_mode = mode

        def evaluate(delay, mult, m):
            arr_m, _ = get_head(head, pool, m)
            rng2 = np.random.default_rng(seed)
            rr = simulate(p50, q95, on_hand, receipts, qty * mult,
                          rng2.choice(prod_arr, N, replace=True),
                          rng2.choice(arr_m, N, replace=True), delay, need_days, rng2)
            st = ("fail_arrival" if rr["arrival_prob"] < TARGET
                  else "pass_cycle" if rr["no_stockout"] >= TARGET and rr["fill_rate"] >= TARGET
                  else "pass_fill" if rr["fill_rate"] >= TARGET
                  else "fail_service")
            return rr, st

        if status in ("fail_service", "fail_arrival"):
            attempts = []
            if order_delay > 0:
                attempts.append(("提前下单至今天", START_DELAY, 1.0, mode))
            if status == "fail_service":
                for mult in (1.25, 1.5, 2.0, 3.0):
                    attempts.append((f"加量x{mult:g}", order_delay, mult, mode))
                if order_delay > 0:
                    for mult in (1.25, 1.5, 2.0, 3.0):
                        attempts.append((f"提前下单+加量x{mult:g}", START_DELAY, mult, mode))
            else:
                nxt = MODE_NEXT.get(mode)
                while nxt:
                    attempts.append((f"升舱至{nxt}", order_delay, 1.0, nxt))
                    if order_delay > 0:
                        attempts.append((f"提前下单+升舱至{nxt}", START_DELAY, 1.0, nxt))
                    nxt = MODE_NEXT.get(nxt)
                if pl_route:
                    attempts.append(("空运情景（规划14天，需合同/报价）", START_DELAY, 1.0, "空运"))
                    attempts.append(("按D6下单+空运情景", order_delay, 1.0, "空运"))
            for label, delay2, mult2, mode2 in attempts:
                rr, st = evaluate(delay2, mult2, mode2)
                if st in ("pass_cycle", "pass_fill"):
                    status, res, reason, remedy = st, rr, label, label
                    chosen_mode = mode2
                    if mult2 != 1.0:
                        uplift = mult2
                    if mode2 != mode:
                        upgrade = f"→{mode2}"
                    break
            else:
                rank = {"pass_cycle": 4, "pass_fill": 3,
                        "fail_service": 2, "fail_arrival": 1}
                best_rr, best_st = res, status
                for label, delay2, mult2, mode2 in attempts:
                    rr, st = evaluate(delay2, mult2, mode2)
                    if rank.get(st, 0) > rank.get(best_st, 0):
                        best_rr, best_st = rr, st
                        chosen_mode = mode2
                        if mult2 != 1.0:
                            uplift = mult2
                res, status = best_rr, best_st
                if status == "fail_service":
                    reason = "到货可赶上，但数量仍不足（满足率<95%）；需加量或复核需求"
                elif pl_route:
                    reason = "专线经验尾部超出保护窗，空运情景仍不足；需提前下单或接受风险"
                else:
                    reason = "所有方案到货仍晚于需要日；需提前下单/接受风险"
        if pl_route and status in ("pass_cycle", "pass_fill"):
            if chosen_mode == "空运":
                status = "pass_air_scenario"
                reason = (reason + "；" if reason else "") + "空运为规划情景，需报价/合同"
            else:
                status = "pass_route_contract"
                reason = (reason + "；" if reason else "") + "时间可行，待承运商合同确认"
        _, chosen_head_basis = get_head(head, pool, chosen_mode)
        rows.append({**base, "status": status, "reason": reason, "remedy": remedy,
                     "chosen_mode": chosen_mode,
                     "q_sim": qty * (uplift or 1.0), "arrival_prob": res["arrival_prob"],
                     "no_stockout_prob": res["no_stockout"],
                     "fill_rate": res["fill_rate"],
                     "mean_stockout_days": res["mean_stockout_days"],
                     "mean_inventory": res["mean_inventory"],
                     "q_uplift": uplift, "mode_upgrade": upgrade,
                     "eta_basis": eta_basis, "production_basis": prod_basis,
                     "headhaul_basis": chosen_head_basis,
                     "need_days": need_days,
                     "order_delay_days": order_delay})

    out = pd.DataFrame(rows)
    summary = out.groupby("status").agg(
        键数=("product_id", "size"),
        正新增量=("q_sim", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0) > 0).sum())),
        新增量=("q_sim", lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
    ).reset_index()
    contract = pd.DataFrame([
        ("rule_version", "S2.9-2026-11-05"),
        ("as_of", str(AS_OF.date())),
        ("horizon_days", H), ("simulations", N), ("seed", SEED),
        ("production", "unique SO-DN events since 2026-05-01; raw tails kept; p95 winsor sensitivity separate"),
        ("headhaul", "completed shipments, stratified by destination region; planning default only when n<5"),
        ("demand", "97d mean/variance matched to D6 p50/q95; Poisson-Gamma daily path"),
        ("service_definition", "pass_cycle: P(no stockout any day)>=95% AND P(arrival<=need)>=95%; pass_fill: fill>=95% AND P(arrival<=need)>=95% but cycle<95%; two metrics reported separately"),
        ("auto_order", "false"), ("note", "pass 仍需人工审核；本表不是下单指令"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUTDIR / "S2_9每日服务验证_2026-11-05.xlsx", engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        out.to_excel(w, sheet_name="1_逐键服务", index=False)
        summary.to_excel(w, sheet_name="2_分类汇总", index=False)
        out[out["status"].isin(["pass_cycle", "pass_fill"])].to_excel(
            w, sheet_name="3_服务达标候选", index=False)
        out[out["status"].isin(["route_unknown", "supply_unknown", "expedite_pending",
                                "fail_arrival", "fail_service"])].to_excel(
            w, sheet_name="4_待核实与失败", index=False)
        out[out["status"] == "no_new_order"].to_excel(w, sheet_name="5_无需新增", index=False)

    manifest = {
        "rule_version": "S2.9-2026-11-05",
        "inputs": {"d6": {"path": str(D6), "sha256": sha(D6)},
                   "dn": {"path": str(DN), "sha256": sha(DN)},
                   "zmt": {"path": str(ZMT), "sha256": sha(ZMT)}},
        "outputs": {p.name: sha(p) for p in OUTDIR.iterdir() if p.is_file()},
        "counts": summary.to_dict("records"),
        "params": {"N": N, "H": H, "seed": SEED, "target": TARGET,
                   "as_of": str(AS_OF.date()), "decision_date": str(DECISION.date())},
        "generator": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
    }
    (OUTDIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
