from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.candidates_v2 import CandidateScore, rank_candidates
from amazon_pairing.ontology import classify_listing_object


EMPTY = ListingAttributes(
    AttributeValue(), AttributeValue(), AttributeValue(), AttributeValue()
)


def product(
    sku: str,
    family: str,
    name: str,
    size: tuple[str, ...] = (),
    color: tuple[str, ...] = (),
    object_type: str = "finished_product",
) -> CandidateProduct:
    attributes = ListingAttributes(
        size=AttributeValue(size, bool(size)),
        color=AttributeValue(color, bool(color)),
        fabric=AttributeValue(),
        count=AttributeValue(),
    )
    return CandidateProduct(sku, family, name, attributes, object_type)


def test_unique_asin_target_gets_strong_score():
    listing = {
        "sku": "DanCA1534D9-Blue-153",
        "title": (
            "Daneey Headboard Wedge Pillow ... with Removable Velvet Cover "
            "(Blue, Queen)"
        ),
        "asin": "B0CHFBPH2G",
        "mainImage": "",
        "fnsku": "",
        "parentSku": "DanVEL-Triangle-CA",
    }
    catalog = {
        "KS0001-HLR-153-DEEPBLUE": product(
            "KS0001-HLR-153-DEEPBLUE",
            "KS0001",
            "三角靠枕-荷兰绒-153-深蓝色",
            size=("153",),
            color=("深蓝色",),
        )
    }
    evidence = {
        "KS0001-HLR-153-DEEPBLUE": ("asin",),
    }

    ranked = rank_candidates(listing, evidence, catalog)

    assert ranked[0].sku == "KS0001-HLR-153-DEEPBLUE"
    assert ranked[0].score > 80
    assert ranked[0].hard_conflicts == 0
    assert "asin" in ranked[0].evidence


def test_reliable_size_conflict_lowers_rank():
    listing = {
        "sku": "DanCA1534D9-Blue-153",
        "title": (
            "Daneey Headboard Wedge Pillow ... with Removable Velvet Cover "
            "(Blue, Queen)"
        ),
        "asin": "B0CHFBPH2G",
        "mainImage": "",
        "fnsku": "",
        "parentSku": "DanVEL-Triangle-CA",
    }
    catalog = {
        "KS0001-HLR-153-DEEPBLUE": product(
            "KS0001-HLR-153-DEEPBLUE",
            "KS0001",
            "三角靠枕-荷兰绒-153-深蓝色",
            size=("153",),
            color=("深蓝色",),
        ),
        "KS0001-HLR-194-DEEPBLUE": product(
            "KS0001-HLR-194-DEEPBLUE",
            "KS0001",
            "三角靠枕-荷兰绒-194-深蓝色",
            size=("194",),
            color=("深蓝色",),
        ),
    }
    evidence = {
        "KS0001-HLR-153-DEEPBLUE": ("asin",),
        "KS0001-HLR-194-DEEPBLUE": ("title_exact",),
    }

    ranked = rank_candidates(listing, evidence, catalog)

    assert ranked[0].sku == "KS0001-HLR-153-DEEPBLUE"
    assert ranked[1].hard_conflicts > 0


def test_cover_listing_can_match_cover_product():
    listing = {
        "sku": "CEN665-Leaves-Grey-66-2",
        "title": (
            "WOWMAX Cotton Pillow Cases ... Pillow Covers with Envelop "
            "Closure, No Filler, Light Gray"
        ),
        "asin": "B0DD425G4B",
        "mainImage": "",
        "fnsku": "",
        "parentSku": "Bedpillow-p",
    }
    catalog = {
        "KS0244-CMGDTH-66x50-GREY": product(
            "KS0244-CMGDTH-66x50-GREY",
            "KS0244",
            "长方形枕套-纯棉贡缎提花-66x50cm-灰色",
            size=("66x50",),
            color=("灰色",),
            object_type="cover",
        ),
        "KS0001-HLR-153-GREY": product(
            "KS0001-HLR-153-GREY",
            "KS0001",
            "三角靠枕-荷兰绒-153-灰色",
            size=("153",),
            color=("灰色",),
        ),
    }
    evidence = {
        "KS0244-CMGDTH-66x50-GREY": ("parent_sku",),
        "KS0001-HLR-153-GREY": ("title_exact",),
    }

    ranked = rank_candidates(listing, evidence, catalog)

    assert ranked[0].sku == "KS0244-CMGDTH-66x50-GREY"
    assert ranked[0].hard_conflicts == 0


def test_conflicting_evidence_marks_conflict_targets():
    listing = {
        "sku": "CONFLICT",
        "title": "Generic pillow",
        "asin": "B000CONFLICT",
        "mainImage": "",
        "fnsku": "",
        "parentSku": "",
    }
    catalog = {
        "KS0001-HLR-153-BLUE": product(
            "KS0001-HLR-153-BLUE",
            "KS0001",
            "三角靠枕-荷兰绒-153-蓝色",
            size=("153",),
            color=("蓝色",),
        ),
        "KS0248-HLR-153-BLUE": product(
            "KS0248-HLR-153-BLUE",
            "KS0248",
            "三角靠枕无扣-荷兰绒-153-蓝色",
            size=("153",),
            color=("蓝色",),
        ),
    }
    evidence = {
        "KS0001-HLR-153-BLUE": ("asin",),
        "KS0248-HLR-153-BLUE": ("asin",),
    }

    ranked = rank_candidates(listing, evidence, catalog)
    conflicts = {row.sku for row in ranked if row.is_strong_conflict}

    assert conflicts == {"KS0001-HLR-153-BLUE", "KS0248-HLR-153-BLUE"}

def test_fabric_terms_allow_broad_material_agreement():
    listing = {
        "sku": "DanCA1534D9-Blue-153",
        "title": "... with Removable Velvet Cover (Blue, Queen)",
        "asin": "B0CHFBPH2G", "mainImage": "", "fnsku": "", "parentSku": ""
    }
    catalog = {
        "KS0001-HLR-153-DEEPBLUE": CandidateProduct(
            "KS0001-HLR-153-DEEPBLUE", "KS0001", "三角靠枕-荷兰绒-153-深蓝色",
            ListingAttributes(
                AttributeValue(("153",), True), AttributeValue(("深蓝色",), True),
                AttributeValue(("荷兰绒",), True), AttributeValue()
            ), "finished_product"
        )
    }
    ranked = rank_candidates(listing, {"KS0001-HLR-153-DEEPBLUE": ("asin",)}, catalog)
    assert ranked[0].hard_conflicts == 0
