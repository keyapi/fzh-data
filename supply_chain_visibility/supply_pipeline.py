# -*- coding: utf-8 -*-
"""Runnable offline pipeline:

saved API responses + local frozen A/B/C -> creation audit -> PO status batch
-> #323 consumer -> full_supply_facts v2 -> verified Parquet/JSON publication.

No network, no business writes. Failure keeps the previous latest pointer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from supply_chain_visibility.abc_inputs import load_frozen_abc
from supply_chain_visibility.full_supply_facts import build_full_supply_facts
from supply_chain_visibility.publication import publish, read_publication, source_freshness
from supply_chain_visibility.supply_position import assemble_input, build_position

SCHEMA_VERSION = "supply-pipeline/v3"
MAPPING_STUB = {"source": "not_provided", "version": "unknown", "rows": []}


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


def _body(payload):
    if not isinstance(payload, dict):
        return {}
    body = payload.get("message", payload)
    return body if isinstance(body, dict) else {}


def _input_entry(role, path, *, rows=0, status="provided", version=None,
                 as_of=None, observed_at=None, required_for_closure=False,
                 reason=None, source=None, temporal=True, version_status=None,
                 time_status=None, completeness="complete", truncated=False,
                 partial_reason=None):
    entry = {
        "role": role,
        "source": source or ("file" if path else "not_provided"),
        "path": str(path) if path else None,
        "sha256": _sha256(path) if path else None,
        "rows": rows,
        "version": version,
        "version_status": version_status or ("provided" if version
                                             else "missing"),
        "as_of": as_of,
        "observed_at": observed_at,
        "time_status": time_status or ("provided" if (as_of or observed_at)
                                       else "missing"),
        "completeness": completeness,
        "truncated": bool(truncated),
        "partial_reason": list(partial_reason or []),
        "temporal": temporal,
        "status": status,
        "required_for_closure": required_for_closure,
        "reason": reason,
    }
    return entry


def _versions(payload):
    body = _body(payload)
    return {key: body.get(key) for key in
            ("schema_version", "rule_version", "implementation_version")
            if body.get(key)}


def _check_mixed(entries, label):
    versions = [_versions(payload) for payload in entries]
    present = [value for value in versions if value]
    if present and len(present) != len(versions):
        raise ValueError("mixed_input_versions:" + label + ":missing_version")
    if present:
        first = present[0]
        if any(value != first for value in present[1:]):
            raise ValueError("mixed_input_versions:" + label)
    return "provided" if present else "missing"


def run_pipeline(*, delivery, mappings, audits, statuses, as_of,
                 so_balances=(), production=(), inventory=(), abc_inventory=(),
                 transit=(), receipts=(), approved_items=(), max_age_seconds=900,
                 layer_status=None):
    if mappings is None:
        mappings = dict(MAPPING_STUB)
    _check_mixed(audits, "audit")
    _check_mixed(statuses, "po_status")
    payload = assemble_input(delivery=delivery, mappings=mappings,
                             audits=audits, statuses=statuses, as_of=as_of)
    payload["max_status_age_seconds"] = max_age_seconds
    position = build_position(payload)
    full = build_full_supply_facts(
        position, so_balances=so_balances, production=production,
        inventory=inventory, abc_inventory=abc_inventory, transit=transit,
        receipts=receipts, approved_items=approved_items, as_of=as_of,
        max_age_seconds=max_age_seconds, layer_status=layer_status)
    return {"position": position, "full": full}


def _rows(path, key):
    if not path:
        return []
    payload = _load(path)
    return payload.get(key) if isinstance(payload, dict) else payload


def _write_attempt(out, exc):
    try:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        temporary = out / (".attempt-" + hashlib.sha1(
            str(exc).encode("utf-8", "replace")).hexdigest()[:12])
        temporary.write_text(json.dumps({
            "status": "failed", "error": str(exc)[:500],
            "error_type": type(exc).__name__,
            "attempted_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False), encoding="utf-8")
        temporary.replace(out / "last_attempt.json")
    except OSError:
        pass


ROLE_LAYER = {"so": "so_demand", "production": "production",
              "inventory": "inventory", "transit": "in_transit",
              "receipt": "receipt"}


def _contract(payload, *, role, key, reject_truncation):
    if not isinstance(payload, dict):
        raise ValueError("input_not_object:" + role)
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise ValueError("input_missing_rows:" + role)
    pagination = payload.get("pagination") or {}
    partial_reason = []
    if payload.get("partial") is True:
        partial_reason.append("business_partial")
    if pagination.get("exhausted") is False:
        partial_reason.append("pagination_not_exhausted")
    if payload.get("truncated") is True:
        partial_reason.append("truncated_flag")
    truncated = bool(partial_reason)
    if truncated and reject_truncation:
        raise ValueError("input_truncated:" + role)
    version = payload.get("schema_version") or payload.get("version")
    as_of = payload.get("as_of")
    observed_at = payload.get("observed_at")
    completeness = "partial" if truncated else "complete"
    if not version or not (as_of or observed_at):
        completeness = "incomplete" if completeness == "complete" else completeness
    return {
        "rows": rows,
        "version": version,
        "version_status": "provided" if version else "missing",
        "as_of": as_of,
        "observed_at": observed_at,
        "time_status": "provided" if (as_of or observed_at) else "missing",
        "completeness": completeness,
        "truncated": truncated,
        "partial_reason": partial_reason,
    }


def _build_inputs(args, delivery, audits, statuses, mapping_path,
                  abc_result):
    inputs = []
    layer_status = {}
    delivery_body = _body(delivery)
    delivery_rows = delivery_body.get("delivery_lines") or []
    pagination = delivery_body.get("pagination") or {}
    delivery_partial = (delivery_body.get("partial") is True
                        or pagination.get("exhausted") is False
                        or pagination.get("partial") is True)
    if delivery_partial:
        layer_status["dn_po"] = "partial"
    inputs.append(_input_entry(
        "delivery", args.delivery_json, rows=len(delivery_rows),
        version=delivery_body.get("schema_version"),
        as_of=delivery_body.get("as_of"),
        observed_at=delivery_body.get("observed_at"),
        required_for_closure=True,
        completeness="partial" if delivery_partial else "complete",
        truncated=delivery_partial,
        partial_reason=(["business_partial"] if delivery_body.get("partial") is True else [])
        + (["pagination_not_exhausted"]
           if pagination.get("exhausted") is False else [])))
    if mapping_path:
        mapping = _load(mapping_path)
        inputs.append(_input_entry(
            "mapping", mapping_path,
            rows=len(mapping.get("rows") or []),
            version=mapping.get("version"),
            source=mapping.get("source"), temporal=False))
    else:
        inputs.append(_input_entry(
            "mapping", None, status="not_provided", reason="no_approved_mapping",
            source="not_provided", temporal=False))
    if not audits:
        inputs.append(_input_entry(
            "audit", None, status="not_provided", required_for_closure=True,
            reason="no_saved_creation_audit"))
    for index, path in enumerate(args.audit_json or ()):
        payload = _load(path)
        body = _body(payload)
        contract = _contract(body, role="audit", key="creations",
                             reject_truncation=False)
        if contract["completeness"] != "complete":
            layer_status["dn_po"] = "partial"
        audit_observed = contract["observed_at"] or max(
            (str(creation.get(key)) for creation in body.get("creations") or []
             for key in ("confirmed_at", "sent_at", "creation")
             if creation.get(key)), default=None)
        inputs.append(_input_entry(
            "audit:%s" % (body.get("delivery_note") or index), path,
            rows=len(contract["rows"]),
            version=contract["version"],
            version_status=contract["version_status"],
            as_of=contract["as_of"], observed_at=audit_observed,
            time_status="provided" if audit_observed else contract["time_status"],
            completeness=contract["completeness"],
            truncated=contract["truncated"],
            partial_reason=contract["partial_reason"],
            required_for_closure=True))
    if not statuses:
        inputs.append(_input_entry(
            "po_status", None, status="not_provided",
            required_for_closure=True, reason="no_saved_po_status"))
    for index, path in enumerate(args.status_json or ()):
        payload = _load(path)
        body = _body(payload)
        entries = body.get("results", body.get("statuses")) or {}
        contract = _contract({"results": list(entries.values()),
                              **{key: body.get(key) for key in
                                 ("schema_version", "version", "as_of",
                                  "observed_at", "partial", "truncated",
                                  "pagination")}},
                             role="po_status", key="results",
                             reject_truncation=False)
        if contract["completeness"] != "complete":
            layer_status["dn_po"] = "partial"
        inputs.append(_input_entry(
            "po_status:%s" % index, path, rows=len(entries),
            version=contract["version"],
            version_status=contract["version_status"],
            as_of=contract["as_of"], observed_at=contract["observed_at"],
            time_status=contract["time_status"],
            completeness=contract["completeness"],
            truncated=contract["truncated"],
            partial_reason=contract["partial_reason"],
            required_for_closure=True))
    for role, path, key in (
            ("so", args.so_json, "balances"),
            ("production", args.production_json, "production"),
            ("inventory", args.inventory_json, "inventory"),
            ("transit", args.transit_json, "transit"),
            ("receipt", args.receipt_json, "receipts"),
            ("approved_items", args.approved_items_json, "items")):
        if not path:
            inputs.append(_input_entry(role, None, status="not_provided",
                                       temporal=role != "approved_items"))
            continue
        payload = _load(path)
        if role == "approved_items":
            contract = _contract(payload, role=role, key=key,
                                 reject_truncation=False)
            inputs.append(_input_entry(
                role, path, rows=len(contract["rows"]),
                version=contract["version"],
                version_status=contract["version_status"],
                as_of=contract["as_of"], observed_at=contract["observed_at"],
                time_status=contract["time_status"],
                completeness=contract["completeness"],
                truncated=contract["truncated"],
                partial_reason=contract["partial_reason"], temporal=False))
            continue
        contract = _contract(payload, role=role, key=key,
                             reject_truncation=True)
        if contract["completeness"] != "complete":
            layer_status[ROLE_LAYER[role]] = "incomplete"
        inputs.append(_input_entry(
            role, path, rows=len(contract["rows"]),
            version=contract["version"],
            version_status=contract["version_status"],
            as_of=contract["as_of"], observed_at=contract["observed_at"],
            time_status=contract["time_status"],
            completeness=contract["completeness"],
            truncated=contract["truncated"],
            partial_reason=contract["partial_reason"]))
    if abc_result:
        for item in abc_result["report"]["inputs"]:
            inputs.append(_input_entry(
                item["role"], item["path"], rows=item["row_count"],
                version=item["version"], as_of=item.get("as_of"),
                time_status=item.get("time_status"),
                source=item.get("source", "frozen_workbook"),
                temporal=item["role"] == "C"))
    else:
        for role in ("A", "B", "C"):
            inputs.append(_input_entry(
                role, None, status="not_provided",
                reason="frozen_abc_not_provided",
                temporal=role == "C"))
    return inputs, layer_status


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline saved-response supply pipeline")
    parser.add_argument("--delivery-json")
    parser.add_argument("--mapping-json")
    parser.add_argument("--audit-json", action="append", default=[])
    parser.add_argument("--status-json", action="append", default=[])
    parser.add_argument("--so-json")
    parser.add_argument("--production-json")
    parser.add_argument("--inventory-json")
    parser.add_argument("--transit-json")
    parser.add_argument("--receipt-json")
    parser.add_argument("--approved-items-json")
    parser.add_argument("--a-workbook")
    parser.add_argument("--b-workbook")
    parser.add_argument("--c-workbook")
    parser.add_argument("--a-version")
    parser.add_argument("--b-version")
    parser.add_argument("--c-version")
    parser.add_argument("--c-declared-b-version")
    parser.add_argument("--a-sha256")
    parser.add_argument("--b-sha256")
    parser.add_argument("--c-sha256")
    parser.add_argument("--a-rows", type=int)
    parser.add_argument("--b-rows", type=int)
    parser.add_argument("--c-rows", type=int)
    parser.add_argument("--max-stock-age-days", type=int, default=1)
    parser.add_argument("--as-of")
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--out", required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--allow-stale", action="store_true")
    parser.add_argument("--replay-run")
    args = parser.parse_args(argv)

    if args.inspect:
        as_of = args.as_of or datetime.now(timezone.utc).isoformat()
        state = read_publication(args.out, as_of=as_of,
                                 max_age_seconds=args.max_age_seconds,
                                 allow_stale=args.allow_stale)
        print(json.dumps({key: state.get(key) for key in
                          ("status", "readable", "refresh_status",
                           "warnings", "rows")},
                         ensure_ascii=False))
        return 0 if state.get("status") != "corrupted" \
            and state.get("status") != "incompatible_version" else 1
    if args.replay_run:
        try:
            return replay_run(args.replay_run, args.out, as_of=args.as_of)
        except Exception as exc:  # noqa: BLE001
            print("FAIL replay: %s" % exc, file=sys.stderr)
            return 1

    if not args.delivery_json:
        parser.error("--delivery-json is required unless --inspect/--replay-run")
    if not args.as_of:
        parser.error("--as-of is required unless --inspect")
    abc_flags = [args.a_workbook, args.b_workbook, args.c_workbook]
    if any(abc_flags) and not all(abc_flags):
        parser.error("--a-workbook/--b-workbook/--c-workbook must be provided together")
    if all(abc_flags) and not all((args.a_version, args.b_version, args.c_version)):
        parser.error("--a-version/--b-version/--c-version are required with A/B/C")

    try:
        delivery = _load(args.delivery_json)
        mapping = _load(args.mapping_json) if args.mapping_json else None
        audits = _load_many(args.audit_json)
        statuses = _load_many(args.status_json)
        approved_items = _rows(args.approved_items_json, "items")
        abc_result = None
        abc_inventory = []
        if all(abc_flags):
            expected = {}
            for letter, digest, count in (
                    ("a", args.a_sha256, args.a_rows),
                    ("b", args.b_sha256, args.b_rows),
                    ("c", args.c_sha256, args.c_rows)):
                rule = {}
                if digest:
                    rule["sha256"] = digest
                if count is not None:
                    rule["rows"] = count
                if rule:
                    expected[letter] = rule
            abc_result = load_frozen_abc(
                args.a_workbook, args.b_workbook, args.c_workbook,
                as_of=_as_date(args.as_of), a_version=args.a_version,
                b_version=args.b_version, c_version=args.c_version,
                c_declared_b_version=args.c_declared_b_version,
                max_stock_age_days=args.max_stock_age_days,
                expected=expected or None, as_of_time=args.as_of)
            abc_inventory = abc_result["inventory"]
            approved_items = list(approved_items or []) + abc_result["approved_items"]
        inputs, layer_status = _build_inputs(
            args, delivery, audits, statuses, args.mapping_json, abc_result)
        result = run_pipeline(
            delivery=delivery, mappings=mapping, audits=audits, statuses=statuses,
            as_of=args.as_of,
            so_balances=_rows(args.so_json, "balances"),
            production=_rows(args.production_json, "production"),
            inventory=_rows(args.inventory_json, "inventory"),
            abc_inventory=abc_inventory,
            transit=_rows(args.transit_json, "transit"),
            receipts=_rows(args.receipt_json, "receipts"),
            approved_items=approved_items,
            max_age_seconds=args.max_age_seconds,
            layer_status=layer_status)
        freshness = source_freshness(inputs, as_of=args.as_of,
                                     max_age_seconds=args.max_age_seconds)
        if result["full"].get("freshness"):
            freshness["row_level"] = result["full"]["freshness"]["summary"]
        effective_argv = list(argv) if argv is not None else sys.argv[1:]
        published = publish(
            args.out, full_result=result["full"],
            position_result=result["position"], inputs=inputs,
            pipeline_as_of=args.as_of, rerun_argv=effective_argv,
            effective_args=vars(args),
            abc_report=(abc_result or {}).get("report"),
            max_age_seconds=args.max_age_seconds, freshness=freshness)
    except Exception as exc:  # noqa: BLE001
        _write_attempt(args.out, exc)
        print("FAIL pipeline failed, latest kept: %s" % exc, file=sys.stderr)
        return 1
    summary = published["manifest"]["output_summary"]
    print("OK pipeline: rows=%s unknown=%s -> %s"
          % (summary["full_supply_facts_rows"], summary["unknown_rows"],
             published["run_dir"]))
    return 0


def replay_run(run_dir, out, *, as_of=None):
    """Re-run from the frozen input copies, verifying their bytes first."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest.get("inputs") or ():
        frozen = item.get("frozen_path")
        if not frozen:
            continue
        path = run_dir / frozen
        if not path.is_file():
            raise ValueError("frozen input missing: " + frozen)
        expected = item.get("frozen_sha256") or item.get("sha256")
        if expected and _sha256(path) != expected:
            raise ValueError("frozen input hash mismatch: " + frozen)
    template = (manifest.get("rerun") or {}).get("argv")
    if not template:
        raise ValueError("manifest has no replay argv")
    resolved = [part.replace("{run_dir}", str(run_dir))
                    .replace("{out}", str(out)) for part in template]
    if as_of:
        if "--as-of" in resolved:
            resolved[resolved.index("--as-of") + 1] = as_of
        else:
            resolved += ["--as-of", as_of]
    return main(resolved)


def _as_date(as_of):
    parsed = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of must be an aware timestamp")
    return parsed.date().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
