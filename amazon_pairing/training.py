from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import linear_kernel
import numpy as np

from .attributes import extract_attributes
from .candidates import CandidateProduct, ListingQuery
from .features import build_pair_features
from .ranking import PairExample


@dataclass(frozen=True)
class TrainingListing:
    msku: str
    title: str
    asin: str
    target_sku: str
    family: str


class FamilyClassifier:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        self.model = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced")

    @staticmethod
    def _text(msku: str, title: str) -> str:
        return f"{msku} {title}".lower()

    def fit(self, rows: list[TrainingListing]) -> "FamilyClassifier":
        matrix = self.vectorizer.fit_transform([self._text(row.msku, row.title) for row in rows])
        self.model.fit(matrix, [row.family for row in rows])
        return self

    def predict(self, msku: str, title: str, top_k: int = 2) -> tuple[tuple[str, float], ...]:
        matrix = self.vectorizer.transform([self._text(msku, title)])
        probabilities = self.model.predict_proba(matrix)[0]
        ranked = sorted(zip(self.model.classes_, probabilities), key=lambda row: row[1], reverse=True)
        return tuple((str(family), float(score)) for family, score in ranked[:top_k])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path) -> "FamilyClassifier":
        return joblib.load(path)


class CandidateRetriever:
    def __init__(self, catalog: list[CandidateProduct]):
        self.catalog = catalog
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        self.matrix = self.vectorizer.fit_transform(
            [f"{product.sku} {product.name}".lower() for product in catalog]
        )
        self.by_family: dict[str, list[int]] = {}
        for index, product in enumerate(catalog):
            self.by_family.setdefault(product.family, []).append(index)

    @staticmethod
    def _attribute_priority(attributes, product: CandidateProduct) -> tuple[int, int]:
        if attributes is None:
            return 0, 0
        agreements = 0
        conflicts = 0
        for query_value, product_value in (
            (attributes.size, product.attributes.size),
            (attributes.color, product.attributes.color),
            (attributes.fabric, product.attributes.fabric),
            (attributes.count, product.attributes.count),
        ):
            if not query_value.reliable or not query_value.values or not product_value.values:
                continue
            if set(query_value.values).isdisjoint(product_value.values):
                conflicts += 1
            else:
                agreements += 1
        return conflicts, agreements

    def retrieve(
        self, msku: str, title: str, families: tuple[str, ...], limit: int, attributes=None
    ) -> list[int]:
        eligible = [index for family in families for index in self.by_family.get(family, [])]
        vector = self.vectorizer.transform([f"{msku} {title}".lower()])
        scored = []
        for index in eligible:
            conflicts, agreements = self._attribute_priority(attributes, self.catalog[index])
            similarity = float(linear_kernel(vector, self.matrix[index])[0, 0])
            scored.append((index, conflicts, agreements, similarity))
        compatible = [row for row in scored if row[1] == 0]
        if compatible:
            scored = compatible
        scored.sort(key=lambda row: (-row[2], -row[3], row[0]))
        return [index for index, _, _, _ in scored[:limit]]

    def retrieve_many(
        self, queries: list[tuple], limit: int
    ) -> list[list[int]]:
        if not queries:
            return []
        query_matrix = self.vectorizer.transform(
            [f"{query[0]} {query[1]}".lower() for query in queries]
        )
        results: list[list[int] | None] = [None] * len(queries)
        grouped: dict[tuple[str, ...], list[int]] = {}
        for index, query in enumerate(queries):
            families = query[2]
            grouped.setdefault(tuple(families), []).append(index)
        for families, query_indices in grouped.items():
            eligible = [index for family in families for index in self.by_family.get(family, [])]
            if not eligible:
                for query_index in query_indices:
                    results[query_index] = []
                continue
            similarities = linear_kernel(query_matrix[query_indices], self.matrix[eligible])
            for local_index, query_index in enumerate(query_indices):
                scores = similarities[local_index]
                attributes = queries[query_index][3] if len(queries[query_index]) > 3 else None
                ranked = []
                for local_position, catalog_index in enumerate(eligible):
                    conflicts, agreements = self._attribute_priority(attributes, self.catalog[catalog_index])
                    ranked.append((catalog_index, conflicts, agreements, float(scores[local_position])))
                compatible = [row for row in ranked if row[1] == 0]
                if compatible:
                    ranked = compatible
                ranked.sort(key=lambda row: (-row[2], -row[3], row[0]))
                results[query_index] = [row[0] for row in ranked[:limit]]
        return [result or [] for result in results]


def build_pair_examples(
    listings: list[TrainingListing],
    catalog: list[CandidateProduct],
    max_candidates: int = 20,
    predicted_families: list[tuple[str, ...]] | None = None,
    retriever: CandidateRetriever | None = None,
    inject_positive: bool = True,
) -> tuple[list[PairExample], float]:
    catalog_by_sku = {product.sku: product for product in catalog}
    catalog_index_by_sku = {product.sku: index for index, product in enumerate(catalog)}
    retriever = retriever or CandidateRetriever(catalog)
    examples: list[PairExample] = []
    retrieved_positive = 0
    if predicted_families is not None and len(predicted_families) != len(listings):
        raise ValueError("Predicted families must align one-to-one with listings")
    family_sets = predicted_families or [(listing.family,) for listing in listings]
    listing_attributes = [extract_attributes(f"{listing.msku} {listing.title}") for listing in listings]
    selected_many = retriever.retrieve_many(
        [
            (listing.msku, listing.title, tuple(families), attributes)
            for listing, families, attributes in zip(listings, family_sets, listing_attributes)
        ],
        max_candidates,
    )

    for index, (listing, families, selected) in enumerate(zip(listings, family_sets, selected_many)):
        positive = catalog_by_sku.get(listing.target_sku)
        positive_index = catalog_index_by_sku.get(listing.target_sku)
        if positive_index is not None and positive_index in selected:
            retrieved_positive += 1
        if inject_positive and positive_index is not None and positive_index not in selected:
            selected = ([positive_index] + selected)[:max_candidates]
        if inject_positive and positive_index is not None and not any(
            position != positive_index for position in selected
        ):
            broad = retriever.retrieve(
                listing.msku, listing.title, tuple(families), max_candidates, attributes=None
            )
            hard_negative = next((position for position in broad if position != positive_index), None)
            if hard_negative is not None:
                selected = (selected + [hard_negative])[:max_candidates]

        attributes = listing_attributes[index]
        query = ListingQuery(
            msku=listing.msku,
            title=listing.title,
            predicted_families=tuple(families),
            attributes=attributes,
        )
        query_id = f"{listing.msku.casefold()}|{listing.asin.upper()}|{index}"
        for position in selected:
            product = catalog[position]
            examples.append(
                PairExample(
                    query_id=query_id,
                    msku=listing.msku,
                    asin=listing.asin,
                    product=product,
                    label=int(product.sku == listing.target_sku),
                    features=build_pair_features(query, product),
                )
            )
    recall = retrieved_positive / len(listings) if listings else 0.0
    return examples, recall
