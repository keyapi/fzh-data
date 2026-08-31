from amazon_pairing.catalog import infer_product_object_type


def test_pillowcase_is_cover_product():
    assert (
        infer_product_object_type("长方形枕套-纯棉贡缎提花-66x50cm-灰色")
        == "cover"
    )


def test_ordinary_triangle_pillow_stays_finished():
    assert infer_product_object_type("三角靠枕-荷兰绒-153-深蓝色") == "finished_product"


def test_bundle_name_is_combo():
    assert infer_product_object_type("创意床品6件套-纯棉印花-灰色") == "combo"


def test_foam_in_ordinary_product_name_is_not_foam_part():
    assert infer_product_object_type("弧形海绵靠枕-涤麻-45-灰色") == "finished_product"
