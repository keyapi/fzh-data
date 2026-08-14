from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .data import AmazonListing, _key, _text


MSKU_SUFFIXES = (
    "-fba",
    "-afn",
    "-mfn",
    "-us",
    "-uk",
    "-ca",
    "-de",
    "-fr",
    "-it",
    "-es",
    "-eu",
    "-au",
)
CUSTOMER_PREFIX = re.compile(r"^(?:nb[/_\-]?)?", re.IGNORECASE)
TRAILING_INDEX = re.compile(r"-\d+$")


def normalize_customer_code(value: str) -> str:
    text = CUSTOMER_PREFIX.sub("", _text(value)).strip("/").casefold()
    return text


def msku_variants(msku: str) -> tuple[str, ...]:
    current = _key(msku)
    if not current:
        return ()
    seen = [current]
    changed = True
    while changed:
        changed = False
        for suffix in MSKU_SUFFIXES:
            if current.endswith(suffix) and current != suffix:
                current = current[: -len(suffix)].rstrip("-_")
                if current and current not in seen:
                    seen.append(current)
                    changed = True
        match = TRAILING_INDEX.search(current)
        if match and current.count("-") >= 1:
            current = current[: match.start()]
            if current and current not in seen:
                seen.append(current)
                changed = True
    return tuple(seen)


@dataclass
class LiveEvidenceMaps:
    msku: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    asin: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    parent_sku: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    parent_asin: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    image: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    near_msku: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    customer_code: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


def add_target(index: dict[str, set[str]], key: str, sku: str) -> None:
    if key and sku:
        index[key].add(sku)


def build_live_maps(
    matched: list[AmazonListing],
    customer_code_index: dict[str, set[str]] | None = None,
) -> LiveEvidenceMaps:
    maps = LiveEvidenceMaps()
    if customer_code_index:
        for code, skus in customer_code_index.items():
            for sku in skus:
                add_target(maps.customer_code, normalize_customer_code(code), sku)
    for row in matched:
        sku = row.target_sku
        if not sku:
            continue
        add_target(maps.msku, _key(row.msku), sku)
        add_target(maps.asin, row.asin, sku)
        add_target(maps.parent_sku, _key(row.parent_sku), sku)
        add_target(maps.parent_asin, row.parent_asin, sku)
        add_target(maps.image, row.image_url, sku)
        for variant in msku_variants(row.msku):
            add_target(maps.near_msku, variant, sku)
        add_target(maps.customer_code, normalize_customer_code(row.msku), sku)
        for variant in msku_variants(row.msku):
            add_target(maps.customer_code, normalize_customer_code(variant), sku)
    return maps


@dataclass(frozen=True)
class EvidenceMatch:
    targets: tuple[str, ...]
    evidence: str
    unique: bool


def _catalog_targets(raw: set[str] | None, catalog_skus: set[str]) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(sorted(sku for sku in raw if not catalog_skus or sku in catalog_skus))


def resolve_live_targets(
    listing: AmazonListing,
    maps: LiveEvidenceMaps,
    catalog_skus: set[str],
) -> EvidenceMatch:
    checks = (
        ("live_msku", maps.msku.get(_key(listing.msku))),
        ("live_asin", maps.asin.get(listing.asin) if listing.asin else None),
        ("live_parent_sku", maps.parent_sku.get(_key(listing.parent_sku)) if listing.parent_sku else None),
        ("live_parent_asin", maps.parent_asin.get(listing.parent_asin) if listing.parent_asin else None),
        ("live_image", maps.image.get(listing.image_url) if listing.image_url else None),
        (
            "near_msku",
            set().union(*(maps.near_msku.get(variant, set()) for variant in msku_variants(listing.msku)))
            if listing.msku
            else None,
        ),
        (
            "customer_code",
            set().union(
                *(
                    maps.customer_code.get(normalize_customer_code(variant), set())
                    for variant in (listing.msku,) + msku_variants(listing.msku)
                )
            )
            if listing.msku
            else None,
        ),
    )
    first_conflict: EvidenceMatch | None = None
    for name, raw in checks:
        targets = _catalog_targets(set(raw) if raw else None, catalog_skus)
        if len(targets) == 1:
            return EvidenceMatch(targets, name, True)
        if len(targets) > 1 and first_conflict is None:
            first_conflict = EvidenceMatch(targets, f"{name}_conflict", False)
    if first_conflict:
        return first_conflict
    return EvidenceMatch((), "", False)


def load_customer_code_index(mapping) -> dict[str, set[str]]:
    import pandas as pd

    if mapping is None or getattr(mapping, "empty", True):
        return {}
    sku_cols = [col for col in mapping.columns if col in ("赛狐SKU", "赛狐已存在SKU", "EN产品编号", "产品编号")]
    code_cols = [col for col in mapping.columns if col in ("通途SKU", "客户物料号", "SKU别名")]
    if not sku_cols:
        return {}
    index: dict[str, set[str]] = defaultdict(set)
    for _, row in mapping.iterrows():
        skus: set[str] = set()
        for col in sku_cols:
            for part in re.split(r"[|;,，；]", _text(row.get(col))):
                part = part.strip()
                if re.match(r"^KS\d{4}", part, re.I):
                    skus.add(part)
        if not skus:
            continue
        for col in code_cols:
            for part in re.split(r"[|;,，；]", _text(row.get(col))):
                code = normalize_customer_code(part)
                if code:
                    index[code].update(skus)
    return dict(index)


def summarize_propagation(
    unmatched: list[AmazonListing],
    maps: LiveEvidenceMaps,
    catalog_skus: set[str],
) -> dict:
    counts = defaultdict(int)
    unique_by = defaultdict(int)
    conflict_by = defaultdict(int)
    covered: list[str] = []
    for row in unmatched:
        match = resolve_live_targets(row, maps, catalog_skus)
        counts["input"] += 1
        if not match.targets:
            counts["uncovered"] += 1
            continue
        counts["covered"] += 1
        covered.append(row.msku)
        if match.unique:
            counts["unique"] += 1
            unique_by[match.evidence] += 1
        else:
            counts["conflict"] += 1
            conflict_by[match.evidence] += 1
    return {
        "input": counts["input"],
        "covered": counts["covered"],
        "unique": counts["unique"],
        "conflict": counts["conflict"],
        "uncovered": counts["uncovered"],
        "unique_by_evidence": dict(unique_by),
        "conflict_by_evidence": dict(conflict_by),
        "accounted": counts["unique"] + counts["conflict"] + counts["uncovered"],
    }
