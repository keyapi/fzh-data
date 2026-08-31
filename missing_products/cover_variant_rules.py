# -*- coding: utf-8 -*-
"""Rules for EN 皮壳# variants: must hang on PK# template with copied attributes."""
from __future__ import annotations

from enum import Enum
from typing import Any


class CoverGap(str, Enum):
    OK = "ok"
    CREATE_VARIANT = "create_variant"
    ATTACH_TO_TEMPLATE = "attach_to_template"


def cover_item_code(product_code: str, product_template: str, cover_template: str) -> str:
    prefix = product_template + "-"
    if not product_code.startswith(prefix):
        raise ValueError(f"{product_code} is not a variant of {product_template}")
    return cover_template + "-" + product_code[len(prefix) :]


def cover_item_name(product_name: str) -> str:
    name = (product_name or "").strip()
    if not name:
        raise ValueError("product_name is empty")
    if name.startswith("皮壳#"):
        return name
    return "皮壳#" + name


def classify_cover_gap(
    *,
    product: dict[str, Any],
    cover: dict[str, Any] | None,
    cover_template: str,
) -> CoverGap:
    if not product.get("variant_of"):
        raise ValueError(f"{product.get('item_code')} is not a multi-spec product variant")
    if cover is None:
        return CoverGap.CREATE_VARIANT
    vo = cover.get("variant_of") or None
    attrs = cover.get("attributes") or []
    if vo != cover_template or not attrs:
        return CoverGap.ATTACH_TO_TEMPLATE
    return CoverGap.OK


def cover_variant_payload(
    product: dict[str, Any],
    *,
    product_template: str,
    cover_template: str,
    cover_group: str,
) -> dict[str, Any]:
    attrs = [
        {"attribute": a["attribute"], "attribute_value": a["attribute_value"]}
        for a in (product.get("attributes") or [])
        if a.get("attribute") and a.get("attribute_value")
    ]
    if len(attrs) < 2:
        raise ValueError(f"{product.get('item_code')} missing variant attributes")
    payload = {
        "item_code": cover_item_code(product["item_code"], product_template, cover_template),
        "item_name": cover_item_name(product["item_name"]),
        "item_group": cover_group,
        "variant_of": cover_template,
        "has_variants": 0,
        "stock_uom": product.get("stock_uom") or "个",
        "is_stock_item": 1,
        "include_item_in_manufacturing": 1,
        "is_sales_item": 1,
        "is_purchase_item": 1,
        "attributes": attrs,
    }
    validate_supporting_item_payload(payload)
    return payload


def validate_supporting_item_payload(payload: dict[str, Any]) -> None:
    code = payload.get("item_code") or ""
    if not code.startswith("PK#"):
        return
    if payload.get("has_variants"):
        return
    if not payload.get("variant_of"):
        raise ValueError("皮壳 SKU 必须 variant_of 皮壳模板（禁止独立物料）")
    if not str(payload["variant_of"]).startswith("PK#"):
        raise ValueError("皮壳 SKU 的 variant_of 必须是 PK# 模板")
    attrs = payload.get("attributes") or []
    if not attrs:
        raise ValueError("皮壳变体必须带 attributes（与成品同属性）")


_BOM_META = {
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "idx",
    "doctype",
    "parent",
    "parentfield",
    "parenttype",
}

_BOM_ITEM_KEEP = ("item_code", "qty", "uom", "stock_uom", "rate", "do_not_explode")
_BOM_OP_KEEP = (
    "operation",
    "workstation",
    "workstation_type",
    "time_in_mins",
    "hour_rate",
    "batch_size",
    "sequence_id",
    "fixed_time",
)


def strip_bom_for_recreate(bom: dict[str, Any]) -> dict[str, Any]:
    """Keep fields needed to POST a replacement BOM after recreating the item."""
    out: dict[str, Any] = {
        "item": bom["item"],
        "company": bom.get("company") or "FZH",
        "uom": bom.get("uom") or "个",
        "quantity": bom.get("quantity") or 1.0,
        "is_active": 1,
        "is_default": 1,
        "with_operations": 1 if bom.get("operations") else int(bom.get("with_operations") or 0),
        "rm_cost_as_per": bom.get("rm_cost_as_per") or "Price List",
        "buying_price_list": bom.get("buying_price_list") or "标准采购",
        "currency": bom.get("currency") or "CNY",
        "items": [
            {k: row[k] for k in _BOM_ITEM_KEEP if k in row and row[k] is not None}
            for row in (bom.get("items") or [])
        ],
    }
    if bom.get("routing"):
        out["routing"] = bom["routing"]
    ops = bom.get("operations") or []
    if ops:
        out["operations"] = [
            {k: row[k] for k in _BOM_OP_KEEP if k in row and row[k] is not None}
            for row in ops
        ]
        out["with_operations"] = 1
    return out
