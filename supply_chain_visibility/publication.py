# -*- coding: utf-8 -*-
"""Verified, atomic publication for supply facts.

One run directory contains the primary Parquet facts file, its JSON trace copy,
the independent supply_position dataset, the timeline trace and one manifest.
Every dataset is read back and compared field by field before ``latest.json``
is switched. Failures keep the previous pointer and record ``last_attempt``.

No network, no business writes, no credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from collections import Counter

from supply_chain_visibility.full_supply_facts import (
    IMPLEMENTATION_VERSION as FULL_IMPLEMENTATION,
    QTY_FIELDS,
    RULE_VERSION as FULL_RULE,
    SCHEMA_VERSION as FULL_SCHEMA,
    _iso,
    _qty,
    _time_parts,
    assess_freshness,
    assess_stage_freshness,
)
from supply_chain_visibility.supply_position import (
    IMPLEMENTATION_VERSION as POSITION_IMPLEMENTATION,
    QUANTITIES as POSITION_QUANTITIES,
    RULE_VERSION as POSITION_RULE,
    VERSION as POSITION_SCHEMA,
    position_table,
)

PUBLICATION_SCHEMA = "supply-publication/v7"
TARGET_SUMMARY_SCHEMA = "supply-target-summary/v1"
FULL_KEY = ("item_code", "uom", "warehouse", "purpose", "tt_sku", "branch",
            "market", "product_form")
FULL_STRING_COLUMNS = (
    "item_code", "uom", "warehouse", "purpose", "tt_sku", "branch",
    "market", "product_form", "pool",
    "scope", "coverage", "next_node", "inventory_as_of_raw",
    "inventory_time_status", "inventory_freshness",
    "inventory_observed_uom", "inventory_inclusion_status",
    "attribution_status", "abc_identity_source", "order_eligibility",
    "receipt_basis",
    "available_date_raw", "available_date_time_status", "date_confidence",
    "available_date_kind",
)
FULL_DECIMAL_COLUMNS = tuple(QTY_FIELDS)
FULL_TIME_COLUMNS = ("inventory_as_of", "available_date")
FULL_JSON_LIST_COLUMNS = ("stage_quantities", "unknown_reasons", "sources",
                          "alerts", "b_units", "order_blockers")
FULL_JSON_DICT_COLUMNS = ("source_status",)
FULL_BOOL_COLUMNS = ("forecast_connected", "netting_ready", "auto_order",
                     "inventory_current_available", "inventory_time_proven")
FULL_INT_COLUMNS = ("inventory_date_age_days",)

TARGET_KEY = FULL_KEY
BUSINESS_CONFLICT_REASONS = (
    "source_payload_conflict", "receipt_before_signed",
    "time_order_conflict", "stage_regression",
    "same_stage_quantity_conflict")
STAGE_KEY = ("item_code", "uom", "warehouse", "purpose", "tt_sku", "branch",
             "stage", "stage_fact_id")
STAGE_STRING_COLUMNS = (
    "item_code", "uom", "warehouse", "purpose", "tt_sku", "branch",
    "market", "product_form", "pool", "scope", "stage",
    "doc_type", "doc_name", "doc_line", "batch_id",
    "stage_fact_id", "physical_lineage_id", "lineage_status", "payload_hash",
    "lineage_namespace", "lineage_key",
    "inclusion_proof", "qty_status", "confidence",
    "stage_measured_qty", "same_stage_reconciliation_status",
    "inventory_freshness", "attribution_status",
    "counted_reason", "observed_at_raw", "observed_at_time_status",
    "eta_raw", "eta_time_status", "available_at_raw",
    "available_at_time_status", "signed_at_raw", "signed_at_time_status",
    "received_at_raw", "received_at_time_status", "overlap_status",
    "inventory_inclusion_status", "owner_status", "source_status",
)
STAGE_DECIMAL_COLUMNS = ("qty",)
STAGE_TIME_COLUMNS = ("observed_at", "eta", "available_at", "signed_at",
                      "received_at", "actual_at", "expected_at")
STAGE_JSON_LIST_COLUMNS = ("cg_blocking_reasons", "unknown_reasons",
                           "conflicts", "blockers", "payload_hashes",
                           "payload_candidates")
STAGE_JSON_DICT_COLUMNS = ("source_identity", "fact_identity")
STAGE_BOOL_COLUMNS = ("counted_as_supply", "cg_stale", "cg_eligible",
                      "payload_conflict", "evidence_only",
                      "inventory_time_proven")

POSITION_STRING_COLUMNS = ("item_code", "tt_sku", "warehouse", "purpose", "uom",
                           "as_of", "mapping_version", "inventory_inclusion_status",
                           "action", "coverage")
POSITION_FLOAT_COLUMNS = (*POSITION_QUANTITIES, "known_dn_net_qty",
                          "available_stock_qty", "open_order_qty",
                          "in_production_qty")
POSITION_INT_COLUMNS = ("line_count", "unknown_quantity_lines",
                        "return_review_lines")
POSITION_BOOL_COLUMNS = ("netting_ready", "auto_order")
POSITION_JSON_COLUMNS = ("reasons", "tranches")
POSITION_KEY = ("item_code", "tt_sku", "warehouse", "purpose", "uom")

DECIMAL_SCALE = Decimal("0.000001")


class CorruptedPublication(ValueError):
    """The published bytes do not match their manifest."""


class IncompatiblePublication(ValueError):
    """The published schema is not readable by this implementation."""


def _json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _key(row, fields):
    return tuple("" if row.get(name) is None else str(row.get(name))
                 for name in fields)


def _sorted_rows(rows, fields):
    return sorted(rows, key=lambda row: _key(row, fields))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               default=str, sort_keys=False), encoding="utf-8")


def _write_json_atomic(path, payload):
    temporary = path.with_name(".tmp-" + uuid.uuid4().hex)
    _write_json(temporary, payload)
    os.replace(temporary, path)


def _safe_name(value):
    text = "".join(ch if ch.isalnum() or ch in "-_." else "_"
                   for ch in str(value))
    return text[:60] or "input"


def _freeze_inputs(inputs, tmp_dir):
    """Copy every participating input into the run's private immutable inputs/.

    ``not_provided`` inputs are optional sources that never took part. Anything
    else participated in the computation, so a missing path, a missing file, a
    changed digest or a copy failure aborts the publication before latest.json
    can switch.
    """
    frozen_dir = Path(tmp_dir) / "inputs"
    frozen_dir.mkdir(parents=True, exist_ok=True)
    mapping = {}
    frozen = []
    for index, item in enumerate(inputs or ()):
        if item.get("status") == "not_provided":
            continue
        path = item.get("path")
        role = item.get("role")
        if not path:
            raise CorruptedPublication(
                "provided input has no path: " + str(role))
        source = Path(path)
        if not source.is_file():
            raise CorruptedPublication(
                "input missing at publish: %s %s" % (role, source))
        source_digest = _sha256(source)
        if item.get("sha256") and source_digest != item["sha256"]:
            raise CorruptedPublication(
                "input changed while freezing: " + str(path))
        suffix = source.suffix or ".bin"
        name = "%02d_%s%s" % (index, _safe_name(role), suffix)
        destination = frozen_dir / name
        shutil.copy2(source, destination)
        digest = _sha256(destination)
        if digest != source_digest:
            raise CorruptedPublication(
                "input copy mismatch: " + str(path))
        if item.get("sha256") and digest != item["sha256"]:
            raise CorruptedPublication(
                "input changed while freezing: " + str(path))
        item["frozen_path"] = "inputs/" + name
        item["frozen_sha256"] = digest
        item["frozen_size"] = destination.stat().st_size
        mapping[os.path.normcase(os.path.abspath(str(source)))] = (
            "{run_dir}/inputs/" + name)
        frozen.append({"role": item.get("role"), "original_path": str(path),
                       "frozen_path": "inputs/" + name, "sha256": digest})
    return mapping, frozen


def _freeze_argv(argv, mapping, out_value):
    if not argv:
        return None
    frozen = []
    replace_out = False
    for arg in argv:
        if replace_out:
            frozen.append("{out}")
            replace_out = False
            continue
        if arg == "--out":
            frozen.append(arg)
            replace_out = True
            continue
        key = os.path.normcase(os.path.abspath(str(arg)))
        frozen.append(mapping.get(key, arg))
    return frozen


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _resolved_template(argv, run_dir, out):
    if not argv:
        return None
    return [part.replace("{run_dir}", str(run_dir)).replace("{out}", str(out))
            for part in argv]


def _powershell_command(argv, run_dir, out):
    resolved = _resolved_template(argv, run_dir, out)
    if not resolved:
        return None
    args = list(resolved)
    if args and (args[0].endswith("supply_pipeline.py")
                 or args[0].endswith("supply_pipeline")):
        args = args[1:]
    return "python -m supply_chain_visibility.supply_pipeline " + " ".join(
        _ps_quote(arg) for arg in args)


def canonical_full_row(row):
    out = {}
    for name in FULL_STRING_COLUMNS:
        out[name] = row.get(name)
    for name in FULL_DECIMAL_COLUMNS:
        out[name] = _qty(row.get(name), signed=(name == "dn_net_qty"))
    for name in FULL_TIME_COLUMNS:
        out[name] = _iso(row.get(name))
    for name in FULL_BOOL_COLUMNS:
        out[name] = bool(row.get(name))
    for name in FULL_INT_COLUMNS:
        value = row.get(name)
        out[name] = None if value is None else int(value)
    for name in FULL_JSON_LIST_COLUMNS:
        out[name] = _json_copy(row.get(name) or [])
    for name in FULL_JSON_DICT_COLUMNS:
        out[name] = _json_copy(row.get(name) or {})
    return out


def canonical_full_rows(rows):
    return _sorted_rows([canonical_full_row(row) for row in rows], FULL_KEY)


def target_summary_schema():
    import pyarrow as pa
    return pa.schema([
        *[(name, pa.string()) for name in FULL_STRING_COLUMNS],
        *[(name, pa.decimal128(38, 6)) for name in FULL_DECIMAL_COLUMNS],
        *[(name, pa.timestamp("us", tz="UTC")) for name in FULL_TIME_COLUMNS],
        *[(name, pa.bool_()) for name in FULL_BOOL_COLUMNS],
        *[(name, pa.int64()) for name in FULL_INT_COLUMNS],
        *[(name, pa.string()) for name in
          (*FULL_JSON_LIST_COLUMNS, *FULL_JSON_DICT_COLUMNS)],
    ])


def _full_record(row):
    record = {}
    for name in FULL_STRING_COLUMNS:
        record[name] = row.get(name)
    for name in FULL_DECIMAL_COLUMNS:
        value = row.get(name)
        if value is None:
            record[name] = None
        else:
            with localcontext() as context:
                context.prec = 38
                record[name] = Decimal(value).quantize(DECIMAL_SCALE)
    for name in FULL_TIME_COLUMNS:
        value = row.get(name)
        record[name] = datetime.fromisoformat(value) if value else None
    for name in FULL_BOOL_COLUMNS:
        record[name] = bool(row.get(name))
    for name in FULL_INT_COLUMNS:
        value = row.get(name)
        record[name] = None if value is None else int(value)
    for name in (*FULL_JSON_LIST_COLUMNS, *FULL_JSON_DICT_COLUMNS):
        record[name] = json.dumps(row.get(name), ensure_ascii=False,
                                  sort_keys=True)
    return record


def _canonical_from_parquet(record):
    out = {}
    for name in FULL_STRING_COLUMNS:
        out[name] = record.get(name)
    for name in FULL_DECIMAL_COLUMNS:
        value = record.get(name)
        out[name] = _qty(value, signed=(name == "dn_net_qty")) if value is not None else None
    for name in FULL_TIME_COLUMNS:
        value = record.get(name)
        if value is None:
            out[name] = None
        elif value.tzinfo is None:
            raise CorruptedPublication("naive timestamp in parquet: " + name)
        else:
            out[name] = value.astimezone(timezone.utc).isoformat()
    for name in FULL_BOOL_COLUMNS:
        out[name] = bool(record.get(name))
    for name in FULL_INT_COLUMNS:
        out[name] = record.get(name)
    for name in FULL_JSON_LIST_COLUMNS:
        raw = record.get(name)
        out[name] = json.loads(raw) if raw else []
    for name in FULL_JSON_DICT_COLUMNS:
        raw = record.get(name)
        out[name] = json.loads(raw) if raw else {}
    return out


def target_summary_table(rows):
    import pyarrow as pa
    records = [_full_record(row) for row in rows]
    return pa.Table.from_pylist(records, schema=target_summary_schema())


def canonical_stage_row(row):
    out = {}
    for name in STAGE_STRING_COLUMNS:
        out[name] = row.get(name)
    for name in STAGE_DECIMAL_COLUMNS:
        out[name] = _qty(row.get(name), signed=True)
    for name in STAGE_TIME_COLUMNS:
        out[name] = _iso(row.get(name))
    for name in STAGE_BOOL_COLUMNS:
        out[name] = bool(row.get(name))
    for name in STAGE_JSON_LIST_COLUMNS:
        value = _json_copy(row.get(name) or [])
        out[name] = value if isinstance(value, list) else []
    for name in STAGE_JSON_DICT_COLUMNS:
        value = _json_copy(row.get(name) or {})
        out[name] = value if isinstance(value, dict) else {}
    return out


def canonical_stage_rows(rows):
    return _sorted_rows([canonical_stage_row(row) for row in rows], STAGE_KEY)


def stage_schema():
    import pyarrow as pa
    return pa.schema([
        *[(name, pa.string()) for name in STAGE_STRING_COLUMNS],
        *[(name, pa.decimal128(38, 6)) for name in STAGE_DECIMAL_COLUMNS],
        *[(name, pa.timestamp("us", tz="UTC")) for name in STAGE_TIME_COLUMNS],
        *[(name, pa.bool_()) for name in STAGE_BOOL_COLUMNS],
        *[(name, pa.string()) for name in
          (*STAGE_JSON_LIST_COLUMNS, *STAGE_JSON_DICT_COLUMNS)],
    ])


def full_schema():
    return stage_schema()


def _stage_record(row):
    record = {}
    for name in STAGE_STRING_COLUMNS:
        record[name] = row.get(name)
    for name in STAGE_DECIMAL_COLUMNS:
        value = row.get(name)
        if value is None:
            record[name] = None
        else:
            with localcontext() as context:
                context.prec = 38
                record[name] = Decimal(value).quantize(DECIMAL_SCALE)
    for name in STAGE_TIME_COLUMNS:
        value = row.get(name)
        record[name] = datetime.fromisoformat(value) if value else None
    for name in STAGE_BOOL_COLUMNS:
        record[name] = bool(row.get(name))
    for name in (*STAGE_JSON_LIST_COLUMNS, *STAGE_JSON_DICT_COLUMNS):
        record[name] = json.dumps(row.get(name), ensure_ascii=False,
                                  sort_keys=True)
    return record


def _stage_from_parquet(record):
    out = {}
    for name in STAGE_STRING_COLUMNS:
        out[name] = record.get(name)
    for name in STAGE_DECIMAL_COLUMNS:
        value = record.get(name)
        out[name] = _qty(value, signed=True) if value is not None else None
    for name in STAGE_TIME_COLUMNS:
        value = record.get(name)
        if value is None:
            out[name] = None
        elif value.tzinfo is None:
            raise CorruptedPublication("naive timestamp in parquet: " + name)
        else:
            out[name] = value.astimezone(timezone.utc).isoformat()
    for name in STAGE_BOOL_COLUMNS:
        out[name] = bool(record.get(name))
    for name in STAGE_JSON_LIST_COLUMNS:
        raw = record.get(name)
        out[name] = json.loads(raw) if raw else []
    for name in STAGE_JSON_DICT_COLUMNS:
        raw = record.get(name)
        out[name] = json.loads(raw) if raw else {}
    return out


def stage_table(rows):
    import pyarrow as pa
    records = [_stage_record(row) for row in rows]
    return pa.Table.from_pylist(records, schema=stage_schema())


def full_table(rows):
    return stage_table(rows)


def canonical_position_row(row):
    out = {}
    for name in POSITION_STRING_COLUMNS:
        out[name] = row.get(name)
    for name in POSITION_FLOAT_COLUMNS:
        out[name] = row.get(name)
    for name in POSITION_INT_COLUMNS:
        out[name] = row.get(name)
    for name in POSITION_BOOL_COLUMNS:
        out[name] = bool(row.get(name))
    for name in POSITION_JSON_COLUMNS:
        out[name] = _json_copy(row.get(name) or [])
    return out


def canonical_position_rows(rows):
    return [canonical_position_row(row) for row in rows]


def _position_from_parquet(record):
    out = {}
    for name in POSITION_STRING_COLUMNS:
        out[name] = record.get(name)
    for name in POSITION_FLOAT_COLUMNS:
        out[name] = record.get(name)
    for name in POSITION_INT_COLUMNS:
        out[name] = record.get(name)
    for name in POSITION_BOOL_COLUMNS:
        out[name] = bool(record.get(name))
    for name in POSITION_JSON_COLUMNS:
        raw = record.get(name + "_json")
        out[name] = json.loads(raw) if raw else []
    return out


def _assert_unique(rows, fields, message):
    seen = set()
    for row in rows:
        key = _key(row, fields)
        if key in seen:
            raise CorruptedPublication(message + ": " + "|".join(key))
        seen.add(key)


def _compare_rows(left, right, message):
    if len(left) != len(right):
        raise CorruptedPublication("%s row count %s != %s"
                                   % (message, len(left), len(right)))
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            keys = sorted(set(a) | set(b))
            diff = [key for key in keys if a.get(key) != b.get(key)]
            raise CorruptedPublication("%s row %s differs: %s"
                                       % (message, index, ",".join(diff)))


def _verify_full(root, json_rows):
    import pyarrow.parquet as pq
    path = root / "supply_target_summary.parquet"
    if not path.is_file():
        raise CorruptedPublication("missing supply_target_summary.parquet")
    table = pq.read_table(path)
    if not table.schema.equals(target_summary_schema()):
        raise CorruptedPublication("supply_target_summary parquet schema mismatch")
    parquet_rows = _sorted_rows(
        [_canonical_from_parquet(record) for record in table.to_pylist()],
        FULL_KEY)
    _assert_unique(parquet_rows, FULL_KEY, "duplicate target summary key")
    _compare_rows(json_rows, parquet_rows, "supply_target_summary json/parquet")
    return len(parquet_rows)


def _verify_stage(root, json_rows):
    import pyarrow.parquet as pq
    path = root / "full_supply_facts.parquet"
    if not path.is_file():
        raise CorruptedPublication("missing full_supply_facts.parquet")
    table = pq.read_table(path)
    if not table.schema.equals(stage_schema()):
        raise CorruptedPublication("full_supply_facts parquet schema mismatch")
    parquet_rows = _sorted_rows(
        [_stage_from_parquet(record) for record in table.to_pylist()],
        STAGE_KEY)
    _assert_unique(parquet_rows, STAGE_KEY, "duplicate stage fact key")
    _compare_rows(json_rows, parquet_rows, "full_supply_facts json/parquet")
    return len(parquet_rows)


def _verify_position(root, position_result, json_rows):
    import pyarrow.parquet as pq
    path = root / "supply_position.parquet"
    if not path.is_file():
        raise CorruptedPublication("missing supply_position.parquet")
    expected = position_table(position_result)
    table = pq.read_table(path)
    if not table.schema.equals(expected.schema):
        raise CorruptedPublication("supply_position parquet schema mismatch")
    parquet_rows = [_position_from_parquet(record) for record in table.to_pylist()]
    _compare_rows(json_rows, parquet_rows, "supply_position json/parquet")
    return len(parquet_rows)


def _verify_timeline(root, json_rows):
    path = root / "timeline.json"
    if not path.is_file():
        raise CorruptedPublication("missing timeline.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    _compare_rows(json_rows, loaded, "timeline json")
    _assert_unique(loaded, FULL_KEY, "duplicate timeline target key")
    return len(loaded)


def _dataset_entry(*, file, fmt, dataset, role, schema_version, rule_version,
                   implementation_version, grain, unique_key, rows, sha256,
                   source_versions=None, source_hashes=None, as_of=None,
                   observed_at=None, freshness=None, stale=False, stats=None,
                   relations=None, extra=None):
    entry = {
        "file": file,
        "format": fmt,
        "dataset": dataset,
        "role": role,
        "schema_version": schema_version,
        "rule_version": rule_version,
        "implementation_version": implementation_version,
        "grain": grain,
        "unique_key": list(unique_key),
        "rows": rows,
        "sha256": sha256,
        "source_versions": source_versions or {},
        "source_hashes": source_hashes or {},
        "as_of": as_of,
        "observed_at": observed_at,
        "freshness": freshness,
        "stale": stale,
        "stats": stats or {},
        "relations": relations or [],
    }
    if extra:
        entry.update(extra)
    return entry


def source_freshness(inputs, *, as_of, max_age_seconds):
    now, _, _ = _time_parts(as_of)
    if now is None:
        raise ValueError("as_of must be an aware timestamp")
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) \
            or max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be a positive integer")
    sources = []
    for item in inputs or ():
        if item.get("status") == "not_provided":
            continue
        if item.get("temporal") is False:
            # Static reference inputs (mapping / A / B / approved items).
            continue
        value = item.get("observed_at") or item.get("as_of")
        parsed, raw, time_status = _time_parts(value)
        status = "unknown"
        age = None
        if parsed is not None:
            age = (now - parsed).total_seconds()
            if age < 0:
                status = "future"
            elif age > max_age_seconds:
                status = "stale"
            else:
                status = "fresh"
        if item.get("status") in ("partial", "failed", "truncated",
                                  "incomplete"):
            status = "unknown"
        sources.append({"role": item.get("role") or item.get("path"),
                        "time": parsed.isoformat() if parsed else raw,
                        "time_status": time_status, "age_seconds": age,
                        "status": status,
                        "input_status": item.get("status"),
                        "version_status": item.get("version_status"),
                        "completeness": item.get("completeness")})
    if any(source["status"] in ("stale", "future") for source in sources):
        overall = "stale"
    elif any(source["status"] == "unknown" for source in sources):
        overall = "unknown"
    else:
        overall = "fresh"
    return {"status": overall, "sources": sources}


def _business_conflict_stats(stage_rows):
    """Count published conflict facts; these make the run partial, not failed."""
    rows = 0
    reasons = Counter()
    for row in stage_rows:
        found = {reason for reason in (row.get("conflicts") or ())
                 if reason in BUSINESS_CONFLICT_REASONS}
        if row.get("payload_conflict"):
            found.add("source_payload_conflict")
        if found:
            rows += 1
            reasons.update(found)
    return rows, dict(sorted(reasons.items()))


def build_manifest(*, run_id, run_dir, pipeline_as_of, inputs, full_result,
                   position_result, position_rows, timeline_rows,
                   files, freshness, rerun_argv, rerun_template,
                   effective_args, frozen_inputs, max_age_seconds,
                   abc_report=None, stage_rows=None, target_rows=None):
    stage_rows = list(stage_rows or [])
    target_rows = list(target_rows or [])
    full_summary = full_result["summary"]
    position_report = position_result.get("report") or {}
    observed_values = []
    for item in inputs or ():
        parsed, _, _ = _time_parts(item.get("observed_at") or item.get("as_of"))
        if parsed is not None:
            observed_values.append(parsed)
    observed_at = max(observed_values).isoformat() if observed_values else None
    stale = freshness.get("status") != "fresh"
    abc_versions = {}
    for item in inputs or ():
        if item.get("role") in ("A", "B", "C"):
            abc_versions[item["role"]] = {
                "version": item.get("version"),
                "sha256": item.get("sha256"),
                "row_count": item.get("rows"),
                "as_of": item.get("as_of"),
                "time_status": item.get("time_status"),
            }
    if abc_report:
        abc_versions.update({
            "version_relation": abc_report.get("version_relation"),
            "b_version": abc_report.get("b_version"),
            "c_declared_b_version": abc_report.get("c_declared_b_version"),
            "c_dependency_source": abc_report.get("c_dependency_source"),
            "input_rows_total": abc_report.get("input_rows_total"),
            "a_input_rows": abc_report.get("a_input_rows"),
            "a_active_items": abc_report.get("a_active_items"),
            "b_input_rows": abc_report.get("b_input_rows"),
            "b_unique_item_pool": abc_report.get("b_unique_item_pool"),
            "c_input_rows": abc_report.get("c_input_rows"),
        })
    source_versions = {
        "delivery": (position_report.get("source_versions") or {}),
        "position_rule_version": POSITION_RULE,
        "position_implementation_version": POSITION_IMPLEMENTATION,
        "full_facts_rule_version": FULL_RULE,
        "full_facts_implementation_version": FULL_IMPLEMENTATION,
        "ABC": abc_versions,
    }
    source_hashes = {item.get("role", "input"): item.get("sha256")
                     for item in inputs or () if item.get("sha256")}
    failed_inputs = [item.get("role") for item in inputs or ()
                     if item.get("status") == "failed"]
    closure_missing = [item.get("role") for item in inputs or ()
                       if item.get("required_for_closure")
                       and item.get("status") == "not_provided"]
    version_unknown = [item.get("role") for item in inputs or ()
                       if item.get("temporal") is not False
                       and item.get("status") != "not_provided"
                       and item.get("version_status") == "missing"]
    contract_incomplete = [item.get("role") for item in inputs or ()
                           if item.get("completeness") in ("partial",
                                                           "incomplete")]
    partial_reasons = sorted({
        reason for item in inputs or ()
        for reason in (item.get("partial_reason") or [])})
    business_conflict_rows, business_conflict_reasons = (
        _business_conflict_stats(stage_rows))
    if business_conflict_rows:
        partial_reasons = sorted(set(partial_reasons) | {"business_conflict"})
    partial = bool(full_summary.get("unknown_rows")) or bool(failed_inputs) \
        or bool(closure_missing) or bool(version_unknown) \
        or bool(contract_incomplete) or bool(business_conflict_rows)
    position_unknown_rows = sum(
        1 for row in position_rows
        if row.get("unknown_quantity_lines")
        or (row.get("unresolved_qty") not in (None, 0)))
    position_partial = position_unknown_rows > 0 or bool(
        position_report.get("input_lines") is not None
        and position_report.get("input_lines")
        != position_report.get("accounted_lines"))
    position_stats = {
        "partial": position_partial,
        "unknown_rows": position_unknown_rows,
        "unknown_reason_distribution": position_report.get("outcomes"),
        "failed_inputs": failed_inputs,
    }
    full_stats = {
        "partial": partial,
        "unknown_rows": full_summary.get("unknown_rows"),
        "unknown_reason_distribution":
            full_summary.get("unknown_reason_distribution"),
        "attribution_distribution": full_summary.get("attribution_distribution"),
        "by_coverage": full_summary.get("by_coverage"),
        "inventory_stale_rows": full_summary.get("inventory_stale_rows"),
        "failed_inputs": failed_inputs,
        "closure_missing_inputs": closure_missing,
    }
    stage_stats = {
        "partial": partial,
        "rows": len(stage_rows),
        "stage_summary": full_result.get("stage_summary"),
        "stage_freshness": full_result.get("stage_freshness"),
        "business_conflict_rows": business_conflict_rows,
        "business_conflict_reasons": business_conflict_reasons,
        "failed_inputs": failed_inputs,
    }
    datasets = {
        "full_supply_facts.parquet": _dataset_entry(
            file="full_supply_facts.parquet", fmt="parquet",
            dataset="full_supply_facts", role="primary",
            schema_version=FULL_SCHEMA, rule_version=FULL_RULE,
            implementation_version=FULL_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku×branch×stage×doc_line/batch_id",
            unique_key=STAGE_KEY, rows=len(stage_rows),
            sha256=files["full_supply_facts.parquet"],
            source_versions=source_versions, source_hashes=source_hashes,
            as_of=pipeline_as_of, observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats=stage_stats,
            relations=[{"to": "full_supply_facts.json", "type": "trace_copy"},
                       {"to": "supply_target_summary.parquet",
                        "type": "compatible_summary"},
                       {"to": "supply_position.parquet",
                        "type": "input_dataset"}],
            extra={"decimal_columns": list(STAGE_DECIMAL_COLUMNS),
                   "decimal_scale": 6,
                   "time_columns": list(STAGE_TIME_COLUMNS),
                   "time_timezone": "UTC",
                   "bool_columns": list(STAGE_BOOL_COLUMNS),
                   "json_columns": list(STAGE_JSON_LIST_COLUMNS
                                        + STAGE_JSON_DICT_COLUMNS),
                   "counted_as_supply":
                       "at most one current stage per proven physical batch; "
                       "open_po is reconciliation only",
                   "null_policy": "null means unknown; zero is a separate value"}),
        "full_supply_facts.json": _dataset_entry(
            file="full_supply_facts.json", fmt="json",
            dataset="full_supply_facts", role="trace",
            schema_version=FULL_SCHEMA, rule_version=FULL_RULE,
            implementation_version=FULL_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku×branch×stage×doc_line/batch_id",
            unique_key=STAGE_KEY, rows=len(stage_rows),
            sha256=files["full_supply_facts.json"],
            source_versions=source_versions, source_hashes=source_hashes,
            as_of=pipeline_as_of, observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats=stage_stats,
            relations=[{"to": "full_supply_facts.parquet",
                        "type": "trace_of_primary"}],
            extra={"decimal_columns": list(STAGE_DECIMAL_COLUMNS),
                   "decimal_scale": 6,
                   "time_columns": list(STAGE_TIME_COLUMNS),
                   "time_timezone": "UTC",
                   "bool_columns": list(STAGE_BOOL_COLUMNS),
                   "json_columns": list(STAGE_JSON_LIST_COLUMNS
                                        + STAGE_JSON_DICT_COLUMNS),
                   "null_policy": "null means unknown; zero is a separate value"}),
        "supply_target_summary.parquet": _dataset_entry(
            file="supply_target_summary.parquet", fmt="parquet",
            dataset="supply_target_summary", role="compatible",
            schema_version=TARGET_SUMMARY_SCHEMA, rule_version=FULL_RULE,
            implementation_version=FULL_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku×branch×market×product_form",
            unique_key=FULL_KEY, rows=len(target_rows),
            sha256=files["supply_target_summary.parquet"],
            source_versions=source_versions, source_hashes=source_hashes,
            as_of=pipeline_as_of, observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats=full_stats,
            relations=[{"to": "supply_target_summary.json",
                        "type": "trace_copy"},
                       {"to": "full_supply_facts.parquet",
                        "type": "compatible_view"}],
            extra={"decimal_columns": list(FULL_DECIMAL_COLUMNS),
                   "decimal_scale": 6,
                   "time_columns": list(FULL_TIME_COLUMNS),
                   "time_timezone": "UTC",
                   "int_columns": list(FULL_INT_COLUMNS),
                   "json_columns": list(FULL_JSON_LIST_COLUMNS
                                        + FULL_JSON_DICT_COLUMNS),
                   "null_policy": "null means unknown; zero is a separate value"}),
        "supply_target_summary.json": _dataset_entry(
            file="supply_target_summary.json", fmt="json",
            dataset="supply_target_summary", role="trace",
            schema_version=TARGET_SUMMARY_SCHEMA, rule_version=FULL_RULE,
            implementation_version=FULL_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku×branch×market×product_form",
            unique_key=FULL_KEY, rows=len(target_rows),
            sha256=files["supply_target_summary.json"],
            source_versions=source_versions, source_hashes=source_hashes,
            as_of=pipeline_as_of, observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats=full_stats,
            relations=[{"to": "supply_target_summary.parquet",
                        "type": "trace_of_primary"}],
            extra={"decimal_columns": list(FULL_DECIMAL_COLUMNS),
                   "decimal_scale": 6,
                   "time_columns": list(FULL_TIME_COLUMNS),
                   "time_timezone": "UTC",
                   "int_columns": list(FULL_INT_COLUMNS),
                   "json_columns": list(FULL_JSON_LIST_COLUMNS
                                        + FULL_JSON_DICT_COLUMNS),
                   "null_policy": "null means unknown; zero is a separate value"}),
        "supply_position.parquet": _dataset_entry(
            file="supply_position.parquet", fmt="parquet",
            dataset="supply_position", role="independent",
            schema_version=POSITION_SCHEMA, rule_version=POSITION_RULE,
            implementation_version=POSITION_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku",
            unique_key=POSITION_KEY, rows=len(position_rows),
            sha256=files["supply_position.parquet"],
            source_versions=position_report.get("source_versions") or {},
            source_hashes=source_hashes, as_of=pipeline_as_of,
            observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats=position_stats,
            relations=[{"to": "full_supply_facts.parquet",
                        "type": "input_dataset"}],
            extra={"quantity_contract":
                   "float64 per supply-position/v1 (independent dataset); "
                   "not the full facts decimal contract",
                   "json_columns": ["reasons", "tranches"],
                   "time_columns": ["as_of (string per supply-position/v1)"],
                   "null_policy": "null means unknown; zero is a separate value"}),
        "supply_position.json": _dataset_entry(
            file="supply_position.json", fmt="json",
            dataset="supply_position", role="trace",
            schema_version=POSITION_SCHEMA, rule_version=POSITION_RULE,
            implementation_version=POSITION_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku",
            unique_key=POSITION_KEY, rows=len(position_rows),
            sha256=files["supply_position.json"],
            source_versions=position_report.get("source_versions") or {},
            source_hashes=source_hashes, as_of=pipeline_as_of,
            observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats=position_stats,
            relations=[{"to": "supply_position.parquet",
                        "type": "trace_of_primary"}],
            extra={"quantity_contract":
                   "float64 per supply-position/v1 (independent dataset)",
                   "json_columns": ["reasons", "tranches"],
                   "time_columns": ["as_of (string per supply-position/v1)"],
                   "null_policy": "null means unknown; zero is a separate value"}),
        "timeline.json": _dataset_entry(
            file="timeline.json", fmt="json", dataset="timeline",
            role="trace", schema_version=FULL_SCHEMA, rule_version=FULL_RULE,
            implementation_version=FULL_IMPLEMENTATION,
            grain="item_code×uom×warehouse×purpose×tt_sku×branch×market×product_form",
            unique_key=FULL_KEY, rows=len(timeline_rows),
            sha256=files["timeline.json"],
            source_versions=source_versions, source_hashes=source_hashes,
            as_of=pipeline_as_of, observed_at=observed_at,
            freshness=freshness, stale=stale,
            stats={"partial": partial,
                   "unknown_rows": full_summary.get("unknown_rows"),
                   "unknown_reason_distribution":
                       full_summary.get("unknown_reason_distribution"),
                   "failed_inputs": failed_inputs},
            relations=[{"to": "full_supply_facts.parquet",
                        "type": "derived_from"}],
            extra={"forecast_connected": False,
                   "decimal_columns": ["stages[].qty (normalized string)"],
                   "time_columns": ["stages[].date (UTC ISO or null)",
                                    "as_of (UTC ISO)"],
                   "time_timezone": "UTC",
                   "null_policy": "null means unknown; zero is a separate value"}),
    }
    input_rows_total = sum(int(item.get("rows") or 0) for item in inputs or ())
    manifest = {
        "schema_version": PUBLICATION_SCHEMA,
        "run_id": run_id,
        "pipeline_as_of": pipeline_as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "forecast_connected": False,
        "netting_ready": False,
        "auto_order": False,
        "publish_status": "succeeded",
        "partial_reason": partial_reasons,
        "business_conflict_rows": business_conflict_rows,
        "business_conflict_reasons": business_conflict_reasons,
        "max_age_seconds": max_age_seconds,
        "inputs": inputs,
        "input_summary": {
            "rows_total": input_rows_total,
            "by_role": {item.get("role"): int(item.get("rows") or 0)
                        for item in inputs or ()},
            "provided": [item.get("role") for item in inputs or ()
                         if item.get("status") != "not_provided"],
            "not_provided": [item.get("role") for item in inputs or ()
                             if item.get("status") == "not_provided"],
            "version_unknown": version_unknown,
            "contract_incomplete": contract_incomplete,
            "frozen_inputs": frozen_inputs,
            "provided_count": sum(
                1 for item in inputs or ()
                if item.get("status") != "not_provided"),
            "frozen_count": len(frozen_inputs),
        },
        "output_summary": {
            "full_supply_facts_rows": len(stage_rows),
            "supply_target_summary_rows": len(target_rows),
            "supply_position_rows": len(position_rows),
            "timeline_rows": len(timeline_rows),
            "stage_summary": full_result.get("stage_summary"),
            "stage_unique_key": list(STAGE_KEY),
            "business_conflict_rows": business_conflict_rows,
            "business_conflict_reasons": business_conflict_reasons,
            "by_purpose": full_summary.get("by_purpose"),
            "by_coverage": full_summary.get("by_coverage"),
            "attribution_distribution": full_summary.get("attribution_distribution"),
            "unknown_rows": full_summary.get("unknown_rows"),
            "unknown_reason_distribution":
                full_summary.get("unknown_reason_distribution"),
            "source_reconciliation": full_summary.get("source_reconciliation"),
            "layer_status": full_summary.get("layer_status"),
            "partial": partial,
            "partial_reason": partial_reasons,
            "closure_missing_inputs": closure_missing,
            "failed_inputs": failed_inputs,
            "version_unknown_inputs": version_unknown,
            "contract_incomplete_inputs": contract_incomplete,
            "cross_layer_total": None,
        },
        "freshness": freshness,
        "datasets": datasets,
        "relations": [
            {"from": "supply_position.parquet", "to": "full_supply_facts.parquet",
             "type": "input_dataset"},
            {"from": "full_supply_facts.json", "to": "full_supply_facts.parquet",
             "type": "trace_copy"},
            {"from": "supply_target_summary.parquet",
             "to": "full_supply_facts.parquet", "type": "compatible_view"},
            {"from": "supply_target_summary.json",
             "to": "supply_target_summary.parquet", "type": "trace_copy"},
            {"from": "timeline.json", "to": "supply_target_summary.parquet",
             "type": "derived_from"},
        ],
        "rerun": {
            "argv": list(rerun_template) if rerun_template else None,
            "command": (("python -m supply_chain_visibility.supply_pipeline "
                         "--replay-run %s --out %s"
                         % (_ps_quote(run_dir),
                            _ps_quote(Path(run_dir).parent.parent / "replay")))
                        if rerun_template else None),
            "effective_args": effective_args or {},
            "frozen_inputs": frozen_inputs or [],
        },
        "versions": {
            "publication": PUBLICATION_SCHEMA,
            "full_supply_facts": FULL_SCHEMA,
            "full_supply_facts_rule": FULL_RULE,
            "full_supply_facts_implementation": FULL_IMPLEMENTATION,
            "supply_target_summary": TARGET_SUMMARY_SCHEMA,
            "supply_position": POSITION_SCHEMA,
            "supply_position_rule": POSITION_RULE,
            "supply_position_implementation": POSITION_IMPLEMENTATION,
        },
    }
    return manifest


def _attempt_payload(core, metadata):
    payload = dict(metadata or {})
    payload.update(core)
    return payload


def publish(out, *, full_result, position_result, inputs, pipeline_as_of,
            rerun_argv=None, rerun_template=None, effective_args=None,
            abc_report=None, max_age_seconds=900, freshness=None,
            extra_manifest=None, attempt_metadata=None):
    """Write a verified run and only then switch latest.json."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    run_id = hashlib.sha1(("%s|%s" % (pipeline_as_of, time.time_ns()))
                          .encode()).hexdigest()[:12]
    run_dir = out / "runs" / ("run-%s-%s"
                              % (time.strftime("%Y%m%d_%H%M%S"), run_id))
    tmp_dir = Path(tempfile.mkdtemp(prefix=".publish-", dir=str(out)))
    renamed = False
    try:
        target_rows = canonical_full_rows(full_result["rows"])
        stage_rows = canonical_stage_rows(full_result.get("stage_rows") or [])
        position_rows = canonical_position_rows(position_result.get("rows") or [])
        timeline_rows = _json_copy((full_result.get("timeline") or {}).get("rows") or [])
        _assert_unique(stage_rows, STAGE_KEY, "duplicate stage fact key")
        _assert_unique(target_rows, FULL_KEY, "duplicate target summary key")
        _assert_unique(position_rows, POSITION_KEY, "duplicate position target key")
        _assert_unique(timeline_rows, FULL_KEY, "duplicate timeline target key")
        files = {}
        paths = {
            "full_supply_facts.json": stage_rows,
            "supply_target_summary.json": target_rows,
            "supply_position.json": position_rows,
            "timeline.json": timeline_rows,
        }
        for name, payload in paths.items():
            path = tmp_dir / name
            _write_json(path, payload)
            files[name] = _sha256(path)
        import pyarrow.parquet as pq
        full_path = tmp_dir / "full_supply_facts.parquet"
        full_table_for_write = stage_table(stage_rows)
        pq.write_table(full_table_for_write, full_path, compression="zstd")
        if not pq.read_table(full_path).equals(full_table_for_write):
            raise CorruptedPublication("full parquet readback mismatch")
        files["full_supply_facts.parquet"] = _sha256(full_path)
        target_path = tmp_dir / "supply_target_summary.parquet"
        target_table_for_write = target_summary_table(target_rows)
        pq.write_table(target_table_for_write, target_path,
                       compression="zstd")
        if not pq.read_table(target_path).equals(target_table_for_write):
            raise CorruptedPublication(
                "target summary parquet readback mismatch")
        files["supply_target_summary.parquet"] = _sha256(target_path)
        position_path = tmp_dir / "supply_position.parquet"
        position_table_for_write = position_table(position_result)
        pq.write_table(position_table_for_write, position_path, compression="zstd")
        if not pq.read_table(position_path).equals(position_table_for_write):
            raise CorruptedPublication("position parquet readback mismatch")
        files["supply_position.parquet"] = _sha256(position_path)
        freshness = freshness or source_freshness(
            inputs, as_of=pipeline_as_of, max_age_seconds=max_age_seconds)
        if full_result.get("freshness") and "row_level" not in freshness:
            freshness["row_level"] = full_result["freshness"]["summary"]
        frozen_map, frozen_inputs = _freeze_inputs(inputs, tmp_dir)
        rerun_template = _freeze_argv(rerun_argv, frozen_map, out)
        manifest = build_manifest(
            run_id=run_id, run_dir=run_dir, pipeline_as_of=pipeline_as_of,
            inputs=inputs, full_result=full_result,
            position_result=position_result, position_rows=position_rows,
            timeline_rows=timeline_rows, files=files, freshness=freshness,
            rerun_argv=rerun_argv, rerun_template=rerun_template,
            effective_args=effective_args, frozen_inputs=frozen_inputs,
            max_age_seconds=max_age_seconds, abc_report=abc_report,
            stage_rows=stage_rows, target_rows=target_rows)
        if extra_manifest:
            manifest.update(extra_manifest)
        _write_json(tmp_dir / "manifest.json", manifest)
        manifest_sha256 = _sha256(tmp_dir / "manifest.json")
        # Full readback and cross-format verification before publishing.
        _verify_stage(tmp_dir, stage_rows)
        _verify_full(tmp_dir, target_rows)
        _verify_position(tmp_dir, position_result, position_rows)
        _verify_timeline(tmp_dir, timeline_rows)
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        if run_dir.exists():
            shutil.rmtree(run_dir)
        tmp_dir.rename(run_dir)
        renamed = True
        pointer = {
            "run_dir": str(run_dir),
            "manifest": str(run_dir / "manifest.json"),
            "manifest_sha256": manifest_sha256,
            "as_of": pipeline_as_of,
            "run_id": run_id,
            "schema_version": PUBLICATION_SCHEMA,
            "full_supply_facts_schema": FULL_SCHEMA,
            "supply_target_summary_schema": TARGET_SUMMARY_SCHEMA,
        }
        latest_tmp = out / ".latest.json.tmp"
        _write_json(latest_tmp, pointer)
        latest_tmp.replace(out / "latest.json")
        try:
            _write_json_atomic(out / "last_attempt.json", _attempt_payload({
                "status": "succeeded", "run_id": run_id,
                "run_dir": str(run_dir),
                "attempted_at": datetime.now(timezone.utc).isoformat()},
                attempt_metadata))
        except OSError:
            pass
        return {"status": "ok", "run_dir": str(run_dir), "manifest": manifest}
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if renamed and run_dir.exists():
            # Never leave an unreferenced "successful" run behind.
            latest = out / "latest.json"
            referenced = False
            if latest.is_file():
                try:
                    referenced = str(run_dir) == json.loads(
                        latest.read_text(encoding="utf-8")).get("run_dir")
                except (ValueError, OSError):
                    referenced = False
            if not referenced:
                shutil.rmtree(run_dir, ignore_errors=True)
        try:
            _write_json_atomic(out / "last_attempt.json", _attempt_payload({
                "status": "failed", "error": str(exc)[:500],
                "error_type": type(exc).__name__,
                "attempted_at": datetime.now(timezone.utc).isoformat()},
                attempt_metadata))
        except OSError:
            pass
        raise


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_publication(out, *, as_of, max_age_seconds, allow_stale=False):
    """Verify a published run and report a consumer-visible state."""
    root = Path(out)
    warnings = []
    try:
        latest_path = root / "latest.json"
        if not latest_path.is_file():
            raise CorruptedPublication("missing latest.json")
        latest = _load(latest_path)
        if latest.get("schema_version") not in (None, PUBLICATION_SCHEMA):
            raise IncompatiblePublication(
                "latest schema " + str(latest.get("schema_version")))
        run_dir = Path(latest.get("run_dir") or "")
        if not run_dir.is_dir():
            raise CorruptedPublication("latest run_dir missing")
        if root.resolve() not in run_dir.resolve().parents:
            raise CorruptedPublication("latest run_dir escapes output root")
        manifest_path = run_dir / "manifest.json"
        if (latest.get("manifest_sha256")
                and _sha256(manifest_path) != latest["manifest_sha256"]):
            raise CorruptedPublication("manifest sha256 mismatch")
        manifest = _load(manifest_path)
        if manifest.get("schema_version") != PUBLICATION_SCHEMA:
            raise IncompatiblePublication(
                "publication schema " + str(manifest.get("schema_version")))
        manifest_versions = manifest.get("versions") or {}
        if manifest_versions.get("full_supply_facts") != FULL_SCHEMA:
            raise IncompatiblePublication(
                "full facts schema " + str(
                    manifest_versions.get("full_supply_facts")))
        if (manifest_versions.get("supply_target_summary")
                != TARGET_SUMMARY_SCHEMA):
            raise IncompatiblePublication(
                "target summary schema " + str(
                    manifest_versions.get("supply_target_summary")))
        if manifest.get("publish_status") != "succeeded":
            raise CorruptedPublication("manifest is not a successful publication")
        datasets = manifest.get("datasets") or {}
        required = {"full_supply_facts.parquet", "full_supply_facts.json",
                    "supply_target_summary.parquet",
                    "supply_target_summary.json",
                    "supply_position.parquet", "supply_position.json",
                    "timeline.json"}
        if not required.issubset(set(datasets)):
            raise CorruptedPublication("manifest datasets incomplete")
        for name, entry in datasets.items():
            path = run_dir / name
            if not path.is_file():
                raise CorruptedPublication("missing dataset " + name)
            if _sha256(path) != entry.get("sha256"):
                raise CorruptedPublication("sha256 mismatch " + name)
            expected_schema = {
                "full_supply_facts": FULL_SCHEMA,
                "supply_target_summary": TARGET_SUMMARY_SCHEMA,
                "supply_position": POSITION_SCHEMA,
                "timeline": FULL_SCHEMA,
            }.get(entry.get("dataset"))
            if expected_schema and entry.get("schema_version") != expected_schema:
                raise IncompatiblePublication(
                    "%s schema %s" % (name, entry.get("schema_version")))
        stage_json = _load(run_dir / "full_supply_facts.json")
        stage_json_rows = _sorted_rows(stage_json, STAGE_KEY)
        _assert_unique(stage_json_rows, STAGE_KEY, "duplicate stage fact key")
        if len(stage_json_rows) != datasets["full_supply_facts.json"]["rows"]:
            raise CorruptedPublication("full_supply_facts.json row count mismatch")
        if _verify_stage(run_dir, stage_json_rows) != datasets[
                "full_supply_facts.parquet"]["rows"]:
            raise CorruptedPublication(
                "full_supply_facts.parquet row count mismatch")
        target_json = _load(run_dir / "supply_target_summary.json")
        target_json_rows = _sorted_rows(target_json, FULL_KEY)
        _assert_unique(target_json_rows, FULL_KEY,
                       "duplicate target summary key")
        if len(target_json_rows) != datasets[
                "supply_target_summary.json"]["rows"]:
            raise CorruptedPublication(
                "supply_target_summary.json row count mismatch")
        if _verify_full(run_dir, target_json_rows) != datasets[
                "supply_target_summary.parquet"]["rows"]:
            raise CorruptedPublication(
                "supply_target_summary.parquet row count mismatch")
        position_json = canonical_position_rows(_load(run_dir / "supply_position.json"))
        if len(position_json) != datasets["supply_position.json"]["rows"]:
            raise CorruptedPublication("supply_position.json row count mismatch")
        _assert_unique(position_json, POSITION_KEY, "duplicate position target key")
        # Re-read the Parquet without the original in-memory result.
        import pyarrow.parquet as pq
        position_parquet = pq.read_table(run_dir / "supply_position.parquet")
        if not position_parquet.schema.equals(position_table({"rows": []}).schema):
            raise CorruptedPublication("supply_position parquet schema mismatch")
        position_rows = [_position_from_parquet(record)
                         for record in position_parquet.to_pylist()]
        if len(position_rows) != datasets["supply_position.parquet"]["rows"]:
            raise CorruptedPublication("supply_position.parquet row count mismatch")
        _compare_rows(position_json, position_rows,
                      "supply_position json/parquet")
        timeline_json = _load(run_dir / "timeline.json")
        if len(timeline_json) != datasets["timeline.json"]["rows"]:
            raise CorruptedPublication("timeline row count mismatch")
        _verify_timeline(run_dir, timeline_json)
        now, _, _ = _time_parts(as_of)
        if now is None:
            raise ValueError("as_of must be an aware timestamp")
        freshness = manifest.get("freshness") or {}
        stale_sources = []
        unknown_sources = []
        for source in freshness.get("sources") or ():
            parsed, _, _ = _time_parts(source.get("time"))
            if parsed is None:
                unknown_sources.append(source.get("role"))
                continue
            age = (now - parsed).total_seconds()
            if age < 0 or age > max_age_seconds:
                stale_sources.append(source.get("role"))
        if stale_sources:
            warnings.append("stale_sources:" + ",".join(sorted(stale_sources)))
        if unknown_sources:
            warnings.append("unknown_source_time:" + ",".join(sorted(unknown_sources)))
        publish_row_level = freshness.get("row_level") or {}
        # Row freshness is recomputed against THIS read time; the publish-time
        # snapshot is never trusted and a fresh file header cannot mask it.
        row_level = assess_stage_freshness(
            stage_json_rows, as_of=as_of,
            max_age_seconds=max_age_seconds)
        target_row_level = assess_freshness(
            target_json_rows, as_of=as_of,
            max_age_seconds=max_age_seconds)["summary"]
        row_issues = sum(int(row_level.get(key) or 0) for key in
                         ("stale", "unknown", "future"))
        if row_issues:
            warnings.append("row_level_freshness_issues:%s" % row_issues)
        last_attempt = {}
        attempt_path = root / "last_attempt.json"
        if attempt_path.is_file():
            last_attempt = _load(attempt_path)
        refresh_status = ("failed_using_previous"
                          if last_attempt.get("status") == "failed" else "succeeded")
        partial = bool((manifest.get("output_summary") or {}).get("partial"))
        business_conflict_rows = (
            (manifest.get("output_summary") or {}).get("business_conflict_rows")
            or manifest.get("business_conflict_rows") or 0)
        business_conflict_reasons = (
            (manifest.get("output_summary") or {})
            .get("business_conflict_reasons")
            or manifest.get("business_conflict_reasons") or {})
        if partial:
            warnings.append("manifest_partial")
        if business_conflict_rows:
            warnings.append("business_conflicts:%s" % business_conflict_rows)
        if stale_sources or unknown_sources or row_issues:
            # Unknown/naive/date-only source time is never treated as fresh.
            status = "stale"
        elif partial:
            status = "partial"
        elif refresh_status == "failed_using_previous":
            status = "refresh_failed_using_previous"
        else:
            status = "healthy"
        readable = (status in ("healthy", "partial") or
                    (allow_stale and status in ("stale", "partial",
                                                "refresh_failed_using_previous")))
        if not readable:
            warnings.append("read_refused_use_allow_stale")
        return {"status": status, "readable": readable,
                "warnings": warnings,
                "refresh_status": refresh_status,
                "manifest": manifest, "latest": latest,
                "last_attempt": last_attempt,
                "refresh_stage": last_attempt.get("stage"),
                "collection_status": (last_attempt.get("collection_status")
                                      or manifest.get("collection_status")),
                "business_unknown": (last_attempt.get("business_unknown")
                                     or manifest.get("business_unknown") or []),
                "freshness": freshness, "row_level": row_level,
                "publish_row_level": publish_row_level,
                "target_row_level": target_row_level,
                "target_summary_rows": (manifest.get("output_summary") or {})
                .get("supply_target_summary_rows"),
                "partial_reason": (manifest.get("partial_reason")
                                   or (manifest.get("output_summary") or {})
                                   .get("partial_reason") or []),
                "business_conflict_rows": business_conflict_rows,
                "business_conflict_reasons": business_conflict_reasons,
                "full_chain_ready": False,
                "forecast_connected": False,
                "netting_ready": False,
                "rows": (manifest.get("output_summary") or {}).get(
                    "full_supply_facts_rows")}
    except IncompatiblePublication as exc:
        return {"status": "incompatible_version", "readable": False,
                "warnings": [str(exc)], "full_chain_ready": False}
    except Exception as exc:  # noqa: BLE001
        return {"status": "corrupted", "readable": False,
                "warnings": [str(exc)[:500]], "full_chain_ready": False}
