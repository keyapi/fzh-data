from __future__ import annotations

from .attributes import extract_attributes
from .candidates import CandidateProduct
from .ontology import classify_listing_object
from .training import CandidateRetriever


def _allowed_object_types(object_type: str) -> set[str]:
    if object_type == "finished_product":
        return {"finished_product", "ordinary"}
    if object_type in {"cover", "foam_part", "combo", "unknown"}:
        return {object_type}
    return {"finished_product", "ordinary"}


def build_fallback_evidence(
    rows: list[dict],
    catalog: list[CandidateProduct],
    max_candidates: int = 20,
    predicted_families: list[tuple[str, ...]] | None = None,
) -> list[dict[str, tuple[str, ...]]]:
    if predicted_families is not None and len(predicted_families) != len(rows):
        raise ValueError("predicted_families must be aligned with rows")
    if not rows or not catalog:
        return []
    families_by_type: dict[str, tuple[str, ...]] = {}
    for object_type in ("finished_product", "cover", "foam_part", "combo", "unknown"):
        families = tuple(
            sorted(
                {
                    product.family
                    for product in catalog
                    if product.object_type in _allowed_object_types(object_type)
                }
            )
        )
        families_by_type[object_type] = families

    prepared = []
    empty = set()
    for index, row in enumerate(rows):
        classification = classify_listing_object(
            msku=row.get("sku", ""),
            title=row.get("title", ""),
            parent_sku=row.get("parentSku", ""),
            fulfillment=row.get("switchFulfillmentTo", row.get("fulfillment", "")),
        )
        families = families_by_type[classification.object_type]
        if predicted_families is not None and predicted_families[index]:
            allowed_family_set = set(families)
            families = tuple(
                family for family in predicted_families[index] if family in allowed_family_set
            )
        if not families:
            empty.add(index)
            continue
        prepared.append(
            (
                index,
                (
                    row.get("sku", ""),
                    row.get("title", ""),
                    families,
                    extract_attributes(f"{row.get('sku', '')} {row.get('title', '')}"),
                ),
            )
        )

    retriever = CandidateRetriever(catalog)
    selected_many = retriever.retrieve_many(
        [query for _, query in prepared],
        max_candidates,
    )
    result: list[dict[str, tuple[str, ...]]] = [{} for _ in rows]
    for (row_index, _), selected in zip(prepared, selected_many):
        result[row_index] = {
            catalog[catalog_index].sku: ("family_candidate",)
            for catalog_index in selected
            if catalog_index < len(catalog)
        }
    for index in empty:
        result[index] = {}
    return result
