import pytest

from channel_account_sync.names import (
    AMAZON_EU_COUNTRY_SITES,
    parse_aliases,
    reject_amazon_euro,
    sheet_to_en_name,
    split_account,
)


def test_illios_sheet_maps_to_illiospl():
    assert sheet_to_en_name("Illiosenergy") == "ILLIOSPL"
    assert sheet_to_en_name("AMZFZHSXDE") == "AMZFZHSXDE"


def test_parse_aliases_keeps_canonical_first_and_dedupes():
    got = parse_aliases("AMZFZHSXDE", "FZHSXDE, FZHSX欧洲, AMZFZHSXEUR, FZHSXDE")
    assert got[0] == "AMZFZHSXDE"
    assert got.count("FZHSXDE") == 1
    assert "AMZFZHSXEUR" in got


def test_amazon_euro_is_rejected():
    assert reject_amazon_euro("AMZFZHSXEUR", "Amazon", "EUR")
    assert reject_amazon_euro("AMZJohnaEU", "Amazon", "EU")
    assert reject_amazon_euro("AMZFZHSXDE", "Amazon", "DE") is None
    assert reject_amazon_euro("WFEU", "Wayfair", "EU") is None


def test_split_amazon_country_and_empty_code():
    code, region, empty = split_account("AMZFZHSXDE", "Amazon", "AMZ")
    assert (code, region, empty) == ("FZHSX", "DE", 0)
    code, region, empty = split_account("ILLIOSPL", "Illiosenergy", "ILLIOS")
    assert (code, region, empty) == (None, "PL", 1)
    code, region, empty = split_account("WFEU", "Wayfair", "WF")
    assert (code, region, empty) == (None, "EU", 1)


def test_split_refuses_amazon_eur():
    with pytest.raises(ValueError, match="country-level"):
        split_account("AMZFZHSXEUR", "Amazon", "AMZ")


def test_johna_eu_sites_are_nine_countries():
    assert AMAZON_EU_COUNTRY_SITES == (
        "DE",
        "ES",
        "FR",
        "IT",
        "UK",
        "PL",
        "NL",
        "BE",
        "SE",
    )
