from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class AttributeValue:
    values: tuple[str, ...] = ()
    reliable: bool = False


@dataclass(frozen=True)
class ListingAttributes:
    size: AttributeValue
    color: AttributeValue
    fabric: AttributeValue
    count: AttributeValue


COLOR_TERMS = (
    ("navy blue", "藏青"),
    ("navy", "藏青"),
    ("dark grey", "深灰色"),
    ("dark gray", "深灰色"),
    ("light grey", "浅灰色"),
    ("light gray", "浅灰色"),
    ("grey", "灰色"),
    ("gray", "灰色"),
    ("blue", "蓝色"),
    ("black", "黑色"),
    ("white", "白色"),
    ("beige", "米色"),
    ("taupe", "灰褐色"),
    ("pink", "粉色"),
    ("red", "红色"),
    ("orange", "橙色"),
    ("green", "绿色"),
    ("yellow", "黄色"),
    ("purple", "紫色"),
    ("brown", "咖啡色"),
    ("marron", "咖啡色"),
    ("braun", "咖啡色"),
    ("coffee", "咖啡色"),
    ("cream", "奶油色"),
)
FABRIC_TERMS = (
    ("corduroy", "条绒"),
    ("chenille", "雪尼尔"),
    ("boucle", "圈圈呢"),
    ("velvet", "绒布"),
    ("linen", "亚麻"),
)


@lru_cache(maxsize=1)
def load_us_size_map() -> dict:
    path = Path(__file__).resolve().parent / "knowledge" / "us-size-map.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def normalize_fabric(value: str) -> str:
    lowered = value.lower()
    if any(token in lowered for token in ("velvet", "荷兰绒", "暗花绒")):
        return "绒布"
    return value


def _decimal_text(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".")


def _terms(text: str, terms: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    found: list[str] = []
    remaining = text
    for token, normalized in terms:
        pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
        if re.search(pattern, remaining) and normalized not in found:
            found.append(normalized)
            remaining = re.sub(pattern, " ", remaining)
    return tuple(found)


def _expand_near_cm(values: tuple[str, ...], near: dict) -> tuple[str, ...]:
    expanded: list[str] = []
    for value in values:
        if value not in expanded:
            expanded.append(value)
        for alias in near.get(value, []) or []:
            if alias not in expanded:
                expanded.append(alias)
    return tuple(expanded)


def _bed_sizes(text: str, size_map: dict) -> tuple[str, ...]:
    beds = size_map.get("bed") or {}
    found: list[str] = []
    for token, cms in sorted(beds.items(), key=lambda item: -len(item[0])):
        pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
        if re.search(pattern, text):
            for cm in cms:
                if cm not in found:
                    found.append(str(cm))
    return tuple(found)


def extract_attributes(text: str) -> ListingAttributes:
    lowered = text.lower().replace("×", "x")
    size_map = load_us_size_map()
    near = {str(key): list(value) for key, value in (size_map.get("near_cm") or {}).items()}
    size_values: tuple[str, ...] = ()
    size_reliable = False
    dimensions = re.search(
        r"(?<!\d)(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(inches|inch|in|cm)\b",
        lowered,
    )
    if dimensions:
        values = [Decimal(dimensions.group(i)) for i in range(1, 4)]
        if dimensions.group(4) in {"inches", "inch", "in"}:
            values = [value * Decimal("2.54") for value in values]
        size_values = ("x".join(_decimal_text(value) for value in values),)
        size_reliable = True
    else:
        single_with_unit = re.search(
            r"(?<!\d)(\d{2,3}(?:\.\d+)?)(?:(?:\s*(cm|inches|inch)\b)|(?:\s*([\"']))|(?:in\b))",
            lowered,
        )
        if single_with_unit:
            value = Decimal(single_with_unit.group(1))
            unit = single_with_unit.group(2) or single_with_unit.group(3) or "in"
            if unit != "cm":
                value *= Decimal("2.54")
            size_values = (_decimal_text(value),)
            size_reliable = unit == "cm"
        else:
            single = re.search(r"(?<!\d)(\d{2,3})(?!\d)", lowered)
            if single:
                size_values = (single.group(1),)
        bed = _bed_sizes(lowered, size_map)
        if bed:
            extra = size_values if size_reliable else ()
            size_values = tuple(dict.fromkeys(tuple(bed) + extra))
            size_reliable = True

    if size_reliable:
        size_values = _expand_near_cm(size_values, near)
    count = re.search(r"\b(\d+)\s*(?:piece|pack|pcs?)\b", lowered)
    count_value = AttributeValue((count.group(1),), True) if count else AttributeValue()
    colors = _terms(lowered, COLOR_TERMS)
    fabrics = tuple(normalize_fabric(value) for value in _terms(lowered, FABRIC_TERMS))
    return ListingAttributes(
        size=AttributeValue(size_values, size_reliable),
        color=AttributeValue(colors, bool(colors)),
        fabric=AttributeValue(fabrics, bool(fabrics)),
        count=count_value,
    )
