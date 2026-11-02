"""Versioned A/B/C structured datasets (JSON or Parquet + sidecar manifest).

The worksheets stay available through ``preforecast_readiness.from_workbooks``
as the frozen regression adapter. This module only validates the structured
contract and feeds the same join/attribution code; it never re-implements the
A/B/C rules and never infers missing identity from names.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from supply_chain_visibility.abc_inputs import attribute_readiness
from supply_chain_visibility.preforecast_readiness import assess_readiness

SCHEMA_VERSION = "abc-datasets/v1"
TOP_FIELDS = {
    "schema_version", "dataset_version", "source", "observed_at", "as_of",
    "row_count", "sha256", "dependency_versions", "rows",
}
TOP_REQUIRED = {"schema_version", "dataset_version", "source", "row_count",
                "sha256"}
A_FIELDS = {"item_code", "active", "role", "inclusion_reason"}
B_FIELDS = {
    "item_code", "tt_sku", "market", "branch", "destination_pool", "warehouse",
    "product_form", "purpose", "channel", "uom", "source_ref", "evidence",
    "netting_gate", "blockers", "demand_row", "pool",
}
C_FIELDS = {
    "item_code", "pool", "uom", "qty", "source_ref", "snapshot_id",
    "observed_at", "as_of", "join_class", "b_version", "b_hash",
    "demand_eligibility",
}
A_REQUIRED = {"item_code", "active", "role", "inclusion_reason"}
B_REQUIRED = {"item_code", "tt_sku", "market", "branch", "product_form",
              "uom", "netting_gate", "blockers", "demand_row"}
C_REQUIRED = {"item_code", "pool", "uom", "qty", "source_ref", "snapshot_id",
              "join_class", "b_version", "b_hash"}


class AbcDatasetError(ValueError):
    """Structured A/B/C input violates the versioned contract."""


def _text(value):
    return "" if value is None else str(value).strip()


def _canonical_rows(rows):
    return json.dumps(rows, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def rows_sha256(rows):
    return hashlib.sha256(_canonical_rows(rows).encode("utf-8")).hexdigest()


def _read_json(path):
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("non-standard JSON number: " + value)))
    except (OSError, ValueError) as exc:
        raise AbcDatasetError("cannot read %s: %s" % (path, exc))


def _read_parquet(path):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - base env
        raise AbcDatasetError("pyarrow is required for Parquet datasets") from exc
    path = Path(path)
    sidecar = path.with_suffix(".manifest.json")
    if not sidecar.is_file():
        raise AbcDatasetError(
            "Parquet dataset needs sidecar manifest: %s" % sidecar)
    envelope = _read_json(sidecar)
    rows = pq.read_table(path).to_pylist()
    return envelope, rows


def _validate_time(value, label, *, allow_date_only=True):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if allow_date_only and len(text) == 10:
        try:
            date.fromisoformat(text)
            return text
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AbcDatasetError("%s is not ISO-8601: %r" % (label, value)) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if allow_date_only and len(text) == 10:
            return text
        raise AbcDatasetError("%s must carry an explicit timezone" % label)
    return text


def _alias(row, names, label, *, required=False):
    present = [name for name in names
               if name in row and _text(row.get(name))]
    values = sorted({_text(row[name]) for name in present})
    if len(values) > 1:
        raise AbcDatasetError("%s alias conflict: %s" % (label, ", ".join(values)))
    if required and not values:
        raise AbcDatasetError("%s needs one of %s" % (label, ", ".join(names)))
    return values[0] if values else None


def _check_row(row, index, role, allowed, required):
    label = "%s.rows[%s]" % (role, index)
    if not isinstance(row, dict):
        raise AbcDatasetError("%s must be an object" % label)
    unknown = sorted(set(row) - allowed)
    if unknown:
        raise AbcDatasetError("%s unknown field(s): %s"
                              % (label, ", ".join(unknown)))
    missing = sorted(required - set(row))
    if missing:
        raise AbcDatasetError("%s missing field(s): %s"
                              % (label, ", ".join(missing)))


def _validate_envelope(envelope, rows, role):
    if not isinstance(envelope, dict):
        raise AbcDatasetError("%s envelope must be an object" % role)
    unknown = sorted(set(envelope) - TOP_FIELDS)
    if unknown:
        raise AbcDatasetError("%s envelope unknown field(s): %s"
                              % (role, ", ".join(unknown)))
    missing = sorted(TOP_REQUIRED - set(envelope))
    if missing:
        raise AbcDatasetError("%s envelope missing field(s): %s"
                              % (role, ", ".join(missing)))
    if envelope["schema_version"] != SCHEMA_VERSION:
        raise AbcDatasetError("%s schema_version must be %s"
                              % (role, SCHEMA_VERSION))
    for name in ("dataset_version", "source"):
        if not _text(envelope[name]):
            raise AbcDatasetError("%s.%s must be non-empty" % (role, name))
    if type(envelope["row_count"]) is not int or envelope["row_count"] != len(rows):
        raise AbcDatasetError("%s.row_count %r != %s rows"
                              % (role, envelope["row_count"], len(rows)))
    digest = rows_sha256(rows)
    if _text(envelope["sha256"]).lower() != digest:
        raise AbcDatasetError("%s.sha256 does not match rows" % role)
    if not (_text(envelope.get("observed_at")) or _text(envelope.get("as_of"))):
        raise AbcDatasetError("%s needs observed_at or as_of" % role)
    _validate_time(envelope.get("observed_at"), role + ".observed_at")
    _validate_time(envelope.get("as_of"), role + ".as_of")
    deps = envelope.get("dependency_versions") or {}
    if not isinstance(deps, dict):
        raise AbcDatasetError("%s.dependency_versions must be an object" % role)
    return digest, deps


def _validate_a(row, index):
    _check_row(row, index, "A", A_FIELDS, A_REQUIRED)
    label = "A.rows[%s]" % index
    if not _text(row["item_code"]):
        raise AbcDatasetError("%s.item_code required" % label)
    if type(row["active"]) is not bool:
        raise AbcDatasetError("%s.active must be boolean" % label)
    if not _text(row["role"]):
        raise AbcDatasetError("%s.role required" % label)
    if row["inclusion_reason"] is not None and not isinstance(
            row["inclusion_reason"], str):
        raise AbcDatasetError("%s.inclusion_reason must be string/null" % label)
    return {"item_code": _text(row["item_code"]), "active": row["active"],
            "role": _text(row["role"]),
            "inclusion_reason": row["inclusion_reason"]}


def _validate_b(row, index):
    _check_row(row, index, "B", B_FIELDS, B_REQUIRED)
    label = "B.rows[%s]" % index
    if not _text(row["item_code"]):
        raise AbcDatasetError("%s.item_code required" % label)
    if not _text(row["uom"]):
        raise AbcDatasetError("%s.uom required" % label)
    if type(row["demand_row"]) is not bool:
        raise AbcDatasetError("%s.demand_row must be boolean" % label)
    warehouse = _alias(row, ("destination_pool", "warehouse"), label + ".warehouse")
    purpose = _alias(row, ("purpose", "channel"), label + ".purpose")
    source = _alias(row, ("source_ref", "evidence"), label + ".source_ref",
                    required=True)
    blockers = row.get("blockers")
    if isinstance(blockers, list):
        blockers = ";".join(_text(value) for value in blockers if _text(value))
    elif blockers is not None and not isinstance(blockers, str):
        raise AbcDatasetError("%s.blockers must be string/list/null" % label)
    return {
        "item_code": _text(row["item_code"]), "pool": row.get("pool"),
        "uom": _text(row["uom"]), "warehouse": warehouse,
        "branch": _text(row.get("branch")) or None,
        "purpose": purpose, "tt_sku": _text(row.get("tt_sku")) or None,
        "market": _text(row.get("market")) or None,
        "product_form": _text(row.get("product_form")) or None,
        "demand_row": row["demand_row"],
        "netting_gate": _text(row.get("netting_gate")),
        "blockers": blockers or "",
        "source_ref": source,
    }


def _validate_c(row, index):
    _check_row(row, index, "C", C_FIELDS, C_REQUIRED)
    label = "C.rows[%s]" % index
    for name in ("item_code", "pool", "uom", "source_ref", "snapshot_id",
                 "join_class", "b_version", "b_hash"):
        if not _text(row[name]):
            raise AbcDatasetError("%s.%s required" % (label, name))
    qty = row["qty"]
    if qty is not None:
        if isinstance(qty, bool) or not isinstance(qty, (int, float, Decimal)):
            raise AbcDatasetError("%s.qty must be a number or null" % label)
        try:
            number = Decimal(str(qty))
        except (InvalidOperation, ValueError):
            raise AbcDatasetError("%s.qty must be a finite number" % label)
        if not number.is_finite():
            raise AbcDatasetError("%s.qty must be finite" % label)
        if number < 0:
            raise AbcDatasetError("%s.qty must be non-negative" % label)
    observed = _alias(row, ("observed_at", "as_of"), label + ".observed_at",
                      required=True)
    _validate_time(observed, label + ".observed_at")
    return {
        "item_code": _text(row["item_code"]), "pool": _text(row["pool"]),
        "uom": _text(row["uom"]), "qty": qty,
        "join_class": _text(row["join_class"]),
        "source_ref": _text(row["source_ref"]),
        "as_of": observed, "observed_at": observed,
        "snapshot_id": _text(row["snapshot_id"]),
        "b_version": _text(row["b_version"]),
        "b_hash": _text(row["b_hash"]),
        "demand_eligibility": _text(row.get("demand_eligibility")) or None,
    }


def load_dataset(path, role):
    """Load one A/B/C envelope; JSON inline or Parquet + sidecar manifest."""
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        envelope, rows = _read_parquet(path)
    else:
        envelope = _read_json(path)
        rows = envelope.get("rows") if isinstance(envelope, dict) else None
    if not isinstance(rows, list):
        raise AbcDatasetError("%s.rows must be a list" % role)
    digest, deps = _validate_envelope(envelope, rows, role)
    validate = {"A": _validate_a, "B": _validate_b, "C": _validate_c}[role]
    checked = [validate(row, index) for index, row in enumerate(rows)]
    return {"path": str(path), "envelope": envelope, "rows": checked,
            "sha256": digest, "dependency_versions": deps,
            "version": _text(envelope["dataset_version"]),
            "source": _text(envelope["source"]),
            "as_of": envelope.get("as_of"),
            "observed_at": envelope.get("observed_at")}


def _check_c_dependency(c_dataset, b_dataset, override=None):
    declared = c_dataset["dependency_versions"].get("B")
    if isinstance(declared, dict):
        version = _text(declared.get("version"))
        digest = _text(declared.get("sha256")) or _text(declared.get("sha"))
    else:
        version, digest = _text(declared), ""
    if not version:
        raise AbcDatasetError("C.dependency_versions.B.version required")
    if version != b_dataset["version"]:
        raise AbcDatasetError(
            "C depends on B %s but B dataset is %s"
            % (version, b_dataset["version"]))
    if digest and digest.lower() != b_dataset["sha256"].lower():
        raise AbcDatasetError("C dependency B sha256 mismatch")
    versions = {row["b_version"] for row in c_dataset["rows"]}
    hashes = {row["b_hash"] for row in c_dataset["rows"]}
    if versions != {b_dataset["version"]}:
        raise AbcDatasetError("C row b_version does not match B dataset")
    if hashes != {b_dataset["sha256"]}:
        raise AbcDatasetError("C row b_hash does not match B dataset")
    if override and _text(override) != b_dataset["version"]:
        raise AbcDatasetError(
            "declared B version %s != structured B %s"
            % (override, b_dataset["version"]))
    return b_dataset["version"]


def load_abc_datasets(a_path, b_path, c_path, *, as_of, max_stock_age_days,
                      as_of_time=None, c_declared_b_version=None):
    """Validate structured A/B/C, reuse assess_readiness + attribute_readiness."""
    if type(max_stock_age_days) is not int or max_stock_age_days < 0:
        raise AbcDatasetError("max_stock_age_days must be a non-negative integer")
    a_dataset = load_dataset(a_path, "A")
    b_dataset = load_dataset(b_path, "B")
    c_dataset = load_dataset(c_path, "C")
    b_version = _check_c_dependency(c_dataset, b_dataset,
                                    override=c_declared_b_version)
    readiness = assess_readiness(
        a_dataset["rows"], b_dataset["rows"], c_dataset["rows"],
        as_of=as_of, max_stock_age_days=max_stock_age_days,
        b_version=b_version, c_declared_b_version=b_version)
    attributed = attribute_readiness(
        readiness, as_of=as_of, max_stock_age_days=max_stock_age_days,
        as_of_time=as_of_time)
    report = dict(attributed["report"])
    inputs = []
    for role, dataset in (("A", a_dataset), ("B", b_dataset), ("C", c_dataset)):
        inputs.append({
            "role": role, "source": "structured_" + dataset["source"],
            "path": dataset["path"], "sha256": dataset["sha256"],
            "version": dataset["version"], "row_count": len(dataset["rows"]),
            "as_of": dataset["as_of"], "observed_at": dataset["observed_at"],
            "time_status": ("provided" if (dataset["as_of"]
                                           or dataset["observed_at"])
                            else "missing"),
        })
    report.update({
        "schema_version": SCHEMA_VERSION,
        "implementation_version": "fzh.abc_datasets@2026-11-02.1",
        "dataset_versions": {"A": a_dataset["version"],
                             "B": b_dataset["version"],
                             "C": c_dataset["version"]},
        "dataset_sha256": {"A": a_dataset["sha256"],
                           "B": b_dataset["sha256"],
                           "C": c_dataset["sha256"]},
        "b_version": b_version,
        "c_declared_b_version": b_version,
        "version_relation": "match",
        "inputs": inputs,
        "input_rows_total": sum(len(dataset["rows"]) for dataset in
                                (a_dataset, b_dataset, c_dataset)),
    })
    return {"schema_version": "abc-frozen/v4", "as_of": as_of,
            "approved_items": attributed["approved_items"],
            "inventory": attributed["rows"], "report": report,
            "readiness": readiness,
            "datasets": {"A": a_dataset, "B": b_dataset, "C": c_dataset}}
