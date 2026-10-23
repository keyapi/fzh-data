#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2: 楔形枕 8-SKU 补货分配实验（OR-Tools CP-SAT）

读取 data/input.json，建立 12 个月、8 SKU、3 个月交期的整数规划：
  - 决策：每个 SKU 在 t=0 的下单量（0 或 >= MOQ）
  - 库存平衡：inv[t+1] = inv[t] + arrivals[t] - demand[t]（允许缺货）
  - 目标：持有成本 + 20 倍缺货惩罚 + 小额固定下单费
  - 预算：B=257（业务启发式总量）与 B=180（压力预算）
  - 敏感性：需求 ±25%

运行：
    uv run python solve.py

输出：
    - 控制台 Markdown 摘要
    - data/results.json（全部数字，便于复核）
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

from ortools.sat.python import cp_model

# Windows 控制台编码兜底
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "data" / "input.json"
RESULTS_PATH = BASE_DIR / "data" / "results.json"

HORIZON = 12          # 月，t=0..11
LEAD_TIME = 3         # 下单后 3 个月到货
SCALE = 10            # 需求/库存内部用 0.1 件为整数单位
HOLD_COST = 1.0       # 每件每月持有成本
SHORT_COST = 20.0     # 每件每月缺货惩罚 = 20 × 持有
FIXED_COST = 5.0      # 每个开单 SKU 的固定下单费
SOLVER_TIME_LIMIT = 120
RANDOM_SEED = 42


# ---------------------------------------------------------------------------
# 输入与基线
# ---------------------------------------------------------------------------

def load_input() -> dict:
    with INPUT_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def heuristic_qty(rate: float, available: float, in_transit: float) -> int:
    """业务公式：ceil(rate × 6 − available − in_transit)，下限 0。"""
    raw = rate * 6.0 - available - in_transit
    if raw <= 1e-9:
        return 0
    return int(math.ceil(raw - 1e-9))


def scale_to_budget(qty: list[int], budget: int) -> list[int]:
    """把一组整数按比例缩放到预算 B（最大余数法）。用于构造同预算的启发式对照。"""
    total = sum(qty)
    if total == 0:
        return [0] * len(qty)
    raw = [q * budget / total for q in qty]
    floors = [int(math.floor(x)) for x in raw]
    remainder = budget - sum(floors)
    order = sorted(
        range(len(qty)),
        key=lambda i: (-(raw[i] - floors[i]), -qty[i], i),
    )
    for i in order[:remainder]:
        floors[i] += 1
    return floors


# ---------------------------------------------------------------------------
# 独立仿真（不依赖求解器），用于评估任意策略
# ---------------------------------------------------------------------------

def evaluate(skus: list[dict], qty: list[int], factor: float, budget: int | None = None) -> dict:
    """按 12 个月逐月仿真，返回逐 SKU 与汇总指标。qty 为 t=0 下单件数。"""
    per_sku: list[dict] = []
    monthly_short = [0] * HORIZON
    monthly_inv = [0] * HORIZON

    for s, q in zip(skus, qty):
        rate = s["rate"] * factor
        demand = round(s["rate"] * factor * SCALE)      # 0.1 件单位
        avail = round(s["available"] * SCALE)
        transit = round(s["in_transit"] * SCALE)

        inv = avail
        short_units = 0
        short_3_5 = 0
        short_3_8 = 0
        stockout_months = 0
        stockout_months_post = 0

        for t in range(HORIZON):
            arrivals = q * SCALE + transit if t == LEAD_TIME else 0
            available_now = inv + arrivals
            short = max(0, demand - available_now)
            inv = available_now + short - demand  # = max(0, available_now - demand)

            short_units += short
            monthly_short[t] += short
            monthly_inv[t] += inv

            if short > 0:
                stockout_months += 1
                if t >= LEAD_TIME:
                    stockout_months_post += 1
            if 3 <= t <= 5:      # 到货后前 3 个月（下一补货周期）
                short_3_5 += short
            if 3 <= t <= 8:      # 到货后前 6 个月（业务覆盖窗口）
                short_3_8 += short

        per_sku.append(
            {
                "sku": s["sku"],
                "qty": q,
                "rate": rate,
                "coverage_total_months": (s["available"] + s["in_transit"] + q) / rate,
                "coverage_post_arrival_months": (
                    max(0.0, s["available"] - LEAD_TIME * rate) + s["in_transit"] + q
                ) / rate,
                "shortage_units": short_units / SCALE,
                "shortage_3_5": short_3_5 / SCALE,
                "shortage_3_8": short_3_8 / SCALE,
                "end_inventory": inv / SCALE,
                "stockout_months": stockout_months,
                "stockout_months_post_arrival": stockout_months_post,
            }
        )

    opened = sum(1 for q in qty if q > 0)
    totals = {
        "order_qty": sum(qty),
        "budget": budget,
        "budget_slack": (budget - sum(qty)) if budget is not None else None,
        "holding_unit_months": sum(monthly_inv) / SCALE,
        "shortage_units": sum(monthly_short) / SCALE,
        "shortage_3_5": sum(x["shortage_3_5"] for x in per_sku),
        "shortage_3_8": sum(x["shortage_3_8"] for x in per_sku),
        "stockout_sku_months": sum(x["stockout_months"] for x in per_sku),
        "stockout_sku_months_post_arrival": sum(
            x["stockout_months_post_arrival"] for x in per_sku
        ),
        "max_stockout_months_post_arrival": max(
            (x["stockout_months_post_arrival"] for x in per_sku), default=0
        ),
        "skus_opened": opened,
        "fixed_order_cost": FIXED_COST * opened,
        "evaluation_cost": (
            sum(monthly_inv) / SCALE
            + SHORT_COST * (sum(monthly_short) / SCALE)
            + FIXED_COST * opened
        ),
        "moq_violations": [
            x["sku"]
            for x, s in zip(per_sku, skus)
            if 0 < x["qty"] < s["moq"]
        ],
    }
    totals["moq_feasible"] = len(totals["moq_violations"]) == 0
    totals["monthly_shortage_units"] = [x / SCALE for x in monthly_short]
    totals["monthly_end_inventory_units"] = [x / SCALE for x in monthly_inv]

    return {"per_sku": per_sku, "totals": totals}


# ---------------------------------------------------------------------------
# CP-SAT 模型
# ---------------------------------------------------------------------------

def solve_cpsat(skus: list[dict], budget: int, factor: float) -> dict:
    model = cp_model.CpModel()
    n = len(skus)

    q_vars: list = []
    open_vars: list = []
    caps: list[int] = []
    demands: list[int] = []

    for s in skus:
        rate = s["rate"] * factor
        demand = round(s["rate"] * factor * SCALE)
        cap = max(s["moq"], int(math.ceil(rate * HORIZON)))
        demands.append(demand)
        caps.append(cap)

        q = model.NewIntVar(0, cap, f"q_{s['sku']}")
        z = model.NewBoolVar(f"open_{s['sku']}")
        model.Add(q <= cap * z)
        model.Add(q >= s["moq"] * z)
        model.Add(q >= z)  # q=0 时强制 z=0，便于固定成本与开单数一致
        q_vars.append(q)
        open_vars.append(z)

    model.Add(sum(q_vars) <= budget)

    inv_vars: list[list] = []
    short_vars: list[list] = []
    for i, s in enumerate(skus):
        avail = round(s["available"] * SCALE)
        transit = round(s["in_transit"] * SCALE)
        ub_inv = avail + transit + caps[i] * SCALE
        inv = [
            model.NewIntVar(0, ub_inv, f"inv_{s['sku']}_{t}")
            for t in range(HORIZON + 1)
        ]
        short = [
            model.NewIntVar(0, demands[i], f"short_{s['sku']}_{t}")
            for t in range(HORIZON)
        ]
        model.Add(inv[0] == avail)
        for t in range(HORIZON):
            arrivals = q_vars[i] * SCALE + transit if t == LEAD_TIME else 0
            # inv[t+1] = inv[t] + arrivals[t] - demand[t] + shortage[t]
            model.Add(inv[t + 1] == inv[t] + arrivals - demands[i] + short[t])
        inv_vars.append(inv)
        short_vars.append(short)

    # 目标放大 10 倍以保持整数：真实成本 = 目标值 / 10
    objective = (
        sum(inv_vars[i][t + 1] for i in range(n) for t in range(HORIZON))
        + int(SHORT_COST) * sum(short_vars[i][t] for i in range(n) for t in range(HORIZON))
        + int(FIXED_COST * SCALE) * sum(open_vars)
    )
    model.Minimize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = RANDOM_SEED
    solver.parameters.log_search_progress = False

    started = time.perf_counter()
    status = solver.Solve(model)
    stage1_runtime = time.perf_counter() - started

    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": status_name,
            "feasible": False,
            "runtime_seconds": stage1_runtime,
            "budget": budget,
            "factor": factor,
        }

    primary_best = int(round(solver.ObjectiveValue()))
    stage1_solution = [solver.Value(q) for q in q_vars]

    # 第二阶段（字典序）：固定主目标最优值，再让缺货尽量晚发生。
    # 原因：固定预算下总缺货件数基本不随分配变化，主目标存在大量并列最优；
    # 用“越早缺货权重越大”的次目标挑出一个服务时点更合理的解。
    model.Add(objective == primary_best)
    weighted_shortage = sum(
        (HORIZON - t) * short_vars[i][t]
        for i in range(n)
        for t in range(HORIZON)
    )
    model.Minimize(weighted_shortage)

    solver2 = cp_model.CpSolver()
    solver2.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT
    solver2.parameters.num_search_workers = 1
    solver2.parameters.random_seed = RANDOM_SEED
    solver2.parameters.log_search_progress = False

    started = time.perf_counter()
    status2 = solver2.Solve(model)
    stage2_runtime = time.perf_counter() - started
    runtime = stage1_runtime + stage2_runtime

    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # 理论上不会发生；退回第一阶段解
        qty = stage1_solution
        solver_obj = primary_best / SCALE
        tie_breaker = None
    else:
        qty = [solver2.Value(q) for q in q_vars]
        solver_obj = solver2.Value(objective) / SCALE
        tie_breaker = solver2.ObjectiveValue()

    status_name = f"{solver.StatusName(status)} -> {solver2.StatusName(status2)}"
    final_solver = solver2 if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE) else solver
    solver_inv = [
        [final_solver.Value(inv_vars[i][t]) / SCALE for t in range(HORIZON + 1)]
        for i in range(n)
    ]
    solver_short = [
        [final_solver.Value(short_vars[i][t]) / SCALE for t in range(HORIZON)]
        for i in range(n)
    ]
    evaluation = evaluate(skus, qty, factor, budget=budget)

    # 回读校验：模型目标 vs 独立仿真
    verification = {
        "objective_matches_simulation": abs(solver_obj - evaluation["totals"]["evaluation_cost"]) < 1e-6,
        "solver_objective": solver_obj,
        "simulated_objective": evaluation["totals"]["evaluation_cost"],
    }

    return {
        "status": status_name,
        "feasible": True,
        "runtime_seconds": runtime,
        "runtime_stage1_seconds": stage1_runtime,
        "runtime_stage2_seconds": stage2_runtime,
        "budget": budget,
        "factor": factor,
        "qty": qty,
        "solver_objective": solver_obj,
        "tie_breaker_weighted_shortage": tie_breaker,
        "solver_inventory_end_of_month": solver_inv,
        "solver_shortage_by_month": solver_short,
        "verification": verification,
        "evaluation": evaluation,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def policy_summary(label: str, result: dict) -> dict:
    t = result["totals"]
    return {
        "label": label,
        "order_qty": t["order_qty"],
        "budget": t["budget"],
        "budget_slack": t["budget_slack"],
        "holding_unit_months": round(t["holding_unit_months"], 2),
        "shortage_units": round(t["shortage_units"], 2),
        "shortage_3_5": round(t["shortage_3_5"], 2),
        "shortage_3_8": round(t["shortage_3_8"], 2),
        "stockout_sku_months_post_arrival": t["stockout_sku_months_post_arrival"],
        "max_stockout_months_post_arrival": t["max_stockout_months_post_arrival"],
        "skus_opened": t["skus_opened"],
        "evaluation_cost": round(t["evaluation_cost"], 2),
        "moq_feasible": t["moq_feasible"],
        "moq_violations": t["moq_violations"],
    }


def print_policy_table(label: str, result: dict) -> None:
    print(f"\n### {label}\n")
    print("| SKU | 下单 | 总覆盖月 | 到货后覆盖月 | 缺货件 | 到货后前3月缺货 | 末库存 | 缺货月数 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for x in result["per_sku"]:
        print(
            f"| {x['sku']} | {x['qty']} | {x['coverage_total_months']:.2f} | "
            f"{x['coverage_post_arrival_months']:.2f} | {x['shortage_units']:.1f} | "
            f"{x['shortage_3_5']:.1f} | {x['end_inventory']:.1f} | {x['stockout_months']} |"
        )
    t = result["totals"]
    print(
        f"\n合计：下单 {t['order_qty']} 件；持有 {t['holding_unit_months']:.1f} 件·月；"
        f"缺货 {t['shortage_units']:.1f} 件；到货后前 3 月缺货 {t['shortage_3_5']:.1f} 件；"
        f"评价成本 {t['evaluation_cost']:.1f}；MOQ 可行：{'是' if t['moq_feasible'] else '否（' + ','.join(t['moq_violations']) + '）'}"
    )


def main() -> None:
    data = load_input()
    skus = data["skus"]
    budgets = [257, 180]
    factors = [("base", 1.0), ("low", 0.75), ("high", 1.25)]

    base_h = [heuristic_qty(s["rate"], s["available"], s["in_transit"]) for s in skus]
    assert sum(base_h) == 257, f"业务启发式合计应为 257，实际 {sum(base_h)}"
    assert base_h == [s["heuristic_qty"] for s in skus], "输入中的 heuristic_qty 与公式不一致"

    results: dict = {
        "meta": {
            "model": "OR-Tools CP-SAT, deterministic 12-month single-order model",
            "horizon_months": HORIZON,
            "lead_time_months": LEAD_TIME,
            "scale": SCALE,
            "holding_cost_per_unit_month": HOLD_COST,
            "shortage_penalty_per_unit_month": SHORT_COST,
            "fixed_order_cost_per_sku": FIXED_COST,
            "budgets": budgets,
            "demand_scenarios": {name: factor for name, factor in factors},
            "solver_time_limit_seconds": SOLVER_TIME_LIMIT,
            "solver_workers": 1,
            "seed": RANDOM_SEED,
            "input_file": "data/input.json",
        },
        "base": {},
        "sensitivity": {},
    }

    print("# E2 补货分配实验结果（自动生成）")
    print(f"\n输入：{len(skus)} 个 SKU；12 个月；交期 {LEAD_TIME} 个月；预算 {budgets}。")

    # 基础情景：业务启发式 257 与同预算缩放 180
    h257 = evaluate(skus, base_h, 1.0, budget=sum(base_h))
    h180_qty = scale_to_budget(base_h, 180)
    h180 = evaluate(skus, h180_qty, 1.0, budget=180)
    results["base"]["heuristic_257"] = {
        "policy": policy_summary("业务启发式 H257", h257),
        "per_sku": h257["per_sku"],
        "totals": h257["totals"],
    }
    results["base"]["heuristic_180_scaled"] = {
        "policy": policy_summary("按比例缩放的启发式 H180", h180),
        "qty": h180_qty,
        "per_sku": h180["per_sku"],
        "totals": h180["totals"],
    }

    print("\n## 启发式基线")
    print_policy_table("H257（业务公式，合计 257）", h257)
    print_policy_table("H180（H257 按比例缩放到 180，构造对照）", h180)

    # 基础情景两个预算的优化解
    for budget in budgets:
        sol = solve_cpsat(skus, budget, 1.0)
        key = f"opt_{budget}"
        results["base"][key] = {
            "status": sol["status"],
            "feasible": sol["feasible"],
            "runtime_seconds": sol["runtime_seconds"],
            "runtime_stage1_seconds": sol.get("runtime_stage1_seconds"),
            "runtime_stage2_seconds": sol.get("runtime_stage2_seconds"),
            "budget": budget,
            "qty": sol.get("qty"),
            "solver_objective": sol.get("solver_objective"),
            "tie_breaker_weighted_shortage": sol.get("tie_breaker_weighted_shortage"),
            "verification": sol.get("verification"),
            "policy": policy_summary(f"CP-SAT B={budget}", sol["evaluation"]),
            "per_sku": sol["evaluation"]["per_sku"],
            "totals": sol["evaluation"]["totals"],
        }
        print(
            f"\n## CP-SAT B={budget}\n\n"
            f"状态：{sol['status']}；运行时：{sol['runtime_seconds']:.3f} 秒；"
            f"目标值：{sol['solver_objective']:.2f}"
        )
        print_policy_table(f"CP-SAT B={budget}", sol["evaluation"])

    # 敏感性：±25% 需求
    for name, factor in factors:
        if factor == 1.0:
            continue
        h_qty = [heuristic_qty(s["rate"] * factor, s["available"], s["in_transit"]) for s in skus]
        h_eval = evaluate(skus, h_qty, factor, budget=sum(h_qty))
        entry = {
            "factor": factor,
            "heuristic_natural": {
                "qty": h_qty,
                "policy": policy_summary(f"H natural ×{factor}", h_eval),
                "totals": h_eval["totals"],
            },
            "heuristic_at_budget": {},
            "opt": {},
        }
        for budget in budgets:
            hb_qty = scale_to_budget(h_qty, budget)
            hb_eval = evaluate(skus, hb_qty, factor, budget=budget)
            entry["heuristic_at_budget"][str(budget)] = {
                "qty": hb_qty,
                "policy": policy_summary(f"H ×{factor} adjusted to B={budget}", hb_eval),
                "totals": hb_eval["totals"],
            }
            sol = solve_cpsat(skus, budget, factor)
            entry["opt"][str(budget)] = {
                "status": sol["status"],
                "feasible": sol["feasible"],
                "runtime_seconds": sol["runtime_seconds"],
                "runtime_stage1_seconds": sol.get("runtime_stage1_seconds"),
                "runtime_stage2_seconds": sol.get("runtime_stage2_seconds"),
                "qty": sol.get("qty"),
                "solver_objective": sol.get("solver_objective"),
                "tie_breaker_weighted_shortage": sol.get("tie_breaker_weighted_shortage"),
                "verification": sol.get("verification"),
                "policy": policy_summary(f"CP-SAT ×{factor} B={budget}", sol["evaluation"]),
                "per_sku": sol["evaluation"]["per_sku"],
                "totals": sol["evaluation"]["totals"],
            }
        results["sensitivity"][name] = entry

    # ------------------------------------------------------------------
    # 诊断：业务公式本质上是“6 个月总覆盖”的逐 SKU 下限
    # ------------------------------------------------------------------
    floor_qty = list(base_h)  # 与业务公式完全一致
    floor_moq_qty = [
        max(q, s["moq"]) if q > 0 else 0 for q, s in zip(floor_qty, skus)
    ]
    floor_moq_eval = evaluate(skus, floor_moq_qty, 1.0, budget=sum(floor_moq_qty))
    opt257_floor_violations = [
        x["sku"]
        for x in results["base"]["opt_257"]["per_sku"]
        if x["qty"] > 0 and x["coverage_total_months"] < 6.0 - 1e-9
    ]
    opt180_floor_violations = [
        x["sku"]
        for x in results["base"]["opt_180"]["per_sku"]
        if x["qty"] > 0 and x["coverage_total_months"] < 6.0 - 1e-9
    ]
    results["diagnostics"] = {
        "six_month_floor_qty": floor_qty,
        "six_month_floor_total": sum(floor_qty),
        "six_month_floor_note": (
            "业务公式 q=ceil(rate*6-available-in_transit) 的逐 SKU 最小值，"
            "等价于要求每个 SKU 的总覆盖 >= 6 个月；因此业务公式不是优化结果，"
            "而是该覆盖率下限的逐 SKU 取整实现。"
        ),
        "six_month_floor_with_moq_qty": floor_moq_qty,
        "six_month_floor_with_moq_total": sum(floor_moq_qty),
        "six_month_floor_with_moq_policy": policy_summary(
            "6 个月覆盖下限 + MOQ", floor_moq_eval
        ),
        "six_month_floor_with_moq_totals": floor_moq_eval["totals"],
        "opt257_skus_below_six_month_total_coverage": opt257_floor_violations,
        "opt180_skus_below_six_month_total_coverage": opt180_floor_violations,
    }

    # 不可消除的到货前缺货（t=0..2，任何 t=0 下单都来不及）
    pre_arrival = sum(
        max(0.0, LEAD_TIME * s["rate"] - s["available"]) for s in skus
    )
    results["meta"]["unavoidable_pre_arrival_shortage_base"] = round(pre_arrival, 2)

    # 预算-短缺关系诊断：在基础需求下，消除到货后缺货所需的最低下单量
    need_orders = 0
    for s in skus:
        post_demand = (HORIZON - LEAD_TIME) * s["rate"]
        post_supply = max(0.0, s["available"] - LEAD_TIME * s["rate"]) + s["in_transit"]
        need_orders += max(0.0, post_demand - post_supply)
    results["meta"]["orders_to_eliminate_post_arrival_shortage_base"] = round(need_orders, 2)

    RESULTS_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 控制台汇总
    print("\n## 汇总对比（基础需求）\n")
    print("| 策略 | 下单 | 持有(件·月) | 缺货(件) | 到货后前3月缺货 | 最长到货后缺货月数 | 评价成本 | MOQ |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for key in ["heuristic_257", "opt_257", "heuristic_180_scaled", "opt_180"]:
        p = results["base"][key]["policy"]
        print(
            f"| {p['label']} | {p['order_qty']} | {p['holding_unit_months']:.1f} | "
            f"{p['shortage_units']:.1f} | {p['shortage_3_5']:.1f} | "
            f"{p['max_stockout_months_post_arrival']} | {p['evaluation_cost']:.1f} | "
            f"{'是' if p['moq_feasible'] else '否'} |"
        )

    print("\n## 敏感性（±25% 需求，同预算对照）\n")
    print("| 情景 | 预算 | H 自然下单 | H@B 缺货 | Opt 缺货 | H@B 前3月缺货 | Opt 前3月缺货 | H@B 持有 | Opt 持有 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    total_demand = sum(s["rate"] for s in skus)

    def sens_row(label: str, factor: float, budget: int, h_policy: dict, o_policy: dict) -> str:
        return (
            f"| {label} | {budget} | {h_policy['order_qty']} | "
            f"{h_policy['shortage_units']:.1f} | {o_policy['shortage_units']:.1f} | "
            f"{h_policy['shortage_3_5']:.1f} | {o_policy['shortage_3_5']:.1f} | "
            f"{h_policy['holding_unit_months']:.1f} | {o_policy['holding_unit_months']:.1f} |"
        )

    # base 行使用实际业务启发式（H257）与按比例缩放的 H180
    print(
        sens_row(
            "base ×1.00",
            1.0,
            257,
            results["base"]["heuristic_257"]["policy"],
            results["base"]["opt_257"]["policy"],
        )
    )
    print(
        sens_row(
            "base ×1.00",
            1.0,
            180,
            results["base"]["heuristic_180_scaled"]["policy"],
            results["base"]["opt_180"]["policy"],
        )
    )
    for name in ["low", "high"]:
        e = results["sensitivity"][name]
        for budget in budgets:
            print(
                sens_row(
                    f"{name} ×{e['factor']:.2f}",
                    e["factor"],
                    budget,
                    e["heuristic_at_budget"][str(budget)]["policy"],
                    e["opt"][str(budget)]["policy"],
                )
            )
    print(
        "\n注：H@B = 把该情景下业务公式的自然下单量按比例调整到预算 B（最大余数法），"
        "仅用于同预算对照；它可能低于 MOQ。"
    )
    for name in ["low", "high"]:
        hp = results["sensitivity"][name]["heuristic_natural"]["policy"]
        print(
            f"- {name} ×{results['sensitivity'][name]['factor']:.2f}："
            f"H 自然下单 {hp['order_qty']} 件，缺货 {hp['shortage_units']:.1f} 件。"
        )

    d = results["diagnostics"]
    fm = d["six_month_floor_with_moq_policy"]
    print("\n## 诊断：业务公式 = 6 个月总覆盖下限\n")
    print(
        f"- 无 MOQ 时，逐 SKU 下限合计 {d['six_month_floor_total']} 件，"
        f"恰好等于业务启发式总量；在 B=257 下它是唯一可行点。"
    )
    print(
        f"- 加入 MOQ 后，2876 的 7 件低于 MOQ 8，下限合计变为 "
        f"{d['six_month_floor_with_moq_total']} 件（超出 257 预算 1 件）；"
        f"该可行解持有 {fm['holding_unit_months']:.1f} 件·月、缺货 {fm['shortage_units']:.1f} 件、"
        f"评价成本 {fm['evaluation_cost']:.1f}。"
    )
    print(
        f"- CP-SAT B=257 解低于 6 个月总覆盖的 SKU："
        f"{', '.join(d['opt257_skus_below_six_month_total_coverage']) or '无'}；"
        f"B=180 解：{', '.join(d['opt180_skus_below_six_month_total_coverage']) or '无'}。"
    )

    all_runtimes = [
        results["base"][f"opt_{b}"]["runtime_seconds"] for b in budgets
    ] + [
        results["sensitivity"][n]["opt"][str(b)]["runtime_seconds"]
        for n in ["low", "high"]
        for b in budgets
    ]
    print(f"\n求解器运行时：最小 {min(all_runtimes):.3f} 秒，最大 {max(all_runtimes):.3f} 秒。")
    print(f"\n结果已写入：{RESULTS_PATH}")


if __name__ == "__main__":
    main()
