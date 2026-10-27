# -*- coding: utf-8 -*-
"""2026-10-29 广范围自发货补货决策包（人工审核用）。

输入均为已复审产物：供应净额 r5 条件情景 + 刷新预测 forecast-20261027-r2。
本模块只做「每个键都有去向」的汇总与情景对照，不预测、不下单、不写生产。

去向互斥四类：``建议补货`` / ``无需补货`` / ``不可算`` / ``待核``。

数量语义三态（``value_status``）：
- ``measured``：来自 r5 净额，数值可证（0 就是真实的 0）；
- ``unknown``：无库存基准，所有数量字段为 null；
- ``not_covered``：缺预测需求证据，需求/缺口为 null，不能当作零需求。

所有数量汇总与 ABC 分级都按 UOM 分组；多 UOM 时不输出无单位标量。
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from self_fulfilled_demand.canonical import load_sku_map

from . import artifacts
from .forecast import _is_true

DEST_SUGGEST = "建议补货"
DEST_NONE = "无需补货"
DEST_UNKNOWN = "不可算"
DEST_VERIFY = "待核"
DESTINATIONS = (DEST_SUGGEST, DEST_NONE, DEST_UNKNOWN, DEST_VERIFY)

GAP_TODAY_NOTE = "净额视界末（netting_horizon_end）的累计未满足量，不是某一天的缺口"
EVIDENCE_KNOWN = "known"
EVIDENCE_UNKNOWN = "unknown"
EVIDENCE_NOT_COVERED = "not_covered"

VALUE_MEASURED = "measured"
VALUE_MEASURED_ZERO = "measured_zero"
VALUE_UNKNOWN = "unknown"
VALUE_NOT_COVERED = "not_covered"

DISCLAIMER = (
    "条件情景，不是采购指令。缺口基于 2026-10-26 库存快照与 2026-10-29 起的预测窗口；"
    "在途/PO 无 ETA、未履约 SO 未接入、预测只覆盖通过资格的销售键；不得当作当前全量缺口。"
)
GAP_DATE_NOTE = "桶边界（首个含缺口桶的起点），不是精确缺货日；精确到日需桶内时序证据"
COUNTERFACTUAL_NOTE = (
    "反事实量：假设无 ETA 的条件供应在缺口前全部可用时的补货下限；"
    "在逐行 ETA/资格证据补齐前不可采用"
)

DEFAULT_SKU_MAP = "D:/Work/fzh-order-store/sku_map.tsv"
KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


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
    buckets: dict[str, dict]
    sources: dict


def _sha(path) -> str:
    return artifacts.sha256_text(path)


def _verify_r5_outputs(run_dir: Path, manifest: dict) -> dict:
    """F5：消费前核验 r5 产物与它自己声明的哈希一致。"""
    declared = manifest.get("outputs") or {}
    result = {}
    for name in ("supply_netting", "replenishment_review", "supply_facts"):
        path = run_dir / f"{name}.parquet"
        actual = _sha(path)
        expected = str(declared.get(f"{name}_sha256") or "").lower()
        if not expected:
            raise ValueError(f"r5 manifest 未声明 {name} 的 sha256，拒绝消费")
        if actual != expected:
            raise ValueError(f"r5 产物哈希不符：{name} 实测 {actual}，声明 {expected}")
        result[name] = dict(path=str(path), sha256=actual, verified=True)
    return result


def load_inputs(run_dir: str | Path, *, forecast_root: str | Path,
                demand_netting: str | Path, forecast_lead_days: int = 60,
                sku_map_path: str | Path = DEFAULT_SKU_MAP) -> Inputs:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))
    r5_sources = _verify_r5_outputs(run_dir, manifest)
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
    run_path = Path(forecast_root) / str(run_id)
    windows_path = run_path / "forecast_sku_warehouse_windows.parquet"
    manifest_path = run_path / "forecast_manifest.json"
    windows_sha = _sha(windows_path)
    manifest_sha = _sha(manifest_path)
    # F5：与 r5 冻结时记录的预测哈希比对；不一致直接拒绝，避免静默换输入。
    for label, actual in (("windows", windows_sha), ("manifest", manifest_sha)):
        expected = str(forecast_meta.get(f"{label}_sha256") or "").lower()
        if expected and actual != expected:
            raise ValueError(f"预测 {label} 与 r5 冻结值不符：实测 {actual}，r5 记录 {expected}")
    forecast_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    forecast_meta.setdefault("code_git_head", (forecast_doc.get("code") or {}).get("git_head"))
    forecast_meta.update(windows_path=str(windows_path), manifest_path=str(manifest_path),
                         windows_sha256=windows_sha, manifest_sha256=manifest_sha,
                         windows_verified=bool(forecast_meta.get("windows_sha256")),
                         manifest_verified=bool(forecast_meta.get("manifest_sha256")))

    windows_all = pd.read_parquet(windows_path)
    windows_all = windows_all[windows_all["lead_days"] == forecast_lead_days].copy()

    demand_path = Path(demand_netting)
    demand = pd.read_parquet(demand_path)
    keep = demand["in_default_series"].fillna(False).astype(bool)
    history = demand.loc[keep, ["canonical_sku", "canonical_warehouse", "canonical_uom",
                                "demand_date", "quantity_default"]].rename(
        columns={"quantity_default": "quantity"})
    history_meta = dict(path=str(demand_path), sha256=_sha(demand_path),
                        rows=int(len(history)), default_rows=int(len(history)))
    declared_history = str(((manifest.get("inputs") or {}).get("demand_netting") or {})
                           .get("sha256") or "").lower()
    history_meta["matches_r5"] = bool(declared_history) and declared_history == history_meta["sha256"]
    if declared_history and not history_meta["matches_r5"]:
        raise ValueError(
            f"历史需求与 r5 冻结哈希不符：实测 {history_meta['sha256']}，r5 记录 {declared_history}")
    history_meta["verified"] = history_meta["matches_r5"]

    sku_path = Path(sku_map_path)
    sku_meta = dict(path=str(sku_path), sha256=_sha(sku_path))

    bucket_ends = {b["bucket_id"]: b["end"] for b in manifest.get("buckets", [])}
    buckets = {b["bucket_id"]: {
        "start": b["start"], "end": b.get("end"),
        "granularity": GAP_DATE_NOTE,
    } for b in manifest.get("buckets", [])}
    horizon_end = max(bucket_ends.values()) if bucket_ends else None

    return Inputs(
        run_dir=run_dir, manifest=manifest, netting=netting, review=review, facts=facts,
        forecast_windows=windows_all,
        forecast_meta=forecast_meta,
        sku_map=load_sku_map(sku_path),
        history=history,
        buckets=buckets,
        sources=dict(r5=r5_sources, forecast=forecast_meta,
                     history=history_meta, sku_map=sku_meta,
                     forecast_rows_in=int(len(windows_all)),
                     horizon_end=horizon_end),
    )


def _map_forecast_keys(windows: pd.DataFrame, sku_map: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """F4：返回 (可规范化行, 被排除行明细)，排除原因逐行保留。"""
    lookup = {str(r.tongtool_sku): r.item_codes[0]
              for r in sku_map.itertuples(index=False)
              if r.mapping_status == "mapped" and len(r.item_codes) == 1}
    frame = windows.copy()
    frame["canonical_sku"] = frame["tongtool_sku"].map(lambda s: lookup.get(str(s).strip()))
    frame["canonical_warehouse"] = frame["canonical_warehouse"].astype(str)
    frame["canonical_uom"] = frame["canonical_uom"].astype(str)

    excluded = []
    for row in frame.itertuples(index=False):
        reason = None
        if pd.isna(row.canonical_sku):
            reason = "sku_mapping_missing_or_ambiguous"
        elif row.canonical_uom in ("", "unknown", "nan"):
            reason = "uom_missing"
        if reason:
            excluded.append(dict(raw_sku=str(row.tongtool_sku),
                                 raw_warehouse=str(row.canonical_warehouse),
                                 raw_uom=str(row.canonical_uom), reason=reason,
                                 raw_block_reason=str(getattr(row, "netting_block_reason", "") or "")))
    keep = frame[frame["canonical_sku"].notna()
                 & ~frame["canonical_uom"].isin(["", "unknown", "nan"])]
    return keep, excluded


def _per_uom_buffers(history: pd.DataFrame, demand_by_key: pd.DataFrame) -> pd.DataFrame:
    """F3：ABC 与缓冲都在 UOM 组内计算，禁止跨 UOM 排序。"""
    from .pack import FLAT_SL, HISTORY_DAYS, SCENARIO_WINDOW_DAYS, _z

    if demand_by_key.empty:
        return pd.DataFrame(columns=KEY + ["tier", "sigma_daily", "buffer_flat95"])
    frame = demand_by_key.copy()
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce").fillna(0.0)
    tiers = []
    for uom, group in frame.groupby("canonical_uom", sort=False):
        group = group.sort_values("quantity", ascending=False).copy()
        total = float(group["quantity"].sum())
        if total > 0:
            group["cum_share"] = group["quantity"].cumsum() / total
            # 用「加本行之前的累计占比」分档：组内第一名永远是 A
            before = group["cum_share"] - group["quantity"] / total
            group["tier"] = np.where(before < 0.80, "A",
                                     np.where(before < 0.95, "B", "C"))
        else:
            group["tier"] = "A"
        tiers.append(group[KEY + ["tier"]])
    scored = pd.concat(tiers, ignore_index=True)

    stats = pd.DataFrame(columns=KEY + ["sigma_daily"])
    if len(history):
        hist = history.copy()
        hist["demand_date"] = pd.to_datetime(hist["demand_date"])
        cutoff = hist["demand_date"].max() - pd.Timedelta(days=HISTORY_DAYS)
        hist = hist[hist["demand_date"] >= cutoff]
        stats = (hist.groupby(KEY)["quantity"].agg(sigma_daily="std").reset_index())
    merged = scored.merge(stats, on=KEY, how="left")
    merged["sigma_daily"] = pd.to_numeric(merged["sigma_daily"], errors="coerce").fillna(0.0)
    merged["buffer_flat95"] = _z(FLAT_SL) * merged["sigma_daily"] * math.sqrt(SCENARIO_WINDOW_DAYS)
    return merged


def build_pack(inputs: Inputs) -> tuple[pd.DataFrame, dict]:
    """返回 (逐键决策表, 覆盖对账与统计)。"""
    netting = inputs.netting[inputs.netting["scenario"] == "expected"]
    per_key = netting.groupby(KEY, as_index=False).agg(
        horizon_demand=("period_demand", "sum"),
        receipts=("receipts", "sum"),
        gap_today=("unserved", "last"),
        conditional_supply=("conditional_receipts", "max"),
        opening=("opening", "first"),
        opening_lower_bound=("opening_lower_bound", "first"),
        status=("status", "first"),
        unknown_reason=("unknown_reason", "first"),
    )
    per_key["key_source"] = "netting"
    first_gap = (netting[netting["gap"].fillna(0) > 0]
                 .sort_values("bucket_id")
                 .groupby(KEY, as_index=False)["bucket_id"].first()
                 .rename(columns={"bucket_id": "first_gap_bucket"}))
    per_key = per_key.merge(first_gap, on=KEY, how="left")
    per_key["first_gap_bucket_start"] = per_key["first_gap_bucket"].map(
        lambda b: (inputs.buckets.get(b) or {}).get("start"))
    per_key["first_gap_bucket_end"] = per_key["first_gap_bucket"].map(
        lambda b: (inputs.buckets.get(b) or {}).get("end"))

    review = inputs.review[KEY + ["protect_demand", "protect_gap", "horizon_unserved",
                                  "needs_review"]]
    per_key = per_key.merge(review, on=KEY, how="left")

    outside = inputs.facts[(inputs.facts["disposition_reason"] == "outside_demand_scope")
                           & (inputs.facts["source_layer"] == "inventory_snapshot")]
    stock_only = (outside.groupby(KEY, as_index=False)
                  .agg(opening=("qty", "sum"), rows=("qty", "size")))
    stock_only["key_source"] = "stock_only"

    mapped, forecast_excluded = _map_forecast_keys(inputs.forecast_windows, inputs.sku_map)
    mapped["eligible"] = mapped["netting_eligible"].map(_is_true).astype(bool)
    ineligible = (mapped[~mapped["eligible"]].groupby(KEY, as_index=False)
                  .agg(ineligible_rows=("tongtool_sku", "size"),
                       block_reasons=("netting_block_reason", lambda s: ";".join(
                           sorted({str(v) for v in s if pd.notna(v) and str(v)})))))
    forecast_keys = mapped[KEY].drop_duplicates()
    forecast_keys["key_source"] = "forecast_only"

    known_keys = set(map(tuple, per_key[KEY].itertuples(index=False)))
    extra = []
    for table in (stock_only[KEY + ["key_source"]], ineligible[KEY].assign(key_source="forecast_only"),
                  forecast_keys):
        for row in table.itertuples(index=False):
            if (row.canonical_sku, row.canonical_warehouse, row.canonical_uom) not in known_keys:
                extra.append(dict(canonical_sku=row.canonical_sku,
                                  canonical_warehouse=row.canonical_warehouse,
                                  canonical_uom=row.canonical_uom,
                                  key_source=row.key_source))
    extras = pd.DataFrame(extra, columns=KEY + ["key_source"]).drop_duplicates(KEY)

    # 规范化输入键集合：独立于输出，供对账使用
    input_keys = (pd.concat([per_key[KEY + ["key_source"]], extras[KEY + ["key_source"]]],
                            ignore_index=True)
                  .drop_duplicates(KEY).reset_index(drop=True))

    frame = (pd.concat([per_key, extras], ignore_index=True)
             .drop_duplicates(KEY).reset_index(drop=True))
    frame = frame.drop(columns=[c for c in ("key_source",) if c in frame.columns], errors="ignore")
    frame = frame.merge(stock_only[KEY + ["opening", "rows"]], on=KEY, how="left",
                        suffixes=("", "_stock"))
    frame["opening"] = frame["opening"].where(frame["opening"].notna(), frame.get("opening_stock"))
    frame = frame.drop(columns=[c for c in ("opening_stock", "rows") if c in frame.columns])
    frame = frame.merge(ineligible, on=KEY, how="left")
    frame["ineligible_rows"] = frame["ineligible_rows"].fillna(0).astype(int)
    frame = frame.merge(input_keys, on=KEY, how="left")

    demand_by_key = frame[frame["horizon_demand"].notna()][KEY + ["horizon_demand"]].rename(
        columns={"horizon_demand": "quantity"})
    buffers = _per_uom_buffers(inputs.history, demand_by_key)
    frame = frame.merge(buffers, on=KEY, how="left")
    for column in ("tier", "sigma_daily", "buffer_flat95"):
        if column not in frame.columns:
            frame[column] = None
    frame["buffer_flat95"] = pd.to_numeric(frame["buffer_flat95"], errors="coerce").fillna(0.0)

    rows = [_decide(row) for row in frame.itertuples(index=False)]
    result = pd.DataFrame(rows)
    result["forecast_run_id"] = inputs.forecast_meta.get("run_id")
    result["forecast_window"] = (f"{inputs.forecast_meta.get('window_start')}.."
                                 f"{inputs.forecast_meta.get('window_end')}")
    result["netting_run_id"] = inputs.manifest.get("run_id")
    result["netting_as_of"] = inputs.manifest.get("as_of")
    result["netting_horizon_end"] = inputs.sources.get("horizon_end")
    result["basis_forecast"] = (f"forecast {inputs.forecast_meta.get('run_id')}"
                                f" lead={inputs.forecast_meta.get('lead_days')}d")
    result["basis_supply"] = f"r5 条件情景（{inputs.manifest.get('run_id')}）"
    result["data_cutoff"] = str((inputs.manifest.get("inputs", {})
                                 .get("demand_netting", {}) or {}).get("date_max") or "")
    result["bucket_granularity"] = GAP_DATE_NOTE

    rank = {DEST_SUGGEST: 0, DEST_VERIFY: 1, DEST_UNKNOWN: 2, DEST_NONE: 3}
    result["_rank"] = result["destination"].map(rank)
    result = (result.sort_values(["_rank", "gap_today"], ascending=[True, False],
                                 na_position="last")
              .drop(columns=["_rank"]).reset_index(drop=True))

    stats = _reconcile(result, input_keys, inputs, forecast_excluded)
    return result, stats


def _decide(row) -> dict:
    key = dict(canonical_sku=row.canonical_sku, canonical_warehouse=row.canonical_warehouse,
               canonical_uom=row.canonical_uom)
    opening = row.opening
    measured = row.key_source == "netting"
    conditional = row.conditional_supply if pd.notna(row.conditional_supply) else 0.0
    buffer = row.buffer_flat95 if pd.notna(row.buffer_flat95) else 0.0

    if measured and pd.isna(opening):
        measured = False        # r5 行但期初未知 → 不可算
    if measured and (pd.notna(row.status) and row.status == "unknown"):
        measured = False

    if not measured and (pd.notna(row.status) and row.status == "unknown"):
        value_status = VALUE_UNKNOWN
        demand_evidence = gap_evidence = EVIDENCE_UNKNOWN
        destination = DEST_UNKNOWN
        reason = str(row.unknown_reason) if pd.notna(row.unknown_reason) else "opening_unproven"
        numbers = dict(horizon_demand=None, protect_demand=None, protect_gap=None,
                       gap_today=None, qty_high=None, qty_low_counterfactual=None,
                       qty_current=None, qty_higher=None, extra_holding=None)
    elif not measured:
        value_status = VALUE_NOT_COVERED
        demand_evidence = gap_evidence = EVIDENCE_NOT_COVERED
        destination = DEST_VERIFY
        reason = ("预测键未过资格且无库存基准" if (row.ineligible_rows and pd.isna(opening))
                  else "预测键未过资格" if row.ineligible_rows
                  else "无预测覆盖（仅有库存，缺需求证据）")
        numbers = dict(horizon_demand=None, protect_demand=None, protect_gap=None,
                       gap_today=None, qty_high=None, qty_low_counterfactual=None,
                       qty_current=None, qty_higher=None, extra_holding=None)
    else:
        demand_evidence = gap_evidence = EVIDENCE_KNOWN
        demand = float(row.horizon_demand)
        receipts = float(row.receipts) if pd.notna(row.receipts) else 0.0
        unserved = float(row.gap_today) if pd.notna(row.gap_today) else 0.0
        if unserved > 0:
            destination, reason = DEST_SUGGEST, "模型化缺口 > 0"
            qty_high = float(math.ceil(unserved))
            qty_low_counterfactual = float(max(0.0, math.ceil(unserved - conditional)))
            qty_current = qty_high
            qty_higher = float(max(0.0, math.ceil(demand + buffer - float(opening) - receipts)))
        else:
            destination, reason = DEST_NONE, "期初覆盖已知需求"
            qty_high = qty_current = qty_low_counterfactual = 0.0
            qty_higher = float(max(0.0, math.ceil(demand + buffer - float(opening) - receipts)))
        qty_higher = max(qty_higher, qty_current)
        value_status = VALUE_MEASURED_ZERO if (demand == 0 and unserved == 0) else VALUE_MEASURED
        numbers = dict(horizon_demand=demand, protect_demand=_num(row.protect_demand),
                       protect_gap=_num(row.protect_gap),
                       gap_today=unserved, qty_high=qty_high,
                       qty_low_counterfactual=qty_low_counterfactual, qty_current=qty_current,
                       qty_higher=qty_higher, extra_holding=qty_higher - qty_current)

    verify = []
    if destination == DEST_SUGGEST and conditional > 0:
        verify.append(f"条件供应 {conditional:g} 无 ETA，未计入；qty_low_counterfactual 仅为反事实下限")
    if row.ineligible_rows:
        verify.append(f"预测未过资格 {row.ineligible_rows} 行（{row.block_reasons or '见 forecast'}）")
    if pd.isna(opening) and pd.notna(row.opening_lower_bound):
        verify.append(f"已知库存下界 {row.opening_lower_bound:g}")
    needs_review = row.needs_review if isinstance(row.needs_review, str) else ""
    if needs_review:
        verify.append(needs_review)
    if destination == DEST_VERIFY and row.ineligible_rows == 0:
        verify.append("缺预测需求证据；不能当作零需求")
    if destination == DEST_UNKNOWN:
        verify.append("无库存基准：数量字段保持 null，不得按 0 处理")

    return dict(
        **key,
        destination=destination, destination_reason=reason, value_status=value_status,
        demand_evidence_status=demand_evidence, gap_evidence_status=gap_evidence,
        gap_today_note=GAP_TODAY_NOTE,
        key_source=(row.key_source if isinstance(row.key_source, str) else None),
        opening=None if pd.isna(opening) else float(opening),
        opening_lower_bound=_num(row.opening_lower_bound),
        **numbers,
        first_gap_bucket_start=(row.first_gap_bucket_start
                                if isinstance(row.first_gap_bucket_start, str) else None),
        first_gap_bucket_end=(row.first_gap_bucket_end
                              if isinstance(row.first_gap_bucket_end, str) else None),
        buffer_reference=float(buffer),
        conditional_supply=float(conditional) if measured else None,
        service_tier=(row.tier if isinstance(row.tier, str) else None),
        status=(row.status if isinstance(row.status, str) else None),
        to_verify="；".join(verify),
        human_review="",
        qty_low_semantics=(COUNTERFACTUAL_NOTE
                           if destination == DEST_SUGGEST else None),
    )


def _num(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(value)


def _key_set(frame: pd.DataFrame) -> set:
    return set(map(tuple, frame[KEY].itertuples(index=False)))


def _reconcile(result: pd.DataFrame, input_keys: pd.DataFrame, inputs: Inputs,
               forecast_excluded: list[dict]) -> dict:
    """F4：用独立重建的输入键集合与输出比对，不以输出自身为预言机。"""
    source_keys = _key_set(input_keys)
    output_keys = _key_set(result)
    duplicates = int(input_keys.duplicated(KEY).sum())
    missing = sorted(source_keys - output_keys)
    unexpected = sorted(output_keys - source_keys)

    counts = result["destination"].value_counts().to_dict()
    destinations = {d: int(counts.get(d, 0)) for d in DESTINATIONS}
    reconciled = (not missing and not unexpected and duplicates == 0
                  and sum(destinations.values()) == len(source_keys) == len(result))
    if not reconciled:
        raise ValueError(
            f"决策包对账失败：输入 {len(source_keys)} 键 / 输出 {len(result)} 键；"
            f"缺 {len(missing)}、多 {len(unexpected)}、输入重复 {duplicates}")

    suggest = result[result["destination"] == DEST_SUGGEST]
    per_uom = []
    for uom, group in suggest.groupby("canonical_uom", sort=True):
        per_uom.append(dict(
            uom=uom,
            suggest_keys=int(len(group)),
            gap_today=round(float(group["gap_today"].sum()), 6),
            protect_gap=round(float(group["protect_gap"].fillna(0).sum()), 6),
            qty_current=float(group["qty_current"].fillna(0).sum()),
            qty_higher=float(group["qty_higher"].fillna(0).sum()),
            extra_holding=float(group["extra_holding"].fillna(0).sum()),
            qty_low_counterfactual=float(group["qty_low_counterfactual"].fillna(0).sum()),
        ))
    by_uom = (result.groupby(["canonical_uom", "destination"], as_index=False)
              .agg(keys=("canonical_sku", "size")))
    pivot = (by_uom.pivot(index="canonical_uom", columns="destination", values="keys")
             .fillna(0).astype(int).reset_index())
    for name in DESTINATIONS:
        if name not in pivot.columns:
            pivot[name] = 0

    # 无单位的全局标量只在「单一 UOM 的建议集合」下给出，否则 None。
    single = len(per_uom) == 1
    totals = per_uom[0] if single else {}
    scenarios = [
        dict(scenario="current_policy", uom=(totals.get("uom") if single else None),
             definition="按模型化缺口补货（期初 + 已证到货 vs 预测需求）",
             suggest_qty=totals.get("qty_current") if single else None,
             uncovered_deviation=totals.get("extra_holding") if single else None,
             note="覆盖模型化缺口，但不覆盖需求波动；条件供应未计入"),
        dict(scenario="higher_service_flat95", uom=(totals.get("uom") if single else None),
             definition="缺口 + 历史 σ × 14 天参考缓冲（flat 95% 分位近似）",
             suggest_qty=totals.get("qty_higher") if single else None,
             extra_holding=totals.get("extra_holding") if single else None,
             uncovered_deviation=0.0,
             note="缓冲是参考量，不是覆盖率承诺；未含提前期，未证"),
    ]

    excluded_counts = {}
    for row in forecast_excluded:
        excluded_counts[row["reason"]] = excluded_counts.get(row["reason"], 0) + 1

    return dict(
        universe_keys=len(source_keys),
        destinations=destinations,
        reconciliation_ok=True,
        missing_keys=len(missing), unexpected_keys=len(unexpected),
        input_duplicates=duplicates,
        suggest_keys=int(len(suggest)),
        value_status=result["value_status"].value_counts().to_dict(),
        scenarios=scenarios,
        scenarios_by_uom=per_uom,
        single_uom=(totals.get("uom") if single else None),
        scalar_note=("单 UOM，标量带单位" if single
                     else "多 UOM：不输出无单位标量，请按 scenarios_by_uom 使用"),
        by_uom=pivot.to_dict("records"),
        source_ledger=dict(
            forecast_rows_in=inputs.sources.get("forecast_rows_in"),
            forecast_rows_normalized=int(len(inputs.forecast_windows)) - len(forecast_excluded),
            forecast_rows_excluded=len(forecast_excluded),
            forecast_excluded_reasons=excluded_counts,
            forecast_excluded_rows=forecast_excluded,
            r5_keys=int(len(inputs.review)),
            stock_only_keys=int(len(inputs.facts[
                (inputs.facts["disposition_reason"] == "outside_demand_scope")
                & (inputs.facts["source_layer"] == "inventory_snapshot")][KEY].drop_duplicates())),
            note="预测源行 4,518 = 规范化行 + 排除行；排除行在原始预测中保留，不冒充 canonical 键",
        ),
        uom_note="所有数量汇总与 ABC 分级都在 UOM 组内完成；跨 UOM 不相加",
    )


def manifest(inputs: Inputs, stats: dict, *, out_dir: Path, data_cutoff: str,
             code: dict, supersedes: str | None = None, fixes: list | None = None,
             test_count: int | None = None) -> dict:
    supersedes_info = None
    if supersedes:
        previous = Path(supersedes)
        supersedes_info = dict(path=str(previous),
                               manifest_sha256=_sha(previous / "decision_pack_manifest.json"),
                               note="原包保留不覆盖；本包为 F1–F7 修复版")
    fix_list = fixes or ["F1 null 语义", "F2 严格 JSON", "F3 按 UOM 汇总",
                         "F4 独立输入集合对账与 255 行明细", "F5 直接输入哈希锁定",
                         "F6 qty_low_counterfactual 反事实标注", "F7 桶起点字段"]
    return dict(
        schema_version="replenishment-decision-pack-v1",
        generated_at=datetime.now(timezone.utc).isoformat(),
        decision_date="2026-10-29",
        data_cutoff=data_cutoff,
        previous_report_date="2026-10-27",
        usage_scope="人工审核候选；不得直接生成采购单，也不代表供应功能验收",
        supersedes=supersedes_info,
        run_id=inputs.manifest.get("run_id"),
        as_of=inputs.manifest.get("as_of"),
        stock_snapshot=(inputs.manifest.get("timing") or {}).get("snapshot_date"),
        stock_vs_as_of=(inputs.manifest.get("timing") or {}),
        netting_horizon_end=inputs.sources.get("horizon_end"),
        forecast_window=[inputs.forecast_meta.get("window_start"),
                         inputs.forecast_meta.get("window_end")],
        gap_from_as_of_days=inputs.forecast_meta.get("gap_from_as_of_days"),
        forecast=inputs.forecast_meta,
        forecast_generated_by=((inputs.forecast_meta.get("code_git_head")) or None),
        reviewed_commit="6a7d56bd",
        forecast_note=("forecast_generated_by 是上游 manifest 记录的生成代码；"
                       "reviewed_commit 是独立复审的提交，二者不混称"),
        netting=dict(run_id=inputs.manifest.get("run_id"),
                     manifest_sha256=_sha(inputs.run_dir / "supply_netting_manifest.json"),
                     partial=inputs.manifest.get("partial"),
                     partial_reasons=inputs.manifest.get("partial_reasons"),
                     checks=inputs.manifest.get("checks")),
        code=code,
        sources=inputs.sources,
        verification=dict(
            r5_outputs_match_manifest=True,
            forecast_windows_match_r5=inputs.forecast_meta.get("windows_verified"),
            forecast_manifest_match_r5=inputs.forecast_meta.get("manifest_verified"),
            history_matches_r5=inputs.sources["history"].get("matches_r5"),
            sku_map_recorded=True,
        ),
        inputs=dict(
            supply_netting=inputs.sources["r5"]["supply_netting"]["sha256"],
            replenishment_review=inputs.sources["r5"]["replenishment_review"]["sha256"],
            supply_facts=inputs.sources["r5"]["supply_facts"]["sha256"],
            forecast_windows=inputs.forecast_meta.get("windows_sha256"),
            forecast_manifest=inputs.forecast_meta.get("manifest_sha256"),
            demand_netting=inputs.sources["history"]["sha256"],
            sku_map=inputs.sources["sku_map"]["sha256"],
        ),
        coverage=stats,
        fixes=fix_list,
        test_count=test_count,
        limits=[DISCLAIMER,
                "历史订单全部早于 as_of，净额需求来自预测；as_of 到预测起点 2.779 天无需求数据",
                "在途/通途 PO 无逐行 ETA，r5 已证到货全桶为 0；条件供应不能直接抵缺口",
                "qty_low_counterfactual 假定条件供应在缺口前可用，属反事实量，未获 ETA/资格证据前不可采用",
                "未履约 SO 未接入；工厂 SO 管线不在本包",
                "预测仅覆盖通过预测资格的 582 个销售输入行；未覆盖键不能当作零需求",
                "服务水平缓冲用历史 σ 与 14 天窗口，按 UOM 分组，未含提前期，不是覆盖率承诺",
                "无库存基准键保持 unknown（数量 null）；待核键需求/缺口为 null",
                "缺口日期是桶边界，不是精确缺货日",
                "净额视界止于 netting_horizon_end，未覆盖预测窗口剩余部分"],
        outputs={},
    )


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.floating,)):
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _strict_json(payload) -> str:
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if "NaN" in text or "Infinity" in text:
        raise ValueError("JSON 中仍含 NaN/Infinity")


    def _reject(token):
        raise ValueError(f"严格 JSON 校验失败：{token}")

    json.loads(text, parse_constant=_reject)
    return text


def write_outputs(result: pd.DataFrame, stats: dict, doc: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet = out_dir / "decision_pack_2026-10-29.parquet"
    result.to_parquet(parquet, index=False, compression="zstd")

    records = [{k: _json_safe(v) for k, v in record.items()}
               for record in result.to_dict("records")]
    json_path = out_dir / "decision_pack_2026-10-29.json"
    json_path.write_text(_strict_json(records), encoding="utf-8")

    excluded_rows = stats["source_ledger"].get("forecast_excluded_rows") or []
    excluded_path = out_dir / "forecast_source_excluded.csv"
    pd.DataFrame(excluded_rows,
                 columns=["raw_sku", "raw_warehouse", "raw_uom", "reason", "raw_block_reason"]
                 ).to_csv(excluded_path, index=False, encoding="utf-8-sig")

    xlsx = out_dir / "decision_pack_2026-10-29.xlsx"
    _workbook(result, stats, doc, xlsx, excluded_rows)
    doc["outputs"] = dict(parquet=str(parquet), json=str(json_path), xlsx=str(xlsx),
                          forecast_source_excluded=str(excluded_path))
    for name, path in list(doc["outputs"].items()):
        doc["outputs"][name + "_sha256"] = _sha(path)
    manifest_path = out_dir / "decision_pack_manifest.json"
    manifest_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str,
                                        allow_nan=False), encoding="utf-8")
    doc["outputs"]["manifest"] = str(manifest_path)
    return doc["outputs"]


def _workbook(result: pd.DataFrame, stats: dict, doc: dict, path: Path,
              excluded_rows=None) -> None:
    dest = pd.DataFrame([{"去向": k, "键数": v} for k, v in stats["destinations"].items()])
    dest.loc[len(dest)] = {"去向": "合计（独立对账）", "键数": stats["universe_keys"]}
    ledger = pd.DataFrame([{
        "项目": "预测源行", "值": stats["source_ledger"]["forecast_rows_in"]},
        {"项目": "可规范化行", "值": stats["source_ledger"]["forecast_rows_normalized"]},
        {"项目": "排除行", "值": stats["source_ledger"]["forecast_rows_excluded"]},
        {"项目": "排除原因", "值": json.dumps(stats["source_ledger"]["forecast_excluded_reasons"],
                                         ensure_ascii=False)},
        {"项目": "r5 净额键", "值": stats["source_ledger"]["r5_keys"]},
        {"项目": "仅库存键", "值": stats["source_ledger"]["stock_only_keys"]},
        {"项目": "缺键 / 多键 / 输入重复", "值": f"{stats['missing_keys']} / "
                                              f"{stats['unexpected_keys']} / {stats['input_duplicates']}"},
    ])
    scenario = pd.DataFrame(stats["scenarios_by_uom"])
    limits = pd.DataFrame({"限制": doc["limits"]})
    manifest_rows = pd.DataFrame([{"key": k, "value": json.dumps(v, ensure_ascii=False, default=str)
                                   if isinstance(v, (dict, list)) else v}
                                  for k, v in doc.items() if k != "outputs"])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _sheet(writer, result, "决策清单")
        _sheet(writer, dest, "去向对账")
        _sheet(writer, ledger, "源行对账")
        _sheet(writer, scenario, "情景对照")
        _sheet(writer, limits, "数据与限制")
        _sheet(writer, pd.DataFrame(excluded_rows or [],
                                    columns=["raw_sku", "raw_warehouse", "raw_uom",
                                             "reason", "raw_block_reason"]),
               "预测源行排除")
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
    parser.add_argument("--sku-map", default=DEFAULT_SKU_MAP)
    parser.add_argument("--supersedes",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/decision-pack-2026-10-29",
                        help="原包目录（只读取哈希，不覆盖）")
    parser.add_argument("--test-count", type=int, default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    inputs = load_inputs(args.run, forecast_root=args.forecast_root,
                         demand_netting=args.demand, sku_map_path=args.sku_map)
    result, stats = build_pack(inputs)
    from .__main__ import _git_meta
    doc = manifest(inputs, stats, out_dir=Path(args.out),
                   data_cutoff=str((inputs.manifest.get("inputs", {})
                                    .get("demand_netting", {}) or {}).get("date_max") or ""),
                   code=_git_meta(), supersedes=args.supersedes,
                   test_count=args.test_count)
    outputs = write_outputs(result, stats, doc, Path(args.out))
    print(json.dumps({k: stats[k] for k in ("universe_keys", "destinations", "scenarios_by_uom",
                                            "reconciliation_ok", "source_ledger")},
                     ensure_ascii=False, indent=1))
    print("输出：", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
