"""Bridge-side operator scope resolution and ledger filtering.

Scope key is (product_id, branch). The source is a site-private JSON file
maintained by System Manager; there is no inference from warehouse ownership.
Default deny: a user with no active assignment sees no rows.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SCOPE_SCHEMA = "demand-scope/v1"
BRANCHES = ("USNJ", "USTX", "PL")
ENTRY_FIELDS = {"user", "product_id", "branch", "active", "source",
                "valid_from", "approved_by", "notes"}


class ScopeError(ValueError):
    pass


def _clean(payload, strict):
    if not isinstance(payload, dict):
        if strict:
            raise ScopeError("范围文件必须是对象")
        return {"schema": SCOPE_SCHEMA, "assignments": []}
    if set(payload) - {"schema", "assignments", "updated_by", "updated_at"}:
        if strict:
            raise ScopeError("范围文件只能包含 schema/assignments/updated_by/updated_at")
    if payload.get("schema") not in (None, SCOPE_SCHEMA):
        if strict:
            raise ScopeError("范围文件 schema 不受支持")
    raw = payload.get("assignments")
    if not isinstance(raw, list):
        if strict:
            raise ScopeError("assignments 必须是列表")
        return {"schema": SCOPE_SCHEMA, "assignments": []}
    out, seen = [], set()
    for item in raw:
        if not isinstance(item, dict) or set(item) - ENTRY_FIELDS:
            if strict:
                raise ScopeError("范围条目必须是对象且只含支持字段")
            continue
        values = [item.get("user"), item.get("product_id"), item.get("branch")]
        if not all(isinstance(v, str) and v.strip() for v in values):
            if strict:
                raise ScopeError("user/product_id/branch 必须是非空文本")
            continue
        user, product, branch = (v.strip() for v in values)
        if branch not in BRANCHES:
            if strict:
                raise ScopeError("branch 必须是 USNJ/USTX/PL")
            continue
        key = (user, product, branch)
        if key in seen:
            if strict:
                raise ScopeError("重复范围条目")
            continue
        seen.add(key)
        out.append({"user": user, "product_id": product, "branch": branch,
                    "active": bool(item.get("active", True)),
                    "source": str(item.get("source") or ""),
                    "valid_from": str(item.get("valid_from") or ""),
                    "approved_by": str(item.get("approved_by") or ""),
                    "notes": str(item.get("notes") or "")})
    return {"schema": SCOPE_SCHEMA, "assignments": out}


def load(path):
    path = Path(path)
    if not path.exists():
        return {"schema": SCOPE_SCHEMA, "assignments": []}
    try:
        return _clean(json.loads(path.read_text(encoding="utf-8")), strict=False)
    except (OSError, ValueError):
        return {"schema": SCOPE_SCHEMA, "assignments": []}


def save(path, payload, actor):
    normalized = _clean(payload, strict=True)
    normalized["updated_by"] = str(actor)
    from datetime import datetime, timezone
    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return normalized


def keys_for(assignments, user):
    return {(a["product_id"], a["branch"])
            for a in assignments.get("assignments", [])
            if a.get("active", True) and a.get("user") == user}


def all_scope(roles):
    return bool(set(roles) & {"Demand Reviewer", "System Manager"})


def can_read_publication(roles):
    return all_scope(roles)


def in_scope(row, allowed):
    if allowed is None:
        return True
    return bool(row) and (row.get("product_id"), row.get("branch")) in allowed


def filter_state(state, allowed):
    """Return a copy of state limited to allowed (product_id, branch) keys.

    `allowed=None` means all-scope (reviewer/System Manager). Contributors get
    scoped baseline rows/proposals/audit and NO publication objects, because a
    publication embeds every row and would otherwise leak the whole ledger.
    """
    baseline = state.get("baseline")
    if baseline is None:
        return {**state, "coverage": {"visible_rows": 0, "baseline_rows": 0,
                                      "scope": "all" if allowed is None else "assigned"}}
    rows = list(baseline.get("rows", []))
    visible = rows if allowed is None else [
        r for r in rows if (r.get("product_id"), r.get("branch")) in allowed]
    row_ids = {r.get("id") for r in visible}
    proposals = [p for p in state.get("proposals", []) if p.get("row_id") in row_ids]
    proposal_ids = {p.get("id") for p in proposals}
    if allowed is None:
        publications = list(state.get("publications", []))
        audit = list(state.get("audit", []))
    else:
        publications = []
        publication_ids = set()
        audit = [a for a in state.get("audit", [])
                 if a.get("entity") in row_ids | proposal_ids
                 or a.get("entity") in publication_ids
                 or a.get("actor") == state.get("actor")]
    return {**state,
            "baseline": {**baseline, "rows": visible},
            "proposals": proposals,
            "publications": publications,
            "audit": audit,
            "coverage": {"visible_rows": len(visible), "baseline_rows": len(rows),
                         "scope": "all" if allowed is None else "assigned"}}
