"""Formal read-only EN → full_supply_facts refresh entry.

One command collects the EN test/prod site, validates every page, adapts the
responses into the existing ``full_supply_facts`` inputs, computes, verifies
Parquet/JSON/manifest, and only then atomically switches ``latest.json``.

No replenishment quantity, no order, no PO creation, no EN write, no
production deploy. Credentials come from ``EN_API/.env``; the only artifacts
are under the git-ignored ``out/`` directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from supply_chain_visibility.abc_datasets import load_abc_datasets
from supply_chain_visibility.abc_inputs import load_frozen_abc
from supply_chain_visibility.en_collect import (
    CollectionError,
    HttpEnClient,
    build_mappings,
    build_production,
    build_receipts,
    build_so_balances,
    build_transit,
    collect,
)
from supply_chain_visibility.publication import publish, source_freshness
from supply_chain_visibility.supply_pipeline import _build_inputs, run_pipeline

SCHEMA_VERSION = "supply-snapshot-refresh/v1"


@dataclass
class RefreshOptions:
    out: str
    as_of: str
    sales_order: str | None = None
    page_size: int = 500
    max_pages: int = 200
    delivery_page_size: int | None = None
    include_inactive: bool = False
    a_dataset: str | None = None
    b_dataset: str | None = None
    c_dataset: str | None = None
    a_workbook: str | None = None
    b_workbook: str | None = None
    c_workbook: str | None = None
    a_version: str | None = None
    b_version: str | None = None
    c_version: str | None = None
    c_declared_b_version: str | None = None
    no_abc: bool = False
    scope_json: str | None = None
    max_stock_age_days: int = 1
    max_age_seconds: int = 900


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(payload, ensure_ascii=False,
                                    indent=2, default=str),
                         encoding="utf-8")
    os.replace(temporary, path)


def _write_attempt(out, status, stage, source, error="", error_type=""):
    _atomic_json(Path(out) / "last_attempt.json", {
        "status": status, "stage": stage, "source": source,
        "error": str(error)[:500], "error_type": error_type or type(error).__name__,
        "attempted_at": _now()})


class RefreshLock:
    """Non-blocking cross-platform lock held for the whole refresh."""

    def __init__(self, path):
        self.path = Path(path)
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._handle = open(self.path, "a+b")
            self._handle.seek(0)
            if self._handle.read(1) == b"":
                self._handle.seek(0)
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if self._handle is not None:
                self._handle.close()
            self._handle = None
            raise CollectionError(
                "lock", "refresh",
                "another refresh already holds the lock") from exc
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._handle is None:
            return False
        try:
            if os.name == "nt":
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
        return False


def _as_aware(value):
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return parsed


def _load_abc(options):
    if options.no_abc:
        return None, []
    if options.a_dataset or options.b_dataset or options.c_dataset:
        if not all((options.a_dataset, options.b_dataset, options.c_dataset)):
            raise CollectionError("abc", "config",
                                  "A/B/C structured datasets must be supplied together")
        result = load_abc_datasets(
            options.a_dataset, options.b_dataset, options.c_dataset,
            as_of=_as_aware(options.as_of).date().isoformat(),
            max_stock_age_days=options.max_stock_age_days,
            as_of_time=options.as_of,
            c_declared_b_version=options.c_declared_b_version)
        return result, list(result["datasets"]["B"]["rows"])
    if options.a_workbook or options.b_workbook or options.c_workbook:
        if not all((options.a_workbook, options.b_workbook,
                    options.c_workbook)):
            raise CollectionError("abc", "config",
                                  "A/B/C workbooks must be supplied together")
        if not all((options.a_version, options.b_version, options.c_version)):
            raise CollectionError("abc", "config",
                                  "A/B/C workbook versions are required")
        result = load_frozen_abc(
            options.a_workbook, options.b_workbook, options.c_workbook,
            as_of=_as_aware(options.as_of).date().isoformat(),
            a_version=options.a_version, b_version=options.b_version,
            c_version=options.c_version,
            c_declared_b_version=options.c_declared_b_version,
            max_stock_age_days=options.max_stock_age_days,
            as_of_time=options.as_of)
        return result, _b_rows_from_readiness(result["readiness"])
    raise CollectionError("abc", "config",
                          "supply --a-dataset/--b-dataset/--c-dataset, "
                          "workbooks, or --no-abc with --scope-json")


def _scope_hash(source, version, codes):
    canonical = json.dumps({"source": source, "version": version,
                            "items": sorted(set(codes))},
                           sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _delivery_scope(options, abc_result, b_rows):
    if options.scope_json:
        try:
            raw = json.loads(Path(options.scope_json).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CollectionError("abc", "scope", "cannot read scope: %s" % exc)
        if not isinstance(raw, dict):
            raise CollectionError("abc", "scope", "scope JSON must be an object")
        return raw
    if abc_result is None:
        raise CollectionError(
            "abc", "scope",
            "--no-abc requires an authoritative --scope-json; observed delivery is not scope")
    report = abc_result.get("report") or {}
    source = "ABC:" + str((report.get("dataset_versions") or {}).get("A")
                           or options.a_version or "unknown")
    version = str((report.get("dataset_versions") or {}).get("B")
                  or options.b_version or "unknown")
    b_by_item = defaultdict(list)
    for row in b_rows:
        b_by_item[row.get("item_code")].append(row)
    items = []
    for code in sorted(set(abc_result.get("approved_items") or [])):
        candidates = b_by_item.get(code) or []
        meta = {"item_code": code}
        if len(candidates) == 1:
            for name in ("tt_sku", "branch", "warehouse", "purpose",
                         "market", "product_form", "uom"):
                if candidates[0].get(name) not in (None, ""):
                    meta[name] = candidates[0][name]
        items.append(meta)
    codes = [item["item_code"] for item in items]
    return {"status": "provided", "source": source, "version": version,
            "hash": _scope_hash(source, version, codes), "items": items}


def _b_rows_from_readiness(readiness):
    rows = []
    for row in readiness.get("rows") or []:
        units = list(row.get("b_units") or [])
        if not units and row.get("canonical_uom"):
            units = [row["canonical_uom"]]
        for uom in units or [None]:
            rows.append({
                "item_code": row["item_code"], "uom": uom,
                "warehouse": row.get("b_warehouse"),
                "branch": row.get("b_branch"),
                "purpose": row.get("b_purpose"),
                "tt_sku": row.get("b_tt_sku"),
                "market": row.get("b_market"),
                "product_form": row.get("b_product_form"),
            })
    return rows


def _write_staging(staging, name, payload):
    path = Path(staging) / name
    _atomic_json(path, payload)
    return str(path)


def _mapping_version(options, abc_result):
    if abc_result is None:
        return "not_provided"
    versions = (abc_result.get("report") or {}).get("dataset_versions") or {}
    return versions.get("B") or options.b_version or "unknown"


def _rerun_argv(options, paths):
    argv = ["python", "-m", "supply_chain_visibility.supply_pipeline",
            "--delivery-json", paths["delivery"],
            "--mapping-json", paths["mapping"],
            "--so-json", paths["so"],
            "--production-json", paths["production"],
            "--transit-json", paths["transit"],
            "--receipt-json", paths["receipt"],
            "--as-of", options.as_of,
            "--max-stock-age-days", str(options.max_stock_age_days),
            "--max-age-seconds", str(options.max_age_seconds),
            "--out", options.out]
    if "approved_items" in paths:
        argv += ["--approved-items-json", paths["approved_items"]]
    if options.a_dataset:
        argv += ["--a-dataset", options.a_dataset,
                 "--b-dataset", options.b_dataset,
                 "--c-dataset", options.c_dataset]
    elif options.a_workbook:
        argv += ["--a-workbook", options.a_workbook,
                 "--b-workbook", options.b_workbook,
                 "--c-workbook", options.c_workbook,
                 "--a-version", options.a_version,
                 "--b-version", options.b_version,
                 "--c-version", options.c_version]
    if options.c_declared_b_version:
        argv += ["--c-declared-b-version", options.c_declared_b_version]
    return argv


def _unknown_summary(result, abc_result, collection):
    unknown = list(collection.get("business_unknown") or [])
    if abc_result is None:
        unknown.append({"source": "ABC", "status": "not_provided"})
    summary = result["full"]["summary"]
    unknown.append({
        "source": "full_supply_facts",
        "unknown_rows": summary.get("unknown_rows"),
        "unknown_reason_distribution": summary.get("unknown_reason_distribution"),
        "inventory_time_unknown_rows": summary.get("inventory_time_unknown_rows"),
        "attribution_distribution": summary.get("attribution_distribution"),
    })
    return unknown


def _pipeline_args(paths):
    return SimpleNamespace(
        delivery_json=paths["delivery"], mapping_json=paths["mapping"],
        audit_json=[], status_json=[], so_json=paths["so"],
        production_json=paths["production"], inventory_json=None,
        transit_json=paths["transit"], receipt_json=paths["receipt"],
        approved_items_json=paths.get("approved_items"))


def run_refresh(options, client):
    """Run one locked refresh; never raises for expected collection failures."""
    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        with RefreshLock(out / ".refresh.lock"):
            return _run_locked(options, client)
    except CollectionError as exc:
        _write_attempt(out, "failed", exc.stage, exc.source, exc.message,
                       "CollectionError")
        return {"status": "failed", "stage": exc.stage,
                "source": exc.source, "error": exc.message}


def _run_locked(options, client):
    out = Path(options.out)
    staging = out / ".staging" / ("refresh-" + uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        try:
            abc_result, b_rows = _load_abc(options)
            delivery_scope = _delivery_scope(options, abc_result, b_rows)
        except CollectionError:
            raise
        except Exception as exc:  # noqa: BLE001
            _write_attempt(out, "failed", "abc", "structured_or_workbook",
                           str(exc), type(exc).__name__)
            return {"status": "failed", "stage": "abc", "error": str(exc)}
        try:
            collection = collect(
                client, sales_order=options.sales_order,
                page_size=options.page_size, max_pages=options.max_pages,
                delivery_page_size=options.delivery_page_size,
                include_inactive=options.include_inactive,
                delivery_scope=delivery_scope)
        except CollectionError as exc:
            _write_attempt(out, "failed", exc.stage, exc.source,
                           exc.message, "CollectionError")
            return {"status": "failed", "stage": exc.stage,
                    "source": exc.source, "error": exc.message}

        supply = collection["supply"]
        delivery = collection["delivery"]
        if delivery is None:
            _write_attempt(out, "failed", "collect", "delivery",
                           "no delivery pages")
            return {"status": "failed", "stage": "collect",
                    "source": "delivery", "error": "no delivery pages"}
        observed_at = supply.get("observed_at") or options.as_of
        mappings = build_mappings(delivery.get("delivery_lines") or [], b_rows)
        so_rows = build_so_balances(supply, b_rows)
        production = build_production(supply, b_rows)
        transit = build_transit(supply, b_rows)
        receipts = build_receipts(supply, b_rows)
        approved = list((abc_result or {}).get("approved_items") or
                        [item.get("item_code") for item in
                         delivery_scope.get("items") or []
                         if isinstance(item, dict) and item.get("item_code")])
        abc_inventory = list((abc_result or {}).get("inventory") or [])

        paths = {
            "delivery": _write_staging(staging, "delivery.json", delivery),
            "mapping": _write_staging(staging, "mapping.json", {
                "source": ("not_provided" if abc_result is None
                           else "B-structured"),
                "version": _mapping_version(options, abc_result),
                "rows": mappings}),
            "so": _write_staging(staging, "so.json", {
                "schema_version": "local/v1", "observed_at": observed_at,
                "balances": so_rows}),
            "production": _write_staging(staging, "production.json", {
                "schema_version": "local/v1", "observed_at": observed_at,
                "production": production}),
            "transit": _write_staging(staging, "transit.json", {
                "schema_version": "local/v1", "observed_at": observed_at,
                "transit": transit}),
            "receipt": _write_staging(staging, "receipt.json", {
                "schema_version": "local/v1", "observed_at": observed_at,
                "receipts": receipts}),
        }
        if approved:
            paths["approved_items"] = _write_staging(
                staging, "approved_items.json", {
                    "schema_version": "local/v1", "observed_at": observed_at,
                    "items": approved})

        args = _pipeline_args(paths)
        inputs, layer_status = _build_inputs(
            args, delivery, [], [], paths["mapping"], abc_result)
        try:
            result = run_pipeline(
                delivery=delivery, mappings={"source": "B-structured",
                                             "version": _mapping_version(
                                                 options, abc_result),
                                             "rows": mappings},
                audits=[], statuses=[], as_of=options.as_of,
                so_balances=so_rows, production=production,
                abc_inventory=abc_inventory, transit=transit,
                receipts=receipts, approved_items=approved,
                max_age_seconds=options.max_age_seconds,
                layer_status=layer_status)
        except Exception as exc:  # noqa: BLE001
            _write_attempt(out, "failed", "compute", "full_supply_facts",
                           str(exc), type(exc).__name__)
            return {"status": "failed", "stage": "compute",
                    "error": str(exc)}

        freshness = source_freshness(
            inputs, as_of=options.as_of,
            max_age_seconds=options.max_age_seconds)
        if result["full"].get("freshness"):
            freshness["row_level"] = result["full"]["freshness"]["summary"]

        status = dict(collection["status"])
        status["abc"] = {
            "status": "not_provided" if abc_result is None else "ok",
            "inventory_rows": len(abc_inventory),
            "approved_items": len(approved),
        }
        status["adapters"] = {
            "delivery_lines": len(delivery.get("delivery_lines") or []),
            "mappings": len(mappings), "so_balances": len(so_rows),
            "production": len(production), "transit": len(transit),
            "receipts": len(receipts),
        }
        business_unknown = _unknown_summary(result, abc_result, collection)
        extra = {
            "collection_status": status,
            "business_unknown": business_unknown,
            "collection": {
                "schema_version": SCHEMA_VERSION,
                "supply_snapshot_id": collection["supply_signature"].get(
                    "snapshot_id"),
                "delivery_snapshot_id": (
                    collection["delivery_signature"] or {}).get("snapshot_id"),
                "page_size": options.page_size,
                "max_pages": options.max_pages,
            },
        }
        attempt_metadata = {
            "stage": "publish", "source": "full_supply_facts",
            "collection_status": status,
            "business_unknown": business_unknown,
        }
        try:
            published = publish(
                options.out, full_result=result["full"],
                position_result=result["position"], inputs=inputs,
                pipeline_as_of=options.as_of,
                rerun_argv=_rerun_argv(options, paths),
                effective_args={"source": "snapshot_refresh",
                                "as_of": options.as_of,
                                "sales_order": options.sales_order,
                                "page_size": options.page_size},
                abc_report=(abc_result or {}).get("report"),
                max_age_seconds=options.max_age_seconds,
                freshness=freshness, extra_manifest=extra,
                attempt_metadata=attempt_metadata)
        except Exception as exc:  # noqa: BLE001
            _write_attempt(out, "failed", "publish", "full_supply_facts",
                           str(exc), type(exc).__name__)
            return {"status": "failed", "stage": "publish",
                    "error": str(exc)}
        return {"status": "ok", "run_dir": published["run_dir"],
                "collection_status": status,
                "business_unknown": business_unknown}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _parse(argv=None):
    parser = argparse.ArgumentParser(
        prog="supply_snapshot_refresh",
        description="Read-only EN collection → full_supply_facts publication")
    parser.add_argument("--env", choices=("test", "prod"), default="test")
    parser.add_argument("--env-file")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--so", help="sales order name for a bounded snapshot")
    scope.add_argument("--all", action="store_true",
                       help="all readable SO lines (paginated)")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--delivery-page-size", type=int)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--delivery-include-inactive", action="store_true")
    parser.add_argument("--as-of")
    parser.add_argument("--max-stock-age-days", type=int, default=1)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--out", required=True)
    parser.add_argument("--a-dataset")
    parser.add_argument("--b-dataset")
    parser.add_argument("--c-dataset")
    parser.add_argument("--a-workbook")
    parser.add_argument("--b-workbook")
    parser.add_argument("--c-workbook")
    parser.add_argument("--a-version")
    parser.add_argument("--b-version")
    parser.add_argument("--c-version")
    parser.add_argument("--c-declared-b-version")
    parser.add_argument("--no-abc", action="store_true")
    parser.add_argument("--scope-json",
                        help="authoritative scope required with --no-abc")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse(argv)
    if not (1 <= args.page_size <= 2000):
        raise SystemExit("--page-size must be 1..2000")
    if args.delivery_page_size is not None and not (
            1 <= args.delivery_page_size <= 2000):
        raise SystemExit("--delivery-page-size must be 1..2000")
    if args.max_pages < 1:
        raise SystemExit("--max-pages must be >= 1")
    if args.max_stock_age_days < 0 or args.max_age_seconds < 0:
        raise SystemExit("age limits must be non-negative")
    abc_flags = (args.a_dataset, args.b_dataset, args.c_dataset,
                 args.a_workbook, args.b_workbook, args.c_workbook)
    if args.no_abc and any(abc_flags):
        raise SystemExit("--no-abc cannot be combined with A/B/C inputs")
    if args.scope_json and not args.no_abc:
        raise SystemExit("--scope-json is only used with --no-abc")
    as_of = args.as_of or _now()
    try:
        _as_aware(as_of)
    except ValueError as exc:
        raise SystemExit("--as-of must be timezone-aware: %s" % exc)
    options = RefreshOptions(
        out=args.out, as_of=as_of,
        sales_order=args.so if args.so else None,
        page_size=args.page_size, max_pages=args.max_pages,
        delivery_page_size=args.delivery_page_size,
        include_inactive=args.delivery_include_inactive,
        a_dataset=args.a_dataset, b_dataset=args.b_dataset,
        c_dataset=args.c_dataset,
        a_workbook=args.a_workbook, b_workbook=args.b_workbook,
        c_workbook=args.c_workbook,
        a_version=args.a_version, b_version=args.b_version,
        c_version=args.c_version,
        c_declared_b_version=args.c_declared_b_version,
        no_abc=args.no_abc,
        scope_json=args.scope_json,
        max_stock_age_days=args.max_stock_age_days,
        max_age_seconds=args.max_age_seconds)
    try:
        client = HttpEnClient(args.env, args.env_file)
    except CollectionError as exc:
        _write_attempt(args.out, "failed", exc.stage, exc.source,
                       exc.message, "CollectionError")
        print(json.dumps({"status": "failed", "stage": exc.stage,
                          "source": exc.source, "error": exc.message},
                         ensure_ascii=False))
        return 1
    result = run_refresh(options, client)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
