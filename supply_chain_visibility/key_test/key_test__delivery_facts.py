# -*- coding: utf-8 -*-
"""Delivery-Note-centric actual delivery facts (read-only, pure builders + API).

The anchor is a Delivery Note Item.  SO association is an optional, strictly
validated edge.  Target scope is injected by the authoritative
warehouse_restock input; the frozen 9-SKU list is only an acceptance fixture.
No number guessing, no auto-linking, no automatic ordering.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict

import frappe
from frappe.utils import now_datetime

SCHEMA_VERSION = "supply-facts/v3"
RULE_VERSION = "2026-10-30.2"
IMPLEMENTATION_VERSION = "key_test.delivery_facts@2026-10-30.2"

# Acceptance fixture only. It is NOT an approved business target list.
ACCEPTANCE_FIXTURE_VERSION = "jack_w1_sample9_2026-10-26"
ACCEPTANCE_FIXTURE_ITEMS = {
    "KS0156-NYBDSFH-52x52x5-BLACK": {"customer_sku": "TT0031038K0062927", "slot": "S1_urgent"},
    "PK#KS0001-XMMBS-100-HEMPNATURAL": {"customer_sku": "C/Linen-Natural-100-688-wow", "slot": "S2_overlap_1"},
    "ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45": {"customer_sku": "TT0312701K0064561", "slot": "S2_overlap_2"},
    "PK#KS0001-QDKTR-100-DEEPGREY": {"customer_sku": "CENCord995-DKGrey-97", "slot": "S3_in_production"},
    "PK#KS0001-CMKTR-100-WHITE": {"customer_sku": "C/Cord-White-100-706-wow", "slot": "S5_po_eta_uncertain"},
    "PK#KS0001-PR-100-WHITE": {"customer_sku": "C/Velvet-White-100-664-wow", "slot": "S6_zero_stock_1"},
    "KS0121-KQC-194-WHITE": {"customer_sku": "TT0031010K0062880", "slot": "S6_zero_stock_2"},
    "PK#KS0001-DM-194-IVORY": {"customer_sku": "CEN1607NLinen-Ivory-194", "slot": "S7_in_stock_sufficient"},
    "PK#KS0001-DM-100-GREY": {"customer_sku": "CENKZ1323-LTGrey-97", "slot": "S8_in_stock_short"},
}

FILTER_KEYS = {
    "sales_order", "customer", "item_code", "from_date", "to_date",
    "association_status", "relevance_status", "include_unlinked",
    "include_inactive", "limit", "offset",
}
ASSOCIATION_VALUES = {
    "linked", "so_header_only", "unlinked", "ambiguous", "conflict", "restricted",
}
RELEVANCE_VALUES = {"in_scope", "out_of_scope", "unknown"}
FRAMEWORK_ARGS = {"cmd", "csrf_token", "_"}
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000
SORT_KEYS = ["posting_date", "delivery_note", "idx", "delivery_note_item"]


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _finite(value):
    """Strict finite number: bool/None/NaN/Infinity/text → None."""
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


def _day(value):
    return str(value)[:10] if value else None


def _iso(value):
    return str(value).replace(" ", "T")[:19] if value else None


def normalize_scope(raw):
    """Validate authoritative scope input from warehouse_restock."""
    pending = {"status": "pending", "source": None, "version": None,
               "hash": None, "items": {}, "reason": "no_authoritative_scope"}
    if raw in (None, "", {}):
        return pending
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return dict(pending, status="invalid", reason="scope_not_json")
    if not isinstance(raw, dict):
        return dict(pending, status="invalid", reason="scope_not_object")
    source, version, expected_hash = (_text(raw.get("source")),
                                      _text(raw.get("version")),
                                      _text(raw.get("hash")))
    items_raw = raw.get("items")
    if not source or not version or not expected_hash or not isinstance(items_raw, list):
        return dict(pending, status="invalid", reason="scope_fields_missing")
    items = {}
    codes = []
    for entry in items_raw:
        if isinstance(entry, str):
            code = entry.strip()
            meta = {}
        elif isinstance(entry, dict):
            code = _text(entry.get("item_code"))
            meta = {key: value for key, value in entry.items() if key != "item_code"}
        else:
            return dict(pending, status="invalid", reason="scope_item_invalid")
        if not code:
            return dict(pending, status="invalid", reason="scope_item_blank")
        items[code] = meta
        codes.append(code)
    canonical = json.dumps({"source": source, "version": version,
                            "items": sorted(set(codes))},
                           sort_keys=True, ensure_ascii=False)
    actual_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        return dict(pending, status="invalid", reason="scope_hash_mismatch",
                    source=source, version=version, hash=expected_hash,
                    computed_hash=actual_hash, items=items)
    return {"status": "provided", "source": source, "version": version,
            "hash": expected_hash, "items": items, "reason": ""}


def scope_for_item(item_code, scope):
    code = _text(item_code)
    if scope.get("status") != "provided":
        return "unknown", "scope_" + _text(scope.get("status") or "pending")
    if not code:
        return "unknown", "missing_item_code"
    if code in (scope.get("items") or {}):
        return "in_scope", ""
    return "out_of_scope", "not_in_authoritative_scope"


def uom_evidence(item):
    qty = _finite(item.get("qty"))
    stock_qty = _finite(item.get("stock_qty"))
    factor = _finite(item.get("conversion_factor"))
    uom = _text(item.get("uom"))
    stock_uom = _text(item.get("stock_uom"))
    if qty is None:
        return "unknown", "invalid_quantity"
    magnitude = abs(qty)
    if not uom or not stock_uom:
        return "unknown", "uom_missing"
    if uom == stock_uom and (stock_qty is None
                             or abs(abs(stock_qty) - magnitude) < 1e-6):
        return "known", "same_uom"
    if factor is not None and factor > 0 and stock_qty is not None \
            and abs(abs(stock_qty) - magnitude * factor) < 1e-6:
        return "known", "conversion_factor"
    return "unknown", "conversion_unproven"


def _association(item, dn, so_headers, so_items_by_name, so_items_by_parent,
                 permitted_sos, candidates):
    so_detail = _text(item.get("so_detail"))
    so_header = _text(item.get("against_sales_order"))
    candidates_for_item = candidates.get(
        (_text(dn.get("customer")), _text(item.get("item_code"))), [])
    if so_detail:
        if not so_header:
            return ("conflict", None, None, "so_header_missing", candidates_for_item)
        so_item = so_items_by_name.get(so_detail)
        if so_item is None:
            if so_header not in permitted_sos:
                return ("restricted", None, None, "so_not_readable", [])
            return ("conflict", None, None, "so_detail_not_found",
                    candidates_for_item)
        parent = _text(so_item.get("parent"))
        if parent != so_header:
            return ("conflict", None, None, "so_detail_parent_mismatch",
                    candidates_for_item)
        if parent not in permitted_sos:
            return ("restricted", None, None, "so_not_readable", [])
        header = so_headers.get(parent) or {}
        if int(header.get("docstatus") or 0) != 1:
            return ("conflict", parent, so_detail, "so_not_submitted",
                    candidates_for_item)
        if _text(so_item.get("item_code")) != _text(item.get("item_code")):
            return ("conflict", parent, so_detail, "so_item_code_mismatch",
                    candidates_for_item)
        if _text(so_item.get("uom")) != _text(item.get("uom")):
            return ("conflict", parent, so_detail, "so_uom_mismatch",
                    candidates_for_item)
        if _text(header.get("customer")) != _text(dn.get("customer")):
            return ("conflict", parent, so_detail, "so_customer_mismatch",
                    candidates_for_item)
        return ("linked", parent, so_detail, "", [])
    if so_header:
        if so_header not in permitted_sos:
            return ("restricted", None, None, "so_not_readable", [])
        header = so_headers.get(so_header) or {}
        if int(header.get("docstatus") or 0) != 1:
            return ("conflict", so_header, None, "so_not_submitted",
                    candidates_for_item)
        if _text(header.get("customer")) != _text(dn.get("customer")):
            return ("conflict", so_header, None, "so_customer_mismatch",
                    candidates_for_item)
        matches = [row for row in so_items_by_parent.get(so_header, [])
                   if _text(row.get("item_code")) == _text(item.get("item_code"))]
        lines = [{"so": so_header, "so_line": row.get("name"),
                  "qty": row.get("qty"), "uom": row.get("uom")} for row in matches]
        if len(matches) == 1:
            return ("so_header_only", so_header, None,
                    "so_header_only_unique_item_candidate", lines)
        if len(matches) > 1:
            return ("ambiguous", so_header, None, "multiple_so_lines_same_item", lines)
        return ("conflict", so_header, None, "so_item_not_found", candidates_for_item)
    return ("unlinked", None, None, "no_so_reference", candidates_for_item)


def _logistics_for_dn(dn_name, logistics):
    numbers = (logistics.get("numbers_by_dn") or {}).get(dn_name, [])
    shipments = logistics.get("shipment_by_number") or {}
    resolved = [shipments.get(entry.get("number")) for entry in numbers]
    resolved = [row for row in resolved if row]
    if not logistics.get("shipment_permission", True):
        return "permission", numbers, resolved
    if not numbers:
        return "no_waybill", numbers, resolved
    if any(row.get("identity_conflict") for row in resolved):
        return "identity_conflict", numbers, resolved
    if len(numbers) > 1:
        return "allocation_unknown", numbers, resolved
    if not resolved:
        return "unresolved_waybill", numbers, resolved
    return "linked", numbers, resolved


def group_key(line):
    return (line.get("item_code") or "", line.get("uom") or "",
            line.get("customer") or "", line.get("warehouse") or "",
            line.get("channel") or "unknown")


def _safe_sums(lines):
    total = 0.0
    unknown = 0
    for line in lines:
        value = _finite(line.get("actual_qty"))
        if value is None:
            unknown += 1
        else:
            total += value
    return round(total, 6), unknown


def summarize_lines(lines, so_items_by_name):
    """Build SO fulfillment / ambiguity pools / supply ledger for a line set."""
    linked_by_line = defaultdict(float)
    so_line_meta = defaultdict(list)
    for line in lines:
        if line.get("association_status") != "linked" or not line.get("so_line"):
            continue
        value = _finite(line.get("actual_qty"))
        if value is None:
            return {
                "so_fulfillment": [], "ambiguity_pools": [], "supply_ledger": [],
                "reason": "linked_delivery_quantity_unknown",
            }
        linked_by_line[(line["so"], line["so_line"])] += value
        so_line_meta[(line["so"], line["so_line"])].append(line)
    so_fulfillment = []
    for key in sorted(so_line_meta, key=lambda item: (str(item[0]), str(item[1]))):
        line = so_line_meta[key][0]
        so_item = so_items_by_name.get(key[1]) or {}
        so_qty = _round(so_item.get("qty"))
        order_uom = _text(so_item.get("uom"))
        if so_qty is None or not order_uom or order_uom != _text(line.get("uom")):
            open_qty = None
            open_status = "unknown_uom_or_quantity"
        else:
            open_qty = max(0.0, round(so_qty - linked_by_line[key], 6))
            open_status = "known"
        so_fulfillment.append({
            "so": key[0], "so_line": key[1], "item_code": line["item_code"],
            "uom": line["uom"], "warehouse": line.get("warehouse"),
            "customer": line.get("customer"),
            "channel": line.get("channel") or "unknown",
            "so_qty": so_qty,
            "linked_delivered_qty": round(linked_by_line[key], 6),
            "so_open_qty": open_qty,
            "unresolved_demand_qty": open_qty,
            "potential_overlap_qty": None,
            "confirmed_additional_supply_qty": None,
            "open_status": open_status,
            "eligible": False,
            "note": ("无独立物理证据，SO 余额只记 unresolved demand；"
                     "潜在重叠见 ambiguity_pools"),
        })
    # Ambiguity pools: group sums only, never greedy allocation to SO lines.
    so_open = defaultdict(float)
    so_open_unknown = defaultdict(int)
    so_lines_by_group = defaultdict(list)
    for row in so_fulfillment:
        key = (row["item_code"] or "", row["uom"] or "",
               row.get("customer") or "", row.get("warehouse") or "",
               row.get("channel") or "unknown")
        so_lines_by_group[key].append(row)
        if row["so_open_qty"] is None:
            so_open_unknown[key] += 1
        else:
            so_open[key] += row["so_open_qty"]
    pool = defaultdict(float)
    pool_unknown = defaultdict(int)
    for line in lines:
        if line.get("association_status") != "unlinked":
            continue
        key = group_key(line)
        value = _finite(line.get("actual_qty"))
        if value is None:
            pool_unknown[key] += 1
        else:
            pool[key] += value
    keys = sorted(set(so_lines_by_group) | set(pool), key=lambda item: tuple(
        "" if part is None else str(part) for part in item))
    ambiguity_pools = []
    for key in keys:
        open_total = round(so_open.get(key, 0.0), 6)
        pool_qty = round(pool.get(key, 0.0), 6)
        if so_open_unknown.get(key) or pool_unknown.get(key):
            potential = None
            unresolved = None
        else:
            potential = min(open_total, pool_qty)
            unresolved = max(0.0, round(open_total - pool_qty, 6))
        ambiguity_pools.append({
            "item_code": key[0], "uom": key[1], "customer": key[2],
            "warehouse": key[3], "channel": key[4],
            "so_open_total_qty": (None if so_open_unknown.get(key) else open_total),
            "unlinked_delivery_qty": (None if pool_unknown.get(key) else pool_qty),
            "potential_overlap_qty": potential,
            "unresolved_demand_qty": unresolved,
            "candidate_so_lines": [
                {"so": row["so"], "so_line": row["so_line"],
                 "so_open_qty": row["so_open_qty"]}
                for row in sorted(so_lines_by_group.get(key, []),
                                  key=lambda item: (str(item["so"]), str(item["so_line"])))],
            "eligible": False,
            "note": "pool-level overlap only; never allocated greedily to a SO line",
        })
    supply_ledger = []
    for row in so_fulfillment:
        supply_ledger.append({
            "supply_role": "so_line", "so": row["so"], "so_line": row["so_line"],
            "item_code": row["item_code"], "uom": row["uom"],
            "warehouse": row["warehouse"], "channel": row["channel"],
            "linked_fulfilled_qty": row["linked_delivered_qty"],
            "unresolved_demand_qty": row["unresolved_demand_qty"],
            "potential_overlap_qty": None,
            "confirmed_additional_supply_qty": None,
            "eligible": False,
            "reason": "SO balance is unresolved demand, not confirmed supply",
        })
    for line in lines:
        if line.get("association_status") != "unlinked":
            continue
        supply_ledger.append({
            "supply_role": "unlinked_delivery", "so": None, "so_line": None,
            "item_code": line.get("item_code"), "uom": line.get("uom"),
            "warehouse": line.get("warehouse"),
            "channel": line.get("channel") or "unknown",
            "linked_fulfilled_qty": 0.0,
            "unresolved_demand_qty": None,
            "potential_overlap_qty": None,
            "confirmed_additional_supply_qty": None,
            "eligible": False,
            "unknown_qty": _round(line.get("actual_qty")),
            "reason": "no SO association; keep logistics/PO trail only",
            "delivery_note": line.get("delivery_note"),
            "delivery_note_item": line.get("delivery_note_item"),
            "candidate_so_lines": line.get("candidate_so_lines") or [],
        })
    return {"so_fulfillment": so_fulfillment,
            "ambiguity_pools": ambiguity_pools,
            "supply_ledger": supply_ledger, "reason": ""}


def _conservation(lines):
    groups = defaultdict(lambda: {
        "rows": 0, "submitted_rows": 0, "inactive_rows": 0,
        "gross_magnitude_qty": 0.0, "return_magnitude_qty": 0.0,
        "actual_qty": 0.0, "unknown_quantity_rows": 0,
    })
    for line in lines:
        key = group_key(line)
        group = groups[key]
        group["rows"] += 1
        if line.get("docstatus") != 1:
            group["inactive_rows"] += 1
            continue
        group["submitted_rows"] += 1
        unknown = False
        magnitude = _finite(line.get("qty_magnitude"))
        if magnitude is None:
            unknown = True
        elif line.get("role") == "return":
            group["return_magnitude_qty"] += magnitude
        else:
            group["gross_magnitude_qty"] += magnitude
        actual = _finite(line.get("actual_qty"))
        if actual is None:
            unknown = True
        else:
            group["actual_qty"] += actual
        if unknown:
            group["unknown_quantity_rows"] += 1
    rows = []
    for key, value in sorted(groups.items(), key=lambda item: tuple(
            "" if part is None else str(part) for part in item[0])):
        rows.append({
            "item_code": key[0], "uom": key[1], "customer": key[2],
            "warehouse": key[3], "channel": key[4],
            **{name: (value[name] if name in ("rows", "submitted_rows",
                                              "inactive_rows",
                                              "unknown_quantity_rows")
                     else round(value[name], 6))
               for name in value},
            "ok": value["unknown_quantity_rows"] == 0,
        })
    return {
        "groups": rows,
        "row_counts": {
            "total": len(lines),
            "submitted": sum(1 for line in lines if line.get("docstatus") == 1),
            "inactive": sum(1 for line in lines if line.get("docstatus") != 1),
            "returns": sum(1 for line in lines if line.get("role") == "return"),
            "unknown_quantity": sum(1 for line in lines
                                    if _finite(line.get("actual_qty")) is None),
        },
        "all_groups_ok": all(row["ok"] for row in rows),
        "note": "Global cross-item quantity is intentionally not reported as a business total.",
    }


def build_delivery_facts(headers, items, so_headers, so_items, permitted_sos,
                         candidates, logistics, *, scope=None, instance="",
                         observed_at=None, restricted=False,
                         channel_by_item=None, as_of=None):
    scope = normalize_scope(scope)
    header_by_name = {row.get("name"): row for row in headers or []}
    items_by_name = {row.get("name"): row for row in items or []}
    so_items_by_name = {row.get("name"): row for row in so_items or []}
    so_items_by_parent = defaultdict(list)
    for row in so_items or []:
        so_items_by_parent[row.get("parent")].append(row)
    channel_map = dict(channel_by_item or {})
    candidates = candidates or {}

    base_lines = []
    for item in items or []:
        dn = header_by_name.get(item.get("parent"))
        if dn is None:
            continue
        relevance, scope_reason = scope_for_item(item.get("item_code"), scope)
        association, so, so_line, assoc_reason, candidate_lines = _association(
            item, dn, so_headers or {}, so_items_by_name, so_items_by_parent,
            permitted_sos or set(), candidates)
        uom_status, uom_reason = uom_evidence(item)
        raw_signed = _finite(item.get("qty"))
        magnitude = None if raw_signed is None else abs(raw_signed)
        is_return = bool(int(item.get("is_return") or dn.get("is_return") or 0))
        docstatus = int(dn.get("docstatus") or 0)
        direction = "invalid"
        if raw_signed is not None:
            if is_return:
                direction = ("negative_return" if raw_signed < 0 else
                             "positive_return" if raw_signed > 0 else "zero_return")
            elif raw_signed >= 0:
                direction = "outbound"
            else:
                direction = "outbound_negative"
        source_wh = _text(item.get("warehouse")) or _text(dn.get("set_warehouse"))
        target_wh = _text(item.get("target_warehouse")) or _text(
            dn.get("set_target_warehouse"))
        source_wh_status = ("dn_item" if _text(item.get("warehouse"))
                            else "dn_header" if _text(dn.get("set_warehouse"))
                            else "unknown")
        target_wh_status = ("dn_item" if _text(item.get("target_warehouse"))
                            else "dn_header" if _text(dn.get("set_target_warehouse"))
                            else "unknown")
        logistics_status, numbers, _shipments = _logistics_for_dn(
            dn.get("name"), logistics or {})
        channel = channel_map.get(item.get("item_code")) or "unknown"
        if channel not in ("fba", "in_house", "unknown"):
            channel = "unknown"
        actual = None
        if docstatus != 1:
            actual = 0.0
        elif direction in ("outbound", "negative_return", "positive_return", "zero_return"):
            actual = magnitude if not is_return else 0.0
        line = {
            "source_instance": instance,
            "delivery_note": dn.get("name"),
            "delivery_note_item": item.get("name"),
            "idx": item.get("idx"),
            "stable_id": "%s::%s::%s" % (instance, dn.get("name"), item.get("name")),
            "docstatus": docstatus,
            "is_return": is_return,
            "return_against": dn.get("return_against"),
            "amended_from": dn.get("amended_from"),
            "source_modified": _iso(dn.get("modified")),
            "item_code": item.get("item_code"),
            "item_name": item.get("item_name"),
            "customer_item_code": item.get("customer_item_code"),
            "customer": dn.get("customer"),
            "company": dn.get("company"),
            "branch_status": "unknown",
            "branch_reason": "目标分公司映射未证",
            "raw_signed_qty": _round(raw_signed),
            "qty_magnitude": _round(magnitude),
            "qty": _round(raw_signed),
            "quantity_direction": direction,
            "uom": item.get("uom"),
            "stock_qty": _round(item.get("stock_qty")),
            "stock_uom": item.get("stock_uom"),
            "conversion_factor": item.get("conversion_factor"),
            "conversion_basis": uom_reason,
            "uom_status": uom_status,
            "source_warehouse": source_wh or None,
            "target_warehouse": target_wh or None,
            "warehouse": target_wh or source_wh or None,
            "warehouse_status": source_wh_status,
            "target_warehouse_status": target_wh_status,
            "destination_status": ("known" if target_wh and target_wh_status != "unknown"
                                   else "unknown"),
            "channel": channel,
            "posting_date": _day(dn.get("posting_date")),
            "posting_time": _text(dn.get("posting_time")),
            "timezone_status": "unverified",
            "observed_at": observed_at,
            "so": so, "so_line": so_line,
            "association_status": association,
            "association_reason": assoc_reason,
            "candidate_so_lines": candidate_lines,
            "relevance_status": relevance,
            "scope_rule_version": scope.get("version"),
            "scope_source": scope.get("source"),
            "scope_hash": scope.get("hash"),
            "role": "return" if is_return else "outbound",
            "exclusion_reason": scope_reason,
            "quantity_status": "known" if raw_signed is not None else "unknown",
            "identity_status": ("known" if item.get("name") and dn.get("name")
                                else "unknown"),
            "logistics_status": logistics_status,
            "logistic_numbers": numbers,
            "tongtool_po": dn.get("custom_tongtool_purchase_order"),
            "po_status": ("code_only" if dn.get("custom_tongtool_purchase_order")
                          else "missing"),
            "receipt_status": "not_integrated",
            "inventory_status": "not_integrated",
            "is_current_execution": docstatus == 1,
            "inactive_reason": ("" if docstatus == 1 else
                                "draft" if docstatus == 0 else "cancelled"),
            "gross_qty": _round(magnitude) if not is_return else None,
            "returned_qty": 0.0,
            "actual_qty": actual,
            "excess_return_qty": 0.0,
            "return_status": "",
            "conflicts": [], "unknown_reasons": [],
            "source_records": ["Delivery Note %s" % dn.get("name"),
                               "Delivery Note Item %s" % item.get("name")],
            "rule_version": RULE_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
        }
        if docstatus != 1:
            line["quantity_status"] = "not_current"
        if direction in ("outbound_negative", "invalid"):
            line["conflicts"].append("quantity_direction_" + direction)
        if relevance == "unknown":
            line["unknown_reasons"].append(scope_reason)
        if uom_status == "unknown":
            line["unknown_reasons"].append(uom_reason)
        if association in ("conflict", "ambiguous", "restricted"):
            line["conflicts"].append(assoc_reason)
        if logistics_status in ("allocation_unknown", "identity_conflict",
                                "unresolved_waybill", "permission"):
            line["unknown_reasons"].append(logistics_status)
        if target_wh_status == "unknown":
            line["unknown_reasons"].append("target_warehouse_unknown")
        base_lines.append(line)

    # Return allocation: ERPNext negative qty → magnitude; strictly validated.
    returns = sorted([line for line in base_lines if line["is_return"]],
                     key=lambda row: (row["posting_date"] or "",
                                      row["delivery_note"] or "", row["idx"] or 0))
    capacity = {row["delivery_note_item"]: _finite(row["qty_magnitude"])
                for row in base_lines if not row["is_return"]}
    allocated = defaultdict(float)
    for ret in returns:
        if ret["docstatus"] != 1:
            ret["actual_qty"] = 0.0
            ret["quantity_status"] = "not_current"
            ret["return_status"] = "inactive_return"
            continue
        magnitude = _finite(ret["qty_magnitude"])
        if magnitude is None:
            ret["return_status"] = "invalid_quantity"
            ret["actual_qty"] = None
            ret["conflicts"].append("invalid_quantity")
            continue
        original_name = _text((items_by_name.get(ret["delivery_note_item"]) or {})
                              .get("dn_detail"))
        original = items_by_name.get(original_name)
        original_line = next((row for row in base_lines
                              if row["delivery_note_item"] == original_name), None)
        expected_parent = _text(ret["return_against"])
        if not original_name:
            ret["return_status"] = "return_reference_missing"
        elif original is None:
            ret["return_status"] = "return_reference_missing"
        elif original.get("parent") not in header_by_name:
            ret["return_status"] = "return_reference_restricted"
        elif expected_parent != original.get("parent"):
            ret["return_status"] = "return_reference_conflict"
        elif int((header_by_name.get(original.get("parent")) or {})
                 .get("docstatus") or 0) != 1:
            ret["return_status"] = "return_reference_not_submitted"
        elif original_line is None or original_line["is_return"]:
            ret["return_status"] = "return_of_return"
        elif (_text(original.get("item_code")) != _text(ret["item_code"])
              or _text(original.get("uom")) != _text(ret["uom"])
              or _text((header_by_name.get(original.get("parent")) or {})
                       .get("customer")) != _text(ret["customer"])
              or _text(original.get("warehouse")) != _text(
                  items_by_name.get(ret["delivery_note_item"], {}).get("warehouse"))):
            ret["return_status"] = "return_identity_mismatch"
        else:
            original_capacity = capacity.get(original_name)
            if original_capacity is None:
                ret["return_status"] = "return_reference_quantity_unknown"
            else:
                remaining = max(0.0, original_capacity - allocated[original_name])
                take = min(magnitude, remaining)
                allocated[original_name] += take
                original_line["returned_qty"] = round(allocated[original_name], 6)
                ret["actual_qty"] = -take
                ret["return_status"] = ("return_matched"
                                        if take + 1e-9 >= magnitude
                                        else "return_excess")
                ret["excess_return_qty"] = round(max(0.0, magnitude - take), 6)
                ret["so"] = original_line["so"]
                ret["so_line"] = original_line["so_line"]
                ret["association_status"] = original_line["association_status"]
                ret["association_reason"] = "inherited_from_original"
                ret["relevance_status"] = original_line["relevance_status"]
                ret["channel"] = original_line["channel"]
                ret["warehouse"] = original_line["warehouse"]
        if ret["return_status"] not in ("return_matched", "return_excess"):
            ret["actual_qty"] = 0.0
        if ret["return_status"] not in ("return_matched",):
            ret["conflicts"].append(ret["return_status"])

    summaries = summarize_lines(base_lines, so_items_by_name)
    association_edges = []
    for line in base_lines:
        association_edges.append({
            "edge_type": "delivery_to_so",
            "delivery_note": line["delivery_note"],
            "delivery_note_item": line["delivery_note_item"],
            "so": line["so"], "so_line": line["so_line"],
            "status": line["association_status"],
            "reason": line["association_reason"],
            "qty": line["actual_qty"], "uom": line["uom"],
            "allocation": ("linked_line" if line["association_status"] == "linked"
                           else "manual_review"),
            "source_records": line["source_records"],
        })
        for candidate in line["candidate_so_lines"] or []:
            association_edges.append({
                "edge_type": "candidate_so_line",
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "so": candidate.get("so"), "so_line": candidate.get("so_line"),
                "status": "candidate", "reason": "same_item_same_customer_candidate",
                "qty": None, "uom": candidate.get("uom"),
                "allocation": "manual_review",
                "source_records": line["source_records"],
            })

    physical_chain = []
    for line in base_lines:
        numbers = line["logistic_numbers"] or []
        allocation = ("single_waybill" if len(numbers) == 1 else
                      "allocation_unknown" if len(numbers) > 1 else "no_waybill")
        qty = line["actual_qty"] if len(numbers) == 1 else None
        if not numbers:
            physical_chain.append({
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "stage": "shipment", "target": None, "target_is_record": False,
                "qty": None, "uom": line["uom"], "allocation": "no_waybill",
                "status": "no_waybill",
            })
        for number in numbers:
            shipment = (logistics.get("shipment_by_number") or {}).get(
                number.get("number")) or {}
            physical_chain.append({
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "stage": "shipment",
                "target": shipment.get("shipment") or number.get("number"),
                "target_is_record": bool(shipment.get("shipment")),
                "qty": qty, "uom": line["uom"], "allocation": allocation,
                "status": (shipment.get("progress") or {}).get(
                    "latest_progress_status")
                if isinstance(shipment.get("progress"), dict) else None,
            })
        if line["tongtool_po"]:
            physical_chain.append({
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "stage": "tongtool_po", "target": line["tongtool_po"],
                "target_is_record": False, "qty": None, "uom": line["uom"],
                "allocation": "code_only", "status": "code_only",
            })
        for stage in ("receipt", "inventory"):
            physical_chain.append({
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "stage": stage, "target": None, "target_is_record": False,
                "qty": None, "uom": line["uom"], "allocation": "unknown",
                "status": "not_integrated",
            })

    coverage_exceptions = []
    for line in base_lines:
        reasons = []
        if line["docstatus"] != 1:
            reasons.append(line["inactive_reason"] or "inactive")
        if line["relevance_status"] != "in_scope":
            reasons.append("relevance_" + line["relevance_status"])
        if line["association_status"] != "linked":
            reasons.append("association_" + line["association_status"])
        if line["association_reason"]:
            reasons.append(line["association_reason"])
        if line["return_status"] and line["return_status"] != "return_matched":
            reasons.append(line["return_status"])
        if line["quantity_direction"] not in ("outbound", "negative_return",
                                              "positive_return", "zero_return"):
            reasons.append("quantity_direction_" + line["quantity_direction"])
        if reasons:
            coverage_exceptions.append({
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "item_code": line["item_code"],
                "association_status": line["association_status"],
                "relevance_status": line["relevance_status"],
                "reasons": sorted(set(reasons)),
                "actual_qty": line["actual_qty"], "uom": line["uom"],
                "warehouse": line["warehouse"], "channel": line["channel"],
            })

    association_counts = defaultdict(int)
    relevance_counts = defaultdict(int)
    for line in base_lines:
        association_counts[line["association_status"]] += 1
        relevance_counts[line["relevance_status"]] += 1
    for key in ASSOCIATION_VALUES:
        association_counts.setdefault(key, 0)
    for key in RELEVANCE_VALUES:
        relevance_counts.setdefault(key, 0)

    unlinked_lines = [line for line in base_lines
                      if line["association_status"] == "unlinked"
                      and line["docstatus"] == 1]
    by_customer = defaultdict(int)
    by_item = defaultdict(int)
    for line in unlinked_lines:
        by_customer[line["customer"]] += 1
        by_item[line["item_code"]] += 1
    unlinked_summary = {
        "rows": len(unlinked_lines),
        "with_tongtool_po": sum(1 for line in unlinked_lines if line["tongtool_po"]),
        "with_waybill": sum(1 for line in unlinked_lines
                            if line["logistics_status"] != "no_waybill"),
        "unknown_quantity_rows": sum(1 for line in unlinked_lines
                                     if _finite(line["actual_qty"]) is None),
        "top_customers": [
            {"customer": key, "rows": value}
            for key, value in sorted(by_customer.items(),
                                     key=lambda item: (-item[1], str(item[0])))[:20]],
        "top_items": [
            {"item_code": key, "rows": value}
            for key, value in sorted(by_item.items(),
                                     key=lambda item: (-item[1], str(item[0])))[:20]],
        "receipt_inventory_status": "not_integrated",
        "note": ("Cross-item quantity totals are not reported; use "
                 "conservation.groups for item×UOM×customer×warehouse×channel."),
    }
    coverage = {
        "scope": {
            "status": scope.get("status"), "source": scope.get("source"),
            "version": scope.get("version"), "hash": scope.get("hash"),
            "reason": scope.get("reason"),
            "items": sorted(scope.get("items") or {}),
        },
        "as_of": as_of,
        "observed_at": observed_at,
        "delivery_notes": {
            "total": len(header_by_name),
            "submitted": sum(1 for dn in header_by_name.values()
                             if int(dn.get("docstatus") or 0) == 1),
            "draft": sum(1 for dn in header_by_name.values()
                         if int(dn.get("docstatus") or 0) == 0),
            "cancelled": sum(1 for dn in header_by_name.values()
                             if int(dn.get("docstatus") or 0) == 2),
            "returns": sum(1 for dn in header_by_name.values()
                           if int(dn.get("is_return") or 0)),
            "amended": sum(1 for dn in header_by_name.values()
                           if dn.get("amended_from")),
        },
        "delivery_lines": {
            "total": len(base_lines),
            "submitted": sum(1 for line in base_lines if line["docstatus"] == 1),
            "draft": sum(1 for line in base_lines if line["docstatus"] == 0),
            "cancelled": sum(1 for line in base_lines if line["docstatus"] == 2),
            "returns": sum(1 for line in base_lines if line["is_return"]),
            "amended_from": sum(1 for line in base_lines if line["amended_from"]),
        },
        "association": dict(sorted(association_counts.items())),
        "relevance": dict(sorted(relevance_counts.items())),
        "unlinked_summary": unlinked_summary,
        "conservation": _conservation(base_lines),
        "restricted": bool(restricted),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "scope": coverage["scope"],
        "as_of": as_of,
        "delivery_lines": base_lines,
        "association_edges": association_edges,
        "coverage_exceptions": coverage_exceptions,
        "so_fulfillment": summaries["so_fulfillment"],
        "ambiguity_pools": summaries["ambiguity_pools"],
        "supply_ledger": summaries["supply_ledger"],
        "summary_reason": summaries["reason"],
        "physical_chain": physical_chain,
        "coverage": coverage,
    }


# ── read-only API ───────────────────────────────────────────────────────────

def _normalize_filters(filters=None, extra=None):
    if extra:
        unexpected = sorted(set(extra) - FRAMEWORK_ARGS)
        if unexpected:
            frappe.throw("Unknown parameter(s): %s" % ", ".join(unexpected),
                         frappe.ValidationError)
    if filters is None:
        filters = {}
    elif isinstance(filters, str):
        try:
            filters = json.loads(filters or "{}")
        except Exception:
            frappe.throw("filters must be a JSON object", frappe.ValidationError)
    if not isinstance(filters, dict):
        frappe.throw("filters must be a JSON object", frappe.ValidationError)
    unknown = sorted(set(filters) - FILTER_KEYS)
    if unknown:
        frappe.throw("Unknown filter(s): %s; allowed: %s"
                     % (", ".join(unknown), ", ".join(sorted(FILTER_KEYS))),
                     frappe.ValidationError)
    out = {}
    for key in ("sales_order", "customer", "item_code", "from_date", "to_date"):
        value = filters.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            frappe.throw("filter %s must be a string" % key, frappe.ValidationError)
        if value.strip():
            out[key] = value.strip()
    for key in ("association_status", "relevance_status"):
        value = filters.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            values = [part.strip() for part in value.split(",") if part.strip()]
        elif isinstance(value, (list, tuple)):
            values = [str(part).strip() for part in value if str(part).strip()]
        else:
            frappe.throw("filter %s must be a string or list" % key,
                         frappe.ValidationError)
        allowed = ASSOCIATION_VALUES if key == "association_status" else RELEVANCE_VALUES
        bad = sorted(set(values) - allowed)
        if bad:
            frappe.throw("Unknown %s: %s" % (key, ", ".join(bad)),
                         frappe.ValidationError)
        out[key] = set(values)
    for key, default in (("include_unlinked", True), ("include_inactive", False)):
        if key not in filters:
            out[key] = default
            continue
        value = filters[key]
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = bool(value)
        elif isinstance(value, str) and value.strip().lower() in (
                "1", "true", "yes", "on", "0", "false", "no", "off"):
            out[key] = value.strip().lower() in ("1", "true", "yes", "on")
        else:
            frappe.throw("%s must be boolean" % key, frappe.ValidationError)
    limit = filters.get("limit", DEFAULT_LIMIT) or DEFAULT_LIMIT
    offset = filters.get("offset", 0) or 0
    try:
        limit, offset = int(limit), int(offset)
    except Exception:
        frappe.throw("limit/offset must be integers", frappe.ValidationError)
    if not 1 <= limit <= MAX_LIMIT:
        frappe.throw("limit must be between 1 and %d" % MAX_LIMIT,
                     frappe.ValidationError)
    if offset < 0:
        frappe.throw("offset must be >= 0", frappe.ValidationError)
    out["limit"], out["offset"] = limit, offset
    return out


def _load_reference_data(items):
    """Parent permission first; child rows only for permitted SOs."""
    parents = sorted({_text(item.get("against_sales_order")) for item in items
                      if _text(item.get("against_sales_order"))})
    permitted_rows = frappe.get_list(
        "Sales Order", filters=[["name", "in", parents],
                                ["docstatus", "in", (0, 1, 2)]],
        fields=["name", "customer", "docstatus"], limit_page_length=0) \
        if parents else []
    permitted = {row.name for row in permitted_rows}
    headers = {row.name: {"name": row.name, "customer": row.customer,
                          "docstatus": row.docstatus}
               for row in permitted_rows}
    so_items = frappe.get_all(
        "Sales Order Item", filters={"parent": ["in", sorted(permitted)]},
        fields=["name", "parent", "item_code", "qty", "uom", "stock_uom"]) \
        if permitted else []
    return headers, so_items, permitted


def _candidate_rows(items, headers_by_name, scope):
    if scope.get("status") != "provided":
        return {}
    scope_items = set(scope.get("items") or {})
    relevant = [item for item in items
                if not _text(item.get("so_detail"))
                and not _text(item.get("against_sales_order"))
                and _text(item.get("item_code")) in scope_items]
    item_codes = sorted({_text(item.get("item_code")) for item in relevant})
    customers = sorted({_text(headers_by_name.get(item.get("parent"), {}).get("customer"))
                        for item in relevant})
    customers = [value for value in customers if value]
    if not item_codes or not customers:
        return {}
    rows = frappe.db.sql(
        """select soi.name as so_line, soi.parent as so, soi.item_code,
                  soi.qty, soi.uom, so.customer
           from `tabSales Order Item` soi
           join `tabSales Order` so on so.name = soi.parent
           where so.docstatus = 1 and soi.item_code in %(items)s
             and so.customer in %(customers)s""",
        {"items": tuple(item_codes), "customers": tuple(customers)}, as_dict=True)
    so_names = sorted({row.so for row in rows})
    permitted = {row.name for row in frappe.get_list(
        "Sales Order", filters=[["name", "in", so_names], ["docstatus", "=", 1]],
        fields=["name"], limit_page_length=0)} if so_names else set()
    grouped = defaultdict(list)
    for row in rows:
        if row.so in permitted:
            grouped[(row.customer, row.item_code)].append({
                "so": row.so, "so_line": row.so_line, "qty": row.qty,
                "uom": row.uom})
    return grouped


def _load_logistics(dn_names):
    numbers_by_dn, shipment_by_number = {}, {}
    shipment_permission = frappe.has_permission("Shipment", "read")
    event_status = {"available": True, "restricted": False, "reason": ""}
    try:
        from key_test.supply_facts import load_shipments
        numbers_by_dn, shipment_by_number, _ship_restricted, event_status = \
            load_shipments(dn_names)
    except Exception as exc:  # noqa: BLE001
        event_status = {"available": False, "restricted": False,
                        "reason": "query_error", "error": str(exc)}
    return {
        "numbers_by_dn": numbers_by_dn,
        "shipment_by_number": shipment_by_number,
        "shipment_permission": shipment_permission,
        "event_status": event_status,
    }


def _query_coverage(lines, page):
    association = defaultdict(int)
    relevance = defaultdict(int)
    for line in lines:
        association[line["association_status"]] += 1
        relevance[line["relevance_status"]] += 1
    for key in ASSOCIATION_VALUES:
        association.setdefault(key, 0)
    for key in RELEVANCE_VALUES:
        relevance.setdefault(key, 0)
    return {
        "filtered_rows": len(lines),
        "page_rows": len(page),
        "association": dict(sorted(association.items())),
        "relevance": dict(sorted(relevance.items())),
        "conservation": _conservation(page),
        "aggregation_scope": "query_page",
        "note": "Page-scoped aggregates; use export for the full snapshot.",
    }


@frappe.whitelist()
def get_delivery_facts(filters=None, scope=None, **kwargs):
    """DN-item anchored actual delivery facts; SO links are optional edges."""
    filters = _normalize_filters(filters, kwargs)
    normalized_scope = normalize_scope(scope)
    if not frappe.has_permission("Delivery Note", "read"):
        frappe.throw("No permission for Delivery Note", frappe.PermissionError)

    dn_filters = [["docstatus", "in",
                   (0, 1, 2) if filters["include_inactive"] else (1,)]]
    if filters.get("customer"):
        dn_filters.append(["customer", "=", filters["customer"]])
    if filters.get("from_date"):
        dn_filters.append(["posting_date", ">=", filters["from_date"]])
    if filters.get("to_date"):
        dn_filters.append(["posting_date", "<=", filters["to_date"]])
    headers = [dict(row) for row in frappe.get_list(
        "Delivery Note", filters=dn_filters,
        fields=["name", "customer", "company", "posting_date", "posting_time",
                "docstatus", "is_return", "return_against", "amended_from",
                "set_warehouse", "set_target_warehouse",
                "custom_tongtool_purchase_order", "modified", "status"],
        limit_page_length=0)]
    total_headers = frappe.db.count("Delivery Note", filters=dn_filters)
    restricted = total_headers > len(headers)
    names = [row["name"] for row in headers]
    items = [dict(row) for row in frappe.get_all(
        "Delivery Note Item", filters={"parent": ["in", names]},
        fields=["name", "parent", "idx", "item_code", "item_name",
                "customer_item_code", "qty", "uom", "stock_qty", "stock_uom",
                "conversion_factor", "warehouse", "target_warehouse",
                "against_sales_order", "so_detail", "dn_detail"])] if names else []

    so_headers, so_items, permitted_sos = _load_reference_data(items)
    headers_by_name = {row["name"]: row for row in headers}
    candidates = _candidate_rows(items, headers_by_name, normalized_scope)
    logistics = _load_logistics(names)
    as_of = now_datetime().date().isoformat()
    result = build_delivery_facts(
        headers, items, so_headers, so_items, permitted_sos, candidates,
        logistics, scope=normalized_scope,
        instance=getattr(frappe.local, "site", "") or "",
        observed_at=_iso(now_datetime()), restricted=restricted, as_of=as_of)
    result["coverage"]["shipment_permission"] = logistics["shipment_permission"]
    result["coverage"]["shipment_logistics_event"] = logistics["event_status"]

    rows = result["delivery_lines"]
    if filters.get("sales_order"):
        rows = [row for row in rows if row.get("so") == filters["sales_order"]]
    if filters.get("item_code"):
        rows = [row for row in rows if row.get("item_code") == filters["item_code"]]
    if filters.get("association_status"):
        rows = [row for row in rows
                if row.get("association_status") in filters["association_status"]]
    if filters.get("relevance_status"):
        rows = [row for row in rows
                if row.get("relevance_status") in filters["relevance_status"]]
    if not filters["include_unlinked"]:
        rows = [row for row in rows if row.get("association_status") != "unlinked"]
    rows.sort(key=lambda row: (str(row.get("posting_date") or ""),
                               str(row.get("delivery_note") or ""),
                               int(row.get("idx") or 0),
                               str(row.get("delivery_note_item") or "")))
    total = len(rows)
    offset, limit = filters["offset"], filters["limit"]
    page = rows[offset:offset + limit]
    selected = {row["delivery_note_item"] for row in page}
    exhausted = offset + len(page) >= total
    snapshot_payload = {
        "ids": sorted(row["stable_id"] for row in rows),
        "schema": result["schema_version"], "rule": result["rule_version"],
        "implementation": result["implementation_version"],
        "scope_hash": normalized_scope.get("hash"), "as_of": as_of,
    }
    snapshot_id = hashlib.sha1(json.dumps(
        snapshot_payload, sort_keys=True).encode("utf-8")).hexdigest()

    so_items_by_name = {row.get("name"): row for row in so_items or []}
    summaries = summarize_lines(page, so_items_by_name)
    pagination = {
        "limit": limit, "offset": offset, "returned": len(page), "total": total,
        "next_offset": None if exhausted else offset + len(page),
        "next_cursor": page[-1]["delivery_note_item"] if page and not exhausted else None,
        "exhausted": exhausted, "partial": not exhausted,
        "termination_reason": "exhausted" if exhausted else "page_limit",
        "sort": list(SORT_KEYS), "unique_key": "delivery_note_item",
    }
    result["delivery_lines"] = page
    result["association_edges"] = [row for row in result["association_edges"]
                                   if row.get("delivery_note_item") in selected]
    result["coverage_exceptions"] = [row for row in result["coverage_exceptions"]
                                     if row.get("delivery_note_item") in selected]
    result["physical_chain"] = [row for row in result["physical_chain"]
                                if row.get("delivery_note_item") in selected]
    result["so_fulfillment"] = summaries["so_fulfillment"]
    result["ambiguity_pools"] = summaries["ambiguity_pools"]
    result["supply_ledger"] = summaries["supply_ledger"]
    result["summary_reason"] = summaries["reason"]
    result["coverage"]["global"] = {
        key: value for key, value in result["coverage"].items()
        if key not in ("global", "query")
    }
    result["coverage"]["query"] = _query_coverage(rows, page)
    result["pagination"] = pagination
    result["snapshot_id"] = snapshot_id
    result["applied_filters"] = {key: value for key, value in filters.items()
                                 if key not in ("limit", "offset")}
    result["counts"] = {
        "delivery_notes": len({row.get("delivery_note") for row in page}),
        "delivery_lines": len(page),
        "association_edges": len(result["association_edges"]),
        "coverage_exceptions": len(result["coverage_exceptions"]),
        "so_fulfillment": len(result["so_fulfillment"]),
        "ambiguity_pools": len(result["ambiguity_pools"]),
        "supply_ledger": len(result["supply_ledger"]),
        "physical_chain": len(result["physical_chain"]),
    }
    return result

