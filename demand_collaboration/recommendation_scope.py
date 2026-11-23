"""Row-level scope for read-only recommendation snapshots.

Scope is (user, sku, branch) from a site-private JSON file. Default deny for
operators; reviewers and System Managers see the full snapshot. The stored
snapshot is never modified; this module only produces a filtered view.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "demand-recommendation-scope/v1"


def _truth(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    return str(value).strip().lower() not in {"false", "0", "no", "n", "否", "off", "disabled"}
BRANCHES = {"USNJ", "USTX", "PL", "*"}


def load(path):
    if not path:
        return {"schema": SCHEMA, "assignments": []}
    p = Path(path)
    if not p.exists():
        return {"schema": SCHEMA, "assignments": []}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": SCHEMA, "assignments": []}
    out = []
    for item in payload.get("assignments", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        user, sku, branch = item.get("user"), item.get("sku"), item.get("branch")
        if not all(isinstance(v, str) and v.strip() for v in (user, sku, branch)):
            continue
        if branch not in BRANCHES:
            continue
        active = (_truth(item.get("active", True)) and _truth(item.get("valid", True))
                  and _truth(item.get("enabled", True)))
        out.append({"user": user.strip(), "sku": sku.strip(), "branch": branch,
                    "active": active})
    return {"schema": SCHEMA, "assignments": out}


def allows(user, role, row, assignments):
    if str(role).lower() in {"reviewer", "system manager", "system"}:
        return True
    branch = str(row.get("market") or row.get("customer") or "").upper()
    for a in assignments:
        if not a["active"] or a["user"] != user:
            continue
        if a["sku"] == "*" or a["sku"] == row.get("sku"):
            if a["branch"] == "*" or a["branch"] == branch:
                return True
            if row.get("ownership_pending") and a["branch"] in {"USNJ", "*"}:
                return True
    return False


def filter_snapshot(snapshot, user, role, path):
    if not snapshot:
        return None
    assignments = load(path)["assignments"]
    rows = [row for row in snapshot.get("rows", []) if allows(user, role, row, assignments)]
    view = dict(snapshot)
    view["rows"] = rows
    if str(role).lower() not in {"reviewer", "system manager", "system"}:
        # Rejected/skipped diagnostics can contain out-of-scope SKUs.
        view["rejected"] = []
        view["skipped"] = []
    view["visible_count"] = len(rows)
    view["scope_filtered"] = True
    return view
