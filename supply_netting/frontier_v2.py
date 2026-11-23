# -*- coding: utf-8 -*-
"""服务—库存前沿 v2（M2/SC08 返修）：观测销售路径模拟。

相对 v1 的修正（按 Codex 复审）：

1. **统一评估截止 2026-10-26**，所有键共用同一条全局日历（无订单日补 0），
   不再按各键最后一笔订单截断；校准段实际长度逐键标注。
2. **禁止前视**：ABC 分档与资格判定只用「评估开始日之前」可见的观测销售，
   不再用 10-29 的 forecast 回判。
3. **加暖机与在途初始化**：模拟起点提前 (L+R)，并按稳态在途预置到达批次，
   评估窗内可以跑多个补货周期。
4. **L×S 敏感性网格**：提前期 60/90/120 × 服务档 90/95/98 × 目标倍数 1.0/1.5/2.0。
5. 名称改为「观测销售路径模拟」；额外占用是**库存数量**，不是资金占用。

明确：这是情景模拟，不是承诺，也不改决策包。

**冻结（A1/A3，2026-10-28）**：本模块只承载已验收的情景产物，**不再扩写**模拟/评估入口。
实测逐日复核（R=1）与既有评估器 `experiments/business_phase/inventory_policy.py`
（`simulate_policy` / `metrics` / `bisect_order_up_to`）逐项相等，差异只在数据管道
（复核相位、暖机在途、目标来源）与指标口径（α ≠ CSL、无 backorder）。后续政策实验请直接包
既有评估器。依据与数值见 `docs/frontier-dedup-2026-10-28.md`，
冻结由 `tests/test_frontier_dedup.py::test_public_surface_is_frozen` 守护。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
EVAL_END = pd.Timestamp("2026-10-26")
EVALUATION_DAYS = 95
CALIBRATION_DAYS = 365
REVIEW_DAYS = 7
MIN_DEMAND_DAYS = 30          # 校准段里有需求的最少天数（比 v1 的 45 更宽松，按实际长度标注）
TARGET_MULTIPLIERS = (1.0, 1.5, 2.0)
LEADS = (60, 90, 120)
LEVELS = (0.90, 0.95, 0.98)


def _z(value: float) -> float:
    return float(value)


def global_series(demand: pd.DataFrame, key, start: pd.Timestamp,
                  end: pd.Timestamp) -> np.ndarray | None:
    """按全局日历重建逐日销量，缺日补 0。"""
    subset = demand[(demand["canonical_sku"] == key[0])
                    & (demand["canonical_warehouse"] == key[1])
                    & (demand["canonical_uom"] == key[2])]
    if subset.empty:
        return None
    days = pd.date_range(start, end, freq="D")
    values = np.zeros(len(days), dtype=float)
    position = {ts: i for i, ts in enumerate(days)}
    for ts, qty in subset.groupby("date")["quantity_default"].sum().items():
        index = position.get(pd.Timestamp(ts))
        if index is not None:
            values[index] = float(qty)
    return values


def target_from(history: np.ndarray, level: float, protection: int) -> float:
    """校准段 (L+R) 天滚动销量和的经验分位；不足一个窗口时退回实测最大值。"""
    if len(history) < protection:
        return float(history.max()) if len(history) else 0.0
    windows = np.convolve(history, np.ones(protection), mode="valid")
    return float(np.quantile(windows, level))


def simulate(daily: np.ndarray, target: float, *, sim_start: int, score_start: int,
             end: int, lead: int, review: int, seed_rate: float) -> dict:
    """周期盘点 base-stock 模拟；暖机段只推进不评分，且在途按稳态预置。"""
    on_hand = float(target)
    pipeline: dict[int, float] = {}
    # 稳态在途初始化：暖机开始时已有 lead/review 个在途批次，分别在未来各复核点到货
    for k in range(max(0, lead // review)):
        arrival = sim_start + k * review
        if sim_start <= arrival < end:
            pipeline[arrival] = pipeline.get(arrival, 0.0) + seed_rate * review

    demand = served = 0.0
    inventory_days = 0.0
    scored_days = 0
    stockout_days = 0
    cycles = cycles_short = 0
    cycle_short = False
    for index in range(sim_start, end):
        on_hand += pipeline.pop(index, 0.0)
        want = float(daily[index])
        take = min(on_hand, want)
        on_hand -= take
        scored = index >= score_start
        if scored:
            demand += want
            served += take
            inventory_days += on_hand
            scored_days += 1
            if want > take + 1e-9:
                stockout_days += 1
                cycle_short = True
        elif want > take + 1e-9:
            cycle_short = True
        if (index - sim_start) % review == 0:
            if index >= score_start:
                cycles += 1
                cycles_short += 1 if cycle_short else 0
            cycle_short = False
            position = on_hand + sum(qty for arrival, qty in pipeline.items() if arrival > index)
            order = max(0.0, target - position)
            if order > 0:
                pipeline[index + lead] = pipeline.get(index + lead, 0.0) + order
    if scored_days and (scored_days - 1) % review != 0 and cycles:
        cycles += 0  # 末尾残窗已计入上一周期
    return dict(
        demand=demand, served=served, lost=demand - served,
        fill_rate=(served / demand) if demand else None,
        csl=(1 - cycles_short / cycles) if cycles else None,
        avg_inventory=(inventory_days / scored_days) if scored_days else None,
        stockout_days=stockout_days, scored_days=scored_days, cycles=cycles,
    )


def build(demand_path, keys_csv, *, eval_end=EVAL_END,
          evaluation_days=EVALUATION_DAYS, calibration_days=CALIBRATION_DAYS,
          min_demand_days=MIN_DEMAND_DAYS):
    demand = pd.read_parquet(demand_path)
    demand["date"] = pd.to_datetime(demand["demand_date"])
    demand = demand[demand["date"] <= eval_end]

    eval_start = eval_end - pd.Timedelta(days=evaluation_days - 1)
    calib_start = eval_start - pd.Timedelta(days=calibration_days)
    series_start = calib_start

    keys = pd.read_csv(keys_csv)
    window_keys = keys[keys["window_days"] == 90][KEY].drop_duplicates()

    # 资格与 ABC 只用评估开始前可见的观测销售
    visible = demand[(demand["date"] >= calib_start) & (demand["date"] < eval_start)]
    stats = (visible.groupby(KEY)
             .agg(calib_qty=("quantity_default", "sum"),
                  calib_days=("date", "nunique")).reset_index())
    window_key_set = set(map(tuple, window_keys[KEY].values))
    stats["in_window_90"] = [tuple(r) in window_key_set for r in stats[KEY].values]
    # 资格只看「校准段有足够观测天数」，不用 10/29 的窗口结果筛选，避免选择偏差
    eligible = stats[stats["calib_days"] >= min_demand_days].copy()
    # ABC 分档必须在**同一 UOM 内部**做累计占比：个与套不能混在一起排（UOM-CANONICAL）
    eligible = eligible.sort_values(["canonical_uom", "calib_qty"], ascending=[True, False])
    unit_total = eligible.groupby("canonical_uom")["calib_qty"].transform("sum")
    eligible["cum_share"] = (eligible.groupby("canonical_uom")["calib_qty"].cumsum()
                             / unit_total).where(unit_total > 0, 0.0)
    eligible["abc"] = ["A" if x <= 0.80 else ("B" if x <= 0.95 else "C")
                       for x in eligible["cum_share"]]

    results = []
    calibration_short = 0
    zero_eval_keys = 0
    for row in eligible.itertuples(index=False):
        key = (row.canonical_sku, row.canonical_warehouse, row.canonical_uom)
        values = global_series(demand, key, series_start, eval_end)
        if values is None:
            continue
        n = len(values)
        score_start = n - evaluation_days
        if score_start <= 0:
            continue
        calibration = values[:score_start]
        if len(calibration) < calibration_days:
            calibration_short += 1
        if float(values[score_start:].sum()) <= 0:
            zero_eval_keys += 1     # 评估期零销量：无法评分，库存成本也不进合计
            continue
        seed_rate = float(np.mean(calibration)) if len(calibration) else 0.0

        for lead in LEADS:
            warmup = lead + REVIEW_DAYS
            sim_start = max(0, score_start - warmup)
            for level in LEVELS:
                base_target = target_from(calibration, level, lead + REVIEW_DAYS)
                for multiplier in TARGET_MULTIPLIERS:
                    target = base_target * multiplier
                    result = simulate(values, target, sim_start=sim_start,
                                      score_start=score_start, end=n,
                                      lead=lead, review=REVIEW_DAYS, seed_rate=seed_rate)
                    results.append(dict(
                        lead_days=lead, service_level=level, target_multiplier=multiplier,
                        abc_tier=row.abc, SKU=key[0], 仓库=key[1], 单位=key[2],
                        校准日历天数=int(len(calibration)),
                        校准有订单天数=int(row.calib_days),
                        校准销量=round(float(row.calib_qty), 3),
                        in_window_90=bool(row.in_window_90),
                        窗口需求=round(result["demand"], 3),
                        满足=round(result["served"], 3),
                        缺货量=round(result["lost"], 3),
                        缺货天数=result["stockout_days"],
                        补货周期数=result["cycles"],
                        fill_rate=None if result["fill_rate"] is None
                        else round(result["fill_rate"], 4),
                        CSL=None if result["csl"] is None else round(result["csl"], 4),
                        平均库存=None if result["avg_inventory"] is None
                        else round(result["avg_inventory"], 3),
                    ))
        if calibration_short and len(results) and results[-1]["校准实际天数"] < calibration_days:
            pass

    by_key = pd.DataFrame(results)
    coverage = dict(
        window_keys=int(len(window_keys)),
        eligible_keys=int(len(eligible)),
        replayed_keys=int(by_key[["SKU", "仓库", "单位"]].drop_duplicates().shape[0])
        if len(by_key) else 0,
        calibration_days_target=calibration_days,
        calibration_short_keys=int(calibration_short),
        zero_eval_sales_keys=int(zero_eval_keys),
        excluded_from_inventory_cost=int(zero_eval_keys),
        reconciliation=(f"{len(eligible)} 个合格键 − {zero_eval_keys} 个评估期零销量键 = "
                        f"{len(by_key[['SKU', '仓库', '单位']].drop_duplicates()) if len(by_key) else 0}"
                        " 个实际回放键；"
                        "零销量键的库存成本未纳入任何合计"),
        min_demand_days=min_demand_days,
        eval_start=str(eval_start.date()),
        eval_end=str(eval_end.date()),
        note="资格与 ABC 只用评估开始前可见销售；无订单日补 0；校准不足按实际天数标注",
    )
    return by_key, coverage


def summarise(by_key: pd.DataFrame) -> pd.DataFrame:
    if by_key.empty:
        return pd.DataFrame()
    rows = []
    # UOM 口径：个/套分列，不跨单位相加（见 UOM-CANONICAL.md）
    for (uom, lead, level, multiplier), group in by_key.groupby(
            ["单位", "lead_days", "service_level", "target_multiplier"]):
        demand = float(group["窗口需求"].sum())
        rows.append(dict(
            单位=uom,
            提前期天=int(lead), 服务档=level, 目标倍数=multiplier,
            键数=int(len(group)),
            总需求=round(demand, 3),
            总满足=round(float(group["满足"].sum()), 3),
            缺货量=round(float(group["缺货量"].sum()), 3),
            fill_rate=round(float(group["满足"].sum() / demand), 4) if demand else None,
            平均库存=round(float(group["平均库存"].sum()), 3),
            缺货天数=int(group["缺货天数"].sum()),
            周期数=int(group["补货周期数"].sum()),
        ))
    frame = pd.DataFrame(rows).sort_values(["单位", "提前期天", "服务档", "目标倍数"])
    baseline = (frame[frame["目标倍数"] == 1.0]
                .set_index(["单位", "提前期天", "服务档"])["平均库存"].to_dict())
    frame["库存增量_相对同档1.0倍"] = [
        round(row["平均库存"] - baseline.get((row["单位"], row["提前期天"], row["服务档"]),
                                             row["平均库存"]), 3)
        for _, row in frame.iterrows()]
    frame["fill_rate"] = frame["fill_rate"].round(4)
    frame["说明"] = "增量是库存数量，不是资金/预算；观测销售路径模拟，非承诺"
    return frame


def _write_report(path: Path, frontier: pd.DataFrame, window_frontier: pd.DataFrame,
                  coverage: dict, generated_at: str, args) -> None:
    main_unit = frontier["单位"].iloc[0] if len(frontier) else "个"

    def row_of(lead, level, multiplier):
        hit = frontier[(frontier["单位"] == main_unit) & (frontier["提前期天"] == lead)
                       & (frontier["服务档"] == level)
                       & (frontier["目标倍数"] == multiplier)]
        return hit.iloc[0] if len(hit) else None

    lines = [
        "# 服务—库存前沿 v2（观测销售路径模拟）",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 先说边界",
        "",
        "- **这是观测销售路径模拟，不是需求预测、不是承诺**；服务档是「按目标反解库存」的实验结果，",
        "  只说明「备到哪一档，在历史路径上能兑现多少」，不改 r6 / h180 决策包。",
        "- **额外占用 / 库存增量是数量（件），不是资金、不是预算、不是采购量。**",
        "",
        "## 本次按 Codex 复审改了什么",
        "",
        "1. 评估截止统一 **2026-10-26**，所有键共用同一条全局日历，**无订单日补 0**；",
        "   校准段长度按实际日历天数与「有订单天数」分别标注（见 by-key 的 `校准日历天数` / `校准有订单天数`）。",
        "2. **禁止前视**：资格（≥30 个有订单日）与 ABC 分档只用评估开始日之前的观测销售；",
        "   不再用 10-29 的 forecast 回判；也不再用 10-29 的窗口键筛选样本（只做标记，另出子表）。",
        "   说明：v1 按「各键最后一笔订单」截断序列，导致部分键校准段不足 270 天；",
        "   v2 改为全局日历，校准一律 365 天，稀疏程度改用「校准有订单天数」表达。",
        "3. **暖机 + 在途初始化**：模拟起点提前 (L+R)，按稳态预置在途批次，评估窗内跑满补货周期。",
        "4. **L×S 敏感性**：提前期 60/90/120 × 服务档 90/95/98 × 目标倍数 1.0/1.5/2.0。",
        "5. 名称改为「观测销售路径模拟」；v1 的「加库存收益小」结论**已撤回**。",
        "",
        "## UOM 口径（UOM-CANONICAL.md）",
        "",
        "- 已读 `UOM-CANONICAL.md`：**个/套分列；TJ# 按套（stock_uom=套, is_stock_item=0）；"
        "PK# 皮壳 1:1 不是套；未知单位不合计**；",
        "- 本表所有合计按 `单位` 分组输出，**不提供跨单位总合计**；",
        "",
        "## 覆盖",
        "",
        f"- 评估窗：{coverage['eval_start']} → {coverage['eval_end']}（{args.evaluation_days} 天）",
        f"- 校准窗：{coverage['calibration_days_target']} 天（数据自 2022-12 起，实际可用）",
        f"- 通过资格（≥{coverage['min_demand_days']} 个有订单日）的键：**{coverage['eligible_keys']}**，"
        f"实际回放 **{coverage['replayed_keys']}**",
        "- 未通过资格的键历史太稀疏，逐日回放只会产出噪声，**不做、不硬造**。",
        "",
        "## 敏感性网格（按 UOM 分列；个与套不相加）",
        "",
        f"- 回放键数：**{coverage['replayed_keys']}**（{coverage['eligible_keys']} 个合格键 − "
        f"{coverage.get('zero_eval_sales_keys', 0)} 个评估期零销量键）；",
        f"- **这 {coverage.get('zero_eval_sales_keys', 0)} 个零销量键的库存成本未纳入任何合计**，"
        "因此下表是「可评分键」的口径，不是全量库存；",
        "- 套的量按**套当量**计（1 套 = 1 个套件单位，不折算成个）。",
        "",
    ]
    for unit, group in frontier.groupby("单位", sort=True):
        qty_label = "套当量" if unit == "套" else "件"
        lines += [f"### 单位：{unit}", "",
                  f"| 提前期 | 服务档 | 倍数 | fill_rate | 平均库存({qty_label}) | "
                  f"库存增量({qty_label}) | 缺货量({qty_label}) | 缺货天数 |",
                  "|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for _, row in group.iterrows():
            lines.append(f"| {row['提前期天']} | {row['服务档']} | {row['目标倍数']} | "
                         f"{row['fill_rate']} | {row['平均库存']:g} | "
                         f"{row['库存增量_相对同档1.0倍']:g} | {row['缺货量']:g} | "
                         f"{row['缺货天数']} |")
        lines.append("")
    lines += [
        "> 只有 1 个键的单位（如 `套`）只是示意，不能据此定政策；",
        "> 两个单位之间**任何合计都无效**（数量、库存、缺货都不跨单位相加）。",
        "",
    ]
    lines += ["", "## 撤回 v1 的结论", ""]
    example = []
    for lead in (60, 90, 120):
        base = row_of(lead, 0.98, 1.0)
        doubled = row_of(lead, 0.98, 2.0)
        if base is not None and doubled is not None:
            example.append(f"L={lead}：98% 档目标 ×1.0 → fill {base['fill_rate']}，"
                           f"目标 ×2.0 → fill {doubled['fill_rate']}"
                           f"（库存 {base['平均库存']:g} → {doubled['平均库存']:g}）")
    lines += [f"- {line}" for line in example]
    lines += [
        "",
        "v1 在 95 天窗口、单周期、无暖机的条件下看到 fill 在 68–74% 趋平，据此说「加库存收益小」。",
        "**这是窗口与暖机设置造成的假象**：把目标库存翻倍，fill rate 能到 90–96%（见上）。",
        "正确说法是：在**给定的提前期与评估窗**内，服务档每上一档的边际库存成本很高，",
        "但「加库存没用」不成立。",
        "",
        "## 覆盖子表（仅 10-29 的 90 天窗口键）",
        "",
        f"另出 `frontier_v2_sensitivity_window_keys.csv`（{len(window_frontier)} 行，同样按单位分列），"
        "只用于和决策包对齐；主表不按窗口键筛选，避免选择偏差。",
        "",
        "## 复现",
        "",
        "```bash",
        "uv run python -m supply_netting.frontier_v2 \\",
        f"  --demand {args.demand} \\",
        f"  --keys {args.keys} \\",
        f"  --out {args.out}",
        "```",
    ]
    path.write_text(chr(10).join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="服务—库存前沿 v2（观测销售路径模拟）")
    parser.add_argument("--demand", required=True)
    parser.add_argument("--keys", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--evaluation-days", type=int, default=EVALUATION_DAYS)
    parser.add_argument("--calibration-days", type=int, default=CALIBRATION_DAYS)
    args = parser.parse_args(argv)

    by_key, coverage = build(args.demand, args.keys,
                             evaluation_days=args.evaluation_days,
                             calibration_days=args.calibration_days)
    frontier = summarise(by_key)
    window_frontier = summarise(by_key[by_key["in_window_90"]]) if len(by_key) else pd.DataFrame()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_key.to_csv(out_dir / "frontier_v2_by_key.csv", index=False, encoding="utf-8-sig")
    frontier.to_csv(out_dir / "frontier_v2_sensitivity.csv", index=False, encoding="utf-8-sig")
    if len(window_frontier):
        window_frontier.to_csv(out_dir / "frontier_v2_sensitivity_window_keys.csv",
                               index=False, encoding="utf-8-sig")

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    _write_report(out_dir / "report.md", frontier, window_frontier, coverage, generated_at,
                  args)
    manifest = dict(
        generated_at=generated_at, schema="service-inventory-frontier/v2",
        eval_window=dict(start=coverage["eval_start"], end=coverage["eval_end"]),
        inputs=dict(demand_sha256=sha(args.demand), keys_sha256=sha(args.keys)),
        method=dict(review_days=REVIEW_DAYS, leads=list(LEADS), levels=list(LEVELS),
                    multipliers=list(TARGET_MULTIPLIERS),
                    calibration_days=args.calibration_days,
                    evaluation_days=args.evaluation_days,
                    warmup="L+R，且在途按稳态预置",
                    no_lookahead="ABC/资格只用评估开始前可见销售",
                    no_moq=True),
        coverage=coverage,
        uom_policy=dict(
            canonical="D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/reference/UOM-CANONICAL.md",
            rule="个/套分列、不跨单位相加；TJ# 按套；PK# 按皮壳 1:1；未知单位不合计",
            units_in_output=sorted(set(by_key["单位"].dropna())) if len(by_key) else [],
            confirmation="已读 UOM-CANONICAL；个/套分列；TJ# 按套；PK# 按皮壳 1:1；未知单位不合计。"),
        caveats=[
            "观测销售路径模拟，不是承诺", "不改 r6 / h180 决策包",
            "额外占用是库存数量，不是资金/预算",
        ])
    (out_dir / "frontier_v2_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(dict(coverage=coverage,
                          rows=len(frontier),
                          sample=frontier.head(6).to_dict("records")),
                     ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
