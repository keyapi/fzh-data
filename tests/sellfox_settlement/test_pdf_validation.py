from decimal import Decimal

import pytest

from sellfox_settlement.pdf_validation import csv_controls, parse_amount, parse_spans


def span(text, x, y, width=120):
    return {'text': text, 'bbox': (x, y, x + width, y + 10)}


@pytest.mark.parametrize(('text', 'expected'), [('1,234.56', '1234.56'),
    ('-1.234,56', '-1234.56'), ('1\u00a0234,56', '1234.56'), ('0', '0'),
    ('−665,21', '-665.21')])
def test_localized_money(text, expected):
    assert parse_amount(text) == Decimal(expected)


def test_coordinates_separate_columns_and_ignore_content_stream_order():
    spans = [span('Product sales (non-FBA)', 24, 218), span('123.45', 360, 218, 30),
             span('Seller fulfilled selling fees', 407, 217), span('-22.34', 678, 217, 30)]
    result = parse_spans(list(reversed(spans)), 792, 612)
    assert result['controls']['product_sales_non_fba'] == Decimal('123.45')
    assert result['controls']['selling_fees_non_fba'] == Decimal('-22.34')
    assert result['control_evidence']['product_sales_non_fba'][0]['label_bbox'][0] == 24


def test_ambiguous_adjacent_rows_are_reported_not_guessed():
    spans = [span('Product sales (non-FBA)', 24, 218), span('123.45', 360, 220, 30),
             span('FBA product sales', 24, 222)]
    result = parse_spans(spans, 792, 612)
    assert 'product_sales_non_fba' not in result['controls']
    assert any(issue['reason'] == 'ambiguous_amount_row' for issue in result['issues'])


def test_currency_kr_remains_inferred_and_truncated_end_time_is_retained():
    result = parse_spans([
        span('Alla belopp i kr, om inte annat anges', 610, 64),
        span('Kontoaktivitet Aug 1, 2026 00:00 GMT+2 till Aug 31, 2026 23', 20, 62, 380),
    ], 792, 612)
    assert result['currency'] == 'SEK'
    assert result['currency_evidence']['kind'] == 'inferred'
    assert result['period_start'] == '2026-08-01'
    assert result['period_end'] == '2026-08-31'
    assert result['period_end_time'] is None


def test_unknown_labels_and_duplicate_controls_remain_visible():
    result = parse_spans([span('New undefined fee', 407, 218), span('-8.00', 678, 218, 30),
        span('Product sales (non-FBA)', 24, 218), span('10.00', 360, 218, 30),
        span('Product sales (non-FBA)', 24, 230), span('20.00', 360, 230, 30)], 792, 612)
    assert 'product_sales_non_fba' not in result['controls']
    assert any(issue['reason'] == 'unknown_label' for issue in result['issues'])
    assert any(issue['reason'] == 'duplicate_control' for issue in result['issues'])


def test_one_row_can_have_debits_and_credits_and_aliases_are_case_insensitive():
    result = parse_spans([span('A-to-z Guarantee CLAIMS', 24, 218),
        span('-10.00', 295, 218, 30), span('2.00', 370, 218, 20)], 792, 612)
    assert result['controls']['guarantee_claims'] == Decimal('-8.00')
    assert len(result['control_evidence']['guarantee_claims'][0]['amounts']) == 2


@pytest.mark.parametrize('value', ['1,23,4.56', '1,234', '1.234', '$2.00', 'NaN'])
def test_ambiguous_or_corrupt_amount_is_rejected(value):
    with pytest.raises(ValueError):
        parse_amount(value)


def test_explicit_currency_and_blank_fee_do_not_fill_zero():
    result = parse_spans([span('All amounts in CAD, unless specified', 610, 64),
        span('FBA inventory and inbound services fees', 407, 300)], 792, 612)
    assert result['currency_evidence']['kind'] == 'direct'
    assert 'inventory_inbound_fees' not in result['controls']
    assert any(i['reason'] == 'missing_amount_row' for i in result['issues'])


def test_bare_kr_does_not_disambiguate_scandinavian_currencies():
    result = parse_spans([span('All amounts in kr', 610, 64)], 792, 612)
    assert result['currency'] is None
    assert result['currency_evidence']['kind'] == 'unknown'


def transaction(**values):
    row = dict.fromkeys(['product_sales', 'shipping_credits', 'gift_wrap_credits',
        'promotional_rebates', 'selling_fees', 'fba_fees', 'other_transaction_fees',
        'other', 'total'], '0')
    row.update(type='Order', fulfillment='FBM', source_line=1, description='synthetic')
    row.update(values)
    return row


def test_csv_controls_keep_other_refund_bucket_unallocated():
    result = csv_controls([transaction(type='Refund', product_sales='-100', other='20', total='-80')])
    assert result['controls']['refunds_non_fba'] == Decimal('-100')
    assert result['unallocated'][0]['amount'] == Decimal('20')
    assert result['controls']['totals'] == Decimal('-80')


def test_csv_controls_preserve_deferred_and_split_advertising():
    result = csv_controls([transaction(product_sales='100', total='100', transaction_status='Deferred'),
        transaction(type='Service Fee', description='Cost of Advertising', total='-10')])
    assert result['controls']['product_sales_non_fba'] == Decimal('100')
    assert result['controls']['advertising'] == Decimal('-10')
    assert result['input_rows'] == 2


def test_csv_controls_mixed_currency_and_missing_required_column_fail():
    with pytest.raises(ValueError, match='currency'):
        csv_controls([transaction(currency='USD'), transaction(currency='EUR')])
    bad = transaction()
    del bad['total']
    with pytest.raises(ValueError, match='total'):
        csv_controls([bad])


def test_csv_collected_tax_template_and_fee_net_types_are_separate():
    result = csv_controls([transaction(product_sales='100', collected_sales_tax='20',
        marketplace_withheld_tax='-20', selling_fees='-10', total='90'),
        transaction(type='Service Fee', description='Subscription', selling_fees='-2', total='-2'),
        transaction(type='Chargeback Refund', product_sales='-50', selling_fees='5', total='-45')])
    assert result['controls']['tax_collected'] == Decimal('20')
    assert result['controls']['tax'] == 0
    assert result['controls']['selling_fees_net'] == Decimal('-10')
    assert result['controls']['service_fees'] == Decimal('-2')
    assert result['controls']['chargebacks'] == Decimal('-45')
