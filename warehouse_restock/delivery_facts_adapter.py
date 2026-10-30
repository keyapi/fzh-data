# -*- coding: utf-8 -*-
"""Read-only adapter from delivery facts to warehouse_restock.

Target scope must be injected by warehouse_restock (source/version/hash).
Rows are split by item × UOM × channel × destination; partial snapshots,
mixed versions and path failures are rejected. Unknown stays unknown.
No purchase order is generated.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict


def _finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value):
    number = _finite(value)
    return None if number is None else round(number, 6)


def _scope_hash(scope):
    canonical = json.dumps({"source": scope.get("source"),
                            "version": scope.get("version"),
                            "items": sorted(scope.get("items") or [])},
                           sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_delivery_snapshot(delivery):
    """Common gates: complete pagination, single version, valid scope."""
    if not isinstance(delivery, dict):
        raise ValueError("delivery input must be an object")
    pagination = delivery.get("pagination") or {}
    if pagination.get("exhausted") is not True or pagination.get("partial") is True:
        raise ValueError("delivery snapshot is partial or not exhausted")
    for key in ("schema_version", "rule_version", "implementation_version"):
        if not delivery.get(key):
            raise ValueError("delivery snapshot missing %s" % key)
    coverage = delivery.get("coverage") or {}
    scope = delivery.get("scope") or coverage.get("scope") or {}
    if scope.get("status") != "provided":
        return {"status": "scope_pending", "rows": [], "summary": {
            "auto_order": False,
            "reason": "authoritative warehouse_restock scope not provided",
        }}
    if scope.get("hash") != _scope_hash(scope):
        raise ValueError("delivery scope hash mismatch")
    return {"status": "ok", "scope": scope, "coverage": coverage}


def build_restock_delivery_view(delivery, *, fba_item_codes=(),
                                channel_by_item=None):
    gate = validate_delivery_snapshot(delivery)
    if gate["status"] != "ok":
        return gate
    scope = gate["scope"]
    coverage = gate["coverage"]
    lines = list(delivery.get("delivery_lines") or [])
    pools = list(delivery.get("ambiguity_pools") or [])
    fba_items = {str(code) for code in (fba_item_codes or ())}
    channel_map = dict(channel_by_item or {})
    seen = set()
    duplicates = []
    for line in lines:
        key = line.get("delivery_note_item")
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    grouped = defaultdict(list)
    for line in lines:
        if line.get("docstatus") != 1:
            continue
        channel = (line.get("channel")
                   or channel_map.get(line.get("item_code"))
                   or ("fba" if line.get("item_code") in fba_items else "unknown"))
        if channel not in ("fba", "in_house", "unknown"):
            channel = "unknown"
        destination = line.get("target_warehouse") or line.get("warehouse") or ""
        key = (line.get("item_code"), line.get("uom") or "",
               channel, destination)
        grouped[key].append(line)
    pool_by_key = defaultdict(list)
    for pool in pools:
        pool_by_key[(pool.get("item_code"), pool.get("uom") or "",
                     pool.get("channel") or "unknown",
                     pool.get("warehouse") or "")].append(pool)
    rows = []
    for item_code in sorted(scope.get("items") or []):
        observed = {key: value for key, value in grouped.items()
                    if key[0] == item_code}
        if not observed:
            rows.append({
                "item_code": item_code, "uom": None, "channel": "unknown",
                "destination": "", "actual_delivery_qty": None,
                "qty_status": "no_observed_delivery",
                "linked_delivery_qty": None, "unlinked_delivery_qty": None,
                "unresolved_demand_qty": None, "potential_overlap_qty": None,
                "unknown_delivery_qty": None,
                "received_qty": None, "pending_qty": None,
                "inventory_qty": None,
                "receipt_source_status": "not_integrated",
                "inventory_source_status": "not_integrated",
                "eligible_for_restock": False,
                "suggested_action": "manual_review_no_delivery_evidence",
                "auto_order": False,
                "note": "no observed submitted DN line; not zero",
            })
            continue
        for key in sorted(observed, key=lambda item: tuple(
                "" if part is None else str(part) for part in item)):
            bucket = observed[key]
            item_code, uom, channel, destination = key
            actual_values = [_finite(line.get("actual_qty")) for line in bucket]
            unknown = any(value is None for value in actual_values)
            actual = None if unknown else round(sum(actual_values), 6)
            linked_values = [_finite(line.get("actual_qty")) for line in bucket
                             if line.get("association_status") == "linked"]
            unlinked_values = [_finite(line.get("actual_qty")) for line in bucket
                               if line.get("association_status") == "unlinked"]
            linked = (None if any(value is None for value in linked_values)
                      else round(sum(linked_values), 6))
            unlinked = (None if any(value is None for value in unlinked_values)
                        else round(sum(unlinked_values), 6))
            pool_rows = pool_by_key.get((item_code, uom, channel, destination), [])
            potential = [pool.get("potential_overlap_qty") for pool in pool_rows]
            unresolved = [pool.get("unresolved_demand_qty") for pool in pool_rows]
            potential_value = (None if len(potential) != 1
                               or potential[0] is None else potential[0])
            unresolved_value = (None if len(unresolved) != 1
                                or unresolved[0] is None else unresolved[0])
            if channel == "unknown":
                action = "manual_review_channel_unknown"
            elif unknown:
                action = "manual_review_delivery_unknown"
            elif unlinked is not None and abs(unlinked) > 1e-9:
                action = "manual_review_unlinked_delivery"
            elif potential_value:
                action = "manual_review_potential_overlap"
            else:
                action = "candidate_no_action"
            rows.append({
                "item_code": item_code, "uom": uom, "channel": channel,
                "destination": destination,
                "actual_delivery_qty": actual,
                "qty_status": "unknown" if unknown else "known",
                "linked_delivery_qty": linked,
                "unlinked_delivery_qty": unlinked,
                "unresolved_demand_qty": unresolved_value,
                "potential_overlap_qty": potential_value,
                "unknown_delivery_qty": None,
                "received_qty": None, "pending_qty": None,
                "inventory_qty": None,
                "receipt_source_status": "not_integrated",
                "inventory_source_status": "not_integrated",
                "eligible_for_restock": False,
                "suggested_action": action,
                "auto_order": False,
                "note": "suggestion only; no automatic ordering",
            })
    return {
        "status": "ok",
        "scope": scope,
        "rows": rows,
        "summary": {
            "approved_items": len(scope.get("items") or []),
            "row_count": len(rows),
            "duplicate_line_ids": duplicates,
            "duplicate_free": not duplicates,
            "grouping": "item×uom×channel×destination",
            "auto_order": False,
            "note": "No cross-UOM or cross-channel sum; no purchase order generated.",
        },
    }
