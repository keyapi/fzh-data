"""Runtime cache and checkpoint helpers for sync-combos apply."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class ComboOpsCache:
    """Reuse category and bottom SKU lookups within one sync-combos run."""

    def __init__(self) -> None:
        self.category_by_cid: dict[str, dict[str, Any] | None] = {}
        self.bottom_rows: dict[str, dict[str, Any]] = {}
        self.category_fetch_calls = 0
        self.category_cache_hits = 0

    def set_bottom_rows(self, rows: dict[str, dict[str, Any]]) -> None:
        self.bottom_rows = dict(rows)

    def get_category(
        self,
        full_cid: str,
        fetch: Callable[[], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        if full_cid not in self.category_by_cid:
            self.category_fetch_calls += 1
            self.category_by_cid[full_cid] = fetch()
        else:
            self.category_cache_hits += 1
        return self.category_by_cid[full_cid]


def index_raw_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_sku: dict[str, dict[str, Any]] = {}
    for row in rows:
        sku = str(row.get("sku") or "")
        if sku:
            by_sku[sku] = row
    return by_sku


def checkpoint_path(report_path: str | None) -> Path | None:
    if not report_path:
        return None
    path = Path(report_path)
    return path.with_name(f"{path.stem}.checkpoint{path.suffix}")


def write_checkpoint(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
