from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteResult:
    object_type: str
    reasons: tuple[str, ...]


FEATURE_COVER = re.compile(
    r"\b(?:with\s+)?(?:a\s+)?removable(?:\s+\w+){0,3}\s+cover\b"
    r"|\bwith\s+(?:a\s+)?(?:\w+\s+){0,3}cover\b",
    re.IGNORECASE,
)
STRONG_COVER_TITLE = (
    "cover only",
    "just pillow cover",
    "no filler",
)
PILLOW_COVERS = re.compile(r"\b(?:pillow|cushion) covers\b", re.IGNORECASE)
SKU_COVER = re.compile(r"(?:^|[-_])cover(?:$|[-_])", re.IGNORECASE)
SKU_FOAM = re.compile(r"(?:^|[-_])foam(?:$|[-_])", re.IGNORECASE)
FINISHED_NOUN = re.compile(
    r"\b(?:pillow|cushion|headboard|wedge|bolster|sham|duvet|comforter)\b",
    re.IGNORECASE,
)
COMBO = re.compile(
    r"\b(?:[2-9]|\d{2,})[ -]?(?:piece|pack|pcs?)\b|\b(?:set of|sofa set|bundle|multipack)\b",
    re.IGNORECASE,
)


def _true_cover(msku: str, title: str, parent_sku: str) -> bool:
    sku_blob = f"{msku} {parent_sku}"
    if SKU_COVER.search(sku_blob):
        return True
    lowered = title.lower()
    if any(token in lowered for token in STRONG_COVER_TITLE):
        return True
    if PILLOW_COVERS.search(lowered):
        return True
    if FEATURE_COVER.search(title):
        return False
    return False


def _true_foam(msku: str, title: str, parent_sku: str) -> bool:
    lowered = title.lower()
    if "foam only" in lowered or "replacement foam" in lowered:
        return True
    if FINISHED_NOUN.search(title):
        return False
    return bool(SKU_FOAM.search(f"{msku} {parent_sku}"))


def route_listing(
    msku: str, title: str, parent_sku: str = "", fulfillment: str = ""
) -> RouteResult:
    reasons: list[str] = []
    cover = _true_cover(msku, title, parent_sku)
    foam = _true_foam(msku, title, parent_sku)
    combo = bool(COMBO.search(f"{msku} {title}"))
    accessory = any(token in f"{msku} {title}".lower() for token in ("accessory", "frame only", "replacement cushion"))
    fba = fulfillment.upper() in {"AFN", "FBA"}

    if cover:
        reasons.append("cover")
    if foam:
        reasons.append("foam")
    if combo:
        reasons.append("set_count")
    if accessory:
        reasons.append("accessory")

    if fba and (cover or foam) and not any(
        token in title.lower() for token in (*STRONG_COVER_TITLE, "foam only", "replacement foam")
    ):
        cover = False
        foam = False
        reasons.append("fba_finished_prior")

    strong_types = [
        object_type
        for object_type, matched in (("cover", cover), ("foam", foam), ("combo", combo))
        if matched
    ]
    if len(strong_types) == 1:
        return RouteResult(strong_types[0], tuple(reasons))
    if len(strong_types) > 1 or accessory:
        return RouteResult("unknown", tuple(reasons))
    if "fba_finished_prior" in reasons:
        return RouteResult("ordinary", tuple(reasons) or ("no_special_signal",))
    return RouteResult("ordinary", ("no_special_signal",) if not reasons else tuple(reasons))
