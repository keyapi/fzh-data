from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteResult:
    object_type: str
    reasons: tuple[str, ...]


def route_listing(msku: str, title: str, parent_sku: str = "") -> RouteResult:
    text = " ".join((msku, title, parent_sku)).lower()
    reasons: list[str] = []

    cover = any(token in text for token in ("cover only", "just pillow cover", "no filler"))
    cover = cover or bool(re.search(r"(?:^|[-_ ])cover(?:$|[-_ ])", text))
    cover = cover or bool(re.search(r"\b(?:pillow|cushion) covers\b", text))
    foam = any(token in text for token in ("foam only", "replacement foam"))
    foam = foam or bool(re.search(r"(?:^|[-_ ])foam(?:$|[-_ ])", text))
    combo = bool(
        re.search(r"\b(?:[2-9]|\d{2,})[ -]?(?:piece|pack|pcs?)\b", text)
        or re.search(r"\b(?:set of|sofa set|bundle|multipack)\b", text)
    )
    accessory = any(token in text for token in ("accessory", "frame only", "replacement cushion"))

    if cover:
        reasons.append("cover")
    if foam:
        reasons.append("foam")
    if combo:
        reasons.append("set_count")
    if accessory:
        reasons.append("accessory")

    strong_types = [
        object_type
        for object_type, matched in (("cover", cover), ("foam", foam), ("combo", combo))
        if matched
    ]
    if len(strong_types) == 1:
        return RouteResult(strong_types[0], tuple(reasons))
    if len(strong_types) > 1 or accessory:
        return RouteResult("unknown", tuple(reasons))
    return RouteResult("ordinary", ("no_special_signal",))
