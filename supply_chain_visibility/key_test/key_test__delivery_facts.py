# -*- coding: utf-8 -*-
"""Delivery-Note-centric actual delivery facts (read-only, pure builders + API).

The anchor is a submitted ``Delivery Note Item``.  SO association is an
optional edge: a DN line without SO is still a real delivery and keeps its
logistics / PO / receipt trail.  Nothing here guesses an SO from item prefix,
BOM, or same-item proximity; candidates are for manual review only.
"""
from __future__ import annotations

import json
from collections import defaultdict

import frappe
from frappe.utils import now_datetime

SCHEMA_VERSION = "supply-facts/v3"
RULE_VERSION = "2026-10-30.1"
IMPLEMENTATION_VERSION = "key_test.delivery_facts@2026-10-30.1"
SCOPE_VERSION = "jack_w1_sample9_2026-10-26"

APPROVED_TARGET_ITEMS = {
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
    "customer", "item_code", "from_date", "to_date", "association_status",
    "relevance_status", "include_unlinked", "include_inactive", "limit", "offset",
}
ASSOCIATION_VALUES = {
    "linked", "so_header_only", "unlinked", "ambiguous", "conflict", "restricted",
}
RELEVANCE_VALUES = {"in_scope", "out_of_scope", "unknown"}
FRAMEWORK_ARGS = {"cmd", "csrf_token", "_"}
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000
SORT_KEYS = ["posting_date", "delivery_note", "idx", "delivery_note_item"]
RETURN_ISSUES = {
    "return_reference_missing", "return_reference_conflict",
    "return_reference_restricted", "return_excess", "return_of_return",
}


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round(value):
    return None if value is None else round(_num(value), 6)


def _day(value):
    return str(value)[:10] if value else None


def _iso(value):
    return str(value).replace(" ", "T")[:19] if value else None


def scope_for_item(item_code):
    item_code = _text(item_code)
    if not item_code:
        return "unknown", "缺少 item_code"
    if item_code in APPROVED_TARGET_ITEMS:
        return "in_scope", ""
    return "out_of_scope", "不在已批准 9-SKU 清单（%s）" % SCOPE_VERSION


def uom_evidence(item):
    qty = item.get("qty")
    stock_qty = item.get("stock_qty")
    uom = _text(item.get("uom"))
    stock_uom = _text(item.get("stock_uom"))
    factor = _num(item.get("conversion_factor"))
    if qty is None:
        return "unknown", "missing_quantity"
    if not uom or not stock_uom:
        return "unknown", "uom_missing"
    if uom == stock_uom and (stock_qty is None or abs(_num(stock_qty) - _num(qty)) < 1e-6):
        return "known", "same_uom"
    if factor > 0 and stock_qty is not None \
            and abs(_num(stock_qty) - _num(qty) * factor) < 1e-6:
        return "known", "conversion_factor"
    return "unknown", "conversion_unproven"


def _association(item, dn, so_headers, so_items_by_name, so_items_by_parent,
                 so_detail_parent, permitted_sos, candidates):
    """Return (status, so, so_line, reason, candidate_lines)."""
    so_detail = _text(item.get("so_detail"))
    so_header = _text(item.get("against_sales_order"))
    candidates_for_item = candidates.get(
        (_text(dn.get("customer")), _text(item.get("item_code"))), [])
    if so_detail:
        so_item = so_items_by_name.get(so_detail)
        if so_item is None:
            parent = _text(so_detail_parent.get(so_detail))
            if parent and parent not in permitted_sos:
                return ("restricted", parent, so_detail, "so_not_readable", [])
            return ("conflict", so_header or parent or None, so_detail,
                    "so_detail_not_found", candidates_for_item)
        parent = _text(so_item.get("parent"))
        if parent not in permitted_sos:
            return ("restricted", parent, so_detail, "so_not_readable", [])
        header = so_headers.get(parent) or {}
        if int(header.get("docstatus") or 0) != 1:
            return ("conflict", parent, so_detail, "so_not_submitted", candidates_for_item)
        if _text(so_item.get("item_code")) != _text(item.get("item_code")):
            return ("conflict", parent, so_detail, "so_item_code_mismatch",
                    candidates_for_item)
        if _text(header.get("customer")) != _text(dn.get("customer")):
            return ("conflict", parent, so_detail, "so_customer_mismatch",
                    candidates_for_item)
        return ("linked", parent, so_detail, "", [])
    if so_header:
        if so_header not in permitted_sos:
            return ("restricted", so_header, None, "so_not_readable", [])
        header = so_headers.get(so_header) or {}
        if int(header.get("docstatus") or 0) != 1:
            return ("conflict", so_header, None, "so_not_submitted", candidates_for_item)
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
    identity_conflict = any(row.get("identity_conflict") for row in resolved)
    if not logistics.get("shipment_permission", True):
        return "permission", numbers, resolved
    if not numbers:
        return "no_waybill", numbers, resolved
    if identity_conflict:
        return "identity_conflict", numbers, resolved
    if len(numbers) > 1:
        return "allocation_unknown", numbers, resolved
    if not resolved:
        return "unresolved_waybill", numbers, resolved
    return "linked", numbers, resolved


def build_delivery_facts(headers, items, so_headers, so_items, permitted_sos,
                         candidates, logistics, *, instance="test",
                         observed_at=None, restricted=False,
                         so_detail_parent=None):
    """Pure builder. ``headers``/``items`` are plain dicts from read-only loads."""
    header_by_name = {row.get("name"): row for row in headers or []}
    items_by_name = {row.get("name"): row for row in items or []}
    so_items_by_name = {row.get("name"): row for row in so_items or []}
    so_items_by_parent = defaultdict(list)
    for row in so_items or []:
        so_items_by_parent[row.get("parent")].append(row)
    candidates = candidates or {}

    base_lines = []
    for item in items or []:
        dn = header_by_name.get(item.get("parent"))
        if dn is None:
            continue
        relevance, scope_reason = scope_for_item(item.get("item_code"))
        association, so, so_line, assoc_reason, candidate_lines = _association(
            item, dn, so_headers or {}, so_items_by_name, so_items_by_parent,
            so_detail_parent or {}, permitted_sos or set(), candidates)
        uom_status, uom_reason = uom_evidence(item)
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
        docstatus = int(dn.get("docstatus") or 0)
        is_return = bool(int(item.get("is_return") or dn.get("is_return") or 0))
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
            "qty": _round(item.get("qty")),
            "uom": item.get("uom"),
            "stock_qty": _round(item.get("stock_qty")),
            "stock_uom": item.get("stock_uom"),
            "conversion_factor": item.get("conversion_factor"),
            "conversion_basis": uom_reason,
            "uom_status": uom_status,
            "source_warehouse": source_wh or None,
            "target_warehouse": target_wh or None,
            "warehouse_status": source_wh_status,
            "target_warehouse_status": target_wh_status,
            "destination_status": ("known" if target_wh and target_wh_status != "unknown"
                                   else "unknown"),
            "posting_date": _day(dn.get("posting_date")),
            "posting_time": _text(dn.get("posting_time")),
            "timezone_status": "unverified",
            "observed_at": observed_at,
            "so": so,
            "so_line": so_line,
            "association_status": association,
            "association_reason": assoc_reason,
            "candidate_so_lines": candidate_lines,
            "relevance_status": relevance,
            "scope_rule_version": SCOPE_VERSION,
            "role": "outbound",
            "exclusion_reason": scope_reason,
            "quantity_status": "known" if item.get("qty") is not None else "unknown",
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
            "gross_qty": _round(item.get("qty")),
            "returned_qty": 0.0,
            "actual_qty": _round(item.get("qty")) if docstatus == 1 else 0.0,
            "excess_return_qty": 0.0,
            "return_status": "",
            "conflicts": [],
            "unknown_reasons": [],
            "source_records": ["Delivery Note %s" % dn.get("name"),
                               "Delivery Note Item %s" % item.get("name")],
            "rule_version": RULE_VERSION,
            "implementation_version": IMPLEMENTATION_VERSION,
        }
        if docstatus != 1:
            line["quantity_status"] = "not_current"
        if relevance == "unknown":
            line["unknown_reasons"].append(scope_reason)
        if uom_status == "unknown":
            line["unknown_reasons"].append(uom_reason)
        if association in ("conflict", "ambiguous", "restricted"):
            line["conflicts"].append(assoc_reason)
        if logistics_status in ("allocation_unknown", "identity_conflict"):
            line["unknown_reasons"].append(logistics_status)
        if target_wh_status == "unknown":
            line["unknown_reasons"].append("target_warehouse_unknown")
        base_lines.append(line)

    # Return allocation: original DN item capacity, no guessing.
    returns = sorted(
        [line for line in base_lines if line["is_return"]],
        key=lambda row: (row["posting_date"] or "", row["delivery_note"] or "",
                         row["idx"] or 0))
    capacity = {row["delivery_note_item"]: _num(row["qty"])
                for row in base_lines if not row["is_return"]}
    allocated = defaultdict(float)
    for ret in returns:
        ret["role"] = "return"
        ret["gross_qty"] = _round(ret["qty"])
        original_name = _text(
            (items_by_name.get(ret["delivery_note_item"]) or {}).get("dn_detail"))
        if ret["docstatus"] != 1:
            ret["actual_qty"] = 0.0
            ret["quantity_status"] = "not_current"
            ret["return_status"] = "inactive_return"
            continue
        original = items_by_name.get(original_name)
        original_line = next((row for row in base_lines
                              if row["delivery_note_item"] == original_name), None)
        if not original_name:
            ret["return_status"] = "return_reference_missing"
        elif original is None:
            ret["return_status"] = "return_reference_missing"
        elif original.get("parent") not in header_by_name:
            ret["return_status"] = "return_reference_restricted"
        elif original_line is None:
            ret["return_status"] = "return_reference_missing"
        elif original_line["is_return"]:
            ret["return_status"] = "return_of_return"
        else:
            remaining = max(0.0, capacity.get(original_name, 0.0)
                            - allocated[original_name])
            take = min(_num(ret["qty"]), remaining)
            allocated[original_name] += take
            original_line["returned_qty"] = allocated[original_name]
            original_line["actual_qty"] = max(
                0.0, _num(original_line["qty"]) - allocated[original_name])
            ret["actual_qty"] = -take
            ret["return_status"] = ("return_matched" if take + 1e-9 >= _num(ret["qty"])
                                    else "return_excess")
            ret["excess_return_qty"] = max(0.0, _num(ret["qty"]) - take)
            ret["so"] = original_line["so"]
            ret["so_line"] = original_line["so_line"]
            ret["association_status"] = original_line["association_status"]
            ret["association_reason"] = "inherited_from_original"
            ret["relevance_status"] = original_line["relevance_status"]
            ret["exclusion_reason"] = original_line["exclusion_reason"]
        if ret["return_status"] in ("return_reference_missing",
                                    "return_reference_restricted",
                                    "return_of_return"):
            ret["actual_qty"] = 0.0
        if ret["return_status"] in RETURN_ISSUES or ret["return_status"]:
            if ret["return_status"] != "return_matched":
                ret["conflicts"].append(ret["return_status"])

    for line in base_lines:
        if line["is_return"]:
            continue
        line["actual_qty"] = (max(0.0, _num(line["qty"]) - line["returned_qty"])
                             if line["docstatus"] == 1 else 0.0)

    # Association edges (including manual-review candidates).
    association_edges = []
    for line in base_lines:
        association_edges.append({
            "edge_type": "delivery_to_so",
            "delivery_note": line["delivery_note"],
            "delivery_note_item": line["delivery_note_item"],
            "so": line["so"], "so_line": line["so_line"],
            "status": line["association_status"],
            "reason": line["association_reason"],
            "qty": line["actual_qty"],
            "uom": line["uom"],
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

    # SO fulfillment + replenishment supply ledgers.
    linked_by_line = defaultdict(float)
    so_line_meta = {}
    for line in base_lines:
        if line["association_status"] != "linked" or not line["so_line"]:
            continue
        key = (line["so"], line["so_line"])
        linked_by_line[key] += _num(line["actual_qty"])
        so_line_meta.setdefault(key, line)
    pool = defaultdict(float)
    for line in base_lines:
        if line["association_status"] == "unlinked":
            pool[(_text(line["customer"]), _text(line["item_code"]))] += _num(line["actual_qty"])
    pool_remaining = dict(pool)
    so_fulfillment = []
    supply_ledger = []
    for key in sorted(so_line_meta, key=lambda k: (str(k[0]), str(k[1]))):
        line = so_line_meta[key]
        so_item = so_items_by_name.get(key[1]) or {}
        linked = round(linked_by_line[key], 6)
        so_qty = _round(so_item.get("qty"))
        order_uom = _text(so_item.get("uom"))
        if so_qty is None or not order_uom or order_uom != _text(line.get("uom")):
            so_open = None
            potential = None
            confirmed = None
            unknown = None
        else:
            so_open = max(0.0, round(so_qty - linked, 6))
            pool_key = (_text(line["customer"]), _text(line["item_code"]))
            available_pool = pool_remaining.get(pool_key, 0.0)
            potential = min(so_open, max(0.0, available_pool))
            pool_remaining[pool_key] = available_pool - potential
            confirmed = max(0.0, round(so_open - potential, 6))
            unknown = potential
        so_fulfillment.append({
            "so": key[0], "so_line": key[1],
            "item_code": line["item_code"], "uom": line["uom"],
            "so_qty": so_qty, "linked_delivered_qty": linked,
            "so_open_qty": so_open,
            "unlinked_candidate_qty": (None if potential is None else potential),
            "potential_overlap_qty": potential,
            "confirmed_additional_supply_qty": confirmed,
            "association_gap_qty": unknown,
            "demand_status": "active",
            "eligible": False,
            "note": "未关联交付可能属于该 SO；potential_overlap 只供人工审核",
        })
        supply_ledger.append({
            "supply_role": "so_line", "so": key[0], "so_line": key[1],
            "item_code": line["item_code"], "uom": line["uom"],
            "linked_fulfilled_qty": linked,
            "confirmed_additional_supply_qty": confirmed,
            "potential_overlap_qty": potential,
            "unknown_qty": unknown,
            "eligible": False,
            "reason": "unlinked delivery is not proof of extra supply",
        })
    for line in base_lines:
        if line["association_status"] != "unlinked" or not line["actual_qty"]:
            continue
        supply_ledger.append({
            "supply_role": "unlinked_delivery",
            "so": None, "so_line": None,
            "item_code": line["item_code"], "uom": line["uom"],
            "linked_fulfilled_qty": 0.0,
            "confirmed_additional_supply_qty": 0.0,
            "potential_overlap_qty": None,
            "unknown_qty": _num(line["actual_qty"]),
            "eligible": False,
            "reason": "no SO association; keep logistics/PO trail only",
            "delivery_note": line["delivery_note"],
            "delivery_note_item": line["delivery_note_item"],
            "candidate_so_lines": line["candidate_so_lines"],
        })

    # Physical chain: DN -> Shipment / Tongtool PO (never copy full DN qty).
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
                "status": shipment.get("progress", {}).get("latest_progress_status")
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
        physical_chain.append({
            "delivery_note": line["delivery_note"],
            "delivery_note_item": line["delivery_note_item"],
            "stage": "receipt", "target": None, "target_is_record": False,
            "qty": None, "uom": line["uom"], "allocation": "unknown",
            "status": "not_integrated",
        })
        physical_chain.append({
            "delivery_note": line["delivery_note"],
            "delivery_note_item": line["delivery_note_item"],
            "stage": "inventory", "target": None, "target_is_record": False,
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
        if line["actual_qty"] < 0:
            reasons.append("return_negative_actual")
        if reasons:
            coverage_exceptions.append({
                "delivery_note": line["delivery_note"],
                "delivery_note_item": line["delivery_note_item"],
                "item_code": line["item_code"],
                "association_status": line["association_status"],
                "relevance_status": line["relevance_status"],
                "reasons": sorted(set(reasons)),
                "actual_qty": line["actual_qty"],
                "uom": line["uom"],
            })

    association_counts = defaultdict(int)
    relevance_counts = defaultdict(int)
    status_counts = defaultdict(int)
    for line in base_lines:
        association_counts[line["association_status"]] += 1
        relevance_counts[line["relevance_status"]] += 1
        status_counts["docstatus_%s" % line["docstatus"]] += 1
        if line["is_return"]:
            status_counts["return"] += 1
        if line["amended_from"]:
            status_counts["amended_from"] += 1
    for key in ASSOCIATION_VALUES:
        association_counts.setdefault(key, 0)
    for key in RELEVANCE_VALUES:
        relevance_counts.setdefault(key, 0)
    gross = sum(_num(line["gross_qty"]) for line in base_lines
                if line["docstatus"] == 1 and not line["is_return"])
    returns = sum(_num(line["gross_qty"]) for line in base_lines
                  if line["docstatus"] == 1 and line["is_return"])
    excess = sum(_num(line["excess_return_qty"]) for line in base_lines
                 if line["docstatus"] == 1 and line["is_return"])
    inactive_raw = sum(_num(line["gross_qty"]) for line in base_lines
                       if line["docstatus"] != 1)
    actual = sum(_num(line["actual_qty"]) for line in base_lines
                 if line["docstatus"] == 1)
    conservation = {
        "submitted_gross_qty": round(gross, 6),
        "submitted_return_qty": round(returns, 6),
        "matched_return_qty": round(returns - excess, 6),
        "excess_return_qty": round(excess, 6),
        "inactive_raw_qty": round(inactive_raw, 6),
        "actual_delivery_qty": round(actual, 6),
        "conservation_ok": abs(
            (gross - (returns - excess)) - actual) < 1e-6,
    }
    unlinked_lines = [line for line in base_lines
                      if line["association_status"] == "unlinked"
                      and line["docstatus"] == 1]
    by_customer = defaultdict(lambda: {"rows": 0, "qty": 0.0})
    by_item = defaultdict(lambda: {"rows": 0, "qty": 0.0})
    for line in unlinked_lines:
        by_customer[line["customer"]]["rows"] += 1
        by_customer[line["customer"]]["qty"] += _num(line["actual_qty"])
        by_item[line["item_code"]]["rows"] += 1
        by_item[line["item_code"]]["qty"] += _num(line["actual_qty"])
    unlinked_summary = {
        "rows": len(unlinked_lines),
        "qty": round(sum(_num(line["actual_qty"]) for line in unlinked_lines), 6),
        "with_tongtool_po": sum(1 for line in unlinked_lines if line["tongtool_po"]),
        "with_waybill": sum(1 for line in unlinked_lines
                            if line["logistics_status"] != "no_waybill"),
        "top_customers": [
            {"customer": key, "rows": value["rows"], "qty": round(value["qty"], 6)}
            for key, value in sorted(by_customer.items(),
                                     key=lambda item: (-item[1]["qty"], str(item[0])))[:20]],
        "top_items": [
            {"item_code": key, "rows": value["rows"], "qty": round(value["qty"], 6)}
            for key, value in sorted(by_item.items(),
                                     key=lambda item: (-item[1]["qty"], str(item[0])))[:20]],
        "receipt_inventory_status": "not_integrated",
    }
    coverage = {
        "scope_rule_version": SCOPE_VERSION,
        "approved_target_items": sorted(APPROVED_TARGET_ITEMS),
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
            "submitted": status_counts.get("docstatus_1", 0),
            "draft": status_counts.get("docstatus_0", 0),
            "cancelled": status_counts.get("docstatus_2", 0),
            "returns": status_counts.get("return", 0),
            "amended_from": status_counts.get("amended_from", 0),
        },
        "association": dict(sorted(association_counts.items())),
        "relevance": dict(sorted(relevance_counts.items())),
        "unlinked_summary": unlinked_summary,
        "restricted": bool(restricted),
        "observed_at": observed_at,
        "conservation": conservation,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "scope": {"version": SCOPE_VERSION,
                  "approved_items": sorted(APPROVED_TARGET_ITEMS)},
        "delivery_lines": base_lines,
        "association_edges": association_edges,
        "coverage_exceptions": coverage_exceptions,
        "so_fulfillment": so_fulfillment,
        "supply_ledger": supply_ledger,
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
    for key in ("customer", "item_code", "from_date", "to_date"):
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
    so_details = sorted({_text(item.get("so_detail")) for item in items
                         if _text(item.get("so_detail"))})
    detail_rows = frappe.get_all(
        "Sales Order Item", filters={"name": ["in", so_details]},
        fields=["name", "parent", "item_code", "qty", "uom", "stock_uom"]) \
        if so_details else []
    detail_parent = {row.name: row.parent for row in detail_rows}
    parents = {_text(item.get("against_sales_order")) for item in items
               if _text(item.get("against_sales_order"))}
    parents |= {row.parent for row in detail_rows if row.parent}
    parents = sorted(parents)
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
    return headers, so_items, permitted, detail_parent


def _candidate_rows(items, headers_by_name):
    item_codes = sorted({_text(item.get("item_code")) for item in items
                         if not _text(item.get("so_detail"))
                         and not _text(item.get("against_sales_order"))
                         and _text(item.get("item_code")) in APPROVED_TARGET_ITEMS})
    customers = sorted({_text(headers_by_name.get(item.get("parent"), {}).get("customer"))
                        for item in items
                        if not _text(item.get("so_detail"))
                        and not _text(item.get("against_sales_order"))
                        and _text(item.get("item_code")) in APPROVED_TARGET_ITEMS})
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


@frappe.whitelist()
def get_delivery_facts(filters=None, **kwargs):
    """DN-item anchored actual delivery facts; SO links are optional edges."""
    filters = _normalize_filters(filters, kwargs)
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

    so_headers, so_items, permitted_sos, so_detail_parent = _load_reference_data(items)
    headers_by_name = {row["name"]: row for row in headers}
    candidates = _candidate_rows(items, headers_by_name)
    logistics = _load_logistics(names)
    result = build_delivery_facts(
        headers, items, so_headers, so_items, permitted_sos, candidates,
        logistics, instance=getattr(frappe.local, "site", "") or "",
        observed_at=_iso(now_datetime()), restricted=restricted,
        so_detail_parent=so_detail_parent)
    result["coverage"]["shipment_permission"] = logistics["shipment_permission"]
    result["coverage"]["shipment_logistics_event"] = logistics["event_status"]
    result["coverage"]["restricted_delivery_notes"] = restricted

    rows = result["delivery_lines"]
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
    result["pagination"] = pagination
    result["applied_filters"] = {key: value for key, value in filters.items()
                                 if key not in ("limit", "offset")}
    result["counts"] = {
        "delivery_notes": len(headers),
        "delivery_lines": total,
        "association_edges": len(result["association_edges"]),
        "coverage_exceptions": len(result["coverage_exceptions"]),
        "so_fulfillment": len(result["so_fulfillment"]),
        "supply_ledger": len(result["supply_ledger"]),
        "physical_chain": len(result["physical_chain"]),
    }
    return result
