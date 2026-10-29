"""Step-3 production evidence layer (pure, read-only).

This module classifies four independent production evidence classes per Work
Order:

* first_process_done
* all_process_done
* qc_performed (inspection executed; not a pass)
* stock_in_posted (book inbound from submitted Manufacture Stock Entries)

``qc_passed`` is emitted separately and, without an explicit coverage quantity,
its quantity stays ``None`` (unknown). No consumer is switched in this batch.

Identity rules (v1):
* Only tracking-number (菲号) evidence is ``proven``.
* Batch cards without a proven common physical identity are ``estimated``.
* Quantities are never summed across operations; a minimum across operations is
  not proof that the same physical units completed every operation.
* Missing/restricted/conflicting inputs are ``None``/``unknown``, never zero.
"""
import json
import math
from collections import Counter, defaultdict

COMPLETED = "Completed"
SUBMITTED = 1
CANCELLED = 2
QC_OPERATION = "质检"

BLOCKING_PROCESS_CONFLICTS = {
    "operation_id_not_found",
    "ambiguous_operation_name",
    "operation_not_in_routing",
    "operation_missing",
    "qty_missing",
    "qty_invalid",
    "zero_completed_qty",
    "duplicate_job_card",
    "duplicate_job_card_payload",
    "tracking_qty_missing",
    "tracking_qty_invalid",
    "tracking_qty_conflict",
    "tracking_reference_missing",
    "routing_work_order_mismatch",
    "job_card_work_order_mismatch",
    "tracking_work_order_mismatch",
}

PROVEN = "proven"
ESTIMATED = "estimated"
UNKNOWN = "unknown"
MIXED = "mixed"


def _parse_number(value):
    """Return (finite number, None) or (None, 'missing'|'invalid')."""
    if value is None or value == "":
        return None, "missing"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(number):
        return None, "invalid"
    return number, None


def _num(value):
    return _parse_number(value)[0]


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _conflict(code, detail=None):
    return {"code": code, "detail": detail or {}}


def _evidence(name, *, proven=None, estimated=None, confidence=UNKNOWN,
              reasons=None, conflicts=None, components=None,
              source_records=None, observed_at=None, **extra):
    row = {
        "class": name,
        "qty_proven": proven,
        "qty_estimated": estimated,
        "qty_unknown": None,
        "confidence": confidence,
        "started_at": None,
        "completed_at": None,
        "time_status": "not_applicable",
        "reasons": list(reasons or []),
        "conflicts": list(conflicts or []),
        "components": dict(components or {}),
        "source_records": list(source_records or []),
        "observed_at": observed_at,
    }
    row.update(extra)
    return row


def _jc_qty(jc):
    return _num(jc.get("total_completed_qty"))


def _valid_jc(jc):
    return _int(jc.get("docstatus")) == SUBMITTED and jc.get("status") == COMPLETED


def _jc_end(jc):
    end = jc.get("actual_end_date")
    if end:
        return end
    ends = [log.get("to_time") for log in (jc.get("time_logs") or []) if log.get("to_time")]
    return max(ends) if ends else None


def _jc_start(jc):
    start = jc.get("actual_start_date")
    if start:
        return start
    starts = [log.get("from_time") for log in (jc.get("time_logs") or [])
              if log.get("from_time")]
    return min(starts) if starts else None


def _time_summary(records):
    if not records:
        return None, None, "not_applicable"
    ends = [_jc_end(jc) for jc in records]
    starts = [_jc_start(jc) for jc in records]
    missing = any(value is None for value in ends + starts)
    completed = None if any(value is None for value in ends) else max(ends)
    started = None if any(value is None for value in starts) else min(starts)
    return started, completed, ("partial_missing" if missing else "complete")


def _assign_time(ev, records, qty, allowed):
    if not allowed or qty is None or qty <= 1e-9:
        ev["started_at"], ev["completed_at"], ev["time_status"] = (
            None, None, "not_applicable")
        return
    ev["started_at"], ev["completed_at"], ev["time_status"] = _time_summary(records)


def _jc_sources(records):
    rows, seen = [], set()
    for jc in records:
        name = jc.get("name")
        if name and name not in seen:
            seen.add(name)
            rows.append({"doctype": "Job Card", "name": name,
                         "operation_id": jc.get("operation_id"),
                         "tracking_number": jc.get("tracking_number") or ""})
    return sorted(rows, key=lambda row: (row["name"],
                                         row.get("operation_id") or "",
                                         row.get("tracking_number") or ""))


def _posted_at(entries):
    if not entries:
        return None, "not_applicable"
    stamps = []
    for entry in entries:
        date, time_value = entry.get("posting_date"), entry.get("posting_time")
        if not date or not time_value:
            return None, "partial_missing"
        stamps.append("%s %s" % (date, time_value))
    return max(stamps), "complete"


def _resolve_operation(jc, ops_by_id, name_counts, by_name):
    operation_id = jc.get("operation_id")
    if operation_id:
        if operation_id in ops_by_id:
            return ops_by_id[operation_id], None
        return None, _conflict("operation_id_not_found",
                               {"operation_id": operation_id,
                                "job_card": jc.get("name")})
    name = jc.get("operation")
    if not name:
        return None, _conflict("operation_missing", {"job_card": jc.get("name")})
    if name_counts.get(name, 0) == 1:
        return by_name[name][0], None
    if name_counts.get(name, 0) > 1:
        return None, _conflict("ambiguous_operation_name",
                               {"operation": name, "job_card": jc.get("name")})
    return None, _conflict("operation_not_in_routing",
                           {"operation": name, "job_card": jc.get("name")})


def _tn_qty(tracking_numbers, wo_name=None):
    values, missing, invalid, conflicts = {}, [], [], []
    by_name = defaultdict(list)
    for row in tracking_numbers or []:
        declared = row.get("work_order")
        if declared and str(declared) != str(wo_name):
            conflicts.append(_conflict("tracking_work_order_mismatch",
                                       {"tracking_number": row.get("name"),
                                        "work_order": declared}))
            continue
        name = row.get("name")
        if name:
            by_name[name].append(row)
    for name, rows in by_name.items():
        kinds, quantities = set(), set()
        for row in rows:
            qty, error = _parse_number(row.get("qty"))
            if error:
                kinds.add(error)
            elif qty <= 0:
                kinds.add("invalid")
            else:
                kinds.add("valid")
                quantities.add(round(qty, 9))
        if kinds == {"valid"} and len(quantities) == 1:
            values[name] = next(iter(quantities))
        elif kinds == {"missing"}:
            values[name] = None
            missing.append(name)
        elif kinds == {"invalid"}:
            values[name] = None
            invalid.append(name)
        else:
            values[name] = None
            conflicts.append(_conflict(
                "tracking_qty_conflict",
                {"tracking_number": name, "kinds": sorted(kinds),
                 "quantities": sorted(quantities)}))
    return (values, sorted(set(missing)), sorted(set(invalid)), conflicts)


def _completed_qty(jc, conflicts):
    qty, error = _parse_number(jc.get("total_completed_qty"))
    if error == "missing":
        conflicts.append(_conflict("qty_missing", {"job_card": jc.get("name")}))
        return None
    if error == "invalid":
        conflicts.append(_conflict("qty_invalid", {"job_card": jc.get("name")}))
        return None
    if qty <= 1e-9:
        conflicts.append(_conflict("zero_completed_qty",
                                   {"job_card": jc.get("name")}))
        return None
    return qty


def _collect_tn_cards(job_cards, tn_names, process_conflicts):
    """Return {(operation_id, tn): [valid completed cards]}."""
    cards = defaultdict(list)
    for jc in job_cards:
        if not _valid_jc(jc):
            continue
        operation = jc.get("_operation")
        if operation is None or operation["is_corrective_operation"]:
            continue
        tn = jc.get("tracking_number") or ""
        if not tn:
            continue
        if tn not in tn_names:
            process_conflicts.append(_conflict(
                "tracking_reference_missing",
                {"tracking_number": tn, "job_card": jc.get("name")}))
            continue
        if _completed_qty(jc, process_conflicts) is None:
            continue
        cards[(operation["name"], tn)].append(jc)
    return cards


def _canonical_jc(jc):
    payload = {key: value for key, value in jc.items() if key != "_operation"}
    return json.dumps(payload, sort_keys=True, default=str)


def _select_tn_card(found, operation_name, tn, conflicts):
    by_name = defaultdict(list)
    for jc in found:
        by_name[jc.get("name")].append(jc)
    if len(by_name) > 1:
        conflicts.append(_conflict(
            "duplicate_job_card",
            {"operation": operation_name, "tracking_number": tn,
             "job_cards": sorted(str(name) for name in by_name)}))
        return None
    if not by_name:
        return None
    name, rows = next(iter(by_name.items()))
    if len({_canonical_jc(jc) for jc in rows}) > 1:
        conflicts.append(_conflict(
            "duplicate_job_card_payload",
            {"operation": operation_name, "tracking_number": tn,
             "job_card": name}))
        return None
    return rows[0]


def _tn_complete(tn, ops, cards, tn_qty, conflicts):
    records = []
    for operation in ops:
        found = cards.get((operation["name"], tn), [])
        if not found:
            return False, []
        jc = _select_tn_card(found, operation["name"], tn, conflicts)
        if jc is None:
            return False, []
        qty = _jc_qty(jc)
        if qty is None or qty + 1e-9 < tn_qty:
            return False, []
        records.append(jc)
    return True, records


def _batch_qty(operation, cards):
    values = []
    for jc in cards.get(operation["name"], []):
        if not _valid_jc(jc):
            continue
        qty = _jc_qty(jc)
        if qty is None:
            continue
        if qty > 1e-9:
            values.append(qty)
    return sum(values) if values else None


def _valid_return_original(original, entry, wo):
    if original is None or original.get("name") == entry.get("name"):
        return False
    if _int(original.get("docstatus")) != SUBMITTED or _int(original.get("is_return")):
        return False
    if original.get("work_order") != wo.get("name"):
        return False
    if original.get("purpose") != "Manufacture":
        return False
    return any(item.get("is_finished_item")
               and item.get("item_code") == wo.get("production_item")
               and item.get("uom") == wo.get("stock_uom")
               for item in original.get("items") or [])


def _stock_in(wo, stock_entries, availability, conflicts):
    if availability.get("stock_entries") is False:
        return _evidence("stock_in_posted", confidence=UNKNOWN,
                         reasons=["permission"])
    if not wo.get("stock_uom"):
        return _evidence("stock_in_posted", confidence=UNKNOWN,
                         reasons=["unit_missing"], conflicts=conflicts)

    # Deduplicate by Stock Entry identity. Identical payloads are idempotent;
    # different payloads for the same name are a conflict, never a second sum.
    unique, seen = [], {}
    net_conflict = False
    for entry in stock_entries or []:
        name = entry.get("name")
        if name:
            payload = json.dumps(entry, sort_keys=True, default=str)
            if name in seen:
                if seen[name] != payload:
                    conflicts.append(_conflict("duplicate_stock_entry_payload",
                                               {"stock_entry": name}))
                    net_conflict = True
                continue
            seen[name] = payload
        unique.append(entry)

    gross, returned, entries, unallocated = 0.0, 0.0, [], 0.0
    for entry in unique:
        if entry.get("work_order") != wo.get("name"):
            continue
        if entry.get("purpose") != "Manufacture" or _int(entry.get("docstatus")) != SUBMITTED:
            continue
        is_return = bool(_int(entry.get("is_return")))
        item_seen = {}
        for item in entry.get("items") or []:
            if not item.get("is_finished_item"):
                continue
            item_name = item.get("name")
            if item_name:
                payload = json.dumps(item, sort_keys=True, default=str)
                if item_name in item_seen:
                    if item_seen[item_name] != payload:
                        conflicts.append(_conflict("duplicate_stock_entry_item",
                                                   {"stock_entry": entry.get("name"),
                                                    "item": item_name}))
                        net_conflict = True
                    continue
                item_seen[item_name] = payload
            qty, error = _parse_number(item.get("qty"))
            if error == "missing":
                conflicts.append(_conflict("stock_in_qty_missing",
                                           {"stock_entry": entry.get("name")}))
                net_conflict = True
                continue
            if error == "invalid":
                conflicts.append(_conflict("stock_in_qty_invalid",
                                           {"stock_entry": entry.get("name")}))
                net_conflict = True
                continue
            if not is_return and qty < 0:
                conflicts.append(_conflict("stock_in_qty_invalid",
                                           {"stock_entry": entry.get("name")}))
                net_conflict = True
                continue
            qty = abs(qty) if is_return else qty
            if item.get("item_code") != wo.get("production_item"):
                code = "return_unallocated" if is_return else "stock_in_item_mismatch"
                conflicts.append(_conflict(code,
                                           {"stock_entry": entry.get("name"),
                                            "item_code": item.get("item_code")}))
                net_conflict = True
                if is_return:
                    unallocated += abs(qty)
                continue
            if not item.get("uom"):
                conflicts.append(_conflict("stock_in_uom_missing",
                                           {"stock_entry": entry.get("name")}))
                net_conflict = True
                continue
            if item.get("uom") != wo.get("stock_uom"):
                conflicts.append(_conflict("stock_in_uom_mismatch",
                                           {"stock_entry": entry.get("name"),
                                            "uom": item.get("uom")}))
                net_conflict = True
                continue
            if is_return:
                reference = (entry.get("outgoing_stock_entry")
                             or item.get("against_stock_entry"))
                if reference:
                    original = next((candidate for candidate in unique
                                     if candidate.get("name") == reference), None)
                    if not _valid_return_original(original, entry, wo):
                        conflicts.append(_conflict("return_reference_invalid",
                                                   {"stock_entry": entry.get("name"),
                                                    "reference": reference}))
                        unallocated += abs(qty)
                        net_conflict = True
                        continue
                else:
                    conflicts.append(_conflict("return_reference_missing",
                                               {"stock_entry": entry.get("name")}))
                returned += abs(qty)
                entries.append(entry)
            else:
                gross += qty
                entries.append(entry)

    net = gross - returned
    if net_conflict:
        qty = None
        confidence = UNKNOWN
    else:
        qty = round(net, 9)
        confidence = PROVEN
    posted_at, time_status = _posted_at(entries)
    source_records, seen_sources = [], set()
    for entry in entries:
        name = entry.get("name")
        if name and name not in seen_sources:
            seen_sources.add(name)
            source_records.append({"doctype": "Stock Entry", "name": name})
    source_records.sort(key=lambda row: row["name"])
    return _evidence(
        "stock_in_posted", proven=qty, estimated=None, confidence=confidence,
        components={"gross_qty": round(gross, 9),
                    "return_qty": round(returned, 9),
                    "net_qty": None if qty is None else qty,
                    "unallocated_return_qty": round(unallocated, 9),
                    "return_rows": len([e for e in entries if _int(e.get("is_return"))])},
        conflicts=conflicts, source_records=source_records,
        posted_at=posted_at, time_status=time_status)


def _qi_reference_ok(qi, job_card_names, stock_entry_names):
    ref_type = qi.get("reference_type")
    if ref_type == "Job Card":
        return qi.get("reference_name") in job_card_names
    if ref_type == "Stock Entry":
        return qi.get("reference_name") in stock_entry_names
    return False


def _qc_passed(wo, quality_inspections, job_cards, stock_entries,
               availability):
    if availability.get("quality_inspections") is False:
        return _evidence("qc_passed", confidence=UNKNOWN, reasons=["permission"])
    job_card_names = {jc.get("name") for jc in job_cards}
    stock_entry_names = {se.get("name") for se in stock_entries or []}
    groups = defaultdict(list)
    qi_conflicts = []
    for qi in quality_inspections or []:
        if _int(qi.get("docstatus")) != SUBMITTED:
            continue
        status = qi.get("status")
        if status not in ("Accepted", "Rejected"):
            continue
        if qi.get("reference_type") not in ("Job Card", "Stock Entry"):
            qi_conflicts.append(_conflict("qi_reference_type_invalid",
                                          {"reference_type": qi.get("reference_type")}))
            continue
        if not _qi_reference_ok(qi, job_card_names, stock_entry_names):
            qi_conflicts.append(_conflict("qi_reference_unallocated",
                                          {"reference_name": qi.get("reference_name")}))
            continue
        if qi.get("item_code") != wo.get("production_item"):
            qi_conflicts.append(_conflict("qi_item_mismatch",
                                          {"item_code": qi.get("item_code")}))
            continue
        groups[(qi.get("reference_type"), qi.get("reference_name"),
                qi.get("item_code"))].append(qi)

    accepted, rejected, coverage_values = [], [], []
    for group in groups.values():
        statuses = {qi.get("status") for qi in group}
        if {"Accepted", "Rejected"} <= statuses:
            qi_conflicts.append(_conflict("qi_result_conflict",
                                          {"reference_name": group[0].get("reference_name")}))
        accepted_here = [qi for qi in group if qi.get("status") == "Accepted"]
        rejected_here = [qi for qi in group if qi.get("status") == "Rejected"]
        if len(accepted_here) > 1:
            qi_conflicts.append(_conflict("qi_coverage_conflict",
                                          {"reference_name": group[0].get("reference_name")}))
        accepted.extend(accepted_here)
        rejected.extend(rejected_here)
        coverage_values.extend(_num(qi.get("coverage_qty")) for qi in accepted_here
                               if _num(qi.get("coverage_qty")) is not None)

    source_records = [{"doctype": "Quality Inspection", "name": qi.get("name"),
                       "status": qi.get("status")}
                      for group in groups.values() for qi in group]
    source_records.sort(key=lambda row: (row.get("name") or "", row.get("status") or ""))
    if qi_conflicts:
        return _evidence("qc_passed", confidence=UNKNOWN,
                         reasons=["qc_result_conflict"], conflicts=qi_conflicts,
                         status=None, qty=None, source_records=source_records,
                         coverage_values=coverage_values)
    if accepted:
        # v1 deliberately keeps the passed quantity unknown: Accepted and
        # sample_size/coverage do not prove which physical units passed.
        return _evidence("qc_passed", confidence=UNKNOWN,
                         reasons=["coverage_qty_not_available"],
                         conflicts=qi_conflicts, status="Accepted", qty=None,
                         source_records=source_records,
                         coverage_values=coverage_values)
    if rejected:
        return _evidence("qc_passed", confidence=UNKNOWN,
                         reasons=["qc_rejected"], conflicts=qi_conflicts,
                         status="Rejected", qty=None, source_records=source_records)
    return _evidence("qc_passed", confidence=UNKNOWN,
                     reasons=["qc_result_not_recorded"], conflicts=qi_conflicts,
                     status=None, qty=None, source_records=source_records)


def _dedupe_job_cards(cards, conflicts):
    """Deduplicate replays by JC identity + full payload before pools split."""
    unique, by_name = [], defaultdict(list)
    for jc in cards:
        name = jc.get("name")
        if name:
            by_name[name].append(jc)
        else:
            unique.append(jc)
    for name, rows in by_name.items():
        if len({_canonical_jc(jc) for jc in rows}) > 1:
            conflicts.append(_conflict("duplicate_job_card_payload",
                                       {"job_card": name}))
            continue
        unique.append(rows[0])
    return unique


def build_wo_evidence(wo, operations, job_cards, tracking_numbers=None,
                      stock_entries=None, quality_inspections=None,
                      order_uom=None, availability=None, observed_at=None):
    """Build four evidence classes plus qc_performed/qc_passed for one WO."""
    availability = dict(availability or {})
    stock_entries = list(stock_entries or [])
    quality_inspections = list(quality_inspections or [])
    tracking_numbers = list(tracking_numbers or [])
    global_conflicts = []
    process_conflicts = []

    ops = []
    for row in operations or []:
        row = dict(row)
        declared = row.get("work_order") or row.get("parent")
        if declared and str(declared) != str(wo.get("name")):
            process_conflicts.append(_conflict(
                "routing_work_order_mismatch",
                {"routing": row.get("name"), "work_order": declared}))
            continue
        row["is_corrective_operation"] = bool(_int(row.get("is_corrective_operation")))
        ops.append(row)
    ops_by_id = {row.get("name"): row for row in ops}
    by_name = defaultdict(list)
    for row in ops:
        by_name[row.get("operation")].append(row)
    name_counts = Counter(row.get("operation") for row in ops)

    # Resolve every Job Card to a routing row exactly once; unresolved cards are
    # conflicts, never silently matched by operation name.
    resolved_cards = []
    for jc in job_cards or []:
        declared = jc.get("work_order")
        if declared and str(declared) != str(wo.get("name")):
            process_conflicts.append(_conflict(
                "job_card_work_order_mismatch",
                {"job_card": jc.get("name"), "work_order": declared}))
            continue
        operation, conflict = _resolve_operation(jc, ops_by_id, name_counts, by_name)
        if conflict:
            process_conflicts.append(conflict)
            continue
        jc = dict(jc)
        jc["_operation"] = operation
        resolved_cards.append(jc)
    resolved_cards = _dedupe_job_cards(resolved_cards, process_conflicts)

    required = sorted([row for row in ops if not row["is_corrective_operation"]],
                      key=lambda row: (_num(row.get("sequence_id")) or 0,
                                       row.get("operation") or ""))
    required_ids = {row["name"] for row in required}
    if required:
        first_seq = min(_num(row.get("sequence_id")) or 0 for row in required)
        first_ops = [row for row in required
                     if (_num(row.get("sequence_id")) or 0) == first_seq]
    else:
        first_ops = []

    tn_values, tn_missing, tn_invalid, tn_conflicts = _tn_qty(
        tracking_numbers, wo.get("name"))
    tn_names = set(tn_values)
    has_tn = bool(tn_names)
    process_conflicts.extend(tn_conflicts)
    cards = _collect_tn_cards(resolved_cards, tn_names, process_conflicts)

    tn_first, tn_all = 0.0, 0.0
    first_records, all_records = [], []
    valid_tn_count = 0
    for tn in tn_names:
        tn_qty = tn_values.get(tn)
        if tn_qty is None:
            continue
        valid_tn_count += 1
        if first_ops:
            ok, records = _tn_complete(tn, first_ops, cards, tn_qty, process_conflicts)
            if ok:
                tn_first += tn_qty
                first_records.extend(records)
        if required:
            ok, records = _tn_complete(tn, required, cards, tn_qty, process_conflicts)
            if ok:
                tn_all += tn_qty
                all_records.extend(records)

    tn_first_value = round(tn_first, 9) if valid_tn_count else None
    tn_all_value = round(tn_all, 9) if valid_tn_count else None
    if has_tn and tn_missing:
        process_conflicts.append(_conflict("tracking_qty_missing",
                                           {"tracking_numbers": tn_missing}))
    if has_tn and tn_invalid:
        process_conflicts.append(_conflict("tracking_qty_invalid",
                                           {"tracking_numbers": tn_invalid}))

    batch_cards = defaultdict(list)
    for jc in resolved_cards:
        if not _valid_jc(jc):
            continue
        if jc.get("tracking_number"):
            continue
        if jc["_operation"]["name"] not in required_ids:
            continue
        if _completed_qty(jc, process_conflicts) is None:
            continue
        batch_cards[jc["_operation"]["name"]].append(jc)
    batch_first_qty = {op["name"]: _batch_qty(op, batch_cards) for op in first_ops}
    batch_all_qty = {op["name"]: _batch_qty(op, batch_cards) for op in required}
    batch_first_complete = bool(first_ops) and all(
        batch_first_qty.get(op["name"]) is not None for op in first_ops)
    batch_all_complete = bool(required) and all(
        batch_all_qty.get(op["name"]) is not None for op in required)
    batch_first_est = (min(batch_first_qty[op["name"]] for op in first_ops)
                       if batch_first_complete else None)
    batch_all_est = (min(batch_all_qty[op["name"]] for op in required)
                     if batch_all_complete else None)
    has_batch = any(batch_all_qty.get(op["name"]) is not None for op in required)
    if has_batch:
        process_conflicts.append(_conflict("batch_identity_unproven", {}))

    # Blocked sources / unit mismatch / cancelled WO: process evidence is unknown,
    # but a valid submitted Stock Entry remains a stock fact.
    permission_blocked = (availability.get("work_order") is False
                          or availability.get("job_cards") is False)
    blocked_reasons = []
    if availability.get("work_order") is False:
        blocked_reasons.append("permission")
    if availability.get("job_cards") is False:
        blocked_reasons.append("permission")
    if _int(wo.get("docstatus")) == CANCELLED:
        blocked_reasons.append("wo_cancelled")
        global_conflicts.append(_conflict("wo_cancelled", {}))
    if not wo.get("stock_uom"):
        blocked_reasons.append("unit_missing")
    elif order_uom and order_uom != wo.get("stock_uom"):
        blocked_reasons.append("unit_mismatch")

    if blocked_reasons:
        blocked_conflicts = [] if permission_blocked else process_conflicts
        first = _evidence("first_process_done", confidence=UNKNOWN,
                          reasons=blocked_reasons, conflicts=blocked_conflicts)
        all_ev = _evidence("all_process_done", confidence=UNKNOWN,
                           reasons=blocked_reasons, conflicts=blocked_conflicts)
        qc_perf = _evidence("qc_performed", confidence=UNKNOWN,
                            reasons=blocked_reasons, conflicts=blocked_conflicts)
        qc_records = []
    else:
        # first_process_done: TN evidence is proven; batch is estimated.
        if has_tn and (tn_missing or tn_invalid) and valid_tn_count == 0:
            first_proven, first_conf = None, UNKNOWN
        elif has_tn:
            first_proven, first_conf = tn_first_value, PROVEN
        elif batch_first_complete:
            first_proven, first_conf = None, ESTIMATED
        else:
            first_proven, first_conf = 0.0, PROVEN
        first_reasons = []
        if has_batch:
            first_reasons.append("batch_identity_unproven")
        if tn_missing:
            first_reasons.append("tracking_qty_missing")
        if tn_invalid:
            first_reasons.append("tracking_qty_invalid")
        if first_proven is not None and batch_first_est is not None:
            first_conf = MIXED
        first = _evidence(
            "first_process_done", proven=first_proven, estimated=batch_first_est,
            confidence=first_conf, reasons=first_reasons,
            conflicts=process_conflicts,
            components={"tn_qty": tn_first_value, "batch_qty": batch_first_est})

        # all_process_done: only TN is proven. A complete batch pool without
        # identity makes the total unknown (overlap cannot be proven).
        all_reasons = []
        if tn_missing:
            all_reasons.append("tracking_qty_missing")
        if tn_invalid:
            all_reasons.append("tracking_qty_invalid")
        if has_tn and batch_all_complete:
            all_proven, all_est, all_conf = None, batch_all_est, UNKNOWN
            all_reasons.extend(["batch_identity_unproven", "pool_overlap_unknown"])
        elif has_tn:
            if (tn_missing or tn_invalid) and valid_tn_count == 0:
                all_proven, all_est, all_conf = None, None, UNKNOWN
            else:
                all_proven, all_est, all_conf = tn_all_value, None, PROVEN
        elif batch_all_complete:
            all_proven, all_est, all_conf = None, batch_all_est, ESTIMATED
            all_reasons.append("batch_identity_unproven")
        elif has_batch:
            all_proven, all_est, all_conf = 0.0, None, PROVEN
            all_reasons.append("batch_pool_incomplete")
        else:
            all_proven, all_est, all_conf = 0.0, None, PROVEN
            all_reasons.append("no_evidence")
        all_ev = _evidence(
            "all_process_done", proven=all_proven, estimated=all_est,
            confidence=all_conf, reasons=all_reasons, conflicts=process_conflicts,
            components={"tn_qty": tn_all_value, "batch_qty": batch_all_est})

        # qc_performed: inspection executed (not a pass); TN proven, batch estimated.
        qc_ops = [op for op in required if op.get("operation") == QC_OPERATION]
        qc_proven, qc_est = 0.0, None
        qc_records = []
        if qc_ops:
            qc_op = qc_ops[0]
            for tn in tn_names:
                tn_qty = tn_values.get(tn)
                if tn_qty is None:
                    continue
                found = cards.get((qc_op["name"], tn), [])
                if not found:
                    continue
                jc = _select_tn_card(found, qc_op["name"], tn, process_conflicts)
                if jc is None:
                    continue
                qty = _jc_qty(jc)
                if qty is not None and qty > 1e-9:
                    qc_proven += min(qty, tn_qty)
                    qc_records.append(jc)
            qc_batch = _batch_qty(qc_op, batch_cards)
            qc_est = qc_batch
            qc_records.extend(batch_cards.get(qc_op["name"], []))
        qc_perf = _evidence(
            "qc_performed",
            proven=round(qc_proven, 9) if has_tn else None,
            estimated=qc_est, confidence=MIXED if (has_tn and qc_est) else
            (PROVEN if has_tn else (ESTIMATED if qc_est else PROVEN)),
            reasons=["no_qc_operation"] if not qc_ops else [],
            conflicts=process_conflicts,
            components={"tn_qty": round(qc_proven, 9) if has_tn else None,
                        "batch_qty": qc_est})

    process_unknown = any(conflict["code"] in BLOCKING_PROCESS_CONFLICTS
                          for conflict in process_conflicts)
    if process_unknown and not blocked_reasons:
        for ev in (first, all_ev, qc_perf):
            if ev["qty_proven"] in (0, 0.0, None):
                ev["qty_proven"] = None
            ev["confidence"] = UNKNOWN
            ev["reasons"] = sorted(set(ev["reasons"] + ["conflict"]))

    first_records_for_time = first_records or [
        jc for op in first_ops for jc in batch_cards.get(op["name"], [])]
    all_records_for_time = all_records or [
        jc for op in required for jc in batch_cards.get(op["name"], [])]
    allowed_time = not blocked_reasons and not process_unknown
    first_qty = (first["qty_proven"] if first["qty_proven"] is not None
                 else first["qty_estimated"])
    all_qty = (all_ev["qty_proven"] if all_ev["qty_proven"] is not None
               else all_ev["qty_estimated"])
    qc_qty = (qc_perf["qty_proven"] if qc_perf["qty_proven"] is not None
              else qc_perf["qty_estimated"])
    _assign_time(first, first_records_for_time, first_qty, allowed_time)
    _assign_time(all_ev, all_records_for_time, all_qty, allowed_time)
    _assign_time(qc_perf, qc_records, qc_qty, allowed_time)
    first["source_records"] = _jc_sources(first_records_for_time)
    all_ev["source_records"] = _jc_sources(all_records_for_time)
    qc_perf["source_records"] = _jc_sources(qc_records)

    if not required and not blocked_reasons:
        for ev in (first, all_ev, qc_perf):
            ev.update({"qty_proven": None, "qty_estimated": None,
                       "confidence": UNKNOWN, "reasons": ["no_routing"],
                       "started_at": None, "completed_at": None,
                       "time_status": "not_applicable"})
    if (tn_missing or tn_invalid) and not blocked_reasons:
        for ev in (first, all_ev, qc_perf):
            ev["confidence"] = UNKNOWN
    if permission_blocked:
        for ev in (first, all_ev, qc_perf):
            ev.update({"qty_proven": None, "qty_estimated": None,
                       "confidence": UNKNOWN, "reasons": ["permission"],
                       "source_records": [], "components": {}, "conflicts": [],
                       "started_at": None, "completed_at": None,
                       "time_status": "not_applicable"})

    stock_conflicts = []
    stock = _stock_in(wo, stock_entries, availability, stock_conflicts)
    wo_job_cards = [jc for jc in job_cards or []
                    if not jc.get("work_order")
                    or str(jc.get("work_order")) == str(wo.get("name"))]
    wo_stock_entries = [se for se in stock_entries
                        if not se.get("work_order")
                        or str(se.get("work_order")) == str(wo.get("name"))]
    qc_passed = _qc_passed(wo, quality_inspections, wo_job_cards,
                           wo_stock_entries, availability)
    for ev in (first, all_ev, qc_perf, qc_passed, stock):
        ev["observed_at"] = observed_at
    global_conflicts.extend(stock_conflicts)
    global_conflicts.extend(qc_passed.get("conflicts", []))
    if (_int(wo.get("docstatus")) == CANCELLED
            and stock.get("qty_proven") not in (None, 0, 0.0)):
        global_conflicts.append(_conflict("wo_cancelled_with_valid_stock_in",
                                          {"wo": wo.get("name"),
                                           "qty": stock.get("qty_proven")}))

    return {
        "wo": wo.get("name"),
        "uom": wo.get("stock_uom"),
        "required_operations": [] if permission_blocked else required,
        "first_process_done": first,
        "all_process_done": all_ev,
        "qc_performed": qc_perf,
        "qc_passed": qc_passed,
        "stock_in_posted": stock,
        "conflicts": global_conflicts,
        "reasons": sorted({reason for ev in (first, all_ev, qc_perf, qc_passed, stock)
                           for reason in ev.get("reasons", [])}),
    }


def aggregate_wo_evidence(evidence_list):
    """Keep work orders separate; never collapse them into one physical batch."""
    rows = list(evidence_list or [])
    return {
        "work_orders": rows,
        "wo_count": len(rows),
        "qty_proven": None,
        "qty_estimated": None,
        "reason": "per_wo_only",
    }


def _roll_confidence(rows, field, proven, estimated):
    if any(row[field].get("confidence") == UNKNOWN for row in rows):
        return UNKNOWN
    if proven is not None and estimated not in (None, 0, 0.0):
        return MIXED
    if proven is not None:
        return PROVEN
    if estimated is not None:
        return ESTIMATED
    return UNKNOWN


def _roll_qty(rows, field, qty_field):
    if any(row[field].get("confidence") == UNKNOWN for row in rows):
        return None
    values = [row[field].get(qty_field) for row in rows]
    present = [value for value in values if value is not None]
    return round(sum(present), 9) if present else None


def unknown_line_evidence(reason="permission"):
    """Line-level unknown when process sources cannot be read/queried."""
    empty = _evidence("all_process_done", confidence=UNKNOWN, reasons=[reason])
    return {
        "work_orders": [], "wo_count": 0,
        "first_process_done": dict(empty, **{"class": "first_process_done"}),
        "all_process_done": empty,
        "qc_performed": dict(empty, **{"class": "qc_performed"}),
        "qc_passed": _evidence("qc_passed", confidence=UNKNOWN, reasons=[reason]),
        "stock_in_posted": _evidence("stock_in_posted", confidence=UNKNOWN,
                                     reasons=[reason]),
        "conflicts": [], "source_records": [],
    }


def rollup_line_evidence(evidence_list):
    """Aggregate per-WO evidence for one SO line without merging identities."""
    rows = list(evidence_list or [])
    if not rows:
        empty = _evidence("all_process_done", proven=0.0, confidence=PROVEN)
        return {
            "work_orders": [], "wo_count": 0,
            "first_process_done": dict(empty, **{"class": "first_process_done"}),
            "all_process_done": empty,
            "qc_performed": dict(empty, **{"class": "qc_performed",
                                           "qty_proven": None}),
            "qc_passed": _evidence("qc_passed", confidence=UNKNOWN,
                                   reasons=["qc_result_not_recorded"]),
            "stock_in_posted": _evidence("stock_in_posted", proven=0.0,
                                         confidence=PROVEN),
            "conflicts": [], "source_records": [],
        }

    def rolled(field):
        proven = _roll_qty(rows, field, "qty_proven")
        estimated = _roll_qty(rows, field, "qty_estimated")
        return {
            "class": field,
            "qty_proven": proven,
            "qty_estimated": estimated,
            "confidence": _roll_confidence(rows, field, proven, estimated),
            "reasons": sorted({reason for row in rows
                               for reason in row[field].get("reasons", [])}),
            "conflicts": [conflict for row in rows
                          for conflict in row[field].get("conflicts", [])],
            "source_records": sorted(
                [source for row in rows for source in row[field].get("source_records", [])],
                key=lambda source: (source.get("doctype", ""), source.get("name", ""))),
        }

    first = rolled("first_process_done")
    all_process = rolled("all_process_done")
    qc_performed = rolled("qc_performed")
    stock = rolled("stock_in_posted")
    qc_passed = _evidence(
        "qc_passed", confidence=UNKNOWN,
        reasons=sorted({reason for row in rows
                        for reason in row["qc_passed"].get("reasons", [])}),
        conflicts=[conflict for row in rows
                   for conflict in row["qc_passed"].get("conflicts", [])],
        source_records=sorted(
            [source for row in rows for source in row["qc_passed"].get("source_records", [])],
            key=lambda source: (source.get("doctype", ""), source.get("name", ""))),
        status=(rows[0]["qc_passed"].get("status") if rows else None))
    return {
        "work_orders": rows,
        "wo_count": len(rows),
        "first_process_done": first,
        "all_process_done": all_process,
        "qc_performed": qc_performed,
        "qc_passed": qc_passed,
        "stock_in_posted": stock,
        "conflicts": [conflict for row in rows for conflict in row.get("conflicts", [])],
        "source_records": sorted(
            [source for row in rows for source in row.get("source_records", [])],
            key=lambda source: (source.get("doctype", ""), source.get("name", ""))),
    }
