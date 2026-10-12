import csv
from decimal import Decimal
import importlib

import pytest


def module():
    return importlib.import_module('sellfox_settlement.non_v2_validation')


@pytest.mark.parametrize('value,separator,expected', [
    ('1,234.56', '.', '1234.56'), ('1.234,56', ',', '1234.56'),
    ('−456,58', ',', '-456.58'), ('(1 234,56)', ',', '-1234.56'),
    ('', '.', None), ('0', '.', '0'),
])
def test_money_is_exact_and_keeps_missing_distinct(value, separator, expected):
    result = module().parse_money(value, separator)
    assert result == (Decimal(expected) if expected is not None else None)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '12oops', '1,23,4.00'])
def test_bad_money_is_rejected(value):
    with pytest.raises(ValueError):
        module().parse_money(value, '.')


@pytest.mark.parametrize('raw,expected', [
    ('Aug 1, 2026 6:00:11 AM PDT', '2026-08-01T06:00:11-07:00'),
    ('02.08.2026 10:47:23 UTC', '2026-08-02T10:47:23+00:00'),
    ('2 août 2026 10:07:08 UTC', '2026-08-02T10:07:08+00:00'),
    ('4 aug. 2026 05:14:59 UTC', '2026-08-04T05:14:59+00:00'),
    ('1 ago 2026 11:39:54 p.m. GMT-7', '2026-08-01T23:39:54-07:00'),
    ('2 set 2026 08:17:18 UTC', '2026-09-02T08:17:18+00:00'),
    ('1 sept. 2026 20:51:51 UTC', '2026-09-01T20:51:51+00:00'),
])
def test_dates_keep_report_timezone(raw, expected):
    assert module().parse_date(raw).isoformat() == expected


def test_unknown_timezone_does_not_become_utc():
    with pytest.raises(ValueError):
        module().parse_date('Aug 1, 2026 6:00:11 AM MYSTERY')


def test_transaction_summary_pairing_detects_duplicates(tmp_path):
    for name in ['Example交易.csv', 'Example汇总.pdf', 'ExampleSummary.pdf']:
        (tmp_path / name).touch()
    pairs = module().pair_files(tmp_path)
    assert len(pairs) == 1
    assert pairs[0]['status'] == 'ambiguous_pair'


def test_reordered_columns_use_semantic_aliases_and_preserve_bad_rows(tmp_path):
    path = tmp_path / 'synthetic.csv'
    headers = ['total', 'sku', 'order id', 'type', 'date/time', 'quantity',
               'product sales', 'shipping credits', 'gift wrap credits',
               'promotional rebates', 'selling fees', 'fba fees',
               'other transaction fees', 'other', 'Transaction Status',
               'fulfillment', 'marketplace', 'product sales tax',
               'shipping credits tax', 'giftwrap credits tax',
               'promotional rebates tax', 'marketplace withheld tax']
    with path.open('w', encoding='utf-8', newline='') as f:
        f.write('All amounts in USD, unless specified\n')
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerow(['10', 'SYNTHETIC', 'SYNTHETIC-ORDER', 'Order',
                         'Aug 1, 2026 6:00:11 AM PDT', '1', '12', '0', '0',
                         '0', '-2', '0', '0', '0', 'Released', 'Seller', 'amazon.com',
                         '0', '0', '0', '0', '0'])
        writer.writerow(['broken'])
    result = module().read_csv(path, '2026-08')
    assert result['input_rows'] == 2
    assert len(result['rows']) == 1
    assert len(result['rejected_rows']) == 1
    assert result['rows'][0]['product_sales'] == '12'
    assert result['rows'][0]['fulfillment'] == 'FBM'
    assert result['rows'][0]['currency'] == 'USD'
    assert result['rows'][0]['row_total_difference'] == '0'


def test_missing_required_column_blocks_file(tmp_path):
    path = tmp_path / 'missing.csv'
    path.write_text('date/time,type,total\n', encoding='utf-8')
    with pytest.raises(ValueError, match='missing required'):
        module().read_csv(path, '2026-08')


def test_candidates_only_use_sale_and_refund_rows():
    rows = [
        {'type':'Order', 'product_sales':'100', 'shipping_credits':'5', 'promotional_rebates':'-2', 'product_sales_tax':'10'},
        {'type':'Refund', 'product_sales':'-20', 'shipping_credits':'-1', 'promotional_rebates':'1', 'product_sales_tax':'-2'},
        {'type':'Transfer', 'other':'-50'},
    ]
    values = module().candidate_totals(rows)
    assert values['income_candidate_a'] == '103'
    assert values['refund_candidate_a_signed'] == '-20'
    assert values['net_candidate_a'] == '83'
    assert values['income_candidate_b'] == '113'
    assert values['net_candidate_b'] == '91'


def test_foreign_locale_columns_can_be_reordered(tmp_path):
    path = tmp_path / 'localized.csv'
    aliases = module().HEADER_ALIASES
    fields = sorted(module().REQUIRED)
    headers = [next(k for k, v in aliases.items() if v == field) for field in fields]
    # Explicit German aliases must decide decimal locale even with total first.
    headers[fields.index('product_sales')] = 'umsätze'
    headers[fields.index('date_time')] = 'datum/uhrzeit'
    values = {key: '0' for key in fields}
    values.update(date_time='02.08.2026 10:47:23 UTC', type='Bestellung',
                  transaction_status='Veröffentlicht', fulfillment='Verkäufer',
                  quantity='1', sku='SYNTHETIC', order_id='SYNTHETIC-ORDER',
                  marketplace='amazon.de', product_sales='1,25', total='1,25')
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerow([values[field] for field in fields])
    result = module().read_csv(path, '2026-08')
    assert result['rows'][0]['product_sales'] == '1.25'


def test_synthetic_invalid_status_is_preserved_as_issue(tmp_path):
    path = tmp_path / 'unknown.csv'
    fields = sorted(module().REQUIRED)
    inverse = {v: k for k, v in module().HEADER_ALIASES.items()}
    values = {key:'0' for key in fields}
    values.update(date_time='Aug 1, 2026 6:00:11 AM PDT', type='Order',
                  transaction_status='Mystery', fulfillment='', marketplace='amazon.com')
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([field if field in module().HEADER_ALIASES else inverse[field] for field in fields])
        writer.writerow([values[field] for field in fields])
    result = module().read_csv(path, '2026-08')
    assert result['rows'][0]['transaction_status'] == 'Mystery'
    assert 'unmapped_transaction_status' in result['rows'][0]['issues']


def test_missing_tax_column_is_not_silently_zero(tmp_path):
    path = tmp_path / 'taxmissing.csv'
    fields = sorted(module().REQUIRED - {'product_sales_tax'})
    inverse = {v:k for k,v in module().HEADER_ALIASES.items()}
    with path.open('w', encoding='utf-8', newline='') as f:
        csv.writer(f).writerow([field if field in module().HEADER_ALIASES else inverse[field] for field in fields])
    with pytest.raises(ValueError, match='missing required'):
        module().read_csv(path, '2026-08')


def test_removed_regulatory_pair_is_not_a_valid_complete_profile():
    profile = next(p for p in module().HEADER_PROFILES if 'USD' in p['csv_currencies'])
    original = profile['columns']
    module().validate_header_profile(original, 'USD')
    shortened = [c for c in original if module().HEADER_ALIASES[c] not in {'regulatory_fee', 'tax_on_regulatory_fee'}]
    with pytest.raises(ValueError, match='unverified complete'):
        module().validate_header_profile(shortened, 'USD')


def test_promotion_tax_diagnostic_does_not_change_pr284_candidate_b():
    result = module().candidate_totals([{'type':'Order', 'product_sales':'100',
                                       'promotional_rebates':'-10', 'product_sales_tax':'10',
                                       'promotional_rebates_tax':'-1'}])
    assert result['income_candidate_b'] == '100'
    assert result['promotional_tax_signed'] == '-1'
    assert result['net_b_all_tax_diagnostic'] == '99'


@pytest.mark.parametrize('reason', ['unmapped_type', 'outside_transaction_month', 'unparsed_release_date'])
def test_semantic_issues_fail_technical_gate(reason):
    result = {'summary':{'issue_counts':{reason:1}, 'row_total_nonzero':0},
              'file_errors':[], 'rejected_rows':[], 'pairs':[{'status':'paired'}]}
    assert module().validation_failed(result)
