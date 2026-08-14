from __future__ import annotations

import re
from dataclasses import dataclass

from .attributes import extract_attributes, merge_attributes
from .candidates import CandidateProduct
from .evidence import EVIDENCE_ORDER, STRONG_EVIDENCE
from .ontology import ObjectClassification, classify_listing_object, normalize_size_terms


EVIDENCE_SCORE = {
    "msku": 110,
    "asin_shop": 105,
    "asin": 100,
    "fnsku": 90,
    "msku_affinity": 55,
    "main_image": 85,
    "title_exact": 60,
    "parent_asin": 40,
    "parent_sku": 35,
}

EVIDENCE_PRIORITY = {kind: index for index, kind in enumerate(EVIDENCE_ORDER)}
COLOR_KEYS = ("蓝", "黑", "白", "灰", "红", "橙", "黄", "绿", "紫", "棕", "粉", "米", "咖", "驼", "奶", "象牙")
MAX_RANKED_EVIDENCE = 40


@dataclass(frozen=True)
class CandidateScore:
    sku: str
    name: str
    object_type: str
    score: float
    evidence: tuple[str, ...]
    hard_conflicts: int
    is_strong_conflict: bool


def _agreement(query: tuple[str, ...], product: tuple[str, ...]) -> bool:
    return bool(query and product and not set(query).isdisjoint(product))


def _color_keys(values: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(key for key in COLOR_KEYS if key in value)
    return result


def _color_agreement(query: tuple[str, ...], product: tuple[str, ...]) -> bool:
    return bool(query and product and _color_keys(query).intersection(_color_keys(product)))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.casefold()))

def _fabric_agreement(query: tuple[str, ...], product: tuple[str, ...]) -> bool:
    return bool(query and product and _tokens("".join(query)).intersection(_tokens("".join(product))))


def _token_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    union = len(left_tokens | right_tokens)
    return len(left_tokens & right_tokens) / union if union else 0.0


def _hard_conflicts(
    classification: ObjectClassification,
    product: CandidateProduct,
    attrs,
    sizes: tuple[str, ...],
) -> int:
    conflicts = 0
    if classification.object_type in {"cover", "foam_part", "unknown"}:
        if product.object_type != classification.object_type:
            conflicts += 1
    elif classification.object_type == "finished_product":
        if product.object_type not in {"finished_product", "ordinary"}:
            conflicts += 1

    if sizes and product.attributes.size.values and set(sizes).isdisjoint(product.attributes.size.values):
        conflicts += 1
    if attrs.color.values and product.attributes.color.values:
        if not _color_agreement(attrs.color.values, product.attributes.color.values):
            conflicts += 1
    if attrs.fabric.values and product.attributes.fabric.values:
        if not _fabric_agreement(attrs.fabric.values, product.attributes.fabric.values):
            conflicts += 1
    if attrs.count.values and product.attributes.count.values:
        if set(attrs.count.values).isdisjoint(product.attributes.count.values):
            conflicts += 1
    return conflicts


def rank_candidates(
    listing: dict,
    evidence: dict[str, tuple[str, ...]],
    catalog: dict[str, CandidateProduct],
) -> list[CandidateScore]:
    classification = classify_listing_object(
        msku=listing.get("sku", ""),
        title=listing.get("title", ""),
        parent_sku=listing.get("parentSku", ""),
        fulfillment=listing.get("switchFulfillmentTo", listing.get("fulfillment", "")),
    )
    text = f"{listing.get('sku', '')} {listing.get('title', '')}"
    attrs = merge_attributes(
        extract_attributes(listing.get("title", "")),
        extract_attributes(listing.get("sku", ""), word_boundaries=False),
    )
    size_terms = tuple(normalize_size_terms(listing.get("title", "")))
    agreement_size_terms = tuple(
        normalize_size_terms(listing.get("sku", ""), allow_bare=True)
    )
    reliable_size = attrs.size.values if attrs.size.reliable else ()
    sizes = tuple(dict.fromkeys((*reliable_size, *size_terms)))
    agreement_sizes = tuple(dict.fromkeys((*sizes, *agreement_size_terms)))

    strong_targets = {
        sku
        for sku, reasons in evidence.items()
        if any(reason in STRONG_EVIDENCE for reason in reasons)
    }
    ordered = sorted(
        evidence.items(),
        key=lambda item: (
            -max(EVIDENCE_SCORE.get(reason, 0) for reason in item[1]),
            min(EVIDENCE_PRIORITY.get(reason, 99) for reason in item[1]),
            item[0],
        ),
    )
    selected: dict[str, tuple[str, ...]] = dict(ordered[:MAX_RANKED_EVIDENCE])
    for sku in strong_targets:
        selected.setdefault(sku, evidence[sku])

    results: list[CandidateScore] = []
    for sku, reasons in selected.items():
        product = catalog.get(sku)
        if product is None:
            continue
        base = max(EVIDENCE_SCORE.get(reason, 0) for reason in reasons)
        base += sum(1 for reason in reasons if reason not in {"parent_asin", "parent_sku"})
        agreements = 0
        if agreement_sizes and _agreement(agreement_sizes, product.attributes.size.values):
            agreements += 1
        if _color_agreement(attrs.color.values, product.attributes.color.values):
            agreements += 1
        if _fabric_agreement(attrs.fabric.values, product.attributes.fabric.values):
            agreements += 1
        if attrs.count.values and _agreement(attrs.count.values, product.attributes.count.values):
            agreements += 1
        similarity = _token_similarity(text, product.name)
        conflicts = _hard_conflicts(classification, product, attrs, sizes)
        score = base + agreements * 6 + similarity * 12 - conflicts * 30
        results.append(
            CandidateScore(
                sku=product.sku,
                name=product.name,
                object_type=product.object_type,
                score=round(score, 4),
                evidence=tuple(reasons),
                hard_conflicts=conflicts,
                is_strong_conflict=False,
            )
        )

    sorted_results = sorted(
        results,
        key=lambda row: (-row.score, row.hard_conflicts, row.sku),
    )
    top_strong = [
        row
        for row in sorted_results[:5]
        if row.sku in strong_targets and row.hard_conflicts == 0 and row.sku in catalog
    ]
    top_strong_families = {catalog[row.sku].family for row in top_strong}
    cross_family_conflict = len(top_strong_families) > 1
    results = [
        CandidateScore(
            sku=row.sku,
            name=row.name,
            object_type=row.object_type,
            score=row.score,
            evidence=row.evidence,
            hard_conflicts=row.hard_conflicts,
            is_strong_conflict=cross_family_conflict and row in top_strong,
        )
        for row in results
    ]
    return sorted(
        results,
        key=lambda row: (
            -row.is_strong_conflict,
            -row.score,
            row.hard_conflicts,
            row.sku,
        ),
    )
