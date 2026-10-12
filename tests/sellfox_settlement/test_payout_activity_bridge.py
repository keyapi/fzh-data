import pytest

from sellfox_settlement.payout_activity_bridge import build_bridge


def csv(**kw):
    return dict(source_file='bill.csv', source_line=2, type='Order', order_id='O', sku='S',
                currency='USD', date_time='2026-08-01T01:02:03-07:00',
                transaction_release_date='2026-08-10T01:00:00-07:00',
                transaction_status='Released', product_sales='12', **kw)


def v2(**kw):
    row = dict(id='1', sellerId='seller', marketplaceId='market', orderId='O', msku='S',
               transactionType='Order', currency='USD', settlementId='settlement',
               reportType='standard', siteTimeStr='2026-08-01 01:02:03',
               postedDateTimeStr='2026-08-01 08:02:03', amountType='ItemPrice',
               amountDescription='Principal', amount='10')
    row.update(kw)
    return row


def scope():
    return [dict(file='C:/private/bill.csv', account='A', sellerId='seller', marketplaceId='market')]


def test_unique_event_preserves_subject_difference_and_release_time():
    r = build_bridge([csv()], [v2(), v2(id='2', amountType='ItemFees', amountDescription='Commission', amount='-1')], scope())
    link = r['csv_evidence'][0]
    assert link['status'] == 'unique_event_evidence'
    assert link['time_status'] == 'site_wall_clock_equal'
    assert link['subjects']['product_sales']['csv_minus_v2'] == '2'
    assert link['release_date'] == '2026-08-10T01:00:00-07:00'
    assert r['summary']['v2_rows'] == 2
    assert all(x['status'] == 'unique_event_evidence' for x in r['v2_evidence'])


def test_repeated_csv_and_multiple_settlements_are_not_deduplicated():
    r = build_bridge([csv(), csv()], [v2(), v2(id='2', settlementId='another')], scope())
    assert all(x['status'] == 'multiple_event_candidates' for x in r['csv_evidence'])
    assert all(x['status'] == 'multiple_csv_candidates' for x in r['v2_evidence'])
    assert all('subjects' not in x for x in r['csv_evidence'])


def test_no_cross_account_currency_sku_or_refund_join():
    other = [v2(id=str(i), **kw) for i, kw in enumerate([
        dict(sellerId='other'), dict(currency='CAD'), dict(msku='other'), dict(transactionType='Refund')])]
    r = build_bridge([csv()], other, scope())
    assert r['csv_evidence'][0]['status'] == 'key_unmatched'
    assert r['summary']['v2_status_counts']['key_unmatched'] == 4


def test_non_order_missing_keys_unknown_subjects_and_time_are_retained():
    a = csv(); a['type']='Transfer'
    b = csv(); b['sku']=''
    rows = [v2(siteTimeStr='bad', amountDescription='UnrecognizedSubject'), v2(id='2', transactionType='ServiceFee')]
    r = build_bridge([a, b, csv()], rows, scope())
    assert [x['status'] for x in r['csv_evidence']] == ['non_order_transaction', 'missing_sku', 'unique_event_evidence']
    assert r['csv_evidence'][2]['time_status'] == 'unparsed_site_time'
    assert r['events'][0]['unknown_subject_rows'] == [0]
    assert r['summary']['csv_rows'] == 3 and r['summary']['v2_rows'] == 2


def test_same_key_different_time_stays_candidate_not_forced_equal():
    r = build_bridge([csv()], [v2(siteTimeStr='2026-08-02 01:02:03')], scope())
    assert r['csv_evidence'][0]['time_status'] == 'site_wall_clock_different'
    assert r['csv_evidence'][0]['status'] == 'unique_event_evidence'


def test_file_scope_collision_and_missing_currency_never_guess():
    with pytest.raises(ValueError, match='duplicate scope'):
        build_bridge([csv()], [], scope()+scope())
    a=csv(); a['currency']=''
    r=build_bridge([a], [v2()], scope())
    assert r['csv_evidence'][0]['status']=='missing_currency'


def test_many_csv_rows_to_single_v2_event_are_ambiguous():
    r=build_bridge([csv(), csv()], [v2()], scope())
    assert all(x['status']=='multiple_csv_candidates' for x in r['csv_evidence'])
    assert all('subjects' not in x for x in r['csv_evidence'])


def test_release_comparison_duplicate_native_ids_and_invalid_amount_are_visible():
    a=csv(); a['transaction_release_date']='2026-08-01T01:02:03-07:00'
    r=build_bridge([a], [v2(), v2(amount='NaN')], scope())
    link=r['csv_evidence'][0]
    assert link['release_time_status']=='site_wall_clock_equal'
    assert link['status']=='duplicate_native_identity'
    assert 'subjects' not in link
    assert r['summary']['v2_duplicate_identity_rows']==2
    assert r['summary']['v2_invalid_amount_rows']==1


def test_missing_csv_subject_and_unknown_v2_subject_never_become_zero():
    a=csv(); del a['product_sales']
    r=build_bridge([a], [v2(), v2(id='2',amountDescription='NewSubject')], scope())
    link=r['csv_evidence'][0]
    assert link['subjects']['product_sales']['csv_minus_v2'] is None
    assert link['subject_projection_complete'] is False


def test_refund_signs_currency_evidence_and_inputs_unchanged():
    import copy
    a=csv(); a.update(type='Refund',currency='',product_sales='-12')
    b=v2(transactionType='Refund',amount='-10')
    original=copy.deepcopy((a,b))
    r=build_bridge([a],[b],scope(),{'bill.csv':{'currency':'USD','kind':'pdf'}})
    assert r['csv_evidence'][0]['subjects']['product_sales']['csv_minus_v2']=='-2'
    assert r['csv_evidence'][0]['currency_source']=='file_currency_evidence'
    assert (a,b)==original


def test_conflicting_file_currency_and_missing_scope_are_retained():
    r=build_bridge([csv()],[v2()],scope(),{'bill.csv':{'currency':'CAD'}})
    assert r['csv_evidence'][0]['status']=='currency_evidence_conflict'
    r=build_bridge([csv()],[v2()],[])
    assert r['csv_evidence'][0]['status']=='shop_scope_unmapped'
