"""Read-only EN collection and adapters for the supply snapshot refresh.

Pagination itself reuses ``EN_API/supply_facts_export._paginate`` and
``_paginate_delivery`` (continuity, totals, duplicate pages, exhaustion). This
module adds cross-page version/snapshot/permission checks and converts the
server response into the inputs consumed by ``full_supply_facts``.

No network write, no PO creation, no business-data commit.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

EN_API_DIR = Path(__file__).resolve().parent.parent / "EN_API"

SUPPLY_DATASETS = (
    "lines", "stage_balances", "milestones", "availability_schedule", "links",
    "production_evidence", "shipment_progress",
)
FULFILLED_STAGES = {
    "shipped_in_transit", "arrived_not_sellable",
    "signed_pending_tongtool_receipt", "tongtool_received",
    "delivered_sellable",
}
REQUIRED_SUPPLY_SOURCES = (
    "sales_order", "job_card", "delivery_note", "shipment",
)


class CollectionError(RuntimeError):
    """Collection failed: refresh must not publish or switch latest."""

    def __init__(self, stage, source, message):
        self.stage = stage
        self.source = source
        self.message = message
        super().__init__("%s/%s: %s" % (stage, source, message))


def _text(value):
    return "" if value is None else str(value).strip()


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
    number = _dec(value, signed=signed)
    if number is None:
        return None
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _export():
    if str(EN_API_DIR) not in sys.path:
        sys.path.insert(0, str(EN_API_DIR))
    import supply_facts_export  # noqa: PLC0415
    return supply_facts_export


def _iss():
    if str(EN_API_DIR) not in sys.path:
        sys.path.insert(0, str(EN_API_DIR))
    import item_shipment_status  # noqa: PLC0415
    return item_shipment_status


def resolve_credentials(env="test", env_file=None):
    iss = _iss()
    key, secret = iss.load_credentials(env, iss.resolve_env_files(env_file))
    if not key or not secret or "your_" in key:
        raise CollectionError("collect", "credentials",
                              "EN_API/.env is missing ERP credentials")
    return key, secret, iss.ENV_URLS[env]


class HttpEnClient:
    """Thin client over the existing export module (no re-implemented API)."""

    def __init__(self, env="test", env_file=None):
        self.key, self.secret, self.base_url = resolve_credentials(env, env_file)
        self.export = _export()

    def supply_pages(self, filters, page_size, max_pages):
        return self.export._paginate(
            self.base_url, self.key, self.secret, filters, page_size,
            max_pages=max_pages)

    def delivery_pages(self, page_size, max_pages, **kwargs):
        return self.export._paginate_delivery(
            self.base_url, self.key, self.secret, page_size,
            max_pages=max_pages, **kwargs)


def _manifest(batch):
    manifest = batch.get("manifest")
    if not isinstance(manifest, dict):
        raise CollectionError("collect", "supply_facts",
                              "batch manifest missing")
    return manifest


def _signature(batch, source):
    manifest = _manifest(batch)
    coverage = manifest.get("coverage") or {}
    signature = {
        "schema_version": batch.get("schema_version"),
        "rule_version": batch.get("rule_version"),
        "implementation_version": batch.get("implementation_version"),
        "as_of": batch.get("as_of"),
        "observed_at": coverage.get("observed_at"),
        "snapshot_id": batch.get("snapshot_id"),
    }
    missing = [name for name in ("schema_version", "rule_version",
                                 "implementation_version", "as_of")
               if not signature.get(name)]
    if missing:
        raise CollectionError("collect", source,
                              "batch missing version/as_of: " + ", ".join(missing))
    if not signature.get("snapshot_id"):
        raise CollectionError("collect", source, "batch missing snapshot_id")
    if not signature.get("observed_at"):
        raise CollectionError("collect", source, "batch missing observed_at")
    return signature


def _stable_signature(signature):
    return {key: value for key, value in signature.items()
            if key != "observed_at"}


def _validate_pagination(batch, index, page_count, row_count, expected_offset,
                         expected_total, source):
    pagination = batch.get("pagination") or {}
    required = ("limit", "offset", "returned", "total", "next_offset",
                "exhausted")
    missing = [name for name in required if name not in pagination]
    if missing:
        raise CollectionError("collect", source,
                              "pagination missing: " + ", ".join(missing))
    try:
        limit = int(pagination["limit"])
        offset = int(pagination["offset"])
        returned = int(pagination["returned"])
        total = int(pagination["total"])
    except (TypeError, ValueError) as exc:
        raise CollectionError("collect", source,
                              "pagination contains non-integer values") from exc
    if limit < 1 or offset != expected_offset or returned != row_count:
        raise CollectionError(
            "collect", source,
            "pagination continuity mismatch at page %s" % index)
    if expected_total is not None and total != expected_total:
        raise CollectionError("collect", source,
                              "pagination total drift at page %s" % index)
    final = index == page_count - 1
    exhausted = pagination.get("exhausted")
    expected_next = offset + row_count
    if final:
        if exhausted is not True or pagination.get("next_offset") is not None:
            raise CollectionError("collect", source,
                                  "final page is not exhausted")
    else:
        if exhausted is not False:
            raise CollectionError("collect", source,
                                  "non-final page is exhausted")
        if not row_count or pagination.get("next_offset") is None:
            raise CollectionError("collect", source,
                                  "empty/gapped page before exhaustion")
        if int(pagination["next_offset"]) != expected_next:
            raise CollectionError("collect", source,
                                  "pagination next_offset gap")
    return total, expected_next


def _check_source_status(coverage, source):
    business_unknown = []
    for name, state in (coverage.get("source_status") or {}).items():
        state = state or {}
        reason = _text(state.get("reason"))
        if reason == "not_integrated":
            business_unknown.append({"source": name, "status": "not_integrated"})
            continue
        if state.get("available") is False:
            raise CollectionError("collect", source,
                                  "%s source unavailable: %s"
                                  % (name, reason or "unknown"))
        if state.get("restricted"):
            raise CollectionError("collect", source,
                                  "%s source restricted" % name)
    for name, flag in (coverage.get("restricted") or {}).items():
        if flag:
            raise CollectionError("collect", source,
                                  "%s restricted for this user" % name)
    if coverage.get("shipment_permission") is False:
        raise CollectionError("collect", source,
                              "shipment permission denied")
    return business_unknown


def validate_supply_batches(batches, terminated):
    if not batches:
        raise CollectionError("collect", "supply_facts", "no pages returned")
    if terminated != "exhausted":
        raise CollectionError("collect", "supply_facts",
                              "pagination terminated by %s" % terminated)
    first_signature = _signature(batches[0], "supply_facts")
    seen = set()
    business_unknown = []
    expected_offset = 0
    expected_total = None
    for index, batch in enumerate(batches):
        if batch.get("schema_version") != first_signature["schema_version"]:
            raise CollectionError("collect", "supply_facts",
                                  "schema drift at page %s" % index)
        if _stable_signature(_signature(batch, "supply_facts")) \
                != _stable_signature(first_signature):
            raise CollectionError("collect", "supply_facts",
                                  "version/snapshot drift at page %s" % index)
        if _manifest(batch).get("truncated"):
            raise CollectionError("collect", "supply_facts",
                                  "server reports truncated page")
        lines = batch.get("lines")
        if not isinstance(lines, list):
            raise CollectionError("collect", "supply_facts",
                                  "lines missing at page %s" % index)
        expected_total, expected_offset = _validate_pagination(
            batch, index, len(batches), len(lines), expected_offset,
            expected_total, "supply_facts")
        for line in lines:
            key = line.get("so_line") or line.get("so_line_id")
            if not key:
                raise CollectionError("collect", "supply_facts",
                                      "line without so_line")
            if key in seen:
                raise CollectionError("collect", "supply_facts",
                                      "duplicate so_line across pages: %s" % key)
            seen.add(key)
        coverage = _manifest(batch).get("coverage") or {}
        business_unknown.extend(_check_source_status(coverage, "supply_facts"))
    if expected_total is not None and len(seen) != expected_total:
        raise CollectionError("collect", "supply_facts",
                              "collected %s lines, expected %s"
                              % (len(seen), expected_total))
    return first_signature, _dedupe_unknown(business_unknown)


def validate_delivery_batches(batches, terminated):
    if not batches:
        return None, []
    if terminated != "exhausted":
        raise CollectionError("collect", "delivery",
                              "pagination terminated by %s" % terminated)
    first = batches[0]
    signature = {
        "schema_version": first.get("schema_version"),
        "rule_version": first.get("rule_version"),
        "implementation_version": first.get("implementation_version"),
        "snapshot_id": first.get("snapshot_id"),
        "as_of": (first.get("coverage") or {}).get("as_of"),
    }
    for name in ("schema_version", "rule_version", "implementation_version",
                 "snapshot_id", "as_of"):
        if not signature.get(name):
            raise CollectionError("collect", "delivery",
                                  "batch missing " + name)
    seen = set()
    business_unknown = []
    expected_offset = 0
    expected_total = None
    for index, batch in enumerate(batches):
        current = {
            "schema_version": batch.get("schema_version"),
            "rule_version": batch.get("rule_version"),
            "implementation_version": batch.get("implementation_version"),
            "snapshot_id": batch.get("snapshot_id"),
            "as_of": (batch.get("coverage") or {}).get("as_of"),
        }
        if current != signature:
            raise CollectionError("collect", "delivery",
                                  "version/snapshot drift at page %s" % index)
        lines = batch.get("delivery_lines") or []
        expected_total, expected_offset = _validate_pagination(
            batch, index, len(batches), len(lines), expected_offset,
            expected_total, "delivery")
        for line in lines:
            key = line.get("delivery_note_item")
            if not key:
                raise CollectionError("collect", "delivery",
                                      "delivery line without identity")
            if key in seen:
                raise CollectionError("collect", "delivery",
                                      "duplicate delivery_note_item: %s" % key)
            seen.add(key)
        business_unknown.extend(_check_source_status(
            batch.get("coverage") or {}, "delivery"))
    if expected_total is not None and len(seen) != expected_total:
        raise CollectionError("collect", "delivery",
                              "collected %s delivery lines, expected %s"
                              % (len(seen), expected_total))
    return signature, _dedupe_unknown(business_unknown)


def _dedupe_unknown(items):
    out = []
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def merge_supply(batches):
    first = batches[0]
    manifest = _manifest(first)
    merged = {name: [] for name in SUPPLY_DATASETS}
    for batch in batches:
        for name in SUPPLY_DATASETS:
            merged[name].extend(batch.get(name) or [])
    coverage = dict(manifest.get("coverage") or {})
    coverage["so_lines"] = len(merged["lines"])
    coverage["sales_orders"] = len({line.get("so") for line in merged["lines"]
                                    if line.get("so")})
    coverage["so_lines_total"] = (batches[-1].get("pagination") or {}).get(
        "total", len(merged["lines"]))
    dn_names, shipment_names = set(), set()
    for link in merged["links"]:
        for side in ("source", "target"):
            doctype = link.get(side + "_doctype")
            name = link.get(side + "_name")
            if not name:
                continue
            if doctype == "Delivery Note":
                dn_names.add(name)
            elif doctype == "Shipment" and link.get("target_is_record") is True:
                shipment_names.add(name)
    coverage["delivery_notes"] = len(dn_names)
    coverage["shipments"] = len(shipment_names)
    merged.update({
        "schema_version": first.get("schema_version"),
        "rule_version": first.get("rule_version"),
        "implementation_version": first.get("implementation_version"),
        "as_of": first.get("as_of"),
        "observed_at": coverage.get("observed_at"),
        "snapshot_id": _signature(first, "supply_facts")["snapshot_id"],
        "scope": first.get("applied_filters") or {},
        "coverage": coverage,
        "source_status": coverage.get("source_status") or {},
        "pagination": batches[-1].get("pagination") or {},
    })
    return merged


def merge_delivery(batches):
    if not batches:
        return None
    first = batches[0]
    coverage = dict(first.get("coverage") or {})
    lines = [line for batch in batches for line in batch.get("delivery_lines") or []]
    merged = {
        "schema_version": first.get("schema_version"),
        "rule_version": first.get("rule_version"),
        "implementation_version": first.get("implementation_version"),
        "snapshot_id": first.get("snapshot_id"),
        "scope": first.get("scope") or {},
        "coverage": coverage,
        "as_of": coverage.get("as_of"),
        "observed_at": coverage.get("observed_at"),
        "delivery_lines": lines,
        "pagination": {
            "limit": (first.get("pagination") or {}).get("limit"),
            "offset": 0, "returned": len(lines),
            "total": (batches[-1].get("pagination") or {}).get("total"),
            "next_offset": None, "exhausted": True, "partial": False,
        },
    }
    for name in ("association_edges", "coverage_exceptions", "physical_chain"):
        merged[name] = [row for batch in batches for row in batch.get(name) or []]
    # aggregate_all=1 makes each page carry the same full-query summaries.
    for name in ("so_fulfillment", "ambiguity_pools", "supply_ledger"):
        merged[name] = list(first.get(name) or [])
    return merged


def _b_identity(b_rows, item, uom, warehouse):
    candidates = [row for row in b_rows
                  if row.get("item_code") == item
                  and _text(row.get("uom")) == _text(uom)
                  and _text(row.get("warehouse")) == _text(warehouse)]
    if len(candidates) != 1:
        return {}
    row = candidates[0]
    return {
        "warehouse": row.get("warehouse"),
        "branch": row.get("branch") or "",
        "purpose": row.get("purpose") or "",
        "tt_sku": row.get("tt_sku") or "",
        "market": row.get("market"),
        "product_form": row.get("product_form"),
    }


def _record(item, uom, warehouse, identity, **extra):
    record = {
        "item_code": item, "uom": uom,
        "warehouse": identity.get("warehouse") or warehouse or "",
        "branch": identity.get("branch") or "",
        "purpose": identity.get("purpose") or "",
        "tt_sku": identity.get("tt_sku") or "",
        "market": identity.get("market"),
        "product_form": identity.get("product_form"),
    }
    record.update(extra)
    return record


def build_mappings(delivery_lines, b_rows):
    mappings = []
    for line in delivery_lines:
        item = line.get("item_code")
        uom = line.get("uom")
        warehouse = line.get("target_warehouse") or line.get("warehouse")
        identity = _b_identity(b_rows, item, uom, warehouse)
        if not identity or not identity.get("tt_sku"):
            continue
        purpose = identity.get("purpose")
        if purpose not in ("branch", "fba"):
            continue
        mappings.append({
            "delivery_note": line.get("delivery_note"),
            "dn_item": line.get("delivery_note_item"),
            "item_code": item, "uom": uom, "tt_sku": identity["tt_sku"],
            "warehouse": identity["warehouse"], "purpose": purpose,
            "evidence": "B-structured",
        })
    return mappings


def build_so_balances(supply, b_rows):
    balances = defaultdict(list)
    for row in supply["stage_balances"]:
        balances[row.get("so_line_id")].append(row)
    out = []
    for line in supply["lines"]:
        item = line.get("item_code")
        uom = line.get("uom")
        order_qty = _dec(line.get("qty"))
        fulfilled, unknown_fulfilled = Decimal(0), False
        for row in balances.get(line.get("so_line"), []):
            if row.get("stage") in FULFILLED_STAGES:
                qty = _dec(row.get("qty"))
                if qty is None:
                    unknown_fulfilled = True
                else:
                    fulfilled += qty
        open_qty = (None if order_qty is None or unknown_fulfilled
                    else order_qty - fulfilled)
        if open_qty is not None and open_qty < 0:
            open_qty = None
        identity = _b_identity(b_rows, item, uom, line.get("warehouse"))
        out.append(_record(
            item, uom, line.get("warehouse"), identity,
            so=line.get("so"), so_line=line.get("so_line"),
            source_ref="%s:%s" % (line.get("so"), line.get("so_line")),
            so_open_qty=open_qty,
            source_status="known" if open_qty is not None else "unknown",
            observed_at=supply.get("observed_at"),
            demand_basis="order_qty_minus_fulfilled"))
    return out


def _production_quantity(wo):
    evidence = wo.get("all_process_done") or {}
    confidence = _text(evidence.get("confidence"))
    qty = _dec(evidence.get("qty_proven"))
    if qty is not None and qty > 0 and confidence in ("proven", "mixed"):
        return qty, "proven", evidence
    qty = _dec(evidence.get("qty_estimated"))
    if qty is not None and qty > 0 and confidence in ("estimated", "mixed"):
        return qty, "estimated", evidence
    return None, None, None


def build_production(supply, b_rows):
    line_index = {line.get("so_line"): line for line in supply["lines"]}
    out = []
    for row in supply["production_evidence"]:
        line = line_index.get(row.get("so_line"), {})
        item = line.get("item_code") or row.get("line_item_code")
        uom = line.get("uom")
        warehouse = line.get("warehouse")
        for wo in row.get("work_orders") or []:
            if wo.get("wo_cancelled"):
                continue
            production_item = wo.get("production_item")
            if production_item and item and production_item != item:
                continue
            qty, status, evidence = _production_quantity(wo)
            if qty is None:
                continue
            identity = _b_identity(b_rows, item, uom, warehouse)
            out.append(_record(
                item, uom, warehouse, identity,
                source_ref=wo.get("wo") or wo.get("name"),
                work_order=wo.get("wo") or wo.get("name"),
                batch_id=wo.get("wo") or wo.get("name"),
                qty=qty, evidence_status=status,
                available_date=evidence.get("completed_at")
                or evidence.get("started_at"),
                observed_at=evidence.get("observed_at")
                or row.get("observed_at") or supply.get("observed_at")))
    return out


def build_transit(supply, b_rows):
    out = []
    progress_by_dn = defaultdict(list)
    for progress in supply.get("shipment_progress") or []:
        progress_by_dn[progress.get("dn")].append(progress)
    for row in supply.get("stage_balances") or []:
        if row.get("stage") not in ("shipped_in_transit",
                                    "arrived_not_sellable"):
            continue
        progresses = progress_by_dn.get(row.get("batch_key")) or []
        waybills = sorted({_text(item.get("logistic_number"))
                           for item in progresses
                           if _text(item.get("logistic_number"))})
        qty = (_dec(row.get("qty"))
               if row.get("qty_status") in (None, "known") else None)
        identity = _b_identity(b_rows, row.get("item_code"), row.get("uom"),
                               row.get("warehouse"))
        out.append(_record(
            row.get("item_code"), row.get("uom"), row.get("warehouse"), identity,
            source_ref=row.get("source_record") or row.get("batch_key"),
            waybill=waybills[0] if len(waybills) == 1 else None,
            batch_id=(waybills[0] if len(waybills) == 1
                      else (row.get("source_record") or row.get("batch_key"))),
            qty=qty,
            source_status="known" if qty is not None else "unknown",
            reason=("multi_waybill_allocation_unknown"
                    if len(waybills) > 1 else row.get("exclusion_reason")),
            available_date=(progresses[0].get("eta")
                            if len(progresses) == 1 else None),
            observed_at=supply.get("observed_at")))
    return out


def build_receipts(supply, b_rows):
    out = []
    progress_by_dn = defaultdict(list)
    for progress in supply.get("shipment_progress") or []:
        progress_by_dn[progress.get("dn")].append(progress)
    for row in supply.get("stage_balances") or []:
        if row.get("stage") not in ("signed_pending_tongtool_receipt",
                                    "tongtool_received",
                                    "delivered_sellable"):
            continue
        progresses = progress_by_dn.get(row.get("batch_key")) or []
        proven_progress = [item for item in progresses
                           if item.get("signed_status_proven")]
        signed_values = sorted({_text(item.get("shipment_signed_at"))
                                for item in proven_progress
                                if _text(item.get("shipment_signed_at"))})
        signed = signed_values[0] if len(signed_values) == 1 else None
        received_at = None
        if row.get("stage") in ("tongtool_received", "delivered_sellable"):
            receipt_values = sorted({
                _text(item.get("tongtool_receipt_at")
                      or item.get("tongtool_first_receipt_at")
                      or item.get("tongtool_last_receipt_at"))
                for item in progresses
                if _text(item.get("tongtool_receipt_at")
                         or item.get("tongtool_first_receipt_at")
                         or item.get("tongtool_last_receipt_at"))})
            received_at = (receipt_values[0]
                           if len(receipt_values) == 1 else None)
        identity = _b_identity(b_rows, row.get("item_code"), row.get("uom"),
                               row.get("warehouse"))
        shipments = sorted({_text(item.get("shipment"))
                            for item in progresses
                            if _text(item.get("shipment"))})
        batch_id = (shipments[0] if len(shipments) == 1
                    else (row.get("batch_key") or row.get("source_record")))
        out.append(_record(
            row.get("item_code"), row.get("uom"), row.get("warehouse"), identity,
            source_ref=row.get("source_record") or row.get("batch_key"),
            receipt_id=row.get("batch_key") or row.get("source_record"),
            batch_id=batch_id,
            qty=(_dec(row.get("qty"))
                 if row.get("qty_status") in (None, "known") else None),
            signed_at=signed,
            received_at=received_at,
            pod_uploaded_at=None,
            receipt_basis=("tongtool_received" if row.get("stage")
                           in ("tongtool_received", "delivered_sellable")
                           else "signed_assumed"),
            observed_at=supply.get("observed_at")))
    return out


def collection_status(supply, delivery, supply_signature, delivery_signature,
                      business_unknown):
    return {
        "supply_facts": {
            "status": "ok",
            "rows": {name: len(supply[name]) for name in SUPPLY_DATASETS},
            "versions": {key: supply_signature.get(key) for key in
                         ("schema_version", "rule_version",
                          "implementation_version")},
            "as_of": supply_signature.get("as_of"),
            "observed_at": supply_signature.get("observed_at"),
            "snapshot_id": supply_signature.get("snapshot_id"),
        },
        "delivery": (None if delivery is None else {
            "status": "ok",
            "rows": len(delivery["delivery_lines"]),
            "versions": {key: delivery_signature.get(key) for key in
                         ("schema_version", "rule_version",
                          "implementation_version")},
            "as_of": delivery_signature.get("as_of"),
            "snapshot_id": delivery_signature.get("snapshot_id"),
        }),
        "business_unknown": business_unknown,
    }


def collect(client, *, sales_order=None, page_size=500, max_pages=200,
            delivery_page_size=None, include_inactive=False,
            delivery_scope=None):
    """Collect supply facts + delivery facts; raise CollectionError on gaps."""
    filters = {}
    if sales_order:
        filters["sales_order"] = sales_order
        filters["include_delivered"] = 1
    supply_batches, supply_term = client.supply_pages(
        filters, page_size, max_pages)
    supply_signature, unknown = validate_supply_batches(
        supply_batches, supply_term)
    supply = merge_supply(supply_batches)
    delivery_batches, delivery_term = client.delivery_pages(
        delivery_page_size or page_size, max_pages,
        include_inactive=include_inactive, scope=delivery_scope)
    delivery_signature, delivery_unknown = validate_delivery_batches(
        delivery_batches, delivery_term)
    delivery = merge_delivery(delivery_batches)
    unknown = _dedupe_unknown(unknown + delivery_unknown)
    return {
        "supply": supply, "delivery": delivery,
        "supply_signature": supply_signature,
        "delivery_signature": delivery_signature,
        "business_unknown": unknown,
        "status": collection_status(supply, delivery, supply_signature,
                                    delivery_signature, unknown),
    }
