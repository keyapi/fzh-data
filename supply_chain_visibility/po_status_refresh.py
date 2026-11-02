# -*- coding: utf-8 -*-
"""Batched, resumable PO status refresh.

The caller supplies ``query_many(codes)`` (the delivery_plan batch endpoint,
max 10 codes / 5 cold lookups per call). This module never treats
``partial``/``exhausted=false`` as success and records every unqueried code.
"""
from __future__ import annotations

MAX_BATCH = 10
MAX_COLD = 5


def dedupe_po_codes(item_to_po):
    """Collapse SKU->PO mappings into a unique PO set (no per-SKU queries)."""
    if isinstance(item_to_po, dict):
        values = []
        for codes in item_to_po.values():
            if isinstance(codes, (list, tuple, set)):
                values.extend(codes)
            elif codes:
                values.append(codes)
    else:
        values = [row[1] if isinstance(row, (list, tuple)) else row
                  for row in item_to_po]
    return sorted({str(code).strip() for code in values if str(code).strip()})


def _status(entry, reason, source_status):
    return {
        "found": bool((entry or {}).get("found")) and source_status == "known",
        "raw_status": (entry or {}).get("raw_status"),
        "is_voided": bool((entry or {}).get("is_voided")),
        "source_status": source_status,
        "reason": reason,
    }


def refresh_po_statuses(codes, query_many, *, batch_size=MAX_BATCH,
                        start_index=0):
    """Refresh in batches; returns statuses, unqueried codes and a checkpoint."""
    unique = sorted({str(code).strip() for code in codes or [] if str(code).strip()})
    batches = [unique[index:index + batch_size]
               for index in range(0, len(unique), batch_size)]
    statuses = {}
    unqueried = {}
    termination = "completed"
    exhausted = False
    next_index = len(batches)
    for index in range(max(0, start_index), len(batches)):
        batch = batches[index]
        try:
            response = query_many(batch) or {}
        except Exception as exc:  # noqa: BLE001 - never turn a batch into 500
            for code in batch:
                statuses[code] = _status(None, "source_error", "source_error")
                unqueried[code] = "source_error"
            for rest in batches[index + 1:]:
                for code in rest:
                    statuses[code] = _status(None, "source_error", "not_queried")
                    unqueried[code] = "source_error"
            return {
                "statuses": statuses, "unqueried": unqueried,
                "requested": len(unique), "returned": len(statuses),
                "next_index": index, "resume_at": index,
                "exhausted": False, "partial": True,
                "termination_reason": "source_error",
                "error": str(exc)[:200],
                "note": "unqueried codes are explicit; partial is never treated as success",
            }
        results = response.get("results") or {}
        for code in batch:
            entry = results.get(code)
            if entry is None:
                statuses[code] = _status(None, "missing_in_response", "not_queried")
                unqueried[code] = "missing_in_response"
                continue
            reason = entry.get("reason")
            if reason in ("rate_limited", "partial_not_queried",
                          "truncated_not_queried"):
                statuses[code] = _status(None, reason, "not_queried")
                unqueried[code] = reason
            elif reason in ("source_error", "not_permitted"):
                statuses[code] = _status(None, reason, "source_error")
                unqueried[code] = reason
            else:
                statuses[code] = _status(entry, "", "known")
        if response.get("exhausted") or response.get("termination_reason") == "rate_limited":
            exhausted = True
            termination = response.get("termination_reason") or "rate_limited"
            next_index = index
            for rest in batches[index + 1:]:
                for code in rest:
                    statuses[code] = _status(None, "rate_limited", "not_queried")
                    unqueried[code] = "rate_limited"
            break
        if response.get("partial") and response.get("termination_reason") not in (None, "", "completed"):
            termination = response.get("termination_reason")
    return {
        "statuses": statuses,
        "unqueried": unqueried,
        "requested": len(unique),
        "returned": len(statuses),
        "next_index": next_index,
        "resume_at": next_index if next_index < len(batches) else None,
        "exhausted": exhausted,
        "partial": bool(unqueried) or termination != "completed",
        "termination_reason": termination,
        "note": "unqueried codes are explicit; partial is never treated as success",
    }
