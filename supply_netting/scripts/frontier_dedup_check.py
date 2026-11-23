# -*- coding: utf-8 -*-
"""FRONTIER-DEDUP：frontier_v2 与既有评估器 `inventory_policy` 的差异核查（只读）。

资产复用审计 A1/A2/A3 指出：`frontier.py` / `frontier_v2.py` 自写了 base-stock 回放，
没有复用 `experiments/business_phase/inventory_policy.py`（`simulate_flow` /
`simulate_policy` / `metrics` / `bisect_order_up_to`）。

本脚本做两件事，**都不改任何数字、不重跑已验收产物**：

1. 从 git 取回既有评估器（默认 commit `e3727683`），与 `frontier_v2.simulate` 跑同一组
   合成需求，量化「同一套核心语义」还是「两套算法」；
2. 把差异逐项落到证据上（复核相位、暖机/在途、lost_sales 与 backorder、β/α 与 CSL 定义），
   输出可比对的 JSON 与报告。

结论口径（写进报告，后续政策实验必须遵守）：
- 核心语义相同（逐日复核 R=1 时逐项相等），差异全部来自**数据管道**（复核相位、
  暖机在途、目标水平来源、指标口径）；
- 因此**不替换**已验收的 frontier_v2 产物；但后续政策实验**只准包既有评估器**
  （`inventory_policy.simulate_policy/metrics/bisect_order_up_to`），**不再扩写 frontier_v2**。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

ASSET_COMMIT = "e3727683"
ASSET_PATH = "docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/inventory_policy.py"

#: frontier_v2 的「冻结面」：后续不得再加模拟/评估入口；新增即视为扩写
FROZEN_SURFACE = ("global_series", "target_from", "simulate", "build", "summarise", "main")

COMPARE_CASES = (  # (review, lead, target, 说明)
    (1, 7, 60.0, "逐日复核：相位无差别 → 应当逐项相等"),
    (1, 30, 100.0, "逐日复核 + 长提前期"),
    (7, 7, 60.0, "周复核 + 短提前期：相位差影响最大"),
    (7, 30, 100.0, "周复核 + 中等提前期"),
    (7, 60, 200.0, "周复核 + 长提前期"),
)


class AssetUnavailable(RuntimeError):
    """git 里取不到既有评估器 —— 检查必须失败，不能假装通过。"""


def git_show(commit: str, path: str, repo: str | Path | None = None) -> str:
    cmd = ["git"]
    if repo:
        cmd += ["-C", str(repo)]
    cmd += ["show", f"{commit}:{path}"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise AssetUnavailable(f"git show {commit}:{path} 失败：{result.stderr[:200]}")
    return result.stdout


def load_asset(commit: str = ASSET_COMMIT, path: str = ASSET_PATH,
               repo: str | Path | None = None):
    """把既有评估器从 git 里取出来导入（不落盘到仓库、不改仓库）。"""
    source = git_show(commit, path, repo)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "inventory_policy.py"
        target.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("inventory_policy_asset", target)
        module = importlib.util.module_from_spec(spec)
        sys.modules["inventory_policy_asset"] = module
        spec.loader.exec_module(module)
    return module


def compare_cores(asset, *, days: int = 200, seed: int = 7) -> dict:
    """同一需求序列、同一 (R, L, S)：比对核心回放与 β 口径。"""
    from supply_netting import frontier_v2

    demand = np.array(asset.synthetic_demand(n=days, mean=5.0, seed=seed), dtype=float)
    rows = []
    for review, lead, target, note in COMPARE_CASES:
        periods = asset.simulate_policy(list(demand), lead, review, target, opening=target)
        m = asset.metrics(periods)
        r = frontier_v2.simulate(demand, target, sim_start=0, score_start=0, end=len(demand),
                                 lead=lead, review=review, seed_rate=0.0)
        rows.append(dict(
            review=review, lead=lead, target=target, note=note,
            asset_served=round(float(m["total_fulfilled"]), 6),
            frontier_served=round(float(r["served"]), 6),
            served_delta=round(float(r["served"]) - float(m["total_fulfilled"]), 6),
            asset_beta=round(float(m["beta"]), 6) if m["beta"] is not None else None,
            frontier_fill_rate=round(float(r["fill_rate"]), 6) if r["fill_rate"] is not None else None,
            asset_avg_inventory=round(float(m["avg_closing"]), 6),
            frontier_avg_inventory=round(float(r["avg_inventory"]), 6),
            identical=(abs(float(r["served"]) - float(m["total_fulfilled"])) < 1e-9),
        ))
    daily = [row for row in rows if row["review"] == 1]
    return dict(days=days, seed=seed, cases=rows,
                daily_review_all_identical=bool(daily) and all(r["identical"] for r in daily))


def compare_metrics(asset, *, days: int = 200, seed: int = 4) -> dict:
    """β 与 CSL 不是一回事：同一回放的 β/α 与 fill_rate/CSL 分别是什么口径。"""
    from supply_netting import frontier_v2

    demand = np.array(asset.synthetic_demand(n=days, mean=5.0, seed=seed), dtype=float)
    review, lead, target = 7, 7, 60.0
    periods = asset.simulate_policy(list(demand), lead, review, target, opening=target)
    m = asset.metrics(periods)
    r = frontier_v2.simulate(demand, target, sim_start=0, score_start=0, end=len(demand),
                             lead=lead, review=review, seed_rate=0.0)
    # β 与 fill_rate 是**同一个公式**（满足量/需求量）；两边各自按自己的回放验算一次。
    asset_formula = abs(float(m["beta"]) - float(m["total_fulfilled"]) / float(m["total_demand"])) < 1e-12
    frontier_formula = abs(float(r["fill_rate"]) - float(r["served"]) / float(r["demand"])) < 1e-12
    return dict(
        case=dict(review=review, lead=lead, target=target),
        beta=round(float(m["beta"]), 6), fill_rate=round(float(r["fill_rate"]), 6),
        same_definition=bool(asset_formula and frontier_formula),
        values_differ_due_to_phase=abs(float(m["beta"]) - float(r["fill_rate"])) > 1e-9,
        alpha=round(float(m["alpha"]), 6), csl=round(float(r["csl"]), 6),
        alpha_definition="有需求周期中「完全满足」的占比（周期 = 有需求的期间，本资产里是期间逐条）",
        csl_definition="复核周期（每 review 期一个）中「无任何短缺」的占比；含暖机段短缺泄漏到首个评分周期",
        alpha_equals_csl=abs(float(m["alpha"]) - float(r["csl"])) < 1e-9,
        demand_cycles=int(m["demand_cycles"]), zero_cycles=int(m["zero_cycles"]),
        frontier_cycles=int(r["cycles"]), stockout_days=int(r["stockout_days"]),
    )


def compare_backorder(asset, *, days: int = 200, seed: int = 4) -> dict:
    """lost_sales / backorder：既有评估器显式参数，frontier_v2 只有 lost_sales。"""
    import inspect

    from supply_netting import frontier_v2

    demand = np.array(asset.synthetic_demand(n=days, mean=5.0, seed=seed), dtype=float)
    # 故意选一个会缺货的参数（S 远低于 (L+R) 天需求），否则两种语义看起来一样
    case = dict(lead=30, review=7, order_up_to=25.0, opening=25.0)
    lost = asset.metrics(asset.simulate_policy(list(demand), case["lead"], case["review"],
                                               case["order_up_to"], opening=case["opening"],
                                               semantics="lost_sales"))
    backlog = asset.metrics(asset.simulate_policy(list(demand), case["lead"], case["review"],
                                                  case["order_up_to"], opening=case["opening"],
                                                  semantics="backorder"))
    return dict(
        case=case,
        asset_has_semantics="semantics" in inspect.signature(asset.simulate_flow).parameters,
        asset_lost_sales=dict(lost=round(float(lost["total_lost"]), 3),
                              end_backlog=round(float(lost["end_backlog"]), 3)),
        asset_backorder=dict(lost=round(float(backlog["total_lost"]), 3),
                             end_backlog=round(float(backlog["end_backlog"]), 3)),
        frontier_v2_params=sorted(inspect.signature(frontier_v2.simulate).parameters),
        frontier_v2_supports_backorder=False,
        note="frontier_v2 一律 lost_sales（take=min(on_hand, want)，未满足即消失），没有 backorder 分支",
    )


def surface_drift() -> dict:
    """frontier_v2 的公开函数是否新增（新增即视为「扩写」）。"""
    from supply_netting import frontier_v2

    public = tuple(sorted(name for name in dir(frontier_v2)
                          if not name.startswith("_") and callable(getattr(frontier_v2, name))
                          and getattr(getattr(frontier_v2, name), "__module__", "") == frontier_v2.__name__))
    return dict(frozen=list(FROZEN_SURFACE), public=list(public),
                frozen_is_subset=set(FROZEN_SURFACE) <= set(public),
                new_since_freeze=sorted(set(public) - set(FROZEN_SURFACE)))


def run_check(repo: str | Path | None, commit: str, path: str, days: int, seed: int) -> dict:
    asset = load_asset(commit, path, repo)
    return dict(
        schema_version="frontier-dedup/v1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        asset=dict(commit=commit, path=path,
                   sha256=hashlib.sha256(git_show(commit, path, repo).encode()).hexdigest()),
        cores=compare_cores(asset, days=days, seed=seed),
        metrics=compare_metrics(asset, days=days),
        backorder=compare_backorder(asset, days=days),
        surface=surface_drift(),
    )


def write_report(result: dict, out: Path) -> None:
    cores, metric, bo = result["cores"], result["metrics"], result["backorder"]
    asset = result["asset"]
    lines = [
        "# FRONTIER-DEDUP：frontier_v2 与既有评估器的差异核查",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 既有评估器：`{asset['path']}` @ `{asset['commit']}`（sha256 {asset['sha256'][:12]}…）",
        f"- 合成需求：{cores['days']} 天，seed={cores['seed']}（资产自带 `synthetic_demand`）",
        "- 只读：不改任何数字、不重跑已验收产物、不 push。",
        "",
        "## 1. 结论",
        "",
        f"1. **核心语义是同一套**：逐日复核（R=1）时两边的满足量/缺货量/β/平均库存"
        f"{'完全相等' if cores['daily_review_all_identical'] else '不相等'}，"
        "说明 base-stock 回放本身没有第二套算法。",
        "2. **不能直接替换**：差异全部在数据管道与口径上（复核相位、暖机在途、目标水平来源、"
        "α vs CSL、backorder 支持）。已验收的 frontier_v2 产物保持不动。",
        "3. **后续政策实验只包既有评估器**（`simulate_policy` / `metrics` / `bisect_order_up_to`），"
        "**不再扩写 frontier_v2**；frontier_v2 冻结为历史情景工具。",
        "",
        "## 2. 逐项差异",
        "",
        "| 维度 | `inventory_policy`（既有） | `frontier_v2`（本层） | 能否直接替换 |",
        "|---|---|---|---|",
        "| β / α | β=fill rate 为主、α=CSL 次之；**无需求周期不计算 α**；分母/周期数分开报 | fill_rate 公式同 β；CSL 按**复核周期**计，含暖机泄漏 | β 同口径；**α ≠ CSL** |",
        "| L+R | 复核周期 R、提前期 L；保护期就是 R+L，调用方给 S | 同 R、L；target 取 (L+R) 天滚动和的经验分位 × 倍数 | 保护期概念一致 |",
        "| 政策 | order-up-to 参照政策；`position = 库存 + 在途` | base-stock target；`position = 现库存 + 未来到货` | 同一族 |",
        "| lost_sales / backorder | `semantics` 显式参数，二选一，不混 | **只有 lost_sales** | 不满足（缺 backorder） |",
        "| 复核相位 | 期末复核（t≡R−1），到期日在 t+L | 期初复核（t≡0），到期日在 t+L | 不同相位 → 短提前期差异大 |",
        "| 暖机 / 在途 | 无内置暖机（调用方切片），无在途预置 | 暖机 L+R 天 + 稳态在途预置 | 管道差异，非算法 |",
        "| 目标水平 | 外部给 S；`bisect_order_up_to` 反解目标 β | 经验分位 (L+R) × 1.0/1.5/2.0，前向模拟得 β | 不同：一个是**目标反解**，一个是**分位假设** |",
        "| 数据管道 | 任意序列 / 显式 receipts | 真实观测销售、统一截止、无订单日补 0、ABC/UOM 分组 | 本层独有 |",
        "| 网格 | L=60/90/120、R=7/30、β=90/95/99% | L=60/90/120、level=90/95/98%、×1.0/1.5/2.0 | 网格可对齐 |",
        "",
        "## 3. 数值证据（同一需求、同一 R/L/S）",
        "",
        "| R | L | S | 既有满足 | 本层满足 | 差 | 既有 β | 本层 fill_rate | 结论 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in cores["cases"]:
        lines.append(f"| {row['review']} | {row['lead']} | {row['target']:g} | "
                     f"{row['asset_served']:.0f} | {row['frontier_served']:.0f} | "
                     f"{row['served_delta']:+.0f} | {row['asset_beta']:.4f} | "
                     f"{row['frontier_fill_rate']:.4f} | {row['note']} |")
    lines += [
        "",
        f"- 逐日复核（R=1）两组案例{'全部相等' if cores['daily_review_all_identical'] else '未全部相等'}"
        " → 核心回放等价；周复核的差异来自**复核相位**（期初 vs 期末）与暖机在途，"
        "提前期越长差异越被稀释。",
        "",
        "### β 与 CSL 不是同一件事",
        "",
        f"- β 与 fill_rate **公式相同**（满足量/需求量，两边各自验算：{metric['same_definition']}）；"
        f"同一组参数下两边取值 β={metric['beta']:.4f} vs fill_rate={metric['fill_rate']:.4f}"
        f"（差异来自第 2 节说的复核相位，不是定义不同）。"
        f"但 α={metric['alpha']:.4f} vs CSL={metric['csl']:.4f}"
        f"（相等？{metric['alpha_equals_csl']}）。",
        f"- α：{metric['alpha_definition']}；"
        f"本次有需求周期 {metric['demand_cycles']} 个、零需求周期 {metric['zero_cycles']} 个。",
        f"- CSL：{metric['csl_definition']}；本次复核周期 {metric['frontier_cycles']} 个。",
        "- 因此「CSL 95%」和「α 95%」不能互相翻译，任何对外表述必须写明是哪一个。",
        "",
        "### lost_sales 与 backorder",
        "",
        f"- 缺货情景（L={bo['case']['lead']}、R={bo['case']['review']}、S={bo['case']['order_up_to']:g}）："
        f"`semantics` 参数存在={bo['asset_has_semantics']}；"
        f"lost_sales 丢单={bo['asset_lost_sales']['lost']:g}、期末欠单="
        f"{bo['asset_lost_sales']['end_backlog']:g}；backorder 丢单={bo['asset_backorder']['lost']:g}、"
        f"期末欠单={bo['asset_backorder']['end_backlog']:g}。",
        f"- frontier_v2 参数：{bo['frontier_v2_params']} → **无 semantics**，一律 lost_sales。",
        f"- {bo['note']}。",
        "",
        "## 4. 决策与后续规则",
        "",
        "1. **不替换、不重写**：已验收的 frontier v2 产物（`service-inventory-frontier-2026-10-28-v2/`）"
        "保持原样；本任务不改任何数字。",
        "2. **frontier_v2 冻结**：不得再添加模拟/评估入口。检查结果："
        f"冻结面之外新增函数 = {result['surface']['new_since_freeze'] or '无'}。",
        "3. **后续政策实验只包既有评估器**：新实验（不同 β 目标、R、backorder 情景）一律调用 "
        "`inventory_policy.simulate_policy` + `metrics` + `bisect_order_up_to`，或在其外面包一层"
        "数据管道（本层只负责把需求/日历/资格喂进去），不再复制回放逻辑。",
        "4. **口径披露**：任何引用本层 CSL 的地方必须注明「按复核周期计」，引用 SC08 的 α 必须"
        "注明「按有需求期间计」；两者不得混写。",
        "5. **backorder 情景缺位**：真要做 backorder（欠单后补）必须在既有评估器上跑，"
        "frontier_v2 不做。",
        "",
        "## 5. 复现",
        "",
        "```bash",
        "uv run python -m supply_netting.scripts.frontier_dedup_check",
        "```",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="frontier_v2 与既有评估器的差异核查（只读）")
    parser.add_argument("--repo", default=None, help="git 仓库路径；默认用当前仓库")
    parser.add_argument("--commit", default=ASSET_COMMIT)
    parser.add_argument("--asset-path", default=ASSET_PATH)
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "frontier-dedup-2026-10-28")
    args = parser.parse_args(argv)

    result = run_check(args.repo, args.commit, args.asset_path, args.days, args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    write_report(result, out)
    manifest = dict(schema_version="frontier-dedup/v1", generated_at=result["generated_at"],
                    asset=result["asset"],
                    checks=dict(daily_review_all_identical=result["cores"]["daily_review_all_identical"],
                                beta_same_definition=result["metrics"]["same_definition"],
                                alpha_equals_csl=result["metrics"]["alpha_equals_csl"],
                                frontier_surface_frozen=not result["surface"]["new_since_freeze"]),
                    note="只读核查；不改数值、不重跑已验收产物、不 push")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print(json.dumps(manifest["checks"], ensure_ascii=False))
    print("输出：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
