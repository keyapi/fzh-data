from amazon_pairing.attributes import extract_attributes
from amazon_pairing.labels import HistoricalPairing, audit_historical_pairing
from amazon_pairing.routing import route_listing


def test_router_keeps_cover_out_of_ordinary_products():
    result = route_listing(
        msku="VelvetCover-taupe-153",
        title="Headboard Wedge Pillow Cover, just Pillow Cover, no Filler",
        parent_sku="Dan-Triangle-cover-All",
    )

    assert result.object_type == "cover"
    assert "cover" in result.reasons


def test_router_routes_multipack_to_combo_review():
    result = route_listing(
        msku="KS0527-Modular-Set-Darkgray",
        title="4 Piece Modular Patio Sofa Set with 2 Corner Chairs",
    )

    assert result.object_type == "combo"
    assert "set_count" in result.reasons


def test_router_abstains_when_type_signals_conflict():
    result = route_listing(
        msku="unknown-153",
        title="Replacement cushion accessory for sofa",
    )

    assert result.object_type == "unknown"


def test_attribute_extraction_normalizes_inches_and_color():
    attrs = extract_attributes(
        "Daneey wedge pillow 60 x 20 x 8 inches, navy blue velvet"
    )

    assert attrs.size.values == ("152.4x50.8x20.3",)
    assert attrs.size.reliable is True
    assert attrs.color.values == ("藏青",)
    assert attrs.fabric.values == ("绒布",)


def test_attribute_extraction_keeps_ambiguous_single_number_soft():
    attrs = extract_attributes("Triangle pillow model 153 in grey")

    assert attrs.size.values == ("153",)
    assert attrs.size.reliable is False
    assert attrs.color.values == ("灰色",)


def test_attribute_extraction_treats_single_dimension_with_unit_as_reliable():
    attrs = extract_attributes("Grey triangle pillow 153 cm")

    assert attrs.size.values == ("153", "152")
    assert attrs.size.reliable is True


def test_single_inch_height_is_soft_not_a_product_size():
    attrs = extract_attributes("22IN Tall headboard pillow, pink")

    assert attrs.size.values == ("55.9",)
    assert attrs.size.reliable is False
    assert attrs.color.values == ("粉色",)


def test_bed_size_does_not_absorb_inch_height():
    attrs = extract_attributes(
        "Daneey Foam Headboard Pillow Twin, 22IN Tall Curve Pillow Headboard, White"
    )
    assert "97" in attrs.size.values
    assert "100" in attrs.size.values
    assert "55.9" not in attrs.size.values
    assert attrs.size.reliable is True


def test_router_recognizes_pillow_cover_listing_but_not_removable_cover_product():
    cover = route_listing(
        msku="OSBZ-DB-1",
        title="Decorative Throw Pillow Covers with Flower Pattern",
    )
    product = route_listing(
        msku="Dan760-pink-194",
        title="Headboard Wedge Pillow with Removable Printed Pink Cover, Velvet",
    )

    assert cover.object_type == "cover"
    assert product.object_type == "ordinary"


def test_router_treats_parenthetical_removable_cover_as_ordinary():
    result = route_listing(
        msku="DanCA1534D9-Blue-153",
        title="Wedge Pillow Headboard with Removable Velvet Cover (Blue, Queen)",
        parent_sku="DanVEL-Triangle-CA",
    )
    assert result.object_type == "ordinary"


def test_router_treats_foam_headboard_pillow_as_ordinary():
    result = route_listing(
        msku="LongHuxing-Foam-Lbai-100",
        title="Daneey Foam Headboard Pillow Twin, 22IN Tall Curve Pillow Headboard, White",
        parent_sku="LongDanHuxing-Foam",
        fulfillment="AFN",
    )
    assert result.object_type == "ordinary"
    assert "cover" not in result.reasons


def test_attribute_extraction_maps_queen_to_en_near_cm():
    attrs = extract_attributes("Headboard wedge pillow (Blue, Queen)")
    assert "153" in attrs.size.values
    assert "152" in attrs.size.values
    assert attrs.size.reliable is True


def test_color_terms_do_not_match_inside_other_words():
    attrs = extract_attributes("Reading pillow for bed, Green")

    assert attrs.color.values == ("绿色",)


def test_historical_pairing_requires_unique_alias_and_en_agreement_for_gold_a():
    result = audit_historical_pairing(
        HistoricalPairing(
            msku="TT-ALIAS-1",
            target_sku="KS0001-HLR-153-GREY",
            alias_targets=("TT001",),
            en_targets=("KS0001-HLR-153-GREY",),
        )
    )

    assert result.tier == "gold_a"
    assert result.usable_for_training is True


def test_historical_pairing_quarantines_alias_contradiction():
    result = audit_historical_pairing(
        HistoricalPairing(
            msku="COLLISION",
            target_sku="KS0001-HLR-153-GREY",
            alias_targets=("TT001", "TT002"),
            en_targets=("KS0001-HLR-153-GREY", "KS0001-HLR-153-BLUE"),
        )
    )

    assert result.tier == "quarantine"
    assert result.usable_for_training is False
    assert "alias_ambiguous" in result.reasons


def test_historical_pairing_quarantines_non_ordinary_target():
    result = audit_historical_pairing(
        HistoricalPairing(
            msku="SET-1",
            target_sku="TJ#KS0525x2_KS0526x1-001",
            alias_targets=("TT-SET",),
            en_targets=("TJ#KS0525x2_KS0526x1-001",),
            target_object_type="combo",
        )
    )

    assert result.tier == "quarantine"
    assert "non_ordinary_target" in result.reasons

def test_sku_suffix_cover_is_detected_even_with_parent_sku():
    result = route_listing(
        msku="CENL661-Brown-194-Cover",
        title="Wedge Pillow Cover Pillow Cases (Just Cover), Brown",
        parent_sku="LinenCover-pp",
    )
    assert result.object_type == "cover"
