# -*- coding: utf-8 -*-
"""Runnable offline pipeline:

saved API responses -> creation audit -> PO status batch -> #323 consumer
-> full_supply_facts + timeline -> versioned manifest/latest.

No network, no business writes. Failure keeps the previous latest pointer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from supply_chain_visibility.full_supply_facts import (
    build_full_supply_facts,
)
from supply_chain_visibility.supply_position import assemble_input, build_position

SCHEMA_VERSION = "supply-pipeline/v1"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_many(paths):
    return [_load(path) for path in paths or ()]


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               default=str), encoding="utf-8")


def run_pipeline(*, delivery, mappings, audits, statuses, as_of,
                 so_balances=(), production=(), inventory=(), transit=(),
                 receipts=(), approved_items=(), max_age_seconds=900):
    payload = assemble_input(delivery=delivery, mappings=mappings,
                             audits=audits, statuses=statuses, as_of=as_of)
    position = build_position(payload)
    full = build_full_supply_facts(
        position, so_balances=so_balances, production=production,
        inventory=inventory, transit=transit, receipts=receipts,
        approved_items=approved_items, as_of=as_of,
        max_age_seconds=max_age_seconds)
    return {"position": position, "full": full}


def publish(out, result, *, pipeline_as_of):
    """Write a versioned run and only then switch latest.json."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    run_id = hashlib.sha1(("%s|%s" % (pipeline_as_of, time.time_ns())).encode()).hexdigest()[:12]
    run_dir = out / "runs" / ("run-%s-%s" % (time.strftime("%Y%m%d_%H%M%S"), run_id))
    tmp_dir = Path(tempfile.mkdtemp(prefix=".pipeline-", dir=str(out)))
    files = {}
    try:
        datasets = {
            "supply_position": result["position"]["rows"],
            "full_supply_facts": result["full"]["rows"],
            "timeline": result["full"]["timeline"]["rows"],
        }
        for name, rows in datasets.items():
            path = tmp_dir / ("%s.json" % name)
            _write_json(path, rows)
            files[name] = {"path": "%s.json" % name, "sha256": _sha256(path),
                           "rows": len(rows)}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "as_of": pipeline_as_of,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "full_supply_facts": result["full"]["summary"],
            "position_report": result["position"].get("report"),
            "datasets": files,
            "freshness": result["full"].get("freshness"),
            "forecast_connected": False,
            "netting_ready": False,
            "auto_order": False,
        }
        _write_json(tmp_dir / "manifest.json", manifest)
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        if run_dir.exists():
            shutil.rmtree(run_dir)
        tmp_dir.rename(run_dir)
        pointer = {"run_dir": str(run_dir), "manifest": str(run_dir / "manifest.json"),
                   "as_of": pipeline_as_of, "run_id": run_id}
        latest_tmp = out / ".latest.json.tmp"
        _write_json(latest_tmp, pointer)
        latest_tmp.replace(out / "latest.json")
        try:
            _write_json(out / "last_attempt.json", {
                "status": "succeeded", "run_id": run_id, "run_dir": str(run_dir),
                "attempted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        except OSError:
            pass  # latest already committed; do not report a successful publish as failed.
        return {"status": "ok", "run_dir": str(run_dir), "manifest": manifest}
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp_dir, ignore_errors=True)
        _write_json(out / "last_attempt.json", {
            "status": "failed", "error": str(exc)[:500],
            "attempted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline saved-response supply pipeline")
    parser.add_argument("--delivery-json", required=True)
    parser.add_argument("--mapping-json", required=True)
    parser.add_argument("--audit-json", action="append", required=True)
    parser.add_argument("--status-json", action="append", required=True)
    parser.add_argument("--so-json")
    parser.add_argument("--production-json")
    parser.add_argument("--inventory-json")
    parser.add_argument("--transit-json")
    parser.add_argument("--receipt-json")
    parser.add_argument("--approved-items-json")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    def rows(path, key):
        if not path:
            return []
        payload = _load(path)
        return payload.get(key) if isinstance(payload, dict) else payload

    try:
        result = run_pipeline(
            delivery=_load(args.delivery_json), mappings=_load(args.mapping_json),
            audits=_load_many(args.audit_json), statuses=_load_many(args.status_json),
            as_of=args.as_of,
            so_balances=rows(args.so_json, "balances"),
            production=rows(args.production_json, "production"),
            inventory=rows(args.inventory_json, "inventory"),
            transit=rows(args.transit_json, "transit"),
            receipts=rows(args.receipt_json, "receipts"),
            approved_items=rows(args.approved_items_json, "items"),
            max_age_seconds=args.max_age_seconds)
        published = publish(args.out, result, pipeline_as_of=args.as_of)
    except Exception as exc:  # noqa: BLE001
        out = Path(args.out)
        try:
            out.mkdir(parents=True, exist_ok=True)
            _write_json(out / "last_attempt.json", {
                "status": "failed", "error": str(exc)[:500],
                "attempted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        except Exception:  # noqa: BLE001 - disk failure must not hide original
            pass
        print("✗ pipeline failed, latest kept: %s" % exc, file=sys.stderr)
        return 1
    summary = published["manifest"]["full_supply_facts"]
    print("✓ pipeline: rows=%s unknown=%s -> %s"
          % (summary["rows"], summary["unknown_rows"], published["run_dir"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
