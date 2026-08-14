from __future__ import annotations

from dataclasses import dataclass

from .attributes import ListingAttributes


@dataclass(frozen=True)
class CandidateProduct:
    sku: str
    family: str
    name: str
    attributes: ListingAttributes
    object_type: str = "ordinary"


@dataclass(frozen=True)
class ListingQuery:
    msku: str
    title: str
    predicted_families: tuple[str, ...]
    attributes: ListingAttributes
    exact_targets: tuple[str, ...] = ()
    asin_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateMatch:
    product: CandidateProduct
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CandidateResult:
    candidates: tuple[CandidateMatch, ...]
    used_fallback: bool = False
    warnings: tuple[str, ...] = ()


def _size_compatible(query_value, product_value) -> bool:
    if not (query_value.reliable and query_value.values and product_value.values):
        return True
    query_set = set(query_value.values)
    product_set = set(product_value.values)
    if not query_set.isdisjoint(product_set):
        return True
    query_tokens = {token for value in query_set for token in value.split("x") if token}
    product_tokens = {token for value in product_set for token in value.split("x") if token}
    return not query_tokens.isdisjoint(product_tokens)


def _reliable_conflict(query_value, product_value) -> bool:
    return bool(
        query_value.reliable
        and query_value.values
        and product_value.values
        and set(query_value.values).isdisjoint(product_value.values)
    )


def _has_reliable_conflict(query: ListingQuery, product: CandidateProduct) -> bool:
    if not _size_compatible(query.attributes.size, product.attributes.size):
        return True
    return any(
        _reliable_conflict(query_value, product_value)
        for query_value, product_value in (
            (query.attributes.color, product.attributes.color),
            (query.attributes.fabric, product.attributes.fabric),
            (query.attributes.count, product.attributes.count),
        )
    )


def generate_candidates(
    query: ListingQuery, catalog: tuple[CandidateProduct, ...], limit: int = 20
) -> CandidateResult:
    by_sku = {product.sku: product for product in catalog}
    result: list[CandidateMatch] = []
    seen: set[str] = set()

    for sku in query.exact_targets:
        product = by_sku.get(sku)
        if product and product.object_type == "ordinary":
            result.append(CandidateMatch(product, ("exact_target",)))
            seen.add(sku)

    for sku in query.asin_targets:
        product = by_sku.get(sku)
        if product and product.object_type == "ordinary" and sku not in seen:
            result.append(CandidateMatch(product, ("unique_asin_target",)))
            seen.add(sku)

    family_pool = [
        product
        for product in catalog
        if product.object_type == "ordinary" and product.family in query.predicted_families
    ]
    filtered = [product for product in family_pool if not _has_reliable_conflict(query, product)]
    used_fallback = bool(family_pool and not filtered)
    pool = family_pool if used_fallback else filtered

    for product in pool:
        if product.sku not in seen:
            result.append(CandidateMatch(product, ("family_candidate",)))
            seen.add(product.sku)
        if len(result) >= limit:
            break

    warnings = ("reliable_attributes_removed_all_candidates",) if used_fallback else ()
    return CandidateResult(tuple(result[:limit]), used_fallback, warnings)
