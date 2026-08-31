from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.evidence import EvidenceIndex
from amazon_pairing.v2 import decide_v2


EMPTY = ListingAttributes(
    AttributeValue(), AttributeValue(), AttributeValue(), AttributeValue()
)


def product(sku, family, name, size=(), color=(), object_type="finished_product"):
    attrs = ListingAttributes(
        size=AttributeValue(size, bool(size)),
        color=AttributeValue(color, bool(color)),
        fabric=AttributeValue(),
        count=AttributeValue(),
    )
    return CandidateProduct(sku, family, name, attrs, object_type)


def matched(target="KS0388-HLRJLGBL-62x68x38-LIGHTBLUE"):
    return {
        "shopId": "596737",
        "marketplaceId": "ATVPDKIKX0DER",
        "asin": "B0FJFHJBYL",
        "parentAsin": "B0FJFN6VLJ",
        "parentSku": "Danpinse-KS0388",
        "sku": "Danpinse-KS0388-blue",
        "title": (
            "Daneey Back Pillow for Sitting in Bed, Reading Pillow with "
            "Support and Cylinder Cushion, Light Blue"
        ),
        "mainImage": "image",
        "fnsku": "X004T10CY1",
        "commoditySku": target,
        "commodityName": "复古曲线拼色靠枕",
    }


def test_v2_cross_market_asin_is_strong_single():
    index = EvidenceIndex.build([matched()])
    listing = matched("")
    listing["shopId"] = "596738"
    listing["marketplaceId"] = "A2EUQ1WTGCTBG2"
    listing["sku"] = "Danpinse-KS0388-blue-FBA"
    catalog = {
        "KS0388-HLRJLGBL-62x68x38-LIGHTBLUE": product(
            "KS0388-HLRJLGBL-62x68x38-LIGHTBLUE",
            "KS0388",
            "复古曲线拼色靠枕-荷兰绒+肌理感布料-62x68x38cm-浅蓝色",
            size=("62x68x38",),
            color=("浅蓝色",),
        )
    }

    decision = decide_v2(listing, index, catalog)

    assert decision.bucket == "strong_single"
    assert decision.candidates[0].sku == "KS0388-HLRJLGBL-62x68x38-LIGHTBLUE"
    assert decision.candidates[0].hard_conflicts == 0


def test_v2_cover_listing_is_candidate_not_no_candidate():
    matched_row = {
        "shopId": "596754",
        "marketplaceId": "ATVPDKIKX0DER",
        "asin": "B0DD43YBXC",
        "parentAsin": "B0DD446G24",
        "parentSku": "Bedpillow-p",
        "sku": "CEN665-Leaves-Grey-66-1",
        "title": "WOWMAX Cotton Pillow Cases ... No Filler, Light Gray",
        "mainImage": "image",
        "fnsku": "",
        "commoditySku": "KS0244-CMGDTH-66x50-GREY",
    }
    listing = dict(matched_row, sku="CEN665-Leaves-Grey-66-2", asin="B0DD425G4B", commoditySku=None)
    index = EvidenceIndex.build([matched_row])
    catalog = {
        "KS0244-CMGDTH-66x50-GREY": product(
            "KS0244-CMGDTH-66x50-GREY",
            "KS0244",
            "长方形枕套-纯棉贡缎提花-66x50cm-灰色",
            size=("66x50",),
            color=("灰色",),
            object_type="cover",
        )
    }

    decision = decide_v2(listing, index, catalog)

    assert decision.bucket == "candidate"
    assert decision.object_type == "cover"
    assert decision.candidates[0].sku == "KS0244-CMGDTH-66x50-GREY"


def test_v2_foam_title_is_not_special():
    index = EvidenceIndex.build([])
    listing = {
        "shopId": "596737",
        "marketplaceId": "ATVPDKIKX0DER",
        "sku": "LongHuxing-Foam-Lbai-100",
        "asin": "B0G911FKXZ",
        "parentAsin": "B0G8Z1JH4M",
        "parentSku": "LongDanHuxing-Foam",
        "title": (
            "Daneey Foam Headboard Pillow Twin, 22IN Tall Curve Pillow "
            "Headboard, Linen-Textured Wedge Foam Headboard Pillow"
        ),
        "mainImage": "",
        "fnsku": "",
        "commoditySku": None,
    }

    decision = decide_v2(listing, index, {})

    assert decision.object_type == "finished_product"
    assert decision.bucket == "no_candidate"


def test_v2_low_family_fallback_is_separate_bucket():
    listing = {
        "shopId": "1", "marketplaceId": "US", "sku": "unknown", "asin": "",
        "title": "unrelated title", "mainImage": "", "fnsku": "", "parentSku": ""
    }
    index = EvidenceIndex.build([])
    catalog = {
        "KS0001-HLR-153-BLUE": product(
            "KS0001-HLR-153-BLUE", "KS0001", "三角靠枕-荷兰绒-153-蓝色",
            size=("153",), color=("蓝色",)
        )
    }

    decision = decide_v2(
        listing,
        index,
        catalog,
        fallback_evidence={"KS0001-HLR-153-BLUE": ("family_candidate",)},
    )

    assert decision.bucket == "low_candidate"


def test_v2_combo_keeps_special_bucket_with_candidate():
    matched_row = {
        "shopId": "596765",
        "marketplaceId": "ATVPDKIKX0DER",
        "asin": "B0CKSTPYXV",
        "parentAsin": "B0CKSY151B",
        "parentSku": "BN-Sofa-Support",
        "sku": "BAI31038N0A62927SX-us",
        "title": "BNCKTRD Couch Cushion Support for Sagging Seat",
        "mainImage": "image",
        "fnsku": "",
        "commoditySku": "KS0156-NYBDSFH-52x52x5-BLACK",
    }
    listing = dict(
        matched_row,
        sku="BAI31038N0A62927SX-2pcs-us",
        asin="B0CKSVQ9Y9",
        commoditySku=None,
    )
    index = EvidenceIndex.build([matched_row])
    catalog = {
        "KS0156-NYBDSFH-52x52x5-BLACK": product(
            "KS0156-NYBDSFH-52x52x5-BLACK",
            "KS0156",
            "沙发支撑垫-鸟眼布滴塑防滑面料-52x52x5cm-黑色",
            size=("52x52x5",),
            color=("黑色",),
            object_type="finished_product",
        )
    }

    decision = decide_v2(listing, index, catalog)

    assert decision.bucket == "special_with_candidate"
    assert decision.object_type == "combo"
    assert decision.candidates[0].sku == "KS0156-NYBDSFH-52x52x5-BLACK"
    assert decision.candidates[0].hard_conflicts == 0
