import pytest

from sellfox_settlement.account_validation import alias_index, resolve, infer_site, supplemental_shop_matches, require_private_output


def test_conflicts_are_not_silently_deduplicated():
    index, issues = alias_index([
        {"渠道账号": "AMZOneUS", "渠道账号别名": "SharedUS,SharedUS"},
        {"渠道账号": "AMZTwoUS", "渠道账号别名": "SharedUS"},
    ])
    assert resolve(index, "SharedUS")["status"] == "ambiguous"
    assert any(i["kind"] == "repeated_alias" for i in issues)


def test_case_variants_do_not_merge_accounts():
    index, _ = alias_index([{"渠道账号": "AMZOneUS"}, {"渠道账号": "AMZoneUS"}])
    assert resolve(index, "AMZOneUS")["accounts"] == ["AMZOneUS"]
    assert resolve(index, "AMZONEUS")["status"] == "ambiguous"


def test_currency_alone_cannot_identify_marketplace():
    assert infer_site("generic.csv", [], "EUR")["site"] is None
    assert infer_site("generic.csv", ["amazon.com"], "USD")["site"] == "US"


def test_filename_and_marketplace_conflict_is_retained():
    assert infer_site("某店加拿大202608.csv", ["amazon.com"], "USD")["status"] == "conflict"


def test_supplemental_match_requires_pdf_identity_and_marketplace_consensus():
    files = [
        {"file": "known", "pdf_legal_name": "Legal A", "site_evidence": {"site": "US"}, "shops": [{"sellerId": "seller-a", "marketplaceId": "us"}]},
        {"file": "other", "pdf_legal_name": "Legal B", "site_evidence": {"site": "CA"}, "shops": [{"sellerId": "seller-b", "marketplaceId": "ca"}]},
        {"file": "candidate", "pdf_legal_name": "Legal A", "site_evidence": {"site": "CA"}, "shops": [], "account_candidate": None},
    ]
    shops = [{"sellerId": "seller-a", "marketplaceId": "ca", "id": "new"}]
    result = supplemental_shop_matches(files, shops)
    assert result[0]["id"] == "new"
    assert result[0]["account"] is None
    assert supplemental_shop_matches(files, shops + [dict(shops[0], id="duplicate")]) == []


def test_private_reports_cannot_be_written_into_git_tree(tmp_path):
    (tmp_path/".git").write_text("gitdir: elsewhere", encoding="utf-8")
    with pytest.raises(ValueError, match="outside Git"):
        require_private_output(tmp_path/"reports")
