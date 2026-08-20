from sellfox_cover_inventory.audit_sandbox import (
    page_total,
    parse_config,
    validate_cover_relation,
    validate_warehouse,
    warehouse_cautions,
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


def test_combo_isGroup_true_is_accepted():
    cover = {
        "isGroup": True,
        "childSkus": [{"sku": BASE["sellfox_bottom_sku"], "num": 1}],
    }
    assert validate_cover_relation(cover, BASE["sellfox_bottom_sku"]) == []


def test_page_total_prefers_totalSize():
    assert page_total({"totalSize": 0, "total": 9, "totalCount": 8}) == 0
    assert page_total({"totalCount": 3}) == 3
    assert page_total([]) is None


def test_fba_and_return_warehouses_are_blocked():
    assert "FBA" in validate_warehouse({"name": "FBA-US", "type": "2"}, "FBA-US")[0]
    assert "退货" in validate_warehouse({"name": "CENTRADE-退货产品仓", "type": "3"}, "CENTRADE-退货产品仓")[0]
    assert validate_warehouse({"name": "CENTRADE", "type": "3"}, "CENTRADE") == []


def test_ustx_main_warehouse_is_caution_not_cover_warehouse():
    notes = warehouse_cautions("FZH-DANEEY")
    assert notes
    assert "皮壳" in notes[0]
    assert warehouse_cautions("FZH-DANEEY-皮壳仓库") == []
    assert warehouse_cautions("CENTRADE") == []


def test_poland_sellfox_name_is_covers_pool_finished_is_caution():
    assert warehouse_cautions("POLAND") == []
    assert warehouse_cautions("FZHPoland-covers") == []
    assert warehouse_cautions("波兰-FZHPoland-covers") == []
    assert warehouse_cautions("POLAND-covers") == []
    notes = warehouse_cautions("FZHPoland-finished")
    assert notes
    assert "covers" in notes[0] or "皮壳" in notes[0]
    assert warehouse_cautions("DANEEY-主仓")
    assert warehouse_cautions("美中-DANEEY")
