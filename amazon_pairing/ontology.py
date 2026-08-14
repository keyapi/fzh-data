from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class ObjectClassification:
    object_type: str
    reasons: tuple[str, ...]
    count: int | None = None


BED_SIZE_TERMS = (
    ("california king", "200"),
    ("twin xl", "100"),
    ("twin", "100"),
    ("full", "140"),
    ("queen", "153"),
    ("king", "194"),
)


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _count(text: str) -> int | None:
    count = re.search(r"\b(\d+)\s*(?:piece|pack|pcs?)\b", text)
    if count:
        return int(count.group(1))
    set_count = re.search(r"\bset of\s+(\d+)\b", text)
    return int(set_count.group(1)) if set_count else None


def classify_listing_object(
    msku: str,
    title: str,
    parent_sku: str = "",
    fulfillment: str = "",
) -> ObjectClassification:
    text = " ".join((msku, title, parent_sku)).lower()
    reasons: list[str] = []
    count = _count(text)

    removable_cover = bool(
        re.search(r"\bwith\s+removable\s+[a-z]+\s+cover\b", text)
        or re.search(r"\bremovable\s+[a-z]+\s+cover\b", text)
    )
    standalone_cover = any(
        token in text
        for token in (
            "cover only",
            "just pillow cover",
            "just cover",
            "no filler",
            "pillow covers",
            "pillow cases",
            "cushion covers",
            "replacement cover",
        )
    )
    cover = standalone_cover and not removable_cover
    if cover:
        reasons.append("no_filler" if "no filler" in text else "standalone_cover")
    if removable_cover:
        reasons.append("removable_cover_included")

    standalone_foam = any(
        token in text
        for token in ("replacement foam", "foam only", "foam insert only", "just foam")
    ) or ("no cover" in text and "foam" in text)
    foam_part = standalone_foam and not cover
    if foam_part:
        reasons.append("replacement_foam" if "replacement foam" in text else "standalone_foam")

    combo = count is not None and not cover and not foam_part
    if count is not None:
        reasons.append(f"count_{count}")
    if combo:
        reasons.append("set_count")

    if cover and foam_part:
        return ObjectClassification("unknown", tuple(dict.fromkeys(reasons)), count)
    if cover:
        return ObjectClassification("cover", tuple(dict.fromkeys(reasons)), count)
    if foam_part:
        return ObjectClassification("foam_part", tuple(dict.fromkeys(reasons)), count)
    if combo:
        return ObjectClassification("combo", tuple(dict.fromkeys(reasons)), count)
    if "with removable cover" in text or removable_cover:
        return ObjectClassification("finished_product", tuple(dict.fromkeys(reasons)), count)
    return ObjectClassification("finished_product", tuple(dict.fromkeys(reasons) or ("no_special_signal",)), count)


def _decimal(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".")


def normalize_size_terms(text: str) -> list[str]:
    lowered = _text(text).lower().replace("×", "x").replace("*", "x")
    values: list[str] = []

    dimension = re.search(
        r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:inches|inch|in|\"|cm)\b",
        lowered,
    )
    if dimension:
        value = Decimal(dimension.group(1))
        unit = dimension.group(0)
        if "cm" not in unit:
            value *= Decimal("2.54")
        if "tall" not in lowered[max(0, dimension.start() - 8):dimension.end() + 8]:
            values.append(_decimal(value))

    for term, size in BED_SIZE_TERMS:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered) and size not in values:
            values.append(size)
            lowered = lowered.replace(term, " ")

    return list(dict.fromkeys(values))
