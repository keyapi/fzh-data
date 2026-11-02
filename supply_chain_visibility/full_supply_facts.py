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

SCHEMA_VERSION = "full-supply-facts/v5"
RULE_VERSION = "2026-11-02.7"
IMPLEMENTATION_VERSION = "fzh.full_supply_facts@2026-11-02.7"
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


def _key(item_code, uom, warehouse, purpose, tt_sku=None, branch="",
         market="", product_form=""):
    return (_text(item_code), _text(uom), _text(warehouse), _purpose(purpose),
            _text(tt_sku), _text(branch), _text(market), _text(product_form))


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
    if not key[6]:
        reasons.append("market_unknown")
    if not key[7]:
        reasons.append("product_form_unknown")
    return {
        "item_code": key[0], "uom": key[1] or None, "warehouse": key[2],
        "purpose": purpose, "tt_sku": key[4] or None, "branch": key[5],
        "market": key[6] or None, "product_form": key[7] or None,
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
               identity_status=None, observed_at=None,
               inventory_inclusion_status="unknown"):
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
                "actual_at": (parsed.isoformat()
                              if parsed and date_kind == "actual" else None),
                "expected_at": (parsed.isoformat()
                                if parsed and date_kind == "expected" else None),
                "observed_at": _iso(observed_at),
                "overlap_status": "conflict" if conflict else "unknown",
                "inventory_inclusion_status": inventory_inclusion_status,
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


def _allocation_proof(records, *, quantity_field, payload_fields,
                      identity_groups):
    """Validate and deduplicate an explicit allocation ledger.

    Allocation metadata is a measurement contract, not an annotation beside
    the real quantity.  Every row must declare one stable allocation id, the
    measured quantity must equal ``allocated_qty``, every row must agree on
    the physical source capacity, and the deduplicated allocation sum may not
    exceed that capacity.
    """
    # ``line_id`` is often a normal source-line identity.  It becomes an
    # allocation id only when an allocation contract is otherwise present.
    allocation_fields = ("allocation_id", "allocated_qty",
                         "source_qty", "total_qty")
    if not any(any(record.get(field) not in (None, "")
                   for field in allocation_fields) for record in records):
        return {"status": "absent", "records": [], "replayed": 0}
    allocations = {}
    signatures = {}
    replay_counts = defaultdict(int)
    source_quantities = set()
    replayed = 0
    for record in records:
        allocation_id = _text(record.get("allocation_id")
                              or record.get("line_id"))
        allocated = _dec(record.get("allocated_qty"))
        declared = _dec(record.get("source_qty"))
        if declared is None:
            declared = _dec(record.get("total_qty"))
        measured = _dec(record.get(quantity_field))
        if (not allocation_id or allocated is None or declared is None
                or measured is None or measured != allocated):
            return {"status": "invalid", "records": [], "replayed": 0}
        target = tuple(
            next((_text(record.get(field)) for field in group
                  if _text(record.get(field))), "")
            for group in identity_groups)
        signature = (
            target,
            tuple(_payload_key(record.get(field)) for field in payload_fields),
            _payload_key(allocated), _payload_key(declared))
        if allocation_id in allocations:
            if signatures[allocation_id] != signature:
                return {"status": "invalid", "records": [], "replayed": 0}
            replayed += 1
            replay_counts[allocation_id] += 1
            continue
        item = dict(record)
        item[quantity_field] = _qty(allocated)
        item.update({"_allocation_id": allocation_id,
                     "_allocated_qty": _qty(allocated),
                     "_replay_count": 1})
        allocations[allocation_id] = item
        signatures[allocation_id] = signature
        source_quantities.add(declared)
    if len(source_quantities) != 1:
        return {"status": "invalid", "records": [], "replayed": 0}
    capacity = next(iter(source_quantities))
    total = sum((_dec(item["_allocated_qty"]) for item in allocations.values()),
                Decimal(0))
    if total > capacity:
        return {"status": "invalid", "records": [], "replayed": 0}
    for allocation_id, count in replay_counts.items():
        allocations[allocation_id]["_replay_count"] += count
    return {"status": "valid",
            "records": [allocations[key] for key in sorted(allocations)],
            "replayed": replayed, "source_qty": _qty(capacity),
            "allocated_qty": _qty(total)}


def _dedupe_layer(records, *, layer, source_groups, identity_groups,
                  payload_fields):
    """Collapse replay, surface conflicts and keep missing identity unknown.

    ``source_groups`` identify the physical document/line/batch and are grouped
    together with item_code/uom. Business dimensions (warehouse/branch/purpose/
    tt_sku) are target attribution, never source identity: a physical source
    cannot become two supplies merely by being claimed by two targets. A split
    is legal only with allocation_id + allocated_qty and a capacity proof.
    """
    groups = defaultdict(list)
    missing = []
    for record in records:
        source_values = tuple(
            next((_text(record.get(field)) for field in group
                  if _text(record.get(field))), "")
            for group in source_groups)
        target_values = tuple(
            next((_text(record.get(field)) for field in group
                  if _text(record.get(field))), "")
            for group in identity_groups)
        if not any(source_values):
            missing.append(record)
        else:
            physical = source_values + (_text(record.get("item_code")),
                                        _text(record.get("uom")))
            groups[physical].append((target_values, record))
    effective = []
    replayed = conflicts = splits = target_conflicts = 0
    for physical, entries in sorted(groups.items()):
        source_identity = {
            group[0]: value for group, value in
            zip(tuple(source_groups) + (("item_code",), ("uom",)),
                physical) if value}
        items = [record for _, record in entries]
        by_target = defaultdict(list)
        for target_values, record in entries:
            by_target[target_values].append(record)
        payloads = []
        for record in items:
            payload = tuple(_payload_key(record.get(field))
                            for field in payload_fields)
            if payload not in payloads:
                payloads.append(payload)
        allocation = _allocation_proof(
            items, quantity_field=payload_fields[0],
            payload_fields=payload_fields, identity_groups=identity_groups)
        if allocation["status"] == "valid":
            splits += len(allocation["records"])
            replayed += allocation["replayed"]
            for record in allocation["records"]:
                allocation_id = record["_allocation_id"]
                merged = dict(record)
                merged.update({
                    "_source_identity": dict(source_identity,
                                             allocation_id=allocation_id),
                    "_split": len(allocation["records"]) > 1})
                effective.append(merged)
            continue
        if allocation["status"] == "invalid":
            conflicts += 1
            if len(by_target) > 1:
                target_conflicts += 1
            for target_values, target_items in sorted(by_target.items()):
                merged = dict(target_items[0])
                merged.update({
                    "_conflict": True,
                    "_conflict_reason": "source_allocation_conflict",
                    "_records": target_items,
                    "_conflict_candidates": items,
                    "_source_identity": source_identity})
                effective.append(merged)
            continue
        if len(by_target) > 1:
            conflicts += 1
            target_conflicts += 1
            for target_values, target_items in sorted(by_target.items()):
                merged = dict(target_items[0])
                merged.update({
                    "_conflict": True,
                    "_conflict_reason": "source_target_conflict",
                    "_records": target_items,
                    "_conflict_candidates": items,
                    "_source_identity": source_identity})
                effective.append(merged)
            continue
        if len(payloads) > 1:
            conflicts += 1
            target_values, target_items = next(iter(by_target.items()))
            merged = dict(target_items[0])
            merged.update({
                "_conflict": True,
                "_conflict_reason": "source_payload_conflict",
                "_records": target_items,
                "_conflict_candidates": items,
                "_source_identity": source_identity})
            effective.append(merged)
            continue
        target_values, target_items = next(iter(by_target.items()))
        if len(target_items) > 1:
            replayed += len(target_items) - 1
        merged = dict(target_items[0])
        merged.update({
            "_source_identity": dict(source_identity,
                                     **_source_identity(
                                         tuple(group[0] for group in
                                               identity_groups),
                                         target_values)),
            "_replay_count": len(target_items)})
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
        "target_conflicts": target_conflicts,
        "split_allocations": splits,
        "missing_identity": len(missing),
        "effective_rows": len(effective),
    }


def _row_for(rows, item, uom, warehouse, purpose, branch="", tt_sku=None,
             market="", product_form=""):
    """Exact-key attach for non-authoritative sources; never fill identity."""
    key = _key(item, uom, warehouse, purpose, tt_sku, branch,
               market, product_form)
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
                   item.get("branch"), item.get("market"),
                   item.get("product_form"))
        if key[0] and (key[4] or key[5]):
            identities.add(key)
    return identities


def _position_source_identities(row):
    identities = set()
    for source in row.get("sources") or ():
        if source.get("layer") != "dn_line":
            continue
        identity = source.get("source_identity")
        if not identity:
            continue
        values = tuple(sorted((str(key), _text(value))
                              for key, value in identity.items()
                              if value not in (None, "")))
        if values:
            identities.add(values)
    return identities


def _position_tranche_identity(tranche):
    delivery_note = _text(tranche.get("delivery_note"))
    dn_item = _text(tranche.get("dn_item")
                    or tranche.get("delivery_note_item"))
    if not delivery_note or not dn_item:
        return None
    return (_text(tranche.get("instance")), delivery_note, dn_item)


def _position_tranche_payload(tranche):
    return (_qty(tranche.get("qty"), signed=True),
            _text(tranche.get("bucket")))


def _position_tranche_map(row):
    mapped = {}
    for tranche in row.get("_position_tranches") or ():
        identity = _position_tranche_identity(tranche)
        if identity is None:
            return None
        payload = _position_tranche_payload(tranche)
        if identity in mapped and _position_tranche_payload(mapped[identity]) != payload:
            return None
        mapped.setdefault(identity, tranche)
    return mapped or None


def _position_totals(tranches):
    totals = {"dn_net_qty": Decimal(0),
              "po_completed_assumed_qty": Decimal(0),
              "open_po_qty": Decimal(0), "unresolved_qty": Decimal(0)}
    for tranche in tranches:
        qty = _dec(tranche.get("qty"), signed=True)
        bucket = _text(tranche.get("bucket"))
        if qty is None or bucket not in totals or bucket == "dn_net_qty":
            return None
        totals["dn_net_qty"] += qty
        totals[bucket] += qty
    return totals


def _position_tranches_cover(row, mapped):
    totals = _position_totals(mapped.values()) if mapped else None
    if totals is None:
        return False
    for field, value in totals.items():
        actual = _dec(row.get(field), signed=(field == "dn_net_qty"))
        if actual is None or actual != value:
            return False
    return True


def _position_tranche_sequence_covers(row, tranches):
    totals = _position_totals(tranches) if tranches else None
    if totals is None:
        return False
    return all(
        _dec(row.get(field), signed=(field == "dn_net_qty")) == value
        for field, value in totals.items())


def _rebuild_position_from_tranches(row, mapped):
    totals = _position_totals(mapped.values())
    if totals is None:
        raise ValueError("position tranche coverage lost")
    for field, value in totals.items():
        row[field] = _qty(value, signed=(field == "dn_net_qty"))
    row["_position_tranches"] = [mapped[key] for key in sorted(mapped)]
    row["stage_quantities"] = [
        fragment for fragment in row.get("stage_quantities") or ()
        if fragment.get("stage") not in ("po_completed_assumed", "po_open")]
    for identity, tranche in sorted(mapped.items()):
        bucket = _text(tranche.get("bucket"))
        stage = {"po_completed_assumed_qty": "po_completed_assumed",
                 "open_po_qty": "po_open"}.get(bucket)
        if stage:
            _add_stage(
                row, stage, _dec(tranche.get("qty"), signed=True),
                tranche.get("_position_as_of") if stage == "po_completed_assumed"
                else None,
                "observation" if stage == "po_completed_assumed" else None,
                source_identity={"instance": identity[0],
                                 "delivery_note": identity[1],
                                 "dn_item": identity[2]})


def _merge_unique(existing, incoming):
    seen = {}
    for item in list(existing or ()) + list(incoming or ()):
        seen[json.dumps(item, sort_keys=True, default=str)] = item
    return [seen[key] for key in sorted(seen)]


def _merge_position_evidence(target, source):
    target["sources"] = _merge_unique(target.get("sources"),
                                      source.get("sources"))
    target["stage_quantities"] = _merge_unique(
        target.get("stage_quantities"), source.get("stage_quantities"))
    target["unknown_reasons"] = sorted(set(
        list(target.get("unknown_reasons") or ())
        + list(source.get("unknown_reasons") or ())))
    layers = set(target.get("_unknown_layers") or ())
    layers |= set(source.get("_unknown_layers") or ())
    if layers:
        target["_unknown_layers"] = layers


def _merge_position_quantities(target, source):
    left = _dec(target.get("dn_net_qty"), signed=True)
    right = _dec(source.get("dn_net_qty"), signed=True)
    target["dn_net_qty"] = (None if left is None or right is None
                            else _qty(left + right, signed=True))
    for field in ("po_completed_assumed_qty", "open_po_qty", "unresolved_qty"):
        left = _dec(target.get(field))
        right = _dec(source.get(field))
        target[field] = (None if left is None or right is None
                         else _qty(left + right))


def _enrich_blank_position_rows(rows, abc_rows):
    """Fill blank DN/PO identity only if the *complete* B candidate set agrees.

    When a rekey would land on an existing row, never overwrite it: proven
    distinct sources are summed, an exact replay is deduplicated, and an
    unprovable collision keeps both rows marked for review.
    """
    identities = _abc_identities(abc_rows)
    for key, row in list(rows.items()):
        if row["purpose"] not in VALID_PURPOSES:
            continue
        identity_complete = (bool(row["tt_sku"])
                             and (row["purpose"] != "branch"
                                  or bool(row["branch"]))
                             and bool(row.get("market"))
                             and bool(row.get("product_form")))
        if identity_complete:
            continue
        matches = [
            identity for identity in identities
            if identity[0] == key[0] and identity[1] == key[1]
            and identity[2] == key[2] and identity[3] == key[3]
            and (not row["tt_sku"] or not identity[4]
                 or identity[4] == row["tt_sku"])
            and (not row["branch"] or not identity[5]
                 or identity[5] == row["branch"])
            and (not row.get("market") or not identity[6]
                 or identity[6] == row.get("market"))
            and (not row.get("product_form") or not identity[7]
                 or identity[7] == row.get("product_form"))]
        if len(matches) == 1:
            identity = matches[0]
            original_tt_sku = row["tt_sku"]
            original_branch = row["branch"]
            original_market = row.get("market")
            original_product_form = row.get("product_form")
            original_reasons = list(row["unknown_reasons"])
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
            if not row.get("market") and identity[6]:
                row["market"] = identity[6]
                row["unknown_reasons"] = [
                    reason for reason in row["unknown_reasons"]
                    if reason != "market_unknown"]
            if not row.get("product_form") and identity[7]:
                row["product_form"] = identity[7]
                row["unknown_reasons"] = [
                    reason for reason in row["unknown_reasons"]
                    if reason != "product_form_unknown"]
            attached = _key(row["item_code"], row["uom"], row["warehouse"],
                            row["purpose"], row["tt_sku"], row["branch"],
                            row.get("market"), row.get("product_form"))
            if attached == key:
                continue
            if attached not in rows:
                del rows[key]
                rows[attached] = row
                continue
            existing = rows[attached]
            blank_tranches = _position_tranche_map(row)
            existing_tranches = _position_tranche_map(existing)
            overlap = (set(blank_tranches or ())
                       & set(existing_tranches or ()))
            payload_conflict = any(
                _position_tranche_payload(blank_tranches[identity])
                != _position_tranche_payload(existing_tranches[identity])
                for identity in overlap)
            if payload_conflict:
                row["tt_sku"] = original_tt_sku
                row["branch"] = original_branch
                row["market"] = original_market
                row["product_form"] = original_product_form
                row["unknown_reasons"] = original_reasons
                for target in (row, existing):
                    _mark_unknown(target, "dn_po",
                                  "dn_physical_payload_conflict")
                    target["unresolved_qty"] = None
                continue
            if (blank_tranches and existing_tranches
                    and _position_tranches_cover(row, blank_tranches)
                    and _position_tranches_cover(existing, existing_tranches)):
                union = dict(existing_tranches)
                for identity, tranche in blank_tranches.items():
                    union.setdefault(identity, tranche)
                _merge_position_evidence(existing, row)
                _rebuild_position_from_tranches(existing, union)
                del rows[key]
                continue
            blank_sources = _position_source_identities(row)
            existing_sources = _position_source_identities(existing)
            same_payload = all(
                row.get(field) == existing.get(field)
                for field in ("dn_net_qty", "po_completed_assumed_qty",
                              "open_po_qty", "unresolved_qty"))
            if (blank_sources and existing_sources
                    and blank_sources == existing_sources and same_payload):
                _merge_position_evidence(existing, row)
                del rows[key]
            elif (blank_sources and existing_sources
                  and not (blank_sources & existing_sources)):
                _merge_position_evidence(existing, row)
                _merge_position_quantities(existing, row)
                del rows[key]
            else:
                # Cannot prove distinct sources: keep both rows, lose nothing.
                row["tt_sku"] = original_tt_sku
                row["branch"] = original_branch
                row["market"] = original_market
                row["product_form"] = original_product_form
                row["unknown_reasons"] = original_reasons
                for target in (row, existing):
                    target["unknown_reasons"] = sorted(set(
                        target["unknown_reasons"]
                        + ["abc_identity_key_conflict"]))
        elif len(matches) > 1:
            row["unknown_reasons"].append("target_key_ambiguous")


WAYBILL_IDENTITY_FIELDS = ("delivery_note", "delivery_note_item", "item_code",
                           "uom", "warehouse", "branch", "purpose", "tt_sku")
WAYBILL_PHYSICAL_FIELDS = ("delivery_note", "delivery_note_item", "item_code",
                           "uom")
WAYBILL_TARGET_FIELDS = ("warehouse", "branch", "purpose", "tt_sku")


def _waybill_identity(event):
    values = []
    for field in WAYBILL_IDENTITY_FIELDS:
        if field == "delivery_note_item":
            values.append(_text(event.get("delivery_note_item")
                                or event.get("dn_item")))
        else:
            values.append(_text(event.get(field)))
    return tuple(values)


def _waybill_physical_identity(event):
    values = []
    for field in WAYBILL_PHYSICAL_FIELDS:
        if field == "delivery_note_item":
            values.append(_text(event.get("delivery_note_item")
                                or event.get("dn_item")))
        else:
            values.append(_text(event.get(field)))
    values.append(_text(event.get("waybill") or event.get("shipment")))
    return tuple(values)


def _explicit_target_identities(identities):
    """Candidates that fill every target dimension that actually varies."""
    varying = [
        index for index in range(len(WAYBILL_TARGET_FIELDS))
        if len({identity[4 + index] for identity in identities}) > 1]
    return sorted(
        identity for identity in identities
        if all(identity[4 + index] for index in varying))


def _event_sort_key(event):
    return (_text(event.get("waybill") or event.get("shipment")),
            json.dumps(event, sort_keys=True, ensure_ascii=False, default=str))


def collapse_waybills(events: Iterable[dict]) -> list[dict]:
    """Dedupe logistics by full business identity, not DN×item×UOM only."""
    raw_events = list(events)
    raw_physical_groups = defaultdict(list)
    for event in raw_events:
        raw_physical_groups[_waybill_physical_identity(event)].append(event)
    events = []
    invalid_allocations = set()
    target_groups = tuple((field,) for field in WAYBILL_TARGET_FIELDS)
    for physical, group in sorted(raw_physical_groups.items()):
        allocation = _allocation_proof(
            group, quantity_field="qty",
            payload_fields=("qty", "available_date", "observed_at",
                            "source_status"),
            identity_groups=target_groups)
        if allocation["status"] == "valid":
            events.extend(allocation["records"])
        else:
            events.extend(group)
            if allocation["status"] == "invalid":
                invalid_allocations.add(physical)
    by_identity = defaultdict(list)
    physical_groups = defaultdict(list)
    for event in events:
        by_identity[_waybill_identity(event)].append(event)
        physical_groups[_waybill_physical_identity(event)].append(event)
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
            if group and all(item.get("_allocation_id") for item in group):
                for item in group:
                    kept = dict(item)
                    kept["source_identity"] = dict(
                        identity_dict, allocation_id=item["_allocation_id"])
                    out.append(kept)
                continue
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
    # One physical shipment/line cannot be claimed by several targets merely
    # because warehouse/branch/purpose differ. Keep the observation but do not
    # choose one; a capacity-proven allocation is the only legal split.
    for physical, group_events in sorted(physical_groups.items()):
        identities = {_waybill_identity(event) for event in group_events}
        waybill = physical[-1]
        if physical in invalid_allocations:
            out = [item for item in out
                   if not (_text(item.get("waybill") or item.get("shipment"))
                           == waybill
                           and _waybill_identity(item) in identities)]
            base = sorted(group_events, key=_event_sort_key)[0]
            base_identity = _waybill_identity(base)
            merged = dict(base)
            merged.update({
                "qty": None, "qty_status": "unknown",
                "reason": "source_allocation_conflict",
                "candidates": [dict(item) for item in group_events],
                "source_identity": _source_identity(
                    WAYBILL_IDENTITY_FIELDS, base_identity),
                "_replay_count": 1})
            out.append(merged)
            continue
        if len(identities) <= 1:
            continue
        if physical not in invalid_allocations and all(
                event.get("_allocation_id") for event in group_events):
            continue
        explicit = _explicit_target_identities(identities)
        if not explicit:
            continue
        out = [item for item in out
               if not (_text(item.get("waybill") or item.get("shipment"))
                       == waybill
                       and _waybill_identity(item) in identities)]
        base = sorted(group_events, key=_event_sort_key)[0]
        merged = dict(base)
        merged.update({
            "qty": None, "qty_status": "unknown",
            "reason": "multi_assignment_allocation_unknown",
            "candidates": [_source_identity(WAYBILL_IDENTITY_FIELDS, item)
                           for item in explicit],
            "source_identity": _source_identity(
                WAYBILL_IDENTITY_FIELDS, _waybill_identity(base)),
            "_replay_count": 1})
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
    row.pop("_position_tranches", None)
    fragments = row["stage_quantities"]
    identities = defaultdict(set)
    for fragment in fragments:
        identity = fragment.get("source_identity")
        if identity:
            identities[json.dumps(identity, sort_keys=True, default=str)].add(
                fragment.get("stage"))
    overlap_keys = {key for key, stages in identities.items() if len(stages) > 1}
    for fragment in fragments:
        identity = fragment.get("source_identity")
        if identity and json.dumps(identity, sort_keys=True,
                                   default=str) in overlap_keys:
            fragment["overlap_status"] = "same_identity_cross_stage"
    if overlap_keys:
        row["unknown_reasons"].append("same_identity_cross_stage")
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
    reason = ("source_business_partial" if status == "partial"
              else "source_contract_incomplete")
    for row in rows:
        _merge_source(row, layer, status, reason=reason)
        if layer == "dn_po":
            row["source_status"]["dn_po"] = "partial"
            continue
        _mark_unknown(row, layer, reason)
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
        source_report = position_result.get("report") or {}
        versions = source_report.get("source_versions") or {}
        key = _key(pos.get("item_code"), pos.get("uom"), pos.get("warehouse"),
                   pos.get("purpose"), pos.get("tt_sku"), pos.get("branch"),
                   pos.get("market"), pos.get("product_form"))
        payload = (pos.get("dn_net_qty"), pos.get("po_completed_assumed_qty"),
                   pos.get("open_po_qty"), pos.get("unresolved_qty"))
        if key in rows:
            existing_row = rows[key]
            existing = tuple(existing_row.get(field) for field in
                             ("dn_net_qty", "po_completed_assumed_qty",
                              "open_po_qty", "unresolved_qty"))
            if existing != tuple(_qty(value, signed=(index == 0))
                                 for index, value in enumerate(payload)):
                raise ValueError("duplicate_target_key")
            incoming = [dict(tranche, _position_as_of=pos.get("as_of"))
                        for tranche in pos.get("tranches") or ()]
            existing_map = _position_tranche_map(existing_row)
            incoming_probe = {"_position_tranches": incoming}
            incoming_map = _position_tranche_map(incoming_probe)
            if ((existing_map is None) != (incoming_map is None)
                    or (existing_map is not None
                        and (set(existing_map) != set(incoming_map)
                             or any(_position_tranche_payload(existing_map[item])
                                    != _position_tranche_payload(incoming_map[item])
                                    for item in existing_map)))):
                raise ValueError("duplicate_target_key_source_conflict")
            for tranche in pos.get("tranches") or ():
                _merge_source(
                    existing_row, "dn_line", "known",
                    versions.get("observed_at") or versions.get("as_of"),
                    source_identity={
                        "instance": tranche.get("instance"),
                        "delivery_note": tranche.get("delivery_note"),
                        "dn_item": tranche.get("dn_item")},
                    evidence={"creation": tranche.get("creation"),
                              "po_code": tranche.get("po_code"),
                              "bucket": tranche.get("bucket"),
                              "qty": _qty(tranche.get("qty"), signed=True)})
            continue
        row = rows.setdefault(key, _row_base(key))
        touched["dn_po"].append(row)
        row["_position_tranches"] = [
            dict(tranche, _position_as_of=pos.get("as_of"))
            for tranche in pos.get("tranches") or ()]
        row["dn_net_qty"] = _qty(pos.get("dn_net_qty"), signed=True)
        row["po_completed_assumed_qty"] = _qty(pos.get("po_completed_assumed_qty"))
        row["open_po_qty"] = _qty(pos.get("open_po_qty"))
        row["unresolved_qty"] = _qty(pos.get("unresolved_qty"))
        if any(pos.get(f) is None for f in
               ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty")):
            _mark_unknown(row, "dn_po", "dn_po_quantity_unknown")
        if "po_in_snapshot" in (pos.get("reasons") or []):
            row["inventory_inclusion_status"] = "po_in_snapshot"
        # Position.as_of is calculation time, not the time the DN was observed.
        _merge_source(row, "dn_po", "known",
                      versions.get("observed_at") or versions.get("as_of"))
        for tranche in pos.get("tranches") or []:
            physical_identity = {
                "instance": tranche.get("instance"),
                "delivery_note": tranche.get("delivery_note"),
                "dn_item": tranche.get("dn_item")}
            _merge_source(
                row, "dn_line", "known",
                versions.get("observed_at") or versions.get("as_of"),
                source_identity=physical_identity,
                evidence={"creation": tranche.get("creation"),
                          "po_code": tranche.get("po_code"),
                          "bucket": tranche.get("bucket"),
                          "qty": _qty(tranche.get("qty"), signed=True)})
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
        tranche_map = _position_tranche_map(row)
        raw_tranches = row.get("_position_tranches") or ()
        measured_tranches = bool(raw_tranches) and all(
            _dec(tranche.get("qty"), signed=True) is not None
            and _text(tranche.get("bucket")) in {
                "po_completed_assumed_qty", "open_po_qty", "unresolved_qty"}
            for tranche in raw_tranches)
        # Tranches are the physical DN ledger.  When the aggregate was built
        # from exact replays, rebuild it from the physical union; when the
        # tranches conflict or do not explain the aggregate, retain sources
        # but do not publish a numeric DN/PO total.
        if measured_tranches and tranche_map and (
                _position_tranches_cover(row, tranche_map)
                or (len(raw_tranches) > len(tranche_map)
                    and _position_tranche_sequence_covers(row, raw_tranches))):
            _rebuild_position_from_tranches(row, tranche_map)
        elif measured_tranches:
            reason = ("dn_physical_payload_conflict" if tranche_map is None
                      else "dn_tranche_coverage_mismatch")
            _mark_unknown(row, "dn_po", reason)
            row["unresolved_qty"] = None
        else:
            _add_stage(row, "po_completed_assumed",
                       _dec(pos.get("po_completed_assumed_qty")),
                       pos.get("as_of"), "observation")
            _add_stage(row, "po_open", _dec(pos.get("open_po_qty")), None, None)

    # A/B identity is applied before any non-authoritative source, so order
    # cannot make a blank row adopt the first arriving branch.
    _enrich_blank_position_rows(rows, abc_rows)

    abc_seen = {}
    abc_conflicted = set()
    for item in abc_rows:
        key = _key(item.get("item_code"), item.get("uom"), item.get("warehouse"),
                   item.get("purpose"), item.get("tt_sku"), item.get("branch"),
                   item.get("market"), item.get("product_form"))
        row = rows.setdefault(key, _row_base(key))
        touched["inventory"].append(row)
        row.setdefault("_inventory_sources", set()).add("abc")
        payload = (item.get("inventory_observed_qty"), item.get("inventory_qty"),
                   item.get("inventory_current_available_qty"),
                   item.get("inventory_as_of_raw"),
                   item.get("attribution_status"))
        conflict = (key in abc_conflicted
                    or (key in abc_seen and abc_seen[key] != payload))
        if conflict:
            abc_conflicted.add(key)
        else:
            abc_seen.setdefault(key, payload)
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
        row["inventory_observed_qty"] = (
            None if conflict else _qty(item.get("inventory_observed_qty")))
        row["inventory_qty"] = (
            None if conflict else _qty(item.get("inventory_qty")))
        row["inventory_current_available_qty"] = (
            None if conflict else _qty(item.get("inventory_current_available_qty")))
        status = "conflict" if conflict else _text(
            item.get("source_status") or "unknown")
        reason = ("abc_inventory_key_conflict" if conflict
                  else ("" if inventory_qty is not None
                        else "inventory_not_attributed"))
        _merge_source(row, "inventory", status, item.get("inventory_as_of"),
                      reason,
                      source_identity={"source_ref": item.get("source_ref"),
                                       "item_code": item.get("item_code"),
                                       "pool": item.get("pool")})
        if observed is not None:
            _add_stage(row, "inventory", observed, item.get("inventory_as_of_raw"),
                       "observation",
                       source_identity={"source_ref": item.get("source_ref")})
        for reason_text in item.get("reasons") or []:
            if reason_text not in row["unknown_reasons"]:
                row["unknown_reasons"].append(reason_text)
        if item.get("coverage") and item.get("coverage") != "abc_inventory":
            row["coverage"] = item.get("coverage")
        if (not conflict and current is None and status == "known"
                and observed is not None):
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
                       item.get("branch"), item.get("tt_sku"),
                       item.get("market"), item.get("product_form"))
        touched["so_demand"].append(row)
        if item.get("_conflict"):
            reason = item.get("_conflict_reason") or "source_payload_conflict"
            _merge_source(row, "so_demand", "conflict",
                          source_identity=item["_source_identity"],
                          reason=reason)
            _mark_unknown(row, "so_demand", reason)
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
                   replay=item.get("_replay_count", 1) > 1,
                   observed_at=item.get("observed_at"))

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
                       item.get("branch"), item.get("tt_sku"),
                       item.get("market"), item.get("product_form"))
        touched["production"].append(row)
        if item.get("_conflict"):
            reason = item.get("_conflict_reason") or "source_payload_conflict"
            _merge_source(row, "production", "conflict",
                          source_identity=item["_source_identity"],
                          reason=reason)
            _mark_unknown(row, "production", reason)
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
                       replay=item.get("_replay_count", 1) > 1,
                       observed_at=item.get("observed_at"))
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
                   replay=item.get("_replay_count", 1) > 1,
                   observed_at=item.get("observed_at"))

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
                       item.get("branch"), item.get("tt_sku"),
                       item.get("market"), item.get("product_form"))
        touched["inventory"].append(row)
        row.setdefault("_inventory_sources", set()).add("generic")
        if item.get("_conflict"):
            reason = item.get("_conflict_reason") or "source_payload_conflict"
            _merge_source(row, "inventory", "conflict",
                          source_identity=item["_source_identity"],
                          reason=reason)
            _mark_unknown(row, "inventory", reason)
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
        inventory_groups[(id(row), item.get("_allocation_id"))].append(item)
    for items in inventory_groups.values():
        row = _row_for(rows, items[0].get("item_code"),
                       items[0].get("uom"), items[0].get("warehouse"),
                       items[0].get("purpose"), items[0].get("branch"),
                       items[0].get("tt_sku"), items[0].get("market"),
                       items[0].get("product_form"))
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
                    replay=observed_item.get("_replay_count", 1) > 1,
                    observed_at=observed_item.get("as_of"),
                    inventory_inclusion_status="included")

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
                       event.get("branch"), event.get("tt_sku"),
                       event.get("market"), event.get("product_form"))
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
                       replay=int(event.get("_replay_count", 1)) > 1,
                       observed_at=event.get("observed_at"),
                       inventory_inclusion_status="not_included")

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
                       receipt.get("branch"), receipt.get("tt_sku"),
                       receipt.get("market"), receipt.get("product_form"))
        touched["receipt"].append(row)
        if receipt.get("_conflict"):
            reason = (receipt.get("_conflict_reason")
                      or "source_payload_conflict")
            _merge_source(row, "receipt", "conflict",
                          source_identity=receipt["_source_identity"],
                          reason=reason)
            _mark_unknown(row, "receipt", reason)
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
                           replay=receipt.get("_replay_count", 1) > 1,
                           observed_at=receipt.get("observed_at"),
                           inventory_inclusion_status="unknown")
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
                 row["tt_sku"], row["branch"], row.get("market"),
                 row.get("product_form")) for row in ordered]
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
                           "actual_at": fragment.get("actual_at"),
                           "expected_at": fragment.get("expected_at"),
                           "observed_at": fragment.get("observed_at"),
                           "overlap_status": fragment.get("overlap_status"),
                           "inventory_inclusion_status": fragment.get(
                               "inventory_inclusion_status"),
                           "source_identity": fragment.get("source_identity"),
                           "replay": fragment.get("replay", False),
                           "conflict": fragment.get("conflict", False),
                           "identity_status": fragment.get("identity_status")})
        events.append({
            "item_code": row["item_code"], "uom": row["uom"],
            "warehouse": row["warehouse"], "purpose": row["purpose"],
            "branch": row["branch"], "tt_sku": row["tt_sku"],
            "market": row.get("market"),
            "product_form": row.get("product_form"),
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
        sources = list(row.get("sources") or ())
        if not sources:
            problems.append({"layer": None, "status": "unknown"})
        for source in sources:
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
                    "market": row.get("market"),
                    "product_form": row.get("product_form"),
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
