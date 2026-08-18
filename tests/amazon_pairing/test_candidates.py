from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct, ListingQuery, generate_candidates
from amazon_pairing.features import build_pair_features


def attrs(size=(), color=(), fabric=(), count=(), reliable=True):
    return ListingAttributes(
        size=AttributeValue(tuple(size), reliable and bool(size)),
        color=AttributeValue(tuple(color), reliable and bool(color)),
        fabric=AttributeValue(tuple(fabric), reliable and bool(fabric)),
        count=AttributeValue(tuple(count), reliable and bool(count)),
    )


CATALOG = (
    CandidateProduct("KS0001-HLR-153-GREY", "KS0001", "三角靠枕 灰色", attrs(["153"], ["灰色"], ["绒布"])),
    CandidateProduct("KS0001-HLR-153-BLUE", "KS0001", "三角靠枕 蓝色", attrs(["153"], ["蓝色"], ["绒布"])),
    CandidateProduct("KS0001-HLR-194-GREY", "KS0001", "三角靠枕 灰色", attrs(["194"], ["灰色"], ["绒布"])),
    CandidateProduct("KS0002-HLR-153-GREY", "KS0002", "其他靠枕", attrs(["153"], ["灰色"])),
)


def test_candidate_generation_blocks_family_and_reliable_conflicts():
    result = generate_candidates(
        ListingQuery(
            msku="triangle-grey-153",
            title="Grey velvet triangle pillow 153 cm",
            predicted_families=("KS0001",),
            attributes=attrs(["153"], ["灰色"], ["绒布"]),
        ),
        CATALOG,
    )

    assert [candidate.product.sku for candidate in result.candidates] == [
        "KS0001-HLR-153-GREY"
    ]
    assert result.used_fallback is False


def test_candidate_generation_does_not_filter_on_soft_size():
    result = generate_candidates(
        ListingQuery(
            msku="triangle-grey-153",
            title="Grey triangle pillow model 153",
            predicted_families=("KS0001",),
            attributes=attrs(["153"], ["灰色"], reliable=False),
        ),
        CATALOG,
    )

    assert {candidate.product.sku for candidate in result.candidates} == {
        "KS0001-HLR-153-GREY",
        "KS0001-HLR-153-BLUE",
        "KS0001-HLR-194-GREY",
    }


def test_candidate_generation_falls_back_when_reliable_filters_empty_pool():
    result = generate_candidates(
        ListingQuery(
            msku="triangle-purple-999",
            title="Purple triangle pillow 999 cm",
            predicted_families=("KS0001",),
            attributes=attrs(["999"], ["紫色"]),
        ),
        CATALOG,
    )

    assert result.used_fallback is True
    assert result.warnings == ("reliable_attributes_removed_all_candidates",)
    assert len(result.candidates) == 3


def test_exact_alias_evidence_is_kept_ahead_of_attribute_filtering():
    result = generate_candidates(
        ListingQuery(
            msku="known-alias",
            title="Blue pillow",
            predicted_families=("KS0001",),
            attributes=attrs(color=["蓝色"]),
            exact_targets=("KS0001-HLR-153-GREY",),
        ),
        CATALOG,
    )

    assert result.candidates[0].product.sku == "KS0001-HLR-153-GREY"
    assert result.candidates[0].evidence == ("exact_target",)


def test_pair_features_expose_agreements_and_contradictions():
    query = ListingQuery(
        msku="triangle-grey-153",
        title="Grey velvet triangle pillow 153 cm",
        predicted_families=("KS0001",),
        attributes=attrs(["153"], ["灰色"], ["绒布"]),
    )

    matched = build_pair_features(query, CATALOG[0])
    wrong_color = build_pair_features(query, CATALOG[1])

    assert matched["size_agreement"] == 1.0
    assert matched["color_agreement"] == 1.0
    assert matched["reliable_conflicts"] == 0.0
    assert wrong_color["color_contradiction"] == 1.0
    assert wrong_color["reliable_conflicts"] == 1.0
