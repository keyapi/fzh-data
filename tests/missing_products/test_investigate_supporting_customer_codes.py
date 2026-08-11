from missing_products.investigate_supporting_customer_codes import summarize


def test_summary_deduplicates_same_item_and_flags_only_cross_item_duplicates():
    rows = [
        {"item_code": "HM1510-A", "ref_code": "TT1-Foam"},
        {"item_code": "HM1510-A", "ref_code": "TT1-Foam"},
        {"item_code": "HM1510-A", "ref_code": "TT2-Foam"},
        {"item_code": "HM1510-B", "ref_code": "TT2-Foam"},
    ]

    result = summarize(rows)

    assert result["row_count"] == 4
    assert result["unique_item_customer_pairs"] == 3
    assert result["duplicate_customer_codes"] == {
        "TT2-Foam": ["HM1510-A", "HM1510-B"]
    }
