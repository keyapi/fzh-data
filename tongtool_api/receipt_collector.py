"""Bounded, overlapping-window collection for Tongtool receipt rows.

Tongtool exposes no stable receipt or line ID. This collector therefore keeps
raw rows and flags overlap duplicates explicitly; it never invents a business
identity, UOM, or timezone.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from tongtool_api.purchase_receipts import CALL_INTERVAL_SECONDS, fetch_receipts


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
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise TypeError("start/end must be a date, datetime, or ISO date string")


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
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    if not 0 <= overlap_days < window_days:
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


def _repo_root() -> Optional[Path]:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return None


def _check_cache_dir(cache_dir: Path) -> None:
    root = _repo_root()
    if root is not None and cache_dir.resolve().is_relative_to(root):
        raise ValueError("cache_dir must be outside the git repository")


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
) -> CollectionResult:
    """Fetch overlapping windows and flag, not hide, ambiguous duplicates.

    Rows with the same weak key are deduplicated only when they come from
    different collection windows (the likely overlap replay). Duplicates inside
    one window are kept and marked ``possible_duplicate`` because they could be
    two real receipts at the same second. Raw rows stay in the caller's cache
    directory; pass a path outside the git repository.
    """
    windows = split_windows(start, end, window_days=window_days, overlap_days=overlap_days)
    cache_path = Path(cache_dir) if cache_dir is not None else None
    if cache_path is not None:
        _check_cache_dir(cache_path)
        cache_path.mkdir(parents=True, exist_ok=True)

    collected: list[tuple[CollectionWindow, dict]] = []
    truncated = []
    cache_hits = 0
    for index, window in enumerate(windows):
        payload = None
        if cache_path is not None:
            file_path = cache_path / (_cache_key(window, po_code, page_size, max_pages) + ".json")
            if file_path.is_file():
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                cache_hits += 1
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
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            if cache_path is not None:
                file_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            if index < len(windows) - 1:
                sleep(interval)
        if payload.get("truncated"):
            truncated.append(window)
        collected.extend((window, row) for row in payload["rows"])

    groups: dict[tuple, list[int]] = {}
    for index, (_, row) in enumerate(collected):
        groups.setdefault(weak_event_key(row), []).append(index)

    dropped: set[int] = set()
    possible: set[int] = set()
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        first_window = collected[indexes[0]][0]
        same_window = [index for index in indexes if collected[index][0] == first_window]
        if len(same_window) > 1:
            possible.update(same_window)
        for index in indexes:
            if collected[index][0] != first_window:
                dropped.add(index)

    rows = tuple(
        CollectedRow(
            source_index=index,
            collected_window=window,
            row=row,
            weak_event_key=weak_event_key(row),
            overlap_duplicate=index in dropped,
            possible_duplicate=index in possible,
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
