from amazon_pairing.ontology import classify_listing_object, normalize_size_terms


def test_removable_cover_is_finished_product_not_cover():
    classification = classify_listing_object(
        msku="DanCA1534D9-Blue-153",
        title=(
            "Daneey Headboard Wedge Pillow Bed Wedge Pillow for Headboard "
            "Bolster Reading Pillow for Bed Back Pillow with Removable "
            "Velvet Cover (Blue, Queen)"
        ),
        parent_sku="DanVEL-Triangle-CA",
        fulfillment="MFN",
    )

    assert classification.object_type == "finished_product"
    assert "removable_cover_included" in classification.reasons
    assert classification.count is None


def test_no_filler_pillow_cases_is_cover():
    classification = classify_listing_object(
        msku="CEN665-Leaves-Grey-66-2",
        title=(
            "WOWMAX Cotton Pillow Cases Standard Size Jacquard Satin Fabric "
            "Standard Pillow Cases Set of 2, Breathable Pillow Covers with "
            "Envelop Closure, No Filler, Light Gray"
        ),
        parent_sku="Bedpillow-p",
        fulfillment="MFN",
    )

    assert classification.object_type == "cover"
    assert "no_filler" in classification.reasons
    assert classification.count == 2


def test_foam_word_in_finished_title_is_not_foam_part():
    classification = classify_listing_object(
        msku="LongHuxing-Foam-Lbai-100",
        title=(
            "Daneey Foam Headboard Pillow Twin, 22IN Tall Curve Pillow "
            "Headboard, Linen-Textured Wedge Foam Headboard Pillow"
        ),
        parent_sku="LongDanHuxing-Foam",
        fulfillment="MFN",
    )

    assert classification.object_type == "finished_product"


def test_replacement_foam_is_foam_part():
    classification = classify_listing_object(
        msku="replacement-foam",
        title="Replacement Foam Insert Only, No Cover, High-Density Foam",
        parent_sku="",
        fulfillment="MFN",
    )

    assert classification.object_type == "foam_part"
    assert "replacement_foam" in classification.reasons


def test_multi_piece_rule_is_combo():
    classification = classify_listing_object(
        msku="BAI31038N0A62927SX-2pcs-us",
        title=(
            "BNCKTRD Couch Cushion Support for Sagging Seat 2 PCS, Arched "
            "Furniture Seat Under Cushion Sag Repair with High-Density Foam"
        ),
        parent_sku="BN-Sofa-Support",
        fulfillment="MFN",
    )

    assert classification.object_type == "combo"
    assert classification.count == 2


def test_bed_size_terms_map_to_cm():
    assert normalize_size_terms("Queen headboard pillow") == ["153"]
    assert normalize_size_terms("King headboard pillow") == ["194"]
    assert normalize_size_terms("California King headboard pillow") == ["200"]
    assert normalize_size_terms("22IN Tall curve pillow") == []
    assert normalize_size_terms("27.5 inches long") == ["69.9"]
