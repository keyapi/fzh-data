"""Read-only EN Tongtool Stock Latest overlay for the USNJ recommendation page.

The overlay is a *live observation*, never a source of truth for the immutable
recommendation snapshot.  It is joined to recommendation rows by
``(sku, warehouse)`` exactly as the two systems expose them; a row that cannot be
matched is reported as ``not_found`` and its quantities stay ``None`` (unknown),
never ``0``.

EN is accessed with GET requests only.  Credentials come from the existing
``EN_API/.env`` file or process environment (``ERP_API_KEY`` / ``ERP_API_SECRET``). When the live fetch
fails the caller may serve a previously written cache file, marked ``stale`` so
the page can say it is old data.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

SCHEMA = "en-live-stock-overlay/v1"
SOURCE = "en_tongtool_stock_latest"
DEFAULT_ENV_FILE = str(Path(__file__).resolve().parent.parent / "EN_API" / ".env")
DEFAULT_BASE = "https://erpnext.vilavi.cn"
RUN_DOCTYPE = "Tongtool Stock Run"
LATEST_DOCTYPE = "Tongtool Stock Latest"
RUN_JOB = "stock_snapshot"
QUANTITIES = ("available", "intransit", "waiting_shipment", "defects")


class LiveStockError(Exception):
    """The live EN observation could not be trusted or completed."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _number(value):
    """Return a finite number, or ``None`` for an explicitly unknown cell."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise LiveStockError("stock quantity must be numeric, not boolean")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize(value):
    """Join key normalisation: ignore case and whitespace only."""
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def key_of(sku, warehouse):
    return normalize(sku) + "\x1f" + normalize(warehouse)


def validate_run(run):
    if not isinstance(run, dict):
        raise LiveStockError("EN stock run is missing")
    if run.get("job") != RUN_JOB:
        raise LiveStockError("EN stock run is not a stock snapshot")
    if str(run.get("status") or "") != "Success" or run.get("complete") not in (1, True):
        raise LiveStockError("EN stock run is not complete and successful")
    for field in ("run_id", "snapshot_at", "snapshot_date"):
        if not run.get(field):
            raise LiveStockError("EN stock run lacks " + field)
    try:
        if int(run.get("row_count", -1)) < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise LiveStockError("EN stock run lacks a valid row_count") from None
    return run


def credentials(env_file=None):
    """Explicit file, then complete process pair, then repository-local .env.

    A partial pair in a selected source fails rather than combining credentials
    from another source or account. No credential value appears in errors.
    DEMAND_LIVE_STOCK_ENV is an explicit file override for existing callers.
    """
    from dotenv import dotenv_values

    def pair(values, label):
        for prefix in ("ERP_", "PROD_ERP_"):
            key = str(values.get(prefix + "API_KEY") or "").strip()
            secret = str(values.get(prefix + "API_SECRET") or "").strip()
            if key or secret:
                if not key or not secret:
                    raise LiveStockError("EN credential pair incomplete in " + label)
                return key, secret
        return None

    explicit = env_file or os.environ.get("DEMAND_LIVE_STOCK_ENV")
    if not explicit:
        process_pair = pair(os.environ, "process environment")
        if process_pair:
            return process_pair
    path = Path(explicit or DEFAULT_ENV_FILE)
    if not path.is_file():
        raise LiveStockError("EN credential file unavailable at " + str(path))
    try:
        file_pair = pair(dotenv_values(path), "selected file")
    except OSError as exc:
        raise LiveStockError("EN credential file unreadable") from exc
    if not file_pair:
        raise LiveStockError("EN credential pair unavailable in selected file")
    return file_pair


def _session(key, secret):
    import requests

    session = requests.Session()
    session.headers["Authorization"] = "token " + key + ":" + secret
    session.headers["Accept"] = "application/json"
    return session


def _get(session, url, params, timeout):
    import requests

    try:
        response = session.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise LiveStockError("EN request failed: " + str(exc)) from exc
    if response.status_code != 200:
        raise LiveStockError(f"EN {url} returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise LiveStockError("EN returned non-JSON payload") from exc


def get_run(session, base=None, timeout=20):
    base = (base or os.environ.get("DEMAND_LIVE_STOCK_BASE", DEFAULT_BASE)).rstrip("/")
    payload = _get(session, base + "/api/resource/" + quote(RUN_DOCTYPE, safe=""), {
        "fields": json.dumps(["*"]),
        "filters": json.dumps([["job", "=", RUN_JOB], ["status", "=", "Success"],
                               ["complete", "=", 1]]),
        "order_by": "snapshot_at desc",
        "limit_page_length": 1,
    }, timeout)
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) != 1:
        raise LiveStockError("EN has no latest stock snapshot run")
    return validate_run(rows[0])


def read_rows(session, run, base=None, timeout=20, page_size=500, max_pages=200):
    base = (base or os.environ.get("DEMAND_LIVE_STOCK_BASE", DEFAULT_BASE)).rstrip("/")
    url = base + "/api/resource/" + quote(LATEST_DOCTYPE, safe="")
    rows, seen = [], set()
    for page in range(max_pages):
        payload = _get(session, url, {
            "fields": json.dumps(["*"]),
            "filters": json.dumps([["run_id", "=", run["run_id"]]]),
            "order_by": "name asc",
            "limit_start": page * page_size,
            "limit_page_length": page_size,
        }, timeout)
        batch = payload.get("data")
        if not isinstance(batch, list):
            raise LiveStockError("EN stock page has no data container")
        for row in batch:
            name = row.get("name")
            if not name or name in seen:
                raise LiveStockError("EN stock page has a missing/duplicate record name")
            seen.add(name)
        rows.extend(batch)
        if len(batch) < page_size:
            break
    else:
        raise LiveStockError("EN stock pagination was not exhausted")
    expected = int(run.get("row_count", -1))
    if expected >= 0 and len(rows) != expected:
        raise LiveStockError("EN stock row count does not match the run manifest")
    return rows


def _stock_record(row):
    sku = str(row.get("sku") or "").strip()
    warehouse = str(row.get("warehouse") or "").strip()
    if not sku or not warehouse:
        raise LiveStockError("EN stock row lacks sku/warehouse")
    return {
        "sku": sku,
        "warehouse": warehouse,
        "warehouse_id": row.get("warehouse_id"),
        "available": _number(row.get("available")),
        "intransit": _number(row.get("intransit")),
        "waiting_shipment": _number(row.get("waiting_shipment")),
        "defects": _number(row.get("defects")),
        "snapshot_at": row.get("snapshot_at"),
        "run_id": row.get("run_id"),
    }


def build_overlay(rows, run, base=None, fetched_at=None):
    """Turn EN stock rows into a serialisable overlay keyed by SKU × warehouse.

    Duplicate physical keys are aggregated.  A quantity is aggregated only when
    every duplicate carries a known number; otherwise it stays ``None`` so an
    unknown cell can never turn into an invented total.
    """
    grouped = {}
    for row in rows:
        record = _stock_record(row)
        key = key_of(record["sku"], record["warehouse"])
        bucket = grouped.setdefault(key, {"record": record, "count": 0,
                                          "values": {field: [] for field in QUANTITIES}})
        bucket["count"] += 1
        for field in QUANTITIES:
            bucket["values"][field].append(record[field])
    output = []
    for key, bucket in grouped.items():
        record = dict(bucket["record"])
        for field in QUANTITIES:
            values = bucket["values"][field]
            record[field] = (sum(values) if all(value is not None for value in values)
                             else None)
        record["duplicate_rows"] = bucket["count"]
        record["stock_key"] = key
        output.append(record)
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "base": (base or os.environ.get("DEMAND_LIVE_STOCK_BASE", DEFAULT_BASE)).rstrip("/"),
        "run_id": run.get("run_id"),
        "snapshot_at": run.get("snapshot_at"),
        "snapshot_date": run.get("snapshot_date"),
        "row_count": len(output),
        "source_row_count": len(rows),
        "warehouse_count": len({row["warehouse"] for row in output}),
        "samples": [
            {"sku": row["sku"], "warehouse": row["warehouse"]}
            for row in output[:10]
        ],
        "fetched_at": fetched_at or _now(),
        "status": "ok",
        "stale": False,
        "rows": output,
    }


def fetch_live(env_file=None, base=None, timeout=20):
    key, secret = credentials(env_file)
    session = _session(key, secret)
    run = get_run(session, base, timeout)
    rows = read_rows(session, run, base, timeout)
    # Guard against the mirror being replaced while pages were read.
    confirmed = get_run(session, base, timeout)
    for field in ("run_id", "snapshot_at", "complete", "row_count"):
        if confirmed.get(field) != run.get(field):
            raise LiveStockError("EN stock snapshot changed during read")
    return build_overlay(rows, run, base, fetched_at=_now())


def index_overlay(overlay):
    if not overlay or overlay.get("status") not in {"ok", "fallback_stale"}:
        return {}
    return {key_of(row.get("sku"), row.get("warehouse")): row
            for row in overlay.get("rows") or []}


def _delta(live, snapshot):
    if live is None or snapshot is None:
        return None
    try:
        return float(live) - float(snapshot)
    except (TypeError, ValueError):
        return None


def attach_to_snapshot(view, overlay):
    """Return a decorated copy of a recommendation view; never mutate inputs."""
    if not view or not overlay:
        return view
    view = dict(view)
    rows = [dict(row) for row in view.get("rows") or []]
    meta = {key: overlay.get(key) for key in
            ("schema", "source", "base", "run_id", "snapshot_at", "snapshot_date",
             "row_count", "source_row_count", "warehouse_count", "fetched_at",
             "status", "stale", "error", "fallback_reason")}
    if overlay.get("status") == "unavailable":
        meta["status"] = "unavailable"
        for row in rows:
            row["live_stock"] = None
    else:
        index = index_overlay(overlay)
        matched = 0
        for row in rows:
            aliases = row.get("tongtool_skus") or [row.get("tongtool_sku") or row.get("sku")]
            aliases = sorted({a for a in aliases if a})
            matches, seen_keys = [], set()
            for alias in aliases:
                key = key_of(alias, row.get("warehouse"))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                found = index.get(key)
                if found:
                    matches.append(found)
            live = None
            if matches:
                live = dict(matches[0])
                partial = len(matches) < len(aliases)
                for field in QUANTITIES:
                    values = [m.get(field) for m in matches]
                    if any(v is None for v in values):
                        partial = True
                        live[field] = None
                    elif partial:
                        live[field] = None
                    else:
                        live[field] = sum(values)
                live["partial"] = partial
                live["missing_alias_count"] = max(0, len(aliases) - len(matches))
                live["duplicate_rows"] = sum(int(m.get("duplicate_rows") or 1) for m in matches)
                live["alias_count"] = len(matches)
            if live is None:
                row["live_stock"] = {"status": "not_found",
                                     "run_id": overlay.get("run_id"),
                                     "snapshot_at": overlay.get("snapshot_at")}
                continue
            matched += 1
            record = dict(live)
            record.pop("stock_key", None)
            record["status"] = "matched"
            record["stale"] = bool(overlay.get("stale"))
            record["snapshot_c_qty"] = row.get("c_qty")
            record["snapshot_e_qty"] = row.get("e_qty")
            record["available_delta_vs_snapshot"] = _delta(record.get("available"),
                                                            row.get("c_qty"))
            record["intransit_delta_vs_snapshot"] = _delta(record.get("intransit"),
                                                            row.get("e_qty"))
            row["live_stock"] = record
        meta["matched_count"] = matched
        meta["unmatched_count"] = len(rows) - matched
    view["rows"] = rows
    view["live_stock"] = meta
    return view


def _write_cache(path, overlay):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".live-stock-", suffix=".json",
                                         dir=str(target.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(overlay, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_cache(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    if not isinstance(payload.get("rows"), list):
        return None
    return payload


class LiveStockSource:
    """Fetch once per TTL, persist a private cache, and fall back to it stale."""

    def __init__(self, env_file=None, base=None, cache_path=None, timeout=20,
                 ttl_seconds=60, fetcher=None):
        self.env_file = env_file
        self.base = base
        self.cache_path = cache_path
        self.timeout = timeout
        self.ttl_seconds = ttl_seconds
        self.fetcher = fetcher
        self._lock = threading.Lock()
        self._value = None
        self._at = 0.0

    def get(self, force=False):
        with self._lock:
            now = time.monotonic()
            if not force and self._value is not None and now - self._at < self.ttl_seconds:
                return self._value
            try:
                overlay = (self.fetcher() if self.fetcher
                           else fetch_live(self.env_file, self.base, self.timeout))
                if not isinstance(overlay, dict) or overlay.get("schema") != SCHEMA:
                    raise LiveStockError("live stock payload has an unexpected schema")
                overlay = dict(overlay, status="ok", stale=False)
                if self.cache_path:
                    _write_cache(self.cache_path, overlay)
                self._value = overlay
            except Exception as exc:  # noqa: BLE001 - page must stay readable
                reason = f"{type(exc).__name__}: {exc}"
                cached = _read_cache(self.cache_path) if self.cache_path else None
                if cached:
                    self._value = dict(cached, status="fallback_stale", stale=True,
                                       fallback_reason=reason,
                                       fetched_at=cached.get("fetched_at"),
                                       served_at=_now())
                else:
                    self._value = {
                        "schema": SCHEMA, "source": SOURCE, "status": "unavailable",
                        "stale": True, "error": reason, "rows": [],
                        "run_id": None, "snapshot_at": None, "snapshot_date": None,
                        "row_count": 0, "fetched_at": None,
                    }
            self._at = now
            return self._value


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="只读拉取 EN Tongtool Stock Latest 并写入本地缓存")
    parser.add_argument("--env-file", default=os.environ.get("DEMAND_LIVE_STOCK_ENV", DEFAULT_ENV_FILE))
    parser.add_argument("--base", default=os.environ.get("DEMAND_LIVE_STOCK_BASE", DEFAULT_BASE))
    parser.add_argument("--out", required=True, help="私有缓存 JSON 路径")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args(argv)
    overlay = fetch_live(args.env_file, args.base, args.timeout)
    _write_cache(args.out, overlay)
    print(json.dumps({key: overlay[key] for key in
                      ("status", "stale", "run_id", "snapshot_at", "row_count",
                       "warehouse_count", "fetched_at")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
