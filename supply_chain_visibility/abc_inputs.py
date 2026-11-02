"""Frozen A/B/C attribution for full supply facts (read-only, no network).

A defines the approved target universe; B is the authority for UOM / warehouse
pool / branch / purpose / tt_sku; C carries the inventory quantity and its
observation time. Missing dimensions stay null/unknown with an explicit reason.
No value is inferred from item_code, source warehouse, customer or names, and a
physical CG pool is never copied into multiple branch pools.

Three distinct layers are kept apart:

* ``inventory_observed_qty`` / ``inventory_observed_uom``: what C observed;
* ``attribution_status`` / ``inventory_qty``: whether B can attribute it;
* ``inventory_current_available_qty`` / ``order_eligibility``: whether the
  attribution is time-proven and the B order gates are open.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from supply_chain_visibility.preforecast_readiness import (
    VALID_PURPOSES,
    from_workbooks,
)

SCHEMA_VERSION = "abc-frozen/v2"
ATTRIBUTION_VALUES = ("attributed", "partial_identity", "unattributed",
                      "uom_mismatch", "a_inactive", "b_identity_conflict",
                      "cg_pool_ambiguous", "b_multi_uom_ambiguous",
                      "version_conflict", "a_only")
FRESHNESS_VALUES = ("fresh", "stale", "future", "unknown_time")


def _dec(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _qty(value):
    number = _dec(value)
    return None if number is None else str(number)


def _observed(value):
    """Return (aware UTC datetime | None, raw | None, status)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None, "missing"
    raw = value
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return None, raw.isoformat(), "date_only"
    elif isinstance(value, str):
        text = value.strip()
        if len(text) == 10:
            try:
                date.fromisoformat(text)
                return None, raw, "date_only"
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                date.fromisoformat(text)
            except ValueError:
                return None, raw, "invalid"
            return None, raw, "date_only"
    else:
        return None, str(raw), "invalid"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, raw if isinstance(raw, str) else parsed.isoformat(), "naive"
    return parsed.astimezone(timezone.utc), raw if isinstance(raw, str) else parsed.isoformat(), "known"


def _freshness(time_status, observed_at, as_of_time, date_age_days,
               max_stock_age_days):
    """Return (freshness, time_proven). Naive/date-only is never exact time."""
    if observed_at is not None and as_of_time is not None:
        if observed_at > as_of_time:
            return "future", True
        seconds = (as_of_time - observed_at).total_seconds()
        if seconds > max_stock_age_days * 86400:
            return "stale", True
        return "fresh", True
    if time_status in ("missing", "invalid"):
        return "unknown_time", False
    if date_age_days is None:
        return "unknown_time", False
    if date_age_days < 0:
        return "future", False
    if date_age_days > max_stock_age_days:
        return "stale", False
    return "unknown_time", False


def _sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _expected_check(letter, actual_sha, actual_rows, expected):
    if not expected:
        return
    rule = expected.get(letter) or {}
    if rule.get("sha256") and rule["sha256"].lower() != actual_sha.lower():
        raise ValueError("input_hash_mismatch:" + letter)
    if rule.get("rows") is not None and rule["rows"] != actual_rows:
        raise ValueError("input_row_count_mismatch:" + letter)


def _order_blockers(source, *, a_active, unit_match, multi_uom, b_conflict,
                    version_conflict, time_proven, fresh, has_c):
    reasons = set(source.get("reasons") or [])
    blockers = set()
    if "b_existing_netting_gate_closed" in reasons:
        blockers.add("b_netting_gate_closed")
    if "no_independent_demand_qualification" in reasons:
        blockers.add("no_independent_demand")
    if "c_not_qualified_for_netting" in reasons:
        blockers.add("c_not_qualified")
    if not a_active:
        blockers.add("a_inactive")
    if b_conflict:
        blockers.add("b_identity_conflict")
    if version_conflict:
        blockers.add("c_b_version_conflict")
    if has_c:
        if multi_uom:
            blockers.add("b_multi_uom_ambiguous")
        elif not unit_match:
            blockers.add("uom_mismatch")
        if not time_proven:
            blockers.add("inventory_time_unknown")
        if fresh == "stale":
            blockers.add("inventory_stale")
        elif fresh == "future":
            blockers.add("inventory_future")
    return blockers


def attribute_readiness(readiness, *, as_of, max_stock_age_days,
                        as_of_time=None):
    """Map readiness rows to strict full-facts inventory rows.

    Observed quantity, attributed quantity and current-available quantity are
    different facts. A unit mismatch or missing unit keeps the observation but
    never upgrades it to attributed/current available.
    """
    today = date.fromisoformat(as_of)
    if type(max_stock_age_days) is not int or max_stock_age_days < 0:
        raise ValueError("max_stock_age_days must be a non-negative integer")
    as_of_parsed, _, _ = _observed(as_of_time) if as_of_time else (None, None, None)
    rows = []
    approved = sorted({row["item_code"] for row in readiness.get("rows") or []
                       if row.get("a_active") is True})
    for source in readiness.get("rows") or []:
        item = source.get("item_code")
        uom = source.get("canonical_uom")
        pool = source.get("pool")
        observed_raw = source.get("inventory_qty_raw")
        if observed_raw is None:
            observed_raw = source.get("inventory_observed_qty")
        observed_qty = _dec(observed_raw)
        has_c = (source.get("c_join_class") is not None
                 or source.get("c_source_ref") is not None
                 or observed_raw is not None)
        observed_at, as_of_raw, time_status = _observed(
            source.get("inventory_as_of_raw") or source.get("inventory_as_of"))
        date_age = source.get("inventory_age_days")
        fresh, time_proven = _freshness(
            time_status, observed_at, as_of_parsed, date_age,
            max_stock_age_days)
        owner = bool(source.get("b_attribution_available"))
        a_active = source.get("a_active") is True
        b_conflict = source.get("b_identity_conflict") is True
        reasons = list(source.get("reasons") or [])
        identities = [identity for identity in source.get("b_target_identities") or []
                      if any(identity.get(key) for key in
                             ("warehouse", "branch", "purpose", "tt_sku"))]
        b_units = sorted({
            str(unit).strip() for unit in source.get("b_units") or []
            if unit is not None and str(unit).strip()})
        unit_match = bool(uom and len(b_units) == 1 and b_units[0] == uom)
        multi_uom = len(b_units) > 1
        identity_conflict = b_conflict or len(identities) > 1
        version_conflict = "c_declared_b_version_mismatch" in reasons
        join_full = (source.get("c_join_class") == "join_full"
                     and bool(source.get("c_source_ref")) and bool(uom))
        blockers = _order_blockers(
            source, a_active=a_active, unit_match=unit_match,
            multi_uom=multi_uom, b_conflict=b_conflict,
            version_conflict=version_conflict, time_proven=time_proven,
            fresh=fresh, has_c=has_c)
        if has_c and observed_qty is None:
            reasons.append("c_quantity_unknown")
        if has_c and not time_proven:
            reasons.append("inventory_time_unknown")
        if fresh == "stale":
            reasons.append("inventory_stale")
        if fresh == "future":
            reasons.append("inventory_future")
        if multi_uom:
            reasons.append("b_multi_uom_ambiguous")
        elif owner and has_c and not unit_match:
            reasons.append("uom_mismatch")
        if b_conflict:
            reasons.append("b_identity_conflict")
        if not a_active and owner:
            reasons.append("a_inactive")
        if not owner:
            reasons.append("c_without_b_attribution" if has_c
                           else "b_missing_same_product_pool")
        if blockers:
            reasons.append("order_blocked")

        def base_row(*, row_uom=None, warehouse=None, branch=None,
                     purpose="unknown", tt_sku=None, observed=None,
                     inventory=None, attribution="unattributed",
                     coverage="abc_inventory"):
            return {
                "item_code": item,
                "uom": row_uom if row_uom is not None else (uom or ""),
                "warehouse": warehouse or pool or "",
                "purpose": purpose if purpose in VALID_PURPOSES else "unknown",
                "tt_sku": tt_sku or "",
                "branch": branch or "",
                "pool": pool,
                "b_units": list(b_units),
                "source_ref": source.get("c_source_ref"),
                "qty": _qty(inventory),
                "observed_qty": _qty(observed),
                "inventory_qty": _qty(inventory),
                "inventory_observed_qty": _qty(observed),
                "inventory_observed_uom": uom,
                "inventory_current_available_qty": None,
                "inventory_as_of": observed_at.isoformat() if observed_at else None,
                "inventory_as_of_raw": as_of_raw,
                "inventory_time_status": time_status,
                "inventory_time_proven": bool(time_proven),
                "inventory_date_age_days": date_age,
                "inventory_freshness": fresh,
                "source_status": ("known" if observed is not None
                                  else ("unknown" if has_c else "missing")),
                "attribution_status": attribution,
                "inventory_trusted": attribution == "attributed",
                "abc_identity_source": "B" if owner else ("C" if has_c else "A"),
                "order_eligibility": "blocked" if blockers else "unknown",
                "order_blockers": sorted(blockers),
                "coverage": coverage,
                "reasons": sorted(set(reasons)),
            }

        identity = identities[0] if identities else {}
        warehouse = (identity.get("warehouse") or source.get("b_warehouse")
                     or pool)
        branch = identity.get("branch") or source.get("b_branch")
        purpose = identity.get("purpose") or source.get("b_purpose")
        tt_sku = identity.get("tt_sku") or source.get("b_tt_sku")

        if owner and identity_conflict:
            # A shared/conflicting identity cannot be attributed to one branch.
            for claimed in identities or [identity]:
                row = base_row(
                    row_uom=uom,
                    warehouse=claimed.get("warehouse") or warehouse,
                    branch=claimed.get("branch"),
                    purpose=claimed.get("purpose"),
                    tt_sku=claimed.get("tt_sku"),
                    observed=None, inventory=None,
                    attribution=("b_identity_conflict" if b_conflict
                                 else "cg_pool_ambiguous"),
                    coverage=("abc_conflict_identity" if b_conflict
                              else "abc_cg_pool_identity"))
                row["reasons"] = sorted(set(row["reasons"] + [
                    "b_identity_conflict" if b_conflict
                    else "cg_pool_allocation_unknown"]))
                rows.append(row)
            pooled = base_row(row_uom=uom, observed=observed_qty, inventory=None,
                              attribution=("b_identity_conflict" if b_conflict
                                           else "cg_pool_ambiguous"),
                              coverage=("abc_conflict_unattributed" if b_conflict
                                        else "abc_cg_pool_unattributed"))
            pooled["reasons"] = sorted(set(pooled["reasons"] + (
                ["b_identity_conflict"] if b_conflict else
                ["cg_pool_allocation_unknown",
                 "cg_pool_shared_by_multiple_attributions"])))
            rows.append(pooled)
            continue

        if owner and multi_uom:
            # Keep every B unit destination; the C observation stays once.
            observed_placed = False
            for unit in b_units:
                row = base_row(
                    row_uom=unit, warehouse=warehouse, branch=branch,
                    purpose=purpose, tt_sku=tt_sku,
                    observed=(observed_qty if unit == uom else None),
                    inventory=None, attribution="b_multi_uom_ambiguous",
                    coverage="abc_multi_uom_identity")
                row["b_units"] = [unit]
                if unit == uom:
                    observed_placed = True
                rows.append(row)
            if not observed_placed:
                observed_row = base_row(
                    row_uom=uom, warehouse=warehouse, branch=branch,
                    purpose=purpose, tt_sku=tt_sku, observed=observed_qty,
                    inventory=None, attribution="b_multi_uom_ambiguous",
                    coverage="abc_multi_uom_unattributed")
                observed_row["b_units"] = list(b_units)
                rows.append(observed_row)
            continue

        row_uom = uom
        if not owner:
            attribution = "unattributed"
        elif not a_active:
            attribution = "a_inactive"
        elif version_conflict:
            attribution = "version_conflict"
        elif not has_c:
            attribution = "partial_identity"
        elif not unit_match:
            attribution = "uom_mismatch"
        elif not (warehouse and purpose in VALID_PURPOSES
                  and (branch or purpose == "fba") and tt_sku and uom):
            attribution = "partial_identity"
        else:
            attribution = "attributed"
        inventory_qty = observed_qty if attribution == "attributed" else None
        row = base_row(
            row_uom=row_uom, warehouse=warehouse, branch=branch,
            purpose=purpose, tt_sku=tt_sku, observed=observed_qty,
            inventory=inventory_qty, attribution=attribution,
            coverage=("abc_inventory" if owner else
                      ("abc_unattributed_inventory" if has_c
                       else "abc_approved_without_identity")))
        if (attribution == "attributed" and time_proven
                and fresh == "fresh" and inventory_qty is not None):
            row["inventory_current_available_qty"] = _qty(inventory_qty)
        if not has_c:
            row["reasons"] = sorted(set(row["reasons"] + ["c_uncovered_not_zero"]))
        if attribution == "partial_identity":
            row["reasons"] = sorted(set(row["reasons"] + ["identity_partial"]))
        rows.append(row)

    deduped = {}
    for row in rows:
        key = (row["item_code"], row["uom"] or "", row["warehouse"] or "",
               row["purpose"], row["tt_sku"] or "", row["branch"] or "")
        if key in deduped:
            previous = deduped[key]
            comparable = ("inventory_qty", "inventory_observed_qty",
                          "inventory_as_of_raw", "attribution_status",
                          "inventory_freshness", "inventory_time_proven",
                          "b_units", "order_blockers")
            if any(previous.get(field) != row.get(field) for field in comparable):
                ambiguous = {"cg_pool_ambiguous", "b_multi_uom_ambiguous",
                             "b_identity_conflict"}
                observation_merge = (
                    previous.get("inventory_qty") is None
                    and row.get("inventory_qty") is None
                    and previous.get("attribution_status") in ambiguous
                    and row.get("attribution_status") in ambiguous
                    and (previous.get("inventory_observed_qty") is None)
                    != (row.get("inventory_observed_qty") is None))
                if not observation_merge:
                    raise ValueError("duplicate_target_key")
                keep = (previous if previous.get("inventory_observed_qty")
                        is not None else row)
                keep["reasons"] = sorted(set(previous["reasons"]
                                             + row["reasons"]))
                keep["b_units"] = sorted(set(
                    list(previous.get("b_units") or [])
                    + list(row.get("b_units") or [])))
                deduped[key] = keep
                continue
            previous["reasons"] = sorted(set(previous["reasons"] + row["reasons"]))
        else:
            deduped[key] = row
    output = [deduped[key] for key in sorted(deduped)]
    destinations = Counter(row["attribution_status"] for row in output)
    reason_counts = Counter(reason for row in output for reason in row["reasons"])
    report = {
        "output_rows": len(output),
        "full_keys": len(deduped),
        "approved_items": len(approved),
        "destinations": dict(sorted(destinations.items())),
        "stale_rows": sum(1 for row in output
                          if row["inventory_freshness"] == "stale"),
        "unknown_time_rows": sum(1 for row in output
                                 if not row["inventory_time_proven"]),
        "uom_mismatch_rows": sum(1 for row in output
                                 if row["attribution_status"] == "uom_mismatch"),
        "a_inactive_rows": sum(1 for row in output
                               if row["attribution_status"] == "a_inactive"),
        "multi_uom_rows": sum(1 for row in output
                              if row["attribution_status"] == "b_multi_uom_ambiguous"),
        "order_blocked_rows": sum(1 for row in output
                                  if row["order_eligibility"] == "blocked"),
        "unknown_reason_distribution": dict(sorted(reason_counts.items())),
        "cg_pool_identities": sum(1 for row in output
                                  if row["coverage"] == "abc_cg_pool_identity"),
        "attributed_current_available": sum(
            1 for row in output if row["inventory_current_available_qty"] is not None),
        "netting_ready": False,
    }
    return {"rows": output, "approved_items": approved, "report": report}


def load_frozen_abc(a_path, b_path, c_path, *, as_of, a_version, b_version,
                    c_version, c_declared_b_version=None, max_stock_age_days,
                    expected=None, as_of_time=None):
    """Read frozen A/B/C, verify the input contract and attribute inventory."""
    if not all((a_version, b_version, c_version)):
        raise ValueError("A/B/C versions are required")
    if expected is not None and not isinstance(expected, dict):
        raise ValueError("expected must be a mapping")
    readiness = from_workbooks(
        a_path, b_path, c_path, as_of=as_of,
        max_stock_age_days=max_stock_age_days,
        b_version=b_version, c_declared_b_version=c_declared_b_version)
    inputs = []
    roles = (("a", "A", a_path, a_version), ("b", "B", b_path, b_version),
             ("c", "C", c_path, c_version))
    rows_by_role = {"A": readiness["report"]["a_input_rows"],
                    "B": readiness["report"]["b_input_rows"],
                    "C": readiness["report"]["c_input_rows"]}
    for letter, role, path, version in roles:
        digest = _sha256(path)
        _expected_check(letter, digest, rows_by_role[role], expected)
        inputs.append({
            "role": role, "source": "frozen_workbook", "path": str(path),
            "sha256": digest, "version": version,
            "row_count": rows_by_role[role],
            "as_of": _c_as_of(readiness) if role == "C" else None,
            "time_status": _c_time_status(readiness) if role == "C" else "not_applicable",
        })
    attributed = attribute_readiness(
        readiness, as_of=as_of, max_stock_age_days=max_stock_age_days,
        as_of_time=as_of_time)
    report = dict(attributed["report"])
    report.update({
        "schema_version": SCHEMA_VERSION,
        "implementation_version": "fzh.abc_inputs@2026-11-02.2",
        "a_input_rows": readiness["report"]["a_input_rows"],
        "a_active_items": readiness["report"]["a_active_items"],
        "b_input_rows": readiness["report"]["b_input_rows"],
        "b_unique_item_pool": readiness["report"]["b_unique_item_pool"],
        "c_input_rows": readiness["report"]["c_input_rows"],
        "readiness_output_keys": readiness["report"]["output_keys"],
        "version_relation": readiness["report"].get("version_relation"),
        "b_version": b_version,
        "c_declared_b_version": readiness["report"].get("c_declared_b_version"),
        "c_dependency_source": readiness["report"].get("c_dependency_source"),
        "inputs": inputs,
        "input_rows_total": (readiness["report"]["a_input_rows"]
                             + readiness["report"]["b_input_rows"]
                             + readiness["report"]["c_input_rows"]),
    })
    return {"schema_version": SCHEMA_VERSION, "as_of": as_of,
            "approved_items": attributed["approved_items"],
            "inventory": attributed["rows"], "report": report,
            "readiness": readiness}


def _c_as_of(readiness):
    values = [row.get("inventory_as_of_raw") or row.get("inventory_as_of")
              for row in readiness.get("rows") or []
              if row.get("inventory_as_of_raw") or row.get("inventory_as_of")]
    return max((str(value) for value in values), default=None)


def _c_time_status(readiness):
    statuses = set()
    for row in readiness.get("rows") or []:
        raw = row.get("inventory_as_of_raw") or row.get("inventory_as_of")
        if raw is None:
            continue
        _, _, status = _observed(raw)
        statuses.add(status)
    if not statuses:
        return "missing"
    if statuses == {"known"}:
        return "known"
    if "invalid" in statuses:
        return "invalid"
    if "date_only" in statuses or "naive" in statuses:
        return "date_only_or_naive"
    return "unknown"
