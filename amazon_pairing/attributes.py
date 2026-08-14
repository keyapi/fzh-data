from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


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
    ("brown", "棕色"),
    ("coffee", "咖啡色"),
    ("cream", "奶油色"),
)
FABRIC_TERMS = (
    ("corduroy", "条绒"),
    ("chenille", "雪尼尔"),
    ("boucle", "圈圈呢"),
    ("velvet", "绒布"),
    ("linen", "涤麻"),
)


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


def extract_attributes(text: str) -> ListingAttributes:
    lowered = text.lower().replace("×", "x")
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
