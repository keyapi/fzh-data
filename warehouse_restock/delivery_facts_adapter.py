# -*- coding: utf-8 -*-
"""Read-only adapter from delivery facts to warehouse_restock.

It answers "what did we actually deliver for each approved target item, and
what is still unresolved" without computing purchase orders.  Unknown stays
unknown; no automatic ordering; FBA and in-house channels are never summed.
"""
from __future__ import annotations

from collections import defaultdict

SCOPE_VERSION = "jack_w1_sample9_2026-10-26"
# Kept in sync with key_test.delivery_facts.APPROVED_TARGET_ITEMS.
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


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round(value):
    return None if value is None else round(_num(value), 6)


def build_restock_delivery_view(delivery, *, fba_item_codes=(),
                                channel_by_item=None):
    """Return one row per approved target item (plus conservation summary)."""
    lines = list((delivery or {}).get("delivery_lines") or [])
    coverage = (delivery or {}).get("coverage") or {}
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
        grouped[line.get("item_code")].append(line)

    rows = []
    for item_code in sorted(APPROVED_TARGET_ITEMS):
        meta = APPROVED_TARGET_ITEMS[item_code]
        item_lines = [line for line in grouped.get(item_code, [])
                      if line.get("relevance_status") == "in_scope"]
        current = [line for line in item_lines
                   if line.get("docstatus") == 1]
        actual = sum(_num(line.get("actual_qty")) for line in current)
        linked = sum(_num(line.get("actual_qty")) for line in current
                     if line.get("association_status") == "linked")
        unlinked = sum(_num(line.get("actual_qty")) for line in current
                       if line.get("association_status") == "unlinked")
        unknown_qty = sum(_num(line.get("actual_qty")) for line in current
                          if line.get("uom_status") != "known")
        uom_unknown = any(line.get("uom_status") != "known" for line in current)
        if not current:
            actual_value = None
            qty_status = "no_observed_delivery"
        elif uom_unknown:
            actual_value = None
            qty_status = "unknown_uom"
        else:
            actual_value = _round(actual)
            qty_status = "known"
        channel = (channel_map.get(item_code)
                   or ("fba" if item_code in fba_items else "unknown"))
        if channel not in ("fba", "in_house", "unknown"):
            channel = "unknown"
        if channel == "unknown":
            action = "manual_review_channel_unknown"
        elif qty_status != "known":
            action = "manual_review_delivery_unknown"
        elif abs(unlinked) > 1e-9:
            action = "manual_review_unlinked_delivery"
        else:
            action = "candidate_no_action"
        rows.append({
            "item_code": item_code,
            "customer_sku": meta.get("customer_sku"),
            "scope_slot": meta.get("slot"),
            "scope_rule_version": SCOPE_VERSION,
            "channel": channel,
            "actual_delivery_qty": actual_value,
            "qty_status": qty_status,
            "linked_delivery_qty": _round(linked) if qty_status == "known" else None,
            "unlinked_delivery_qty": _round(unlinked) if qty_status == "known" else None,
            "unknown_delivery_qty": _round(unknown_qty) if unknown_qty else None,
            "received_qty": None,
            "pending_qty": None,
            "inventory_qty": None,
            "receipt_source_status": "not_integrated",
            "inventory_source_status": "not_integrated",
            "eligible_for_restock": False,
            "suggested_action": action,
            "auto_order": False,
            "note": ("只输出行动建议；未关联交付/渠道/入库未证前不进入补货量"
                     if action != "candidate_no_action" else
                     "当前仅证明交付事实，不证明额外供应"),
        })
    in_scope = [line for line in lines
                if line.get("relevance_status") == "in_scope"
                and line.get("docstatus") == 1]
    out_scope = [line for line in lines
                 if line.get("relevance_status") == "out_of_scope"
                 and line.get("docstatus") == 1]
    return {
        "scope_rule_version": SCOPE_VERSION,
        "rows": rows,
        "summary": {
            "approved_items": len(rows),
            "in_scope_actual_delivery_qty": _round(
                sum(_num(line.get("actual_qty")) for line in in_scope)),
            "out_of_scope_actual_delivery_qty": _round(
                sum(_num(line.get("actual_qty")) for line in out_scope)),
            "duplicate_line_ids": duplicates,
            "duplicate_free": not duplicates,
            "conservation_actual_delivery_qty": (
                coverage.get("conservation") or {}).get("actual_delivery_qty"),
            "auto_order": False,
            "note": "No purchase order is generated by this adapter.",
        },
    }
