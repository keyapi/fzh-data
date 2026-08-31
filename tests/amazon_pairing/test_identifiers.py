from amazon_pairing.identifiers import IdentifierAffinityIndex


def test_msku_affinity_transfers_target_from_similar_historical_sku():
    index = IdentifierAffinityIndex.build(
        [
            {
                "sku": "FBADUS-CY1Blue-Queen",
                "commoditySku": "KS0002-DL-153-DEEPBLUE",
            },
            {
                "sku": "LongHuxing-Foam-Lbai-100",
                "commoditySku": "KS0524-HLR-100-WHITE",
            },
        ]
    )

    candidates = index.candidates_for_listing(
        {"sku": "FBADUS-CY1Blue-Queen-FBA"},
        max_targets=3,
    )

    assert candidates["KS0002-DL-153-DEEPBLUE"] == ("msku_affinity",)
    assert next(iter(candidates)) == "KS0002-DL-153-DEEPBLUE"


def test_msku_affinity_returns_empty_for_empty_catalog():
    index = IdentifierAffinityIndex.build([])

    assert index.candidates_for_listing({"sku": "anything"}) == {}
