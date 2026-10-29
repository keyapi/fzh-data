# -*- coding: utf-8 -*-
"""Final logistics progress adjudication (pure, read-only).

Evidence level, not update time, decides the final progress:

* a valid actual terminal event (signed / POD / completed) is sticky;
* actual events outrank estimated events;
* non-terminal events are compared by the defined logistics stage order;
* ``event_at`` only breaks ties inside the same stage;
* ``source_updated_at`` can revise the same source+event but never promotes a
  stage.

Ambiguous input (exceptions, same-time conflicts, missing times, stage
regressions, same-stage payload conflicts) returns ``unknown`` plus
``conflict_flag`` and keeps every raw candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
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

_STAGE_RANK = {status: index for index, status in enumerate(STATUS_ORDER)}


@dataclass(frozen=True)
class ProgressEvidence:
    raw_status: Optional[str]
    normalized_status: Optional[str]
    event_kind: str = "actual"          # actual / estimated
    event_at: Optional[str] = None
    source_updated_at: Optional[str] = None
    source: Optional[str] = None
    source_record: Optional[str] = None


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
        "normalized_status": status,
        "event_kind": evidence.event_kind or "actual",
        "event_at": evidence.event_at,
        "timezone_status": _tz_status(evidence.event_at),
        "source_updated_at": evidence.source_updated_at,
        "source": evidence.source,
        "source_record": evidence.source_record,
        "is_final": _is_final(status),
        "stage_rank": _rank(status),
    }


def _canonical(evidence: ProgressEvidence):
    return (
        _normalized(evidence), evidence.event_kind or "actual",
        _text(evidence.event_at), _text(evidence.source_updated_at),
        _text(evidence.source), _text(evidence.source_record),
    )


def _revision_key(evidence: ProgressEvidence):
    return (
        _text(evidence.source), _normalized(evidence),
        evidence.event_kind or "actual", _text(evidence.event_at),
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


def _result(status, at, source, is_final, reasons, rows):
    return {
        "latest_progress_status": status,
        "latest_progress_at": at,
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
    finals = [row for row in rows if _is_final(_normalized(row))]
    actuals = [row for row in rows
               if not _is_final(_normalized(row))
               and (row.event_kind or "actual") == "actual"]
    estimates = [row for row in rows
                 if (row.event_kind or "actual") == "estimated"]
    exceptions = [row for row in rows if _is_exception(_normalized(row))]
    reasons = set()

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
                       True, reasons, rows)

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
        # A later event that regresses to an earlier stage is contradictory.
        if chosen_at is not None:
            for row in timed:
                rank = _rank(_normalized(row))
                if rank is not None and rank < max_rank and _parse(row.event_at) > chosen_at:
                    reasons.add("stage_regression")
                    break
        # Same instant, different payload is never force-ordered.
        same_instant = [row for row in timed
                        if _text(row.event_at) == _text(chosen.event_at)]
        if len({_normalized(row) for row in same_instant}) > 1:
            reasons.add("same_time_conflict")
            return _result(None, None, None, False, reasons, rows)
        return _result(_normalized(chosen), chosen.event_at, chosen.source,
                       False, reasons, rows)

    if estimates:
        timed = [row for row in estimates if _parse(row.event_at) is not None]
        if timed:
            chosen = max(timed, key=lambda row: _parse(row.event_at))
        else:
            chosen = estimates[0]
        if len({_normalized(row) for row in estimates}) > 1 and not timed:
            reasons.add("missing_time")
        return _result(_normalized(chosen), chosen.event_at, chosen.source,
                       False, reasons, rows)

    reasons.add("unknown_status")
    return _result(None, None, None, False, reasons, rows)


def classify_stage(progress: dict) -> str:
    status = _text((progress or {}).get("latest_progress_status"))
    if not status:
        return UNKNOWN_STAGE
    if _is_final(status):
        return SIGNED_PENDING_STAGE
    if _is_exception(status):
        return UNKNOWN_STAGE
    if status in TRANSPORT_STATUSES or status == ESTIMATED_STATUS:
        return TRANSPORT_STAGE
    return UNKNOWN_STAGE


def progress_from_shipment(row) -> dict:
    """Build evidence from one Shipment row without inventing missing values."""
    row = row or {}
    status = _text(row.get("status11"))
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
            return dlvr or ata
        # Clearance/transfer/dispatch have no dedicated timestamp on Shipment;
        # reusing ata would fabricate a same-instant conflict with 已到港.
        return None

    evidence = []
    if status:
        evidence.append(ProgressEvidence(
            raw_status=status, normalized_status=status, event_kind="actual",
            event_at=status_time(status), source_updated_at=updated,
            source="carrier_status", source_record=record + ".status11"))
    if atd:
        evidence.append(ProgressEvidence(
            raw_status="已离港", normalized_status="已离港", event_kind="actual",
            event_at=atd, source_updated_at=updated, source="carrier_field",
            source_record=record + ".atd"))
    if ata:
        evidence.append(ProgressEvidence(
            raw_status="已到港", normalized_status="已到港", event_kind="actual",
            event_at=ata, source_updated_at=updated, source="carrier_field",
            source_record=record + ".ata"))
    if dlvr and not _is_final(status):
        evidence.append(ProgressEvidence(
            raw_status="已签收", normalized_status="已签收", event_kind="actual",
            event_at=dlvr, source_updated_at=updated, source="carrier_field",
            source_record=record + ".dlvr"))
    if eta:
        evidence.append(ProgressEvidence(
            raw_status="ETA", normalized_status=ESTIMATED_STATUS,
            event_kind="estimated", event_at=eta, source_updated_at=updated,
            source="carrier_eta", source_record=record + ".eta"))
    return adjudicate_progress(evidence)
