import importlib
from decimal import Decimal


def module():
    return importlib.import_module('sellfox_settlement.monthly_validation')


def test_missing_pdf_component_stays_partial_even_at_zero_difference():
    csv = {'controls':{'fba_fees_net':Decimal('-3')},
           'comparison_groups':{'fba_fees_net':['fba_fees','inventory_inbound_fees']}}
    pdf = {'controls':{'fba_fees':Decimal('-3')}}
    result = module().compare_controls(csv, pdf)
    assert result[0]['status'] == 'partial'
    assert result[0]['missing_components'] == ['inventory_inbound_fees']


def test_refund_other_bridge_is_explanatory_and_keeps_original_controls():
    csv = {'controls':{'refunds_non_fba':Decimal('-20')},
           'unallocated':[{'reason':'refund_other_combines_components','amount':Decimal('5')}]}
    pdf = {'controls':{'refunds_non_fba':Decimal('-15')}}
    bridge = module().refund_other_bridge(csv, pdf)
    assert bridge['residual'] == '0'
    assert csv['controls']['refunds_non_fba'] == Decimal('-20')


def test_candidate_groups_do_not_mix_currency_or_status():
    rows = [{'source_file':'synthetic','currency':'USD','transaction_status':'Released','type':'Order','product_sales':'10'},
            {'source_file':'synthetic','currency':'USD','transaction_status':'Deferred','type':'Order','product_sales':'20'},
            {'source_file':'other','currency':'EUR','transaction_status':'Released','type':'Order','product_sales':'30'}]
    result = module().candidate_groups(rows, {})
    assert len(result) == 3
    assert sorted(r['income_candidate_a'] for r in result) == ['10','20','30']


def test_currency_mapping_fills_only_missing_currency():
    rows = [{'source_file':'synthetic','currency':'','transaction_status':'Released',
             'type':'Order','product_sales':'10'},
            {'source_file':'synthetic','currency':'USD','transaction_status':'Released',
             'type':'Order','product_sales':'20'}]
    groups = module().candidate_groups(rows, {'synthetic':{'currency':'EUR'}})
    assert {g['currency'] for g in groups} == {'USD','EUR'}


def test_ordinary_difference_is_preserved():
    csv = {'controls':{'refunds_non_fba':Decimal('-20')}}
    pdf = {'controls':{'refunds_non_fba':Decimal('-15')}}
    result = module().compare_controls(csv, pdf)
    assert result[0]['status'] == 'difference'
    assert result[0]['difference'] == '-5'
    assert csv['controls']['refunds_non_fba'] == Decimal('-20')


def test_manifest_hashes_only_original_report_sources(tmp_path):
    (tmp_path / 'synthetic.csv').write_text('synthetic source', encoding='utf8')
    (tmp_path / 'synthetic.pdf').write_bytes(b'synthetic source, not a real PDF')
    (tmp_path / 'ignored.txt').write_text('not an input', encoding='utf8')
    before = module().source_manifest(tmp_path)
    assert before['counts'] == {'csv':1,'pdf':1}
    assert before['total_files'] == 2
    (tmp_path / 'synthetic.csv').write_text('changed source', encoding='utf8')
    assert module().source_manifest(tmp_path) != before


def test_pdf_window_uses_report_timezone_instead_of_csv_calendar_date():
    rows = [{'source_file':'synthetic','source_line':1,'date_time':'2026-08-31T23:10:00+00:00'}]
    issues = module().pdf_window_checks(rows, {'timezone':'GMT+2',
        'period_start':'2026-08-01','period_end':'2026-08-31'})
    assert issues[0]['converted_date'] == '2026-09-01'
    assert issues[0]['reason'] == 'csv_timestamp_outside_pdf_timezone_window'
