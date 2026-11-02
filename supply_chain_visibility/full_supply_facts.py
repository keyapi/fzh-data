# -*- coding: utf-8 -*-
"""Full supply facts: DN/PO position joined with SO, production, inventory,
transit and receipts, keeping per-stage quantity/date fragments.

Rules (colleague R1/R2):
* purpose must come from an approved mapping; missing/unknown/invalid stays
  ``unknown`` and never defaults to branch/in-house;
* inventory ``as_of`` is an observation, not an availability date;
* each stage keeps its own date fragments; different stages never conflict,
  same-stage batches (11/10, 11/20) are both retained;
* expected and actual dates stay distinguishable;
* SO balance is demand, never proven production;
* quantities stay null when the source is unknown/unavailable;
* independent DN rows are preserved; approved items without evidence are listed;
* POD upload is not a receipt; multiple waybills never copy the quantity.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

SCHEMA_VERSION = "full-supply-facts/v1"
RULE_VERSION = "2026-11-02.2"
IMPLEMENTATION_VERSION = "fzh.full_supply_facts@2026-11-02.2"

VALID_PURPOSES = ("branch", "fba")
QTY_FIELDS = ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty",
              "unresolved_qty", "so_open_qty", "in_production_qty",
              "in_production_estimated_qty", "inventory_qty", "in_transit_qty",
              "received_qty")
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


def _dec(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _text(value):
    return "" if value is None else str(value).strip()


def _aware(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo and parsed.utcoffset() is not None else None


def _purpose(value):
    purpose = _text(value)
    return purpose if purpose in VALID_PURPOSES else "unknown"


def _key(item_code, uom, warehouse, purpose, tt_sku=None, branch=""):
    return (_text(item_code), _text(uom), _text(warehouse), _purpose(purpose),
            _text(tt_sku), _text(branch))


def _row_base(key):
    purpose = key[3]
    scope = {"branch": "in_house", "fba": "external_fba"}.get(purpose, "unknown")
    reasons = ["purpose_unknown"] if purpose == "unknown" else []
    return {
        "item_code": key[0], "uom": key[1] or None, "warehouse": key[2],
        "purpose": purpose, "tt_sku": key[4] or None, "branch": key[5],
        "pool": key[2], "scope": scope,
        **{name: None for name in QTY_FIELDS},
        "inventory_as_of": None, "available_date": None,
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
        row[field] = None


def _add_qty(row, field, layer, qty):
    if qty is None:
        _mark_unknown(row, layer, "quantity_unknown_" + layer)
        return
    if layer in row.get("_unknown_layers", set()):
        return
    row[field] = str((_dec(row[field]) or Decimal(0)) + qty)


def _add_stage(row, stage, qty, date=None, date_kind=None):
    """Append a quantity/date fragment only; aggregates are handled separately."""
    if qty is None:
        return
    fragment = {"stage": stage, "qty": str(qty), "date": date,
                "date_kind": date_kind,
                "date_confidence": ({"observation": "observed",
                                     "expected": "expected",
                                     "actual": "confirmed"}.get(date_kind, "unknown"))}
    if fragment not in row["stage_quantities"]:
        row["stage_quantities"].append(fragment)


def _merge_source(row, layer, status, observed_at=None, reason=""):
    row["source_status"][layer] = status
    row["sources"].append({"layer": layer, "observed_at": observed_at})
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
                  and (not branch or not candidate[5] or candidate[5] == branch)]
    if len(candidates) == 1:
        target = rows[candidates[0]]
        # Attach explicit identity from the source; never infer it.
        if branch and not target["branch"]:
            target["branch"] = _text(branch)
        if tt_sku and not target["tt_sku"]:
            target["tt_sku"] = _text(tt_sku)
        return target
    row = rows.setdefault(key, _row_base(key))
    if len(candidates) > 1:
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
        quantities = {str(_dec(item.get("qty"))) for item in items}
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
    arrivals = [fragment for fragment in fragments
                if fragment["date_kind"] in ("expected", "actual")
                and _aware(fragment["date"]) is not None]
    if arrivals:
        earliest = min(arrivals, key=lambda item: _aware(item["date"]))
        row["available_date"] = earliest["date"]
        row["available_date_kind"] = earliest["date_kind"]
        row["date_confidence"] = ("confirmed" if earliest["date_kind"] == "actual"
                                  else "expected")
    row["unknown_reasons"] = sorted(set(row["unknown_reasons"]))
    row["source_status"] = dict(sorted(row["source_status"].items()))


def build_full_supply_facts(position_result: dict, *, so_balances=(),
                            production=(), inventory=(), transit=(),
                            receipts=(), approved_items=(), as_of=None,
                            max_age_seconds=None) -> dict:
    rows = {}
    for pos in position_result.get("rows") or []:
        key = _key(pos.get("item_code"), pos.get("uom"), pos.get("warehouse"),
                   pos.get("purpose"), pos.get("tt_sku"), pos.get("branch"))
        row = rows.setdefault(key, _row_base(key))
        for field in ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty",
                      "unresolved_qty"):
            row[field] = pos.get(field)
        if any(pos.get(f) is None for f in
               ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty")):
            _mark_unknown(row, "dn_po", "dn_po_quantity_unknown")
        row["sources"].append({"layer": "dn_po", "observed_at": pos.get("as_of")})
        row["source_status"]["dn_po"] = "known"
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
                row["in_production_estimated_qty"] = str(
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

    inventory_by_row = defaultdict(lambda: (None, []))
    for item in inventory:
        row = _row_for(rows, item.get("item_code"), item.get("uom"),
                       item.get("warehouse"), item.get("purpose"),
                       item.get("branch"), item.get("tt_sku"))
        inventory_by_row[id(row)][1].append(item)
    for _identity, (_unused, items) in inventory_by_row.items():
        row = items and _row_for(rows, items[0].get("item_code"),
                                 items[0].get("uom"), items[0].get("warehouse"),
                                 items[0].get("purpose"), items[0].get("branch"),
                                 items[0].get("tt_sku"))
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
            _add_stage(row, "inventory", qty, item.get("as_of"), "observation")

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
    summary = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "rows": len(ordered),
        "by_purpose": dict(sorted(Counter(row["purpose"] for row in ordered).items())),
        "unknown_purpose_rows": sum(1 for row in ordered
                                    if row["purpose"] == "unknown"),
        "unknown_rows": sum(1 for row in ordered if row["unknown_reasons"]),
        "forecast_connected": False,
        "netting_ready": False,
        "auto_order": False,
        "global_qty_total": None,
        "note": "SO balance is demand; stage dates stay separate; forecast not connected.",
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
            date = _aware(fragment.get("date"))
            if date and date < now:
                alerts.add("date_in_past")
            stages.append({"node": fragment["stage"], "qty": fragment["qty"],
                           "date": fragment.get("date"),
                           "date_kind": fragment.get("date_kind"),
                           "date_confidence": fragment.get("date_confidence")})
        events.append({
            "item_code": row["item_code"], "uom": row["uom"],
            "warehouse": row["warehouse"], "purpose": row["purpose"],
            "branch": row["branch"], "scope": row["scope"],
            "stages": stages, "next_node": row["next_node"],
            "alerts": sorted(alerts),
            "unknown_reasons": row["unknown_reasons"],
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
