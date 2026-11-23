"""Read-only EN live stock rows; no data is written to the pack or EN."""
from __future__ import annotations
import os, tempfile
from pathlib import Path


def read_live(env_file=None):
    from demand_collaboration.live_stock import LiveStockSource
    cache = Path(tempfile.gettempdir()) / "supply_copilot_live_stock.json"
    source = LiveStockSource(
        env_file=env_file or os.environ.get("EN_API_ENV"),
        base=os.environ.get("DEMAND_LIVE_STOCK_BASE"),
        cache_path=str(cache),
        timeout=20,
        ttl_seconds=0,
    )
    overlay = source.get()
    if overlay.get("status") != "ok":
        raise RuntimeError(overlay.get("error") or "EN live stock unavailable")
    return overlay.get("rows") or []
