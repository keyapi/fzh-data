"""Pure helpers for independent expedite and new-order recommendations."""

from __future__ import annotations

import math
from datetime import date
from typing import Iterable

import numpy as np


def split_actions(net_need, late_supply, blocked: bool = False) -> dict:
    """Split a positive net gap into late-supply expedite and new-order actions.

    ``remaining_need`` preserves the unrounded balance; ``new_order_qty`` is
    rounded up to whole units. Unknown inputs and explicitly blocked rows never
    produce executable actions.
    """
    try:
        need = float(net_need)
        late = float(late_supply)
    except (TypeError, ValueError):
        need = late = math.nan
    if not math.isfinite(need) or not math.isfinite(late) or blocked:
        return {"expedite_qty": None, "new_order_qty": None,
                "remaining_need": need if math.isfinite(need) else None,
                "actions": ["观察"]}

    gap = max(0.0, need)
    expedite = min(gap, max(0.0, late))
    remaining = max(0.0, gap - expedite)
    new_order = int(math.ceil(remaining - 1e-9)) if remaining > 0 else 0
    actions = []
    if expedite > 0:
        actions.append("催已有")
    if new_order > 0:
        actions.append("新补")
    if not actions:
        actions.append("不补")
    return {"expedite_qty": expedite, "new_order_qty": new_order,
            "remaining_need": remaining, "actions": actions}


def action_export_fields(split: dict, legacy_action: str,
                          new_order_qty=None) -> dict:
    """Assemble authoritative export quantities from a split and optional MOQ rounding."""
    actions = list(split.get("actions", []))
    blocked = (legacy_action == "观察" or "观察" in actions
               or split.get("expedite_qty") is None
               or split.get("new_order_qty") is None)
    if blocked:
        return {"action": legacy_action, "independent_actions": "观察",
                "has_expedite_action": False, "has_new_order_action": False,
                "expedite_qty": None, "new_order_qty": None, "qty": None,
                "remaining_need": split.get("remaining_need")}

    has_expedite = "催已有" in actions
    has_new_order = "新补" in actions
    if has_new_order:
        quantity = split["new_order_qty"] if new_order_qty is None else new_order_qty
    else:
        quantity = 0
    expedite = split["expedite_qty"] if has_expedite else 0
    return {"action": legacy_action, "independent_actions": "、".join(actions),
            "has_expedite_action": has_expedite,
            "has_new_order_action": has_new_order,
            "expedite_qty": expedite, "new_order_qty": quantity,
            "qty": quantity, "remaining_need": split.get("remaining_need")}


def horizon_net_need(total_demand_quantile, available_supply, cg_credit=0) -> float | None:
    """Net an already horizon-total demand quantile against available supply."""
    try:
        demand, supply, credit = (float(total_demand_quantile),
                                  float(available_supply), float(cg_credit))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (demand, supply, credit)):
        return None
    return demand - supply - credit


def classify_cg_inventory(records: Iterable[dict], *, source_usable: bool = True) -> tuple[dict, dict, list]:
    """Separate explicitly eligible, fresh CG credits from uncredited source rows.

    The returned unknown map is keyed by (EN item, owner pool). Raw rows remain
    in diagnostics with a disposition, so omitted CG stock is never mistaken for
    an observed zero. Missing owner/item rows remain diagnostics only.
    """
    credits: dict[tuple[str, str], float] = {}
    unknown: dict[tuple[str, str], dict] = {}
    diagnostics = []

    def explicit_true(value) -> bool:
        return value is True or isinstance(value, np.bool_) and bool(value)

    def explicit_false(value) -> bool:
        if value is False or isinstance(value, np.bool_) and not bool(value):
            return True
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            return float(value) == 0.0
        return isinstance(value, str) and value.strip().lower() in {"false", "0"}

    for source in records:
        row = dict(source)
        status = str(row.get("cg_status", "")).strip().lower()
        if "cg_eligible" in row and row.get("cg_eligible") is not None:
            eligible = explicit_true(row.get("cg_eligible"))
            eligibility_conflict = status == "cg_eligible" and not eligible
        else:
            eligible = status == "cg_eligible"
            eligibility_conflict = False
        stale = row.get("cg_stale", row.get("stale"))
        fresh = source_usable and explicit_false(stale)
        try:
            qty = float(row.get("cg_available"))
            qty_known = math.isfinite(qty)
        except (TypeError, ValueError):
            qty, qty_known = None, False

        key_values = (row.get("erp_item_code"), row.get("cg_owner"))
        key = tuple(str(value).strip() for value in key_values)
        has_key = all(value and value.lower() != "nan" for value in key)
        disposition = "credited" if eligible and fresh and qty_known else "unknown_not_credited"
        row["cg_consumption_disposition"] = disposition
        diagnostics.append(row)
        if not has_key:
            continue
        if disposition == "credited":
            credits[key] = credits.get(key, 0.0) + qty
            continue
        group = unknown.setdefault(key, {"unknown_qty": 0.0,
                                         "unknown_qty_complete": True,
                                         "row_count": 0,
                                         "reasons": set()})
        group["row_count"] += 1
        if qty_known:
            group["unknown_qty"] += qty
        else:
            group["unknown_qty_complete"] = False
        if not eligible:
            group["reasons"].add("cg_not_explicitly_eligible")
        if eligibility_conflict:
            group["reasons"].add("cg_eligibility_conflict")
        if not fresh:
            group["reasons"].add("cg_stale_or_staleness_unknown" if source_usable
                                 else "cg_source_future_or_date_unknown")
        if not qty_known:
            group["reasons"].add("cg_available_unknown")

    for group in unknown.values():
        group["reasons"] = sorted(group["reasons"])
        if not group["unknown_qty_complete"]:
            group["unknown_qty_known_subtotal"] = group["unknown_qty"]
            group["unknown_qty"] = None
    return credits, unknown, diagnostics


def route_candidates_for_pool(head_samples: dict, pool: str) -> list[tuple[str, str]]:
    """List only explicitly observed, named main/last-mile pairs for a pool."""
    mains = {"sea_regular", "sea_fast", "air"}
    lasts = {"truck", "express"}
    routes = {(main, last) for (route_pool, main, last), values in head_samples.items()
              if route_pool == pool and values and main in mains and last in lasts}
    order_main = ("sea_regular", "sea_fast", "air")
    order_last = ("truck", "express")
    return sorted(routes, key=lambda route: (order_main.index(route[0]),
                                              order_last.index(route[1])))


def select_route_candidate(routes: list[tuple], need_days: float) -> tuple[tuple | None, bool]:
    """Select the first priority-ordered route that fits; otherwise the fastest known."""
    fitting = [route for route in routes if route[2]["p90"] <= float(need_days)]
    if fitting:
        return fitting[0], True
    if routes:
        return min(routes, key=lambda route: route[2]["p90"]), False
    return None, False


def production_samples_for_pool_role(production: dict, pool: str, role: str) -> tuple[list, str]:
    """Use role-specific samples or a clearly labeled same-pool fallback."""
    exact = list(production.get((pool, role), []))
    if exact:
        return exact, "role_specific"
    all_roles = list(production.get((pool, "__all_roles__"), []))
    if all_roles:
        return all_roles, "pool_all_roles_fallback"
    fallback = [day for (sample_pool, sample_role), days in production.items()
                if sample_pool == pool and sample_role != "__all_roles__"
                for day in days]
    return fallback, "pool_all_roles_fallback" if fallback else "unavailable"


def bootstrap_independent_route(production_days, head_days, n: int = 5000,
                                seed: int = 42) -> dict | None:
    """Combine independent observed production and physical-route samples."""
    production = np.asarray(production_days, dtype=float)
    head = np.asarray(head_days, dtype=float)
    production = production[np.isfinite(production) & (production >= 0)]
    head = head[np.isfinite(head) & (head >= 0)]
    if not len(production) or not len(head):
        return None
    rng = np.random.default_rng(seed)
    totals = rng.choice(production, size=n, replace=True) + rng.choice(head, size=n, replace=True)
    return {"p50": float(np.quantile(totals, 0.5)),
            "p90": float(np.quantile(totals, 0.9)),
            "n_production": int(len(production)), "n_head": int(len(head)),
            "stage_independence_assumption": True,
            "no_service_guarantee": True}


def unknown_age_transit_days(stage: str, production_days: float,
                             full_transit_days: float) -> float:
    """Use a full head-haul observation for unknown-age stages, without production."""
    if stage not in {"intr", "wait", "po"}:
        raise ValueError(f"unsupported supply stage: {stage}")
    return float(full_transit_days)


def select_snapshot_date(snapshot_dates: Iterable[str], as_of: str | date) -> str | None:
    """Choose the latest snapshot no later than as-of; never consume future data."""
    cutoff = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    eligible = []
    for raw in snapshot_dates:
        try:
            parsed = date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            continue
        if parsed <= cutoff:
            eligible.append(parsed)
    return max(eligible).isoformat() if eligible else None
