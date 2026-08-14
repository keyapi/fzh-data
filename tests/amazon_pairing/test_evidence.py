from amazon_pairing.evidence import EvidenceIndex


def matched_row(**overrides) -> dict:
    row = {
        "shopId": "596737",
        "marketplaceId": "ATVPDKIKX0DER",
        "asin": "B000TEST",
        "parentAsin": "B000PARENT",
        "parentSku": "PARENT",
        "sku": "LISTING",
        "title": "Test listing",
        "mainImage": "https://example.invalid/main.jpg",
        "fnsku": "X000TEST",
        "commoditySku": "KS0001-HLR-153-BLUE",
        "commodityName": "三角靠枕",
    }
    row.update(overrides)
    return row


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
