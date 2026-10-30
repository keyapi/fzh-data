"""Bounded, overlapping-window collection for Tongtool receipt rows.

Tongtool exposes no stable receipt or line ID. This collector therefore keeps
raw rows and flags overlap duplicates explicitly; it never invents a business
identity, UOM, or timezone.
"""
from __future__ import annotations

import hashlib
import json
import time
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from tongtool_api.purchase_receipts import CALL_INTERVAL_SECONDS, fetch_receipts, _parse_bound
from tongtool_api.purchase_receipts import BUSINESS_TIMEZONE


@dataclass(frozen=True)
class CollectionWindow:
    start: date
    end: date


@dataclass(frozen=True)
class CollectedRow:
    source_index: int
    collected_window: CollectionWindow
    row: dict
    weak_event_key: tuple
    overlap_duplicate: bool
    possible_duplicate: bool
    dedup_assumed: bool = False


@dataclass(frozen=True)
class CollectionResult:
    rows: tuple[CollectedRow, ...]
    windows: tuple[CollectionWindow, ...]
    input_count: int
    unique_count: int
    overlap_duplicate_count: int
    possible_duplicate_count: int
    truncated_windows: tuple[CollectionWindow, ...]
    cache_hits: int


def _as_date(value: str | date | datetime) -> date:
    return _parse_bound(value, "date bound", end_of_day=False).date()


def split_windows(
    start: str | date | datetime,
    end: str | date | datetime,
    *,
    window_days: int = 7,
    overlap_days: int = 1,
) -> tuple[CollectionWindow, ...]:
    """Split [start, end] into overlapping inclusive date windows."""
    first, last = _as_date(start), _as_date(end)
    if first > last:
        raise ValueError("start must not be after end")
    if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days < 1:
        raise ValueError("window_days must be >= 1")
    if isinstance(overlap_days, bool) or not isinstance(overlap_days, int) or not 0 <= overlap_days < window_days:
        raise ValueError("overlap_days must be >= 0 and < window_days")
    step = window_days - overlap_days
    windows = []
    cursor = first
    while cursor <= last:
        window_end = min(cursor + timedelta(days=window_days - 1), last)
        windows.append(CollectionWindow(cursor, window_end))
        if window_end >= last:
            break
        cursor += timedelta(days=step)
    return tuple(windows)


def weak_event_key(row: dict) -> tuple:
    """Stable-ish key for audit only; the source provides no stable ID."""
    fields = ("purchaseOrderCode", "purchaseOrderId", "goodsDetailId", "sku",
              "warehouseId", "warehousingDate", "warehousingNum")
    return tuple("" if row.get(field) is None else str(row.get(field)) for field in fields)


def _check_cache_dir(cache_dir: Path) -> None:
    assert_outside_repo(cache_dir, "cache_dir")


def assert_outside_repo(path: Path, label: str = "path") -> None:
    resolved = Path(path).resolve()
    if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise ValueError(f"{label} must be outside any git repository")


def _cache_key(window: CollectionWindow, po_code: Optional[str], page_size: int, max_pages: int) -> str:
    raw = json.dumps({
        "start": window.start.isoformat(), "end": window.end.isoformat(),
        "po_code": po_code, "page_size": page_size, "max_pages": max_pages,
    }, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def collect_receipts(
    caller: Callable[[str, dict], dict],
    start: str | date | datetime,
    end: str | date | datetime,
    *,
    window_days: int = 7,
    overlap_days: int = 1,
    po_code: Optional[str] = None,
    page_size: int = 100,
    max_pages: int = 1,
    cache_dir: Optional[Path] = None,
    sleep: Callable[[float], object] = time.sleep,
    interval: float = CALL_INTERVAL_SECONDS,
    cache_mode: str = "live",
    cache_ttl_seconds: float = 3600,
    cache_namespace: Optional[str] = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> CollectionResult:
    """Fetch overlapping windows and flag, not hide, ambiguous duplicates.

    Rows with the same weak key are deduplicated only when they come from
    different collection windows (the likely overlap replay). Duplicates inside
    one window are kept and marked ``possible_duplicate`` because they could be
    two real receipts at the same second. Raw rows stay in the caller's cache
    directory; pass a path outside the git repository.
    """
    windows = split_windows(start, end, window_days=window_days, overlap_days=overlap_days)
    if cache_mode not in ("live", "frozen"):
        raise ValueError("cache_mode must be live or frozen")
    if not CALL_INTERVAL_SECONDS <= interval < float("inf") or not 0 < cache_ttl_seconds < float("inf"):
        raise ValueError("interval must be >=13 seconds and cache TTL must be positive and finite")
    current = now()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("cache clock must have an explicit timezone")
    cache_path = Path(cache_dir) if cache_dir is not None else None
    if cache_path is not None:
        _check_cache_dir(cache_path)
        if not isinstance(cache_namespace, str) or not cache_namespace.strip():
            raise ValueError("cached collection requires an explicit account namespace")
        cache_path.mkdir(parents=True, exist_ok=True)

    collected: list[tuple[CollectionWindow, dict]] = []
    truncated = []
    cache_hits = 0
    for index, window in enumerate(windows):
        current = now()
        payload = None
        if cache_path is not None:
            namespace = hashlib.sha256(cache_namespace.encode()).hexdigest()[:16]
            file_path = cache_path / (namespace + "_" + _cache_key(window, po_code, page_size, max_pages) + ".json")
            if file_path.is_file():
                try:
                    cached = json.loads(file_path.read_text(encoding="utf-8"))
                    if not isinstance(cached, dict):
                        raise ValueError("invalid cache envelope")
                    fetched = datetime.fromisoformat(cached["fetched_at"])
                    age = (current - fetched).total_seconds()
                    valid = (cached.get("cache_namespace") == cache_namespace
                             and cached.get("window") == {"start": window.start.isoformat(), "end": window.end.isoformat()}
                             and cached.get("po_code") == po_code
                             and isinstance(cached.get("rows"), list)
                             and all(isinstance(row, dict) for row in cached["rows"])
                             and isinstance(cached.get("complete"), bool)
                             and isinstance(cached.get("truncated"), bool))
                    fresh = (0 <= age < cache_ttl_seconds and window.end < current.astimezone(BUSINESS_TIMEZONE).date()
                             and cached.get("complete") is True and not cached.get("truncated"))
                    if valid and (cache_mode == "frozen" or fresh):
                        payload = cached
                        cache_hits += 1
                except (ValueError, KeyError, TypeError):
                    pass  # Corrupt or legacy cache is never treated as a complete source.
        if payload is None:
            result = fetch_receipts(
                caller, window.start, window.end, po_code=po_code,
                page_size=page_size, max_pages=max_pages, sleep=sleep,
            )
            payload = {
                "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
                "po_code": po_code,
                "rows": result.rows,
                "complete": result.complete,
                "truncated": result.truncated,
                "fetched_at": now().isoformat(),
                "cache_namespace": cache_namespace,
            }
            if cache_path is not None:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_path,
                                                 suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(json.dumps(payload, ensure_ascii=False))
                try:
                    temporary.replace(file_path)
                finally:
                    temporary.unlink(missing_ok=True)
            if index < len(windows) - 1:
                sleep(interval)
        if payload.get("truncated") or not payload.get("complete"):
            truncated.append(window)
        collected.extend((window, row) for row in payload["rows"])

    groups: dict[tuple, list[int]] = {}
    for index, (_, row) in enumerate(collected):
        groups.setdefault(weak_event_key(row), []).append(index)

    dropped: set[int] = set()
    possible: set[int] = set()
    assumed: set[int] = set()
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        per_window = defaultdict(list)
        for index in indexes:
            per_window[collected[index][0]].append(index)
        if len(per_window) == 1:
            possible.update(indexes)
            continue
        source_row = collected[indexes[0]][1]
        required = ("purchaseOrderCode", "goodsDetailId", "sku", "warehouseId", "warehousingDate", "warehousingNum")
        try:
            event_date = _as_date(source_row.get("warehousingDate"))
            intersects = max(window.start for window in per_window) <= event_date <= min(window.end for window in per_window)
        except (TypeError, ValueError):
            intersects = False
        versions = {json.dumps(collected[index][1], sort_keys=True, ensure_ascii=False) for index in indexes}
        if not intersects or any(source_row.get(name) in (None, "") for name in required) or len(versions) > 1:
            possible.update(indexes)
            continue
        # A weak key cannot prove identity. Preserve the largest observed
        # multiplicity; a later 2-row window must not be reduced to an earlier 1.
        keep = max(per_window.values(), key=len)
        dropped.update(set(indexes) - set(keep))
        assumed.update(indexes)
        if len(keep) > 1 or len({len(value) for value in per_window.values()}) > 1:
            possible.update(indexes)

    rows = tuple(
        CollectedRow(
            source_index=index,
            collected_window=window,
            row=row,
            weak_event_key=weak_event_key(row),
            overlap_duplicate=index in dropped,
            possible_duplicate=index in possible,
            dedup_assumed=index in assumed,
        )
        for index, (window, row) in enumerate(collected)
    )
    return CollectionResult(
        rows=rows,
        windows=windows,
        input_count=len(rows),
        unique_count=sum(not row.overlap_duplicate for row in rows),
        overlap_duplicate_count=len(dropped),
        possible_duplicate_count=len(possible),
        truncated_windows=tuple(truncated),
        cache_hits=cache_hits,
    )


def build_summary(result: CollectionResult) -> dict:
    """Aggregate-only audit summary; never includes row-level quantities."""
    kept = [row for row in result.rows if not row.overlap_duplicate]
    days = Counter((row.row.get("warehousingDate") or "")[:10] for row in kept)
    return {
        "input_count": result.input_count,
        "unique_count": result.unique_count,
        "unique_count_semantics": "retained_observations_not_proven_unique_events",
        "overlap_duplicate_count": result.overlap_duplicate_count,
        "possible_duplicate_count": result.possible_duplicate_count,
        "windows": [{"start": w.start.isoformat(), "end": w.end.isoformat()} for w in result.windows],
        "truncated_windows": [
            {"start": w.start.isoformat(), "end": w.end.isoformat()} for w in result.truncated_windows
        ],
        "cache_hits": result.cache_hits,
        "distinct_po": len({row.row.get("purchaseOrderCode") for row in kept if row.row.get("purchaseOrderCode")}),
        "distinct_sku": len({row.row.get("sku") for row in kept if row.row.get("sku")}),
        "day_counts": dict(sorted(days.items())),
        "rows_without_uom": len(kept),
        "rows_without_stable_id": len(kept),
    }
