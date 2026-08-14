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
