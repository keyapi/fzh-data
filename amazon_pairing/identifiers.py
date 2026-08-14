from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


@dataclass(frozen=True)
class _IdentifierRow:
    msku: str
    target_sku: str


class IdentifierAffinityIndex:
    def __init__(
        self,
        vectorizer: TfidfVectorizer,
        matrix,
        rows: list[_IdentifierRow],
    ):
        self.vectorizer = vectorizer
        self.matrix = matrix
        self.rows = rows

    @classmethod
    def build(cls, rows: list[dict]) -> "IdentifierAffinityIndex":
        clean = [
            _IdentifierRow(str(row.get("sku") or ""), str(row.get("commoditySku") or ""))
            for row in rows
            if str(row.get("sku") or "") and str(row.get("commoditySku") or "")
        ]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        matrix = vectorizer.fit_transform([row.msku.casefold() for row in clean]) if clean else None
        return cls(vectorizer, matrix, clean)

    def candidates_for_listing(self, listing: dict, max_targets: int = 20) -> dict[str, tuple[str, ...]]:
        if self.matrix is None or not str(listing.get("sku") or ""):
            return {}
        vector = self.vectorizer.transform([str(listing.get("sku") or "").casefold()])
        scores = np.asarray(linear_kernel(vector, self.matrix)[0])
        order = np.argsort(-scores)
        result: dict[str, tuple[str, ...]] = {}
        for index in order:
            if len(result) >= max_targets:
                break
            target = self.rows[int(index)].target_sku
            result.setdefault(target, ("msku_affinity",))
        return result
