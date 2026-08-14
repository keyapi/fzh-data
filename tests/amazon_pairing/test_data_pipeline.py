import json
from pathlib import Path

import pandas as pd

from amazon_pairing.data import build_label_audit, load_amazon_cache


def test_load_amazon_cache_keeps_required_listing_fields(tmp_path: Path):
    cache = tmp_path / "amazon_matched.json"
    cache.write_text(
        json.dumps(
            [
                {
                    "shopId": "1",
                    "marketplaceId": "US",
                    "sku": "MSKU-1",
                    "asin": "B001",
                    "title": "Pillow",
                    "commoditySku": "KS0001-A",
                    "mainImage": "https://example.invalid/a.jpg",
                    "onlineStatus": "Active",
                }
            ]
        ),
        encoding="utf-8",
    )

    rows = load_amazon_cache(cache)

    assert rows[0].msku == "MSKU-1"
    assert rows[0].target_sku == "KS0001-A"
    assert rows[0].image_url.endswith("a.jpg")


def test_label_audit_uses_unique_alias_mapping_agreement():
    listings = [
        {"msku": "ALIAS-1", "target_sku": "KS0001-A"},
        {"msku": "COLLISION", "target_sku": "KS0001-B"},
        {"msku": "CURRENT-ONLY", "target_sku": "KS0001-C"},
    ]
    aliases = pd.DataFrame(
        [
            {"通途SKU": "TT1", "SKU别名": "ALIAS-1"},
            {"通途SKU": "TT2", "SKU别名": "COLLISION"},
            {"通途SKU": "TT3", "SKU别名": "COLLISION"},
        ]
    )
    mapping = pd.DataFrame(
        [
            {"通途SKU": "TT1", "赛狐SKU": "KS0001-A"},
            {"通途SKU": "TT2", "赛狐SKU": "KS0001-B"},
            {"通途SKU": "TT3", "赛狐SKU": "KS0001-D"},
        ]
    )

    audited = build_label_audit(listings, aliases, mapping)
    by_msku = {row["msku"]: row for row in audited}

    assert by_msku["ALIAS-1"]["tier"] == "gold_a"
    assert by_msku["COLLISION"]["tier"] == "quarantine"
    assert by_msku["CURRENT-ONLY"]["tier"] == "silver"


def test_label_audit_quarantines_combo_target_even_with_agreement():
    listings = [{"msku": "SET-1", "target_sku": "TJ#KS1x2-001"}]
    aliases = pd.DataFrame([{"通途SKU": "TTSET", "SKU别名": "SET-1"}])
    mapping = pd.DataFrame([{"通途SKU": "TTSET", "赛狐SKU": "TJ#KS1x2-001"}])

    audited = build_label_audit(listings, aliases, mapping)

    assert audited[0]["tier"] == "quarantine"
    assert "non_ordinary_target" in audited[0]["reasons"]


def test_mapping_main_sku_is_an_exact_key_even_without_alias_export_row():
    listings = [{"msku": "TT-MAIN", "target_sku": "KS0001-A"}]
    aliases = pd.DataFrame(columns=["通途SKU", "SKU别名"])
    mapping = pd.DataFrame([{"通途SKU": "TT-MAIN", "赛狐SKU": "KS0001-A"}])

    audited = build_label_audit(listings, aliases, mapping)

    assert audited[0]["tier"] == "gold_a"


def test_non_product_target_is_quarantined_without_alias_evidence():
    listings = [{"msku": "MATERIAL-1", "target_sku": "HM1510-FOAM-1"}]

    audited = build_label_audit(
        listings,
        pd.DataFrame(columns=["通途SKU", "SKU别名"]),
        pd.DataFrame(columns=["通途SKU", "赛狐SKU"]),
    )

    assert audited[0]["tier"] == "quarantine"
    assert "non_ordinary_target" in audited[0]["reasons"]
