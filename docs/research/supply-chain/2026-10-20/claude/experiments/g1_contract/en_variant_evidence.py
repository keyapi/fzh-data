#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bounded Item/BOM evidence producer (sample of PK/ND variants).

Read-only EN (GET only), single concurrency, >=0.2s between requests,
timeout 30s, HTTP budget 500, wallclock budget 15 min for the first batch.

Scope:
  - input: accepted SO audit (default d8c473fe R1) + exact family manifest
  - first batch: <=20 PK/ND variants (cover/inner + suspicious base-not-family)
  - Item list exact codes (chunks 50) + Item detail (uoms)
  - BOM list by item in (KS bases + variants), no active/default filter
  - BOM detail parent fetch (BOM Item list is 403 in production)
  - current BOM only proves `current_structure_only`; no Version/archived
    historical evidence in this run (Codex validates that boundary in parallel)

Outputs (out/ is gitignored):
  variant_evidence.json           consumer-compatible evidence manifest
  variant_evidence_summary.json   selection/query/budget/counts/hashes
  raw/items.jsonl, raw/boms.jsonl raw detail snapshots + hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "EN_API" / "item_shipment_status.py").exists()),
    Path(__file__).resolve().parents[7],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import EN_API.item_shipment_status as iss  # noqa: E402
import en_family_poc as fp  # noqa: E402

PAGE_SIZE = 100
CHUNK = 50
MIN_INTERVAL = 0.2
TIMEOUT = 30
MAX_ATTEMPTS = 3
SCHEMA_VERSION = "variant_evidence/1"
RULE_VERSION = "variant-evidence/1"
SOURCE = "erpnext.vilavi.cn"
PRODUCER = {"name": "en_variant_evidence", "version": "1"}

ITEM_FIELDS = ["name", "item_code", "item_group", "stock_uom", "disabled",
               "variant_of", "has_variants", "modified"]
ITEM_FALLBACK = ["name", "item_code", "item_group", "stock_uom", "disabled", "modified"]
BOM_FIELDS = ["name", "item", "quantity", "uom", "docstatus", "is_active",
              "is_default", "modified", "creation"]
BOM_FALLBACK = ["name", "item", "quantity", "uom", "docstatus", "is_active",
                "is_default", "modified"]


class BudgetExceeded(RuntimeError):
    pass


class QueryError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def sha_obj(obj) -> str:
    return fp.sha256_bytes(fp._canonical_json(obj))


def num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


class Client:
    def __init__(self, base: str, key: str, secret: str, max_http: int,
                 max_seconds: int):
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {key}:{secret}"
        self.max_http = max_http
        self.max_seconds = max_seconds
        self.started = time.monotonic()
        self.last = 0.0
        self.http_attempts = 0
        self.http_ok = 0
        self.errors: list[dict] = []

    def _guard(self, label: str) -> None:
        if self.http_attempts >= self.max_http:
            raise BudgetExceeded(f"HTTP budget {self.max_http} exceeded at {label}")
        if time.monotonic() - self.started > self.max_seconds:
            raise BudgetExceeded(f"wallclock budget {self.max_seconds}s exceeded at {label}")

    def get(self, path: str, label: str) -> dict:
        wait = MIN_INTERVAL - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(MAX_ATTEMPTS):
            self._guard(label)
            self.http_attempts += 1
            try:
                resp = self.session.get(f"{self.base}{path}", timeout=TIMEOUT)
            except requests.RequestException as e:
                self.errors.append({"label": label, "error": type(e).__name__})
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(1 + attempt)
                    continue
                raise QueryError(f"{label}: {type(e).__name__}") from e
            self.last = time.monotonic()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS - 1:
                retry_after = resp.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 1 + attempt
                time.sleep(delay)
                continue
            if resp.status_code != 200:
                self.errors.append({"label": label, "status": resp.status_code})
                raise QueryError(f"{label}: HTTP {resp.status_code} {resp.text[:140]}",
                                 resp.status_code)
            try:
                body = resp.json()
            except ValueError as e:
                raise QueryError(f"{label}: invalid JSON") from e
            self.http_ok += 1
            return body
        raise QueryError(f"{label}: exhausted attempts")

    def list_all(self, doctype: str, filters: list, fields: list, label: str,
                 fallback_fields: list | None = None, max_pages: int = 20):
        rows: list[dict] = []
        start = 0
        pages = 0
        complete = False
        termination = "max_pages"
        while pages < max_pages:
            query = {
                "filters": json.dumps(filters, ensure_ascii=False),
                "fields": json.dumps(fields, ensure_ascii=False),
                "limit_start": str(start),
                "limit_page_length": str(PAGE_SIZE),
                "order_by": "name asc",
            }
            path = f"/api/resource/{quote(doctype, safe='')}?{urlencode(query)}"
            try:
                body = self.get(path, f"{label}:p{pages + 1}")
            except QueryError as e:
                if e.status == 417 and fallback_fields and fields != fallback_fields:
                    fields = fallback_fields
                    continue
                raise
            data = body.get("data")
            if not isinstance(data, list):
                raise QueryError(f"{label}: data is not a list")
            pages += 1
            if not data:
                complete = True
                termination = "empty"
                break
            rows.extend(data)
            if len(data) < PAGE_SIZE:
                complete = True
                termination = "short_page"
                break
            start += len(data)
        return rows, {"rows": len(rows), "pages": pages, "complete": complete,
                      "termination": termination}

    def doc(self, doctype: str, name: str, label: str) -> dict:
        body = self.get(
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}", label)
        data = body.get("data")
        if not isinstance(data, dict):
            raise QueryError(f"{label}: data is not an object")
        return data


def load_audit(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def select_variants(rows: list[dict], ks_items: set[str], max_n: int) -> list[dict]:
    stats: dict[str, dict] = {}
    for row in rows:
        if row.get("prefix_role") not in ("PK", "ND"):
            continue
        if row.get("disposition") != "pending":
            continue
        code = str(row.get("item_code") or "")
        if not code:
            continue
        rec = stats.setdefault(code, {
            "code": code,
            "role": row.get("prefix_role"),
            "base": row.get("base_item_code") or "",
            "reasons": set(),
            "lines": 0,
            "qty": 0.0,
        })
        rec["reasons"].add(str(row.get("disposition_reason") or ""))
        rec["lines"] += 1
        rec["qty"] += num(row.get("qty")) or 0.0

    def rank(rec):
        return (-rec["qty"], rec["code"])

    absent_pk = sorted((r for r in stats.values()
                        if r["role"] == "PK" and "variant_manifest_absent" in r["reasons"]),
                       key=rank)
    absent_nd = sorted((r for r in stats.values()
                        if r["role"] == "ND" and "variant_manifest_absent" in r["reasons"]),
                       key=rank)
    suspicious = sorted((r for r in stats.values()
                         if "variant_base_not_family" in r["reasons"]), key=rank)
    selected: list[dict] = []
    seen: set[str] = set()
    for bucket, quota in ((absent_pk, 10), (absent_nd, 5), (suspicious, 5)):
        for rec in bucket:
            if len(selected) >= max_n or quota <= 0:
                break
            if rec["code"] in seen:
                continue
            selected.append(rec)
            seen.add(rec["code"])
            quota -= 1
    if len(selected) < max_n:
        for rec in sorted(stats.values(), key=rank):
            if len(selected) >= max_n:
                break
            if rec["code"] in seen:
                continue
            selected.append(rec)
            seen.add(rec["code"])
    for rec in selected:
        rec["reasons"] = sorted(rec["reasons"])
        rec["base_in_family"] = rec["base"] in ks_items
        rec["selection_note"] = ("sample: cover/inner + suspicious; "
                                 "not a population estimate")
    return selected[:max_n]


def uom_factor(item_doc: dict, uom: str, stock_uom: str):
    if not uom or not stock_uom:
        return None
    if uom == stock_uom:
        return 1.0
    for row in item_doc.get("uoms") or []:
        if str(row.get("uom") or "") == uom:
            factor = num(row.get("conversion_factor"))
            return factor if factor and factor > 0 else None
    return None


def flag(value):
    """Strict flag parser.

    Accepts bool, integer 0/1, float 0.0/1.0 (equivalent to 0/1), and strings
    0/1/true/false. Rejects other numbers (2, -1, 0.5), NaN/Inf, and unknown
    strings. Apply the same parser to Item.disabled/has_variants and BOM flags.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, float):
        return bool(value) if math.isfinite(value) and value in (0.0, 1.0) else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "y"):
            return True
        if text in ("0", "false", "no", "n", ""):
            return False
    return None


def item_meta(detail: dict) -> dict:
    return {
        "name": str(detail.get("name") or ""),
        "item_code": str(detail.get("item_code") or detail.get("name") or ""),
        "item_group": str(detail.get("item_group") or ""),
        "disabled": flag(detail.get("disabled")),
        "disabled_raw": detail.get("disabled"),
        "stock_uom": str(detail.get("stock_uom") or ""),
        "variant_of": str(detail.get("variant_of") or ""),
        "has_variants": flag(detail.get("has_variants")),
        "modified": str(detail.get("modified") or ""),
        "sha256": sha_obj(detail),
    }


def analyze_bom(bom: dict, code: str, base: str, item_docs: dict[str, dict]):
    parent = str(bom.get("item") or "")
    lines = bom.get("items")
    if not isinstance(lines, list):
        return None, "bom_items_unavailable"
    if parent == base:
        direction = "ks_parent_variant_component"
        comp_code, out_code = code, base
    elif parent == code:
        direction = "variant_parent_ks_component"
        comp_code, out_code = base, code
    else:
        return None, "bom_parent_unrelated"
    comp_lines = [x for x in lines if str(x.get("item_code") or "") == comp_code]
    if not comp_lines:
        return None, "component_missing"
    out_doc = item_docs.get(out_code)
    comp_doc = item_docs.get(comp_code)
    if not out_doc or not comp_doc:
        return None, "item_missing"
    out_qty = num(bom.get("quantity"))
    out_uom = str(bom.get("uom") or "")
    out_stock_uom = str(out_doc.get("stock_uom") or "")
    out_factor = uom_factor(out_doc, out_uom, out_stock_uom)
    if out_qty is None or out_qty <= 0 or out_factor is None:
        return None, "output_uom_conversion_missing"
    out_stock = out_qty * out_factor
    comp_stock = 0.0
    comp_qty = 0.0
    comp_uoms: set[str] = set()
    comp_stock_uom = str(comp_doc.get("stock_uom") or "")
    for line in comp_lines:
        line_uom = str(line.get("uom") or comp_stock_uom)
        line_stock_uom = str(line.get("stock_uom") or comp_stock_uom)
        qty = num(line.get("qty"))
        stock_qty = num(line.get("stock_qty"))
        if qty is None or qty <= 0:
            return None, "component_qty_invalid"
        if stock_qty is None:
            factor = num(line.get("conversion_factor")) or uom_factor(
                comp_doc, line_uom, line_stock_uom)
            if factor is None:
                return None, "component_uom_conversion_missing"
            stock_qty = qty * factor
        comp_qty += qty
        comp_stock += stock_qty
        comp_uoms.add(line_uom)
        if line_stock_uom:
            comp_stock_uom = line_stock_uom
    if comp_stock <= 0 or out_stock <= 0:
        return None, "quantity_nonpositive"
    if out_stock_uom != comp_stock_uom:
        return None, "stock_uom_mismatch"
    ratio = comp_stock / out_stock
    try:
        docstatus = int(bom.get("docstatus"))
    except (TypeError, ValueError):
        return None, "bom_docstatus_invalid"
    is_active = flag(bom.get("is_active"))
    if is_active is None:
        return None, "bom_flag_invalid"
    raw_default = bom.get("is_default")
    is_default = False if raw_default is None else flag(raw_default)
    if is_default is None:
        return None, "bom_flag_invalid"
    return {
        "name": str(bom.get("name") or ""),
        "modified": str(bom.get("modified") or ""),
        "sha256": sha_obj(bom),
        "docstatus": docstatus,
        "is_active": is_active,
        "eligible_at_evidence": docstatus == 1 and is_active,
        "is_default": is_default,
        "direction": direction,
        "parent_item": parent,
        "child_item": comp_code,
        "component_stock_qty": comp_stock,
        "output_stock_qty": out_stock,
        "uom": comp_stock_uom,
        "ratio": ratio,
        "component_item": comp_code,
        "output_item": out_code,
        "component_qty": comp_qty,
        "component_uoms": sorted(comp_uoms),
        "component_line_count": len(comp_lines),
    }, ""


def clean_candidate(cand: dict) -> dict:
    keys = ("name", "modified", "sha256", "docstatus", "is_active",
            "eligible_at_evidence", "is_default", "direction", "parent_item",
            "child_item", "component_stock_qty", "output_stock_qty", "uom")
    return {k: cand[k] for k in keys}


REASON_CODES = {
    "consistent": "consistent_structure",
    "conflict": "bom_conflict",
    "conflict_mixed_direction": "conflict_mixed_direction",
    "unsupported_direction": "unsupported_direction",
    "missing_evidence": "missing_evidence",
    "item_missing": "item_missing",
    "item_flag_invalid": "item_flag_invalid",
    "unresolved_canonical_mapping": "unresolved_canonical_mapping",
}


def shared_edge(bom: dict, code: str):
    """Raw KS parent → shared component edge (e.g. ND# used by many finished BOMs)."""
    lines = [x for x in (bom.get("items") or [])
             if str(x.get("item_code") or "") == code]
    if not lines:
        return None
    comp_stock = 0.0
    comp_qty = 0.0
    uoms: set[str] = set()
    stock_uom = ""
    for line in lines:
        qty = num(line.get("qty"))
        stock = num(line.get("stock_qty"))
        if qty is None or qty <= 0:
            return None
        if stock is None:
            stock = qty
        comp_qty += qty
        comp_stock += stock
        uoms.add(str(line.get("uom") or ""))
        if line.get("stock_uom"):
            stock_uom = str(line.get("stock_uom"))
    out_qty = num(bom.get("quantity"))
    out_uom = str(bom.get("uom") or "")
    ratio = (comp_stock / out_qty if (out_qty and out_qty > 0 and stock_uom
                                      and out_uom == stock_uom) else None)
    try:
        docstatus = int(bom.get("docstatus"))
    except (TypeError, ValueError):
        docstatus = None
    active = flag(bom.get("is_active"))
    default = flag(bom.get("is_default"))
    return {
        "name": str(bom.get("name") or ""),
        "modified": str(bom.get("modified") or ""),
        "sha256": sha_obj(bom),
        "docstatus": docstatus,
        "is_active": active,
        "eligible_at_evidence": docstatus == 1 and active is True,
        "is_default": bool(default),
        "direction": "ks_parent_variant_component",
        "parent_item": str(bom.get("item") or ""),
        "child_item": code,
        "component_stock_qty": comp_stock,
        "output_stock_qty": out_qty,
        "uom": stock_uom or out_uom,
        "ratio": ratio,
        "ratio_known": ratio is not None,
        "component_qty": comp_qty,
        "component_line_count": len(lines),
        "raw_component_uoms": sorted(x for x in uoms if x),
    }


def build_record(code: str, base: str, role: str, item_docs: dict[str, dict],
                 analyses: list[dict], excluded: list[dict], as_of: str,
                 ks_items: set[str], shared_edges: list[dict] | None = None
                 ) -> tuple[dict, str]:
    variant_item = item_docs.get(code)
    candidates = [clean_candidate(c) for c in analyses]
    if base not in ks_items:
        edges = shared_edges or []
        parents = sorted({e["parent_item"] for e in edges if e.get("parent_item")})
        if len(parents) > 1:
            reason = "shared_component_multiple_parents"
        elif len(parents) == 1:
            reason = "shared_component_single_parent"
        else:
            reason = "unresolved_canonical_mapping_no_parent"
        return {
            "schema_version": SCHEMA_VERSION, "canonical_ks": base, "role": role,
            "evidence": "missing", "evidence_scope": "historical_unknown",
            "direction": "ks_parent_variant_component" if edges else "",
            "valid_from": as_of, "valid_to": as_of,
            "resolution": "unresolved_canonical_mapping",
            "reason_code": reason,
            "reason_detail": (f"stripped base {base} is not in ks_items; "
                              f"{len(parents)} KS parent edge(s) in sample; "
                              f"canonical mapping is not unique"),
            "base_not_in_manifest": True,
            "not_finished_item": True,
            "shared_parent_ks": parents,
            "item_missing": not bool(variant_item),
            "current_planning_eligible": False,
            "item": item_meta(variant_item) if variant_item else {},
            "candidate_boms": edges, "excluded_boms": excluded,
        }, "unresolved_canonical_mapping"
    if not variant_item:
        return {
            "schema_version": SCHEMA_VERSION, "canonical_ks": base, "role": role,
            "evidence": "missing", "evidence_scope": "historical_unknown",
            "direction": "", "valid_from": as_of, "valid_to": as_of,
            "resolution": "item_missing", "reason_code": REASON_CODES["item_missing"],
            "reason_detail": f"Item detail missing for {code}",
            "current_planning_eligible": False,
            "item": {}, "candidate_boms": candidates, "excluded_boms": excluded,
        }, "item_missing"
    meta = item_meta(variant_item)
    if meta["disabled"] is None:
        return {
            "schema_version": SCHEMA_VERSION, "canonical_ks": base, "role": role,
            "evidence": "missing", "evidence_scope": "historical_unknown",
            "direction": "", "valid_from": as_of, "valid_to": as_of,
            "resolution": "item_flag_invalid",
            "reason_code": REASON_CODES["item_flag_invalid"],
            "reason_detail": f"Item.disabled is not a recognizable flag: "
                             f"{meta.get('disabled_raw')!r}",
            "current_planning_eligible": False,
            "item": meta, "candidate_boms": candidates, "excluded_boms": excluded,
        }, "item_flag_invalid"
    eligible = [c for c in analyses if c["eligible_at_evidence"]]
    for cand in analyses:
        if not cand["eligible_at_evidence"]:
            excluded.append({"name": cand["name"], "reason": "not_eligible_at_evidence"})
    if not analyses:
        return {
            "schema_version": SCHEMA_VERSION, "canonical_ks": base, "role": role,
            "evidence": "missing", "evidence_scope": "historical_unknown",
            "direction": "", "valid_from": as_of, "valid_to": as_of,
            "resolution": "missing_evidence",
            "reason_code": REASON_CODES["missing_evidence"],
            "reason_detail": "no related BOM found",
            "current_planning_eligible": False,
            "item": meta, "candidate_boms": [], "excluded_boms": excluded,
        }, "missing_evidence"
    if not eligible:
        return {
            "schema_version": SCHEMA_VERSION, "canonical_ks": base, "role": role,
            "evidence": "missing", "evidence_scope": "historical_unknown",
            "direction": analyses[0]["direction"], "valid_from": as_of,
            "valid_to": as_of, "resolution": "missing_evidence",
            "reason_code": REASON_CODES["missing_evidence"],
            "reason_detail": "related BOMs exist but none is eligible at evidence time",
            "current_planning_eligible": False,
            "item": meta, "candidate_boms": candidates, "excluded_boms": excluded,
        }, "missing_evidence"

    valid = [c for c in eligible if c["direction"] == "ks_parent_variant_component"]
    reverse = [c for c in eligible if c["direction"] != "ks_parent_variant_component"]
    for cand in reverse:
        excluded.append({"name": cand["name"], "reason": "unsupported_direction",
                         "candidate": clean_candidate(cand)})
    if not valid:
        return {
            "schema_version": SCHEMA_VERSION, "canonical_ks": base, "role": role,
            "evidence": "missing", "evidence_scope": "historical_unknown",
            "direction": reverse[0]["direction"], "valid_from": as_of,
            "valid_to": as_of, "resolution": "unsupported_direction",
            "reason_code": REASON_CODES["unsupported_direction"],
            "reason_detail": (f"{len(reverse)} eligible BOM(s) are variant-parent "
                              f"direction; not cover consumption"),
            "current_planning_eligible": False,
            "item": meta, "candidate_boms": [], "excluded_boms": excluded,
        }, "unsupported_direction"
    if reverse:
        resolution = "conflict_mixed_direction"
        selected = next((c for c in valid if c["is_default"]), valid[0])
        reason_detail = (f"{len(valid)} valid-direction BOM(s) and "
                         f"{len(reverse)} reversed-direction BOM(s) in sample")
    else:
        signatures = {(c["uom"], c["parent_item"], c["child_item"],
                       round(c["ratio"], 9)) for c in valid}
        resolution = "consistent" if len(signatures) == 1 and all(
            abs(c["ratio"] - 1.0) <= 1e-9 for c in valid) else "conflict"
        selected = next((c for c in valid if c["is_default"]), valid[0])
        reason_detail = (f"{len(valid)} BOM(s), ratio={selected['ratio']:.6g}, "
                         f"direction={selected['direction']}")
    current_eligible = (resolution == "consistent"
                        and meta["disabled"] is False
                        and selected["eligible_at_evidence"])
    uom = selected["uom"]
    record = {
        "schema_version": SCHEMA_VERSION,
        "canonical_ks": base,
        "role": role,
        "evidence": "structural",
        "evidence_scope": "current_structure_only",
        "historical_basis": "",
        "direction": selected["direction"],
        "valid_from": as_of,
        "valid_to": as_of,
        "resolution": resolution,
        "reason_code": REASON_CODES[resolution],
        "reason_detail": reason_detail,
        "current_planning_eligible": current_eligible,
        "ratio": selected["ratio"],
        "uom": uom,
        "component": {
            "item_code": selected["component_item"],
            "qty": selected["component_stock_qty"],
            "uom": uom,
            "stock_qty": selected["component_stock_qty"],
            "stock_uom": uom,
            "conversion_factor": 1,
            "line_count": selected["component_line_count"],
        },
        "output": {
            "item_code": selected["output_item"],
            "qty": selected["output_stock_qty"],
            "uom": uom,
            "stock_qty": selected["output_stock_qty"],
            "stock_uom": uom,
            "conversion_factor": 1,
        },
        "item": meta,
        "bom": {"name": selected["name"], "modified": selected["modified"],
                "sha256": selected["sha256"]},
        "candidate_boms": [clean_candidate(c) for c in valid],
        "excluded_boms": excluded,
    }
    return record, resolution


def main() -> int:
    ap = argparse.ArgumentParser(description="Bounded Item/BOM evidence producer")
    ap.add_argument("--audit", default="out/family_poc/r1_d8c473fe/family_so_lines.audit.jsonl")
    ap.add_argument("--bom", default=str(fp.BOM))
    ap.add_argument("--out-dir", default="out/family_poc/evidence_d8c473fe")
    ap.add_argument("--max-variants", type=int, default=20)
    ap.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--max-http", type=int, default=500)
    ap.add_argument("--max-seconds", type=int, default=900)
    ap.add_argument("--max-item-details", type=int, default=60)
    ap.add_argument("--max-bom-details", type=int, default=100)
    args = ap.parse_args()

    audit_path = Path(args.audit)
    if not audit_path.exists():
        print(f"✗ audit 不存在: {audit_path}", file=sys.stderr)
        return 2
    family = fp.load_family_manifest(Path(args.bom))
    ks_items = set(family["ks_items"])
    rows = load_audit(audit_path)
    selected = select_variants(rows, ks_items, args.max_variants)

    key, secret = iss.load_credentials("prod", iss.resolve_env_files())
    if not key or not secret:
        print("✗ EN 生产凭证未配置", file=sys.stderr)
        return 2
    base_url = iss.ENV_URLS["prod"]
    client = Client(base_url, key, secret, args.max_http, args.max_seconds)

    out_dir = Path(args.out_dir)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    status_reasons: list[str] = []
    query_stats: dict[str, dict] = {}
    item_docs: dict[str, dict] = {}
    bom_docs: dict[str, dict] = {}
    item_codes = sorted({r["code"] for r in selected} | {r["base"] for r in selected})
    bom_items = sorted(set(item_codes))

    try:
        item_rows, query_stats["item_list"] = client.list_all(
            "Item", [["name", "in", item_codes]], ITEM_FIELDS, "Item",
            ITEM_FALLBACK, max_pages=20)
        item_names = sorted({str(r.get("name")) for r in item_rows if r.get("name")})
        for name in item_names[:args.max_item_details]:
            item_docs[name] = client.doc("Item", name, f"Item/{name}")
        if len(item_names) > args.max_item_details:
            status_reasons.append("item_detail_truncated")

        bom_rows, query_stats["bom_list"] = client.list_all(
            "BOM", [["item", "in", bom_items]], BOM_FIELDS, "BOM",
            BOM_FALLBACK, max_pages=20)
        bom_names = sorted({str(r.get("name")) for r in bom_rows if r.get("name")})
        for name in bom_names[:args.max_bom_details]:
            bom_docs[name] = client.doc("BOM", name, f"BOM/{name}")
        if len(bom_names) > args.max_bom_details:
            status_reasons.append("bom_detail_truncated")
    except BudgetExceeded as e:
        status_reasons.append("budget_exceeded")
        print(f"✗ {e}", file=sys.stderr)
    except QueryError as e:
        status_reasons.append("query_failed")
        print(f"✗ {e}", file=sys.stderr)

    items_out = {}
    counts = defaultdict(int)
    reason_counts = defaultdict(int)
    for rec in selected:
        code, base, role = rec["code"], rec["base"], rec["role"]
        analyses = []
        excluded = []
        shared = []
        if base not in ks_items:
            # Shared component (e.g. ND# inner) may appear under many KS parents;
            # keep the raw parent edges instead of using the stripped base.
            for name, bom in bom_docs.items():
                if str(bom.get("item") or "") not in ks_items:
                    continue
                edge = shared_edge(bom, code)
                if edge:
                    shared.append(edge)
        else:
            for name, bom in bom_docs.items():
                if str(bom.get("item") or "") not in (base, code):
                    continue
                cand, reason = analyze_bom(bom, code, base, item_docs)
                if cand:
                    analyses.append(cand)
                elif reason:
                    excluded.append({"name": name, "reason": reason})
        record, resolution = build_record(
            code, base, role, item_docs, analyses, excluded, args.as_of, ks_items,
            shared_edges=shared)
        items_out[code] = record
        counts[resolution] += 1
        reason_counts[str(record.get("reason_code") or "unknown")] += 1

    status = "complete" if not status_reasons else "partial"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "version": f"family_variant_manifest/{args.as_of}",
        "source": SOURCE,
        "site": base_url,
        "as_of": args.as_of,
        "producer": dict(PRODUCER, run_id=run_id),
        "rule_version": RULE_VERSION,
        "items": items_out,
    }
    manifest["payload_sha256"] = sha_obj(manifest)

    raw_items = out_dir / "raw" / "items.jsonl"
    raw_boms = out_dir / "raw" / "boms.jsonl"
    with raw_items.open("w", encoding="utf-8") as f:
        for name in sorted(item_docs):
            f.write(json.dumps({"doctype": "Item", "name": name,
                                "sha256": item_meta(item_docs[name])["sha256"],
                                "doc": item_docs[name]},
                               ensure_ascii=False) + "\n")
    with raw_boms.open("w", encoding="utf-8") as f:
        for name in sorted(bom_docs):
            f.write(json.dumps({"doctype": "BOM", "name": name,
                                "sha256": sha_obj(bom_docs[name]),
                                "doc": bom_docs[name]},
                               ensure_ascii=False) + "\n")

    evidence_path = out_dir / "variant_evidence.json"
    evidence_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    summary = {
        "run_id": run_id,
        "status": status,
        "status_reasons": status_reasons,
        "input": {
            "audit": str(audit_path),
            "audit_sha256": fp.sha256_file(audit_path),
            "family_manifest_sha256": family["sha256"],
            "family_manifest_version": family["version"],
        },
        "selection": [{k: r[k] for k in
                       ("code", "role", "base", "base_in_family", "reasons",
                        "lines", "qty", "selection_note")} for r in selected],
        "query": query_stats,
        "budget": {"http_attempts": client.http_attempts,
                   "http_ok": client.http_ok,
                   "max_http": args.max_http,
                   "elapsed_seconds": round(time.monotonic() - client.started, 1),
                   "max_seconds": args.max_seconds,
                   "errors": client.errors},
        "counts": {"variants": len(selected), "records": len(items_out),
                   "by_resolution": dict(sorted(counts.items())),
                   "by_reason_code": dict(sorted(reason_counts.items()))},
        "historical_evidence": "not_attempted; Codex validates historical boundary in parallel",
        "evidence_scope": "current_structure_only",
        "outputs": {
            "evidence": str(evidence_path),
            "evidence_sha256": fp.sha256_file(evidence_path),
            "payload_sha256": manifest["payload_sha256"],
            "raw_items": str(raw_items),
            "raw_items_sha256": fp.sha256_file(raw_items),
            "raw_boms": str(raw_boms),
            "raw_boms_sha256": fp.sha256_file(raw_boms),
        },
        "notes": [
            "sample of <=20 variants; not a population estimate",
            "current BOM only; no Version/archived evidence in this run",
            "structure does not prove sales equivalence or event de-duplication",
        ],
    }
    (out_dir / "variant_evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "counts": summary["counts"],
                      "by_resolution": summary["counts"]["by_resolution"],
                      "http_attempts": client.http_attempts,
                      "evidence_sha256": summary["outputs"]["evidence_sha256"]},
                     ensure_ascii=False))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
