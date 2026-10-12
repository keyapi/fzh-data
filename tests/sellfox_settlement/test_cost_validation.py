import pytest

from sellfox_settlement.cost_validation import main, match_transaction, summarize_coverage, validate_input


def test_split_components_retain_order_and_package_relationship():
    orders = [{"name": "a", "platform_order_id": "ORDER_1", "sale_account": "A", "order_type": "FBM", "order_items": [{"platform_sku": "MSKU", "tongtool_sku": "cover", "erp_item_code": "ITEM", "sx_shipping_cost": 12}, {"platform_sku": "MSKU", "tongtool_sku": "foam", "erp_item_code": "ITEM", "sx_shipping_cost": 20}], "packages": [{"package": "P1"}]}]
    result = match_transaction({"order_id": "ORDER", "sku": "MSKU", "account": "A"}, orders)
    assert result["status"] == "matched"
    assert result["item_count"] == 2
    assert result["package_count"] == 1


def test_duplicate_parent_child_is_ambiguous():
    orders = [{"name": n, "platform_order_id": n, "order_items": [{"platform_sku": "S"}]} for n in ["O", "O_1"]]
    assert match_transaction({"order_id": "O", "sku": "S"}, orders)["status"] == "ambiguous_parent_child"


def test_missing_sku_does_not_claim_order_item_coverage():
    orders = [{"name": "O", "platform_order_id": "O", "order_items": [{"platform_sku": "S"}]}]
    assert match_transaction({"order_id": "O", "sku": "OTHER"}, orders)["status"] == "sku_unmatched"


def test_nbsp_in_bill_sku_matches_the_same_platform_sku():
    orders = [{"name": "O", "platform_order_id": "O", "sale_account": "A", "order_items": [{"platform_sku": "DUS-CYForest -60CM"}]}]
    assert match_transaction({"order_id": "O", "sku": "DUS-CYForest\u00a0-60CM", "account": "A"}, orders)["status"] == "matched"


def test_account_scope_does_not_compare_another_shops_sku():
    orders = [
        {"name": "other", "sale_account": "AMZTOODDLYUS", "platform_order_id": "O", "order_type": "FBA", "order_items": [{"platform_sku": "OTHER-SKU"}]},
        {"name": "same", "sale_account": "AMZDANEEYUS", "platform_order_id": "O", "order_type": "FBA", "order_items": [{"platform_sku": "BILL-SKU"}]},
    ]
    assert match_transaction({"order_id": "O", "sku": "BILL-SKU", "account": "AMZDANEEYUS", "fulfillment": "FBA"}, orders)["status"] == "matched"
    assert match_transaction({"order_id": "O", "sku": "BILL-SKU", "account": "AMZMISSING", "fulfillment": "FBA"}, orders)["status"] == "order_unmatched"


def test_same_id_multiple_accounts_is_ambiguous():
    orders = [{"name": a, "sale_account": a, "platform_order_id": "O", "order_items": [{"platform_sku": "S"}]} for a in ["A", "B"]]
    assert match_transaction({"order_id": "O", "sku": "S"}, orders)["status"] == "ambiguous_account"


def test_fulfillment_conflict_is_preserved_for_review():
    orders = [{"name": "O", "platform_order_id": "O", "order_type": "FBA", "order_items": [{"platform_sku": "S"}]}]
    assert match_transaction({"order_id": "O", "sku": "S", "fulfillment": "FBM"}, orders)["status"] == "fulfillment_conflict"


def test_report_conserves_rows_and_excludes_non_order_cost_denominator():
    rows = [{"type": "Order", "order_id": "O", "sku": "S", "fulfillment": "FBA"}, {"type": "Transfer", "order_id": "", "sku": ""}]
    report, details = summarize_coverage(rows, [])
    assert report["input_rows"] == 2
    assert report["eligible_rows"] == 1
    assert report["excluded_rows"] == 1
    assert len(details) == 2


def test_missing_input_columns_fail_before_reporting_false_zero_coverage():
    with pytest.raises(ValueError, match="sku"):
        validate_input([{"order_id": "O", "type": "Order"}], {"order_id", "type", "sku"}, "transactions")


def test_cli_rejects_other_git_checkout_before_reading_inputs(tmp_path, monkeypatch, capsys):
    checkout = tmp_path / "another-checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["cost_validation", "--global-candidates", "--transactions", "missing.json", "--orders", "missing.json", "--output-dir", str(checkout / "nested" / "private")])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "Git checkout" in capsys.readouterr().err


def test_cli_requires_explicit_link_scope(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['cost_validation', '--transactions','missing.json',
                                    '--orders','missing.json','--output-dir','private'])
    with pytest.raises(SystemExit, match='2'):
        main()
    assert '--account-map' in capsys.readouterr().err


def test_cli_empty_account_map_holds_globally_matching_order(tmp_path, monkeypatch):
    import json
    rows = [{'source_file':'bill.csv','source_line':1,'type':'Order','order_id':'O','sku':'S','fulfillment':'FBA'}]
    orders = [{'name':'O','sale_account':'OTHER','platform_order_id':'O','order_items':[{'platform_sku':'S'}],'packages':[]}]
    for name, value in [('rows',rows),('orders',orders),('map',{})]:
        (tmp_path / (name+'.json')).write_text(json.dumps(value),encoding='utf-8')
    out = tmp_path / 'private'
    monkeypatch.setattr('sys.argv',['cost_validation','--transactions',str(tmp_path/'rows.json'),
                                   '--orders',str(tmp_path/'orders.json'),'--account-map',str(tmp_path/'map.json'),
                                   '--output-dir',str(out)])
    main()
    summary=json.loads((out/'cost_coverage_summary.json').read_text(encoding='utf-8'))
    assert summary['statuses']=={'account_unmapped':1}
    assert summary['link_scope']=='file_native_account'


def test_chargeback_link_probe_does_not_change_cost_denominator():
    rows = [{"type": "Chargeback Refund", "order_id": "O", "sku": "S"}]
    orders = [{"name": "O", "platform_order_id": "O", "order_items": [{"platform_sku": "S"}]}]
    report, details = summarize_coverage(rows, orders)
    assert report["eligible_rows"] == 0
    assert report["supplemental_link_statuses"] == {"matched": 1}
    assert details[0]["supplemental_link_probe"]["status"] == "matched"


def test_separately_fetched_retrocharge_order_still_does_not_claim_sku_coverage():
    rows = [{"type": "Refund_Retrocharge", "order_id": "O", "sku": ""}]
    supplemental = [{"name": "O", "platform_order_id": "O", "order_items": [{"platform_sku": "S"}]}]
    report, details = summarize_coverage(rows, [], supplemental)
    assert report["en_candidate_orders"] == 0
    assert report["eligible_rows"] == 0
    assert details[0]["supplemental_link_probe"]["status"] == "sku_missing"


def test_missing_file_account_mapping_never_falls_back_to_global_matching():
    rows = [{"source_file": "unmapped.csv", "type": "Order", "order_id": "O", "sku": "S"}]
    orders = [{"name": "O", "platform_order_id": "O", "sale_account": "OTHER", "order_items": [{"platform_sku": "S"}]}]
    report, details = summarize_coverage(rows, orders, account_by_file={"known.csv": "A"})
    assert details[0]["status"] == "account_unmapped"
    assert report["eligible_rows"] == 1


def test_supplemental_refund_uses_same_file_account_scope():
    rows = [{"source_file": "known.csv", "type": "Chargeback Refund", "order_id": "O", "sku": "S"}]
    orders = [{"name": "O", "platform_order_id": "O", "sale_account": "OTHER", "order_items": [{"platform_sku": "S"}]}]
    report, details = summarize_coverage(rows, orders, account_by_file={"known.csv": "A"})
    assert details[0]["supplemental_link_probe"]["status"] == "order_unmatched"
    assert report["eligible_rows"] == 0
