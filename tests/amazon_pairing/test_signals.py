from amazon_pairing.attributes import extract_attributes, merge_attributes
from amazon_pairing.ontology import normalize_size_terms


def test_extract_attributes_can_parse_camel_case_color_in_msku():
    attrs = extract_attributes("FBADUS-CY1Blue-Queen", word_boundaries=False)

    assert attrs.color.values == ("蓝色",)


def test_merge_attributes_combines_title_and_msku_signals():
    title = extract_attributes("Blue Queen headboard pillow")
    msku = extract_attributes("FBADUS-CY1Blue-Queen", word_boundaries=False)

    merged = merge_attributes(title, msku)

    assert set(merged.color.values) == {"蓝色"}
    assert merged.size.values == ()


def test_bare_numeric_size_can_be_extracted_from_msku_for_agreement():
    assert normalize_size_terms("mianmapink-140", allow_bare=True) == ["140"]
    assert normalize_size_terms("CEN665-Leaves-Grey-66-2", allow_bare=True) == ["665", "66"]
