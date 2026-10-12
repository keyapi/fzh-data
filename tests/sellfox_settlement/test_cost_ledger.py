from sellfox_settlement.cost_ledger import build_ledger
import hashlib
import json


def digest(orders):
    return hashlib.sha256(json.dumps(orders, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


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
    probe['source_orders_sha256'] = digest([source])
    first = dict(probe, item_position=1, inputs=dict(probe['inputs'], quantity=2))
    result = build_ledger([source], component_probes=[first, probe], component_source_sha256=digest([source]))
    assert result['item_evidence'][0]['current_component_probe'] == first
    assert result['item_evidence'][1]['current_component_probe'] == probe
    wrong = dict(probe, inputs=dict(probe['inputs'], quantity=2))
    import pytest
    with pytest.raises(ValueError, match='component probe input'):
        build_ledger([source], component_probes=[first, wrong], component_source_sha256=digest([source]))


def test_component_probe_requires_hash_and_complete_identity_set():
    import pytest
    source = order('base')
    probe = {'order': source['name'], 'item_position': 1, 'source_orders_sha256': 'wrong',
             'inputs': {}, 'status': 'calculated'}
    with pytest.raises(ValueError, match='snapshot hash'):
        build_ledger([source], component_probes=[probe], component_source_sha256=digest([source]))
    with pytest.raises(ValueError, match='missing component'):
        build_ledger([source], component_probes=[], component_source_sha256=digest([source]))


def test_invalid_quantity_cannot_be_zero_or_fractional_cost_evidence():
    import pytest
    for value in [None, '', -1, '1.5', 'Infinity', True]:
        source = order('base')
        source['order_items'][0]['quantity'] = value
        with pytest.raises(ValueError, match='quantity'):
            build_ledger([source])


def test_component_duplicate_identity_rejected_without_legacy_fallback():
    import pytest
    source = order('base')
    probe = {'order': source['name'], 'item_position': 1,
             'source_orders_sha256': digest([source]), 'inputs': {}}
    with pytest.raises(ValueError, match='duplicate component'):
        build_ledger([source], component_probes=[probe, probe], component_source_sha256=digest([source]))


def test_repeated_refund_transactions_do_not_repeat_ledger_cost():
    source = order('base')
    row = {'type': 'Refund', 'en_order_names': [source['name']]}
    result = build_ledger([source], coverage=[row, row])
    assert result['summary']['output_transaction_rows'] == 2
    assert len(result['groups']) == 1
    assert result['groups'][0]['components']['product']['selected_snapshot_amount'] == '10'
    assert all(r['cost_action'] == 'hold_refund_policy' for r in result['transaction_evidence'])


def test_input_diagnosis_preserves_mapping_candidates_without_filling_cost():
    from sellfox_settlement.cost_ledger import diagnose_cost_inputs
    ledger = {'item_evidence': [
        {'en_order_name': 'o', 'item_position': 1, 'base_order_id': 'b', 'native_account': 'a',
         'warehouse': 'w', 'persisted_item': {'is_deliver_good': 1, 'tongtool_sku': 'alias', 'platform_sku': 'external'},
         'current_component_probe': {'status': 'no_item', 'inputs': {'erp_item_code': None}}}], 'groups': []}
    result = diagnose_cost_inputs(ledger, [{'item_fg': 'item', 'customer_item_code': 'alias'}], [{'name': 'w'}])
    assert result['details'][0]['reason'] == 'deliver_item_missing_erp_mapping'
    assert result['details'][0]['current_bom_exact_candidates'] == ['item']
    assert result['details'][0]['action'] == 'hold_no_mapping_write_or_cost_fill'


def test_missing_warehouse_and_non_delivery_placeholder_are_distinct():
    from sellfox_settlement.cost_ledger import diagnose_cost_inputs
    base = {'en_order_name': 'o', 'item_position': 1, 'base_order_id': 'b', 'native_account': 'a',
            'warehouse': '', 'persisted_item': {'is_deliver_good': 0},
            'current_component_probe': {'status': 'no_item', 'inputs': {}}}
    second = dict(base, item_position=2, persisted_item={'is_deliver_good': 1},
                  current_component_probe={'status': 'no_warehouse_config', 'inputs': {'erp_item_code': 'item'}})
    result = diagnose_cost_inputs({'item_evidence': [base, second], 'groups': []}, [], [])
    assert result['summary']['reason_counts'] == {'non_delivery_missing_item_placeholder': 1, 'warehouse_name_missing': 1}


def test_nondelivery_diagnostic_does_not_release_product_hold():
    from sellfox_settlement.cost_ledger import diagnose_cost_inputs
    parent, child = order('base', product='10'), order('base_1', product='12')
    for o in [parent, child]:
        o['order_items'][0]['is_deliver_good'] = 1
    child['order_items'].append(dict(child['order_items'][0], is_deliver_good=0, erp_item_code=None, sx_shipping_cost='0'))
    ledger = build_ledger([parent, child])
    for row in ledger['item_evidence']:
        row['current_component_probe'] = {'status': 'calculated', 'calculated': {'sx_shipping_cost': 12}} if row['persisted_item']['is_deliver_good'] else {'status': 'no_item', 'calculated': None}
    result = diagnose_cost_inputs(ledger, [], [])
    conflict = result['product_conflicts'][0]
    assert conflict['current_calculation_relation'] == 'incomplete'
    assert conflict['current_explicit_delivery_calculation_relation'] == 'equal'
    assert conflict['financial_status'] == 'hold_unchanged'
