"""Routing rule engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: object  # str | int | float | list


@dataclass(frozen=True)
class RuleAction:
    carrier: str
    label: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RoutingRule:
    name: str
    priority: int
    conditions: list[Condition]
    match: str  # "all" | "any"
    action: RuleAction


@dataclass(frozen=True)
class RoutingResult:
    carrier: str
    label: str
    reason: str
    rule_name: str
    matched: bool


@dataclass
class PackageRoutingData:
    """Flat field bag extracted from package + dims + items for rule evaluation."""
    package_sn: str = ""
    shop_name: str = ""
    warehouse_name: str = ""
    destination_country: str = ""
    destination_state: str = ""
    postal_code: str = ""
    longest_side_cm: float = 0.0
    second_side_cm: float = 0.0
    third_side_cm: float = 0.0
    weight_kg: float = 0.0
    total_quantity: int = 0
    channel_name: str = ""
