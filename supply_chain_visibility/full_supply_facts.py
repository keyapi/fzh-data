# -*- coding: utf-8 -*-
"""Full supply facts v6: stage-detail facts plus a compatible target summary.

``build_full_supply_facts`` keeps the historical target-grained rows (now
published as ``supply_target_summary``) and adds ``stage_rows`` at
item×uom×warehouse×purpose×tt_sku×branch×stage×doc_line/batch grain for the
primary ``full_supply_facts`` dataset.

Rules:
* only open_po / waiting_shipment / in_transit / received / on_hand are stages;
  open_po is reconciliation only and never additive supply;
* signed-but-not-Tongtool-received is in_transit with signed_at; received needs
  a proven Tongtool receipt time; on_hand needs a proven inventory snapshot;
* observed_at / eta / available_at / signed_at / received_at are separate and
  are never substituted for one another; naive/date-only times are not UTC;
* one physical batch has at most one counted_as_supply current stage; cross
  stage evidence is grouped by batch identity and open_po is never counted;
* purpose supports branch/fba/cg; branch has one owner, FBA never binds a
  branch, CG is never copied into branch/FBA, stale CG keeps its observation
  but is not nettable;
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

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

SCHEMA_VERSION = "full-supply-facts/v7"
RULE_VERSION = "2026-11-03.3"
IMPLEMENTATION_VERSION = "fzh.full_supply_facts@2026-11-03.3"
QUANTITY_SCALE = 6

VALID_PURPOSES = ("branch", "fba", "cg")
STAGE_VALUES = ("open_po", "waiting_shipment", "in_transit", "received",
                "on_hand")
STAGE_RANK = {"open_po": 0, "waiting_shipment": 1, "in_transit": 2,
              "received": 3, "on_hand": 4}
FRAGMENT_STAGE = {
    "po_open": "open_po",
    "po_completed_assumed": "waiting_shipment",
    "in_production": "waiting_shipment",
    "in_production_estimated": "waiting_shipment",
    "in_transit": "in_transit",
    "received": "received",
    "inventory": "on_hand",
}
QTY_FIELDS = ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty",
              "unresolved_qty", "so_open_qty", "in_production_qty",
              "in_production_estimated_qty", "inventory_qty",
              "inventory_observed_qty", "inventory_current_available_qty",
              "in_transit_qty", "received_qty", "signed_pending_qty")
LAYER_FIELDS = {
    "dn_po": ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty"),
    "so_demand": ("so_open_qty",),
    "production": ("in_production_qty",),
    "production_estimated": ("in_production_estimated_qty",),
    "inventory": ("inventory_qty", "inventory_current_available_qty"),
    "in_transit": ("in_transit_qty",),
    "receipt": ("received_qty", "signed_pending_qty"),
}
_STATUS_RANK = {
    "known": 0, "proven": 0, "estimated": 0, "ok": 0,
    "partial": 1, "pod_only": 1, "signed_pending": 1,
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
    scope = {"branch": "in_house", "fba": "external_fba",
             "cg": "cg_pool"}.get(purpose, "unknown")
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
               inventory_inclusion_status="unknown", signed_at=None,
               received_at=None):
    """Append a quantity/date fragment only; aggregates are handled separately."""
    if qty is None:
        return
    parsed, raw, status = _time_parts(date_value)
    signed_parsed, signed_raw, signed_status = _time_parts(signed_at)
    received_parsed, received_raw, received_status = _time_parts(received_at)
    observed_parsed, observed_raw, observed_status = _time_parts(observed_at)
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
                "observed_at": (observed_parsed.isoformat()
                                if observed_parsed else None),
                "observed_at_raw": observed_raw,
                "observed_at_time_status": observed_status,
                "signed_at": signed_parsed.isoformat() if signed_parsed else None,
                "signed_at_raw": signed_raw,
                "signed_at_time_status": signed_status,
                "received_at": (received_parsed.isoformat()
                                if received_parsed else None),
                "received_at_raw": received_raw,
                "received_at_time_status": received_status,
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
                identity = dict(source_identity, allocation_id=allocation_id)
                allocated = _dec(record.get("allocated_qty"))
                declared = _dec(record.get("source_qty"))
                if declared is None:
                    declared = _dec(record.get("total_qty"))
                if allocated is not None:
                    identity["allocated_qty"] = _qty(allocated)
                if declared is not None:
                    identity["source_qty"] = _qty(declared)
                batch = _text(record.get("batch_id"))
                if batch:
                    identity["batch_id"] = batch
                merged.update({
                    "_source_identity": identity,
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
                identity = dict(source_identity)
                batch = _text(target_items[0].get("batch_id"))
                if batch:
                    identity["batch_id"] = batch
                merged.update({
                    "_conflict": True,
                    "_conflict_reason": "source_target_conflict",
                    "_records": target_items,
                    "_conflict_candidates": items,
                    "_source_identity": identity})
                effective.append(merged)
            continue
        if len(payloads) > 1:
            conflicts += 1
            target_values, target_items = next(iter(by_target.items()))
            merged = dict(target_items[0])
            identity = dict(source_identity)
            batch = _text(target_items[0].get("batch_id"))
            if batch:
                identity["batch_id"] = batch
            merged.update({
                "_conflict": True,
                "_conflict_reason": "source_payload_conflict",
                "_records": target_items,
                "_conflict_candidates": items,
                "_source_identity": identity})
            effective.append(merged)
            continue
        target_values, target_items = next(iter(by_target.items()))
        if len(target_items) > 1:
            replayed += len(target_items) - 1
        merged = dict(target_items[0])
        identity = dict(source_identity, **_source_identity(
            tuple(group[0] for group in identity_groups), target_values))
        batch = _text(target_items[0].get("batch_id"))
        if batch:
            identity["batch_id"] = batch
        merged.update({
            "_source_identity": identity,
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
            identity = {"instance": identity[0],
                        "delivery_note": identity[1],
                        "dn_item": identity[2]}
            if _text(tranche.get("batch_id")):
                identity["batch_id"] = _text(tranche.get("batch_id"))
            _add_stage(
                row, stage, _dec(tranche.get("qty"), signed=True),
                tranche.get("_position_as_of") if stage == "po_completed_assumed"
                else None,
                "observation" if stage == "po_completed_assumed" else None,
                source_identity=identity)


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
        batch = _text(items[0].get("batch_id"))
        if batch:
            identity_dict["batch_id"] = batch
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
        if _text(base.get("batch_id")):
            merged["source_identity"]["batch_id"] = _text(base.get("batch_id"))
        out.append(merged)
    return sorted(out, key=lambda item: (
        _waybill_identity(item), _text(item.get("waybill")
                                       or item.get("shipment"))))


def _add_receipt_stage(row, record, *, source_identity=None, conflict=False,
                       identity_status=None):
    """Received only when the Tongtool receipt time is proven; signed-only is
    in_transit with signed_at (never a received fact)."""
    qty = _dec(record.get("qty"))
    if qty is None:
        return
    signed = _aware(record.get("signed_at"))
    received = _aware(record.get("received_at"))
    identity = (source_identity if source_identity is not None
                else record.get("_source_identity"))
    if received:
        _add_stage(
            row, "received", qty, received.isoformat(), "actual",
            source_identity=identity, conflict=conflict,
            identity_status=identity_status,
            observed_at=record.get("observed_at"),
            signed_at=signed.isoformat() if signed else None,
            received_at=received.isoformat(),
            inventory_inclusion_status="unknown")
    elif signed:
        _add_stage(
            row, "in_transit", qty, signed.isoformat(), "actual",
            source_identity=identity, conflict=conflict,
            identity_status=identity_status,
            observed_at=record.get("observed_at"),
            signed_at=signed.isoformat(),
            inventory_inclusion_status="unknown")


def _receipt_proven(receipt):
    return _aware(receipt.get("received_at")) is not None


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


def _stage_owner(row):
    purpose = row.get("purpose")
    branch = _text(row.get("branch"))
    if purpose == "branch":
        owner = "branch_owner" if branch else "branch_unknown"
    elif purpose == "fba":
        owner = "fba_branch_conflict" if branch else "fba"
    elif purpose == "cg":
        owner = "cg_branch_conflict" if branch else "cg"
    else:
        owner = "unknown"
    cg_stale = False
    cg_eligible = False
    reasons = []
    if purpose == "cg":
        fresh = row.get("inventory_freshness")
        cg_stale = fresh == "stale"
        cg_eligible = bool(fresh == "fresh"
                           and row.get("attribution_status") == "attributed")
        if fresh == "stale":
            reasons.append("cg_stale")
        elif fresh != "fresh":
            reasons.append("cg_time_unknown")
        if row.get("attribution_status") != "attributed":
            reasons.append("cg_not_attributed")
    if owner.endswith("conflict"):
        reasons.append(owner)
    return owner, cg_stale, cg_eligible, reasons


def _doc_fields(identity):
    identity = {key: value for key, value in (identity or {}).items()
                if value not in (None, "")}
    dn = _text(identity.get("delivery_note"))
    dn_item = _text(identity.get("dn_item"))
    wo = _text(identity.get("work_order") or identity.get("wo")
               or identity.get("name"))
    shipment = _text(identity.get("shipment") or identity.get("waybill")
                     or identity.get("logistic_number"))
    receipt = _text(identity.get("receipt_id"))
    receipt_line = _text(identity.get("line_id")
                         or identity.get("receipt_line"))
    po = _text(identity.get("po_code"))
    snapshot = _text(identity.get("snapshot_id"))
    ref = _text(identity.get("source_ref"))
    doc_type = doc_name = doc_line = None
    if dn:
        doc_type, doc_name, doc_line = "Delivery Note", dn, dn_item or None
    elif wo:
        doc_type, doc_name = "Work Order", wo
    elif shipment:
        doc_type, doc_name = "Shipment", shipment
    elif receipt:
        doc_type, doc_name = "Tongtool Receipt", receipt
        doc_line = receipt_line or None
    elif po:
        doc_type, doc_name = "Purchase Order", po
    elif snapshot or ref:
        doc_type, doc_name = "Inventory Snapshot", snapshot or ref
    return doc_type, doc_name, doc_line


def _fact_identity(row, stage, doc_type, doc_name, doc_line, identity,
                   evidence):
    payload = {
        "item_code": row.get("item_code"), "uom": row.get("uom"),
        "warehouse": row.get("warehouse"), "purpose": row.get("purpose"),
        "tt_sku": row.get("tt_sku"), "branch": row.get("branch"),
        "market": row.get("market"), "product_form": row.get("product_form"),
        "stage": stage,
        "doc_type": doc_type, "doc_name": doc_name, "doc_line": doc_line,
        "source_ref": (identity or {}).get("source_ref"),
        "delivery_note": (identity or {}).get("delivery_note"),
        "dn_item": (identity or {}).get("dn_item"),
        "work_order": ((identity or {}).get("work_order")
                       or (identity or {}).get("wo")
                       or (identity or {}).get("name")),
        "shipment": ((identity or {}).get("shipment")
                     or (identity or {}).get("waybill")
                     or (identity or {}).get("logistic_number")),
        "receipt_id": (identity or {}).get("receipt_id"),
        "receipt_line": ((identity or {}).get("line_id")
                         or (identity or {}).get("receipt_line")),
        "snapshot_id": (identity or {}).get("snapshot_id"),
        "po_code": ((identity or {}).get("po_code")
                    or (evidence or {}).get("po_code")),
        "allocation_id": ((identity or {}).get("allocation_id")
                          or (evidence or {}).get("allocation_id")),
    }
    return {key: _text(value) for key, value in payload.items()
            if _text(value)}


def _lineage(identity, evidence):
    identity = identity or {}
    evidence = evidence or {}
    explicit = _text(identity.get("physical_lineage_id")
                     or identity.get("lineage_id")
                     or identity.get("batch_id")
                     or evidence.get("physical_lineage_id")
                     or evidence.get("lineage_id")
                     or evidence.get("batch_id"))
    allocation = _text(identity.get("allocation_id")
                       or evidence.get("allocation_id"))
    chain = _text(identity.get("parent_lineage_id")
                  or evidence.get("parent_lineage_id")
                  or identity.get("lineage_chain_id")
                  or evidence.get("lineage_chain_id"))
    if explicit:
        return explicit, "proven_explicit_batch"
    if allocation:
        return "ALLOC:" + allocation, "proven_allocation"
    if chain:
        return chain, "proven_chain"
    return None, "unproven"


def _stable_fact_id(fact_identity):
    return hashlib.sha1(json.dumps(
        fact_identity, sort_keys=True, ensure_ascii=False, default=str
    ).encode("utf-8")).hexdigest()[:24]


def _payload_hash(fact):
    payload = {key: fact.get(key) for key in (
        "qty", "qty_status", "confidence",
        "observed_at", "observed_at_raw", "observed_at_time_status",
        "eta", "eta_raw", "eta_time_status",
        "available_at", "available_at_raw", "available_at_time_status",
        "signed_at", "signed_at_raw", "signed_at_time_status",
        "received_at", "received_at_raw", "received_at_time_status",
        "actual_at", "expected_at", "source_status")}
    return hashlib.sha1(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str
    ).encode("utf-8")).hexdigest()[:24]


def _time_field(fact, prefix, value, raw=None, status=None):
    parsed, auto_raw, auto_status = _time_parts(value)
    fact[prefix] = parsed.isoformat() if parsed else None
    fact[prefix + "_raw"] = raw if raw is not None else auto_raw
    fact[prefix + "_time_status"] = (status if status is not None
                                     else auto_status)
    return parsed


def _stage_base(row, *, stage, qty, identity, evidence, confidence,
                qty_status, source_status):
    doc_type, doc_name, doc_line = _doc_fields(identity)
    batch = _text((identity or {}).get("batch_id")
                  or (evidence or {}).get("batch_id")) or None
    lineage, lineage_status = _lineage(identity, evidence)
    fact_identity = _fact_identity(
        row, stage, doc_type, doc_name, doc_line, identity, evidence)
    owner, cg_stale, cg_eligible, cg_reasons = _stage_owner(row)
    inclusion_proof = _text((identity or {}).get("inclusion_proof")
                            or (evidence or {}).get("inclusion_proof"))
    fact = {
        "item_code": row.get("item_code"), "uom": row.get("uom"),
        "warehouse": row.get("warehouse"), "purpose": row.get("purpose"),
        "tt_sku": row.get("tt_sku"), "branch": row.get("branch") or "",
        "market": row.get("market"), "product_form": row.get("product_form"),
        "pool": row.get("pool"), "scope": row.get("scope"),
        "stage": stage,
        "doc_type": doc_type, "doc_name": doc_name, "doc_line": doc_line,
        "batch_id": batch,
        "physical_lineage_id": lineage, "lineage_status": lineage_status,
        "fact_identity": fact_identity,
        "stage_fact_id": _stable_fact_id(fact_identity),
        "payload_hash": None, "payload_conflict": False,
        "payload_hashes": [], "payload_candidates": [],
        "inclusion_proof": inclusion_proof or None,
        "source_identity": dict(identity or {}),
        "inventory_freshness": row.get("inventory_freshness"),
        "inventory_time_proven": bool(row.get("inventory_time_proven")),
        "attribution_status": row.get("attribution_status"),
        "stage_measured_qty": None, "evidence_only": False,
        "same_stage_reconciliation_status": None,
        "qty": _qty(qty, signed=True), "qty_status": qty_status,
        "confidence": confidence, "counted_as_supply": False,
        "counted_reason": "", "source_status": source_status,
        "observed_at": None, "observed_at_raw": None,
        "observed_at_time_status": "missing",
        "eta": None, "eta_raw": None, "eta_time_status": "missing",
        "available_at": None, "available_at_raw": None,
        "available_at_time_status": "missing",
        "signed_at": None, "signed_at_raw": None,
        "signed_at_time_status": "missing",
        "received_at": None, "received_at_raw": None,
        "received_at_time_status": "missing",
        "actual_at": None, "expected_at": None,
        "overlap_status": "unknown",
        "inventory_inclusion_status": "unknown",
        "owner_status": owner, "cg_stale": cg_stale,
        "cg_eligible": cg_eligible,
        "cg_blocking_reasons": list(cg_reasons),
        "unknown_reasons": [], "conflicts": [],
        "blockers": list(cg_reasons),
        "_stage_time": None,
    }
    return fact


def _source_observed(row, layer, identity):
    for source in row.get("sources") or ():
        if source.get("layer") != layer:
            continue
        if identity and source.get("source_identity") != identity:
            continue
        if source.get("observed_at"):
            return source
    return None


def _row_observed(row, layers):
    for layer in layers:
        source = _source_observed(row, layer, None)
        if source:
            return (source.get("observed_at"), source.get("observed_at_raw"),
                    source.get("time_status"))
    return None, None, "missing"


def _fragment_fact(row, fragment):
    raw_stage = _text(fragment.get("stage"))
    stage = FRAGMENT_STAGE.get(raw_stage)
    if stage is None:
        return None
    if (raw_stage == "received" and not fragment.get("received_at")
            and fragment.get("signed_at")):
        stage = "in_transit"
    qty = _dec(fragment.get("qty"), signed=True)
    if qty is None:
        return None
    identity = fragment.get("source_identity") or {}
    evidence = {}
    for source in row.get("sources") or ():
        if (source.get("source_identity") == fragment.get("source_identity")
                and source.get("evidence")):
            evidence = source["evidence"]
            break
    conflict = bool(fragment.get("conflict"))
    if raw_stage == "in_production_estimated":
        confidence, qty_status = "estimated", "estimated"
    elif conflict:
        confidence, qty_status = "conflict", "unknown"
    elif raw_stage == "in_production":
        confidence, qty_status = "proven", "known"
    elif raw_stage in ("po_completed_assumed", "po_open"):
        confidence, qty_status = "observed", "known"
    elif raw_stage == "inventory":
        confidence = ("proven" if row.get("inventory_time_proven")
                      and row.get("attribution_status") == "attributed"
                      else "observed")
        qty_status = "known"
    elif raw_stage == "received":
        if fragment.get("received_at"):
            confidence, qty_status = "proven", "known"
        else:
            confidence, qty_status = "unknown", "unknown"
    else:
        confidence = "proven" if not conflict else "conflict"
        qty_status = "known" if not conflict else "unknown"
    fact = _stage_base(
        row, stage=stage, qty=qty, identity=identity, evidence=evidence,
        confidence=confidence, qty_status=qty_status,
        source_status=("conflict" if conflict
                       else ("known" if qty_status == "known" else "unknown")))
    observed = fragment.get("observed_at")
    observed_raw = fragment.get("observed_at_raw")
    observed_status = fragment.get("observed_at_time_status")
    if not observed and not observed_raw:
        layer = {
            "po_completed_assumed": "dn_po", "po_open": "dn_po",
            "in_production": "production",
            "in_production_estimated": "production",
            "in_transit": "in_transit", "received": "receipt",
            "inventory": "inventory"}.get(raw_stage, "dn_po")
        observed, observed_raw, observed_status = _row_observed(
            row, [layer, "dn_po"])
    if stage == "on_hand" and not observed:
        observed = row.get("inventory_as_of")
        observed_raw = row.get("inventory_as_of_raw")
        observed_status = row.get("inventory_time_status")
    _time_field(fact, "observed_at", observed,
                raw=observed_raw, status=observed_status)
    eta = fragment.get("expected_at") if stage != "on_hand" else None
    _time_field(fact, "eta", eta,
                raw=(fragment.get("date_raw")
                     if fragment.get("date_kind") == "expected" else None),
                status=(fragment.get("date_status")
                        if fragment.get("date_kind") == "expected" else None))
    _time_field(fact, "signed_at", fragment.get("signed_at"),
                raw=fragment.get("signed_at_raw"),
                status=fragment.get("signed_at_time_status"))
    _time_field(fact, "received_at", fragment.get("received_at"),
                raw=fragment.get("received_at_raw"),
                status=fragment.get("received_at_time_status"))
    fact["actual_at"] = fragment.get("actual_at")
    fact["expected_at"] = fragment.get("expected_at")
    if stage == "on_hand":
        _time_field(fact, "available_at", row.get("inventory_as_of"),
                    raw=row.get("inventory_as_of_raw"),
                    status=row.get("inventory_time_status"))
    elif stage == "received":
        _time_field(fact, "available_at", fragment.get("received_at"),
                    raw=fragment.get("received_at_raw"),
                    status=fragment.get("received_at_time_status"))
    if fragment.get("replay"):
        fact["overlap_status"] = "same/proven"
    if conflict:
        fact["overlap_status"] = "conflict"
    signed_dt = _aware(fact.get("signed_at"))
    received_dt = _aware(fact.get("received_at"))
    if (stage == "received" and signed_dt and received_dt
            and received_dt < signed_dt):
        fact["conflicts"].append("receipt_before_signed")
        fact["unknown_reasons"].append("receipt_before_signed")
        fact["qty_status"] = "unknown"
        fact["confidence"] = "conflict"
        fact["source_status"] = "conflict"
        fact["overlap_status"] = "conflict"
    if conflict and not fact["conflicts"]:
        # Generic conflict fragment (e.g. source target/allocation conflict);
        # specific time conflicts above keep their own reason.
        fact["conflicts"].append("source_payload_conflict")
        fact["unknown_reasons"].append("source_payload_conflict")
    if fact["lineage_status"] == "unproven":
        fact["unknown_reasons"].append("physical_lineage_unproven")
    if fragment.get("identity_status") == "missing":
        fact["unknown_reasons"].append("source_identity_missing")
    fact["_stage_time"] = _stage_time(
        stage, fact.get("available_at"), fact.get("actual_at"),
        fact.get("signed_at"), fact.get("received_at"), fact.get("eta"))
    fact["payload_hash"] = _payload_hash(fact)
    return fact


def _stage_time(stage, available, actual, signed, received, eta):
    if stage == "on_hand":
        return _aware(available)
    if stage == "received":
        return _aware(received)
    if stage == "in_transit":
        return _aware(actual) or _aware(signed)
    if stage == "waiting_shipment":
        return _aware(actual) or _aware(eta)
    return None


def _position_stage_facts(row):
    facts = []
    tranches = (row.get("_stage_position_tranches")
                or row.get("_position_tranches") or ())
    if tranches:
        for tranche in tranches:
            qty = _dec(tranche.get("qty"), signed=True)
            if qty is None or qty == 0:
                continue
            identity = {
                "instance": tranche.get("instance"),
                "delivery_note": tranche.get("delivery_note"),
                "dn_item": tranche.get("dn_item")}
            if _text(tranche.get("batch_id")):
                identity["batch_id"] = _text(tranche.get("batch_id"))
            source = _source_observed(row, "dn_line", {
                key: value for key, value in identity.items()
                if value not in (None, "")})
            if source is None:
                source = _source_observed(row, "dn_po", None)
            evidence = (source or {}).get("evidence") or {}
            fact = _stage_base(
                row, stage="in_transit", qty=qty, identity=identity,
                evidence=evidence, confidence="observed", qty_status="known",
                source_status="known")
            _time_field(fact, "observed_at",
                        (source or {}).get("observed_at"))
            fact["_stage_time"] = _stage_time(
                "in_transit", None, None, None, None, None)
            fact["payload_hash"] = _payload_hash(fact)
            facts.append(fact)
        return facts
    qty = _dec(row.get("dn_net_qty"), signed=True)
    if qty is None or qty == 0:
        return facts
    source = _source_observed(row, "dn_line", None)
    if source is None:
        source = _source_observed(row, "dn_po", None)
    identity = (source or {}).get("source_identity") or {}
    fact = _stage_base(
        row, stage="in_transit", qty=qty, identity=identity,
        evidence=(source or {}).get("evidence") or {},
        confidence="observed", qty_status="known", source_status="known")
    _time_field(fact, "observed_at", (source or {}).get("observed_at"))
    fact["_stage_time"] = _stage_time(
        "in_transit", None, None, None, None, None)
    fact["payload_hash"] = _payload_hash(fact)
    facts.append(fact)
    return facts


def _dedupe_stage_facts(facts):
    groups = defaultdict(list)
    for fact in facts:
        groups[fact["stage_fact_id"]].append(fact)
    out = []
    for fact_id in sorted(groups):
        items = groups[fact_id]
        hashes = sorted({fact["payload_hash"] for fact in items
                         if fact["payload_hash"]})
        if len(hashes) <= 1:
            keep = dict(items[0])
            keep["payload_hash"] = hashes[0] if hashes else None
            keep["payload_hashes"] = hashes
            keep["payload_conflict"] = False
            keep["_replay_count"] = len(items)
            out.append(keep)
            continue
        keep = dict(items[0])
        keep.update({
            "payload_conflict": True,
            "payload_hashes": hashes,
            "payload_candidates": [{
                "payload_hash": fact["payload_hash"], "qty": fact["qty"],
                "observed_at": fact["observed_at"], "eta": fact["eta"],
                "signed_at": fact["signed_at"],
                "received_at": fact["received_at"],
                "actual_at": fact["actual_at"]} for fact in items],
            "qty": None, "qty_status": "unknown",
            "confidence": "conflict", "source_status": "conflict",
            "counted_as_supply": False,
            "counted_reason": "source_payload_conflict"})
        keep["conflicts"] = sorted(set(keep["conflicts"]
                                       + ["source_payload_conflict"]))
        keep["unknown_reasons"] = sorted(set(
            keep["unknown_reasons"] + ["source_payload_conflict"]))
        out.append(keep)
    return out


def _stage_inventory_inclusion(facts):
    has_any_on_hand = any(fact["stage"] == "on_hand" for fact in facts)
    by_lineage = defaultdict(list)
    for fact in facts:
        lineage = fact.get("physical_lineage_id")
        if lineage and fact.get("lineage_status") != "unproven":
            by_lineage[lineage].append(fact)
    for fact in facts:
        proof = _text(fact.get("inclusion_proof")).lower()
        if proof in ("included", "not_included", "unknown"):
            fact["inventory_inclusion_status"] = proof
            continue
        if fact["stage"] == "on_hand":
            fact["inventory_inclusion_status"] = (
                "included" if _on_hand_time_usable(fact) else "unknown")
            continue
        if fact["stage"] not in ("received", "in_transit"):
            fact["inventory_inclusion_status"] = "not_applicable"
            continue
        lineage = fact.get("physical_lineage_id")
        if not lineage or fact.get("lineage_status") == "unproven":
            fact["inventory_inclusion_status"] = (
                "unknown" if has_any_on_hand else "not_applicable")
            continue
        peers = [peer for peer in by_lineage.get(lineage, [])
                 if peer["stage"] == "on_hand"
                 and _on_hand_time_usable(peer)]
        if not peers:
            fact["inventory_inclusion_status"] = (
                "unknown" if has_any_on_hand else "not_applicable")
            continue
        on_times = [_aware(peer.get("available_at")) for peer in peers]
        on_times = [value for value in on_times if value is not None]
        on_time = max(on_times) if on_times else None
        event = (_aware(fact.get("received_at"))
                 if fact["stage"] == "received"
                 else (_aware(fact.get("actual_at"))
                       or _aware(fact.get("signed_at"))))
        if on_time is None or event is None:
            fact["inventory_inclusion_status"] = "unknown"
        elif on_time >= event:
            fact["inventory_inclusion_status"] = "included"
        else:
            fact["inventory_inclusion_status"] = "post_snapshot"


def _on_hand_time_usable(fact):
    """Aware proven fresh on-hand time; used for both inclusion and current stage."""
    if fact["stage"] != "on_hand":
        return False
    if not (fact.get("physical_lineage_id")
            and fact.get("lineage_status") != "unproven"):
        return False
    if fact.get("available_at_time_status") != "known":
        return False
    if _aware(fact.get("available_at")) is None:
        return False
    if not fact.get("inventory_time_proven"):
        return False
    if fact.get("inventory_freshness") != "fresh":
        return False
    if (fact.get("qty_status") != "known"
            or _dec(fact.get("qty"), signed=True) is None):
        return False
    return True


def _on_hand_current_eligible(fact):
    """A proven, fresh, owned on-hand fact may supersede a receipt in transit."""
    if not _on_hand_time_usable(fact):
        return False
    if fact.get("owner_status") not in ("branch_owner", "fba", "cg"):
        return False
    if fact["purpose"] == "cg" and not fact.get("cg_eligible"):
        return False
    if not _text(fact.get("uom")):
        return False
    if fact.get("inventory_inclusion_status") != "included":
        return False
    attribution = fact.get("attribution_status")
    if attribution is not None and attribution != "attributed":
        return False
    if fact.get("payload_conflict") or fact.get("conflicts"):
        return False
    return True


def _stage_allocation_measure(items, quantities):
    """Return the conserved allocation sum, or None when proof is incomplete."""
    allocation_ids = set()
    declared = set()
    total = Decimal(0)
    for fact, qty in zip(items, quantities):
        identity = fact.get("source_identity") or {}
        allocation_id = _text(identity.get("allocation_id"))
        allocated = _dec(identity.get("allocated_qty"), signed=True)
        source_qty = _dec(identity.get("source_qty"), signed=True)
        if (not allocation_id or allocated is None or source_qty is None
                or allocated != qty or allocation_id in allocation_ids):
            return None
        allocation_ids.add(allocation_id)
        declared.add(source_qty)
        total += allocated
    if len(declared) != 1:
        return None
    capacity = declared.pop()
    if total <= 0 or total > capacity:
        return None
    return total


def _reconcile_stage_quantities(facts):
    """One physical quantity per physical_lineage_id x stage.

    Multiple provenance chains are evidence, not additive supply. Only a valid
    allocation ledger (allocation_id + allocated_qty + source_qty, conserved)
    may be summed. Differing quantities without proof are a conflict.
    """
    grouped = defaultdict(list)
    for fact in facts:
        if (fact.get("physical_lineage_id")
                and fact.get("lineage_status") != "unproven"):
            grouped[(fact["physical_lineage_id"], fact["stage"])].append(fact)
        else:
            fact["stage_measured_qty"] = None
            fact["evidence_only"] = False
            fact["same_stage_reconciliation_status"] = "unproven_lineage"
    for items in grouped.values():
        def _representative_rank(item):
            if item["stage"] == "on_hand":
                return (0 if _on_hand_time_usable(item) else 1,
                        _text(item["stage_fact_id"]))
            if item["stage"] == "waiting_shipment":
                return (0 if item["confidence"] in ("proven", "observed")
                        else 1, _text(item["stage_fact_id"]))
            return (0, _text(item["stage_fact_id"]))

        items = sorted(items, key=_representative_rank)
        quantities = [_dec(item.get("qty"), signed=True) for item in items]
        if any(value is None for value in quantities):
            for index, item in enumerate(items):
                item["stage_measured_qty"] = None
                item["evidence_only"] = index > 0
                item["same_stage_reconciliation_status"] = "unknown_quantity"
            continue
        has_allocation = any(
            _text((item.get("source_identity") or {}).get("allocation_id"))
            for item in items)
        if has_allocation:
            total = _stage_allocation_measure(items, quantities)
            if total is None:
                for item in items:
                    item["stage_measured_qty"] = None
                    item["evidence_only"] = False
                    item["same_stage_reconciliation_status"] = (
                        "quantity_conflict")
                    item["overlap_status"] = "conflict"
                    item["conflicts"] = sorted(set(
                        item["conflicts"] + ["same_stage_quantity_conflict"]))
                    item["unknown_reasons"] = sorted(set(
                        item["unknown_reasons"]
                        + ["same_stage_quantity_conflict"]))
                continue
            measured = _qty(total, signed=True)
            for item in items:
                item["stage_measured_qty"] = measured
                item["evidence_only"] = False
                item["same_stage_reconciliation_status"] = "allocated_sum"
            continue
        distinct = set(quantities)
        if len(distinct) == 1:
            measured = _qty(quantities[0], signed=True)
            for index, item in enumerate(items):
                item["stage_measured_qty"] = measured
                item["evidence_only"] = index > 0
                item["same_stage_reconciliation_status"] = (
                    "duplicate_evidence" if len(items) > 1 else "single")
            continue
        for item in items:
            item["stage_measured_qty"] = None
            item["evidence_only"] = False
            item["same_stage_reconciliation_status"] = "quantity_conflict"
            item["overlap_status"] = "conflict"
            item["conflicts"] = sorted(set(
                item["conflicts"] + ["same_stage_quantity_conflict"]))
            item["unknown_reasons"] = sorted(set(
                item["unknown_reasons"] + ["same_stage_quantity_conflict"]))


def _select_stage_facts(facts):
    owner_map = defaultdict(set)
    for fact in facts:
        if (fact.get("physical_lineage_id")
                and fact.get("lineage_status") != "unproven"):
            owner_map[(fact["physical_lineage_id"], fact["item_code"],
                       fact["uom"])].add(
                (fact["purpose"], fact["branch"] or ""))
    for fact in facts:
        owners = owner_map.get((fact.get("physical_lineage_id"),
                                fact["item_code"], fact["uom"]))
        if not owners:
            continue
        branches = {branch for purpose, branch in owners
                    if purpose == "branch"}
        purposes = {purpose for purpose, _ in owners
                    if purpose in ("branch", "fba", "cg")}
        if len(branches) > 1:
            fact["owner_status"] = "branch_conflict"
            fact["blockers"].append("branch_owner_conflict")
        if len(purposes) > 1:
            fact["owner_status"] = "owner_purpose_conflict"
            fact["blockers"].append("owner_purpose_conflict")

    _reconcile_stage_quantities(facts)

    groups = defaultdict(list)
    for fact in facts:
        if (fact.get("physical_lineage_id")
                and fact.get("lineage_status") != "unproven"):
            key = (fact["item_code"], fact["uom"], fact["warehouse"],
                   fact["purpose"], fact["tt_sku"], fact["branch"],
                   fact["physical_lineage_id"])
        else:
            key = ("fact", fact["stage_fact_id"])
        groups[key].append(fact)

    blocking = {"source_payload_conflict", "receipt_before_signed",
                "time_order_conflict", "stage_regression"}
    for items in groups.values():
        item_conflicts = {reason for fact in items
                          for reason in fact["conflicts"]
                          if reason in blocking}
        if item_conflicts or any(fact["payload_conflict"] for fact in items):
            reasons = item_conflicts or {"source_payload_conflict"}
            for fact in items:
                fact["counted_as_supply"] = False
                fact["counted_reason"] = ";".join(sorted(reasons))
                fact["unknown_reasons"] = sorted(set(
                    fact["unknown_reasons"] + list(reasons)))
                fact["blockers"] = sorted(set(
                    fact["blockers"] + list(reasons)))
                fact["overlap_status"] = "conflict"
            continue

        transit_times = [
            _aware(fact.get("actual_at")) or _aware(fact.get("signed_at"))
            for fact in items if fact["stage"] == "in_transit"]
        transit_times = [value for value in transit_times if value]
        received_times = [_aware(fact.get("received_at"))
                          for fact in items if fact["stage"] == "received"]
        received_times = [value for value in received_times if value]
        waiting_actual = [_aware(fact.get("actual_at"))
                          for fact in items
                          if fact["stage"] == "waiting_shipment"]
        waiting_actual = [value for value in waiting_actual if value]
        conflict = None
        if (received_times and transit_times
                and min(received_times) < max(transit_times)):
            conflict = "time_order_conflict"
        if (waiting_actual and transit_times
                and max(waiting_actual) > min(transit_times)):
            conflict = "stage_regression"
        if (waiting_actual and received_times
                and max(waiting_actual) > min(received_times)):
            conflict = "stage_regression"
        if conflict:
            for fact in items:
                fact["counted_as_supply"] = False
                fact["counted_reason"] = conflict
                fact["conflicts"] = sorted(set(
                    fact["conflicts"] + [conflict]))
                fact["unknown_reasons"] = sorted(set(
                    fact["unknown_reasons"] + [conflict]))
                fact["blockers"] = sorted(set(
                    fact["blockers"] + [conflict]))
                fact["overlap_status"] = "conflict"
            continue

        present = {fact["stage"] for fact in items}
        on_hand_facts = [fact for fact in items if fact["stage"] == "on_hand"]
        on_hand_current = [fact for fact in on_hand_facts
                           if _on_hand_current_eligible(fact)]
        for fact in on_hand_facts:
            if fact not in on_hand_current:
                fact["inventory_inclusion_status"] = "unknown"
                fact["unknown_reasons"] = sorted(set(
                    fact["unknown_reasons"] + ["on_hand_not_current"]))
        chosen_stage = None
        stage_unknown = None
        if "on_hand" in present:
            if on_hand_current:
                on_times = [_aware(fact["available_at"])
                            for fact in on_hand_current
                            if _aware(fact["available_at"])]
                chosen_stage = "on_hand"
                if (on_times and received_times
                        and max(on_times) < min(received_times)):
                    chosen_stage = "received"
                elif (on_times and transit_times
                      and max(on_times) < min(transit_times)):
                    chosen_stage = "in_transit"
                elif not received_times and not transit_times:
                    # A fresh on-hand fact with no competing proven event time
                    # is the only proven stage.
                    chosen_stage = "on_hand"
            elif "received" in present:
                # Unproven/stale/naive/date-only on-hand never supersedes.
                chosen_stage = "received"
            elif "in_transit" in present:
                chosen_stage = "in_transit"
            else:
                stage_unknown = "on_hand_time_unproven"
        elif "received" in present:
            chosen_stage = "received"
        elif "in_transit" in present:
            chosen_stage = "in_transit"
        elif "waiting_shipment" in present:
            chosen_stage = "waiting_shipment"
        elif "open_po" in present:
            chosen_stage = "open_po"
        chosen_ids = set()
        if chosen_stage:
            at_stage = [fact for fact in items
                        if fact["stage"] == chosen_stage]
            if chosen_stage == "on_hand":
                at_stage = [fact for fact in at_stage
                            if fact in on_hand_current]
            elif chosen_stage == "waiting_shipment":
                strong = [fact for fact in at_stage
                          if fact["confidence"] in ("proven", "observed")]
                if strong:
                    at_stage = strong
            statuses = {fact.get("same_stage_reconciliation_status")
                        for fact in at_stage}
            if statuses & {"quantity_conflict", "unknown_quantity"}:
                chosen_ids = set()
            elif "allocated_sum" in statuses:
                chosen_ids = {id(fact) for fact in at_stage}
            else:
                ordered = sorted(at_stage,
                                 key=lambda item: _text(item["stage_fact_id"]))
                chosen_ids = {id(fact) for fact in ordered
                              if not fact.get("evidence_only")}
        if stage_unknown:
            for fact in on_hand_facts:
                fact["unknown_reasons"] = sorted(set(
                    fact["unknown_reasons"] + [stage_unknown]))
        for fact in items:
            proven = bool(fact.get("physical_lineage_id")
                          and fact.get("lineage_status") != "unproven")
            fact["overlap_status"] = (
                "same/proven" if len(items) > 1 and proven
                else ("distinct/proven" if proven else "unknown"))
            if id(fact) in chosen_ids:
                fact["counted_as_supply"] = True
                fact["counted_reason"] = "current_stage"
            else:
                fact["counted_as_supply"] = False
                if fact.get("evidence_only"):
                    fact["counted_reason"] = "evidence_only_duplicate"
                else:
                    fact["counted_reason"] = (
                        stage_unknown or ("superseded_by_stage:"
                                          + str(chosen_stage)))
            if (fact["stage"] in ("received", "in_transit")
                    and fact["inventory_inclusion_status"] == "unknown"
                    and "on_hand" in present):
                fact["unknown_reasons"] = sorted(set(
                    fact["unknown_reasons"] + ["inventory_inclusion_unknown"]))

    for fact in facts:
        if fact["stage"] == "open_po":
            fact["counted_as_supply"] = False
            fact["counted_reason"] = "open_po_reconciliation_only"
        if (fact["stage"] == "waiting_shipment"
                and fact["confidence"] == "estimated"):
            fact["counted_as_supply"] = False
            fact["counted_reason"] = "estimated_not_proven"
        if fact["payload_conflict"]:
            fact["counted_as_supply"] = False
            fact["counted_reason"] = "source_payload_conflict"
        if fact["conflicts"] or fact["qty_status"] != "known":
            fact["counted_as_supply"] = False
            if "same_stage_quantity_conflict" in fact["conflicts"]:
                fact["counted_reason"] = "same_stage_quantity_conflict"
            else:
                fact["counted_reason"] = (fact["counted_reason"]
                                          if fact["counted_reason"]
                                          not in ("current_stage", "")
                                          else "source_conflict")
        if fact["owner_status"].endswith("conflict"):
            fact["counted_as_supply"] = False
            fact["counted_reason"] = (fact["counted_reason"]
                                      if fact["counted_reason"]
                                      not in ("current_stage", "")
                                      else fact["owner_status"])
        if fact["owner_status"] in ("branch_unknown", "unknown"):
            fact["counted_as_supply"] = False
            fact["counted_reason"] = (fact["counted_reason"]
                                      if fact["counted_reason"]
                                      not in ("current_stage", "")
                                      else fact["owner_status"])
        if fact["lineage_status"] == "unproven":
            fact["counted_as_supply"] = False
            fact["counted_reason"] = (fact["counted_reason"]
                                      if fact["counted_reason"]
                                      not in ("current_stage", "")
                                      else "physical_lineage_unproven")
        if fact["purpose"] == "cg" and not fact["cg_eligible"]:
            fact["counted_as_supply"] = False
            fact["counted_reason"] = (fact["counted_reason"]
                                      if fact["counted_reason"]
                                      not in ("current_stage", "")
                                      else (fact["cg_blocking_reasons"][0]
                                            if fact["cg_blocking_reasons"]
                                            else "cg_not_eligible"))
        if (fact["counted_as_supply"]
                and fact["inventory_inclusion_status"] == "included"
                and fact["stage"] != "on_hand"):
            fact["counted_as_supply"] = False
            fact["counted_reason"] = "inventory_inclusion_included"
        fact["blockers"] = sorted(set(
            list(fact.get("blockers") or ())
            + list(fact.get("cg_blocking_reasons") or ())
            + list(fact.get("conflicts") or ())))
        fact.pop("_stage_time", None)


def build_stage_facts(rows):
    facts = []
    for row in rows:
        for fragment in row.get("stage_quantities") or ():
            fact = _fragment_fact(row, fragment)
            if fact:
                facts.append(fact)
        facts.extend(_position_stage_facts(row))
    facts = _dedupe_stage_facts(facts)
    _stage_inventory_inclusion(facts)
    _select_stage_facts(facts)
    return sorted(facts, key=lambda fact: (
        _text(fact["item_code"]), _text(fact["uom"]),
        _text(fact["warehouse"]), _text(fact["purpose"]),
        _text(fact["tt_sku"]), _text(fact["branch"]),
        STAGE_RANK.get(fact["stage"], 99), _text(fact["doc_line"]),
        _text(fact["stage_fact_id"])))


def summarize_stage_facts(facts):
    counted = [fact for fact in facts if fact["counted_as_supply"]]
    counted_qty = defaultdict(Decimal)
    for fact in counted:
        value = _dec(fact.get("qty"), signed=True)
        if value is not None:
            counted_qty[fact["stage"]] += value
    measured_qty = defaultdict(Decimal)
    measured_seen = set()
    for fact in facts:
        lineage = fact.get("physical_lineage_id")
        value = _dec(fact.get("stage_measured_qty"), signed=True)
        if not lineage or value is None:
            continue
        key = (lineage, fact["stage"])
        if key in measured_seen:
            continue
        measured_seen.add(key)
        measured_qty[fact["stage"]] += value
    conflict_reasons = Counter(
        reason for fact in facts for reason in (fact.get("conflicts") or ()))
    return {
        "rows": len(facts),
        "stage_counts": dict(sorted(Counter(
            fact["stage"] for fact in facts).items())),
        "counted_stage_counts": dict(sorted(Counter(
            fact["stage"] for fact in counted).items())),
        "counted_qty_by_stage": {
            stage: _qty(value, signed=True)
            for stage, value in sorted(counted_qty.items())},
        "stage_measured_qty_by_stage": {
            stage: _qty(value, signed=True)
            for stage, value in sorted(measured_qty.items())},
        "reconciliation_status_counts": dict(sorted(Counter(
            fact.get("same_stage_reconciliation_status")
            for fact in facts).items())),
        "evidence_only_rows": sum(
            1 for fact in facts if fact.get("evidence_only")),
        "conflict_reason_distribution": dict(sorted(conflict_reasons.items())),
        "unknown_rows": sum(1 for fact in facts if fact["unknown_reasons"]),
        "conflict_rows": sum(1 for fact in facts if fact["conflicts"]),
        "payload_conflict_rows": sum(
            1 for fact in facts if fact["payload_conflict"]),
        "overlap_counts": dict(sorted(Counter(
            fact["overlap_status"] for fact in facts).items())),
        "owner_status_counts": dict(sorted(Counter(
            fact["owner_status"] for fact in facts).items())),
        "lineage_status_counts": dict(sorted(Counter(
            fact["lineage_status"] for fact in facts).items())),
        "physical_lineages": len({
            fact["physical_lineage_id"] for fact in facts
            if fact.get("physical_lineage_id")}),
        "unproven_lineage_rows": sum(
            1 for fact in facts if fact["lineage_status"] == "unproven"),
        "batch_identity_missing": sum(
            1 for fact in facts if fact["lineage_status"] == "unproven"),
        "replay_rows": sum(max(0, int(fact.get("_replay_count", 1)) - 1)
                           for fact in facts),
        "cg_fresh": sum(1 for fact in facts
                        if fact["purpose"] == "cg"
                        and not fact["cg_stale"] and fact["cg_eligible"]),
        "cg_stale": sum(1 for fact in facts
                        if fact["purpose"] == "cg" and fact["cg_stale"]),
        "cg_unknown": sum(1 for fact in facts
                          if fact["purpose"] == "cg"
                          and not fact["cg_stale"]
                          and not fact["cg_eligible"]),
    }


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
        source_identity = {"source_ref": item.get("source_ref"),
                           "item_code": item.get("item_code"),
                           "pool": item.get("pool")}
        if _text(item.get("batch_id")):
            source_identity["batch_id"] = _text(item.get("batch_id"))
        _merge_source(row, "inventory", status, item.get("inventory_as_of"),
                      reason,
                      source_identity=source_identity)
        if observed is not None:
            _add_stage(row, "inventory", observed, item.get("inventory_as_of_raw"),
                       "observation",
                       source_identity=source_identity,
                       observed_at=item.get("inventory_as_of"))
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
                        "actual_at", "observed_at"))
    for item in prod_effective:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"),
                       item.get("market"), item.get("product_form"))
        touched["production"].append(row)
        actual_at = _text(item.get("actual_at"))
        prod_date = actual_at or item.get("available_date")
        prod_kind = "actual" if actual_at else "expected"
        if item.get("_conflict"):
            reason = item.get("_conflict_reason") or "source_payload_conflict"
            _merge_source(row, "production", "conflict",
                          item.get("observed_at"),
                          source_identity=item["_source_identity"],
                          reason=reason)
            _mark_unknown(row, "production", reason)
            for record in item["_records"]:
                rec_actual = _text(record.get("actual_at"))
                _add_stage(row, "in_production", _dec(record.get("qty")),
                           rec_actual or record.get("available_date"),
                           "actual" if rec_actual else "expected",
                           source_identity=item["_source_identity"],
                           conflict=True,
                           observed_at=record.get("observed_at"))
            continue
        if item.get("_identity_missing"):
            _merge_source(row, "production", "unknown",
                          item.get("observed_at"), "source_identity_missing")
            _mark_unknown(row, "production", "source_identity_missing")
            _add_stage(row, "in_production", _dec(item.get("qty")),
                       prod_date, prod_kind,
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
                       prod_date, prod_kind,
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
        _add_stage(row, "in_production", qty, prod_date, prod_kind,
                   source_identity=item["_source_identity"],
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
        first = items[0]
        parsed_as_of, _, as_of_status = _time_parts(first.get("as_of"))
        proven = first.get("inventory_time_proven")
        row["inventory_time_proven"] = (
            (parsed_as_of is not None and as_of_status == "known")
            if proven is None else bool(proven))
        freshness = first.get("inventory_freshness")
        if freshness is None:
            now = _aware(as_of)
            if parsed_as_of is None or as_of_status != "known":
                freshness = "unknown_time"
            elif now is not None and parsed_as_of > now:
                freshness = "future"
            else:
                freshness = "fresh"
        row["inventory_freshness"] = freshness
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
        payload_fields=("qty", "signed_at", "received_at", "pod_uploaded_at",
                        "observed_at"))
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
                _add_receipt_stage(
                    row, record, source_identity=receipt["_source_identity"],
                    conflict=True)
            continue
        if receipt.get("_identity_missing"):
            _merge_source(row, "receipt", "unknown",
                          receipt.get("observed_at"), "source_identity_missing")
            _mark_unknown(row, "receipt", "source_identity_missing")
            _add_receipt_stage(
                row, receipt, source_identity=receipt.get("_source_identity"),
                identity_status="missing")
            continue
        qty = _dec(receipt.get("qty"))
        signed = _aware(receipt.get("signed_at"))
        received = _aware(receipt.get("received_at"))
        if qty is None:
            _merge_source(row, "receipt", "unknown",
                          receipt.get("observed_at"), "receipt_qty_unknown",
                          source_identity=receipt["_source_identity"])
            _mark_unknown(row, "receipt", "receipt_qty_unknown")
            continue
        if received:
            if signed and received < signed:
                _merge_source(row, "receipt", "conflict",
                              receipt.get("observed_at"),
                              "receipt_before_signed",
                              source_identity=receipt["_source_identity"])
                _mark_unknown(row, "receipt", "receipt_before_signed")
                _add_receipt_stage(
                    row, receipt, source_identity=receipt["_source_identity"],
                    conflict=True)
                continue
            _merge_source(row, "receipt", "proven", receipt.get("observed_at"),
                          source_identity=receipt["_source_identity"])
            _add_qty(row, "received_qty", "receipt", qty)
            row["receipt_basis"] = "tongtool_received"
            _add_receipt_stage(
                row, receipt, source_identity=receipt["_source_identity"])
        elif signed:
            _merge_source(row, "receipt", "signed_pending",
                          receipt.get("observed_at"),
                          source_identity=receipt["_source_identity"])
            _add_qty(row, "signed_pending_qty", "receipt", qty)
            row["receipt_basis"] = "signed_pending"
            _add_receipt_stage(
                row, receipt, source_identity=receipt["_source_identity"])
        else:
            status = ("pod_only" if receipt.get("pod_uploaded_at")
                      else "unknown")
            reason = ("receipt_pod_only" if status == "pod_only"
                      else "receipt_unknown")
            _merge_source(row, "receipt", status,
                          receipt.get("observed_at"), reason,
                          source_identity=receipt["_source_identity"])
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
        row["_stage_position_tranches"] = row.get("_position_tranches")
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
    stage_rows = build_stage_facts(ordered)
    stage_summary = summarize_stage_facts(stage_rows)
    for row in ordered:
        row.pop("_stage_position_tranches", None)
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
        "stage_rows": len(stage_rows),
        "stage_summary": stage_summary,
        "stage_unique_key": ["item_code", "uom", "warehouse", "purpose",
                             "tt_sku", "branch", "stage", "stage_fact_id"],
        "duplicate_keys": 0,
        "forecast_connected": False,
        "netting_ready": False,
        "auto_order": False,
        "global_qty_total": None,
        "cross_layer_total": None,
        "note": ("SO balance is demand; stage dates stay separate; layers are "
                 "never summed; forecast not connected."),
    }
    result = {"rows": ordered, "stage_rows": stage_rows,
              "stage_summary": stage_summary, "summary": summary,
              "timeline": build_timeline(ordered, as_of=as_of)}
    if as_of is not None and max_age_seconds is not None:
        result["freshness"] = assess_freshness(
            ordered, as_of=as_of, max_age_seconds=max_age_seconds)
        result["stage_freshness"] = assess_stage_freshness(
            stage_rows, as_of=as_of, max_age_seconds=max_age_seconds)
    return result


def assess_stage_freshness(facts, *, as_of, max_age_seconds):
    now = _aware(as_of)
    if now is None:
        raise ValueError("as_of must be an aware timestamp")
    counts = Counter()
    for fact in facts:
        observed = _aware(fact.get("observed_at"))
        if observed is None:
            counts["unknown"] += 1
        elif observed > now:
            counts["future"] += 1
        elif (now - observed).total_seconds() > max_age_seconds:
            counts["stale"] += 1
        else:
            counts["fresh"] += 1
    return {"rows": len(facts), "fresh": counts["fresh"],
            "stale": counts["stale"], "unknown": counts["unknown"],
            "future": counts["future"]}


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
