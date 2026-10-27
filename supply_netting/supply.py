# -*- coding: utf-8 -*-
"""把只读供应事实装成 Jack ``SupplyRow``，并给出每条输入的去向。

来源（全部只读、本地文件）：
- 通途库存快照 ``en_stock.parquet``：``available`` → 期初库存；``intransit`` → 在途（无 ETA）。
- 通途开放采购 ``po_open.tsv``：只有 PO 号与数量，无逐行 ETA，且仓多为物料仓。
- SKU 映射复用 ``self_fulfilled_demand.canonical.load_sku_map``（一对多不任取）。
- 单位证据复用 ``item_uom_cache.parquet``（EN ``Item.stock_uom``）。
- 仓库规范化复用 ``self_fulfilled_demand.canonical.resolve_warehouse``。

不猜身份、不补时区、不把未知数量写 0；无法归到 ``sku × 仓 × 单位`` 的输入
作为证据行保留（``identity_unproven`` / ``uom_unproven`` / ``warehouse_unmapped``）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import load_sku_map, load_uom_cache, load_warehouse_config, resolve_warehouse
from supply_chain_visibility.supply_row import SupplyRow

SOURCE_INVENTORY = "inventory_snapshot"
SOURCE_INTRANSIT = "in_transit"
SOURCE_PO = "po_open"


def load_stock(path: str | Path, snapshot_date: str | None = None) -> tuple[pd.DataFrame, dict]:
    df = pd.read_parquet(path)
    if df.empty:
        raise ValueError(f"库存快照为空：{path}")
    dates = sorted(pd.to_datetime(df["snapshot_date"]).dt.date.unique())
    chosen = date.fromisoformat(snapshot_date) if snapshot_date else dates[-1]
    if chosen not in dates:
        raise ValueError(f"库存快照没有 {chosen}；可用日期：{[str(d) for d in dates]}")
    part = df[pd.to_datetime(df["snapshot_date"]).dt.date == chosen].copy()
    part["snapshot_at"] = pd.to_datetime(part["snapshot_at"])
    meta = dict(path=str(path), snapshot_date=str(chosen), rows=int(len(part)),
                run_id=str(part["run_id"].iloc[0]) if "run_id" in part else None,
                snapshot_at=part["snapshot_at"].max().isoformat(),
                warehouses=sorted(part["warehouse_name"].astype(str).unique().tolist()))
    return part, meta


def load_po(path: str | Path | None) -> tuple[pd.DataFrame, dict]:
    if not path:
        return pd.DataFrame(columns=["document_key", "sku", "qty", "warehouse"]), dict(source="none", rows=0)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    df = pd.read_csv(p, sep="\t", header=None, dtype=str,
                     names=["document_key", "sku", "ordered", "open_qty", "warehouse"])
    df["qty"] = pd.to_numeric(df["open_qty"], errors="coerce")
    df = df[df["qty"].notna() & (df["qty"] > 0)]
    return df, dict(source=str(p), rows=int(len(df)), quantity=float(df["qty"].sum()))


def _fact(reason: str, **fields) -> dict:
    base = dict(event_id=None, source_layer=None, stage=None, sku=None, warehouse=None, uom=None,
                qty=None, available_date=None, date_confidence=None, scope="in_house",
                identity_confidence=None, warehouse_confidence=None, b_min_eligible=False,
                b_max_eligible=False, batch_key=None, batch_proven=False, document_key=None,
                source_key=None, exclusion_reason=reason, disposition_reason=reason,
                bucket_id=None, counted=False, conditional=True, scenario="any",
                raw_sku=None, raw_warehouse=None)
    base.update(fields)
    return base


def build_supply_rows(stock_df: pd.DataFrame, po_df: pd.DataFrame, *,
                      sku_map: pd.DataFrame, uom_cache: pd.DataFrame, warehouse_cfg: dict,
                      include_intransit: bool = True) -> tuple[list[SupplyRow], list[dict]]:
    """返回 (可用 SupplyRow, 无法归属的证据行)。证据行不丢，只是不参与净额。"""
    lookup = {row.tongtool_sku: (tuple(row.item_codes), row.mapping_status)
              for row in sku_map.itertuples(index=False)}
    uoms = {str(r.item_code): (str(r.stock_uom) if pd.notna(r.stock_uom) else None)
            for r in uom_cache.itertuples(index=False)} if not uom_cache.empty else {}

    rows: list[SupplyRow] = []
    evidence: list[dict] = []
    run_id = str(stock_df["run_id"].iloc[0]) if "run_id" in stock_df and len(stock_df) else "unknown"
    snapshot_day = str(pd.to_datetime(stock_df["snapshot_date"]).dt.date.iloc[0])

    def add(raw_sku, raw_wh, qty, stage, source_layer, document_key=None, available_date=None):
        items, status = lookup.get(str(raw_sku).strip(), ((), "unmapped"))
        warehouse = resolve_warehouse(raw_wh, warehouse_cfg)
        canonical_wh = warehouse["canonical_warehouse"]
        wh_confidence = "confirmed" if warehouse["warehouse_status"] in (
            "alias_confirmed", "declared", "third_party") else "unmapped"
        if status != "mapped" or len(items) != 1:
            evidence.append(_fact(
                "identity_unproven", source_layer=source_layer, stage=stage,
                raw_sku=str(raw_sku), raw_warehouse=str(raw_wh), qty=_dec(qty),
                warehouse=canonical_wh, warehouse_confidence=wh_confidence,
                identity_confidence="unproven", document_key=document_key,
                source_key=f"{source_layer}:{run_id}:{raw_sku}:{raw_wh}"))
            return
        item = items[0]
        uom = uoms.get(item)
        if not uom:
            evidence.append(_fact(
                "uom_unproven", source_layer=source_layer, stage=stage, sku=item,
                raw_sku=str(raw_sku), raw_warehouse=str(raw_wh), qty=_dec(qty),
                warehouse=canonical_wh, warehouse_confidence=wh_confidence,
                identity_confidence="proven", document_key=document_key,
                source_key=f"{source_layer}:{run_id}:{raw_sku}:{raw_wh}"))
            return
        if wh_confidence != "confirmed":
            evidence.append(_fact(
                "warehouse_unmapped", source_layer=source_layer, stage=stage, sku=item,
                uom=uom, raw_sku=str(raw_sku), raw_warehouse=str(raw_wh), qty=_dec(qty),
                warehouse=canonical_wh, warehouse_confidence="unmapped",
                identity_confidence="proven", document_key=document_key,
                source_key=f"{source_layer}:{run_id}:{raw_sku}:{raw_wh}"))
            return
        rows.append(SupplyRow(
            sku=item, warehouse=canonical_wh, stage=stage, source_layer=source_layer,
            qty=_dec(qty), qty_status="known", uom=uom, uom_proven=True,
            event_date=snapshot_day,
            available_date=available_date,
            date_confidence="confirmed" if available_date else "unknown",
            timezone_status="verified" if available_date else "unverified",
            identity_confidence="proven", source_as_of=None,
            scope="in_house", warehouse_confidence=wh_confidence, role="unknown",
            b_min_eligible=False, b_max_eligible=True,
            source_key=f"{source_layer}:{run_id}:{raw_sku}:{raw_wh}", source_complete=True,
            document_key=document_key,
        ))

    for record in stock_df.itertuples(index=False):
        available = float(record.available or 0)
        # 0 也是有证据的观测（快照明确为 0），不能当作「没有基准」。
        add(record.sku, record.warehouse_name, available, "on_hand", SOURCE_INVENTORY)
        intransit = float(getattr(record, "intransit", 0) or 0)
        if include_intransit and intransit > 0:
            # 通途在途没有逐行 ETA：保持 date_confidence=unknown，绝不补日期。
            add(record.sku, record.warehouse_name, intransit, "shipped_in_transit", SOURCE_INTRANSIT)

    for record in po_df.itertuples(index=False):
        add(record.sku, record.warehouse, record.qty, "po_open", SOURCE_PO,
            document_key=str(record.document_key))

    return rows, evidence


def _dec(value) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return Decimal(str(round(float(value), 6)))


def load_inputs(*, stock_path, po_path, sku_map_path, uom_cache_path,
                warehouse_alias_path, snapshot_date=None, include_intransit=True):
    stock_df, stock_meta = load_stock(stock_path, snapshot_date)
    po_df, po_meta = load_po(po_path)
    rows, evidence = build_supply_rows(
        stock_df, po_df,
        sku_map=load_sku_map(sku_map_path),
        uom_cache=load_uom_cache(uom_cache_path),
        warehouse_cfg=load_warehouse_config(warehouse_alias_path),
        include_intransit=include_intransit,
    )
    return dict(rows=rows, evidence=evidence, stock_meta=stock_meta, po_meta=po_meta)
