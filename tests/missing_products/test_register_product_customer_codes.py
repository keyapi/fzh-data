import pytest

from missing_products.register_product_customer_codes import (
    REGISTRATIONS,
    validate_registration,
)


def test_registration_scope_contains_only_approved_three_cover_codes():
    assert REGISTRATIONS == {
        "C/Linen-Coffee-194-661-WOW-Cover": "KS0001-CMM-194-COFFEE",
        "C/Linen-Natural-183-688-wow-Cover": "KS0001-XMMBS-183-HEMPNATURAL",
        "TT0000750K0063009-Cover": "KS0002-DL-100-BLACK",
    }


def test_validation_requires_ks_product_target_and_matching_base_code():
    validate_registration(
        "A-Cover",
        "KS0001-A",
        target={"item_code": "KS0001-A", "customer_items": [{"ref_code": "A"}]},
        occupied_by=[],
    )


@pytest.mark.parametrize(
    ("target_code", "target", "occupied_by", "message"),
    [
        ("PK#KS0001-A", {"item_code": "PK#KS0001-A", "customer_items": []}, [], "EN产品"),
        ("KS0001-A", {"item_code": "KS0001-A", "customer_items": []}, [], "基码"),
        ("KS0001-A", {"item_code": "KS0001-A", "customer_items": [{"ref_code": "A"}]}, ["KS9999-X"], "已被占用"),
    ],
)
def test_validation_rejects_unsafe_registration(target_code, target, occupied_by, message):
    with pytest.raises(ValueError, match=message):
        validate_registration("A-Cover", target_code, target, occupied_by)
