from __future__ import annotations

from difflib import SequenceMatcher

from .candidates import CandidateProduct, ListingQuery


def _attribute_features(prefix, query_value, product_value):
    query_set = set(query_value.values)
    product_set = set(product_value.values)
    comparable = bool(query_set and product_set)
    agreement = comparable and not query_set.isdisjoint(product_set)
    contradiction = query_value.reliable and comparable and not agreement
    return {
        f"{prefix}_known": float(comparable),
        f"{prefix}_agreement": float(agreement),
        f"{prefix}_contradiction": float(contradiction),
    }


def build_pair_features(query: ListingQuery, product: CandidateProduct) -> dict[str, float]:
    features = {
        "family_match": float(product.family in query.predicted_families),
        "exact_target": float(product.sku in query.exact_targets),
        "asin_target": float(product.sku in query.asin_targets),
        "msku_sku_similarity": SequenceMatcher(None, query.msku.lower(), product.sku.lower()).ratio(),
        "title_name_similarity": SequenceMatcher(None, query.title.lower(), product.name.lower()).ratio(),
    }
    for prefix, query_value, product_value in (
        ("size", query.attributes.size, product.attributes.size),
        ("color", query.attributes.color, product.attributes.color),
        ("fabric", query.attributes.fabric, product.attributes.fabric),
        ("count", query.attributes.count, product.attributes.count),
    ):
        features.update(_attribute_features(prefix, query_value, product_value))
    features["reliable_conflicts"] = sum(
        features[f"{prefix}_contradiction"] for prefix in ("size", "color", "fabric", "count")
    )
    return features
