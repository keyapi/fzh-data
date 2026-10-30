"""Signed Shipment -> Tongtool purchase receipt reconciliation (pure).

The only accepted association is an already-proven chain:
Shipment -> Delivery Note -> DN.custom_tongtool_purchase_order -> Tongtool PO
-> receipt line (same SKU / warehouse / UOM).

No quantity equality, date proximity, or same-SKU guess is ever used. A
receipt that cannot be allocated to exactly one link stays unknown and is not
counted; duplicate payloads are counted once, conflicting payloads are unknown.

``received_qty == 0`` is only allowed when the caller proves the collection
range was complete. Without a complete coverage envelope, an empty receipt set
means "unknown", never zero.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

STAGE_IN_TRANSIT = "in_transit"
STAGE_PENDING = "signed_pending_tongtool_receipt"
STAGE_RECEIVED = "tongtool_received"
STAGE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReceiptCoverage:
    query_range_complete: bool = False
    requested_windows: tuple = ()
    truncated_windows: tuple = ()
    not_collected_windows: tuple = ()
    source_as_of: Optional[str] = None
    covered_po_codes: tuple = ()
    coverage_mode: str = "time_range"
    po_full_history_proven: bool = False
    po_full_history_source: Optional[str] = None
    po_full_history_as_of: Optional[str] = None
    invalid_reason: Optional[str] = None

    @property
    def structural_complete(self) -> bool:
        if self.invalid_reason is not None or not self.query_range_complete:
            return False
        if self.truncated_windows or self.not_collected_windows:
            return False
        if self.coverage_mode == "po_full_history":
            return bool(self.po_full_history_proven
                        and self.po_full_history_source
                        and self.po_full_history_as_of)
        return bool(self.requested_windows)

    @property
    def complete(self) -> bool:
        return self.structural_complete

    def po_scope_proven(self, po_codes) -> bool:
        codes = {str(code).strip() for code in (po_codes or ()) if str(code).strip()}
        covered = {str(code).strip() for code in self.covered_po_codes
                   if str(code).strip()}
        return bool(codes) and codes <= covered

    def covers_interval(self, start, end) -> bool:
        """True when merged windows continuously cover [start, end]."""
        start_dt, end_dt = _aware_parse(start), _aware_parse(end)
        if start_dt is None or end_dt is None or start_dt > end_dt:
            return False
        bounds = sorted(
            (parsed_start, parsed_end)
            for parsed_start, parsed_end in (
                (_aware_parse(a), _aware_parse(b))
                for a, b in self.requested_windows)
            if parsed_start is not None and parsed_end is not None)
        if not bounds:
            return False
        cursor = start_dt
        for window_start, window_end in bounds:
            if window_end < cursor:
                continue
            if window_start > cursor:
                return False
            if window_end > cursor:
                cursor = window_end
            if cursor >= end_dt:
                return True
        return cursor >= end_dt

    def proves(self, po_codes, signed_at=None) -> bool:
        """Link-specific proof: PO scope plus complete time coverage."""
        if not self.structural_complete or not self.po_scope_proven(po_codes):
            return False
        if self.coverage_mode == "po_full_history":
            return True
        if not signed_at:
            return False
        return self.covers_interval(signed_at, self.source_as_of)

    def status_for(self, po_codes, signed_at=None) -> str:
        if self.invalid_reason:
            return "invalid"
        if not self.structural_complete:
            return "incomplete"
        if not self.po_scope_proven(po_codes):
            return "scope_mismatch"
        return "complete" if self.proves(po_codes, signed_at) else "incomplete"

    def status(self) -> str:
        if self.invalid_reason:
            return "invalid"
        return "complete" if self.structural_complete else "incomplete"

    def as_dict(self) -> dict:
        return {
            "query_range_complete": bool(self.query_range_complete),
            "requested_windows": _window_list(self.requested_windows),
            "truncated_windows": _window_list(self.truncated_windows),
            "not_collected_windows": _window_list(self.not_collected_windows),
            "source_as_of": self.source_as_of,
            "covered_po_codes": list(self.covered_po_codes),
            "coverage_mode": self.coverage_mode,
            "po_full_history_proven": bool(self.po_full_history_proven),
            "po_full_history_source": self.po_full_history_source,
            "po_full_history_as_of": self.po_full_history_as_of,
            "window_gaps": self.window_gaps(),
            "complete": self.structural_complete,
            "invalid_reason": self.invalid_reason,
        }

    def window_gaps(self) -> list:
        bounds = sorted(
            (parsed_start, parsed_end)
            for parsed_start, parsed_end in (
                (_aware_parse(a), _aware_parse(b))
                for a, b in self.requested_windows)
            if parsed_start is not None and parsed_end is not None)
        gaps = []
        cursor = None
        for window_start, window_end in bounds:
            if cursor is not None and window_start > cursor:
                gaps.append({"start": cursor.isoformat(),
                             "end": window_start.isoformat()})
            cursor = window_end if cursor is None else max(cursor, window_end)
        return gaps

    @classmethod
    def from_mapping(cls, value) -> Optional["ReceiptCoverage"]:
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return cls(invalid_reason="coverage_not_object")
        truncated_windows = _window_pairs(value.get("truncated_windows"))
        if value.get("truncated") is True and not truncated_windows:
            truncated_windows = (("truncated", "truncated"),)
        not_collected = value.get("not_collected")
        if not_collected is True:
            not_collected = (("not_collected", "not_collected"),)
        else:
            not_collected = _window_pairs(not_collected)
        windows = _window_pairs(value.get("requested_windows"))
        covered = tuple(
            str(code).strip() for code in value.get("covered_po_codes") or ()
            if str(code).strip())
        mode = value.get("coverage_mode") or "time_range"
        invalid = None
        if mode not in ("time_range", "po_full_history"):
            invalid = "coverage_mode_unknown"
        elif mode == "po_full_history":
            if value.get("po_full_history_proven") is not True:
                invalid = "po_full_history_unproven"
            elif not str(value.get("po_full_history_source") or "").strip():
                invalid = "po_full_history_source_missing"
            elif _aware_parse(value.get("po_full_history_as_of")) is None:
                invalid = "po_full_history_as_of_unverified"
        else:
            if not windows:
                invalid = "requested_windows_empty"
            else:
                for start, end in windows:
                    parsed_start, parsed_end = _aware_parse(start), _aware_parse(end)
                    if parsed_start is None or parsed_end is None:
                        invalid = "window_time_unverified"
                        break
                    if parsed_start > parsed_end:
                        invalid = "window_reversed"
                        break
            if invalid is None:
                as_of = _aware_parse(value.get("source_as_of"))
                if as_of is None:
                    invalid = "source_as_of_unverified"
                elif any(_aware_parse(end) > as_of for _, end in windows):
                    invalid = "source_as_of_before_window_end"
        return cls(
            query_range_complete=value.get("query_range_complete") is True,
            requested_windows=windows,
            truncated_windows=truncated_windows,
            not_collected_windows=not_collected,
            source_as_of=value.get("source_as_of"),
            covered_po_codes=covered,
            coverage_mode=mode,
            po_full_history_proven=value.get("po_full_history_proven") is True,
            po_full_history_source=value.get("po_full_history_source"),
            po_full_history_as_of=value.get("po_full_history_as_of"),
            invalid_reason=invalid,
        )


def _window_pairs(value) -> tuple:
    pairs = []
    for entry in value or ():
        if isinstance(entry, dict):
            start, end = entry.get("start"), entry.get("end")
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            start, end = entry
        else:
            start = end = entry
        if start is None and end is None:
            continue
        pairs.append((start, end))
    return tuple(pairs)


def _window_list(pairs) -> list:
    return [{"start": start, "end": end} for start, end in pairs]


def _within_windows(value, pairs) -> bool:
    parsed = _aware_parse(value)
    if parsed is None:
        return False
    for start, end in pairs or ():
        parsed_start, parsed_end = _aware_parse(start), _aware_parse(end)
        if parsed_start is not None and parsed_end is not None \
                and parsed_start <= parsed <= parsed_end:
            return True
    return False


@dataclass(frozen=True)
class ShipmentLink:
    shipment: str
    dn: Optional[str]
    po_codes: tuple = ()
    signed_at: Optional[str] = None
    qty: object = None
    uom: Optional[str] = None
    sku: Optional[str] = None
    warehouse: Optional[str] = None
    identity_confidence: str = "unproven"
    status_semantics: str = "unproven"
    signed_status_proven: bool = False


@dataclass(frozen=True)
class ReceiptLine:
    receipt_id: Optional[str]
    line_id: Optional[str]
    po_code: Optional[str]
    sku: Optional[str]
    warehouse: Optional[str]
    uom: Optional[str]
    qty: object
    effective_at: Optional[str]
    quantity_semantics: str = "unknown"
    uom_proven: bool = False
    identity_proven: bool = False
    raw: dict = field(default_factory=dict)


def _decimal(value) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _aware_parse(value) -> Optional[datetime]:
    """Return an aware datetime; naive/invalid values are never localized."""
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _time_status(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return "missing"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "invalid"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "timezone_missing"
    return "verified"


def _out(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def _identity(line: ReceiptLine):
    return (line.receipt_id, line.line_id)


def _payload(line: ReceiptLine):
    return (line.po_code, line.sku, line.warehouse, line.uom,
            str(line.qty), line.effective_at, line.quantity_semantics,
            bool(line.uom_proven), bool(line.identity_proven))


def _dedupe(receipts: list[ReceiptLine]):
    """Exact replays count once; same identity with different payload conflicts."""
    by_identity = defaultdict(list)
    passthrough = []
    for line in receipts:
        if line.receipt_id and line.line_id:
            by_identity[_identity(line)].append(line)
        else:
            passthrough.append(line)
    unique, duplicates, conflicts = [], 0, set()
    for key in sorted(by_identity):
        rows = by_identity[key]
        payloads = {_payload(row) for row in rows}
        if len(payloads) > 1:
            conflicts.add(key)
            continue
        unique.append(rows[0])
        duplicates += len(rows) - 1
    return unique + passthrough, duplicates, conflicts


def _link_matches(line: ReceiptLine, link: ShipmentLink) -> bool:
    return (line.po_code in link.po_codes
            and line.sku == link.sku
            and line.warehouse == link.warehouse
            and line.uom == link.uom)


def reconcile_signed_receipts(
    links: Iterable[ShipmentLink],
    receipts: Iterable[ReceiptLine],
    coverage=None,
) -> list[dict]:
    all_links = list(links or [])
    all_receipts = list(receipts or [])
    envelope = ReceiptCoverage.from_mapping(coverage)
    coverage_out = envelope.as_dict() if envelope is not None else None
    unique, duplicates, conflict_keys = _dedupe(all_receipts)

    # A receipt key that could map to more than one link is allocation-unknown.
    link_count = defaultdict(int)
    receipt_keys = {(line.po_code, line.sku, line.warehouse, line.uom)
                    for line in unique}
    for link in all_links:
        for key in receipt_keys:
            if key[0] in link.po_codes and key[1] == link.sku \
                    and key[2] == link.warehouse and key[3] == link.uom:
                link_count[key] += 1
    conflict_pos = {line.po_code for line in all_receipts
                    if _identity(line) in conflict_keys}

    rows = []
    for link in all_links:
        if envelope is None:
            coverage_state = "missing"
        else:
            coverage_state = envelope.status_for(link.po_codes, link.signed_at)
        coverage_complete = coverage_state == "complete"
        common = {"coverage": coverage_out,
                  "coverage_status": coverage_state,
                  "signed_time_status": _time_status(link.signed_at),
                  "signed_status_proven": bool(
                      link.signed_status_proven or link.signed_at)}
        unmatched = sum(1 for line in unique if not _link_matches(line, link))
        if not link.po_codes:
            rows.append(_row(link, STAGE_UNKNOWN, exclusion="no_po_link",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue
        if link.identity_confidence != "proven":
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="identity_unproven",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue
        if not (link.signed_status_proven or link.signed_at):
            rows.append(_row(link, STAGE_IN_TRANSIT, duplicates=duplicates,
                             unmatched=unmatched, **common))
            continue
        if any(po in link.po_codes for po in conflict_pos):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_payload_conflict",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue

        same_po = [line for line in unique if line.po_code in link.po_codes]
        matching = [line for line in same_po if _link_matches(line, link)]
        if same_po and not matching:
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_identity_mismatch",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue
        in_window, outside, unplaceable = [], [], []
        for line in matching:
            if envelope is not None and envelope.coverage_mode == "time_range":
                if _aware_parse(line.effective_at) is None:
                    unplaceable.append(line)
                    continue
                target = (in_window if _within_windows(
                    line.effective_at, envelope.requested_windows) else outside)
            else:
                target = in_window
            target.append(line)
        outside_qty = Decimal(0)
        outside_unknown = False
        for line in outside:
            qty = _decimal(line.qty)
            if qty is None:
                outside_unknown = True
            else:
                outside_qty += qty
        outside_fields = {
            "receipts_outside_coverage": len(outside),
            "outside_coverage_qty": (None if outside_unknown
                                     else _out(outside_qty)),
            "outside_coverage_receipts": [
                {"receipt_id": line.receipt_id, "line_id": line.line_id,
                 "effective_at": line.effective_at, "qty": str(line.qty)}
                for line in outside],
            "receipts_time_unverified": len(unplaceable),
        }
        if unplaceable:
            # An observed receipt whose time cannot be located in the coverage
            # interval cannot contribute to (or be excluded from) closing.
            observed_statuses = {_time_status(line.effective_at)
                                 for line in unplaceable}
            unplaceable_status = ("timezone_missing"
                                  if "timezone_missing" in observed_statuses
                                  else ("missing" if "missing" in observed_statuses
                                        else "invalid"))
            rows.append(_row(
                link, STAGE_PENDING, exclusion="receipt_time_unverified",
                duplicates=duplicates, unmatched=unmatched,
                receipt_time_status=unplaceable_status,
                lag_status="receipt_time_unverified",
                **outside_fields, **common))
            continue
        matching = in_window
        if any(link_count[(line.po_code, line.sku, line.warehouse, line.uom)] > 1
               for line in matching):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_allocation_unknown",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue
        if any(line.quantity_semantics != "increment" for line in matching):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="quantity_semantics_unproven",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue
        if any(not line.uom_proven or not line.identity_proven for line in matching):
            rows.append(_row(link, STAGE_UNKNOWN,
                             exclusion="receipt_identity_unproven",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue

        link_qty = _decimal(link.qty)
        if link_qty is None:
            rows.append(_row(link, STAGE_UNKNOWN, exclusion="signed_qty_unknown",
                             duplicates=duplicates, unmatched=unmatched,
                             **common))
            continue

        signed_at = _aware_parse(link.signed_at)
        coverage_exclusion = ("coverage_scope_mismatch"
                              if coverage_state == "scope_mismatch"
                              else "coverage_incomplete")
        if not matching:
            if not coverage_complete:
                rows.append(_row(
                    link, STAGE_PENDING, exclusion=coverage_exclusion,
                    duplicates=duplicates, unmatched=unmatched,
                    lag_status="no_receipt", **outside_fields, **common))
            else:
                rows.append(_row(
                    link, STAGE_PENDING, received=Decimal(0), pending=link_qty,
                    completion="pending", duplicates=duplicates,
                    unmatched=unmatched,
                    lag_status="no_receipt", **outside_fields, **common))
            continue

        received = Decimal(0)
        time_statuses = set()
        times = []
        invalid_quantity = False
        for line in matching:
            qty = _decimal(line.qty)
            if qty is None:
                invalid_quantity = True
                break
            received += qty
            status = _time_status(line.effective_at)
            time_statuses.add(status)
            parsed = _aware_parse(line.effective_at)
            if parsed is not None:
                times.append((parsed, line.effective_at))
        if invalid_quantity:
            rows.append(_row(link, STAGE_UNKNOWN, exclusion="invalid_quantity",
                             duplicates=duplicates, unmatched=unmatched,
                             **outside_fields, **common))
            continue

        all_times_verified = time_statuses == {"verified"}
        receipt_time_status = ("verified" if all_times_verified else
                               ("missing" if "missing" in time_statuses else
                                "timezone_missing" if "timezone_missing" in time_statuses
                                else "invalid"))
        first_at = min(times)[1] if all_times_verified and times else None
        last_at = max(times)[1] if all_times_verified and times else None

        if received > link_qty:
            rows.append(_row(
                link, STAGE_PENDING, received=received,
                pending=Decimal(0) if coverage_complete else None,
                completion="over_receipt",
                over_receipt=received - link_qty, receipt_conflict=True,
                exclusion="over_receipt", first_at=first_at, last_at=last_at,
                receipt_time_status=receipt_time_status,
                lag_status="over_receipt",
                duplicates=duplicates, unmatched=unmatched,
                **outside_fields, **common))
            continue

        if first_at and signed_at and _aware_parse(first_at) < signed_at:
            rows.append(_row(
                link, STAGE_UNKNOWN, received=received, pending=None,
                completion="unknown", receipt_conflict=True,
                exclusion="receipt_before_signed", first_at=first_at,
                last_at=last_at,
                receipt_time_status=receipt_time_status,
                lag_status="receipt_before_signed",
                duplicates=duplicates, unmatched=unmatched,
                **outside_fields, **common))
            continue

        observed_complete = received >= link_qty
        if observed_complete and coverage_complete:
            completion, status = "complete", STAGE_RECEIVED
            exclusion = None
        elif observed_complete:
            # Observed quantity reaches the link quantity, but the collection
            # scope is not proven: never close or confirm pending.
            completion, status = "coverage_incomplete", STAGE_PENDING
            exclusion = coverage_exclusion
        else:
            completion = "partial" if received > 0 else "unknown"
            status, exclusion = STAGE_PENDING, None
        if coverage_complete and status == STAGE_RECEIVED:
            pending = Decimal(0)
        elif coverage_complete:
            pending = link_qty - received
        else:
            pending = None
        lag_seconds = lag_hours = lag_days = None
        lag_status = "unknown"
        if last_at and signed_at:
            delta = _aware_parse(last_at) - signed_at
            total = delta.total_seconds()
            lag_seconds = int(total)
            lag_hours = round(total / 3600.0, 3)
            lag_days = int(total // 86400)
            lag_status = "verified"
        elif last_at:
            lag_status = "signed_time_%s" % common["signed_time_status"]
        else:
            lag_status = "receipt_time_%s" % receipt_time_status
        rows.append(_row(
            link, status,
            received=received, pending=pending,
            completion=completion, first_at=first_at, last_at=last_at,
            receipt_at=last_at if status == STAGE_RECEIVED else None,
            lag_seconds=lag_seconds, lag_hours=lag_hours, lag_days=lag_days,
            lag_status=lag_status, exclusion=exclusion,
            receipt_time_status=receipt_time_status,
            duplicates=duplicates, unmatched=unmatched,
            **outside_fields, **common))
    return rows


def _row(link: ShipmentLink, status: str, *, exclusion=None, received=None,
         pending=None, completion="unknown", first_at=None, last_at=None,
         receipt_at=None, lag_seconds=None, lag_hours=None, lag_days=None,
         lag_status="unknown", signed_time_status="missing",
         receipt_time_status="missing", over_receipt=None,
         receipt_conflict=False, duplicates=0, unmatched=0,
         coverage=None, coverage_status="missing",
         signed_status_proven=False, receipts_outside_coverage=0,
         outside_coverage_qty=None, outside_coverage_receipts=None,
         receipts_time_unverified=0) -> dict:
    return {
        "shipment": link.shipment,
        "dn": link.dn,
        "po_codes": list(link.po_codes),
        "sku": link.sku,
        "warehouse": link.warehouse,
        "uom": link.uom,
        "status": status,
        "status_semantics": link.status_semantics,
        "shipment_signed_at": link.signed_at,
        "signed_status_proven": bool(signed_status_proven),
        "signed_time_status": signed_time_status,
        "tongtool_first_receipt_at": first_at,
        "tongtool_last_receipt_at": last_at,
        "tongtool_receipt_at": receipt_at,
        "receipt_time_status": receipt_time_status,
        "receipt_lag_seconds": lag_seconds,
        "receipt_lag_hours": lag_hours,
        "receipt_lag_days": lag_days,
        "receipt_lag_status": lag_status,
        "receipt_completion": completion if status != STAGE_UNKNOWN else "unknown",
        "received_qty": _out(received) if received is not None else None,
        "pending_qty": _out(pending) if pending is not None else None,
        "over_receipt_qty": _out(over_receipt) if over_receipt is not None else None,
        "received_evidence_status": "known" if received is not None else "unknown",
        "pending_evidence_status": "known" if pending is not None else "unknown",
        "receipt_conflict": bool(receipt_conflict),
        "receipt_basis": "signed_assumed",
        "identity_confidence": link.identity_confidence,
        "receipts_outside_coverage": receipts_outside_coverage,
        "outside_coverage_qty": outside_coverage_qty,
        "outside_coverage_receipts": list(outside_coverage_receipts or []),
        "receipts_time_unverified": receipts_time_unverified,
        "coverage": coverage,
        "coverage_status": coverage_status,
        "exclusion_reason": exclusion or "",
        "receipt_duplicates": duplicates,
        "unmatched_receipt_rows": unmatched,
    }
