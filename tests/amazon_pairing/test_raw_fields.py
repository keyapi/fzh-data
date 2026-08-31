import json

from amazon_pairing.data import AmazonListing, load_amazon_cache


def test_load_amazon_cache_preserves_all_raw_fields(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            [
                {
                    "shopId": "1",
                    "marketplaceId": "US",
                    "sku": "MSKU",
                    "asin": "ASIN",
                    "parentAsin": "PARENT",
                    "title": "Title",
                    "mainImage": "image",
                    "switchFulfillmentTo": "AFN",
                    "fnsku": "FNSKU",
                    "listingId": "LISTING",
                    "inventoryManage": {"commoditySku": "KS0001-A"},
                }
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_amazon_cache(path)

    assert isinstance(loaded[0], AmazonListing)
    assert loaded[0].listing_id == "LISTING"
    assert loaded[0].fnsku == "FNSKU"
    assert loaded[0].raw["inventoryManage"]["commoditySku"] == "KS0001-A"
