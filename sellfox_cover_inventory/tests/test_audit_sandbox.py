from sellfox_cover_inventory.audit_sandbox import (
    parse_config,
    validate_cover_relation,
)


BASE = {
    "warehouse_name": "CENTRADE",
    "tongtool_base_sku": "TT123",
    "sellfox_bottom_sku": "KS0001-DM-194-GREY",
    "sellfox_cover_sku": "PK#KS0001-DM-194-GREY",
}


def test_parse_config_accepts_one_explicit_mapping():
    config = parse_config(BASE)
    assert config.warehouse_name == "CENTRADE"
    assert config.tongtool_cover_sku == ""


def test_parse_config_rejects_batch():
    try:
        parse_config([BASE])
    except ValueError as exc:
        assert "one JSON object" in str(exc)
    else:
        raise AssertionError("batch config should be rejected")


def test_valid_combo_relation_has_no_problems():
    cover = {
        "isGroup": "1",
        "childSkus": [{"sku": BASE["sellfox_bottom_sku"], "num": "1"}],
    }
    assert validate_cover_relation(cover, BASE["sellfox_bottom_sku"]) == []


def test_processing_product_is_blocked():
    cover = {
        "isGroup": "2",
        "childSkus": [{"sku": BASE["sellfox_bottom_sku"], "num": 1}],
    }
    assert "isGroup must be 1" in validate_cover_relation(cover, BASE["sellfox_bottom_sku"])[0]


def test_wrong_child_or_quantity_is_blocked():
    cover = {"isGroup": 1, "childSkus": [{"sku": "OTHER", "num": 2}]}
    problems = validate_cover_relation(cover, BASE["sellfox_bottom_sku"])
    assert len(problems) == 2
