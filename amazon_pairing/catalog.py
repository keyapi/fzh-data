from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
import json

from .attributes import AttributeValue, ListingAttributes, normalize_fabric
from .candidates import CandidateProduct


def _text(value) -> str:
    return str(value or "").strip()


def _normalize_size(value: str) -> str:
    text = _text(value).lower().replace("×", "x").replace("*", "x")
    text = re.sub(r"\s*cm\b", "", text)
    return re.sub(r"\s+", "", text)


def _en_attributes(item: dict) -> ListingAttributes:
    values: dict[str, list[str]] = {"size": [], "color": [], "fabric": [], "count": []}
    for row in item.get("attributes") or []:
        name = _text(row.get("attribute"))
        value = _text(row.get("attribute_value"))
        if not value:
            continue
        if "尺寸" in name:
            values["size"].append(_normalize_size(value))
        elif "颜色" in name:
            values["color"].append(value)
        elif "面料" in name:
            values["fabric"].append(normalize_fabric(value))
        elif any(token in name for token in ("件数", "数量", "套装")):
            values["count"].append(value)
    return ListingAttributes(
        size=AttributeValue(tuple(dict.fromkeys(values["size"])), bool(values["size"])),
        color=AttributeValue(tuple(dict.fromkeys(values["color"])), bool(values["color"])),
        fabric=AttributeValue(tuple(dict.fromkeys(values["fabric"])), bool(values["fabric"])),
        count=AttributeValue(tuple(dict.fromkeys(values["count"])), bool(values["count"])),
    )


def build_candidate_catalog(
    en_items: list[dict], sellfox_rows: list[dict]
) -> tuple[list[CandidateProduct], list[dict[str, str]]]:
    sellfox = {_text(row.get("sku")): row for row in sellfox_rows if _text(row.get("sku"))}
    catalog: list[CandidateProduct] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in en_items:
        sku = _text(item.get("item_code") or item.get("name"))
        if not sku or sku in seen or not re.match(r"^KS\d{4}(?:-|$)", sku.upper()):
            continue
        seen.add(sku)
        sellfox_row = sellfox.get(sku)
        if not sellfox_row:
            excluded.append({"sku": sku, "reason": "missing_in_sellfox"})
            continue
        if _text(sellfox_row.get("isGroup")) == "1":
            excluded.append({"sku": sku, "reason": "sellfox_combo"})
            continue
        family = _text(item.get("variant_of")) or sku.split("-", 1)[0]
        catalog.append(
            CandidateProduct(
                sku=sku,
                family=family,
                name=_text(item.get("item_name")) or _text(sellfox_row.get("name")),
                attributes=_en_attributes(item),
            )
        )
    return catalog, excluded


def save_catalog(path: Path, catalog: list[CandidateProduct]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(row) for row in catalog], ensure_ascii=False), encoding="utf-8")


def load_catalog(path: Path) -> list[CandidateProduct]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for row in rows:
        attrs = row["attributes"]
        attributes = ListingAttributes(
            **{name: AttributeValue(tuple(value["values"]), value["reliable"]) for name, value in attrs.items()}
        )
        result.append(
            CandidateProduct(
                sku=row["sku"], family=row["family"], name=row["name"],
                attributes=attributes, object_type=row.get("object_type", "ordinary")
            )
        )
    return result
