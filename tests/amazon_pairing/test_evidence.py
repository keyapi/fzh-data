from amazon_pairing.data import AmazonListing
from amazon_pairing.evidence import (
    build_live_maps,
    load_customer_code_index,
    msku_variants,
    resolve_live_targets,
    summarize_propagation,
)
from amazon_pairing.routing import route_listing
import pandas as pd


def listing(**kwargs) -> AmazonListing:
    values = dict(
        shop_id="1",
        marketplace_id="ATVPDKIKX0DER",
        msku="",
        asin="",
        parent_asin="",
        title="",
        target_sku="",
        image_url="",
        online_status="Active",
        fulfillment="MFN",
        parent_sku="",
    )
    values.update(kwargs)
    return AmazonListing(**values)


def test_same_msku_live_pairing_is_used_without_gold_a():
    matched = [
        listing(
            shop_id="2",
            marketplace_id="A2EUQ1WTGCTBG2",
            msku="Danpinse-KS0388-blue-FBA",
            target_sku="KS0388-HLRJLGBL-62x68x38-LIGHTBLUE",
        )
    ]
    unmatched = listing(
        msku="Danpinse-KS0388-blue-FBA",
        title="Daneey Back Pillow for Sitting in Bed, Light Blue",
        parent_sku="Danpinse-KS0388",
        fulfillment="AFN",
    )
    maps = build_live_maps(matched)
    match = resolve_live_targets(unmatched, maps, {"KS0388-HLRJLGBL-62x68x38-LIGHTBLUE"})

    assert match.unique is True
    assert match.evidence == "live_msku"
    assert match.targets == ("KS0388-HLRJLGBL-62x68x38-LIGHTBLUE",)


def test_asin_propagates_across_marketplaces():
    matched = [listing(marketplace_id="A1AM78C64UM0Y8", asin="B0FJFHJBYL", target_sku="KS0001-HLR-153-BLUE")]
    unmatched = listing(marketplace_id="ATVPDKIKX0DER", asin="B0FJFHJBYL", msku="other-msku")
    maps = build_live_maps(matched)
    match = resolve_live_targets(unmatched, maps, {"KS0001-HLR-153-BLUE"})

    assert match.evidence == "live_asin"
    assert match.targets == ("KS0001-HLR-153-BLUE",)


def test_customer_code_prefix_and_near_msku():
    matched = [listing(msku="CEN665-Leaves-Grey-66-1", target_sku="KS0244-CMGDTH-66x50-GREY")]
    maps = build_live_maps(
        matched,
        {"NB/CEN665-Leaves-Grey-66": {"KS0244-CMGDTH-66x50-GREY"}},
    )
    unmatched = listing(msku="CEN665-Leaves-Grey-66-2", title="Leaves Grey Pillow Sham Cover 66")
    match = resolve_live_targets(unmatched, maps, {"KS0244-CMGDTH-66x50-GREY"})

    assert match.unique is True
    assert match.targets == ("KS0244-CMGDTH-66x50-GREY",)
    assert match.evidence in {"near_msku", "customer_code"}


def test_parent_sku_unique_target():
    matched = [
        listing(
            msku="LongHuxing-Foam-White-100",
            parent_sku="LongDanHuxing-Foam",
            target_sku="KS0120-FOAM-100-WHITE",
        )
    ]
    unmatched = listing(
        msku="LongHuxing-Foam-Lbai-100",
        parent_sku="LongDanHuxing-Foam",
        title="Daneey Foam Headboard Pillow Twin, White",
        fulfillment="AFN",
    )
    maps = build_live_maps(matched)
    match = resolve_live_targets(unmatched, maps, {"KS0120-FOAM-100-WHITE"})

    assert match.evidence == "live_parent_sku"
    assert match.targets == ("KS0120-FOAM-100-WHITE",)


def test_mapping_customer_code_index_strips_nb_prefix():
    mapping = pd.DataFrame(
        [{"通途SKU": "CEN665-Leaves-Grey-66", "客户物料号": "NB/CEN665-Leaves-Grey-66", "赛狐SKU": "KS0244-CMGDTH-66x50-GREY"}]
    )
    index = load_customer_code_index(mapping)
    assert "cen665-leaves-grey-66" in index
    assert index["cen665-leaves-grey-66"] == {"KS0244-CMGDTH-66x50-GREY"}


def test_msku_variants_strip_fba_and_trailing_index():
    assert "cen665-leaves-grey-66" in msku_variants("CEN665-Leaves-Grey-66-2")
    assert "danpinse-ks0388-blue" in msku_variants("Danpinse-KS0388-blue-FBA")


def test_propagation_audit_accounts_for_every_row():
    matched = [listing(msku="A", asin="B1", target_sku="KS0001-A")]
    unmatched = [
        listing(msku="A", title="same"),
        listing(msku="Z", title="unknown"),
    ]
    maps = build_live_maps(matched)
    report = summarize_propagation(unmatched, maps, {"KS0001-A"})
    assert report["input"] == 2
    assert report["accounted"] == report["input"]
    assert report["unique"] == 1
    assert report["uncovered"] == 1


def test_golden_routes():
    assert route_listing(
        "DanCA1534D9-Blue-153",
        "Wedge Pillow Headboard with Removable Velvet Cover (Blue, Queen)",
        "DanVEL-Triangle-CA",
    ).object_type == "ordinary"
    assert route_listing(
        "LongHuxing-Foam-Lbai-100",
        "Daneey Foam Headboard Pillow Twin, 22IN Tall Curve Pillow Headboard, White",
        "LongDanHuxing-Foam",
        "AFN",
    ).object_type == "ordinary"
    assert route_listing(
        "CEN665-Leaves-Grey-66-2",
        "Leaves Grey Pillow Sham Cover 66",
        "",
    ).object_type == "ordinary"
    assert route_listing(
        "BAI31038N0A62927SX-2pcs-us",
        "Couch Cushion Support 2 PCS, High-Density Foam",
        "BN-Sofa-Support",
    ).object_type == "combo"

from amazon_pairing.attributes import extract_attributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.evidence import refine_live_match, target_allows_nonordinary_override


def test_parent_multi_target_is_conflict_even_if_catalog_has_one():
    matched = [
        listing(parent_sku="SANJIAO-Bolster", msku="a", target_sku="KS0001-DM-100-GRASSGREEN"),
        listing(parent_sku="SANJIAO-Bolster", msku="b", target_sku="KS0001-HLR-100-GINGER-ALL"),
    ]
    unmatched = listing(msku="child", parent_sku="SANJIAO-Bolster", title="bolster pillow")
    maps = build_live_maps(matched)
    match = resolve_live_targets(unmatched, maps, {"KS0001-DM-100-GRASSGREEN"})
    assert match.unique is False
    assert "conflict" in match.evidence


def test_image_size_mismatch_is_demoted():
    matched = [listing(image_url="http://img/a.jpg", target_sku="KS0001-PR-194-GREY")]
    unmatched = listing(
        msku="CENVel1612-hui-100-Cover",
        title="Triangular Pillow Covers 100 cm Grey",
        image_url="http://img/a.jpg",
    )
    maps = build_live_maps(matched)
    product = CandidateProduct(
        "KS0001-PR-194-GREY",
        "KS0001",
        "三角靠枕-平绒-194-灰色",
        extract_attributes("KS0001-PR-194-GREY 三角靠枕-平绒-194-灰色"),
    )
    match = resolve_live_targets(unmatched, maps, {product.sku})
    match = refine_live_match(unmatched, match, {product.sku: product})
    assert match.unique is False
    assert "size_conflict" in match.evidence


def test_cover_override_only_for_sham_sku():
    assert target_allows_nonordinary_override("cover", "KS0244-CMGDTH-66x50-GREY", "枕套")
    assert not target_allows_nonordinary_override("cover", "KS0001-PR-194-GREY", "三角靠枕-平绒-194-灰色")


def test_same_asin_propagates_across_marketplace():
    index = EvidenceIndex.build(
        [
            matched_row(
                shopId="596737",
                marketplaceId="ATVPDKIKX0DER",
                commoditySku="KS0388-HLRJLGBL-62x68x38-LIGHTBLUE",
            ),
        ]
    )
    listing = matched_row(
        shopId="596738",
        marketplaceId="A2EUQ1WTGCTBG2",
        commoditySku=None,
    )

    candidates = index.candidates_for_listing(listing)

    assert "KS0388-HLRJLGBL-62x68x38-LIGHTBLUE" in candidates
    assert any("asin" in reason for reason in candidates["KS0388-HLRJLGBL-62x68x38-LIGHTBLUE"])


def test_parent_asin_and_parent_sku_are_candidate_evidence():
    index = EvidenceIndex.build([matched_row()])
    listing = matched_row(
        sku="CHILD",
        asin="B000CHILD",
        commoditySku=None,
    )

    candidates = index.candidates_for_listing(listing)

    assert "KS0001-HLR-153-BLUE" in candidates
    evidence = " | ".join(candidates["KS0001-HLR-153-BLUE"])
    assert "parent_asin" in evidence
    assert "parent_sku" in evidence


def test_image_url_is_strong_evidence():
    index = EvidenceIndex.build([matched_row()])
    listing = matched_row(
        sku="OTHER",
        asin="B000OTHER",
        parentAsin="",
        parentSku="",
        fnsku="",
        commoditySku=None,
    )

    candidates = index.candidates_for_listing(listing)

    assert candidates == {
        "KS0001-HLR-153-BLUE": ("main_image", "title_exact")
    }


def test_conflicting_asin_targets_are_preserved_for_review():
    index = EvidenceIndex.build(
        [
            matched_row(commoditySku="KS0001-HLR-153-BLUE"),
            matched_row(
                shopId="596738",
                marketplaceId="A2EUQ1WTGCTBG2",
                commoditySku="KS0248-HLR-153-BLUE",
            ),
        ]
    )
    listing = matched_row(
        shopId="596765",
        marketplaceId="A1RKKUPIHCS9HS",
        commoditySku=None,
    )

    candidates = index.candidates_for_listing(listing)

    assert set(candidates) == {"KS0001-HLR-153-BLUE", "KS0248-HLR-153-BLUE"}
    assert index.conflict_targets(listing) == {"KS0001-HLR-153-BLUE", "KS0248-HLR-153-BLUE"}

def test_empty_shop_does_not_create_asin_shop_evidence():
    index = EvidenceIndex.build([matched_row(shopId="", asin="B000EMPTYSHOP")])
    listing = matched_row(shopId="", asin="B000EMPTYSHOP", commoditySku=None)
    candidates = index.candidates_for_listing(listing)
    assert "asin_shop" not in candidates["KS0001-HLR-153-BLUE"]
