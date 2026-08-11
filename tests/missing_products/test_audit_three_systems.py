from collections import defaultdict

from missing_products.audit_three_systems import (
    count_exact_matches,
    match_tongtu_to_en_products,
    sellfox_status_for_products,
)


def test_complete_suffix_code_uses_exact_product_registrations_first():
    customer_to_products = defaultdict(list)
    customer_to_products["tt0031177k0063900-cover"] = [
        "KS0340-HLR-50-GREY",
        "KS0342-HLR-50-GREY",
    ]
    customer_to_products["tt0031177k0063900"] = ["KS9999-WRONG-CANDIDATE"]

    result = match_tongtu_to_en_products(
        "TT0031177K0063900-Cover", customer_to_products
    )

    assert result.status == "已精确登记"
    assert result.exact_products == (
        "KS0340-HLR-50-GREY",
        "KS0342-HLR-50-GREY",
    )
    assert result.candidate_products == ("KS9999-WRONG-CANDIDATE",)


def test_base_code_match_is_candidate_not_registration():
    customer_to_products = defaultdict(list)
    customer_to_products["curve-pillow-50"] = ["KS0342-HLR-50-GREY"]

    result = match_tongtu_to_en_products(
        "Curve-Pillow-50-Foam", customer_to_products
    )

    assert result.status == "仅基码匹配"
    assert result.exact_products == ()
    assert result.candidate_products == ("KS0342-HLR-50-GREY",)


def test_plain_sku_exact_match_has_no_separate_base_candidate():
    customer_to_products = defaultdict(list)
    customer_to_products["tt0001"] = ["KS0001-CMM-153-PURPLE"]

    result = match_tongtu_to_en_products("TT0001", customer_to_products)

    assert result.status == "已精确登记"
    assert result.exact_products == ("KS0001-CMM-153-PURPLE",)
    assert result.candidate_products == ()


def test_exact_match_count_ignores_unmatched_entries():
    matches = {
        "A-Cover": match_tongtu_to_en_products(
            "A-Cover", {"a-cover": ["KS0001-A"]}
        ),
        "B-Foam": match_tongtu_to_en_products(
            "B-Foam", {"b": ["KS0002-B"]}
        ),
        "C": match_tongtu_to_en_products("C", {}),
    }

    assert count_exact_matches(matches) == 1


def test_sellfox_status_uses_en_product_codes_not_tongtu_code():
    status, present, missing = sellfox_status_for_products(
        ("KS0001-A", "KS0001-B"), {"KS0001-A": {"sku": "KS0001-A"}}
    )

    assert status == "部分存在"
    assert present == ("KS0001-A",)
    assert missing == ("KS0001-B",)


def test_sellfox_status_is_pending_when_no_product_mapping_exists():
    status, present, missing = sellfox_status_for_products((), {})

    assert status == "待EN产品映射"
    assert present == ()
    assert missing == ()
