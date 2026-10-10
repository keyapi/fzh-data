"""Read-only Amazon date-range CSV validation; no tax policy is selected."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
from collections import Counter, defaultdict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from sellfox_settlement.validation_paths import private_output

HEADER_ALIASES = json.loads(Path(__file__).with_name('non_v2_header_aliases.json').read_text(encoding='utf-8'))
HEADER_PROFILES = json.loads(Path(__file__).with_name('non_v2_header_profiles.json').read_text(encoding='utf-8'))
MONEY_FIELDS = {
    'product_sales', 'shipping_credits', 'gift_wrap_credits', 'regulatory_fee',
    'promotional_rebates', 'product_sales_tax', 'shipping_credits_tax',
    'giftwrap_credits_tax', 'tax_on_regulatory_fee', 'promotional_rebates_tax',
    'collected_sales_tax', 'marketplace_withheld_tax', 'selling_fees',
    'fba_fees', 'other_transaction_fees', 'other', 'total',
}
REQUIRED = {'date_time', 'type', 'order_id', 'sku', 'quantity', 'product_sales',
            'shipping_credits', 'gift_wrap_credits', 'promotional_rebates',
            'selling_fees', 'fba_fees', 'other_transaction_fees', 'other',
            'total', 'transaction_status', 'fulfillment', 'marketplace',
            'product_sales_tax', 'shipping_credits_tax', 'giftwrap_credits_tax',
            'promotional_rebates_tax', 'marketplace_withheld_tax'}
GRANULAR_TAX_FIELDS = {'product_sales_tax', 'shipping_credits_tax', 'giftwrap_credits_tax', 'promotional_rebates_tax'}


def norm(value):
    return ' '.join(value.strip().casefold().replace('’', "'").split())


def vocabulary(groups):
    return {norm(alias): key for key, aliases in groups.items() for alias in aliases}


TYPES = vocabulary({
    'Order': ['Order', 'Bestellung', 'Ordine', 'Commande', 'Bestelling', 'Pedido'],
    'Refund': ['Refund', 'Erstattung', 'Rimborso', 'Remboursement', 'Reembolso'],
    'Transfer': ['Transfer', 'Übertrag', 'Trasferimento', 'Transfert', 'Transférer', 'Overboeking', 'Transferir', 'Överföring'],
    'Service Fee': ['Service Fee', 'Servicegebühr', 'Commissione di servizio', 'Frais de service', 'Tarifa de prestación de servicio', 'Tarifa de servicio'],
    'Amazon Fees': ['Amazon Fees', 'Gebühren von Amazon', 'Tariffe e commissioni Amazon', 'Tarifas de Amazon'],
    'FBA Transaction fees': ['FBA Transaction fees', 'Fulfilment by Amazon (FBA) transaction fees', 'Transaktionsgebühren für Versand durch Amazon', 'Commissioni per le transazioni di Logistica di Amazon', 'Frais de transaction Expédié par Amazon', 'Tarifas de transacción de Logística de Amazon'],
    'Shipping Services': ['Shipping Services', 'Versanddienstleistungen', "Services d'expédition"],
    'Adjustment': ['Adjustment', 'Anpassung'],
    'Debt': ['Debt', 'Verbindlichkeit', 'Saldo negativo', 'Solde négatif', 'Saldo descubierto', 'Deuda'],
    'Liquidations': ['Liquidations'],
    'SAFE-T reimbursement': ['SAFE-T reimbursement'],
    'Refund_Retrocharge': ['Refund_Retrocharge'],
    'Chargeback Refund': ['Chargeback Refund'],
})
STATUSES = vocabulary({
    'Released': ['Released', 'Veröffentlicht', 'Emesso', 'Sorti', 'Effectuée', 'Uitgebracht', 'Liberada', 'Släpps', 'Lanzado'],
    'Deferred': ['Deferred', 'Verzögert', 'Differito', 'Différé', 'Différée', 'Diferida', 'Uppskjuten'],
})
FULFILLMENT = vocabulary({'FBA': ['Amazon'], 'FBM': ['Seller', 'Verkäufer', 'Venditore', 'Vendeur', 'Verkoper', 'Vendedor', 'Säljare']})


def parse_money(value, decimal_separator='.'):
    """Reject malformed/ambiguous amounts; distinguish empty from numeric zero."""
    value = value.strip().replace('−', '-').replace('\u00a0', ' ').replace('\u202f', ' ')
    if not value:
        return None
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    group = ',' if decimal_separator == '.' else '.'
    escaped = re.escape(decimal_separator)
    if not re.fullmatch(rf'-?(?:\d+|\d{{1,3}}(?:{re.escape(group)}\d{{3}})+|\d{{1,3}}(?: \d{{3}})+)(?:{escaped}\d+)?', value):
        raise ValueError('invalid localized amount')
    try:
        amount = Decimal(value.replace(group, '').replace(' ', '').replace(decimal_separator, '.'))
    except InvalidOperation as exc:
        raise ValueError('invalid localized amount') from exc
    if not amount.is_finite():
        raise ValueError('non-finite amount')
    return amount


def parse_date(value):
    """Keep the report timezone; never use the workstation timezone."""
    value = value.strip().replace('\u00a0', ' ').replace('a.m.', 'AM').replace('p.m.', 'PM')
    match = re.search(r'\s(UTC|GMT[+-]\d{1,2}|PDT|PST|CET|CEST|BST)$', value)
    if not match:
        raise ValueError('unrecognized date timezone')
    zone = match.group(1)
    offsets = {'UTC': 0, 'PDT': -7, 'PST': -8, 'CET': 1, 'CEST': 2, 'BST': 1}
    offset = int(zone[3:]) if zone.startswith('GMT') else offsets[zone]
    tz = dt.timezone(dt.timedelta(hours=offset))
    value = value[:match.start()].strip()
    value = re.sub(r'\b(?:août|ago|aug)\b\.?', 'Aug', value, flags=re.I)
    value = re.sub(r'\b(?:set|sept|sep)\b\.?', 'Sep', value, flags=re.I)
    for fmt in ('%b %d, %Y %I:%M:%S %p', '%d.%m.%Y %H:%M:%S', '%d %b %Y %H:%M:%S', '%d %b %Y %I:%M:%S %p'):
        try:
            return dt.datetime.strptime(value, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError('unrecognized date format')


def pair_files(root):
    groups = defaultdict(lambda: {'csv': [], 'pdf': []})
    for path in sorted(Path(root).iterdir()):
        if path.is_file() and path.suffix.lower() in {'.csv', '.pdf'}:
            key = re.sub(r'(transaction|summary|交易|汇总)', '', path.stem, flags=re.I)
            groups[re.sub(r'\s+', '', key).casefold()][path.suffix.lower()[1:]].append(str(path))
    return [{'key': key, **paths, 'status': 'paired' if len(paths['csv']) == len(paths['pdf']) == 1 else 'ambiguous_pair'} for key, paths in groups.items()]


def currency_from_metadata(metadata):
    text = ' '.join(' '.join(row) for row in metadata)
    currencies = set(re.findall(r'\b(?:USD|CAD|EUR|GBP|PLN|MXN|SEK)\b', text))
    if 'Alle Beträge in Euro' in text:
        currencies.add('EUR')
    if len(currencies) == 1:
        return next(iter(currencies)), 'csv_metadata'
    return '', 'ambiguous' if currencies else 'missing'


def read_csv(path, month):
    path = Path(path)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        records = list(csv.reader(stream))
    header_index = next((i for i, row in enumerate(records) if 'date_time' in {HEADER_ALIASES.get(norm(c)) for c in row}), None)
    if header_index is None:
        raise ValueError('missing required header')
    header = records[header_index]
    fields = [HEADER_ALIASES.get(norm(c)) for c in header]
    unknown = [c for c, field in zip(header, fields) if field is None]
    required = set(REQUIRED)
    if 'collected_sales_tax' in fields:
        required -= GRANULAR_TAX_FIELDS
        required.add('collected_sales_tax')
        if GRANULAR_TAX_FIELDS & set(fields):
            raise ValueError('combined and granular tax columns coexist')
    if {'regulatory_fee', 'tax_on_regulatory_fee'} & set(fields):
        required |= {'regulatory_fee', 'tax_on_regulatory_fee'}
    missing = sorted(required - set(fields))
    if missing:
        raise ValueError('missing required columns: ' + ', '.join(missing))
    if len(set(fields)) != len(fields):
        raise ValueError('duplicate semantic columns')
    if unknown:
        raise ValueError('unmapped columns: ' + ', '.join(unknown))
    metadata = records[:header_index]
    currency, currency_evidence = currency_from_metadata(metadata)
    separator = '.' if norm(header[fields.index('date_time')]) in {'date/time', 'fecha/hora'} else ','
    # English columns may be reordered. Derive locale from semantic language, not index.
    if 'product sales' in {norm(c) for c in header}:
        separator = '.'
    result = {'source_file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'header': header, 'metadata': metadata, 'currency': currency,
              'currency_evidence': currency_evidence, 'input_rows': 0, 'blank_rows': 0,
              'rows': [], 'rejected_rows': [], 'issues': []}
    for line, values in enumerate(records[header_index + 1:], header_index + 2):
        if not any(v.strip() for v in values):
            result['blank_rows'] += 1
            continue
        result['input_rows'] += 1
        raw = dict(zip(fields, values)) if len(values) == len(fields) else {}
        reasons = []
        row = {'source_file': path.name, 'source_line': line, 'raw': raw, 'currency': currency}
        if not raw:
            reasons.append('column_count_mismatch')
        else:
            row.update(raw)
            row['date_time_raw'] = raw['date_time']
            try:
                timestamp = parse_date(raw['date_time'])
                row['date_time'] = timestamp.isoformat()
                if timestamp.strftime('%Y-%m') != month:
                    reasons.append('outside_transaction_month')
            except ValueError:
                reasons.append('unparsed_date_time')
            for field in MONEY_FIELDS & set(fields):
                try:
                    amount = parse_money(raw[field], separator)
                    row[field] = str(amount) if amount is not None else None
                    if amount is None:
                        reasons.append('missing_amount:' + field)
                except ValueError:
                    reasons.append('invalid_amount:' + field)
            for field, aliases in [('type', TYPES), ('transaction_status', STATUSES), ('fulfillment', FULFILLMENT)]:
                if not raw[field].strip() and field == 'fulfillment':
                    row[field] = ''
                elif norm(raw[field]) in aliases:
                    row[field] = aliases[norm(raw[field])]
                else:
                    row[field] = raw[field]
                    reasons.append('unmapped_' + field)
            if raw.get('transaction_release_date', '').strip():
                row['transaction_release_date_raw'] = raw['transaction_release_date']
                try:
                    row['transaction_release_date'] = parse_date(raw['transaction_release_date']).isoformat()
                except ValueError:
                    reasons.append('unparsed_release_date')
                if row['transaction_status'] == 'Deferred':
                    reasons.append('deferred_with_release_date')
            elif row['transaction_status'] == 'Released' and 'transaction_release_date' in fields:
                reasons.append('released_without_release_date')
            try:
                quantity = Decimal(raw['quantity']) if raw['quantity'].strip() else None
                if quantity is not None and (not quantity.is_finite() or quantity != quantity.to_integral_value()):
                    raise ValueError('noninteger quantity')
                row['quantity'] = str(quantity) if quantity is not None else None
            except (InvalidOperation, ValueError):
                reasons.append('invalid_quantity')
            if not any(reason.startswith(('invalid_amount', 'missing_amount')) for reason in reasons):
                components = sum((Decimal(row[c]) for c in MONEY_FIELDS & set(fields) if c != 'total'), Decimal(0))
                row['row_total_difference'] = str(components - Decimal(row['total']))
        row['issues'] = reasons
        if any(reason.startswith(('column_count', 'unparsed_date', 'invalid_amount', 'missing_amount', 'invalid_quantity')) for reason in reasons):
            result['rejected_rows'].append({'source_file': path.name, 'source_line': line, 'raw_values': values, 'issues': reasons})
        else:
            result['rows'].append(row)
        result['issues'].extend({'source_line': line, 'reason': reason} for reason in reasons)
    assert result['input_rows'] == len(result['rows']) + len(result['rejected_rows'])
    return result


def money(row, key):
    return Decimal(row[key]) if row.get(key) is not None and row.get(key) != '' else Decimal(0)


def candidate_totals(rows, rules=None):
    """Emit every configured candidate. A pending config cannot select one."""
    from sellfox_settlement.finance_rules import load_finance_rules, selected_income_candidate
    rules = rules or load_finance_rules()
    income = set(rules['income_types'])
    refunds = set(rules['refund_types'])
    totals = {}
    for label, spec in rules['income_candidates'].items():
        fields = spec['fields']
        sales = sum((sum((money(row, key) for key in fields), Decimal(0)) for row in rows if row.get('type') in income), Decimal(0))
        returned = sum((sum((money(row, key) for key in fields), Decimal(0)) for row in rows if row.get('type') in refunds), Decimal(0))
        key = label.lower()
        totals['income_candidate_' + key] = str(sales)
        totals['refund_candidate_' + key + '_signed'] = str(returned)
        totals['net_candidate_' + key] = str(sales + returned)
    # Promotion tax stays a diagnostic until finance chooses whether B includes it.
    tax_field = rules['diagnostic_tax_field']
    promo_tax = sum((money(row, tax_field) for row in rows if row.get('type') in income | refunds), Decimal(0))
    totals['promotional_tax_signed'] = str(promo_tax)
    totals['net_b_all_tax_diagnostic'] = str(Decimal(totals['net_candidate_b']) + promo_tax)
    totals['selected_income_candidate'] = selected_income_candidate(rules) or 'unconfirmed'
    return totals


def validate_header_profile(header, currency):
    columns = sorted(norm(column) for column in header)
    if not any(p['columns'] == columns and currency in p['csv_currencies'] for p in HEADER_PROFILES):
        raise ValueError('unverified complete header/currency profile')


def validation_failed(result):
    summary = result['summary']
    return bool(result['file_errors'] or result['rejected_rows'] or
                summary['issue_counts'] or summary['row_total_nonzero'] or
                any(pair['status'] != 'paired' for pair in result['pairs']))


def validate_directory(root, month):
    root = Path(root)
    results = []
    file_errors = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.lower() == '.csv':
            try:
                parsed = read_csv(path, month)
                validate_header_profile(parsed['header'], parsed['currency'])
                results.append(parsed)
            except (ValueError, UnicodeError, csv.Error) as exc:
                file_errors.append({'source_file': path.name, 'reason': str(exc)})
    rows = [row for result in results for row in result['rows']]
    rejected = [row for result in results for row in result['rejected_rows']]
    pairs = pair_files(root)
    summary = {'month': month, 'csv_files': len(results) + len(file_errors), 'csv_success': len(results),
               'csv_failed': len(file_errors), 'input_rows': sum(r['input_rows'] for r in results),
               'normalized_rows': len(rows), 'rejected_rows': len(rejected),
               'header_families': len({tuple(r['header']) for r in results}),
               'zero_row_csv': sum(r['input_rows'] == 0 for r in results),
               'single_row_csv': sum(r['input_rows'] == 1 for r in results),
               'pair_groups': len(pairs), 'paired': sum(p['status'] == 'paired' for p in pairs),
               'row_total_nonzero': sum(Decimal(r.get('row_total_difference', '0')) != 0 for r in rows),
               'issue_counts': dict(Counter(i['reason'] for f in results for i in f['issues'])),
               'type_counts': dict(Counter(r['type'] for r in rows)),
               'status_counts': dict(Counter(r['transaction_status'] for r in rows)),
               'fulfillment_counts': dict(Counter(r['fulfillment'] for r in rows)),
               'currency_missing_files': sum(not r['currency'] for r in results)}
    return {'summary': summary, 'files': results, 'file_errors': file_errors, 'pairs': pairs,
            'rows': rows, 'rejected_rows': rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--month', required=True)
    parser.add_argument('--out', type=Path, required=True, help='Private output directory, outside Git')
    args = parser.parse_args()
    dt.datetime.strptime(args.month, '%Y-%m')
    try:
        output = private_output(args.out, input_root=args.input)
    except ValueError as exc:
        parser.error(str(exc))
    result = validate_directory(args.input, args.month)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'csv_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'normalized_transactions.json').write_text(json.dumps(result['rows'], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
    return int(validation_failed(result))


if __name__ == '__main__':
    raise SystemExit(main())
