from amazon_pairing.catalog import build_candidate_catalog


def test_catalog_uses_en_attributes_and_requires_sellfox_sku():
    en_items = [
        {
            "item_code": "KS0001-HLR-153-GREY",
            "item_name": "三角靠枕-荷兰绒-153cm-灰色",
            "variant_of": "KS0001",
            "attributes": [
                {"attribute": "三角靠枕尺寸", "attribute_value": "153cm"},
                {"attribute": "三角靠枕颜色", "attribute_value": "灰色"},
                {"attribute": "三角靠枕面料", "attribute_value": "荷兰绒"},
            ],
        },
        {
            "item_code": "KS0001-HLR-153-BLUE",
            "item_name": "三角靠枕-荷兰绒-153cm-蓝色",
            "variant_of": "KS0001",
            "attributes": [],
        },
    ]
    sellfox = [
        {"sku": "KS0001-HLR-153-GREY", "name": "Sellfox name", "isGroup": "0"}
    ]

    catalog, excluded = build_candidate_catalog(en_items, sellfox)

    assert [product.sku for product in catalog] == ["KS0001-HLR-153-GREY"]
    assert catalog[0].attributes.size.values == ("153",)
    assert catalog[0].attributes.color.values == ("灰色",)
    assert catalog[0].attributes.fabric.values == ("绒布",)
    assert excluded == [{"sku": "KS0001-HLR-153-BLUE", "reason": "missing_in_sellfox"}]


def test_catalog_excludes_sellfox_combo_even_if_code_looks_like_product():
    en_items = [
        {
            "item_code": "KS0001-GROUP",
            "item_name": "Group",
            "variant_of": "KS0001",
            "attributes": [],
        }
    ]
    sellfox = [{"sku": "KS0001-GROUP", "name": "Group", "isGroup": "1"}]

    catalog, excluded = build_candidate_catalog(en_items, sellfox)

    assert catalog == []
    assert excluded == [{"sku": "KS0001-GROUP", "reason": "sellfox_combo"}]


def test_catalog_normalizes_related_velvet_names_to_comparable_family():
    en_items = [
        {
            "item_code": "KS0001-AHR-153-GREY",
            "item_name": "三角靠枕",
            "variant_of": "KS0001",
            "attributes": [{"attribute": "面料", "attribute_value": "暗花绒"}],
        }
    ]
    sellfox = [{"sku": "KS0001-AHR-153-GREY", "isGroup": "0"}]

    catalog, _ = build_candidate_catalog(en_items, sellfox)

    assert catalog[0].attributes.fabric.values == ("绒布",)
