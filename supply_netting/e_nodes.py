"""本地 E 节点账。观测量不等于可叠加供给，C 只作为独立派生视图。"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .facts import StageBalance, validate_stage_balances

WAREHOUSE_CUSTOMER = {
    "波兰-FZHPoland-covers": "波兰",
    "美东-CENTRADE": "USNJ",
    "美中-FZH-DANEEY": "USTX",
    "美中-FZH-DANEEY-退货产品仓": "USTX",
}
CUSTOMER_DEST = {"波兰": "波兰-FZHPoland-covers", "USNJ": "美东-CENTRADE",
                 "USTX": "美中-FZH-DANEEY"}
POOL_CUSTOMER = {"波兰": "波兰", "美东USNJ": "USNJ", "美中USTX": "USTX"}
NODE_COLUMNS = [
    "node_id", "sku", "product_id", "warehouse", "destination_warehouse", "customer",
    "node", "qty", "uom", "uom_status", "eta", "eta_status", "promised_at", "source",
    "source_row", "source_record_id", "source_as_of", "as_of", "voucher_no",
    "voucher_line_id", "voucher_line_status", "overlap_group", "additive_supply",
    "counted_qty", "counting_reason", "c_bucket", "physical_form", "source_timezone",
]
STOCK_FIELDS = {"available": "available", "intransit": "intransit_observed",
                "waiting_shipment": "waiting_observed", "defects": "defects"}


def require(frame, columns, label):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label}: missing columns {missing}")


def numbers(frame, columns, label, *, nonnegative=False):
    for column in columns:
        converted = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(converted.dropna()).all():
            raise ValueError(f"{label}.{column}: finite quantities required")
        if nonnegative and (converted.dropna() < 0).any():
            raise ValueError(f"{label}.{column}: negative quantity")


def cutoff(as_of):
    value = pd.Timestamp(as_of)
    if value.tzinfo is None:
        raise ValueError("as_of must include timezone")
    return value.tz_convert("Asia/Shanghai")


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, default=str).encode()).hexdigest()


def _value(value):
    return None if pd.isna(value) else value


def _node(**values):
    row = dict.fromkeys(NODE_COLUMNS)
    row.update(eta_status="unknown", additive_supply=False, counted_qty=None,
               voucher_line_status="not_provided", counting_reason="document_lineage_unproven")
    row.update(values)
    row["overlap_group"] = "|".join(str(row.get(k) or "unknown") for k in
                                      ["sku", "customer", "uom"])
    return row


def stock_nodes(stock, facts, as_of, source):
    require(stock, ["stock_key", "warehouse_name", "sku", "snapshot_at", *STOCK_FIELDS], "EN")
    if stock.stock_key.isna().any() or stock.stock_key.duplicated().any():
        raise ValueError("duplicate/empty stock_key; refusing aggregate max/sum")
    if stock[["sku", "warehouse_name"]].isna().any().any():
        raise ValueError("EN missing SKU/warehouse")
    numbers(stock, STOCK_FIELDS, "EN")
    timestamps = pd.to_datetime(stock.snapshot_at, errors="raise")
    if timestamps.isna().any() or (timestamps > cutoff(as_of).tz_localize(None)).any():
        raise ValueError("EN unknown/future snapshot")
    lookup = {}
    if len(facts):
        require(facts, ["warehouse_name", "source_sku", "qty"], "C facts")
        if facts.duplicated(["warehouse_name", "source_sku"]).any():
            raise ValueError("C facts duplicate warehouse/SKU")
        lookup = {(r["warehouse_name"], r["source_sku"]): r for r in facts.to_dict("records")}
    rows = []
    for i, r in enumerate(stock.to_dict("records"), 1):
        wh, sku = r["warehouse_name"], r["sku"]
        c = lookup.get((wh, sku), {})
        for field, node in STOCK_FIELDS.items():
            if field == "available" and "退货" in wh:
                node = "returns_observation"
            if field == "available" and wh.startswith("WayfairCG"):
                node = "cg_observation"
            rows.append(_node(
                node_id=_id(source, r["stock_key"], field), sku=sku,
                product_id=_value(c.get("product_id")), warehouse=wh,
                destination_warehouse=wh, customer=WAREHOUSE_CUSTOMER.get(wh),
                node=node, qty=_value(r[field]), uom=_value(c.get("uom")),
                uom_status=_value(c.get("单位状态")) or "unknown", source=source,
                source_row=i, source_record_id=r["stock_key"],
                source_as_of=r["snapshot_at"], as_of=as_of,
                counting_reason="raw_stock_not_additive_with_C" if field == "available"
                                else "document_lineage_unproven",
                c_bucket=_value(c.get("桶")), physical_form=_value(c.get("physical_form")),
                source_timezone=r.get("source_timezone") or "unknown"))
    return pd.DataFrame(rows, columns=NODE_COLUMNS)


def so_nodes(items, summary, as_of, source):
    keys = ["so", "product_id", "pool"]
    require(items, [*keys, "item_code", "warehouse", "qty", "transaction_date", "delivery_date"], "SO items")
    require(summary, [*keys, "qty"], "SO summary")
    if items[[*keys, "item_code", "warehouse", "qty"]].isna().any().any():
        raise ValueError("SO missing identity/qty")
    if summary[keys + ["qty"]].isna().any().any() or summary.duplicated(keys).any():
        raise ValueError("SO summary duplicate/missing key")
    numbers(items, ["qty"], "SO", nonnegative=True)
    numbers(summary, ["qty"], "SO summary", nonnegative=True)
    days = pd.to_datetime(items.transaction_date, errors="raise")
    if days.isna().any() or (days.dt.date > cutoff(as_of).date()).any():
        raise ValueError("SO unknown/future transaction date")
    # 一些汇总行将 SO 号拼成集合；只按声明的成员核账，不复制/均分其数量。
    assigned = np.zeros(len(items), dtype=int)
    comparisons = []
    for r in summary.to_dict("records"):
        members = {s.strip() for s in str(r["so"]).split(",") if s.strip()}
        mask = items.so.isin(members) & items.product_id.eq(r["product_id"]) & items.pool.eq(r["pool"])
        if not members or set(items.loc[mask, "so"]) != members:
            raise ValueError("SO reconciliation: summary voucher member missing")
        assigned += mask.to_numpy(dtype=int)
        comparisons.append(dict(so=r["so"], product_id=r["product_id"], pool=r["pool"],
                                expected=r["qty"], actual=items.loc[mask, "qty"].sum(min_count=1)))
    recon = pd.DataFrame(comparisons)
    recon["delta"] = recon.actual - recon.expected
    if (assigned != 1).any() or recon[["actual", "expected"]].isna().any().any() or (recon.delta.abs() > 1e-9).any():
        raise ValueError("SO reconciliation failed; summary is not additional supply")
    rows = []
    for i, r in enumerate(items.to_dict("records"), 2):
        customer = POOL_CUSTOMER.get(r["pool"])
        rows.append(_node(
            node_id=_id(source, "csv", i), sku=r["item_code"], product_id=r["product_id"],
            warehouse=r["warehouse"], destination_warehouse=CUSTOMER_DEST.get(customer),
            customer=customer, node="so_unshipped", qty=r["qty"], uom="个",
            uom_status="brief_verified_qty;export_conversion_not_provided",
            promised_at=_value(r["delivery_date"]), source=source, source_row=i,
            source_record_id=f"{r['so']}:export_row:{i}", as_of=as_of,
            voucher_no=r["so"], voucher_line_status="export_row_only_not_SO_Item_name",
            source_timezone="unknown"))
    recon["check"] = "so_summary_vs_items"
    return pd.DataFrame(rows, columns=NODE_COLUMNS), recon


def partition_document_line(root, sku, warehouse, uom, *, ordered, dn, shipped, received):
    """仅用于已证同一订单行/分配额度；不能把累计里程碑相加。"""
    ordered, dn, shipped, received = map(lambda x: Decimal(str(x)), (ordered, dn, shipped, received))
    if not all(x.is_finite() for x in (ordered, dn, shipped, received)) or not (
            ordered >= dn >= shipped >= received >= 0):
        raise ValueError("document quantities must be finite monotone 0<=received<=shipped<=DN<=ordered")
    balances = dict(unreleased=ordered-dn, finished_waiting_shipment=dn-shipped,
                    shipped_in_transit=shipped-received, completed_sellable_delivery=received)
    rows = [StageBalance(balance_id=f"{root}:{stage}", order_key=root, sku=sku,
                         warehouse=warehouse, uom=uom, stage=stage, qty=qty,
                         order_qty=ordered, source="explicit_document_lineage",
                         batch_key=root, batch_proven=True,
                         included_in_opening=stage == "completed_sellable_delivery")
            for stage, qty in balances.items()]
    errors = validate_stage_balances(rows, {root: ordered})
    if errors or sum(r.qty for r in rows) != ordered:
        raise ValueError(f"document partition failed: {errors}")
    return rows


def available_view(c, as_of):
    key = ["product_id", "pool", "physical_form", "canonical_uom"]
    require(c, [*key, "可发供给"], "C availability")
    if c.duplicated(key).any():
        raise ValueError("duplicate C availability key")
    numbers(c, ["可发供给"], "C availability", nonnegative=True)
    result = c.copy().rename(columns={"可发供给": "supply_qty"})
    result["customer"] = result.pool.map(POOL_CUSTOMER)
    result["as_of"] = as_of
    result["non_additive_with_raw"] = True
    result["decision_status"] = "partial;future_supply_and_external_sales_unproven"
    return result


def coverage_table(nodes):
    result = []
    absent = {"dn_unshipped": "DN item/physical shipment link absent",
              "shipped_in_transit": "voucher/lot allocation and ETA absent",
              "po_open": "PO line/receipt allocation not provided in required inputs",
              "cg_transfer": "eligible/non-stale/transfer authority to destination unproven",
              "wip": "WO/first-operation facts not provided",
              "external_sold_unposted": "Poland external order to posting links absent",
              "returns": "return warehouse export incomplete"}
    for customer in CUSTOMER_DEST:
        for node in [*STOCK_FIELDS.values(), "so_unshipped", *absent]:
            group = nodes[nodes.customer.eq(customer) & nodes.node.eq(node)]
            known = group.qty.notna().sum()
            result.append(dict(customer=customer, node=node, rows=len(group),
                               qty=group.qty.sum(min_count=1) if len(group) else None,
                               unknown_rows=len(group)-int(known),
                               status="observed_partial" if len(group) else "unknown",
                               source_complete=False,
                               reason=absent.get(node, "snapshot/export only; no voucher allocation")))
    return pd.DataFrame(result)


def validate_nodes(nodes):
    require(nodes, NODE_COLUMNS, "nodes")
    if nodes.node_id.duplicated().any() or nodes.node_id.isna().any():
        raise ValueError("duplicate/empty node_id")
    numbers(nodes, ["qty"], "nodes")
    if nodes.additive_supply.any() or nodes.counted_qty.notna().any():
        raise ValueError("unproven current inputs must not become additive supply")
    if nodes.eta.notna().any():
        raise ValueError("current inputs have no confirmed ETA")


def reconcile_stock(stock, facts):
    require(facts, ["warehouse_name", "source_sku", "qty"], "C facts")
    if facts.duplicated(["warehouse_name", "source_sku"]).any():
        raise ValueError("C facts duplicate raw key")
    left = stock[["stock_key", "sku", "warehouse_name", "available"]]
    right = facts[["source_sku", "warehouse_name", "qty"]]
    result = left.merge(right, how="outer", left_on=["sku", "warehouse_name"],
                        right_on=["source_sku", "warehouse_name"], indicator=True,
                        validate="one_to_one")
    result["delta"] = result.available - result.qty
    if not result._merge.eq("both").all() or (result.delta.abs() > 1e-9).any():
        raise ValueError("EN/C raw stock reconciliation failed")
    result["check"] = "EN_available_vs_C_raw"
    return result.drop(columns="_merge")


def main():
    from .e_node_artifacts import run
    run()


if __name__ == "__main__":
    main()
