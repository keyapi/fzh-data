# -*- coding: utf-8 -*-
"""Full supply facts v2: DN/PO position joined with SO, production, inventory,
transit, receipts and local frozen A/B/C, keeping per-stage quantity/date
fragments.

Rules:
* purpose must come from an approved mapping; missing/unknown/invalid stays
  ``unknown`` and never defaults to branch/in-house;
* inventory ``as_of`` is an observation, not an availability date; date-only or
  naive source times are never assumed to be UTC;
* each stage keeps its own date fragments; different stages never conflict,
  same-stage batches (11/10, 11/20) are both retained;
* expected and actual dates stay distinguishable;
* SO balance is demand, never proven production;
* quantities stay null when the source is unknown/unavailable; estimated is
  never merged into proven;
* independent DN rows are preserved; approved items without evidence are listed;
* POD upload is not a receipt; multiple waybills never copy the quantity;
* local A/B/C inventory attaches by exact full key only and never fans a
  physical CG pool across branches;
* layers are never summed into one "total supply"; PO completion is an approved
  assumption, not proof of receipt.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

SCHEMA_VERSION = "full-supply-facts/v2"
RULE_VERSION = "2026-11-02.3"
IMPLEMENTATION_VERSION = "fzh.full_supply_facts@2026-11-02.3"
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
    "inventory": ("inventory_qty",),
    "in_transit": ("in_transit_qty",),
    "receipt": ("received_qty",),
}
QTY_BY_STAGE = {
    "po_completed_assumed": "po_completed_assumed_qty",
    "po_open": "open_po_qty",
    "in_production": "in_production_qty",
    "in_production_estimated": "in_production_estimated_qty",
    "inventory": "inventory_qty",
    "in_transit": "in_transit_qty",
    "received": "received_qty",
}


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
        "inventory_freshness": "unknown",
        "inventory_inclusion_status": "unknown",
        "attribution_status": None, "abc_identity_source": None,
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


def _add_stage(row, stage, qty, date_value=None, date_kind=None):
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
                                     "actual": "confirmed"}.get(date_kind, "unknown"))}
    if fragment not in row["stage_quantities"]:
        row["stage_quantities"].append(fragment)


def _merge_source(row, layer, status, observed_at=None, reason=""):
    row["source_status"][layer] = status
    parsed, raw, time_status = _time_parts(observed_at)
    source = {"layer": layer,
              "observed_at": parsed.isoformat() if parsed else None,
              "observed_at_raw": raw, "time_status": time_status}
    if source not in row["sources"]:
        row["sources"].append(source)
    if reason:
        row["unknown_reasons"].append(reason)


def _row_for(rows, item, uom, warehouse, purpose, branch="", tt_sku=None):
    """Attach a non-DN source to the DN/PO row without guessing tt_sku/branch."""
    key = _key(item, uom, warehouse, purpose, tt_sku, branch)
    if key in rows:
        return rows[key]
    candidates = [candidate for candidate, row in rows.items()
                  if candidate[0] == key[0] and candidate[1] == key[1]
                  and candidate[2] == key[2] and candidate[3] == key[3]
                  and (not key[4] or not candidate[4] or candidate[4] == key[4])
                  and (not key[5] or not candidate[5] or candidate[5] == key[5])]
    if len(candidates) == 1:
        target = rows[candidates[0]]
        # Attach explicit identity from the source; never infer it.
        if branch and not target["branch"]:
            target["branch"] = _text(branch)
            target["unknown_reasons"] = [
                reason for reason in target["unknown_reasons"]
                if reason != "branch_unknown"]
        if tt_sku and not target["tt_sku"]:
            target["tt_sku"] = _text(tt_sku)
            target["unknown_reasons"] = [
                reason for reason in target["unknown_reasons"]
                if reason != "tt_sku_unknown"]
        # Keep the lookup identity in sync with explicit fields just attached.
        attached_key = _key(target["item_code"], target["uom"], target["warehouse"],
                            target["purpose"], target["tt_sku"], target["branch"])
        if attached_key != candidates[0]:
            del rows[candidates[0]]
            rows[attached_key] = target
        return target
    row = rows.setdefault(key, _row_base(key))
    if len(candidates) > 1:
        row["unknown_reasons"].append("target_key_ambiguous")
    return row


def _row_abc(rows, key, *, allow_enrich=True):
    """Attach ABC inventory; fill only explicitly supplied empty dimensions.

    A DN/PO row may lack branch/tt_sku because the position grain does not
    carry them. If exactly one candidate matches on the remaining dimensions,
    adopt the explicit ABC identity (B is the authority), never a guessed or
    similar value. Multiple candidates stay ambiguous and are not merged.
    """
    if key in rows:
        return rows[key]
    candidates = [candidate for candidate in rows
                  if candidate[0] == key[0] and candidate[1] == key[1]
                  and candidate[2] == key[2] and candidate[3] == key[3]
                  and (not candidate[4] or not key[4] or candidate[4] == key[4])
                  and (not candidate[5] or not key[5] or candidate[5] == key[5])]
    if allow_enrich and len(candidates) == 1:
        row = rows.pop(candidates[0])
        if key[4] and not row["tt_sku"]:
            row["tt_sku"] = key[4]
            row["unknown_reasons"] = [
                reason for reason in row["unknown_reasons"]
                if reason != "tt_sku_unknown"]
        if key[5] and not row["branch"]:
            row["branch"] = key[5]
            row["unknown_reasons"] = [
                reason for reason in row["unknown_reasons"]
                if reason != "branch_unknown"]
        attached = _key(row["item_code"], row["uom"], row["warehouse"],
                        row["purpose"], row["tt_sku"], row["branch"])
        rows[attached] = row
        return row
    row = rows.setdefault(key, _row_base(key))
    if len(candidates) > 1 or (candidates and not allow_enrich):
        row["unknown_reasons"].append("target_key_ambiguous")
    return row


def collapse_waybills(events: Iterable[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for event in events:
        key = (_text(event.get("delivery_note")), _text(event.get("item_code")),
               _text(event.get("uom")))
        grouped[key].append(event)
    out = []
    for key, items in sorted(grouped.items()):
        numbers = {_text(item.get("waybill")) for item in items
                   if _text(item.get("waybill"))}
        if len(numbers) > 1:
            merged = dict(items[0])
            merged.update({"qty": None, "qty_status": "unknown",
                           "reason": "multi_waybill_allocation_unknown",
                           "waybill_count": len(numbers)})
            out.append(merged)
            continue
        if len(items) == 1:
            out.append(dict(items[0]))
            continue
        quantities = {str(_qty(item.get("qty"))) for item in items}
        if len(numbers) == 1 and len(quantities) == 1:
            out.append(dict(items[0]))
            continue
        merged = dict(items[0])
        merged.update({
            "qty": None, "qty_status": "unknown",
            "reason": ("duplicate_waybill_quantity_conflict"
                       if numbers else "missing_waybill_duplicate_events")})
        out.append(merged)
    return out


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


def build_full_supply_facts(position_result: dict, *, so_balances=(),
                            production=(), inventory=(), abc_inventory=(),
                            transit=(), receipts=(), approved_items=(), as_of=None,
                            max_age_seconds=None) -> dict:
    rows = {}
    for pos in position_result.get("rows") or []:
        key = _key(pos.get("item_code"), pos.get("uom"), pos.get("warehouse"),
                   pos.get("purpose"), pos.get("tt_sku"), pos.get("branch"))
        payload = (pos.get("dn_net_qty"), pos.get("po_completed_assumed_qty"),
                   pos.get("open_po_qty"), pos.get("unresolved_qty"),
                   pos.get("as_of"))
        if key in rows:
            existing = tuple(rows[key].get(field) for field in
                             ("dn_net_qty", "po_completed_assumed_qty",
                              "open_po_qty", "unresolved_qty"))
            if existing != tuple(_qty(value, signed=(index == 0))
                                 for index, value in enumerate(payload[:4])):
                raise ValueError("duplicate_target_key")
            continue
        row = rows.setdefault(key, _row_base(key))
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
        unresolved = _dec(pos.get("unresolved_qty"))
        pending = (unresolved is None or unresolved > 0 or pos.get("unknown_quantity_lines")
                   or pos.get("return_review_lines"))
        row["source_status"]["dn_po"] = "partial" if pending else "known"
        if pending:
            row["unknown_reasons"].extend(pos.get("reasons") or [])
            row["unknown_reasons"].append("dn_po_unresolved")
        observations = source_report.get("po_source_observed_at") or {}
        for code in sorted({t.get("po_code") for t in pos.get("tranches") or [] if t.get("po_code")}):
            _merge_source(row, "po_status", "known", observations.get(code))
        _add_stage(row, "po_completed_assumed",
                   _dec(pos.get("po_completed_assumed_qty")),
                   pos.get("as_of"), "observation")
        _add_stage(row, "po_open", _dec(pos.get("open_po_qty")), None, None)

    for item in so_balances:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        status = _text(item.get("source_status") or "known")
        qty = _dec(item.get("so_open_qty")) if status == "known" else None
        _merge_source(row, "so_demand", status, item.get("observed_at"),
                      "" if qty is not None else "so_open_unknown")
        _add_qty(row, "so_open_qty", "so_demand", qty)

    for item in production:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        evidence = _text(item.get("evidence_status") or "unknown")
        qty = _dec(item.get("qty"))
        if evidence == "estimated":
            _merge_source(row, "production", evidence, item.get("observed_at"))
            if qty is not None:
                row["in_production_estimated_qty"] = _qty(
                    (_dec(row["in_production_estimated_qty"]) or Decimal(0)) + qty)
            _add_stage(row, "in_production_estimated", qty,
                       item.get("available_date"), "expected")
            continue
        if evidence != "proven":
            _merge_source(row, "production", evidence, item.get("observed_at"),
                          "production_" + (evidence or "unknown"))
            _mark_unknown(row, "production", "production_not_proven")
            continue
        _merge_source(row, "production", "proven", item.get("observed_at"))
        _add_qty(row, "in_production_qty", "production", qty)
        _add_stage(row, "in_production", qty, item.get("available_date"),
                   "expected")

    inventory_by_row = defaultdict(list)
    for item in inventory:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        inventory_by_row[id(row)].append(item)
    for items in inventory_by_row.values():
        row = _row_for(rows, items[0].get("item_code"),
                       items[0].get("uom"), items[0].get("warehouse"),
                       items[0].get("purpose"), items[0].get("branch"),
                       items[0].get("tt_sku"))
        row.setdefault("_inventory_sources", set()).add("generic")
        statuses = {_text(item.get("source_status") or "known") for item in items}
        identities = {(_text(item.get("as_of")), str(_dec(item.get("qty"))))
                      for item in items}
        if statuses != {"known"}:
            _merge_source(row, "inventory", "unavailable",
                          items[0].get("observed_at"),
                          "inventory_source_unavailable")
            _mark_unknown(row, "inventory", "inventory_source_unavailable")
        elif len(identities) > 1:
            _merge_source(row, "inventory", "conflict", items[0].get("as_of"),
                          "multiple_inventory_snapshots")
            _mark_unknown(row, "inventory", "multiple_inventory_snapshots")
        else:
            item = items[0]
            qty = _dec(item.get("qty"))
            _merge_source(row, "inventory", "known", item.get("as_of"))
            _add_qty(row, "inventory_qty", "inventory", qty)
            row["inventory_observed_qty"] = row["inventory_qty"]
            _add_stage(row, "inventory", qty, item.get("as_of"), "observation")

    abc_rows = list(abc_inventory or ())
    abc_branch_claims = defaultdict(set)
    for item in abc_rows:
        if item.get("branch"):
            group = (_text(item.get("item_code")), _text(item.get("uom")),
                     _text(item.get("warehouse")),
                     _purpose(item.get("purpose")),
                     _text(item.get("tt_sku")))
            abc_branch_claims[group].add(_text(item.get("branch")))
    for item in abc_rows:
        key = _key(item.get("item_code"), item.get("uom"), item.get("warehouse"),
                   item.get("purpose"), item.get("tt_sku"), item.get("branch"))
        group = (key[0], key[1], key[2], key[3], key[4])
        row = _row_abc(rows, key,
                       allow_enrich=len(abc_branch_claims[group]) <= 1)
        row.setdefault("_inventory_sources", set()).add("abc")
        row["attribution_status"] = item.get("attribution_status")
        row["abc_identity_source"] = item.get("abc_identity_source")
        row["inventory_freshness"] = item.get("inventory_freshness") or "unknown"
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
                      "" if inventory_qty is not None else "inventory_not_attributed")
        if observed is not None:
            _add_stage(row, "inventory", observed, item.get("inventory_as_of_raw"),
                       "observation")
        for reason in item.get("reasons") or []:
            if reason not in row["unknown_reasons"]:
                row["unknown_reasons"].append(reason)
        if item.get("coverage") and item.get("coverage") != "abc_inventory":
            row["coverage"] = item.get("coverage")
        if current is None and status == "known" and observed is not None:
            row["unknown_reasons"].append("inventory_not_current_available")

    for event in collapse_waybills(transit):
        row = _row_for(rows, event.get("item_code"), event.get("uom"),
                       event.get("warehouse"), event.get("purpose"),
                       event.get("branch"), event.get("tt_sku"))
        qty = _dec(event.get("qty"))
        if qty is None:
            reason = event.get("reason") or "in_transit_unknown"
            _merge_source(row, "in_transit", "unknown", event.get("observed_at"),
                          reason)
            _mark_unknown(row, "in_transit", reason)
        else:
            _merge_source(row, "in_transit", "known", event.get("observed_at"))
            _add_qty(row, "in_transit_qty", "in_transit", qty)
            _add_stage(row, "in_transit", qty, event.get("available_date"),
                       "expected")

    for receipt in receipts:
        row = _row_for(rows, receipt.get("item_code"), receipt.get("uom"),
                       receipt.get("warehouse"), receipt.get("purpose"),
                       receipt.get("branch"), receipt.get("tt_sku"))
        evidence, signed = _pod_evidence(receipt)
        qty = _dec(receipt.get("qty"))
        if evidence == "proven" and qty is not None:
            _merge_source(row, "receipt", "proven", receipt.get("observed_at"))
            _add_qty(row, "received_qty", "receipt", qty)
            row["receipt_basis"] = "signed_assumed"
            _add_stage(row, "received", qty, signed.isoformat(), "actual")
        else:
            reason = ("receipt_qty_unknown" if evidence == "proven"
                      else "receipt_" + evidence)
            _merge_source(row, "receipt", evidence, receipt.get("observed_at"),
                          reason)
            _mark_unknown(row, "receipt", reason)

    for code in approved_items or ():
        if not any(row["item_code"] == _text(code) for row in rows.values()):
            key = _key(code, "", "", "unknown")
            row = rows.setdefault(key, _row_base(key))
            row["unknown_reasons"].append("no_observed_supply_or_demand")
            row["coverage"] = "approved_item_without_evidence"

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
        "inventory_current_available_rows": sum(
            1 for row in ordered if row["inventory_current_available"]),
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
                           "date_confidence": fragment.get("date_confidence")})
        events.append({
            "item_code": row["item_code"], "uom": row["uom"],
            "warehouse": row["warehouse"], "purpose": row["purpose"],
            "branch": row["branch"], "tt_sku": row["tt_sku"],
            "scope": row["scope"],
            "stages": stages, "next_node": row["next_node"],
            "alerts": sorted(alerts),
            "unknown_reasons": row["unknown_reasons"],
            "inventory_freshness": row["inventory_freshness"],
            "attribution_status": row["attribution_status"],
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
