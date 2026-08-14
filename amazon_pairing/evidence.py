from __future__ import annotations

import re
import unicodedata
from collections import defaultdict


EVIDENCE_ORDER = (
    "msku",
    "asin_shop",
    "asin",
    "fnsku",
    "main_image",
    "title_exact",
    "parent_asin",
    "parent_sku",
)

STRONG_EVIDENCE = {"msku", "asin_shop", "asin", "fnsku"}


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _norm(value) -> str:
    return unicodedata.normalize("NFKC", _text(value)).strip().casefold()


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _norm(title)).strip()


def _add(index: dict[tuple[str, str], dict[str, set[str]]], kind: str, key: str, target: str) -> None:
    if key and not key.endswith(":"):
        index.setdefault((kind, key), {}).setdefault(target, set()).add(kind)


class EvidenceIndex:
    def __init__(self, index: dict[tuple[str, str], dict[str, set[str]]] | None = None):
        self._index = index or {}

    @classmethod
    def build(cls, rows: list[dict]) -> "EvidenceIndex":
        index: dict[tuple[str, str], dict[str, set[str]]] = {}
        for row in rows:
            target = _text(row.get("commoditySku"))
            if not target:
                continue
            msku = _norm(row.get("sku"))
            asin = _text(row.get("asin")).upper()
            shop = _text(row.get("shopId"))
            parent_asin = _text(row.get("parentAsin")).upper()
            parent_sku = _norm(row.get("parentSku"))
            fnsku = _norm(row.get("fnsku"))
            image = _norm(row.get("mainImage"))
            title = _title_key(_text(row.get("title")))
            _add(index, "msku", f"msku:{msku}", target)
            if shop and asin:
                _add(index, "asin_shop", f"asin_shop:{shop}|{asin}", target)
            _add(index, "asin", f"asin:{asin}", target)
            _add(index, "fnsku", f"fnsku:{fnsku}", target)
            _add(index, "main_image", f"image:{image}", target)
            _add(index, "title_exact", f"title:{title}", target)
            _add(index, "parent_asin", f"parent_asin:{parent_asin}", target)
            _add(index, "parent_sku", f"parent_sku:{parent_sku}", target)
        return cls(index)

    def _target_reasons(self, listing: dict) -> dict[str, set[str]]:
        msku = _norm(listing.get("sku"))
        asin = _text(listing.get("asin")).upper()
        shop = _text(listing.get("shopId"))
        parent_asin = _text(listing.get("parentAsin")).upper()
        parent_sku = _norm(listing.get("parentSku"))
        fnsku = _norm(listing.get("fnsku"))
        image = _norm(listing.get("mainImage"))
        title = _title_key(_text(listing.get("title")))
        keys = {
            "msku": f"msku:{msku}",
            "asin_shop": f"asin_shop:{shop}|{asin}" if shop and asin else "",
            "asin": f"asin:{asin}",
            "fnsku": f"fnsku:{fnsku}",
            "main_image": f"image:{image}",
            "title_exact": f"title:{title}",
            "parent_asin": f"parent_asin:{parent_asin}",
            "parent_sku": f"parent_sku:{parent_sku}",
        }
        merged: dict[str, set[str]] = defaultdict(set)
        for kind in EVIDENCE_ORDER:
            key = keys[kind]
            for target, reasons in self._index.get((kind, key), {}).items():
                merged[target].update(reasons)
        return dict(merged)

    def candidates_for_listing(self, listing: dict) -> dict[str, tuple[str, ...]]:
        merged = self._target_reasons(listing)
        return {
            target: tuple(kind for kind in EVIDENCE_ORDER if kind in reasons)
            for target, reasons in merged.items()
        }

    def conflict_targets(self, listing: dict) -> set[str]:
        strong: dict[str, set[str]] = defaultdict(set)
        for target, reasons in self._target_reasons(listing).items():
            for kind in reasons:
                if kind in STRONG_EVIDENCE:
                    strong[target].add(kind)
        return set(strong) if len(strong) > 1 else set()
