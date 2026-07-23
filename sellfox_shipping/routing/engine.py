"""Rule engine: load YAML rules, evaluate against package data."""

from __future__ import annotations

from pathlib import Path

import yaml

from sellfox_shipping.routing.conditions import evaluate_condition
from sellfox_shipping.routing.models import (
    Condition,
    PackageRoutingData,
    RuleAction,
    RoutingResult,
    RoutingRule,
)


class RuleEngine:
    def __init__(self, rules: list[RoutingRule], exclude_shops: set[str] | None = None):
        self._rules = sorted(rules, key=lambda r: r.priority)
        self._exclude_shops = exclude_shops or set()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RuleEngine":
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        rules = []
        for entry in raw.get("rules", []):
            conditions = []
            for c in entry.get("conditions") or []:
                conditions.append(
                    Condition(field=c["field"], op=c["op"], value=c["value"])
                )
            action = RuleAction(
                carrier=entry["action"]["carrier"],
                label=entry["action"].get("label", entry["action"]["carrier"]),
                reason=entry["action"].get("reason", ""),
            )
            rules.append(
                RoutingRule(
                    name=entry["name"],
                    priority=entry.get("priority", 50),
                    conditions=conditions,
                    match=entry.get("match", "all"),
                    action=action,
                )
            )
        exclude = set(raw.get("exclude_shops", []))
        return cls(rules=rules, exclude_shops=exclude)

    def route(self, data: PackageRoutingData) -> RoutingResult:
        if data.shop_name in self._exclude_shops:
            return RoutingResult(
                carrier="excluded",
                label="排除（平台物流）",
                reason=f"店铺 {data.shop_name} 走平台物流，不参与路由",
                rule_name="exclude_shops",
                matched=False,
            )

        for rule in self._rules:
            if not rule.conditions:
                # Empty conditions = catch-all
                return RoutingResult(
                    carrier=rule.action.carrier,
                    label=rule.action.label,
                    reason=rule.action.reason,
                    rule_name=rule.name,
                    matched=True,
                )

            results = [evaluate_condition(c, data) for c in rule.conditions]
            if rule.match == "all" and all(results):
                return RoutingResult(
                    carrier=rule.action.carrier,
                    label=rule.action.label,
                    reason=rule.action.reason,
                    rule_name=rule.name,
                    matched=True,
                )
            if rule.match == "any" and any(results):
                return RoutingResult(
                    carrier=rule.action.carrier,
                    label=rule.action.label,
                    reason=rule.action.reason,
                    rule_name=rule.name,
                    matched=True,
                )

        return RoutingResult(
            carrier="unknown",
            label="无匹配规则",
            reason="所有规则均不满足",
            rule_name="",
            matched=False,
        )
