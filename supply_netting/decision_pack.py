# -*- coding: utf-8 -*-
"""2026-10-29 广范围自发货补货决策包（人工审核用）。

输入均为已复审产物：供应净额 r5 条件情景 + 刷新预测 forecast-20261027-r2。
本模块只做「每个键都有去向」的汇总与情景对照，不预测、不下单、不写生产。

去向互斥四类：
- ``建议补货``：模型化缺口 > 0，给数量区间与缺口日期；
- ``无需补货``：已知需求被期初覆盖；
- ``不可算``：无库存基准 / 期初数量未证；
- ``待核``：有库存但无预测覆盖、或预测键未进入净额。

数量单位与 SKU/仓/UOM 绑定，任何合计都在 UOM 组内完成，禁止跨 UOM 相加。
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import load_sku_map

from . import artifacts
from .forecast import _is_true

DEST_SUGGEST = "建议补货"
DEST_NONE = "无需补货"
DEST_UNKNOWN = "不可算"
DEST_VERIFY = "待核"
DESTINATIONS = (DEST_SUGGEST, DEST_NONE, DEST_UNKNOWN, DEST_VERIFY)

DISCLAIMER = (
    "条件情景，不是采购指令。缺口基于 2026-10-26 库存快照与 2026-10-29 起的预测窗口；"
    "在途/PO 无 ETA、未履约 SO 未接入、预测只覆盖通过资格的销售键；不得当作当前全量缺口。"
)


@dataclass
class Inputs:
    run_dir: Path
    manifest: dict
    netting: pd.DataFrame
    review: pd.DataFrame
    facts: pd.DataFrame
    forecast_windows: pd.DataFrame
    forecast_meta: dict
    sku_map: pd.DataFrame
    history: pd.DataFrame
    buckets: dict[str, str]


def _sha(path) -> str:
    return artifacts.sha256_text(path)


def load_inputs(run_dir: str | Path, *, forecast_root: str | Path,
                demand_netting: str | Path, forecast_lead_days: int = 60) -> Inputs:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))
    netting = pd.read_parquet(run_dir / "supply_netting.parquet")
    review = pd.read_parquet(run_dir / "replenishment_review.parquet")
    facts = pd.read_parquet(run_dir / "supply_facts.parquet")
    for column in ("opening", "receipts", "gap", "unserved", "period_demand",
                   "conditional_receipts", "qty", "opening_lower_bound"):
        if column in netting.columns:
            netting[column] = pd.to_numeric(netting[column], errors="coerce")
    facts["qty"] = pd.to_numeric(facts["qty"], errors="coerce")

    forecast_meta = dict(manifest.get("forecast") or {})
    run_id = forecast_meta.get("run_id")
    windows_path = Path(forecast_root) / str(run_id) / "forecast_sku_warehouse_windows.parquet"
    windows = pd.read_parquet(windows_path)
    windows = windows[windows["lead_days"] == forecast_lead_days].copy()

    demand = pd.read_parquet(demand_netting)
    keep = demand["in_default_series"].fillna(False).astype(bool)
    history = demand.loc[keep, ["canonical_sku", "canonical_warehouse", "canonical_uom",
                                "demand_date", "quantity_default"]].rename(
        columns={"quantity_default": "quantity"})

    sku_map_path = Path("D:/Work/fzh-order-store/sku_map.tsv")
    return Inputs(
        run_dir=run_dir, manifest=manifest, netting=netting, review=review, facts=facts,
        forecast_windows=windows,
        forecast_meta=dict(forecast_meta, windows_path=str(windows_path),
                           windows_sha256=_sha(windows_path)),
        sku_map=load_sku_map(sku_map_path),
        history=history,
        buckets={b["bucket_id"]: b["start"] for b in manifest.get("buckets", [])},
    )


def _map_forecast_keys(windows: pd.DataFrame, sku_map: pd.DataFrame) -> pd.DataFrame:
    lookup = {str(r.tongtool_sku): r.item_codes[0]
              for r in sku_map.itertuples(index=False)
              if r.mapping_status == "mapped" and len(r.item_codes) == 1}
    frame = windows.copy()
    frame["canonical_sku"] = frame["tongtool_sku"].map(lambda s: lookup.get(str(s).strip()))
    frame["canonical_warehouse"] = frame["canonical_warehouse"].astype(str)
    frame["canonical_uom"] = frame["canonical_uom"].astype(str)
    frame = frame[frame["canonical_sku"].notna()
                  & frame["canonical_uom"].ne("unknown")
                  & frame["canonical_uom"].ne("")]
    return frame


def build_pack(inputs: Inputs) -> tuple[pd.DataFrame, dict]:
    """返回 (逐键决策表, 覆盖对账与统计)。"""
    key = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
    netting = inputs.netting[inputs.netting["scenario"] == "expected"]
    per_key = netting.groupby(key, as_index=False).agg(
        horizon_demand=("period_demand", "sum"),
        receipts=("receipts", "sum"),
        gap_today=("unserved", "last"),
        conditional_supply=("conditional_receipts", "max"),
        opening=("opening", "first"),
        opening_lower_bound=("opening_lower_bound", "first"),
        status=("status", "first"),
        unknown_reason=("unknown_reason", "first"),
    )
    first_gap = (netting[netting["gap"].fillna(0) > 0]
                 .sort_values("bucket_id")
                 .groupby(key, as_index=False)["bucket_id"].first()
                 .rename(columns={"bucket_id": "first_gap_bucket"}))
    per_key = per_key.merge(first_gap, on=key, how="left")
    per_key["gap_date"] = per_key["first_gap_bucket"].map(inputs.buckets)

    review = inputs.review[key + ["protect_demand", "protect_gap", "horizon_unserved",
                                  "needs_review"]]
    per_key = per_key.merge(review, on=key, how="left")

    # 只有库存、没有预测需求的键（r5 事实里标 outside_demand_scope）
    outside = inputs.facts[(inputs.facts["disposition_reason"] == "outside_demand_scope")
                           & (inputs.facts["source_layer"] == "inventory_snapshot")]
    stock_only = (outside.groupby(key, as_index=False)
                  .agg(opening=("qty", "sum"), rows=("qty", "size")))

    # 预测键（含未过资格）映射到 canonical 键，用于「待核」与证据列
    mapped = _map_forecast_keys(inputs.forecast_windows, inputs.sku_map)
    mapped["eligible"] = mapped["netting_eligible"].map(_is_true).astype(bool)
    ineligible = (mapped[~mapped["eligible"]].groupby(key, as_index=False)
                  .agg(ineligible_rows=("tongtool_sku", "size"),
                       block_reasons=("netting_block_reason", lambda s: ";".join(
                           sorted({str(v) for v in s if pd.notna(v) and str(v)})))))

    known_keys = set(map(tuple, per_key[key].itertuples(index=False)))
    extra = []
    for row in stock_only.itertuples(index=False):
        if (row.canonical_sku, row.canonical_warehouse, row.canonical_uom) not in known_keys:
            extra.append(dict(zip(key, (row.canonical_sku, row.canonical_warehouse,
                                        row.canonical_uom))))
    for row in ineligible.itertuples(index=False):
        if (row.canonical_sku, row.canonical_warehouse, row.canonical_uom) not in known_keys:
            extra.append(dict(zip(key, (row.canonical_sku, row.canonical_warehouse,
                                        row.canonical_uom))))
    for row in mapped[mapped["eligible"]].itertuples(index=False):
        if (row.canonical_sku, row.canonical_warehouse, row.canonical_uom) not in known_keys:
            extra.append(dict(zip(key, (row.canonical_sku, row.canonical_warehouse,
                                        row.canonical_uom))))
    extras = pd.DataFrame(extra, columns=key).drop_duplicates()
    frame = pd.concat([per_key, extras], ignore_index=True).drop_duplicates(key).reset_index(drop=True)

    frame = frame.merge(stock_only, on=key, how="left", suffixes=("", "_stock"))
    frame["opening"] = frame["opening"].where(frame["opening"].notna(), frame.get("opening_stock"))
    frame = frame.drop(columns=[c for c in ("opening_stock", "rows") if c in frame.columns])
    frame = frame.merge(ineligible, on=key, how="left")
    frame["ineligible_rows"] = frame["ineligible_rows"].fillna(0).astype(int)

    # 服务水平缓冲（历史 σ，14 天窗口；只作参考，不是覆盖率承诺）
    from .pack import service_level_scenarios
    demand_by_key = frame[frame["horizon_demand"].notna()][key + ["horizon_demand"]].rename(
        columns={"horizon_demand": "quantity"})
    buffers = service_level_scenarios(inputs.history, demand_by_key)
    if len(buffers):
        frame = frame.merge(buffers[key + ["tier", "sigma_daily", "buffer_flat95"]],
                            on=key, how="left")
    for column in ("tier", "sigma_daily", "buffer_flat95"):
        if column not in frame.columns:
            frame[column] = None
    frame["buffer_flat95"] = pd.to_numeric(frame["buffer_flat95"], errors="coerce").fillna(0.0)

    rows = [_decide(row) for row in frame.itertuples(index=False)]
    result = pd.DataFrame(rows)
    # 版本化：每行都能追到预测与净额的 run/manifest
    result["forecast_run_id"] = inputs.forecast_meta.get("run_id")
    result["forecast_window"] = (f"{inputs.forecast_meta.get('window_start')}.."
                                 f"{inputs.forecast_meta.get('window_end')}")
    result["netting_run_id"] = inputs.manifest.get("run_id")
    result["netting_as_of"] = inputs.manifest.get("as_of")
    result["basis_forecast"] = (f"forecast {inputs.forecast_meta.get('run_id')}"
                                f" lead={inputs.forecast_meta.get('lead_days')}d")
    result["basis_supply"] = f"r5 条件情景（{inputs.manifest.get('run_id')}）"
    result["data_cutoff"] = str((inputs.manifest.get("inputs", {})
                                 .get("demand_netting", {}) or {}).get("date_max") or "")
    rank = {DEST_SUGGEST: 0, DEST_VERIFY: 1, DEST_UNKNOWN: 2, DEST_NONE: 3}
    result["_rank"] = result["destination"].map(rank)
    result = (result.sort_values(["_rank", "gap_today"], ascending=[True, False])
              .drop(columns=["_rank"]).reset_index(drop=True))
    stats = _reconcile(result, inputs)
    return result, stats


def _decide(row) -> dict:
    key = dict(canonical_sku=row.canonical_sku, canonical_warehouse=row.canonical_warehouse,
               canonical_uom=row.canonical_uom)
    opening = row.opening
    gap = row.gap_today if pd.notna(row.gap_today) else 0.0
    conditional = row.conditional_supply if pd.notna(row.conditional_supply) else 0.0
    demand = row.horizon_demand if pd.notna(row.horizon_demand) else 0.0
    receipts = row.receipts if pd.notna(row.receipts) else 0.0
    buffer = row.buffer_flat95 if pd.notna(row.buffer_flat95) else 0.0

    if pd.isna(opening):
        if pd.notna(row.status) and row.status == "unknown":
            destination, reason = DEST_UNKNOWN, str(row.unknown_reason or "opening_unproven")
        elif row.ineligible_rows:
            destination, reason = DEST_VERIFY, "预测键未过资格且无库存基准"
        else:
            destination, reason = DEST_VERIFY, "无预测覆盖且无库存基准"
        qty_low = qty_high = qty_current = qty_higher = None
    elif pd.isna(row.horizon_demand):
        # 有库存但没有进入净额：没有需求证据，不能当作零需求
        destination = DEST_VERIFY
        reason = ("预测键未过资格" if row.ineligible_rows
                  else "无预测覆盖（仅有库存，缺需求证据）")
        qty_low = qty_high = qty_current = qty_higher = None
    elif gap > 0:
        destination, reason = DEST_SUGGEST, "模型化缺口 > 0"
        qty_high = float(math.ceil(gap))
        qty_low = float(max(0.0, math.ceil(gap - conditional)))
        qty_current = qty_high
        qty_higher = float(max(0.0, math.ceil(demand + buffer - opening - receipts)))
    else:
        destination, reason = DEST_NONE, "期初覆盖已知需求"
        qty_low = qty_high = qty_current = 0.0
        qty_higher = float(max(0.0, math.ceil(demand + buffer - opening - receipts)))

    if qty_current is not None and qty_higher is not None and qty_higher < qty_current:
        qty_higher = qty_current
    extra = (qty_higher - qty_current
             if qty_current is not None and qty_higher is not None else None)

    verify = []
    if destination == DEST_SUGGEST and conditional > 0:
        verify.append(f"条件供应 {conditional:g} 无 ETA，未计入；需核实")
    if row.ineligible_rows:
        verify.append(f"预测未过资格 {row.ineligible_rows} 行（{row.block_reasons or '见 forecast'}）")
    if pd.isna(opening) and row.opening_lower_bound is not None and pd.notna(row.opening_lower_bound):
        verify.append(f"已知库存下界 {row.opening_lower_bound:g}")
    needs_review = row.needs_review if isinstance(row.needs_review, str) else ""
    if needs_review:
        verify.append(needs_review)
    if destination == DEST_VERIFY and row.ineligible_rows == 0:
        verify.append("缺预测需求证据；不能当作零需求")
    gap_date = row.gap_date if isinstance(row.gap_date, str) else None

    return dict(
        **key,
        destination=destination, destination_reason=reason,
        opening=None if pd.isna(opening) else float(opening),
        opening_lower_bound=(None if row.opening_lower_bound is None
                             or pd.isna(row.opening_lower_bound) else float(row.opening_lower_bound)),
        horizon_demand=float(demand), protect_demand=_num(row.protect_demand),
        gap_today=float(gap), gap_date=gap_date,
        qty_low=qty_low, qty_high=qty_high,
        qty_current=qty_current, qty_higher=qty_higher, extra_holding=extra,
        buffer_reference=float(buffer),
        conditional_supply=float(conditional),
        service_tier=(row.tier if isinstance(row.tier, str) else None),
        status=(row.status if isinstance(row.status, str) else None),
        to_verify="；".join(verify),
        human_review="",
    )


def _num(value):
    return None if value is None or pd.isna(value) else float(value)


def _reconcile(result: pd.DataFrame, inputs: Inputs) -> dict:
    counts = result["destination"].value_counts().to_dict()
    missing = [d for d in DESTINATIONS if d not in counts]
    universe = int(len(result))
    total = int(sum(counts.get(d, 0) for d in DESTINATIONS))
    if missing:
        for name in missing:
            counts[name] = 0
    if total != universe:
        raise ValueError(f"去向对账失败：输入 {universe} 键，去向合计 {total}")
    suggest = result[result["destination"] == DEST_SUGGEST]
    no_action = result[result["destination"] == DEST_NONE]
    by_uom = (suggest.groupby("canonical_uom", as_index=False)
              .agg(suggest_keys=("canonical_sku", "size"),
                   gap_today=("gap_today", "sum"),
                   qty_current=("qty_current", "sum"),
                   qty_higher=("qty_higher", "sum"),
                   extra_holding=("extra_holding", "sum")))
    by_uom_all = (result.groupby("canonical_uom", as_index=False)
                  .agg(keys=("canonical_sku", "size")))
    by_uom = by_uom.merge(by_uom_all, on="canonical_uom", how="outer").fillna(0)
    gap_total = float(suggest["gap_today"].fillna(0).sum())
    qty_current = float(suggest["qty_current"].fillna(0).sum())
    qty_higher = float(suggest["qty_higher"].fillna(0).sum())
    scenarios = [
        dict(scenario="current_policy",
             definition="按模型化缺口补货（期初 + 已证到货 vs 预测需求）",
             suggest_qty=qty_current, residual_gap_modeled=round(max(0.0, gap_total - qty_current), 6),
             extra_holding=0.0,
             uncovered_deviation=round(qty_higher - qty_current, 6),
             note="覆盖模型化缺口，但不覆盖需求波动；条件供应未计入"),
        dict(scenario="higher_service_flat95",
             definition="缺口 + 历史 σ × 14 天参考缓冲（flat 95% 分位近似）",
             suggest_qty=qty_higher, residual_gap_modeled=round(max(0.0, gap_total - qty_higher), 6),
             extra_holding=round(qty_higher - qty_current, 6),
             uncovered_deviation=0.0,
             note="缓冲是参考量，不是覆盖率承诺；未含提前期，未证"),
    ]
    return dict(
        universe_keys=universe,
        destinations={d: int(counts.get(d, 0)) for d in DESTINATIONS},
        reconciliation_ok=total == universe,
        suggest_keys=int(len(suggest)),
        gap_today_total=round(gap_total, 6),
        suggest_qty_current=qty_current,
        suggest_qty_higher=qty_higher,
        extra_holding=round(qty_higher - qty_current, 6),
        no_action_keys=int(len(no_action)),
        no_action_buffer_topup=round(float(no_action["qty_higher"].fillna(0).sum()), 6),
        scenarios=scenarios,
        by_uom=by_uom.to_dict("records"),
        uom_note="所有合计都在 UOM 组内完成；跨 UOM 不相加",
    )


def manifest(inputs: Inputs, stats: dict, *, out_dir: Path, data_cutoff: str,
             code: dict) -> dict:
    return dict(
        schema_version="replenishment-decision-pack-v1",
        generated_at=datetime.now(timezone.utc).isoformat(),
        decision_date="2026-10-29",
        data_cutoff=data_cutoff,
        previous_report_date="2026-10-27",
        usage_scope="人工审核候选；不得直接生成采购单，也不代表供应功能验收",
        run_id=inputs.manifest.get("run_id"),
        as_of=inputs.manifest.get("as_of"),
        stock_snapshot=(inputs.manifest.get("timing") or {}).get("snapshot_date"),
        stock_vs_as_of=(inputs.manifest.get("timing") or {}),
        forecast=inputs.forecast_meta,
        netting=dict(run_id=inputs.manifest.get("run_id"),
                     manifest_sha256=_sha(inputs.run_dir / "supply_netting_manifest.json"),
                     partial=inputs.manifest.get("partial"),
                     partial_reasons=inputs.manifest.get("partial_reasons"),
                     checks=inputs.manifest.get("checks")),
        code=code,
        inputs=dict(
            supply_netting=_sha(inputs.run_dir / "supply_netting.parquet"),
            replenishment_review=_sha(inputs.run_dir / "replenishment_review.parquet"),
            supply_facts=_sha(inputs.run_dir / "supply_facts.parquet"),
            forecast_windows=inputs.forecast_meta.get("windows_sha256"),
            forecast_manifest=inputs.forecast_meta.get("manifest_sha256"),
        ),
        coverage=stats,
        limits=[DISCLAIMER,
                "历史订单全部早于 as_of，净额需求来自预测；as_of 到预测起点 2.779 天无需求数据",
                "在途/通途 PO 无逐行 ETA，r5 已证到货全桶为 0；条件供应不能直接抵缺口",
                "未履约 SO 未接入；工厂 SO 管线不在本包",
                "预测仅覆盖通过预测资格的 582 个销售键；未覆盖键不能当作零需求",
                "服务水平缓冲用历史 σ 与 14 天窗口，未含提前期，不是覆盖率承诺",
                "无库存基准键保持 unknown；待核键需人工补证据"],
        outputs={},
    )


def write_outputs(result: pd.DataFrame, stats: dict, doc: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet = out_dir / "decision_pack_2026-10-29.parquet"
    result.to_parquet(parquet, index=False, compression="zstd")
    json_path = out_dir / "decision_pack_2026-10-29.json"
    json_path.write_text(json.dumps(result.to_dict("records"), ensure_ascii=False, default=str),
                         encoding="utf-8")
    xlsx = out_dir / "decision_pack_2026-10-29.xlsx"
    _workbook(result, stats, doc, xlsx)
    doc["outputs"] = dict(parquet=str(parquet), json=str(json_path), xlsx=str(xlsx))
    for name, path in list(doc["outputs"].items()):
        doc["outputs"][name + "_sha256"] = _sha(path)
    manifest_path = out_dir / "decision_pack_manifest.json"
    manifest_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
    doc["outputs"]["manifest"] = str(manifest_path)
    return doc["outputs"]


def _workbook(result: pd.DataFrame, stats: dict, doc: dict, path: Path) -> None:
    dest = pd.DataFrame([{"去向": k, "键数": v} for k, v in stats["destinations"].items()])
    dest.loc[len(dest)] = {"去向": "合计（对账）", "键数": stats["universe_keys"]}
    scenario = result[result["destination"] == DEST_SUGGEST][
        ["canonical_sku", "canonical_warehouse", "canonical_uom", "gap_today", "qty_current",
         "qty_higher", "extra_holding", "buffer_reference", "gap_date"]].copy()
    scenario["说明"] = ("qty_current=覆盖模型化缺口；qty_higher=按历史波动加 14 天参考缓冲；"
                        "extra_holding 是两者差额，属参考占用，不是承诺")
    scenario = pd.concat([pd.DataFrame(stats["scenarios"]).assign(说明=lambda d: d["note"])
                          .drop(columns=["note"]), scenario], ignore_index=True)
    uom = pd.DataFrame(stats["by_uom"])
    limits = pd.DataFrame({"限制": doc["limits"]})
    manifest_rows = pd.DataFrame([{"key": k, "value": json.dumps(v, ensure_ascii=False, default=str)
                                   if isinstance(v, (dict, list)) else v}
                                  for k, v in doc.items() if k != "outputs"])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _sheet(writer, result, "决策清单")
        _sheet(writer, dest, "去向对账")
        _sheet(writer, scenario, "情景对照")
        _sheet(writer, uom, "UOM 分组")
        _sheet(writer, limits, "数据与限制")
        _sheet(writer, manifest_rows, "Manifest")


def _sheet(writer, frame: pd.DataFrame, name: str) -> None:
    frame.to_excel(writer, sheet_name=name, index=False)
    sheet = writer.sheets[name]
    for index, column in enumerate(frame.columns, start=1):
        width = max(10, min(42, max([len(str(column))] + [len(str(v)) for v in frame[column].head(200)]) + 2))
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    sheet.freeze_panes = "A2"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="2026-10-29 广范围补货决策包")
    parser.add_argument("--run", required=True, help="r5 净额 run 目录")
    parser.add_argument("--forecast-root",
                        default="D:/Work/fzh-order-store/en-demand-v1/forecast")
    parser.add_argument("--demand", required=True, help="demand_netting.parquet（算历史波动）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    inputs = load_inputs(args.run, forecast_root=args.forecast_root, demand_netting=args.demand)
    result, stats = build_pack(inputs)
    from .__main__ import _git_meta
    doc = manifest(inputs, stats, out_dir=Path(args.out),
                   data_cutoff=str((inputs.manifest.get("inputs", {})
                                    .get("demand_netting", {}) or {}).get("date_max") or ""),
                   code=_git_meta())
    outputs = write_outputs(result, stats, doc, Path(args.out))
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("输出：", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
