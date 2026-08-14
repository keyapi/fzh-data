from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.fallback import build_fallback_evidence


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


def test_fallback_retrieves_attribute_compatible_candidate():
    catalog = [
        product(
            "KS0001-HLR-153-DEEPBLUE",
            "KS0001",
            "三角靠枕-荷兰绒-153-深蓝色",
            size=("153",),
            color=("深蓝色",),
        ),
        product(
            "KS0001-HLR-194-DEEPBLUE",
            "KS0001",
            "三角靠枕-荷兰绒-194-深蓝色",
            size=("194",),
            color=("深蓝色",),
        ),
    ]
    rows = [
        {
            "sku": "unknown-blue-queen",
            "title": "Blue Queen headboard wedge pillow with removable cover",
            "asin": "",
            "parentSku": "",
            "mainImage": "",
            "fnsku": "",
        }
    ]

    fallback = build_fallback_evidence(rows, catalog, max_candidates=2)

    assert fallback[0] == {
        "KS0001-HLR-153-DEEPBLUE": ("family_candidate",),
        "KS0001-HLR-194-DEEPBLUE": ("family_candidate",),
    }


def test_fallback_cover_uses_cover_family_pool():
    catalog = [
        product(
            "KS0244-CMGDTH-66x50-GREY",
            "KS0244",
            "长方形枕套-纯棉贡缎提花-66x50cm-灰色",
            size=("66x50",),
            color=("灰色",),
            object_type="cover",
        ),
        product(
            "KS0001-HLR-153-GREY",
            "KS0001",
            "三角靠枕-荷兰绒-153-灰色",
            size=("153",),
            color=("灰色",),
        ),
    ]
    rows = [
        {
            "sku": "pillow-case-2",
            "title": "Pillow Covers with Envelop Closure, No Filler, Light Gray",
            "asin": "",
            "parentSku": "",
            "mainImage": "",
            "fnsku": "",
        }
    ]

    fallback = build_fallback_evidence(rows, catalog, max_candidates=3)

    assert fallback[0] == {"KS0244-CMGDTH-66x50-GREY": ("family_candidate",)}


def test_fallback_returns_empty_for_empty_input():
    assert build_fallback_evidence([], []) == []

def test_fallback_rejects_misaligned_predicted_families():
    import pytest
    with pytest.raises(ValueError, match="aligned"):
        build_fallback_evidence(
            [{"sku": "x", "title": "x"}],
            [],
            predicted_families=[],
        )

def test_fallback_honors_predicted_families():
    catalog = [
        product("KS0001-HLR-153-DEEPBLUE", "KS0001", "三角靠枕-荷兰绒-153-深蓝色", size=("153",), color=("深蓝色",)),
        product("KS0002-DM-153-BLUE", "KS0002", "平条靠枕-涤麻-153-蓝色", size=("153",), color=("蓝色",)),
    ]
    rows = [{"sku": "unknown", "title": "headboard wedge pillow blue queen", "asin": "", "parentSku": "", "mainImage": "", "fnsku": ""}]

    fallback = build_fallback_evidence(rows, catalog, predicted_families=[("KS0001",)])

    assert fallback[0] == {"KS0001-HLR-153-DEEPBLUE": ("family_candidate",)}
