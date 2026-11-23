# -*- coding: utf-8 -*-
"""旧 GS 407,898 行 + 10 月 EN 增量的统一消费接口。

两条独立维度（不要混在一起）
1. **履约类型** ``fulfillment_scope``：self / fba / third_party_or_dropship / unknown。
2. **需求有效性** ``row_role``：sale / return_adjustment / qty_missing / cancelled /
   refunded / embedded_component。

默认主建议只取 self，但所有非 FBA 的有效需求（含代发、unknown）都单独保留并给出
``scope_reason``，不因为「不在默认口径」而被丢进 quarantine。

时间口径（关键）
- GS 月表是**发货口径**，覆盖到 ``despatch_date <= 2026-09-30``；它不包含
  「9 月下单、10 月发货」的单，也不包含 10 月的取消/改量。
- EN 增量补三类缺口：
  a) ``sale_date >= 2026-10-01`` 的新需求；
  b) ``sale_date < 2026-10-01`` 但 GS 没有对应行的迟到订单（``en_late_legacy``）；
  c) 旧单的取消 / 退款 / 数量修改（``superseded_cancelled`` / ``superseded_qty_change``），
     在行级覆盖 GS，GS 行保留在 overlap 里可审计。
- 交叉键 = (完整单据名, 通途SKU)，绝不按订单号整单覆盖，也不按 base_order_id 合并。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from . import config
from .normalize import classify_warehouse
from .store import ParquetStore, now_iso

GS_DEMAND_COLUMNS = {
    "order_id": "order_key",
    "sku_tongtool": "tongtool_sku",
    "platform_sku": "platform_sku",
    "qty": "quantity",
    "sale_date": "sale_date",
    "despatch_date": "despatch_date",
    "channel": "channel",
    "account": "account",
    "warehouse": "warehouse_name",
    "package_id": "package_id",
    "tracking": "tracking_number",
    "amount_raw_cny": "amount_cny",
    "line_id": "gs_line_id",
}

OVERRIDE_STATES = (
    "superseded_cancelled",
    "superseded_qty_change",
    "superseded_cross_cutover",
)
OVERLAP_STATES = (
    "en_match",
    "en_match_qty_diff",
    "gs_only_en_gap",
    "en_only_gs_gap",
) + OVERRIDE_STATES


REQUIRED_GS_COLUMNS = ("order_id", "sku_tongtool", "platform_sku", "qty", "sale_date", "despatch_date", "warehouse")


def load_gs_orders(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path)
    missing = [col for col in REQUIRED_GS_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"GS 订单表缺少必需列 {missing}: {path}")
    out = pd.DataFrame()
    for src, dst in GS_DEMAND_COLUMNS.items():
        out[dst] = df[src] if src in df.columns else None
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce")
    out["sale_date"] = out["sale_date"].astype("string").str.slice(0, 10)
    out["despatch_date"] = out["despatch_date"].astype("string").str.slice(0, 10)
    out["source"] = "gs_legacy"
    out["coverage_status"] = "complete"
    out["currency"] = df["currency"] if "currency" in df.columns else None
    return out


def _scope_for_gs_row(warehouse) -> tuple[str, str]:
    scope, evidence = classify_warehouse(warehouse)
    return (scope or config.SCOPE_UNKNOWN), evidence


def _en_frame(store: ParquetStore) -> pd.DataFrame:
    orders = store.load_orders()
    lines = store.load_lines()
    if not len(orders):
        return pd.DataFrame()
    on_doc = orders.merge(lines, on="en_doc_name", how="left", suffixes=("", "_line"))
    out = pd.DataFrame(
        {
            "order_key": on_doc["en_doc_name"],
            "base_order_id": on_doc["base_order_id"],
            "split_suffix": on_doc["split_suffix"],
            "sale_date": on_doc["sale_date"],
            "despatch_date": on_doc["despatch_date"],
            "warehouse_name": on_doc["warehouse_name"],
            "channel": on_doc["channel"],
            "account": on_doc["account"],
            "platform_code": on_doc["platform_code"],
            "tongtool_sku": on_doc["tongtool_sku"],
            "platform_sku": on_doc["platform_sku"],
            "erp_item_code": on_doc["erp_item_code"],
            "quantity": on_doc["quantity"],
            "demand_kind": on_doc["demand_kind"],
            "demand_kind_basis": on_doc["demand_kind_basis"],
            "is_deliver_good": on_doc["is_deliver_good"],
            "line_key": on_doc["line_key"],
            "source": "en_incremental",
            "coverage_status": on_doc["coverage_status"],
            "ingest_scope": on_doc["ingest_scope"],
            "lifecycle_state": on_doc["lifecycle_state"],
            "order_status": on_doc["order_status"],
            "invalid": on_doc["invalid"],
            "scope_conflict": on_doc["scope_conflict"],
        }
    )
    out["gs_line_id"] = None
    out["amount_cny"] = None
    out["currency"] = on_doc["order_amount_currency"]
    out["package_id"] = on_doc["package_id"]
    out["tracking_number"] = on_doc["tracking_number"]
    scopes, evidences = [], []
    for scope, evidence in zip(on_doc["fulfillment_scope"], on_doc["scope_evidence"]):
        scopes.append(str(scope) if scope is not None and not pd.isna(scope) else config.SCOPE_UNKNOWN)
        evidences.append("" if evidence is None or pd.isna(evidence) else str(evidence))
    out["fulfillment_scope"] = scopes
    out["scope_evidence"] = evidences
    return out


def _gs_frame(path: str | Path) -> pd.DataFrame:
    gs = load_gs_orders(path)
    scopes, evidences = [], []
    for wh in gs["warehouse_name"]:
        scope, evidence = _scope_for_gs_row(wh)
        scopes.append(scope)
        evidences.append(evidence)
    gs["fulfillment_scope"] = scopes
    gs["scope_evidence"] = evidences
    gs["scope_conflict"] = None
    gs["demand_kind"] = config.DSHIP_UNKNOWN
    gs["demand_kind_basis"] = "gs_monthly_sheet_has_no_shipping_method"
    gs["is_deliver_good"] = None
    gs["lifecycle_state"] = "active"
    gs["order_status"] = None
    gs["invalid"] = None
    gs["ingest_scope"] = None
    gs["base_order_id"] = gs["order_key"].astype("string").str.replace(r"_\d+$", "", regex=True)
    gs["split_suffix"] = gs["order_key"].astype("string").str.extract(r"(_\d+)$")[0]
    gs["platform_code"] = None
    gs["line_key"] = gs["gs_line_id"].astype("string")
    return gs


def _tag_rows(df: pd.DataFrame) -> pd.DataFrame:
    """只标需求有效性；履约类型保留在 fulfillment_scope，两者不互相覆盖。"""
    df = df.copy()
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    df["quantity"] = qty
    df["row_role"] = "sale"
    df.loc[df["demand_kind"] == config.DSHIP_EMBEDDED, "row_role"] = "embedded_component"
    df.loc[qty.isna(), "row_role"] = "qty_missing"
    df.loc[qty.fillna(0) < 0, "row_role"] = "return_adjustment"
    df.loc[df["lifecycle_state"].astype("string").str.startswith("cancelled"), "row_role"] = "cancelled"
    df.loc[df["lifecycle_state"].astype("string").eq("refunded"), "row_role"] = "refunded"
    df["in_main_series"] = False
    df["scope_reason"] = None
    return df


def _key_series(df: pd.DataFrame) -> pd.Series:
    return pd.Series(
        list(zip(df["order_key"].astype(str), df["tongtool_sku"].astype(str))),
        index=df.index,
    )


def build_demand(
    store_root: str | Path,
    gs_path: str | Path,
    start: str,
    end: str,
    *,
    scopes: Sequence[str] = (config.SCOPE_SELF,),
    legacy_cutover: str = config.DEFAULT_LEGACY_CUTOVER,
    legacy_despatch_cutover: str = "2026-09-30",
    store: ParquetStore | None = None,
) -> dict[str, pd.DataFrame]:
    """返回 demand / demand_non_fba / deferred / fba / quarantine / returns / overlap / summary。

    ``store`` 可传入已打开的快照对象；调用方（canonical）用它把 orders/lines
    与后续读取固定在同一个快照上。
    """
    store = store or ParquetStore(store_root)
    # 固定在同一快照目录：orders/lines 必须来自同一次提交
    with store.pinned():
        en_all = _en_frame(store)
    gs_all = _gs_frame(gs_path)
    start, end = str(start)[:10], str(end)[:10]

    en = en_all[(en_all["sale_date"] >= start) & (en_all["sale_date"] <= end)].copy() if len(en_all) else en_all
    gs = gs_all[(gs_all["sale_date"] >= start) & (gs_all["sale_date"] <= end)].copy() if len(gs_all) else gs_all

    en["key"] = _key_series(en) if len(en) else pd.Series([], dtype=object)
    gs["key"] = _key_series(gs) if len(gs) else pd.Series([], dtype=object)
    en["recent"] = en["ingest_scope"].isin(["sale_window", "modified_window"])
    en_keys = set(en["key"])
    gs_keys = set(gs["key"])

    # 只有本次增量窗口里的单据才允许覆盖 GS；历史抽样（validation_sample）不覆盖。
    recent = en[en["recent"]].copy()
    recent["cancel_or_refund"] = recent["lifecycle_state"].astype("string").str.startswith(
        ("cancelled", "refunded")
    )
    cancel_keys = set(recent.loc[recent["cancel_or_refund"], "key"])
    en_qty_recent = recent.groupby("key", dropna=False)["quantity"].sum(min_count=1)
    en_qty_all = en.groupby("key", dropna=False)["quantity"].sum(min_count=1)
    gs_qty = gs.groupby("key", dropna=False)["quantity"].sum(min_count=1)
    gs_sale_by_key = gs.groupby("key", dropna=False)["sale_date"].max()
    en_sale_by_key = en.groupby("key", dropna=False)["sale_date"].max()

    # ---- GS 行：按业务行身份裁定来源，日期只作冲突证据 --------------------
    gs_states, gs_keep = [], []
    for key, gs_sale in zip(gs["key"], gs["sale_date"]):
        en_sale = en_sale_by_key.get(key)
        if key in cancel_keys:
            gs_states.append("superseded_cancelled")
            gs_keep.append(False)
        elif key in en_qty_recent.index:
            if _qty_differs(en_qty_recent.get(key), gs_qty.get(key)):
                # 数量修改：以 EN 为准，GS 行保留审计
                gs_states.append("superseded_qty_change")
                gs_keep.append(False)
            elif gs_sale < legacy_cutover <= (en_sale or ""):
                # 同订单同 SKU 同量、销售日期跨切点 → 只算一次，EN 优先
                gs_states.append("superseded_cross_cutover")
                gs_keep.append(False)
            elif gs_sale == en_sale:
                # 同一销售日，历史段以 GS 为准，EN 跳过
                gs_states.append("en_match")
                gs_keep.append(True)
            else:
                # 两边都在历史段但日期不同：保留 GS，标待复核，不覆盖
                gs_states.append("en_match_date_diff")
                gs_keep.append(True)
        elif key in en_keys:
            # 只有历史抽样能到这里：GS 权威，EN 不覆盖
            mismatch = key in en_qty_all.index and _qty_differs(
                en_qty_all.get(key), gs_qty.get(key)
            )
            gs_states.append("en_match_qty_diff" if mismatch else "en_match")
            gs_keep.append(True)
        else:
            gs_states.append("gs_only_en_gap")
            gs_keep.append(True)
    gs["overlap_state"] = gs_states
    gs["en_line_present"] = gs["overlap_state"].isin(
        ["en_match", "en_match_qty_diff", "en_match_date_diff"] + list(OVERRIDE_STATES)
    )
    gs_series = gs[pd.Series(gs_keep, index=gs.index, dtype=bool)].copy()

    # ---- EN 行：增量 / 迟到补洞 / 覆盖改量 / 已在 GS 中则跳过 --------------
    en_states, en_keep, en_sources = [], [], []
    for key, sale_date in zip(en["key"], en["sale_date"]):
        gs_sale = gs_sale_by_key.get(key)
        if sale_date >= legacy_cutover:
            if key in gs_keys:
                if key in en_qty_recent.index and _qty_differs(
                    en_qty_recent.get(key), gs_qty.get(key)
                ):
                    en_states.append("superseded_qty_change")
                    en_sources.append("en_override")
                else:
                    en_states.append("superseded_cross_cutover")
                    en_sources.append("en_incremental")
            else:
                en_states.append("not_applicable")
                en_sources.append("en_incremental")
            en_keep.append(True)
            continue
        if key not in gs_keys:
            en_states.append("en_only_gs_gap")
            en_keep.append(True)
            en_sources.append("en_late_legacy")
            continue
        if key in cancel_keys:
            en_states.append("superseded_cancelled")
            en_keep.append(True)  # 取消单进 quarantine，可审计
            en_sources.append("en_override")
            continue
        if key in en_qty_recent.index and _qty_differs(
            en_qty_recent.get(key), gs_qty.get(key)
        ):
            en_states.append("superseded_qty_change")
            en_keep.append(True)
            en_sources.append("en_override")
            continue
        # 同量且历史段：GS 已代表这一业务行，EN 不双计
        en_states.append("en_match_date_diff" if gs_sale and gs_sale != sale_date else "en_match")
        en_keep.append(False)
        en_sources.append("en_legacy_skipped")
    en["overlap_state"] = en_states
    en["source"] = en_sources
    en["en_line_present"] = True
    en_series = en[pd.Series(en_keep, index=en.index, dtype=bool)].copy()

    series = pd.concat([gs_series, en_series], ignore_index=True)
    series = _tag_rows(series)
    # 单位证据：订单行没有 UOM；不猜，保留 null + 原因，数量仍按「件」计入
    series["uom"] = None
    series["uom_basis"] = "order_line_has_no_uom; EN Item.stock_uom not joined"
    series["uom_status"] = "unknown"

    # ---- 需求有效性 × 履约类型 --------------------------------------------
    valid = series["row_role"].eq("sale")
    fba = series[series["fulfillment_scope"] == config.SCOPE_FBA].copy()
    non_fba = series[(series["fulfillment_scope"] != config.SCOPE_FBA)].copy()
    valid_non_fba = non_fba[non_fba["row_role"].eq("sale")].copy()
    scope_list = list(scopes)
    valid_non_fba["in_main_series"] = valid_non_fba["fulfillment_scope"].isin(scope_list)
    valid_non_fba["scope_reason"] = [
        _scope_reason(scope, included)
        for scope, included in zip(valid_non_fba["fulfillment_scope"], valid_non_fba["in_main_series"])
    ]
    demand = valid_non_fba[valid_non_fba["in_main_series"]].copy()
    deferred = valid_non_fba[~valid_non_fba["in_main_series"]].copy()
    returns = non_fba[non_fba["row_role"].eq("return_adjustment")].copy()
    quarantine = non_fba[~non_fba["row_role"].isin(["sale", "return_adjustment"])].copy()

    for frame in (demand, valid_non_fba, deferred, fba, quarantine, returns):
        frame["sku_key"] = frame["tongtool_sku"].fillna(frame["platform_sku"])
        frame["sku_key_basis"] = frame["tongtool_sku"].notna().map(
            {True: "tongtool_sku", False: "platform_sku"}
        )
        frame["demand_date"] = frame["sale_date"]

    agg = (
        demand.groupby(
            ["demand_date", "sku_key", "demand_kind", "fulfillment_scope", "source", "coverage_status"],
            dropna=False,
        )
        .agg(
            quantity=("quantity", "sum"),
            order_count=("order_key", "nunique"),
            line_count=("order_key", "count"),
        )
        .reset_index()
    )
    agg["in_main_series"] = True
    agg["uom"] = None
    agg["uom_basis"] = "order_line_has_no_uom; EN Item.stock_uom not joined"
    agg["uom_status"] = "unknown"

    agg_wh = (
        demand.groupby(
            [
                "demand_date",
                "sku_key",
                "demand_kind",
                "fulfillment_scope",
                "warehouse_name",
                "uom",
                "source",
                "coverage_status",
            ],
            dropna=False,
        )
        .agg(
            quantity=("quantity", "sum"),
            order_count=("order_key", "nunique"),
            line_count=("order_key", "count"),
        )
        .reset_index()
    )
    agg_wh["uom_status"] = "unknown"
    agg_wh["uom_basis"] = "order_line_has_no_uom; EN Item.stock_uom not joined"

    # ---- 跨源对账：GS 全部行 + EN 历史段全部行（含被覆盖的，可审计） --------
    gs_overlap = gs.copy()
    gs_overlap["gs_quantity"] = gs_overlap["quantity"]
    gs_overlap["en_quantity"] = [en_qty_all.get(k) for k in gs_overlap["key"]] if len(gs_overlap) else []
    en_legacy = en[en["sale_date"] < legacy_cutover].copy() if len(en) else en.copy()
    en_legacy["en_quantity"] = en_legacy["quantity"]
    en_legacy["gs_quantity"] = [gs_qty.get(k) for k in en_legacy["key"]] if len(en_legacy) else []
    en_legacy["en_line_present"] = True
    overlap = pd.concat([gs_overlap, en_legacy], ignore_index=True)
    if len(overlap):
        overlap = overlap[overlap["overlap_state"].isin(OVERLAP_STATES)][
            [
                "order_key",
                "base_order_id",
                "split_suffix",
                "sale_date",
                "despatch_date",
                "tongtool_sku",
                "platform_sku",
                "quantity",
                "gs_quantity",
                "en_quantity",
                "fulfillment_scope",
                "source",
                "coverage_status",
                "overlap_state",
                "en_line_present",
            ]
        ].copy()
    else:
        overlap = pd.DataFrame(
            columns=[
                "order_key", "base_order_id", "split_suffix", "sale_date", "despatch_date",
                "tongtool_sku", "platform_sku", "quantity", "gs_quantity", "en_quantity",
                "fulfillment_scope", "source", "coverage_status", "overlap_state",
                "en_line_present",
            ]
        )

    # ---- sale_date 缺失：单列，不因窗口过滤而消失 --------------------------
    date_unknown = _date_unknown(en_all, gs_all)

    summary = pd.DataFrame(
        [
            {
                "start": start,
                "end": end,
                "legacy_cutover": legacy_cutover,
                "legacy_despatch_cutover": legacy_despatch_cutover,
                "scope_filter": ",".join(scope_list),
                "series_rows": int(len(series)),
                "demand_rows": int(len(demand)),
                "demand_qty": float(demand["quantity"].sum()) if len(demand) else 0.0,
                "non_fba_valid_rows": int(len(valid_non_fba)),
                "deferred_rows": int(len(deferred)),
                "deferred_qty": float(deferred["quantity"].sum()) if len(deferred) else 0.0,
                "fba_rows": int(len(fba)),
                "quarantine_rows": int(len(quarantine)),
                "return_rows": int(len(returns)),
                "en_late_legacy_rows": int((series["source"] == "en_late_legacy").sum()),
                "en_override_rows": int((series["source"] == "en_override").sum()),
                "superseded_cancelled": int((gs_overlap["overlap_state"] == "superseded_cancelled").sum()),
                "superseded_qty_change": int((gs_overlap["overlap_state"] == "superseded_qty_change").sum()),
                "superseded_cross_cutover": int(
                    (gs_overlap["overlap_state"] == "superseded_cross_cutover").sum()
                ),
                "en_match": int((gs_overlap["overlap_state"] == "en_match").sum()),
                "gs_only_en_gap": int((gs_overlap["overlap_state"] == "gs_only_en_gap").sum()),
                "en_only_gs_gap": int((en_legacy["overlap_state"] == "en_only_gs_gap").sum()),
                "qty_mismatch_kept_gs": int((gs_overlap["overlap_state"] == "en_match_qty_diff").sum()),
                "date_unknown_rows": int(len(date_unknown)),
                "date_unknown_qty": float(
                    pd.to_numeric(date_unknown["quantity"], errors="coerce").sum()
                )
                if len(date_unknown)
                else 0.0,
                "uom_unknown_rows": int(len(series)),
                "by_scope": json.dumps(
                    series["fulfillment_scope"].value_counts().to_dict(), ensure_ascii=False
                ),
                "by_role": json.dumps(series["row_role"].value_counts().to_dict(), ensure_ascii=False),
                "by_source": json.dumps(series["source"].value_counts().to_dict(), ensure_ascii=False),
            }
        ]
    )
    return {
        "demand": demand,
        "demand_by_day_sku": agg,
        "demand_by_day_sku_warehouse": agg_wh,
        "demand_non_fba": valid_non_fba,
        "deferred": deferred,
        "fba": fba,
        "quarantine": quarantine,
        "returns": returns,
        "date_unknown": date_unknown,
        "overlap": overlap,
        "summary": summary,
    }


def _date_unknown(en_all: pd.DataFrame, gs_all: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if len(en_all):
        e = en_all[en_all["sale_date"].isna()].copy()
        if len(e):
            e["key"] = _key_series(e)
            e["overlap_state"] = "date_unknown"
            e["en_line_present"] = True
            e["source"] = "en_undated"
            frames.append(e)
    if len(gs_all):
        g = gs_all[gs_all["sale_date"].isna()].copy()
        if len(g):
            g["key"] = _key_series(g)
            g["overlap_state"] = "date_unknown"
            g["en_line_present"] = False
            frames.append(g)
    if not frames:
        return pd.DataFrame(
            columns=[
                "order_key", "tongtool_sku", "platform_sku", "quantity", "sale_date",
                "fulfillment_scope", "row_role", "source", "scope_reason",
            ]
        )
    out = _tag_rows(pd.concat(frames, ignore_index=True))
    out["uom"] = None
    out["uom_basis"] = "order_line_has_no_uom; EN Item.stock_uom not joined"
    out["uom_status"] = "unknown"
    out["in_main_series"] = False
    out["scope_reason"] = "sale_date_missing"
    out["sku_key"] = out["tongtool_sku"].fillna(out["platform_sku"])
    out["demand_date"] = None
    return out


def _qty_differs(en_qty, gs_qty) -> bool:
    if en_qty is None or gs_qty is None:
        return False
    if pd.isna(en_qty) or pd.isna(gs_qty):
        return False
    return float(en_qty) != float(gs_qty)


def _scope_reason(scope: str, included: bool) -> str:
    if scope == config.SCOPE_SELF and included:
        return "included_self_fulfilled_candidate"
    if scope == config.SCOPE_THIRD_PARTY:
        return "included_third_party" if included else "third_party_outside_default_scope"
    if scope == config.SCOPE_UNKNOWN:
        return "scope_unknown_responsibility_pending"
    return "included_other"


def _day_before(date_str: str) -> str:
    return (pd.Timestamp(date_str) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def reconcile_overlap(
    store: ParquetStore,
    gs_path: str | Path,
    start: str,
    end: str,
    run_id: str | None = None,
) -> dict:
    """EN 抽样 vs GS 行级交集（供 ingest 报告的 validation 段）。"""
    with store.pinned():
        en = _en_frame(store)
    if not len(en):
        return {"status": "no_en_rows"}
    en = en[(en["sale_date"] >= start) & (en["sale_date"] < end)]
    gs = _gs_frame(gs_path)
    gs = gs[(gs["sale_date"] >= start) & (gs["sale_date"] < end)]
    en_groups = (
        en.assign(quantity=pd.to_numeric(en["quantity"], errors="coerce"))
        .groupby(["order_key", "tongtool_sku"], dropna=False)["quantity"]
        .sum()
        .reset_index()
    )
    gs_groups = (
        gs.groupby(["order_key", "tongtool_sku"], dropna=False)["quantity"]
        .sum()
        .reset_index()
    )
    merged = en_groups.merge(
        gs_groups,
        on=["order_key", "tongtool_sku"],
        how="outer",
        suffixes=("_en", "_gs"),
        indicator=True,
    )
    both = merged[merged["_merge"] == "both"]
    delta = (both["quantity_en"].fillna(0) - both["quantity_gs"].fillna(0)).abs()
    return {
        "status": "ok",
        "window": {"start": start, "end": end},
        "run_id": run_id,
        "en_orders_sampled": int(en["order_key"].nunique()),
        "en_lines": int(len(en_groups)),
        "gs_orders": int(gs["order_key"].nunique()),
        "gs_lines": int(len(gs_groups)),
        "matched_lines": int(len(both)),
        "en_only_lines": int((merged["_merge"] == "left_only").sum()),
        "gs_only_lines": int((merged["_merge"] == "right_only").sum()),
        "qty_en": float(en_groups["quantity"].fillna(0).sum()),
        "qty_gs": float(gs_groups["quantity"].fillna(0).sum()),
        "matched_qty_delta_abs": float(delta.sum()) if len(both) else 0.0,
        "matched_qty_equal_lines": int((delta == 0).sum()) if len(both) else 0,
        "note": "EN 侧多为抽样（coverage_status=sample）；gs_only 不代表 EN 缺数据。",
    }


def write_outputs(store_root: str | Path, frames: dict[str, pd.DataFrame], meta: dict | None = None) -> Path:
    out_dir = Path(store_root) / "consumer"
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "demand": "demand_lines.parquet",
        "demand_by_day_sku": "demand_by_day_sku.parquet",
        "demand_by_day_sku_warehouse": "demand_by_day_sku_warehouse.parquet",
        "demand_non_fba": "demand_all_non_fba.parquet",
        "deferred": "deferred_out_of_default_scope.parquet",
        "fba": "fba_orders.parquet",
        "quarantine": "quarantine.parquet",
        "returns": "returns.parquet",
        "date_unknown": "date_unknown.parquet",
        "overlap": "overlap_reconciliation.parquet",
        "summary": "summary.parquet",
    }
    for key, filename in targets.items():
        df = frames.get(key)
        if df is None:
            continue
        df.to_parquet(out_dir / filename, index=False, compression="zstd")
    manifest = {
        "generated_at": now_iso(),
        "legacy_cutover": config.DEFAULT_LEGACY_CUTOVER,
        "warehouse_scope_version": config.WAREHOUSE_SCOPE_VERSION,
        "files": {targets[k]: int(len(frames[k])) for k in targets if k in frames},
        "meta": meta or {},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="消费旧 GS + EN 增量，输出统一需求序列")
    ap.add_argument("--store", default="D:/Work/fzh-order-store/en-demand-v1")
    ap.add_argument("--gs-path", default="D:/Work/fzh-order-store/gs_orders.parquet")
    ap.add_argument("--start", default="2026-09-01")
    ap.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    args = ap.parse_args(argv)
    frames = build_demand(args.store, args.gs_path, args.start, args.end)
    out = write_outputs(args.store, frames, meta={"start": args.start, "end": args.end})
    print(
        json.dumps(
            {"out": str(out), "summary": frames["summary"].to_dict("records")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
