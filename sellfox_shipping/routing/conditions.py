"""Condition operator registry and evaluator."""

from __future__ import annotations

from typing import Any, Callable

from sellfox_shipping.routing.models import Condition, PackageRoutingData


def _op_eq(field_val: Any, target: Any) -> bool:
    return field_val == target


def _op_neq(field_val: Any, target: Any) -> bool:
    return field_val != target


def _op_gt(field_val: Any, target: Any) -> bool:
    try:
        return float(field_val) > float(target)
    except (TypeError, ValueError):
        return False


def _op_gte(field_val: Any, target: Any) -> bool:
    try:
        return float(field_val) >= float(target)
    except (TypeError, ValueError):
        return False


def _op_lt(field_val: Any, target: Any) -> bool:
    try:
        return float(field_val) < float(target)
    except (TypeError, ValueError):
        return False


def _op_lte(field_val: Any, target: Any) -> bool:
    try:
        return float(field_val) <= float(target)
    except (TypeError, ValueError):
        return False


def _op_in(field_val: Any, target: Any) -> bool:
    if not isinstance(target, (list, tuple, set)):
        return False
    return field_val in target


def _op_not_in(field_val: Any, target: Any) -> bool:
    if not isinstance(target, (list, tuple, set)):
        return False
    return field_val not in target


def _op_contains(field_val: Any, target: Any) -> bool:
    try:
        return str(target) in str(field_val)
    except (TypeError, ValueError):
        return False


def _op_between(field_val: Any, target: Any) -> bool:
    if not isinstance(target, (list, tuple)) or len(target) != 2:
        return False
    try:
        v = float(field_val)
        return float(target[0]) <= v <= float(target[1])
    except (TypeError, ValueError):
        return False


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": _op_eq,
    "neq": _op_neq,
    "gt": _op_gt,
    "gte": _op_gte,
    "lt": _op_lt,
    "lte": _op_lte,
    "in": _op_in,
    "not_in": _op_not_in,
    "contains": _op_contains,
    "between": _op_between,
}


def evaluate_condition(cond: Condition, data: PackageRoutingData) -> bool:
    field_val = getattr(data, cond.field, None)
    op_fn = OPERATORS.get(cond.op)
    if op_fn is None:
        raise ValueError(f"Unknown operator: {cond.op}")
    return op_fn(field_val, cond.value)
