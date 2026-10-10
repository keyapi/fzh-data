from decimal import Decimal

import pytest

from sellfox_settlement.tail_validation import select_tail, diagnose, parent_child_risks


def item(**values):
    return dict(platform_sku="SKU", quantity=2, last_leg_fee=0,
                upload_allocated_carrier_fee_rmb=0, allocated_carrier_fee_rmb=0,
                hist_predict_fee=0, allocated_tt_fee_rmb=0, **values)


def test_priority_and_no_fallback():
    row = item()
    row.update(upload_allocated_carrier_fee_rmb=12, allocated_carrier_fee_rmb=10,
               hist_predict_fee=8, allocated_tt_fee_rmb=9)
    assert select_tail({}, row)[0:2] == (Decimal('12.0000'), 'upload_allocated_carrier_fee_rmb')
    row.update(upload_allocated_carrier_fee_rmb=0)
    assert select_tail({}, row)[1] == 'allocated_carrier_fee_rmb'
    row.update(allocated_carrier_fee_rmb=0, hist_predict_fee=0)
    assert select_tail({}, row)[0] == 0
    assert select_tail({}, row, '通途尾程费用')[0] == 9


@pytest.mark.parametrize('order', [{'order_type': 'FBA'}, {'platform_code': 'PB'},
                                  {'sale_account': 'TTTOODDLYUS'}, {'warehouse_name': '多渠道仓库-A'}])
def test_excluded_tail_even_with_actual(order):
    row = item()
    row['allocated_carrier_fee_rmb'] = 10
    assert select_tail(order, row)[0] == 0


def test_parent_equal_amount_is_hold_not_auto_dedup():
    orders = [{'name': 'parent', 'sale_account': 'A', 'platform_order_id': '123',
               'order_items': [dict(item(), last_leg_fee=10)], 'packages': [{'package': 'P1'}]},
              {'name': 'child', 'sale_account': 'A', 'platform_order_id': '123_1',
               'order_items': [dict(item(), last_leg_fee=10)], 'packages': [{'package': 'P1'}]}]
    risk = parent_child_risks(orders)[0]
    assert risk['status'] == 'hold_fee_unit_or_allocation_unproven'
    assert risk['equal_positive_totals'] is True
    assert risk['shared_package_ids'] == ['P1']


def test_trace_denominator_and_distinct_items():
    row = item()
    row['allocated_tt_fee_rmb'] = 8
    orders = [{'name': 'O', 'platform_order_id': '1', 'sale_account': 'A',
               'order_type': 'FBM', 'order_items': [row], 'packages': []}]
    coverage = [dict(status='matched', fulfillment='FBM', sku='SKU', en_order_names=['O'],
                     source_file='f.csv', source_line=i) for i in [1, 2]]
    report = diagnose(orders, coverage)
    assert report['summary']['input_transaction_rows'] == 2
    assert report['summary']['matched_item_occurrences'] == 2
    assert report['summary']['unique_matched_items'] == 1
    assert report['summary']['tt_positive_unselected_occurrences'] == 2
    assert report['details'][0]['available_not_selected']['allocated_tt_fee_rmb'] == '8.0000'
    assert report['details'][0]['amount_basis'] == 'persisted_allocated_row_amount_not_multiplied_by_quantity'


def test_missing_link_is_retained():
    report = diagnose([], [dict(status='matched', sku='SKU', en_order_names=['missing'])])
    assert report['summary']['excluded_transaction_rows'] == 1
    assert report['excluded'][0]['reason'] == 'linked_order_missing'


def test_non_finite_rejected():
    row = item()
    row['hist_predict_fee'] = 'NaN'
    with pytest.raises(ValueError):
        select_tail({}, row)
