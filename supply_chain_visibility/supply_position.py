"""Offline DN/PO supply consumer. No network calls or business writes.

PO status 3 closes only audited included rows under the approved coarse policy.
This first consumer does not invent SO/production coverage or available stock.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import uuid

from warehouse_restock.delivery_facts_adapter import validate_delivery_snapshot, _scope_codes


VERSION = "supply-position/v1"
QUANTITIES = ("dn_net_qty", "po_completed_assumed_qty", "open_po_qty", "unresolved_qty")


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timezone-aware timestamp required") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed


def _qty(value, *, signed=False):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a quantity")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid quantity") from exc
    if not number.is_finite() or (number < 0 and not signed):
        raise ValueError("quantity must be finite and non-negative")
    return number


def _equal(left, right):
    a, b = _qty(left), _qty(right)
    return a is not None and b is not None and a == b


def _key(row):
    return row.get("delivery_note"), row.get("dn_item")


def _audit_for(line, creations):
    active = [c for c in creations if c.get("delivery_note") == line["delivery_note"]
              and not c.get("superseded_by")
              and c.get("status") in ("confirmed", "prepared", "request_sent", "outcome_unknown")]
    if not active:
        return None, None, "legacy_or_missing_creation_audit"
    if len(active) != 1:
        return None, None, "ambiguous_creation_audit"
    creation = active[0]
    if creation.get("status") != "confirmed":
        return creation, None, "creation_not_confirmed"
    if not isinstance(creation.get("lines"), list):
        return creation, None, "creation_lines_not_exported"
    matches = [x for x in creation["lines"] if x.get("dn_item") == line["delivery_note_item"]]
    if len(matches) != 1:
        return creation, None, "missing_or_ambiguous_audit_line"
    return creation, matches[0], None


def _classify(line, mapping, creations, statuses, as_of, max_age):
    creation, audit, error = _audit_for(line, creations)
    if error:
        return "unresolved_qty", error, creation
    outcome = audit.get("outcome")
    if outcome != "included":
        return "unresolved_qty", "audit_" + str(outcome or "unknown"), creation
    if mapping is None:
        return "unresolved_qty", "mapping_unknown", creation
    # Audit is a creation-time record, not proof that a subsequently edited DN
    # was also included. Do not silently reuse changed rows or cross units.
    if (audit.get("item_code") != line.get("item_code")
            or audit.get("uom") != line.get("uom")
            or audit.get("tt_sku") != mapping.get("tt_sku")
            or not _equal(audit.get("qty"), line.get("qty", line.get("actual_qty")))
            or not _equal(audit.get("contribution_qty"), audit.get("qty"))):
        return "unresolved_qty", "audit_identity_or_quantity_drift", creation
    code = creation.get("purchase_order_code")
    result = statuses["results"].get(code)
    if not code or not isinstance(result, dict) or result.get("found") is not True:
        reason = result.get("reason") if isinstance(result, dict) else "not_queried"
        return "unresolved_qty", "po_" + str(reason or "unknown"), creation
    if (result.get("identity") or {}).get("purchaseOrderCode") != code:
        return "unresolved_qty", "po_identity_unverified", creation
    observed = result.get("observed_at") or statuses.get("observed_at")
    try:
        age = (as_of - _time(observed)).total_seconds()
    except ValueError:
        return "unresolved_qty", "po_observed_at_unknown", creation
    if age < 0 or age > max_age:
        return "unresolved_qty", "po_status_stale_or_future", creation
    raw = result.get("status")
    if isinstance(raw, bool):
        raw = None
    bucket, reason = {
        "0": ("open_po_qty", "po_open"),
        "1": ("unresolved_qty", "partial_item_allocation_unknown"),
        "2": ("unresolved_qty", "short_receipt_allocation_unknown"),
        "3": ("po_completed_assumed_qty", "po_status_assumed"),
        "4": ("unresolved_qty", "po_voided"),
    }.get(str(raw), ("unresolved_qty", "po_status_unknown"))
    return bucket, reason, creation


def build_position(payload):
    """Build one row per item/SKU/destination/purpose/UOM, with lossless evidence.

    `mappings` are explicitly approved per-DN-line B records, not guessed from
    Item prefixes or source warehouses. Quantities remain in the DN UOM.
    """
    if payload.get("schema_version") != "supply-position-input/v1":
        raise ValueError("unsupported supply position input schema")
    as_of = _time(payload["as_of"])
    if not payload.get("mapping_version"):
        raise ValueError("mapping_version required")
    delivery = payload["delivery"]
    gate = validate_delivery_snapshot(delivery)
    if gate["status"] != "ok":
        raise ValueError("approved scope required; hash is integrity, not authority")
    max_age = payload.get("max_status_age_seconds", 900)
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0:
        raise ValueError("max_status_age_seconds must be a positive integer")
    statuses = payload["po_statuses"]
    if not isinstance(statuses.get("results"), dict):
        raise ValueError("po_statuses.results must be an object keyed by PO code")
    creations = payload["creations"]
    if not isinstance(creations, list) or not all(isinstance(c, dict) for c in creations):
        raise ValueError("creations must be exported creation documents")
    mappings = {}
    for m in payload["mappings"]:
        key = _key(m)
        if not all(key) or key in mappings:
            raise ValueError("mapping must have a unique DN/line key")
        if not all(m.get(k) for k in ("item_code", "tt_sku", "warehouse", "uom", "evidence")):
            raise ValueError("mapping missing identity/warehouse/UOM/evidence")
        if m.get("purpose") not in ("branch", "fba", "unknown"):
            raise ValueError("mapping purpose must be branch/fba/unknown")
        mappings[key] = m
    groups = {}
    seen = set()
    outcomes = Counter()
    scope_items = set(_scope_codes(gate["scope"]["items"]))
    affected_by_returns = {
        (r.get("return_against"), r.get("item_code"), r.get("uom"))
        for r in delivery["delivery_lines"] if r.get("is_return")}
    for line in delivery["delivery_lines"]:
        key = (line.get("delivery_note"), line.get("delivery_note_item"))
        if not all(key) or key in seen:
            raise ValueError("missing or duplicate DN line identity")
        seen.add(key)
        for required in ("item_code", "uom", "docstatus", "actual_qty",
                         "quantity_status", "relevance_status"):
            if required not in line:
                raise ValueError("delivery line missing " + required)
        is_return = bool(line.get("is_return"))
        qty = _qty(line["actual_qty"], signed=is_return)
        m = mappings.get(key)
        reasons = []
        if m and (m["item_code"] != line["item_code"] or m["uom"] != line["uom"]):
            reasons.append("mapping_identity_mismatch")
            m = None
        if m is None:
            reasons.append("mapping_unknown")
        purpose = m["purpose"] if m else "unknown"
        sku, warehouse = (m["tt_sku"], m["warehouse"]) if m else (None, None)
        group = (line["item_code"], sku, warehouse, purpose, line["uom"])
        if group not in groups:
            groups[group] = {"item_code": group[0], "tt_sku": sku, "warehouse": warehouse,
                             "purpose": purpose, "uom": group[4],
                             **{k: Decimal(0) for k in QUANTITIES},
                             "unknown_quantity_lines": 0, "known_dn_net_qty": Decimal(0),
                             "line_count": 0, "return_review_lines": 0,
                             "reasons": set(), "tranches": []}
        row = groups[group]
        return_review = is_return or (key[0], line["item_code"], line["uom"]) in affected_by_returns
        if return_review:
            bucket, reason, creation = "unresolved_qty", "return_requires_review", None
            row["return_review_lines"] += 1
        else:
            bucket, reason, creation = _classify(line, m, creations, statuses, as_of, max_age)
        in_scope = line["item_code"] in scope_items and line["relevance_status"] == "in_scope"
        if not in_scope:
            bucket, reason = "unresolved_qty", "outside_or_unknown_scope"
        if type(line["docstatus"]) is not int or line["docstatus"] != 1:
            bucket, reason, qty = "unresolved_qty", "not_current_submitted_delivery", None
        elif line["quantity_status"] != "known":
            qty = None
        row["line_count"] += 1
        row["reasons"].update(reasons + [reason])
        if qty is None:
            row["unknown_quantity_lines"] += 1
        else:
            row["known_dn_net_qty"] += qty
            row["dn_net_qty"] += qty
            row[bucket] += qty
        outcomes[reason] += 1
        row["tranches"].append({
            "delivery_note": key[0], "dn_item": key[1], "qty": None if qty is None else float(qty),
            "bucket": bucket, "reason": reason, "posting_date": line.get("posting_date"),
            "creation": creation.get("name") if creation else None,
            "po_code": creation.get("purchase_order_code") if creation else None,
            "receipt_basis": "po_status_assumed" if bucket == "po_completed_assumed_qty" else None,
            "actual_receipt_at": None, "available_date": None,
            "mapping_evidence": m["evidence"] if m else None})
    rows = []
    for group in sorted(groups, key=lambda k: tuple(str(v or "") for v in k)):
        row = groups[group]
        if row["dn_net_qty"] != sum(row[k] for k in QUANTITIES[1:]):
            raise ValueError("quantity conservation failed")
        for k in QUANTITIES:
            row[k] = None if row["unknown_quantity_lines"] or row["return_review_lines"] else float(row[k])
        row["known_dn_net_qty"] = float(row["known_dn_net_qty"])
        row["reasons"] = sorted(row["reasons"])
        row.update({"as_of": payload["as_of"], "mapping_version": payload["mapping_version"],
                    "available_stock_qty": None, "open_order_qty": None,
                    "in_production_qty": None, "inventory_inclusion_status": "unknown",
                    "netting_ready": False, "auto_order": False,
                    "action": "excluded_fba" if row["purpose"] == "fba" else "manual_review",
                    "coverage": "dn_po_only"})
        rows.append(row)
    observed_items = {r["item_code"] for r in rows}
    for code in sorted(scope_items - observed_items):
        rows.append({"item_code": code, "tt_sku": None, "warehouse": None,
                     "purpose": "unknown", "uom": None,
                     **{k: None for k in QUANTITIES}, "known_dn_net_qty": 0.0,
                     "unknown_quantity_lines": 0, "line_count": 0, "return_review_lines": 0,
                     "reasons": ["no_observed_delivery"], "tranches": [],
                     "as_of": payload["as_of"], "mapping_version": payload["mapping_version"],
                     "available_stock_qty": None, "open_order_qty": None,
                     "in_production_qty": None, "inventory_inclusion_status": "unknown",
                     "netting_ready": False, "auto_order": False,
                     "action": "manual_review", "coverage": "dn_po_only"})
    return {"schema_version": VERSION, "as_of": payload["as_of"], "rows": rows,
            "report": {"input_lines": len(seen), "output_groups": len(rows),
                       "accounted_lines": sum(r["line_count"] for r in rows),
                       "outcomes": dict(sorted(outcomes.items())),
                       "unused_mapping_lines": len(set(mappings) - seen),
                       "full_chain_ready": False, "scope": gate["scope"],
                       "source_versions": {k: delivery.get(k) for k in (
                           "schema_version", "rule_version", "implementation_version", "snapshot_id")},
                       "max_status_age_seconds": max_age,
                       "limitations": ["SO/production/current-stock inputs not joined",
                                       "PO completion is an approved assumption, not actual receipt",
                                       "no common server snapshot is asserted"]}}


def _attempt(out, status, **extra):
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / (".attempt-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps({"status": status,
        "observed_at": datetime.now(timezone.utc).isoformat(), **extra}), encoding="utf-8")
    os.replace(temporary, root / "last_attempt.json")


def publish_position(result, out):
    """Publish a read-back-verified version; never replace latest on failure."""
    try:
        final = _publish_position(result, out)
    except Exception as exc:
        try:
            _attempt(out, "failed", error_type=type(exc).__name__)
        except OSError:
            pass  # Preserve the original failure, including a genuinely full disk.
        raise
    try:
        _attempt(out, "succeeded", directory=final.name)
    except OSError:
        pass  # The verified latest pointer has already committed successfully.
    return final


def _publish_position(result, out):
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Reject NaN and malformed content before touching the current pointer.
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    # Write to a unique unpublished version. Only the pointer is replaced;
    # renaming an open directory is unreliable on Windows (Arrow/indexers).
    staging = root / ("snapshot-" + token)
    staging.mkdir()
    schema = pa.schema([
        *[(k, pa.string()) for k in ("item_code", "tt_sku", "warehouse", "purpose", "uom",
                                    "as_of", "mapping_version", "inventory_inclusion_status",
                                    "action", "coverage")],
        *[(k, pa.float64()) for k in (*QUANTITIES, "known_dn_net_qty", "available_stock_qty",
                                     "open_order_qty", "in_production_qty")],
        ("line_count", pa.int64()), ("unknown_quantity_lines", pa.int64()),
        ("return_review_lines", pa.int64()),
        ("netting_ready", pa.bool_()), ("auto_order", pa.bool_()),
        ("reasons_json", pa.string()), ("tranches_json", pa.string())])
    records = []
    for row in result["rows"]:
        record = {k: v for k, v in row.items() if k not in ("reasons", "tranches")}
        record["reasons_json"] = json.dumps(row["reasons"], ensure_ascii=False, allow_nan=False)
        record["tranches_json"] = json.dumps(row["tranches"], ensure_ascii=False, allow_nan=False)
        records.append(record)
    table = pa.Table.from_pylist(records, schema=schema)
    file = staging / "supply_position.parquet"
    pq.write_table(table, file, compression="zstd")
    if not pq.read_table(file).equals(table):
        raise ValueError("Parquet readback mismatch")
    manifest = {"schema_version": VERSION, "as_of": result["as_of"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "input_result_sha256": hashlib.sha256(encoded).hexdigest(),
                "file": file.name, "rows": table.num_rows,
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                "full_chain_ready": False, "report": result["report"]}
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (staging / "report.json").write_bytes(encoded)
    final = staging
    pointer = root / (".latest-" + token)
    pointer.write_text(json.dumps({"directory": final.name, "manifest": "manifest.json"}), encoding="utf-8")
    os.replace(pointer, root / "latest.json")
    return final


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="private JSON input envelope")
    parser.add_argument("--out", required=True, help="private versioned output directory")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        result = build_position(payload)
    except Exception as exc:
        _attempt(args.out, "failed", error_type=type(exc).__name__)
        raise
    final = publish_position(result, args.out)
    print(json.dumps({"directory": str(final), "report": result["report"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
