# -*- coding: utf-8 -*-
"""Full supply facts v3: DN/PO position joined with SO, production, inventory,
transit, receipts and local frozen A/B/C, keeping per-stage quantity/date
fragments.

Rules:
* purpose must come from an approved mapping; missing/unknown/invalid stays
  ``unknown`` and never defaults to branch/in-house;
* non-authoritative sources attach by exact full key only; they never fill a
  missing branch/tt_sku. Only explicit B/A identity may fill a blank DN/PO row,
  and only when the complete candidate set agrees on one identity;
* every layer has a stable source identity: same identity + same payload is
  replayed once, same identity + different payload is an explicit conflict,
  different identities are kept separately; missing identity stays unknown;
* quantities stay null when the source is unknown/unavailable; estimated is
  never merged into proven;
* POD upload is not a receipt; multiple waybills never copy the quantity;
* layers are never summed into one "total supply"; PO completion is an approved
  assumption, not proof of receipt.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

SCHEMA_VERSION = "full-supply-facts/v3"
RULE_VERSION = "2026-11-02.4"
IMPLEMENTATION_VERSION = "fzh.full_supply_facts@2026-11-02.4"
QUANTITY_SCALE = 6

VALID_PURPOSES = ("branch", "fba")
QTY_FIELDS = ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty",
              "unresolved_qty", "so_open_qty", "in_production_qty",
              "in_production_estimated_qty", "inventory_qty",
              "inventory_observed_qty", "inventory_current_available_qty",
              "in_transit_qty", "received_qty")
LAYER_FIELDS = {
    "dn_po": ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty"),
    "so_demand": ("so_open_qty",),
    "production": ("in_production_qty",),
    "production_estimated": ("in_production_estimated_qty",),
    "inventory": ("inventory_qty", "inventory_current_available_qty"),
    "in_transit": ("in_transit_qty",),
    "receipt": ("received_qty",),
}
_STATUS_RANK = {
    "known": 0, "proven": 0, "estimated": 0, "ok": 0,
    "partial": 1, "pod_only": 1,
    "unknown": 2, "unqueried": 2,
    "unavailable": 3, "missing": 3,
    "conflict": 4, "failed": 4, "source_error": 4,
}
FRESHNESS_VALUES = ("fresh", "stale", "future", "unknown_time")


def _dec(value, *, signed=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not number.is_finite():
        return None
    return number if signed or number >= 0 else None


def _qty(value, *, signed=False):
    """Normalized decimal string; rejects precision beyond the fixed contract."""
    number = _dec(value, signed=signed)
    if number is None:
        return None
    if -number.as_tuple().exponent > QUANTITY_SCALE:
        raise ValueError("quantity_scale_exceeds_contract")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _text(value):
    return "" if value is None else str(value).strip()


def _payload_key(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    number = _dec(value)
    if number is not None:
        return _qty(number)
    return _text(value)


def _time_parts(value):
    """Return (aware UTC datetime | None, raw | None, status)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None, "missing"
    if isinstance(value, datetime):
        raw = value.isoformat()
        parsed = value
    elif isinstance(value, date):
        return None, value.isoformat(), "date_only"
    elif isinstance(value, str):
        raw = value.strip()
        if len(raw) == 10:
            try:
                date.fromisoformat(raw)
                return None, raw, "date_only"
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                date.fromisoformat(raw)
            except ValueError:
                return None, raw, "invalid"
            return None, raw, "date_only"
    else:
        return None, str(value), "invalid"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, raw, "naive"
    return parsed.astimezone(timezone.utc), raw, "known"


def _aware(value):
    return _time_parts(value)[0]


def _iso(value):
    parsed = _aware(value)
    return parsed.isoformat() if parsed else None


def _purpose(value):
    purpose = _text(value)
    return purpose if purpose in VALID_PURPOSES else "unknown"


def _key(item_code, uom, warehouse, purpose, tt_sku=None, branch=""):
    return (_text(item_code), _text(uom), _text(warehouse), _purpose(purpose),
            _text(tt_sku), _text(branch))


def _row_base(key):
    purpose = key[3]
    scope = {"branch": "in_house", "fba": "external_fba"}.get(purpose, "unknown")
    reasons = []
    if purpose == "unknown":
        reasons.append("purpose_unknown")
    if purpose in VALID_PURPOSES and not key[4]:
        reasons.append("tt_sku_unknown")
    if purpose == "branch" and not key[5]:
        reasons.append("branch_unknown")
    return {
        "item_code": key[0], "uom": key[1] or None, "warehouse": key[2],
        "purpose": purpose, "tt_sku": key[4] or None, "branch": key[5],
        "pool": key[2], "scope": scope,
        **{name: None for name in QTY_FIELDS},
        "inventory_as_of": None, "inventory_as_of_raw": None,
        "inventory_time_status": "missing",
        "inventory_time_proven": False,
        "inventory_date_age_days": None,
        "inventory_observed_uom": None,
        "inventory_freshness": "unknown_time",
        "inventory_inclusion_status": "unknown",
        "attribution_status": None, "abc_identity_source": None,
        "b_units": [], "order_eligibility": "unknown", "order_blockers": [],
        "receipt_basis": None,
        "available_date": None, "available_date_raw": None,
        "available_date_time_status": "missing",
        "date_confidence": "unknown", "available_date_kind": None,
        "stage_quantities": [], "source_status": {}, "unknown_reasons": reasons,
        "sources": [], "next_node": None, "alerts": [],
        "forecast_connected": False, "coverage": "full_inputs",
        "netting_ready": False, "auto_order": False,
    }


def _mark_unknown(row, layer, reason):
    row["unknown_reasons"].append(reason)
    row.setdefault("_unknown_layers", set()).add(layer)
    for field in LAYER_FIELDS.get(layer, ()):
        if field == "inventory_observed_qty":
            continue
        row[field] = None


def _add_qty(row, field, layer, qty):
    if qty is None:
        _mark_unknown(row, layer, "quantity_unknown_" + layer)
        return
    if layer in row.get("_unknown_layers", set()):
        return
    row[field] = _qty((_dec(row[field]) or Decimal(0)) + qty)


def _add_stage(row, stage, qty, date_value=None, date_kind=None, *,
               source_identity=None, replay=False, conflict=False,
               identity_status=None):
    """Append a quantity/date fragment only; aggregates are handled separately."""
    if qty is None:
        return
    parsed, raw, status = _time_parts(date_value)
    fragment = {"stage": stage, "qty": _qty(qty),
                "date": parsed.isoformat() if parsed else None,
                "date_raw": raw, "date_status": status,
                "date_kind": date_kind,
                "date_confidence": ({"observation": "observed",
                                     "expected": "expected",
                                     "actual": "confirmed"}.get(date_kind, "unknown")),
                "source_identity": source_identity,
                "replay": bool(replay), "conflict": bool(conflict),
                "identity_status": identity_status}
    if fragment not in row["stage_quantities"]:
        row["stage_quantities"].append(fragment)


def _merge_source(row, layer, status, observed_at=None, reason="",
                  source_identity=None, evidence=None):
    current = row["source_status"].get(layer)
    if current is None:
        row["source_status"][layer] = status
    elif _STATUS_RANK.get(status, 2) >= _STATUS_RANK.get(current, 2):
        row["source_status"][layer] = status
    parsed, raw, time_status = _time_parts(observed_at)
    source = {"layer": layer, "status": status,
              "observed_at": parsed.isoformat() if parsed else None,
              "observed_at_raw": raw, "time_status": time_status,
              "source_identity": source_identity, "evidence": evidence}
    if source not in row["sources"]:
        row["sources"].append(source)
    if reason:
        row["unknown_reasons"].append(reason)


def _source_identity(identity_fields, values):
    return {field: value for field, value in zip(identity_fields, values)
            if value not in (None, "")}


def _dedupe_layer(records, *, layer, source_groups, identity_groups,
                  payload_fields):
    """Collapse replay, surface conflicts and keep missing identity unknown.

    ``source_groups`` identify the document/line/batch. Business dimensions are
    added to the identity but do not replace a missing source reference.
    """
    groups = defaultdict(list)
    missing = []
    for record in records:
        source_values = tuple(
            next((_text(record.get(field)) for field in group
                  if _text(record.get(field))), "")
            for group in source_groups)
        values = tuple(
            next((_text(record.get(field)) for field in group
                  if _text(record.get(field))), "")
            for group in identity_groups)
        if not any(source_values):
            missing.append(record)
        else:
            groups[values].append(record)
    effective = []
    replayed = conflicts = 0
    for values, items in sorted(groups.items()):
        payloads = []
        for item in items:
            payload = tuple(_payload_key(item.get(field))
                            for field in payload_fields)
            if payload not in payloads:
                payloads.append(payload)
        identity = {group[0]: value for group, value in
                    zip(identity_groups, values) if value}
        if len(payloads) > 1:
            conflicts += 1
            record = dict(items[0])
            record.update({"_conflict": True, "_records": items,
                           "_source_identity": identity})
            effective.append(record)
        else:
            if len(items) > 1:
                replayed += len(items) - 1
            merged = dict(items[0])
            merged.update({"_source_identity": identity,
                           "_replay_count": len(items)})
            effective.append(merged)
    for record in missing:
        item = dict(record)
        item["_identity_missing"] = True
        item["_source_identity"] = None
        effective.append(item)
    return effective, {
        "layer": layer,
        "input_rows": len(records),
        "identities": len(groups),
        "replayed": replayed,
        "conflicts": conflicts,
        "missing_identity": len(missing),
        "effective_rows": len(effective),
    }


def _row_for(rows, item, uom, warehouse, purpose, branch="", tt_sku=None):
    """Exact-key attach for non-authoritative sources; never fill identity."""
    key = _key(item, uom, warehouse, purpose, tt_sku, branch)
    return rows.setdefault(key, _row_base(key))


def _abc_identities(abc_rows):
    identities = set()
    for item in abc_rows:
        purpose = _purpose(item.get("purpose"))
        if purpose not in VALID_PURPOSES:
            continue
        if item.get("attribution_status") in (
                "b_multi_uom_ambiguous", "cg_pool_ambiguous",
                "b_identity_conflict", "a_inactive", "unattributed"):
            continue
        key = _key(item.get("item_code"), item.get("uom"),
                   item.get("warehouse"), purpose, item.get("tt_sku"),
                   item.get("branch"))
        if key[0] and (key[4] or key[5]):
            identities.add(key)
    return identities


def _enrich_blank_position_rows(rows, abc_rows):
    """Fill blank DN/PO identity only if the *complete* B candidate set agrees."""
    identities = _abc_identities(abc_rows)
    for key, row in list(rows.items()):
        if row["purpose"] not in VALID_PURPOSES:
            continue
        if row["tt_sku"] and row["branch"]:
            continue
        matches = [
            identity for identity in identities
            if identity[0] == key[0] and identity[1] == key[1]
            and identity[2] == key[2] and identity[3] == key[3]
            and (not row["tt_sku"] or not identity[4]
                 or identity[4] == row["tt_sku"])
            and (not row["branch"] or not identity[5]
                 or identity[5] == row["branch"])]
        if len(matches) == 1:
            identity = matches[0]
            if not row["tt_sku"] and identity[4]:
                row["tt_sku"] = identity[4]
                row["unknown_reasons"] = [
                    reason for reason in row["unknown_reasons"]
                    if reason != "tt_sku_unknown"]
            if not row["branch"] and identity[5]:
                row["branch"] = identity[5]
                row["unknown_reasons"] = [
                    reason for reason in row["unknown_reasons"]
                    if reason != "branch_unknown"]
            attached = _key(row["item_code"], row["uom"], row["warehouse"],
                            row["purpose"], row["tt_sku"], row["branch"])
            if attached != key:
                del rows[key]
                rows[attached] = row
        elif len(matches) > 1:
            row["unknown_reasons"].append("target_key_ambiguous")


WAYBILL_IDENTITY_FIELDS = ("delivery_note", "delivery_note_item", "item_code",
                           "uom", "warehouse", "branch", "purpose", "tt_sku")


def _waybill_identity(event):
    values = []
    for field in WAYBILL_IDENTITY_FIELDS:
        if field == "delivery_note_item":
            values.append(_text(event.get("delivery_note_item")
                                or event.get("dn_item")))
        else:
            values.append(_text(event.get(field)))
    return tuple(values)


def _event_sort_key(event):
    return (_text(event.get("waybill") or event.get("shipment")),
            json.dumps(event, sort_keys=True, ensure_ascii=False, default=str))


def collapse_waybills(events: Iterable[dict]) -> list[dict]:
    """Dedupe logistics by full business identity, not DN×item×UOM only."""
    events = list(events)
    by_identity = defaultdict(list)
    for event in events:
        by_identity[_waybill_identity(event)].append(event)
    waybill_identities = defaultdict(set)
    for event in events:
        waybill = _text(event.get("waybill") or event.get("shipment"))
        if waybill:
            waybill_identities[waybill].add(_waybill_identity(event))
    out = []
    for identity, raw_items in sorted(by_identity.items()):
        items = sorted(raw_items, key=_event_sort_key)
        identity_dict = _source_identity(WAYBILL_IDENTITY_FIELDS, identity)
        waybills = sorted({_text(item.get("waybill") or item.get("shipment"))
                           for item in items
                           if _text(item.get("waybill") or item.get("shipment"))})
        if len(waybills) > 1:
            merged = dict(items[0])
            merged.update({"qty": None, "qty_status": "unknown",
                           "reason": "multi_waybill_allocation_unknown",
                           "waybills": waybills,
                           "source_identity": identity_dict})
            out.append(merged)
            continue
        buckets = defaultdict(list)
        for item in items:
            buckets[_text(item.get("waybill") or item.get("shipment"))].append(item)
        for waybill, raw_group in sorted(buckets.items()):
            group = sorted(raw_group, key=_event_sort_key)
            payloads = []
            for item in group:
                payload = (_payload_key(item.get("qty")),
                           _text(item.get("available_date")),
                           _text(item.get("source_status")))
                if payload not in payloads:
                    payloads.append(payload)
            if len(payloads) == 1:
                kept = dict(group[0])
                kept["source_identity"] = identity_dict
                if len(group) > 1:
                    kept["_replay_count"] = len(group)
                out.append(kept)
            else:
                merged = dict(group[0])
                merged.update({"qty": None, "qty_status": "unknown",
                               "reason": "duplicate_waybill_quantity_conflict",
                               "candidates": [dict(item) for item in group],
                               "source_identity": identity_dict})
                out.append(merged)
    # A waybill with an empty dimension cannot be split over several explicit
    # destinations; keep the observation but do not choose one.
    for event in events:
        identity = _waybill_identity(event)
        waybill = _text(event.get("waybill") or event.get("shipment"))
        if not waybill:
            continue
        identities = waybill_identities[waybill]
        warehouses = {item[4] for item in identities if item[4]}
        branches = {item[5] for item in identities if item[5]}
        ambiguous = ((not identity[4] and len(warehouses) > 1)
                     or (not identity[5] and len(branches) > 1))
        if ambiguous:
            explicit = {item for item in identities
                        if (identity[4] or item[4])
                        and (identity[5] or item[5])}
            out = [item for item in out
                   if not (_waybill_identity(item) == identity
                           and _text(item.get("waybill")
                                     or item.get("shipment")) == waybill)]
            merged = dict(event)
            merged.update({
                "qty": None, "qty_status": "unknown",
                "reason": "multi_assignment_allocation_unknown",
                "candidates": [_source_identity(WAYBILL_IDENTITY_FIELDS, item)
                               for item in sorted(explicit)],
                "source_identity": _source_identity(WAYBILL_IDENTITY_FIELDS,
                                                    identity)})
            out.append(merged)
    return sorted(out, key=lambda item: (
        _waybill_identity(item), _text(item.get("waybill")
                                       or item.get("shipment"))))


def _pod_evidence(receipt):
    signed = _aware(receipt.get("signed_at"))
    uploaded = _aware(receipt.get("pod_uploaded_at"))
    if signed:
        return "proven", signed
    if uploaded:
        return "pod_only", None
    return "unknown", None


def _finalize(row):
    row.pop("_unknown_layers", set())
    fragments = row["stage_quantities"]
    for fragment in fragments:
        if fragment["stage"] == "inventory":
            row["inventory_as_of"] = fragment["date"]
            row["inventory_as_of_raw"] = fragment["date_raw"]
            row["inventory_time_status"] = fragment["date_status"]
    arrivals = [fragment for fragment in fragments
                if fragment["date_kind"] in ("expected", "actual")
                and fragment["date"] is not None]
    if arrivals:
        earliest = min(arrivals, key=lambda item: item["date"])
        row["available_date"] = earliest["date"]
        row["available_date_raw"] = earliest["date_raw"]
        row["available_date_time_status"] = earliest["date_status"]
        row["available_date_kind"] = earliest["date_kind"]
        row["date_confidence"] = ("confirmed" if earliest["date_kind"] == "actual"
                                  else "expected")
    row["unknown_reasons"] = sorted(set(row["unknown_reasons"]))
    row["source_status"] = dict(sorted(row["source_status"].items()))
    row["inventory_current_available"] = row["inventory_current_available_qty"] is not None


def _contract_unknown(layer_status, layer, rows):
    status = (layer_status or {}).get(layer)
    if status not in ("incomplete", "partial", "unavailable"):
        return
    for row in rows:
        _merge_source(row, layer, status, reason="source_contract_incomplete")
        if layer == "dn_po":
            row["source_status"]["dn_po"] = "partial"
            continue
        _mark_unknown(row, layer, "source_contract_incomplete")
        if layer == "production":
            row["in_production_estimated_qty"] = None


def build_full_supply_facts(position_result: dict, *, so_balances=(),
                            production=(), inventory=(), abc_inventory=(),
                            transit=(), receipts=(), approved_items=(), as_of=None,
                            max_age_seconds=None, layer_status=None) -> dict:
    rows = {}
    touched = defaultdict(list)
    reconciliation = {}
    abc_rows = list(abc_inventory or ())
    for pos in position_result.get("rows") or []:
        key = _key(pos.get("item_code"), pos.get("uom"), pos.get("warehouse"),
                   pos.get("purpose"), pos.get("tt_sku"), pos.get("branch"))
        payload = (pos.get("dn_net_qty"), pos.get("po_completed_assumed_qty"),
                   pos.get("open_po_qty"), pos.get("unresolved_qty"))
        if key in rows:
            existing = tuple(rows[key].get(field) for field in
                             ("dn_net_qty", "po_completed_assumed_qty",
                              "open_po_qty", "unresolved_qty"))
            if existing != tuple(_qty(value, signed=(index == 0))
                                 for index, value in enumerate(payload)):
                raise ValueError("duplicate_target_key")
            continue
        row = rows.setdefault(key, _row_base(key))
        touched["dn_po"].append(row)
        row["dn_net_qty"] = _qty(pos.get("dn_net_qty"), signed=True)
        row["po_completed_assumed_qty"] = _qty(pos.get("po_completed_assumed_qty"))
        row["open_po_qty"] = _qty(pos.get("open_po_qty"))
        row["unresolved_qty"] = _qty(pos.get("unresolved_qty"))
        if any(pos.get(f) is None for f in
               ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty")):
            _mark_unknown(row, "dn_po", "dn_po_quantity_unknown")
        if "po_in_snapshot" in (pos.get("reasons") or []):
            row["inventory_inclusion_status"] = "po_in_snapshot"
        source_report = position_result.get("report") or {}
        versions = source_report.get("source_versions") or {}
        # Position.as_of is calculation time, not the time the DN was observed.
        _merge_source(row, "dn_po", "known",
                      versions.get("observed_at") or versions.get("as_of"))
        for tranche in pos.get("tranches") or []:
            _merge_source(
                row, "dn_line", "known",
                versions.get("observed_at") or versions.get("as_of"),
                source_identity={
                    "delivery_note": tranche.get("delivery_note"),
                    "dn_item": tranche.get("dn_item"),
                    "creation": tranche.get("creation"),
                    "po_code": tranche.get("po_code")})
        unresolved = _dec(pos.get("unresolved_qty"))
        pending = (unresolved is None or unresolved > 0 or pos.get("unknown_quantity_lines")
                   or pos.get("return_review_lines"))
        if pending:
            row["source_status"]["dn_po"] = "partial"
            row["unknown_reasons"].extend(pos.get("reasons") or [])
            row["unknown_reasons"].append("dn_po_unresolved")
        observations = source_report.get("po_source_observed_at") or {}
        for code in sorted({t.get("po_code") for t in pos.get("tranches") or []
                            if t.get("po_code")}):
            _merge_source(row, "po_status", "known", observations.get(code),
                          source_identity={"po_code": code})
        _add_stage(row, "po_completed_assumed",
                   _dec(pos.get("po_completed_assumed_qty")),
                   pos.get("as_of"), "observation")
        _add_stage(row, "po_open", _dec(pos.get("open_po_qty")), None, None)

    # A/B identity is applied before any non-authoritative source, so order
    # cannot make a blank row adopt the first arriving branch.
    _enrich_blank_position_rows(rows, abc_rows)

    for item in abc_rows:
        key = _key(item.get("item_code"), item.get("uom"), item.get("warehouse"),
                   item.get("purpose"), item.get("tt_sku"), item.get("branch"))
        row = rows.setdefault(key, _row_base(key))
        touched["inventory"].append(row)
        row.setdefault("_inventory_sources", set()).add("abc")
        row["attribution_status"] = item.get("attribution_status")
        row["abc_identity_source"] = item.get("abc_identity_source")
        row["b_units"] = list(item.get("b_units") or [])
        row["order_eligibility"] = item.get("order_eligibility") or "unknown"
        row["order_blockers"] = list(item.get("order_blockers") or [])
        row["inventory_observed_uom"] = item.get("inventory_observed_uom")
        row["inventory_time_proven"] = bool(item.get("inventory_time_proven"))
        row["inventory_date_age_days"] = item.get("inventory_date_age_days")
        row["inventory_freshness"] = item.get("inventory_freshness") or "unknown_time"
        row["inventory_time_status"] = item.get("inventory_time_status") or "missing"
        row["inventory_as_of_raw"] = item.get("inventory_as_of_raw")
        observed = _dec(item.get("inventory_observed_qty"))
        inventory_qty = _dec(item.get("inventory_qty"))
        current = _dec(item.get("inventory_current_available_qty"))
        row["inventory_observed_qty"] = _qty(item.get("inventory_observed_qty"))
        row["inventory_qty"] = _qty(item.get("inventory_qty"))
        row["inventory_current_available_qty"] = _qty(
            item.get("inventory_current_available_qty"))
        status = _text(item.get("source_status") or "unknown")
        _merge_source(row, "inventory", status, item.get("inventory_as_of"),
                      "" if inventory_qty is not None else "inventory_not_attributed",
                      source_identity={"source_ref": item.get("source_ref"),
                                       "item_code": item.get("item_code"),
                                       "pool": item.get("pool")})
        if observed is not None:
            _add_stage(row, "inventory", observed, item.get("inventory_as_of_raw"),
                       "observation",
                       source_identity={"source_ref": item.get("source_ref")})
        for reason in item.get("reasons") or []:
            if reason not in row["unknown_reasons"]:
                row["unknown_reasons"].append(reason)
        if item.get("coverage") and item.get("coverage") != "abc_inventory":
            row["coverage"] = item.get("coverage")
        if current is None and status == "known" and observed is not None:
            row["unknown_reasons"].append("inventory_not_current_available")

    so_effective, reconciliation["so_demand"] = _dedupe_layer(
        so_balances, layer="so_demand",
        source_groups=(("source_ref",), ("so",), ("so_line",)),
        identity_groups=(
            ("source_ref",), ("so",), ("so_line",), ("item_code",),
            ("uom",), ("warehouse",), ("purpose",), ("tt_sku",),
            ("branch",)),
        payload_fields=("so_open_qty", "source_status", "observed_at"))
    for item in so_effective:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        touched["so_demand"].append(row)
        if item.get("_conflict"):
            _merge_source(row, "so_demand", "conflict",
                          source_identity=item["_source_identity"],
                          reason="source_payload_conflict")
            _mark_unknown(row, "so_demand", "source_payload_conflict")
            for record in item["_records"]:
                _add_stage(row, "so_demand", _dec(record.get("so_open_qty")),
                           record.get("observed_at"), "observation",
                           source_identity=item["_source_identity"], conflict=True)
            continue
        if item.get("_identity_missing"):
            _merge_source(row, "so_demand", "unknown",
                          item.get("observed_at"), "source_identity_missing")
            _mark_unknown(row, "so_demand", "source_identity_missing")
            _add_stage(row, "so_demand", _dec(item.get("so_open_qty")),
                       item.get("observed_at"), "observation",
                       identity_status="missing")
            continue
        status = _text(item.get("source_status") or "known")
        qty = _dec(item.get("so_open_qty")) if status == "known" else None
        _merge_source(row, "so_demand", status, item.get("observed_at"),
                      "" if qty is not None else "so_open_unknown",
                      source_identity=item["_source_identity"])
        _add_qty(row, "so_open_qty", "so_demand", qty)
        _add_stage(row, "so_demand", qty, item.get("observed_at"), "observation",
                   source_identity=item["_source_identity"],
                   replay=item.get("_replay_count", 1) > 1)

    prod_effective, reconciliation["production"] = _dedupe_layer(
        production, layer="production",
        source_groups=(("source_ref",), ("work_order", "wo", "name")),
        identity_groups=(
            ("source_ref",), ("work_order", "wo", "name"), ("item_code",),
            ("uom",), ("warehouse",), ("purpose",), ("tt_sku",),
            ("branch",)),
        payload_fields=("qty", "evidence_status", "available_date",
                        "observed_at"))
    for item in prod_effective:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        touched["production"].append(row)
        if item.get("_conflict"):
            _merge_source(row, "production", "conflict",
                          source_identity=item["_source_identity"],
                          reason="source_payload_conflict")
            _mark_unknown(row, "production", "source_payload_conflict")
            for record in item["_records"]:
                _add_stage(row, "in_production", _dec(record.get("qty")),
                           record.get("available_date"), "expected",
                           source_identity=item["_source_identity"], conflict=True)
            continue
        if item.get("_identity_missing"):
            _merge_source(row, "production", "unknown",
                          item.get("observed_at"), "source_identity_missing")
            _mark_unknown(row, "production", "source_identity_missing")
            _add_stage(row, "in_production", _dec(item.get("qty")),
                       item.get("available_date"), "expected",
                       identity_status="missing")
            continue
        evidence = _text(item.get("evidence_status") or "unknown")
        qty = _dec(item.get("qty"))
        if evidence == "estimated":
            _merge_source(row, "production", evidence, item.get("observed_at"),
                          source_identity=item["_source_identity"])
            if qty is not None:
                row["in_production_estimated_qty"] = _qty(
                    (_dec(row["in_production_estimated_qty"]) or Decimal(0)) + qty)
            _add_stage(row, "in_production_estimated", qty,
                       item.get("available_date"), "expected",
                       source_identity=item["_source_identity"],
                       replay=item.get("_replay_count", 1) > 1)
            continue
        if evidence != "proven":
            _merge_source(row, "production", evidence, item.get("observed_at"),
                          "production_" + (evidence or "unknown"),
                          source_identity=item["_source_identity"])
            _mark_unknown(row, "production", "production_not_proven")
            continue
        _merge_source(row, "production", "proven", item.get("observed_at"),
                      source_identity=item["_source_identity"])
        _add_qty(row, "in_production_qty", "production", qty)
        _add_stage(row, "in_production", qty, item.get("available_date"),
                   "expected", source_identity=item["_source_identity"],
                   replay=item.get("_replay_count", 1) > 1)

    inv_effective, reconciliation["inventory"] = _dedupe_layer(
        inventory, layer="inventory",
        source_groups=(("source_ref",), ("snapshot_id",)),
        identity_groups=(
            ("source_ref",), ("snapshot_id",), ("item_code",), ("uom",),
            ("warehouse",), ("purpose",), ("tt_sku",), ("branch",)),
        payload_fields=("qty", "as_of", "source_status"))
    inventory_groups = defaultdict(list)
    for item in inv_effective:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        touched["inventory"].append(row)
        row.setdefault("_inventory_sources", set()).add("generic")
        if item.get("_conflict"):
            _merge_source(row, "inventory", "conflict",
                          source_identity=item["_source_identity"],
                          reason="source_payload_conflict")
            _mark_unknown(row, "inventory", "source_payload_conflict")
            for record in item["_records"]:
                _add_stage(row, "inventory", _dec(record.get("qty")),
                           record.get("as_of"), "observation",
                           source_identity=item["_source_identity"], conflict=True)
            continue
        if item.get("_identity_missing"):
            _merge_source(row, "inventory", "unknown",
                          item.get("as_of"), "source_identity_missing")
            _mark_unknown(row, "inventory", "source_identity_missing")
            _add_stage(row, "inventory", _dec(item.get("qty")),
                       item.get("as_of"), "observation",
                       identity_status="missing")
            continue
        inventory_groups[id(row)].append(item)
    for items in inventory_groups.values():
        row = _row_for(rows, items[0].get("item_code"),
                       items[0].get("uom"), items[0].get("warehouse"),
                       items[0].get("purpose"), items[0].get("branch"),
                       items[0].get("tt_sku"))
        statuses = {_text(item.get("source_status") or "known") for item in items}
        identities = {(_text(item.get("as_of")), _qty(item.get("qty")))
                      for item in items}
        for item in items:
            _merge_source(row, "inventory", _text(item.get("source_status")
                                                  or "known"),
                          item.get("as_of"),
                          source_identity=item["_source_identity"])
        if statuses != {"known"}:
            _merge_source(row, "inventory", "unavailable",
                          items[0].get("as_of"),
                          "inventory_source_unavailable")
            _mark_unknown(row, "inventory", "inventory_source_unavailable")
        elif len(identities) > 1:
            _merge_source(row, "inventory", "conflict", items[0].get("as_of"),
                          "multiple_inventory_snapshots")
            _mark_unknown(row, "inventory", "multiple_inventory_snapshots")
        else:
            item = items[0]
            qty = _dec(item.get("qty"))
            _add_qty(row, "inventory_qty", "inventory", qty)
            row["inventory_observed_qty"] = row["inventory_qty"]
            # Keep each observation's source identity as evidence without
            # adding the same row-level stock more than once.
            for observed_item in items:
                _add_stage(
                    row, "inventory", _dec(observed_item.get("qty")),
                    observed_item.get("as_of"), "observation",
                    source_identity=observed_item["_source_identity"],
                    replay=observed_item.get("_replay_count", 1) > 1)

    transit_rows = list(transit or ())
    collapsed = collapse_waybills(transit_rows)
    reconciliation["in_transit"] = {
        "layer": "in_transit", "input_rows": len(transit_rows),
        "identities": len({_waybill_identity(event) for event in collapsed}),
        "replayed": sum(max(0, int(event.get("_replay_count", 1)) - 1)
                        for event in collapsed),
        "conflicts": sum(1 for event in collapsed
                         if event.get("qty") is None
                         and event.get("reason")),
        "missing_identity": sum(1 for event in collapsed
                                if not any(_waybill_identity(event)[4:])),
        "effective_rows": len(collapsed),
    }
    for event in collapsed:
        row = _row_for(rows, event.get("item_code"), event.get("uom"),
                       event.get("warehouse"), event.get("purpose"),
                       event.get("branch"), event.get("tt_sku"))
        touched["in_transit"].append(row)
        qty = _dec(event.get("qty"))
        identity = event.get("source_identity") or _source_identity(
            WAYBILL_IDENTITY_FIELDS, _waybill_identity(event))
        if qty is None:
            reason = event.get("reason") or "in_transit_unknown"
            _merge_source(row, "in_transit", "unknown", event.get("observed_at"),
                          reason, source_identity=identity)
            _mark_unknown(row, "in_transit", reason)
            for record in event.get("candidates") or []:
                _add_stage(row, "in_transit", _dec(record.get("qty")),
                           record.get("available_date"), "expected",
                           source_identity=identity, conflict=True)
        else:
            _merge_source(row, "in_transit", "known", event.get("observed_at"),
                          source_identity=identity)
            _add_qty(row, "in_transit_qty", "in_transit", qty)
            _add_stage(row, "in_transit", qty, event.get("available_date"),
                       "expected", source_identity=identity,
                       replay=int(event.get("_replay_count", 1)) > 1)

    receipt_effective, reconciliation["receipt"] = _dedupe_layer(
        receipts, layer="receipt",
        source_groups=(("source_ref",), ("receipt_id",), ("shipment",)),
        identity_groups=(
            ("source_ref",), ("receipt_id",), ("shipment",), ("item_code",),
            ("uom",), ("warehouse",), ("purpose",), ("tt_sku",),
            ("branch",)),
        payload_fields=("qty", "signed_at", "pod_uploaded_at", "observed_at"))
    for receipt in receipt_effective:
        row = _row_for(rows, receipt.get("item_code"), receipt.get("uom"),
                       receipt.get("warehouse"), receipt.get("purpose"),
                       receipt.get("branch"), receipt.get("tt_sku"))
        touched["receipt"].append(row)
        if receipt.get("_conflict"):
            _merge_source(row, "receipt", "conflict",
                          source_identity=receipt["_source_identity"],
                          reason="source_payload_conflict")
            _mark_unknown(row, "receipt", "source_payload_conflict")
            for record in receipt["_records"]:
                evidence, signed = _pod_evidence(record)
                _add_stage(row, "received", _dec(record.get("qty")),
                           signed.isoformat() if signed else None, "actual",
                           source_identity=receipt["_source_identity"],
                           conflict=True)
            continue
        if receipt.get("_identity_missing"):
            _merge_source(row, "receipt", "unknown",
                          receipt.get("observed_at"), "source_identity_missing")
            _mark_unknown(row, "receipt", "source_identity_missing")
            evidence, signed = _pod_evidence(receipt)
            _add_stage(row, "received", _dec(receipt.get("qty")),
                       signed.isoformat() if signed else None, "actual",
                       identity_status="missing")
            continue
        evidence, signed = _pod_evidence(receipt)
        qty = _dec(receipt.get("qty"))
        if evidence == "proven" and qty is not None:
            _merge_source(row, "receipt", "proven", receipt.get("observed_at"),
                          source_identity=receipt["_source_identity"])
            _add_qty(row, "received_qty", "receipt", qty)
            row["receipt_basis"] = "signed_assumed"
            _add_stage(row, "received", qty, signed.isoformat(), "actual",
                       source_identity=receipt["_source_identity"],
                       replay=receipt.get("_replay_count", 1) > 1)
        else:
            reason = ("receipt_qty_unknown" if evidence == "proven"
                      else "receipt_" + evidence)
            _merge_source(row, "receipt", evidence, receipt.get("observed_at"),
                          reason, source_identity=receipt["_source_identity"])
            _mark_unknown(row, "receipt", reason)

    for code in approved_items or ():
        if not any(row["item_code"] == _text(code) for row in rows.values()):
            key = _key(code, "", "", "unknown")
            row = rows.setdefault(key, _row_base(key))
            row["unknown_reasons"].append("no_observed_supply_or_demand")
            row["coverage"] = "approved_item_without_evidence"

    for layer, row_list in touched.items():
        _contract_unknown(layer_status, layer, row_list)

    for row in rows.values():
        sources = row.pop("_inventory_sources", set())
        if len(sources) > 1:
            row["unknown_reasons"].append("multiple_inventory_sources")
            row["inventory_qty"] = None
            row["inventory_current_available_qty"] = None
        completed = _dec(row["po_completed_assumed_qty"])
        observed = _dec(row["inventory_observed_qty"])
        if observed is None:
            observed = _dec(row["inventory_qty"])
        if (completed is not None and completed > 0 and observed is not None
                and observed > 0 and row["inventory_inclusion_status"] == "unknown"):
            row["unknown_reasons"].append("possible_po_inventory_overlap")
        _finalize(row)
        if row["unknown_reasons"]:
            row["next_node"] = "manual_review_unknown"
        elif row["in_transit_qty"]:
            row["next_node"] = "in_transit_to_warehouse"
        elif row["in_production_qty"]:
            row["next_node"] = "production_to_complete"
        elif row["open_po_qty"]:
            row["next_node"] = "po_waiting_arrival"
        elif row["inventory_qty"]:
            row["next_node"] = "available_on_hand"
        else:
            row["next_node"] = "no_supply_evidence"

    ordered = [rows[key] for key in sorted(rows)]
    keys = [_key(row["item_code"], row["uom"], row["warehouse"], row["purpose"],
                 row["tt_sku"], row["branch"]) for row in ordered]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate_target_key")
    reason_counts = Counter(reason for row in ordered
                            for reason in row["unknown_reasons"])
    summary = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "rows": len(ordered),
        "by_purpose": dict(sorted(Counter(row["purpose"] for row in ordered).items())),
        "by_coverage": dict(sorted(Counter(row["coverage"] for row in ordered).items())),
        "attribution_distribution": dict(sorted(Counter(
            row["attribution_status"] or "none" for row in ordered).items())),
        "unknown_purpose_rows": sum(1 for row in ordered
                                    if row["purpose"] == "unknown"),
        "unknown_rows": sum(1 for row in ordered if row["unknown_reasons"]),
        "unknown_reason_distribution": dict(sorted(reason_counts.items())),
        "inventory_stale_rows": sum(1 for row in ordered
                                    if row["inventory_freshness"] == "stale"),
        "inventory_time_unknown_rows": sum(
            1 for row in ordered if not row["inventory_time_proven"]),
        "inventory_current_available_rows": sum(
            1 for row in ordered if row["inventory_current_available"]),
        "uom_mismatch_rows": sum(1 for row in ordered
                                 if row["attribution_status"] == "uom_mismatch"),
        "a_inactive_rows": sum(1 for row in ordered
                               if row["attribution_status"] == "a_inactive"),
        "order_blocked_rows": sum(1 for row in ordered
                                  if row["order_eligibility"] == "blocked"),
        "source_reconciliation": reconciliation,
        "layer_status": dict(sorted((layer_status or {}).items())),
        "duplicate_keys": 0,
        "forecast_connected": False,
        "netting_ready": False,
        "auto_order": False,
        "global_qty_total": None,
        "cross_layer_total": None,
        "note": ("SO balance is demand; stage dates stay separate; layers are "
                 "never summed; forecast not connected."),
    }
    result = {"rows": ordered, "summary": summary,
              "timeline": build_timeline(ordered, as_of=as_of)}
    if as_of is not None and max_age_seconds is not None:
        result["freshness"] = assess_freshness(
            ordered, as_of=as_of, max_age_seconds=max_age_seconds)
    return result


def build_timeline(rows, *, as_of=None):
    now = _aware(as_of) if as_of else None
    if now is None:
        now = datetime.now(timezone.utc)
    events = []
    for row in rows:
        stages = []
        alerts = set()
        for fragment in row.get("stage_quantities") or ():
            parsed = _aware(fragment.get("date"))
            if parsed and parsed < now:
                alerts.add("date_in_past")
            stages.append({"node": fragment["stage"], "qty": fragment["qty"],
                           "date": fragment.get("date"),
                           "date_raw": fragment.get("date_raw"),
                           "date_status": fragment.get("date_status"),
                           "date_kind": fragment.get("date_kind"),
                           "date_confidence": fragment.get("date_confidence"),
                           "source_identity": fragment.get("source_identity"),
                           "replay": fragment.get("replay", False),
                           "conflict": fragment.get("conflict", False),
                           "identity_status": fragment.get("identity_status")})
        events.append({
            "item_code": row["item_code"], "uom": row["uom"],
            "warehouse": row["warehouse"], "purpose": row["purpose"],
            "branch": row["branch"], "tt_sku": row["tt_sku"],
            "scope": row["scope"],
            "stages": stages, "next_node": row["next_node"],
            "alerts": sorted(alerts),
            "unknown_reasons": row["unknown_reasons"],
            "inventory_freshness": row["inventory_freshness"],
            "inventory_time_proven": row["inventory_time_proven"],
            "attribution_status": row["attribution_status"],
            "order_eligibility": row["order_eligibility"],
            "order_blockers": row["order_blockers"],
            "forecast_connected": False,
            "note": "forecast not connected; no suggested quantity",
        })
    return {"as_of": now.isoformat() if now else None, "rows": events,
            "forecast_connected": False}


def assess_freshness(rows, *, as_of, max_age_seconds):
    now = _aware(as_of)
    if now is None:
        raise ValueError("as_of must be an aware timestamp")
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) \
            or max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be a positive integer")
    out = []
    for row in rows:
        problems = []
        for source in row.get("sources") or ():
            observed = _aware(source.get("observed_at"))
            if observed is None:
                problems.append({"layer": source.get("layer"),
                                 "status": "unknown"})
            elif observed > now:
                problems.append({"layer": source.get("layer"),
                                 "status": "future"})
            elif (now - observed).total_seconds() > max_age_seconds:
                problems.append({"layer": source.get("layer"),
                                 "status": "stale"})
        out.append({"item_code": row["item_code"], "uom": row["uom"],
                    "warehouse": row["warehouse"], "purpose": row["purpose"],
                    "tt_sku": row["tt_sku"], "branch": row["branch"],
                    "problems": problems, "fresh": not problems})
    return {"rows": out,
            "summary": {"rows": len(out),
                        "fresh": sum(1 for r in out if r["fresh"]),
                        "stale": sum(1 for r in out
                                     if any(p["status"] == "stale" for p in r["problems"])),
                        "unknown": sum(1 for r in out
                                       if any(p["status"] == "unknown" for p in r["problems"])),
                        "future": sum(1 for r in out
                                      if any(p["status"] == "future" for p in r["problems"]))}}


def filter_rows(rows, *, scope=None, branch=None, purpose=None,
                warehouse=None):
    out = []
    for row in rows:
        if scope and row.get("scope") != scope:
            continue
        if branch and row["branch"] != branch:
            continue
        if purpose and row["purpose"] != purpose:
            continue
        if warehouse and row["warehouse"] != warehouse:
            continue
        out.append(row)
    return out
