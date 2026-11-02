"""D-independent A/B/C integration inventory. Never generates purchase quantities."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import uuid


# Optional B target-key columns. Missing columns stay null/unknown; never infer
# them from item_code, source warehouse, customer or names.
B_WAREHOUSE_ALIASES = ("目的仓", "目标仓", "warehouse", "仓库")
B_BRANCH_ALIASES = ("branch", "分公司")
B_PURPOSE_ALIASES = ("purpose", "用途")
B_TT_SKU_ALIASES = ("tt_sku", "通途SKU", "通途sku", "产品SKU")
B_TARGET_ALIASES = {
    "warehouse": B_WAREHOUSE_ALIASES,
    "branch": B_BRANCH_ALIASES,
    "purpose": B_PURPOSE_ALIASES,
    "tt_sku": B_TT_SKU_ALIASES,
}
VALID_PURPOSES = ("branch", "fba")


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _pick(row, aliases):
    """Return one explicit alias value; conflicting aliases fail closed."""
    values = sorted({
        str(row.get(name)).strip()
        for name in aliases
        if row.get(name) is not None and str(row.get(name)).strip()
    })
    if len(values) > 1:
        raise ValueError("b_target_alias_conflict:" + ",".join(aliases))
    return values[0] if values else None


def _declared_version(value):
    text = None if value is None else str(value).strip()
    return text or None


def _stock_date(value):
    """Validate the complete source value, not a plausible-looking date prefix."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def assess_readiness(universe, attribution, inventory, *, as_of, max_stock_age_days,
                     b_version=None, c_declared_b_version=None):
    """Preserve A/B/C qualifications separately; matching facts do not approve netting."""
    today = date.fromisoformat(as_of)
    if type(max_stock_age_days) is not int or max_stock_age_days < 0:
        raise ValueError("max_stock_age_days must be a non-negative integer")
    b_version = _declared_version(b_version)
    c_declared_b_version = _declared_version(c_declared_b_version)
    if b_version and c_declared_b_version:
        version_relation = "match" if b_version == c_declared_b_version else "mismatch"
    else:
        version_relation = "unknown"
    a_by_item = {}
    for row in universe:
        item = row["item_code"]
        if not item or type(row["active"]) is not bool:
            raise ValueError("A requires item identity and explicit active boolean")
        if item in a_by_item and a_by_item[item] != row:
            raise ValueError("conflicting A identity")
        a_by_item[item] = row
    b_by_key = defaultdict(list)
    for row in attribution:
        if not row.get("item_code"):
            raise ValueError("B item identity required")
        b_by_key[row["item_code"], row.get("pool")].append(row)
    c_by_key = {}
    for row in inventory:
        key = row["item_code"], row.get("pool"), row.get("uom")
        if not key[0] or key in c_by_key:
            raise ValueError("missing or duplicate C key")
        c_by_key[key] = row
    keys = set(c_by_key)
    c_pairs = {(k[0], k[1]) for k in keys}
    for item, pool in b_by_key:
        if (item, pool) not in c_pairs:
            units = {r.get("uom") for r in b_by_key[item, pool] if r.get("uom")}
            keys.add((item, pool, next(iter(units)) if len(units) == 1 else None))
    represented = {k[0] for k in keys}
    for item, row in a_by_item.items():
        if row["active"] and item not in represented:
            keys.add((item, None, None))
    rows = []
    for item, pool, uom in sorted(keys, key=lambda k: tuple(str(v or "") for v in k)):
        a = a_by_item.get(item, {})
        b = b_by_key.get((item, pool), [])
        c = c_by_key.get((item, pool, uom))
        active = a.get("active") is True
        units = sorted({r["uom"] for r in b if r.get("uom")})
        owner = bool(b) and pool is not None
        qty = _number(c.get("qty")) if c else None
        c_qualified = bool(c and c.get("join_class") == "join_full"
                           and c.get("source_ref") and qty is not None and uom and pool)
        unit_match = bool(uom and units and units == [uom])
        compatible = active and owner and c_qualified and unit_match
        target_rows = sorted({
            (r.get("warehouse"), r.get("branch"), r.get("purpose"), r.get("tt_sku"))
            for r in b
            if any(r.get(k) for k in ("warehouse", "branch", "purpose", "tt_sku"))
        }, key=lambda value: tuple(str(part or "") for part in value))
        identity_conflict = len(target_rows) > 1
        warehouse = target_rows[0][0] if len(target_rows) == 1 else None
        branch = target_rows[0][1] if len(target_rows) == 1 else None
        purpose = target_rows[0][2] if len(target_rows) == 1 else None
        tt_sku = target_rows[0][3] if len(target_rows) == 1 else None
        if purpose is not None and purpose not in VALID_PURPOSES:
            purpose = None
            purpose_invalid = True
        else:
            purpose_invalid = False
        version_trusted = version_relation != "mismatch"
        reasons = []
        if not active:
            reasons.append("a_missing_or_inactive")
        if not owner:
            reasons.append("b_missing_same_product_pool")
        if (b or c) and not unit_match:
            reasons.append("b_c_uom_missing_or_mismatch")
        if owner:
            if not warehouse:
                reasons.append("b_missing_warehouse")
            if not branch:
                reasons.append("b_missing_branch")
            if not purpose and not purpose_invalid:
                reasons.append("b_missing_purpose")
            if not tt_sku:
                reasons.append("b_missing_tt_sku")
        if purpose_invalid:
            reasons.append("b_purpose_invalid")
        if identity_conflict:
            reasons.append("b_identity_conflict")
        if not c:
            reasons.append("c_uncovered_not_zero")
        elif not c_qualified:
            reasons.append("c_not_qualified_for_netting")
        if version_relation == "mismatch":
            reasons.append("c_declared_b_version_mismatch")
        stock_date = _stock_date(c.get("as_of")) if c else None
        if c and c.get("as_of") and stock_date is None:
            reasons.append("inventory_source_time_invalid")
        age = (today - stock_date).days if stock_date else None
        needs_refresh = age is None or age < 0 or age > max_stock_age_days
        if needs_refresh:
            reasons.append("inventory_refresh_needed")
        gates = sorted({str(r.get("netting_gate") or "unknown") for r in b})
        if b and gates != ["是"]:
            reasons.append("b_existing_netting_gate_closed")
        demand = bool(c and c.get("demand_eligibility") == "independent"
                      and any(r.get("demand_row") is True for r in b))
        if not demand:
            reasons.append("no_independent_demand_qualification")
        rows.append({"item_code": item, "pool": pool, "canonical_uom": uom,
                     "a_active": active, "a_role": a.get("role"),
                     "b_attribution_available": owner, "b_evidence_rows": len(b),
                     "b_units": units, "b_netting_gates": gates,
                     "b_blockers": sorted({str(r["blockers"]) for r in b if r.get("blockers")}),
                     "b_warehouse": warehouse, "b_branch": branch,
                     "b_purpose": purpose, "b_tt_sku": tt_sku,
                     "b_identity_conflict": identity_conflict,
                     "b_target_identities": [
                         {"warehouse": part[0], "branch": part[1],
                          "purpose": part[2], "tt_sku": part[3]}
                         for part in target_rows],
                     "inventory_qualified": c_qualified,
                     "inventory_trusted": bool(c_qualified and version_trusted),
                     "inventory_qty": qty if c_qualified and version_trusted else None,
                     "inventory_observed_qty": qty,
                     "inventory_qty_raw": None if not c else c.get("qty"),
                     "c_join_class": c.get("join_class") if c else None,
                     "c_source_ref": c.get("source_ref") if c else None,
                     "inventory_as_of": stock_date.isoformat() if stock_date else None,
                     "inventory_as_of_raw": None if not c else c.get("as_of"),
                     "inventory_age_days": age, "inventory_refresh_needed": needs_refresh,
                     "abc_contract_compatible": bool(compatible and version_trusted),
                     "current_abc_ready": bool(compatible and version_trusted
                                               and not needs_refresh),
                     "independent_demand_candidate": bool(compatible and version_trusted and demand),
                     "d_forecast_status": "not_integrated", "e_supply_status": "not_integrated",
                     "netting_ready": False, "auto_order": False, "reasons": reasons})
    return {"schema_version": "preforecast-readiness/v1", "as_of": as_of, "rows": rows,
            "report": {"a_input_rows": len(universe), "a_active_items": sum(r["active"] for r in a_by_item.values()),
                       "implementation_version": "preforecast-readiness@2026-11-02",
                       "b_input_rows": len(attribution), "b_unique_item_pool": len(b_by_key),
                       "c_input_rows": len(inventory), "output_keys": len(rows),
                       "c_join_classes": dict(Counter(r.get("join_class") for r in inventory)),
                       "c_input_keys_accounted": sum((r["item_code"], r["pool"], r["canonical_uom"]) in c_by_key for r in rows),
                       "abc_contract_compatible": sum(r["abc_contract_compatible"] for r in rows),
                       "current_abc_ready": sum(r["current_abc_ready"] for r in rows),
                       "independent_demand_candidates": sum(r["independent_demand_candidate"] for r in rows),
                       "reasons": dict(Counter(reason for r in rows for reason in r["reasons"])),
                       "b_version": b_version,
                       "c_declared_b_version": c_declared_b_version,
                       "version_relation": version_relation,
                       "max_stock_age_days": max_stock_age_days,
                       "quantity_not_summed_across_forms_or_pools": True,
                       "netting_ready": False}}


def _sheet(path, name, required):
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        values = book[name].iter_rows(values_only=True)
        header = next(values)
        if len(header) != len(set(header)) or not set(required).issubset(header):
            raise ValueError("missing or duplicate columns: " + name)
        return [dict(zip(header, row)) for row in values if any(v is not None for v in row)]
    finally:
        book.close()


def _find_declared_b_versions(rows):
    """Collect every explicit dependency marker; never take the first silently."""
    import re
    found = set()
    for row in rows:
        for key, value in row.items():
            text = "" if value is None else str(value)
            if ("B" in str(key) or "依赖" in str(key)) and "v" in text:
                found.update(re.findall(r"v\d+r\d+", text))
    return found


def from_workbooks(a_path, b_path, c_path, *, as_of, max_stock_age_days,
                   b_version=None, c_declared_b_version=None):
    """Adapter for frozen A FINAL / B v6r10 / C v14; never rewrites their rules."""
    a = _sheet(a_path, "活跃宇宙", ["EN物料", "角色", "活跃分类"])
    b = _sheet(b_path, "主表", ["产品键", "地区", "美国责任方", "UOM_单位", "是否需求行", "可进净额", "限制原因"])
    c = []
    for name in ("19_Top50候选导出", "19b_Top50观察表"):
        c.extend(_sheet(c_path, name, ["product_id", "pool", "canonical_uom", "可发供给",
                                     "join_class", "source_ref", "as_of", "demand_eligibility"]))
    active_classes = {"EN+通途", "仅EN", "仅通途", "仅库存"}
    if any(r["活跃分类"] not in active_classes | {"不活跃"} for r in a):
        raise ValueError("unknown A activity class")
    universe = [{"item_code": r["EN物料"], "active": r["活跃分类"] in active_classes,
                 "role": r["角色"]} for r in a]
    attribution = []
    for r in b:
        pool = "波兰" if r["地区"] == "PL" else (
            r["美国责任方"] if r["地区"] == "US" and r["美国责任方"] in {"美东USNJ", "美中USTX"} else None)
        attribution.append({"item_code": r["产品键"], "pool": pool, "uom": r["UOM_单位"],
                            "warehouse": _pick(r, B_WAREHOUSE_ALIASES),
                            "branch": _pick(r, B_BRANCH_ALIASES),
                            "purpose": _pick(r, B_PURPOSE_ALIASES),
                            "tt_sku": _pick(r, B_TT_SKU_ALIASES),
                            "demand_row": r["是否需求行"] == "Y", "netting_gate": r["可进净额"],
                            "blockers": r["限制原因"]})
    stock = [{"item_code": r["product_id"], "pool": r["pool"], "uom": r["canonical_uom"],
              "qty": r["可发供给"], "join_class": r["join_class"], "source_ref": r["source_ref"],
              "as_of": r["as_of"], "demand_eligibility": r["demand_eligibility"]} for r in c]
    workbook_versions = _find_declared_b_versions(c)
    if len(workbook_versions) > 1:
        raise ValueError("c_dependency_ambiguous:" + ",".join(sorted(workbook_versions)))
    workbook_declared = next(iter(workbook_versions), None)
    cli_declared = _declared_version(c_declared_b_version)
    if cli_declared and workbook_declared and cli_declared != workbook_declared:
        raise ValueError("c_dependency_conflict:%s!=%s"
                         % (cli_declared, workbook_declared))
    declared = cli_declared or workbook_declared
    dependency_source = ("cli" if cli_declared else
                         ("workbook" if workbook_declared else "none"))
    result = assess_readiness(universe, attribution, stock, as_of=as_of,
                              max_stock_age_days=max_stock_age_days,
                              b_version=b_version,
                              c_declared_b_version=declared)
    result["report"]["c_dependency_source"] = dependency_source
    result["report"]["c_workbook_declared_b_version"] = workbook_declared
    result["report"]["inputs"] = [{"path": str(p), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                                   for p in (a_path, b_path, c_path)]
    return result


def publish_readiness(result, out):
    import pyarrow as pa
    import pyarrow.parquet as pq
    root = Path(out) / ("readiness-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    records = []
    for row in result["rows"]:
        record = {}
        for key, value in row.items():
            if isinstance(value, list):
                record[key] = json.dumps(value, ensure_ascii=False)
            elif key == "inventory_qty_raw" and value is not None:
                record[key] = str(value)
            else:
                record[key] = value
        records.append(record)
    schema = pa.schema([
        *[(k, pa.string()) for k in ("item_code", "pool", "canonical_uom", "a_role",
            "b_units", "b_netting_gates", "b_blockers", "c_join_class", "c_source_ref",
            "b_warehouse", "b_branch", "b_purpose", "b_tt_sku", "inventory_qty_raw",
            "b_target_identities", "inventory_as_of", "inventory_as_of_raw",
            "d_forecast_status", "e_supply_status", "reasons")],
        ("b_evidence_rows", pa.int64()), ("inventory_age_days", pa.int64()),
        ("inventory_qty", pa.float64()), ("inventory_observed_qty", pa.float64()),
        *[(k, pa.bool_()) for k in ("a_active", "b_attribution_available",
            "b_identity_conflict", "inventory_qualified", "inventory_trusted",
            "inventory_refresh_needed", "abc_contract_compatible", "current_abc_ready",
            "independent_demand_candidate", "netting_ready", "auto_order")]])
    table = pa.Table.from_pylist(records, schema=schema)
    file = root / "preforecast_readiness.parquet"
    pq.write_table(table, file, compression="zstd")
    if not pq.read_table(file).equals(table):
        raise ValueError("readiness readback mismatch")
    report = {**result["report"], "schema_version": result["schema_version"], "as_of": result["as_of"],
              "rows": table.num_rows,
              "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "parquet_sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("a", "b", "c", "out", "as-of"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--max-stock-age-days", type=int, required=True)
    parser.add_argument("--b-version")
    parser.add_argument("--c-declared-b-version")
    args = parser.parse_args()
    result = from_workbooks(args.a, args.b, args.c, as_of=args.as_of,
                            max_stock_age_days=args.max_stock_age_days,
                            b_version=args.b_version,
                            c_declared_b_version=args.c_declared_b_version)
    root = publish_readiness(result, args.out)
    print(json.dumps({"directory": str(root), "report": result["report"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
