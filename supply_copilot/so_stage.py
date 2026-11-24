"""W1 ``stage_balances`` → per-SKU stage evidence, kept off the proven supply.

SO, production, DN and PO are **different stages** of the same factory
pipeline.  This module only summarizes the stage balances that W1 already
computed; it never adds them to the branch's proven (on-hand + in-transit)
supply, and stage balances are not additive with the SO open quantity measured
from ``lines`` (they are two different measures of the same orders).

Stages W1 cannot place are kept as ``unknown`` — never relabelled as
"not produced" and never dropped.  ``over_produced`` is a separate stage: it
is physical excess stock, not supply for the open order.
"""
from __future__ import annotations

import json
from pathlib import Path

from demand_collaboration.so_evidence import branch, sku_of

STAGE_LABELS = {
    "produced_pending_dn": "完工待发运",
    "in_production": "在产",
    "shipped_in_transit": "工厂在途",
    "not_planned": "未排产",
    "unknown": "阶段未知",
    "over_produced": "超订单现存（不计本订单供给）",
    "arrived_not_sellable": "到仓不可售",
}
STAGE_ORDER = tuple(STAGE_LABELS)
FBA_SCOPE = "external_fba"


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else round(number, 6)


def load_stage_balances(path):
    """Return ``(per_key, stats)`` from W1 records' ``stage_balances``.

    ``per_key`` is ``{(sku, branch): summary}``.  Repeated balance rows (same
    ``so``/``so_line_id``/``source_record``/``batch_key``/``stage``) are counted
    once so a re-appended W1 snapshot cannot inflate the balances.
    """
    stats = {"records": 0, "rows_read": 0, "unique_rows": 0, "duplicate_rows": 0,
             "skipped_no_branch": 0, "skipped_no_sku": 0, "keys": 0,
             "stage_totals": {stage: 0.0 for stage in STAGE_ORDER},
             "stage_known_subtotals": {stage: 0.0 for stage in STAGE_ORDER},
             "stage_unknown_qty_rows": 0, "scope_fba_qty": 0.0,
             "scope_fba_unknown_rows": 0,
             "source": "W1 stage_balances"}
    p = Path(path)
    if not p.exists():
        stats["error"] = f"SO 证据文件不存在：{p}"
        return {}, stats
    out = {}
    seen = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        stats["records"] += 1
        record = json.loads(line)
        payload = record.get("payload") or {}
        lines = payload.get("lines") or []
        br = None
        for row in lines:
            br = branch(row.get("customer"))
            if br:
                break
        for row in payload.get("stage_balances") or []:
            stats["rows_read"] += 1
            qty = _num(row.get("qty"))
            scope = str(row.get("scope") or "in_house")
            stage = str(row.get("stage") or "unknown")
            if scope == FBA_SCOPE:
                if qty is None:
                    stats["scope_fba_unknown_rows"] += 1
                else:
                    stats["scope_fba_qty"] = round(stats["scope_fba_qty"] + qty, 6)
                continue
            if not br:
                stats["skipped_no_branch"] += 1
                continue
            key_fields = (str(row.get("so") or record.get("so")), row.get("so_line_id"),
                          row.get("source_record"), row.get("batch_key"), row.get("stage"))
            if key_fields in seen:
                stats["duplicate_rows"] += 1
                continue
            seen.add(key_fields)
            sku = sku_of(row.get("item_code"))
            if not sku:
                stats["skipped_no_sku"] += 1
                continue
            stats["unique_rows"] += 1
            if qty is None:
                stats["stage_unknown_qty_rows"] += 1
            summary = out.setdefault((sku, br), {
                "so_stage_qty": {},
                "so_stage_incomplete": [],
                "so_stage_rows": 0,
                "so_stage_so_count": 0,
                "so_stage_scope_fba_qty": 0.0,
                "_cells": {},
                "_orders": set(),
            })
            # A stage with any unknown row keeps a *null* total: summing the
            # known rows would publish a partial amount as if it were complete.
            cell = summary["_cells"].setdefault(stage, {"qty": 0.0, "unknown": False})
            if qty is None:
                cell["unknown"] = True
            else:
                cell["qty"] = round(cell["qty"] + qty, 6)
            if qty is None and stage not in summary["so_stage_incomplete"]:
                summary["so_stage_incomplete"].append(stage)
            summary["so_stage_rows"] += 1
            summary["_orders"].add(key_fields[0])
    totals = stats["stage_totals"]
    known_subtotals = stats["stage_known_subtotals"]
    for summary in out.values():
        summary["so_stage_so_count"] = len(summary.pop("_orders"))
        cells = summary.pop("_cells")
        for stage, cell in cells.items():
            value = None if cell["unknown"] else cell["qty"]
            summary["so_stage_qty"][stage] = value
            if stage not in totals:
                continue
            if cell["unknown"]:
                # A total that mixes known and unknown rows is not a total:
                # publish null and keep the known part under its own name.
                totals[stage] = None
            elif totals[stage] is not None:
                totals[stage] = round(totals[stage] + value, 6)
            known_subtotals[stage] = round(known_subtotals[stage] + cell["qty"], 6)
        summary["so_stage_incomplete"].sort()
        summary["so_stage_qty"] = {stage: summary["so_stage_qty"][stage]
                                   for stage in STAGE_ORDER
                                   if stage in summary["so_stage_qty"]}
        summary["so_stage_complete"] = not summary["so_stage_incomplete"]
        summary["so_stage_included_in_proven_supply"] = False
        summary["so_stage_not_additive_with_open_qty"] = True
    stats["keys"] = len(out)
    return out, stats
