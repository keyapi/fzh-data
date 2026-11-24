"""Read W1 SO supply facts into a read-only SKU×customer evidence layer.

SO is an upstream factory delivery pipeline, not overseas available stock. This
module only summarizes open SO lines for display; it never adds them to C/E or
to the recommendation quantity.

Lines are grouped by the SO creation date (``transaction_date``): the default
window is the six months ending at ``as_of``.  Older lines with a positive open
balance are kept as ``history`` instead of being dropped; lines without a
creation date are kept as ``unknown`` so no open quantity disappears.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from pathlib import Path

WINDOW_MONTHS = 6
TRANSACTION_FIELDS = ("transaction_date", "so_transaction_date", "order_date",
                      "so_date", "creation", "created_at", "posting_date")


def branch(customer):
    text = str(customer or "")
    if "美东" in text or "CENTRADE" in text.upper():
        return "USNJ"
    if "美中" in text or "DANEEY" in text.upper():
        return "USTX"
    if "波兰" in text:
        return "PL"
    return None


def sku_of(item_code):
    text = str(item_code or "").strip()
    for prefix in ("PK#", "ND#", "删除"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text or None


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for chunk in (text[:10], text[:19]):
        try:
            return date.fromisoformat(chunk)
        except ValueError:
            continue
    for pattern in ("%Y/%m/%d", "%d/%m/%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def months_before(value, months=WINDOW_MONTHS):
    """Calendar-month subtraction, clamped to the last valid day of month."""
    start = as_date(value)
    if start is None:
        raise ValueError("as_of must be an ISO date")
    year, month = start.year, start.month - months
    while month <= 0:
        month += 12
        year -= 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last))


def _pick(record, payload, row, fields=TRANSACTION_FIELDS):
    nested = [row, payload]
    for name in ("so", "so_detail", "order", "document"):
        value = payload.get(name) if isinstance(payload, dict) else None
        if isinstance(value, dict):
            nested.append(value)
        record_value = record.get(name) if isinstance(record, dict) else None
        if isinstance(record_value, dict):
            nested.append(record_value)
    nested.extend([record])
    for container in nested:
        if not isinstance(container, dict):
            continue
        # ``payload.creation``/``created_at`` describes the W1 run, not the SO;
        # only accept explicit transaction/order dates from the payload itself.
        current = (fields[:4] if fields is TRANSACTION_FIELDS and container is payload
                   else fields)
        for field in current:
            value = container.get(field)
            if value not in (None, ""):
                return value
    return None


def _bucket(created, window_start, as_of=None):
    if created is None:
        return "unknown"
    if as_of is not None and created > as_of:
        return "unknown"
    return "history" if created < window_start else "recent"


def load(path, as_of="2026-11-13", window_start=None):
    """Return {(sku, branch): summary} from W1 supply_facts_raw.jsonl.

    ``window_start`` defaults to six calendar months before ``as_of``; the
    caller may pass an explicit ISO date to freeze the reporting window.
    Kept for the recommendation page: no line deduplication (historic shape).
    """
    summary, _stats = load_deduped(path, as_of=as_of, window_start=window_start,
                                   dedupe=False)
    return summary


def load_deduped(path, as_of="2026-11-13", window_start=None, dedupe=True):
    """Return ``(summary, stats)``; ``dedupe`` collapses repeated SO lines.

    A repeated ``(so, so_line)`` can come from a re-run of the W1 snapshot
    appended to the same file.  With ``dedupe=True`` its open quantity is
    counted once (first occurrence wins) and the collapse is reported instead
    of silently changing the total.
    """
    p = Path(path)
    stats = {"lines_read": 0, "unique_lines": 0, "duplicate_lines": 0,
             "duplicate_open_qty": 0.0, "skipped_no_sku_or_branch": 0,
             "skipped_bad_qty": 0, "skipped_not_open": 0,
             "keys": 0, "dedupe": bool(dedupe)}
    if not p.exists():
        stats["error"] = f"SO 证据文件不存在：{p}"
        return {}, stats
    cutoff = as_date(as_of)
    if cutoff is None:
        raise ValueError("as_of must be an ISO date")
    start = as_date(window_start) if window_start is not None else months_before(cutoff)
    out = {}
    seen = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        payload = record.get("payload") or {}
        for row in payload.get("lines") or []:
            stats["lines_read"] += 1
            sku = sku_of(row.get("item_code"))
            br = branch(row.get("customer"))
            if not sku or not br:
                stats["skipped_no_sku_or_branch"] += 1
                continue
            try:
                qty = float(row.get("qty") or 0)
                delivered = float(row.get("delivered_qty") or 0)
            except (TypeError, ValueError):
                stats["skipped_bad_qty"] += 1
                continue
            open_qty = max(0.0, qty - delivered)
            status = str(row.get("so_status") or "")
            if open_qty <= 0 or status == "Closed" or \
                    str(row.get("so_docstatus")) not in {"1", "1.0"}:
                stats["skipped_not_open"] += 1
                continue
            so_name = record.get("so") or row.get("so")
            if dedupe:
                line_key = (str(so_name), str(row.get("so_line")))
                if line_key in seen:
                    stats["duplicate_lines"] += 1
                    stats["duplicate_open_qty"] += open_qty
                    previous = out.get((sku, br))
                    if previous is not None:
                        previous["so_duplicate_lines"] += 1
                    continue
                seen.add(line_key)
            stats["unique_lines"] += 1
            created = as_date(_pick(record, payload, row))
            delivery = as_date(_pick(record, payload, row,
                                     ("delivery_date", "scheduled_delivery")))
            bucket = _bucket(created, start, cutoff)
            overdue = max(0, (cutoff - delivery).days) if delivery else 0
            key = (sku, br)
            summary = out.setdefault(key, {
                "so_open_qty": 0.0, "so_open_orders": 0,
                "so_recent_open_qty": 0.0, "so_recent_open_orders": 0,
                "so_history_open_qty": 0.0, "so_history_open_orders": 0,
                "so_unknown_date_open_qty": 0.0, "so_unknown_date_open_orders": 0,
                "so_overdue_days_max": 0,
                "so_recent_overdue_days_max": 0,
                "so_history_overdue_days_max": 0,
                "so_window_start": start.isoformat(),
                "so_as_of": cutoff.isoformat(),
                "so_lines": [],
                "so_source_as_of": payload.get("as_of") or "",
                "so_duplicate_lines": 0,
                "_orders": set(), "_recent_orders": set(),
                "_history_orders": set(), "_unknown_orders": set(),
            })
            summary["so_open_qty"] += open_qty
            summary["_orders"].add(so_name)
            summary["so_overdue_days_max"] = max(summary["so_overdue_days_max"], overdue)
            if bucket == "recent":
                summary["so_recent_open_qty"] += open_qty
                summary["_recent_orders"].add(so_name)
                summary["so_recent_overdue_days_max"] = max(
                    summary["so_recent_overdue_days_max"], overdue)
            elif bucket == "history":
                summary["so_history_open_qty"] += open_qty
                summary["_history_orders"].add(so_name)
                summary["so_history_overdue_days_max"] = max(
                    summary["so_history_overdue_days_max"], overdue)
            else:
                summary["so_unknown_date_open_qty"] += open_qty
                summary["_unknown_orders"].add(so_name)
            summary["so_lines"].append({
                "so": so_name,
                "so_line": row.get("so_line"),
                "item_code": row.get("item_code"),
                "status": status,
                "qty": qty,
                "delivered": delivered,
                "open_qty": open_qty,
                "transaction_date": created.isoformat() if created else None,
                "delivery_date": delivery.isoformat() if delivery else None,
                "overdue_days": overdue,
                "date_bucket": bucket,
                "warehouse": row.get("warehouse"),
                "stage": row.get("stage"),
            })
    for summary in out.values():
        summary["so_open_orders"] = len(summary.pop("_orders"))
        summary["so_recent_open_orders"] = len(summary.pop("_recent_orders"))
        summary["so_history_open_orders"] = len(summary.pop("_history_orders"))
        summary["so_unknown_date_open_orders"] = len(summary.pop("_unknown_orders"))
        order = {"recent": 0, "history": 1, "unknown": 2}
        # Stable two-pass sort: newest first inside each bucket, recent bucket first.
        summary["so_lines"].sort(key=lambda line: line.get("transaction_date") or "",
                                 reverse=True)
        summary["so_lines"].sort(key=lambda line: order[line["date_bucket"]])
    stats["keys"] = len(out)
    return out, stats
