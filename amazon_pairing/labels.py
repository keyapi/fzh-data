from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HistoricalPairing:
    msku: str
    target_sku: str
    alias_targets: tuple[str, ...] = ()
    en_targets: tuple[str, ...] = ()
    target_object_type: str = "ordinary"
    confirmed: bool = False


@dataclass(frozen=True)
class LabelAudit:
    tier: str
    usable_for_training: bool
    reasons: tuple[str, ...]


def audit_historical_pairing(pairing: HistoricalPairing) -> LabelAudit:
    reasons: list[str] = []
    if pairing.target_object_type != "ordinary":
        reasons.append("non_ordinary_target")
    if len(set(pairing.alias_targets)) > 1:
        reasons.append("alias_ambiguous")
    if len(set(pairing.en_targets)) > 1:
        reasons.append("en_target_ambiguous")
    if pairing.en_targets and pairing.target_sku not in pairing.en_targets:
        reasons.append("target_contradiction")
    if reasons:
        return LabelAudit("quarantine", False, tuple(reasons))

    if pairing.confirmed:
        return LabelAudit("gold_b", True, ("human_confirmed",))
    if len(pairing.alias_targets) == 1 and pairing.en_targets == (pairing.target_sku,):
        return LabelAudit("gold_a", True, ("unique_alias_en_agreement",))
    return LabelAudit("silver", False, ("current_pairing_only",))
