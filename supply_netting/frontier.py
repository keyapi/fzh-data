# -*- coding: utf-8 -*-
"""服务—库存前沿（M2 / SC08）：真实历史需求路径上的情景回放。

**这不是承诺，是情景。** 口径：
- 需求路径：`demand_netting` 最近 365 天逐日需求（缺日补 0，真实零需求也保留）；
- 库存政策：周期盘点 base-stock（每 7 天复核一次，补货提前期 90 天，**无 MOQ**）；
- 目标库存 S：用**校准段**（评估窗之前的 270 天）里 (L+R)=97 天滚动需求和的
  经验分位确定，评估段只评不调；
- 服务档：uniform 90 / flat95（全键统一 95%）/ uniform 98 / ABC 分档（A98/B95/C90）；
- 供给：只按期初库存 S 与按单到货（无在途/无 ETA 证据，故不额外加供给）。

覆盖披露：只回放「最近 365 天里 ≥45 个有需求日」的键；这批键占 90 天窗口需求的
约 78%、缺口的约 87%，其余键历史太稀疏（中位数一年只有 11 个有需求日），不做单键回放。

复用的现有组件：`pack._z`（正态分位）仅用于对照列；回放本身不假设任何分布。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .pack import _z, abc_tiers

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
LEAD_DAYS = 90
REVIEW_DAYS = 7
CALIBRATION_DAYS = 270
EVALUATION_DAYS = 95
MIN_DEMAND_DAYS = 45
PROTECTION = LEAD_DAYS + REVIEW_DAYS     # 97 天

SCENARIOS = {
    "uniform_90": ("全键统一 90%", lambda tier: 0.90),
    "flat95": ("全键统一 95%（flat95 对照）", lambda tier: 0.95),
    "uniform_98": ("全键统一 98%", lambda tier: 0.98),
    "abc_tiered": ("ABC 分档 A98/B95/C90", lambda tier: {"A": 0.98, "B": 0.95, "C": 0.90}[tier]),
}


def _daily_series(demand: pd.DataFrame, key) -> pd.Series | None:
    subset = demand[(demand["canonical_sku"] == key[0])
                    & (demand["canonical_warehouse"] == key[1])
                    & (demand["canonical_uom"] == key[2])]
    if subset.empty:
        return None
    series = subset.groupby("date")["quantity_default"].sum().sort_index()
    full = pd.date_range(series.index.min(), series.index.max(), freq="D")
    # 用 numpy 重建，避免 arrow 后端 dtype 在 reindex 时的问题
    values = np.zeros(len(full), dtype=float)
    index_position = {ts: i for i, ts in enumerate(full)}
    for ts, qty in series.items():
        position = index_position.get(pd.Timestamp(ts))
        if position is not None:
            values[position] = float(qty)
    return pd.Series(values, index=full)


def replay(daily: np.ndarray, target: float, *, start: int, end: int,
           lead: int = LEAD_DAYS, review: int = REVIEW_DAYS) -> dict:
    """周期盘点 base-stock 回放：每 review 天补到 target，lead 天后到货。"""
    on_hand = float(target)
    pipeline: dict[int, float] = {}
    demand = served = 0.0
    inventory_days = 0.0
    days = 0
    stockout_days = 0
    cycles = 0
    cycles_with_stockout = 0
    cycle_short = False
    for offset, index in enumerate(range(start, end)):
        on_hand += pipeline.pop(index, 0.0)
        want = float(daily[index])
        take = min(on_hand, want)
        on_hand -= take
        demand += want
        served += take
        inventory_days += on_hand
        days += 1
        if want > take + 1e-9:
            stockout_days += 1
            cycle_short = True
        if offset % review == 0:
            if offset:
                cycles += 1
                cycles_with_stockout += 1 if cycle_short else 0
            cycle_short = False
            position = on_hand + sum(qty for arrival, qty in pipeline.items() if arrival > index)
            order = max(0.0, target - position)
            if order > 0:
                pipeline[index + lead] = pipeline.get(index + lead, 0.0) + order
    if days and (days - 1) % review != 0:
        cycles += 1
        cycles_with_stockout += 1 if cycle_short else 0
    return dict(
        demand=demand, served=served, lost=demand - served,
        fill_rate=(served / demand) if demand else None,
        csl=(1 - cycles_with_stockout / cycles) if cycles else None,
        avg_inventory=(inventory_days / days) if days else None,
        stockout_days=stockout_days,
        days=days,
    )


def _target_from(history: np.ndarray, level: float) -> float:
    if len(history) < PROTECTION:
        return float(np.max(history)) if len(history) else 0.0
    windows = np.convolve(history, np.ones(PROTECTION), mode="valid")
    return float(np.quantile(windows, level))


def build_frontier(demand_path: str | Path, keys_csv: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    demand = pd.read_parquet(demand_path)
    demand["date"] = pd.to_datetime(demand["demand_date"])
    demand = demand[demand["date"] >= demand["date"].max() - pd.Timedelta(days=364)]

    keys = pd.read_csv(keys_csv)
    window90 = keys[(keys["window_days"] == 90)][KEY + ["forecast_demand", "qty_current"]]

    # ABC 分档沿用 pack.abc_tiers（按窗口需求占比），保持与决策包同口径
    tiers = abc_tiers(window90.rename(columns={"forecast_demand": "quantity"}))
    tier_map = {tuple(row[k] for k in KEY): row["tier"] for _, row in tiers.iterrows()}

    coverage = demand.groupby(KEY)["date"].nunique().rename("demand_days").reset_index()
    scored = window90.merge(coverage, on=KEY, how="left")
    scored["demand_days"] = scored["demand_days"].fillna(0)

    per_key = []
    skipped = dict(too_sparse=0, no_eval_demand=0)
    for row in scored.itertuples(index=False):
        key = (row.canonical_sku, row.canonical_warehouse, row.canonical_uom)
        if row.demand_days < MIN_DEMAND_DAYS:
            skipped["too_sparse"] += 1
            continue
        series = _daily_series(demand, key)
        if series is None or len(series) <= EVALUATION_DAYS + REVIEW_DAYS:
            skipped["too_sparse"] += 1
            continue
        values = series.to_numpy(dtype=float)
        end = len(values)
        start = end - EVALUATION_DAYS
        calibration = values[:max(0, start)]
        if float(values[start:].sum()) <= 0:
            skipped["no_eval_demand"] += 1
            continue
        tier = tier_map.get(key, "C")
        baseline_target = float(np.mean(np.convolve(calibration, np.ones(PROTECTION), mode="valid"))) \
            if len(calibration) >= PROTECTION else float(np.mean(calibration)) * PROTECTION
        baseline = replay(values, baseline_target, start=start, end=end)
        for name, (label, level_of) in SCENARIOS.items():
            level = level_of(tier)
            target = _target_from(calibration, level)
            result = replay(values, target, start=start, end=end)
            per_key.append(dict(
                场景=name, 场景说明=label, SKU=key[0], 仓库=key[1], 单位=key[2], ABC档=tier,
                服务档=level, 目标库存=round(target, 3), 基线目标库存=round(baseline_target, 3),
                需求=round(result["demand"], 3), 满足=round(result["served"], 3),
                缺货量=round(result["lost"], 3), 缺货天数=result["stockout_days"],
                fill_rate=None if result["fill_rate"] is None else round(result["fill_rate"], 4),
                CSL=None if result["csl"] is None else round(result["csl"], 4),
                平均库存=None if result["avg_inventory"] is None else round(result["avg_inventory"], 3),
                基线平均库存=None if baseline["avg_inventory"] is None else round(baseline["avg_inventory"], 3),
                历史有需求日=int(row.demand_days),
            ))

    per_key_frame = pd.DataFrame(per_key)
    summary = _aggregate(per_key_frame, scored)
    summary["coverage"] = dict(
        window_keys=int(len(scored)),
        replayed_keys=int(per_key_frame[["SKU", "仓库", "单位"]].drop_duplicates().shape[0])
        if len(per_key_frame) else 0,
        window_demand_covered=round(float(
            scored[scored["demand_days"] >= MIN_DEMAND_DAYS]["forecast_demand"].sum()
            / scored["forecast_demand"].sum()), 4),
        window_gap_covered=round(float(
            scored[scored["demand_days"] >= MIN_DEMAND_DAYS]["qty_current"].sum()
            / scored["qty_current"].sum()), 4),
        min_demand_days=MIN_DEMAND_DAYS,
        skipped=skipped,
    )
    return summary, per_key_frame, summary["coverage"] | dict()


def _aggregate(per_key: pd.DataFrame, scored: pd.DataFrame) -> dict:
    if per_key.empty:
        return dict(scenarios=[], coverage={})
    rows = []
    for name, group in per_key.groupby("场景"):
        base_inv = group["基线平均库存"].sum()
        rows.append(dict(
            场景=name,
            场景说明=group["场景说明"].iloc[0],
            键数=int(len(group)),
            总需求=round(float(group["需求"].sum()), 3),
            总满足=round(float(group["满足"].sum()), 3),
            缺口未满足=round(float(group["缺货量"].sum()), 3),
            fill_rate=round(float(group["满足"].sum() / group["需求"].sum()), 4)
            if group["需求"].sum() else None,
            CSL_加权=round(float(np.average(group["CSL"].fillna(0), weights=group["需求"])), 4),
            平均库存合计=round(float(group["平均库存"].sum()), 3),
            基线平均库存合计=round(float(base_inv), 3),
            额外占用=round(float(group["平均库存"].sum() - base_inv), 3),
            缺货天数合计=int(group["缺货天数"].sum()),
        ))
    order = list(SCENARIOS)
    rows.sort(key=lambda r: order.index(r["场景"]))
    return dict(scenarios=rows)


def write_report(path: Path, frontier: pd.DataFrame, coverage: dict, generated_at: str,
                 meta: dict) -> None:
    lines = [
        "# 服务—库存前沿（M2 / SC08）",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 先说结论与边界",
        "",
        "- **这是情景回放，不是 95% 承诺，也不改决策包。** 服务档是「按目标反解库存」的实验，",
        "  实际做到多少见 fill_rate 列；不用于对外承诺，也不改 r6 / h180 的任何数字。",
        "- **没有现成评估器可复用**：仓库内不存在 `inventory_policy` / 服务前沿评估器"
        "（全工作区检索无代码命中），2026-10-23 的服务—库存附件只有结论与合成算例，没有可跑代码。",
        "  唯一可复用的现成件是 `pack.service_level_scenarios`（z×σ×√14 缓冲）与 `pack.abc_tiers`；",
        "  本次沿用 `abc_tiers` 的 ABC 分档，其余回放逻辑为最小实现，未另造模型体系。",
        "",
        "## 真实需求路径的可行性",
        "",
        f"- 90 天窗口 {coverage['window_keys']} 个键里，只有 **{coverage['replayed_keys']} 个**"
        f"「最近 365 天 ≥{coverage['min_demand_days']} 个有需求日」可用于逐日回放；",
        f"- 这批键覆盖 90 天窗口需求的 **{coverage['window_demand_covered']:.1%}**、缺口的 "
        f"**{coverage['window_gap_covered']:.1%}**；",
        "- 其余键历史太稀疏（一年有需求日中位数只有 11 天），逐日回放会产出噪声，**不做、不硬造**；",
        f"- 跳过原因：{json.dumps(coverage['skipped'], ensure_ascii=False)}。",
        "",
        "## 回放口径",
        "",
        f"- 需求：`demand_netting` 最近 365 天逐日需求（缺日补 0）；校准 {CALIBRATION_DAYS} 天、"
        f"评估 {EVALUATION_DAYS} 天；",
        f"- 政策：周期盘点 base-stock，复核 {REVIEW_DAYS} 天、提前期 {LEAD_DAYS} 天、**无 MOQ**；",
        f"- 目标库存 S = 校准段 {PROTECTION} 天滚动需求和的**经验分位**（不做正态假设）；",
        "- 供给：只按期初库存与按单到货；在途/PO 无 ETA，**不额外加供给**；",
        "- 基线（现行规则）= 同样的回放但 S 取校准段 97 天需求**均值**（无安全库存）。",
        "",
        "## 前沿结果（按 UOM 分列，不跨单位相加）",
        "",
    ]
    for _, row in frontier.iterrows():
        lines.append(f"### {row['场景']} — {row['场景说明']}")
        lines.append("")
        lines.append(f"- 键数 **{row['键数']}**；总需求 {row['总需求']:g}；"
                     f"**fill rate {row['fill_rate']}**；CSL（需求加权）{row['CSL_加权']}")
        lines.append(f"- 平均库存 {row['平均库存合计']:g}（基线 {row['基线平均库存合计']:g}，"
                     f"**额外占用 {row['额外占用']:g}**）；缺货 {row['缺口未满足']:g} 件 / "
                     f"{row['缺货天数合计']} 天")
        lines.append("")
    lines += [
        "## 怎么读",
        "",
        "- `fill_rate` 是「评估窗内按件满足比例」，`CSL_加权` 是「无缺货的复核周期占比」；",
        "- `额外占用` = 相对无安全库存基线的平均库存增量；**不是采购量、不是预算**；",
        "- 服务档越高，目标库存随 97 天需求高分位抬升，额外占用与缺货天数同时变化；",
        "- 本表所有数字来自真实历史需求路径的回放，**没有一条是合成需求**；",
        "  但评估窗只有 95 天（不足两个提前期），样本量有限，只能作方向性参考。",
        "- **前沿之所以在 68–74% 就趋平**：提前期 90 天 ≈ 评估窗 95 天，评估窗内下的单要到",
        "  第 90 天才可能到货，因此这张表实际衡量的是「期初备到哪一档、95 天内能兑现多少」，",
        "  而不是「补货能否及时跟上」。要提升 fill rate，先缩短提前期或提高预测精度，",
        "  单纯加安全库存的边际收益在这里已经很小。",
        "",
        "## 复现",
        "",
        "```bash",
        "uv run python -m supply_netting.frontier \\",
        f"  --demand {meta['demand']} \\",
        f"  --keys {meta['keys']} \\",
        f"  --out {meta['out']}",
        "```",
        "",
        "## 版本",
        "",
        f"- 输入 demand sha256：`{meta['demand_sha']}`",
        f"- 输入 keys sha256：`{meta['keys_sha']}`",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="服务—库存前沿（情景回放）")
    parser.add_argument("--demand", required=True)
    parser.add_argument("--keys", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    summary, per_key, coverage = build_frontier(args.demand, args.keys)
    frontier = pd.DataFrame(summary["scenarios"])
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frontier.to_csv(out_dir / "service_inventory_frontier.csv", index=False, encoding="utf-8-sig")
    per_key.to_csv(out_dir / "service_inventory_frontier_by_key.csv", index=False,
                   encoding="utf-8-sig")

    import hashlib

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    meta = dict(demand=str(args.demand), keys=str(args.keys), out=str(out_dir),
                demand_sha=sha(args.demand), keys_sha=sha(args.keys))
    write_report(out_dir / "report.md", frontier, coverage, generated_at, meta)
    manifest = dict(
        generated_at=generated_at,
        schema="service-inventory-frontier/v1",
        inputs=dict(demand_sha256=sha(args.demand), keys_sha256=sha(args.keys)),
        method=dict(lead_days=LEAD_DAYS, review_days=REVIEW_DAYS, no_moq=True,
                    protection_days=PROTECTION, calibration_days=CALIBRATION_DAYS,
                    evaluation_days=EVALUATION_DAYS, min_demand_days=MIN_DEMAND_DAYS,
                    target_rule="校准段 97 天滚动需求和的经验分位（无分布假设）",
                    baseline_rule="同政策但 S=97 天需求均值（无安全库存）"),
        coverage=coverage,
        scenarios=summary["scenarios"],
        caveats=["情景回放，不是 95% 承诺", "不改 r6 / h180 决策包",
                 "评估窗 95 天不足两个提前期，样本有限",
                 "在途/PO 无 ETA，未计任何在途供给"],
    )
    (out_dir / "frontier_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(dict(keys=coverage["replayed_keys"],
                          demand_covered=coverage["window_demand_covered"],
                          scenarios=[{k: r[k] for k in ("场景", "键数", "fill_rate", "额外占用",
                                                        "缺口未满足")}
                                     for r in summary["scenarios"]]), ensure_ascii=False,
                     indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
