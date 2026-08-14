from __future__ import annotations

from dataclasses import dataclass, field

from .candidates import CandidateProduct
from .candidates_v2 import CandidateScore, rank_candidates
from .evidence import EvidenceIndex
from .ontology import classify_listing_object


@dataclass(frozen=True)
class V2Decision:
    listing_id: str
    msku: str
    asin: str
    bucket: str
    object_type: str
    object_reasons: tuple[str, ...]
    candidates: tuple[CandidateScore, ...]
    evidence_sources: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def decide_v2(
    listing: dict,
    index: EvidenceIndex,
    catalog: dict[str, CandidateProduct],
    fallback_evidence: dict[str, tuple[str, ...]] | None = None,
) -> V2Decision:
    classification = classify_listing_object(
        msku=listing.get("sku", ""),
        title=listing.get("title", ""),
        parent_sku=listing.get("parentSku", ""),
        fulfillment=listing.get("switchFulfillmentTo", listing.get("fulfillment", "")),
    )
    evidence = fallback_evidence or index.candidates_for_listing(listing)
    ranked = tuple(rank_candidates(listing, evidence, catalog))
    compatible_conflicts = tuple(row for row in ranked if row.is_strong_conflict)
    sources = tuple(
        dict.fromkeys(
            reason
            for reasons in evidence.values()
            for reason in reasons
        )
    )

    object_type = classification.object_type
    if object_type in {"combo", "foam_part", "unknown"}:
        bucket = "special_with_candidate" if ranked else "special"
    elif object_type == "cover":
        bucket = "candidate" if ranked else "special"
    elif len(compatible_conflicts) > 1:
        bucket = "conflict"
    elif ranked:
        top = ranked[0]
        if top.score >= 80 and top.hard_conflicts == 0 and not top.is_strong_conflict:
            bucket = "strong_single"
        elif top.evidence == ("family_candidate",) and top.score < 10:
            bucket = "low_candidate"
        else:
            bucket = "candidate"
    else:
        bucket = "no_candidate"

    return V2Decision(
        listing_id=str(listing.get("listingId", "")),
        msku=str(listing.get("sku", "")),
        asin=str(listing.get("asin", "")),
        bucket=bucket,
        object_type=object_type,
        object_reasons=tuple(classification.reasons),
        candidates=ranked,
        evidence_sources=sources,
    )
