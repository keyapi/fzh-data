# -*- coding: utf-8 -*-
"""Final logistics progress adjudication (pure, read-only).

Evidence level, not update time, decides the final progress:

* a valid actual terminal event (signed / POD / completed) is sticky;
* actual events outrank estimated events;
* non-terminal events are compared by the defined logistics stage order;
* ``event_at`` only breaks ties inside the same stage;
* ``source_updated_at`` can revise the same source+event but never promotes a
  stage.

Two live status lines plus the Shipment Logistics Event log feed the
adjudication:

* ``status11`` is the crawler's fine-grained actual line;
* ``status4`` is the coarse manual line. Only values in
  ``MANUAL_STATUS_NORMALIZATION`` are understood; anything else keeps its raw
  value, cannot vote, and raises ``manual_status_unmapped``.
* a non-terminal manual value only votes when no fine actual evidence exists,
  so a coarse ``在途`` can never outrank a fine ``已离港``.

Ambiguous input (exceptions, same-time conflicts, missing times, stage
regressions, same-stage payload conflicts, unmapped manual values) returns
``unknown`` or a conflict-flagged result and keeps every raw candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable, Optional

SIGNED_PENDING_STAGE = "signed_pending_tongtool_receipt"
TONGTOOL_RECEIVED_STAGE = "tongtool_received"
TRANSPORT_STAGE = "shipped_in_transit"
UNKNOWN_STAGE = "unknown"

STATUS_ORDER = (
    "已订舱", "已入仓", "已装柜", "报关中", "已报关", "已离港",
    "运输中", "已到港", "清关中", "已清关", "已转运", "派送中",
    "已签收", "已上传POD",
)
FINAL_STATUSES = {"已签收", "已上传POD", "已完结"}
TRANSPORT_STATUSES = set(STATUS_ORDER[:12])
EXCEPTION_TOKENS = ("异常", "撤销", "退回", "修正", "取消", "失败", "错误")
ESTIMATED_STATUS = "ETA"

MANUAL_STATUS_NORMALIZATION_VERSION = "status4-manual/v1"
# Only values whose meaning is proven against the canonical vocabulary are
# mapped. Coarse values collapse into the nearest canonical stage; ``待发`` and
# any other unproven value stays raw (see module docstring).
MANUAL_STATUS_NORMALIZATION = {
    **{status: status for status in STATUS_ORDER},
    "在途": "运输中",
    "到港": "已到港",
    "离港": "已离港",
    "签收": "已签收",
}

EVENT_STATUS_NORMALIZATION_VERSION = "event-logistics/v1"
# Exact descriptions win; otherwise a single unambiguous token may classify a
# free-text description. Multiple token hits stay raw and cannot vote.
EVENT_STATUS_NORMALIZATION = {
    **{status: status for status in STATUS_ORDER},
    "开船": "已离港",
    "抵港": "已到港",
    "签收成功": "已签收",
    "POD": "已上传POD",
    "上传POD": "已上传POD",
    "清关": "清关中",
    "报关": "报关中",
    "转运": "已转运",
    "派送": "派送中",
    "装柜": "已装柜",
    "入仓": "已入仓",
    "订舱": "已订舱",
    "运输": "运输中",
}
_EVENT_TOKEN_ORDER = tuple(
    sorted((key for key in EVENT_STATUS_NORMALIZATION if len(key) > 2),
           key=lambda value: (-len(value), value)))

_STAGE_RANK = {status: index for index, status in enumerate(STATUS_ORDER)}


@dataclass(frozen=True)
class ProgressEvidence:
    raw_status: Optional[str]
    normalized_status: Optional[str]
    event_kind: str = "actual"          # actual / estimated / raw_event
    event_at: Optional[str] = None
    source_updated_at: Optional[str] = None
    source: Optional[str] = None
    source_record: Optional[str] = None
    line: str = "status"               # status11 / status4 / event / field
    granularity: str = "fine"          # fine / coarse
    vote: bool = True
    normalization: Optional[str] = None
    unmapped_manual: bool = False


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _parse(value) -> Optional[datetime]:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Shipment date fields are often date-only. Timezone is reported as
    # unverified in candidates, but the date is still usable for ordering.
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized(evidence: ProgressEvidence) -> str:
    return _text(evidence.normalized_status) or _text(evidence.raw_status)


def _is_final(status: str) -> bool:
    return status in FINAL_STATUSES


def _is_exception(status: str) -> bool:
    return any(token in status for token in EXCEPTION_TOKENS)


def _rank(status: str) -> Optional[int]:
    return _STAGE_RANK.get(status)


def _tz_status(value) -> str:
    text = _text(value)
    if not text:
        return "missing"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "invalid"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "unverified"
    return "verified"


def _candidate(evidence: ProgressEvidence) -> dict:
    status = _normalized(evidence)
    return {
        "raw_status": evidence.raw_status,
        "normalized_status": evidence.normalized_status,
        "effective_status": status,
        "event_kind": evidence.event_kind or "actual",
        "event_at": evidence.event_at,
        "timezone_status": _tz_status(evidence.event_at),
        "source_updated_at": evidence.source_updated_at,
        "source": evidence.source,
        "source_record": evidence.source_record,
        "line": evidence.line,
        "granularity": evidence.granularity,
        "vote": bool(evidence.vote),
        "normalization": evidence.normalization,
        "unmapped_manual": bool(evidence.unmapped_manual),
        "is_final": _is_final(status),
        "stage_rank": _rank(status),
    }


def _canonical(evidence: ProgressEvidence):
    return (
        _normalized(evidence), evidence.event_kind or "actual",
        _text(evidence.event_at), _text(evidence.source_updated_at),
        _text(evidence.source), _text(evidence.source_record),
        evidence.line, evidence.granularity, bool(evidence.vote),
    )


def _revision_key(evidence: ProgressEvidence):
    return (
        _text(evidence.source), _normalized(evidence),
        evidence.event_kind or "actual", _text(evidence.event_at),
        _text(evidence.source_record),
    )


def _dedupe(rows: list[ProgressEvidence]) -> list[ProgressEvidence]:
    """Exact replays collapse; same source/event revisions keep the latest update."""
    by_revision = {}
    passthrough = []
    for row in rows:
        if not _text(row.source):
            passthrough.append(row)
            continue
        key = _revision_key(row)
        current = by_revision.get(key)
        if current is None:
            by_revision[key] = row
            continue
        current_updated = _parse(current.source_updated_at)
        candidate_updated = _parse(row.source_updated_at)
        if candidate_updated is not None and (
                current_updated is None or candidate_updated > current_updated):
            by_revision[key] = row
    return passthrough + list(by_revision.values())


def _result(status, at, source, is_final, reasons, rows, kind=None):
    return {
        "latest_progress_status": status,
        "latest_progress_at": at,
        "latest_progress_kind": None if status is None else (kind or "actual"),
        "progress_source": source,
        "is_final": bool(is_final),
        "conflict_flag": bool(reasons),
        "conflict_reasons": sorted(set(reasons)),
        "progress_candidates": [_candidate(row) for row in sorted(rows, key=_canonical)],
    }


def adjudicate_progress(evidences: Iterable[ProgressEvidence]) -> dict:
    raw_rows = [row for row in (evidences or []) if row is not None]
    if not raw_rows:
        return _result(None, None, None, False, ["no_evidence"], [])
    rows = _dedupe(raw_rows)
    reasons = set()
    if any(row.unmapped_manual for row in rows):
        reasons.add("manual_status_unmapped")
    vote_rows = [row for row in rows if row.vote]
    if not vote_rows:
        reasons.add("unknown_status")
        return _result(None, None, None, False, reasons, rows)

    finals = [row for row in vote_rows if _is_final(_normalized(row))]
    actuals = [row for row in vote_rows
               if not _is_final(_normalized(row))
               and (row.event_kind or "actual") == "actual"]
    estimates = [row for row in vote_rows
                 if (row.event_kind or "actual") == "estimated"]
    exceptions = [row for row in rows if _is_exception(_normalized(row))]

    if finals:
        statuses = {_normalized(row) for row in finals}
        timed = [row for row in finals if _parse(row.event_at) is not None]
        if len(statuses) > 1:
            reasons.add("terminal_status_conflict")
            if timed and len({_text(row.event_at) for row in timed}) == 1:
                reasons.add("same_time_conflict")
                return _result(None, None, None, False, reasons, rows)
            if timed:
                chosen = max(timed, key=lambda row: _parse(row.event_at))
            elif len({_normalized(row) for row in finals}) > 1:
                reasons.add("missing_time")
                return _result(None, None, None, False, reasons, rows)
            else:
                chosen = finals[0]
        else:
            chosen = max(timed, key=lambda row: _parse(row.event_at)) if timed else finals[0]
            if timed and any(_parse(row.event_at) is None for row in finals):
                reasons.add("missing_time")
        if exceptions:
            reasons.add("exception_present")
        chosen_at = _parse(chosen.event_at)
        others = [row for row in rows
                  if not _is_final(_normalized(row))
                  and _normalized(row) != _normalized(chosen)]
        for row in others:
            other_at = _parse(row.event_at)
            if (other_at is None or chosen_at is None
                    or other_at > chosen_at):
                reasons.add("terminal_over_nonterminal")
                break
        return _result(_normalized(chosen), chosen.event_at, chosen.source,
                       True, reasons, rows, kind="actual")

    if exceptions:
        reasons.add("exception_present")
        return _result(None, None, None, False, reasons, rows)

    if actuals:
        timed = [row for row in actuals if _parse(row.event_at) is not None]
        untimed = [row for row in actuals if _parse(row.event_at) is None]
        ranked = [( _rank(_normalized(row)), row) for row in actuals
                  if _rank(_normalized(row)) is not None]
        if not ranked:
            reasons.add("unknown_status")
            return _result(None, None, None, False, reasons, rows)
        if untimed and len({_normalized(row) for row in actuals}) > 1:
            reasons.add("missing_time")
        max_rank = max(rank for rank, _ in ranked)
        top = [row for rank, row in ranked if rank == max_rank]
        timed_top = [row for row in top if _parse(row.event_at) is not None]
        chosen = (max(timed_top, key=lambda row: _parse(row.event_at))
                  if timed_top else top[0])
        chosen_at = _parse(chosen.event_at)
        # A later event that regresses to an earlier stage is contradictory:
        # it makes the whole line unknown instead of confirming either side.
        if chosen_at is not None:
            for row in timed:
                rank = _rank(_normalized(row))
                if rank is not None and rank < max_rank and _parse(row.event_at) > chosen_at:
                    reasons.add("stage_regression")
                    return _result(None, None, None, False, reasons, rows)
        # Same instant, different payload is never force-ordered.
        same_instant = [row for row in timed
                        if _text(row.event_at) == _text(chosen.event_at)]
        if len({_normalized(row) for row in same_instant}) > 1:
            reasons.add("same_time_conflict")
            return _result(None, None, None, False, reasons, rows)
        return _result(_normalized(chosen), chosen.event_at, chosen.source,
                       False, reasons, rows, kind="actual")

    if estimates:
        timed = [row for row in estimates if _parse(row.event_at) is not None]
        if timed:
            chosen = max(timed, key=lambda row: _parse(row.event_at))
        else:
            chosen = estimates[0]
        variants = {(_normalized(row), _text(row.event_at)) for row in estimates}
        if len(variants) > 1:
            reasons.add("eta_conflict")
        if len({_normalized(row) for row in estimates}) > 1 and not timed:
            reasons.add("missing_time")
        return _result(_normalized(chosen), chosen.event_at, chosen.source,
                       False, reasons, rows, kind="estimated")

    reasons.add("unknown_status")
    return _result(None, None, None, False, reasons, rows)


def classify_stage(progress: dict) -> str:
    status = _text((progress or {}).get("latest_progress_status"))
    if not status:
        return UNKNOWN_STAGE
    kind = progress.get("latest_progress_kind")
    if kind is None:
        kind = "estimated" if status == ESTIMATED_STATUS else "actual"
    if _is_final(status):
        return SIGNED_PENDING_STAGE if kind == "actual" else UNKNOWN_STAGE
    if _is_exception(status):
        return UNKNOWN_STAGE
    if kind != "actual":
        # ETA-only evidence is an expectation, never proof of actual movement.
        return UNKNOWN_STAGE
    if status in TRANSPORT_STATUSES or status == ESTIMATED_STATUS:
        return TRANSPORT_STAGE
    return UNKNOWN_STAGE


def _manual_evidence(status4: str, record: str, updated, dlvr, eta):
    mapped = MANUAL_STATUS_NORMALIZATION.get(status4)
    unmapped = mapped is None
    event_at = None
    if mapped is not None and _is_final(mapped):
        event_at = dlvr
    elif mapped == "已离港":
        event_at = None
    return ProgressEvidence(
        raw_status=status4, normalized_status=mapped, event_kind="actual",
        event_at=event_at, source_updated_at=updated,
        source="manual_status", source_record=record + ".status4",
        line="status4", granularity="coarse", vote=not unmapped,
        normalization=MANUAL_STATUS_NORMALIZATION_VERSION,
        unmapped_manual=unmapped)


def _event_is_eta(text: str) -> bool:
    lowered = text.lower()
    return "eta" in lowered or "预计" in text


def _normalize_event(text: str) -> Optional[str]:
    text = _text(text)
    if not text:
        return None
    if text in EVENT_STATUS_NORMALIZATION:
        return EVENT_STATUS_NORMALIZATION[text]
    hits = {EVENT_STATUS_NORMALIZATION[token] for token in _EVENT_TOKEN_ORDER
            if token in text}
    if len(hits) == 1:
        return hits.pop()
    return None


def _event_evidence(event: dict, record: str, updated):
    event = event or {}
    raw = _text(event.get("description")) or _text(event.get("name"))
    if not raw:
        return None
    seq = event.get("seq")
    source_record = "%s.event:%s" % (record, seq if seq not in (None, "") else "?")
    event_at = event.get("time") or event.get("date")
    if _event_is_eta(raw):
        return ProgressEvidence(
            raw_status=raw, normalized_status=ESTIMATED_STATUS,
            event_kind="estimated", event_at=None, source_updated_at=updated,
            source="carrier_event", source_record=source_record, line="event",
            granularity="fine", vote=True,
            normalization=EVENT_STATUS_NORMALIZATION_VERSION)
    mapped = _normalize_event(raw)
    if mapped is None:
        return ProgressEvidence(
            raw_status=raw, normalized_status=None, event_kind="raw_event",
            event_at=event_at, source_updated_at=updated,
            source="carrier_event", source_record=source_record, line="event",
            granularity="fine", vote=False,
            normalization=EVENT_STATUS_NORMALIZATION_VERSION)
    return ProgressEvidence(
        raw_status=raw, normalized_status=mapped, event_kind="actual",
        event_at=event_at, source_updated_at=updated, source="carrier_event",
        source_record=source_record, line="event", granularity="fine",
        vote=True, normalization=EVENT_STATUS_NORMALIZATION_VERSION)


def progress_from_shipment(row, events=None) -> dict:
    """Build evidence from one Shipment row + its Logistics Event rows."""
    row = row or {}
    status11 = _text(row.get("status11"))
    status4 = _text(row.get("status4"))
    atd = row.get("atd")
    ata = row.get("ata")
    dlvr = row.get("dlvr")
    eta = row.get("eta")
    updated = row.get("modified") or row.get("source_updated_at")
    record = _text(row.get("shipment") or row.get("name")) or "Shipment"

    def status_time(current: str):
        if current == "已离港":
            return atd
        if current == "已到港":
            return ata
        if _is_final(current):
            # Never borrow ata: only the delivery timestamp proves signing.
            return dlvr
        # Clearance/transfer/dispatch have no dedicated timestamp on Shipment;
        # reusing ata would fabricate a same-instant conflict with 已到港.
        return None

    evidence = []
    if status11:
        evidence.append(ProgressEvidence(
            raw_status=status11, normalized_status=status11, event_kind="actual",
            event_at=status_time(status11), source_updated_at=updated,
            source="carrier_status", source_record=record + ".status11",
            line="status11", granularity="fine", vote=True))
    if status4:
        evidence.append(_manual_evidence(status4, record, updated, dlvr, eta))
    if atd:
        evidence.append(ProgressEvidence(
            raw_status="已离港", normalized_status="已离港", event_kind="actual",
            event_at=atd, source_updated_at=updated, source="carrier_field",
            source_record=record + ".atd", line="field", granularity="fine",
            vote=True))
    if ata:
        evidence.append(ProgressEvidence(
            raw_status="已到港", normalized_status="已到港", event_kind="actual",
            event_at=ata, source_updated_at=updated, source="carrier_field",
            source_record=record + ".ata", line="field", granularity="fine",
            vote=True))
    if dlvr and not _is_final(status11):
        evidence.append(ProgressEvidence(
            raw_status="已签收", normalized_status="已签收", event_kind="actual",
            event_at=dlvr, source_updated_at=updated, source="carrier_field",
            source_record=record + ".dlvr", line="field", granularity="fine",
            vote=True))
    if eta:
        evidence.append(ProgressEvidence(
            raw_status="ETA", normalized_status=ESTIMATED_STATUS,
            event_kind="estimated", event_at=eta, source_updated_at=updated,
            source="carrier_eta", source_record=record + ".eta", line="field",
            granularity="fine", vote=True))
    for event in events or ():
        item = _event_evidence(event, record, updated)
        if item is not None:
            evidence.append(item)

    # A coarse manual value is corroboration once fine actual evidence exists;
    # otherwise it is the only line we have and may vote.
    fine_actual = any(
        row.granularity == "fine" and row.vote and row.event_kind == "actual"
        and row.line in ("status11", "event", "field")
        for row in evidence)
    if fine_actual:
        evidence = [
            replace(row, vote=False)
            if row.granularity == "coarse" and not _is_final(_normalized(row))
            else row
            for row in evidence]
    return adjudicate_progress(evidence)
