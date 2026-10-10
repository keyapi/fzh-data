from sellfox_settlement.cost_ledger import build_ledger


def order(oid, account='shop', product='10', tail='7'):
    return {'name': account + oid, 'platform_order_id': oid, 'sale_account': account,
            'warehouse_name': 'warehouse', 'order_items': [{'platform_sku': 'sku', 'tongtool_sku': 'sku',
            'quantity': 2, 'sx_shipping_cost': product, 'first_freight': '3',
            'valuation_rate': '0', 'last_leg_fee': tail}]}


def test_splits_exclude_parent_without_multiplying_quantity():
    result = build_ledger([order('base'), order('base_1', product='6'), order('base_2', product='4')])
    group = result['groups'][0]
    assert group['components']['product']['included_snapshot_amount'] == '10'
    assert group['components']['tail']['included_snapshot_amount'] == '14'
    assert group['source_item_rows'] == 3
    assert group['selected_quantity'] == '4'
    assert result['summary']['excluded_parent_item_rows'] == 1


def test_product_difference_is_held_independently():
    result = build_ledger([order('base'), order('base_1', product='12')])
    components = result['groups'][0]['components']
    assert components['product']['status'] == 'hold_parent_children_difference'
    assert components['product']['included_snapshot_amount'] is None
    assert components['product']['selected_snapshot_amount'] == '12'
    assert components['first']['included_snapshot_amount'] == '3'


def test_account_boundary_and_missing_values_are_not_zero():
    a, b = order('base', account='a'), order('base_1', account='b')
    a['order_items'][0]['sx_shipping_cost'] = None
    result = build_ledger([a, b])
    assert len(result['groups']) == 2
    assert result['groups'][0]['components']['product']['status'] == 'hold_missing_amount'


def test_refund_kept_as_evidence_without_cost_reversal():
    result = build_ledger([order('base')], coverage=[{'source_file': 'private.csv', 'source_line': 1,
                           'order_id': 'base', 'type': 'Refund', 'status': 'matched'}])
    assert result['transaction_evidence'][0]['cost_action'] == 'hold_refund_policy'
    assert result['groups'][0]['components']['product']['included_snapshot_amount'] == '10'


def test_duplicate_names_fail_closed():
    import pytest
    with pytest.raises(ValueError, match='duplicate'):
        build_ledger([order('base'), order('base')])


def test_missing_columns_fail_and_nonfinite_never_enter_sums():
    import pytest
    with pytest.raises(ValueError, match='missing columns'):
        build_ledger([{'name': 'x'}])
    with pytest.raises(ValueError, match='non-finite'):
        build_ledger([order('base', product='NaN')])


def test_accountless_current_probe_is_not_attached_to_two_accounts():
    # Synthetic duplicate probe keys must not attach even with distinct account IDs.
    probe = {'order': 'base', 'sku': 'sku', 'status': 'calculated', 'calculated': {'sx_shipping_cost': 90}}
    result = build_ledger([order('base', account='a'), order('base', account='b')], [probe])
    assert all(row['current_bom_raw_probe'] is None for row in result['item_evidence'])
    assert result['summary']['input_item_rows'] == result['summary']['output_item_evidence_rows'] == 2


def test_current_probe_uses_en_name_not_platform_order_id():
    source = order('base')
    source['order_items'][0]['tongtool_sku'] = 'different-internal-sku'
    probe = {'order': source['name'], 'sku': 'different-internal-sku', 'status': 'calculated', 'calculated': {'sx_shipping_cost': 90}}
    result = build_ledger([source], [probe])
    assert result['item_evidence'][0]['current_bom_raw_probe'] == probe


def test_named_probe_does_not_cross_accounts_sharing_platform_order_id():
    a, b = order('base', account='a'), order('base', account='b')
    probe = {'order': a['name'], 'sku': 'sku', 'status': 'calculated'}
    result = build_ledger([a, b], [probe])
    assert result['item_evidence'][0]['current_bom_raw_probe'] == probe
    assert result['item_evidence'][1]['current_bom_raw_probe'] is None


def test_repeated_component_sku_does_not_duplicate_named_probe():
    source = order('base')
    source['order_items'].append(dict(source['order_items'][0]))
    probe = {'order': source['name'], 'sku': 'sku', 'status': 'calculated'}
    result = build_ledger([source], [probe])
    assert all(i['current_bom_raw_probe'] is None for i in result['item_evidence'])


def test_empty_order_items_are_missing_not_zero_cost():
    source = order('base')
    source['order_items'] = []
    result = build_ledger([source])
    assert all(c['status'] == 'hold_missing_items' and c['included_snapshot_amount'] is None
               for c in result['groups'][0]['components'].values())


def test_zero_product_does_not_erase_tail_or_replace_from_generic_cost():
    zero = order('base_1', product='0', tail='222.42')
    zero['order_items'][0]['item_cost'] = '486.39'
    result = build_ledger([order('base', product='0'), zero])
    assert result['groups'][0]['components']['product']['selected_snapshot_amount'] == '0'
    assert result['groups'][0]['components']['tail']['selected_snapshot_amount'] == '222.42'
    assert result['summary']['selected_zero_product_groups'] == 1


def test_component_probe_binds_position_and_exact_inputs():
    source = order('base')
    source['order_items'].append(dict(source['order_items'][0], quantity=4))
    probe = {'order': source['name'], 'item_position': 2, 'sku': 'sku', 'status': 'calculated',
             'inputs': {'erp_item_code': None, 'warehouse_name': 'warehouse', 'tongtool_sku': 'sku',
                        'quantity': 4, 'split_package_cost_factor': 1}}
    result = build_ledger([source], component_probes=[probe])
    assert result['item_evidence'][0]['current_component_probe'] is None
    assert result['item_evidence'][1]['current_component_probe'] == probe
    wrong = dict(probe, inputs=dict(probe['inputs'], quantity=2))
    import pytest
    with pytest.raises(ValueError, match='component probe input'):
        build_ledger([source], component_probes=[wrong])
