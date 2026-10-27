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

from dataclasses import asdict

from self_fulfilled_demand.canonical import load_sku_map, load_uom_cache, load_warehouse_config, resolve_warehouse
from supply_chain_visibility.supply_row import SupplyRow

from .facts import StageBalance, build_availability_schedule, tranches_to_supply_rows

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


def build_supply_facts(stock_df: pd.DataFrame, po_df: pd.DataFrame, *,
                       sku_map: pd.DataFrame, uom_cache: pd.DataFrame, warehouse_cfg: dict,
                       include_intransit: bool = True) -> tuple[list[SupplyRow], list[StageBalance], list[dict]]:
    """返回 (库存期初 SupplyRow, 在途 StageBalance, 无法归属的证据行)。

    库存与在途分开：库存是期初基准，在途是「已发出、未到仓」的阶段余额，
    必须经 ``availability_schedule`` 变成可售 tranche 后再参与分桶。
    """
    lookup = {row.tongtool_sku: (tuple(row.item_codes), row.mapping_status)
              for row in sku_map.itertuples(index=False)}
    uoms = {str(r.item_code): (str(r.stock_uom) if pd.notna(r.stock_uom) else None)
            for r in uom_cache.itertuples(index=False)} if not uom_cache.empty else {}

    rows: list[SupplyRow] = []
    evidence: list[dict] = []
    run_id = str(stock_df["run_id"].iloc[0]) if "run_id" in stock_df and len(stock_df) else "unknown"
    snapshot_day = str(pd.to_datetime(stock_df["snapshot_date"]).dt.date.iloc[0])

    def add(raw_sku, raw_wh, qty, stage, source_layer, document_key=None, available_date=None):
        mapped = _map(raw_sku, raw_wh, qty, document_key, lookup, uoms, warehouse_cfg,
                      run_id, source_layer, stage, evidence)
        if mapped is None:
            return
        item, canonical_wh, uom, wh_confidence = mapped
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

    balances: list[StageBalance] = []
    intransit_seen: dict[tuple, StageBalance] = {}
    for record in stock_df.itertuples(index=False):
        available = float(record.available or 0)
        # 0 也是有证据的观测（快照明确为 0），不能当作「没有基准」。
        add(record.sku, record.warehouse_name, available, "on_hand", SOURCE_INVENTORY)
        intransit = float(getattr(record, "intransit", 0) or 0)
        if not include_intransit or intransit <= 0:
            continue
        mapped = _map(record.sku, record.warehouse_name, intransit, None, lookup, uoms,
                      warehouse_cfg, run_id, SOURCE_INTRANSIT, "shipped_in_transit", evidence)
        if mapped is None:
            continue
        item, canonical_wh, uom, _confidence = mapped
        key = (item, canonical_wh, uom)
        balance_id = f"{SOURCE_INTRANSIT}:{run_id}:{record.sku}:{canonical_wh}"
        previous = intransit_seen.get(key)
        if previous is not None:
            merged = StageBalance(**{**asdict(previous),
                                     "balance_id": f"{previous.balance_id}+{balance_id}",
                                     "order_key": f"{previous.order_key}+{balance_id}",
                                     "qty": (previous.qty or Decimal(0)) + _dec(intransit),
                                     "order_qty": (previous.order_qty or Decimal(0)) + _dec(intransit)})
            intransit_seen[key] = merged
            balances[balances.index(previous)] = merged
            continue
        balance = StageBalance(
            balance_id=balance_id, order_key=balance_id, sku=item, warehouse=canonical_wh,
            uom=uom, stage="shipped_in_transit", qty=_dec(intransit), order_qty=_dec(intransit),
            allocation_status="free",   # 见 docs：来源未显示 FBA 预留，按自由供应处理并留证
            sellable_at=None, date_confidence="unknown", observed_at=snapshot_day,
            source="tongtool_stock.intransit", source_key=balance_id,
        )
        intransit_seen[key] = balance
        balances.append(balance)

    for record in po_df.itertuples(index=False):
        add(record.sku, record.warehouse, record.qty, "po_open", SOURCE_PO,
            document_key=str(record.document_key))

    return rows, balances, evidence


def _map(raw_sku, raw_wh, qty, document_key, lookup, uoms, warehouse_cfg, run_id,
         source_layer, stage, evidence):
    """身份/单位/仓位三关；任一不过就写证据行并返回 None。"""
    items, status = lookup.get(str(raw_sku).strip(), ((), "unmapped"))
    warehouse = resolve_warehouse(raw_wh, warehouse_cfg)
    canonical_wh = warehouse["canonical_warehouse"]
    wh_confidence = "confirmed" if warehouse["warehouse_status"] in (
        "alias_confirmed", "declared", "third_party") else "unmapped"
    base = dict(source_layer=source_layer, stage=stage, raw_sku=str(raw_sku),
                raw_warehouse=str(raw_wh), qty=_dec(qty), warehouse=canonical_wh,
                document_key=document_key,
                source_key=f"{source_layer}:{run_id}:{raw_sku}:{raw_wh}")
    if status != "mapped" or len(items) != 1:
        evidence.append(_fact("identity_unproven", identity_confidence="unproven",
                              warehouse_confidence=wh_confidence, **base))
        return None
    item = items[0]
    uom = uoms.get(item)
    if not uom:
        evidence.append(_fact("uom_unproven", sku=item, identity_confidence="proven",
                              warehouse_confidence=wh_confidence, **base))
        return None
    if wh_confidence != "confirmed":
        evidence.append(_fact("warehouse_unmapped", sku=item, uom=uom,
                              identity_confidence="proven", warehouse_confidence="unmapped",
                              **base))
        return None
    return item, canonical_wh, uom, wh_confidence


def _dec(value) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return Decimal(str(round(float(value), 6)))


def load_inputs(*, stock_path, po_path, sku_map_path, uom_cache_path,
                warehouse_alias_path, snapshot_date=None, include_intransit=True):
    stock_df, stock_meta = load_stock(stock_path, snapshot_date)
    po_df, po_meta = load_po(po_path)
    inventory_rows, balances, evidence = build_supply_facts(
        stock_df, po_df,
        sku_map=load_sku_map(sku_map_path),
        uom_cache=load_uom_cache(uom_cache_path),
        warehouse_cfg=load_warehouse_config(warehouse_alias_path),
        include_intransit=include_intransit,
    )
    schedule = build_availability_schedule(balances)
    tranche_rows, tranche_evidence = tranches_to_supply_rows(schedule)
    return dict(rows=inventory_rows + tranche_rows,
                evidence=evidence + tranche_evidence,
                stage_balances=balances, schedule=schedule,
                stock_meta=stock_meta, po_meta=po_meta)
