import pytest

from missing_products.cover_variant_rules import (
    CoverGap,
    classify_cover_gap,
    cover_item_code,
    cover_item_name,
    cover_variant_payload,
    validate_supporting_item_payload,
)


def test_cover_code_and_name_follow_product_suffix():
    assert (
        cover_item_code("KS0001-CMM-153-PURPLE", "KS0001", "PK#KS0001")
        == "PK#KS0001-CMM-153-PURPLE"
    )
    assert cover_item_name("三角靠枕-纯棉麻-153-紫色") == "皮壳#三角靠枕-纯棉麻-153-紫色"


def test_classify_standalone_cover_without_template_is_attach():
    gap = classify_cover_gap(
        product={"item_code": "KS0001-CMM-153-PURPLE", "variant_of": "KS0001"},
        cover={
            "item_code": "PK#KS0001-CMM-153-PURPLE",
            "variant_of": None,
            "attributes": [],
        },
        cover_template="PK#KS0001",
    )
    assert gap == CoverGap.ATTACH_TO_TEMPLATE


def test_classify_missing_cover_is_create():
    gap = classify_cover_gap(
        product={"item_code": "KS0001-DM-140-SKYBLUE", "variant_of": "KS0001"},
        cover=None,
        cover_template="PK#KS0001",
    )
    assert gap == CoverGap.CREATE_VARIANT


def test_payload_requires_variant_of_and_copied_attributes():
    product = {
        "item_code": "KS0001-DM-140-SKYBLUE",
        "item_name": "三角靠枕-涤麻-140-天蓝色",
        "attributes": [
            {"attribute": "三角靠枕面料", "attribute_value": "涤麻"},
            {"attribute": "三角靠枕尺寸", "attribute_value": "140"},
            {"attribute": "三角靠枕颜色", "attribute_value": "天蓝色"},
        ],
    }
    payload = cover_variant_payload(
        product,
        product_template="KS0001",
        cover_template="PK#KS0001",
        cover_group="皮壳#三角靠枕",
    )
    assert payload["item_code"] == "PK#KS0001-DM-140-SKYBLUE"
    assert payload["item_name"] == "皮壳#三角靠枕-涤麻-140-天蓝色"
    assert payload["variant_of"] == "PK#KS0001"
    assert payload["has_variants"] == 0
    assert payload["item_group"] == "皮壳#三角靠枕"
    assert payload["attributes"] == product["attributes"]
    validate_supporting_item_payload(payload)


def test_aug7_convention_standalone_pk_payload_is_rejected():
    bad = {
        "item_code": "PK#KS0001-CMM-153-PURPLE",
        "item_name": "皮壳#三角靠枕-纯棉麻-153-紫色",
        "item_group": "皮壳#三角靠枕",
        "stock_uom": "个",
        "is_stock_item": 1,
        "include_item_in_manufacturing": 1,
        "is_sales_item": 0,
    }
    with pytest.raises(ValueError, match="variant_of"):
        validate_supporting_item_payload(bad)


def test_strip_bom_keeps_operations_and_workstation():
    from missing_products.cover_variant_rules import strip_bom_for_recreate

    raw = {
        "name": "BOM-X-001",
        "item": "PK#KS0001-CMM-153-PURPLE",
        "company": "FZH",
        "uom": "个",
        "quantity": 1.0,
        "is_active": 1,
        "is_default": 1,
        "with_operations": 1,
        "routing": "R1",
        "rm_cost_as_per": "Price List",
        "buying_price_list": "标准采购",
        "currency": "CNY",
        "items": [
            {
                "name": "row1",
                "item_code": "CMM2020-PURPLE-142-260",
                "qty": 2.31,
                "uom": "米",
                "parent": "BOM-X-001",
            }
        ],
        "operations": [
            {
                "name": "op1",
                "operation": "裁剪",
                "workstation": "裁床",
                "time_in_mins": 1.97,
                "hour_rate": 39.6,
                "batch_size": 1,
                "sequence_id": 1,
            }
        ],
    }
    out = strip_bom_for_recreate(raw)
    assert "name" not in out
    assert out["item"] == "PK#KS0001-CMM-153-PURPLE"
    assert out["items"][0]["item_code"] == "CMM2020-PURPLE-142-260"
    assert "parent" not in out["items"][0]
    assert out["operations"][0]["workstation"] == "裁床"
    assert out["with_operations"] == 1
