from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from .attributes import extract_attributes
from .candidates import _size_compatible
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
MIN_CUSTOMER_CODE_LEN = 10
HARD_EVIDENCE = {"live_msku", "live_asin"}
COVER_TARGET = re.compile(r"枕套|皮壳|床笠|sham|pillow.?cover|cushion.?cover", re.I)
FOAM_TARGET = re.compile(r"海绵|foam", re.I)
COLOR_GROUPS = (frozenset({"棕色", "咖啡色", "褐色"}),)


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
            normalized = normalize_customer_code(code)
            if len(normalized) < MIN_CUSTOMER_CODE_LEN:
                continue
            for sku in skus:
                add_target(maps.customer_code, normalized, sku)
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
    return maps


@dataclass(frozen=True)
class EvidenceMatch:
    targets: tuple[str, ...]
    evidence: str
    unique: bool


def _raw_targets(raw: set[str] | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(sorted(raw))


def _in_catalog(targets: tuple[str, ...], catalog_skus: set[str]) -> tuple[str, ...]:
    if not catalog_skus:
        return targets
    return tuple(sku for sku in targets if sku in catalog_skus)


def resolve_live_targets(
    listing: AmazonListing,
    maps: LiveEvidenceMaps,
    catalog_skus: set[str],
) -> EvidenceMatch:
    checks = (
        ("live_msku", maps.msku.get(_key(listing.msku))),
        ("live_asin", maps.asin.get(listing.asin) if listing.asin else None),
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
                    if len(normalize_customer_code(variant)) >= MIN_CUSTOMER_CODE_LEN
                )
            )
            if listing.msku
            else None,
        ),
        ("live_parent_sku", maps.parent_sku.get(_key(listing.parent_sku)) if listing.parent_sku else None),
        ("live_parent_asin", maps.parent_asin.get(listing.parent_asin) if listing.parent_asin else None),
        ("live_image", maps.image.get(listing.image_url) if listing.image_url else None),
    )
    first_conflict: EvidenceMatch | None = None
    for name, raw in checks:
        all_targets = _raw_targets(set(raw) if raw else None)
        if not all_targets:
            continue
        catalog_targets = _in_catalog(all_targets, catalog_skus)
        if len(all_targets) == 1:
            if catalog_targets:
                return EvidenceMatch(catalog_targets, name, True)
            continue
        if first_conflict is None:
            display = catalog_targets or all_targets
            first_conflict = EvidenceMatch(display, f"{name}_conflict", False)
    if first_conflict:
        return first_conflict
    return EvidenceMatch((), "", False)


def _color_tokens(values: tuple[str, ...]) -> set[str]:
    expanded = set(values)
    for group in COLOR_GROUPS:
        if expanded & group:
            expanded |= set(group)
    return expanded


def _colors_compatible(query_values, product_values) -> bool:
    if not query_values.values or not product_values.values:
        return True
    if not query_values.reliable:
        return True
    return not _color_tokens(query_values.values).isdisjoint(_color_tokens(product_values.values))


def refine_live_match(listing: AmazonListing, match: EvidenceMatch, catalog_by_sku: dict) -> EvidenceMatch:
    if not match.targets or not match.unique:
        return match
    product = catalog_by_sku.get(match.targets[0])
    if product is None:
        return EvidenceMatch((), "", False)
    if match.evidence in HARD_EVIDENCE:
        return match
    query = extract_attributes(f"{listing.msku} {listing.title}")
    if not _size_compatible(query.size, product.attributes.size):
        return EvidenceMatch(match.targets, f"{match.evidence}_size_conflict", False)
    if not _colors_compatible(query.color, product.attributes.color):
        return EvidenceMatch(match.targets, f"{match.evidence}_color_conflict", False)
    return match


def target_allows_nonordinary_override(object_type: str, sku: str, name: str) -> bool:
    blob = f"{sku} {name}"
    if object_type == "cover":
        return sku.upper().startswith("KS0244") or bool(COVER_TARGET.search(blob))
    if object_type == "foam":
        return bool(FOAM_TARGET.search(blob)) or sku.upper().startswith("HM")
    return False


def load_customer_code_index(mapping) -> dict[str, set[str]]:
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
                if len(code) >= MIN_CUSTOMER_CODE_LEN:
                    index[code].update(skus)
    return dict(index)


def summarize_propagation(
    unmatched: list[AmazonListing],
    maps: LiveEvidenceMaps,
    catalog_skus: set[str],
    catalog_by_sku: dict | None = None,
) -> dict:
    counts = defaultdict(int)
    unique_by = defaultdict(int)
    conflict_by = defaultdict(int)
    for row in unmatched:
        match = resolve_live_targets(row, maps, catalog_skus)
        if catalog_by_sku:
            match = refine_live_match(row, match, catalog_by_sku)
        counts["input"] += 1
        if not match.targets:
            counts["uncovered"] += 1
            continue
        counts["covered"] += 1
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

def merge_evidence(*maps: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    merged: dict[str, tuple[str, ...]] = {}
    for evidence in maps:
        for target, reasons in evidence.items():
            merged[target] = tuple(dict.fromkeys((*merged.get(target, ()), *reasons)))
    return merged


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
