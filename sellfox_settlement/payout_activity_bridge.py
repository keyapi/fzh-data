"""Offline evidence links between activity CSV rows and payout V2 fee events.

Neither a tax policy nor a transaction-identity claim: distinct settlement and
activity windows remain distinct. Unknown subjects and every input stay visible.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from sellfox_settlement.cost_validation import normalize_sku
from sellfox_settlement.validation_paths import private_output

ORDER_TYPES = {'Order', 'Refund', 'Refund_Retrocharge', 'Chargeback Refund'}
SUBJECTS = {
    ('ItemPrice', 'Principal'): 'product_sales',
    ('ItemPrice', 'Tax'): 'product_sales_tax',
    ('ItemPrice', 'Shipping'): 'shipping_credits',
    ('ItemPrice', 'ShippingTax'): 'shipping_credits_tax',
    ('ItemPrice', 'GiftWrap'): 'gift_wrap_credits',
    ('ItemPrice', 'GiftWrapTax'): 'giftwrap_credits_tax',
    ('Promotion', 'Principal'): 'promotional_rebates',
    ('Promotion', 'Shipping'): 'promotional_rebates',
    ('Promotion', 'TaxDiscount'): 'promotional_rebates_tax',
    ('ItemFees', 'Commission'): 'selling_fees',
    ('ItemFees', 'RefundCommission'): 'selling_fees',
    ('ItemFees', 'FBAPerUnitFulfillmentFee'): 'fba_fees',
}
for _name in ['MarketplaceFacilitatorTax-Principal', 'MarketplaceFacilitatorTax-Shipping',
              'MarketplaceFacilitatorVAT-Principal', 'MarketplaceFacilitatorVAT-Shipping']:
    SUBJECTS[('ItemWithheldTax', _name)] = 'marketplace_withheld_tax'


def basename(value):
    return Path(str(value).replace('\\', '/')).name


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def compare_time(value, site_value):
    activity, site = timestamp(value), timestamp(site_value)
    if activity is None:
        status = 'unparsed_activity_time'
    elif site is None:
        status = 'unparsed_site_time'
    elif site.tzinfo is not None:
        status = 'unexpected_aware_site_time'
    elif activity.tzinfo is None:
        status = 'activity_offset_missing'
    elif activity.replace(tzinfo=None) == site:
        status = 'site_wall_clock_equal'
    else:
        status = 'site_wall_clock_different'
    return status


def time_evidence(row, event):
    return {'time_status': compare_time(row.get('date_time'), event['site_time']),
            'release_time_status': compare_time(row.get('transaction_release_date'), event['site_time']),
            'activity_date': row.get('date_time'),
            'release_date': row.get('transaction_release_date'),
            'transaction_status': row.get('transaction_status'),
            'site_time': event['site_time'], 'posted_time': event['posted_time']}


def amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def build_bridge(transactions, native_rows, scopes, currency_map=None):
    """Keep a CSV detail and a V2 detail for each original row, without dedup."""
    currency_map = currency_map or {}
    by_file = {}
    for scope in scopes:
        name = basename(scope['file'])
        if name in by_file:
            raise ValueError('duplicate scope filename')
        by_file[name] = scope
    events, event_lookup, by_key = [], {}, defaultdict(list)
    identities = defaultdict(list)
    for i, row in enumerate(native_rows):
        if row.get('id') is not None:
            identities[(str(row.get('sellerId')), str(row.get('marketplaceId')), str(row['id']))].append(i)
    duplicates = [indices for indices in identities.values() if len(indices) > 1]
    duplicate_indices = {i for indices in duplicates for i in indices}
    v2_details = []
    for index, row in enumerate(native_rows):
        key = tuple(str(row.get(k) or '') for k in ['sellerId', 'marketplaceId', 'orderId']) + (
            normalize_sku(row.get('msku')), str(row.get('transactionType') or ''), str(row.get('currency') or ''))
        status = ('non_order_transaction' if key[4] not in ORDER_TYPES else
                  next(('missing_' + label for label, value in zip(
                      ['seller_id', 'marketplace_id', 'order_id', 'sku', 'type', 'currency'], key) if not value), None))
        detail = {'index': index, 'id': row.get('id'), 'currency': row.get('currency'),
                  'seller_id': row.get('sellerId'), 'marketplace_id': row.get('marketplaceId'),
                  'order_id': row.get('orderId'), 'sku': row.get('msku'),
                  'settlement_id': row.get('settlementId'), 'report_type': row.get('reportType'),
                  'transaction_type': row.get('transactionType'), 'status': status,
                  'amount_type': row.get('amountType'), 'amount_description': row.get('amountDescription'),
                  'amount': row.get('amount'), 'site_time': row.get('siteTimeStr'),
                  'posted_time': row.get('postedDateTimeStr'), 'candidate_csv_indices': [],
                  'time_status': 'not_compared_without_unique_event'}
        if status is None:
            event_key = key + tuple(str(row.get(k) or '') for k in
                                   ['settlementId', 'siteTimeStr', 'postedDateTimeStr', 'reportType'])
            if event_key not in event_lookup:
                event_id = len(events)
                event_lookup[event_key] = event_id
                events.append({'index': event_id, 'key': list(key), 'settlement_id': row.get('settlementId'),
                               'site_time': row.get('siteTimeStr'), 'posted_time': row.get('postedDateTimeStr'),
                               'report_type': row.get('reportType'), 'row_indices': [],
                               'unknown_subject_rows': [], 'invalid_amount_rows': [], 'duplicate_identity_rows': [],
                               'subject_sums': {}, 'candidate_csv_indices': []})
                by_key[key].append(event_id)
            event = events[event_lookup[event_key]]
            detail['event_index'] = event['index']
            event['row_indices'].append(index)
            if index in duplicate_indices:
                event['duplicate_identity_rows'].append(index)
            subject = SUBJECTS.get((row.get('amountType'), row.get('amountDescription')))
            value = amount(row.get('amount'))
            if subject is None:
                event['unknown_subject_rows'].append(index)
            if value is None:
                event['invalid_amount_rows'].append(index)
            elif subject:
                event['subject_sums'][subject] = event['subject_sums'].get(subject, Decimal(0)) + value
        v2_details.append(detail)
    csv_details = []
    for index, row in enumerate(transactions):
        scope = by_file.get(basename(row.get('source_file')))
        currency = str(row.get('currency') or '')
        evidence = 'csv'
        entry = currency_map.get(basename(row.get('source_file')), {})
        mapped_currency = entry.get('currency') if isinstance(entry, dict) else entry
        conflict = bool(currency and mapped_currency and currency != mapped_currency)
        if not currency and mapped_currency:
            currency, evidence = mapped_currency, 'file_currency_evidence'
        record = {'index': index, 'source_file': row.get('source_file'), 'source_line': row.get('source_line'),
                  'account': scope.get('account') if scope else None, 'currency': currency,
                  'currency_source': evidence, 'transaction_type': row.get('type'),
                  'order_id': row.get('order_id'), 'sku': row.get('sku'),
                  'seller_id': scope.get('sellerId') if scope else None,
                  'marketplace_id': scope.get('marketplaceId') if scope else None,
                  'csv_total': row.get('total'),
                  'activity_date': row.get('date_time'), 'release_date': row.get('transaction_release_date'),
                  'transaction_status': row.get('transaction_status'), 'candidate_event_indices': [],
                  'time_status': 'not_compared_without_unique_event'}
        if row.get('type') not in ORDER_TYPES:
            status = 'non_order_transaction'
        elif conflict:
            status = 'currency_evidence_conflict'
        elif not scope:
            status = 'shop_scope_unmapped'
        else:
            key = (str(scope.get('sellerId') or ''), str(scope.get('marketplaceId') or ''),
                   str(row.get('order_id') or ''), normalize_sku(row.get('sku')), row.get('type'), currency)
            status = next(('missing_' + label for label, value in zip(
                ['seller_id', 'marketplace_id', 'order_id', 'sku', 'type', 'currency'], key) if not value), None)
            if status is None:
                candidates = by_key.get(key, [])
                record['candidate_event_indices'] = list(candidates)
                status = 'key_unmatched' if not candidates else 'pending'
                for event_id in candidates:
                    events[event_id]['candidate_csv_indices'].append(index)
        record['status'] = status
        csv_details.append(record)
    for record, row in zip(csv_details, transactions):
        if record['status'] != 'pending':
            continue
        candidates = record['candidate_event_indices']
        record['candidate_time_evidence'] = [dict(event_index=i, **time_evidence(row, events[i])) for i in candidates]
        if len(candidates) > 1:
            record['status'] = 'multiple_event_candidates'
        elif len(events[candidates[0]]['candidate_csv_indices']) > 1:
            record['status'] = 'multiple_csv_candidates'
        else:
            event = events[candidates[0]]
            record.update(time_evidence(row, event))
            if event['duplicate_identity_rows']:
                record['status'] = 'duplicate_native_identity'
                continue
            record['status'] = 'unique_event_evidence'
            record['subject_projection_complete'] = not (event['unknown_subject_rows'] or event['invalid_amount_rows'])
            record['subjects'] = {}
            for subject, total in event['subject_sums'].items():
                csv_amount = amount(row.get(subject))
                record['subjects'][subject] = {'csv': row.get(subject), 'v2': str(total),
                    'csv_minus_v2': str(csv_amount - total) if csv_amount is not None and not event['invalid_amount_rows'] else None,
                    'status': 'incomplete_v2_amounts' if event['invalid_amount_rows'] else 'invalid_csv_amount' if csv_amount is None else 'observed_difference' if csv_amount != total else 'equal'}
    for detail in v2_details:
        if detail['status'] is not None:
            continue
        event = events[detail['event_index']]
        candidates = event['candidate_csv_indices']
        detail['candidate_csv_indices'] = candidates
        if not candidates:
            detail['status'] = 'key_unmatched'
        elif len(candidates) > 1:
            detail['status'] = 'multiple_csv_candidates'
        else:
            detail['status'] = csv_details[candidates[0]]['status']
            if detail['status'] == 'unique_event_evidence':
                detail['time_status'] = csv_details[candidates[0]]['time_status']
                detail['release_time_status'] = csv_details[candidates[0]]['release_time_status']
    for event in events:
        event['subject_sums'] = {k: str(v) for k, v in event['subject_sums'].items()}
    def counts(rows, field):
        return dict(Counter(str(row.get(field) or 'missing') for row in rows))
    summary = {'csv_rows': len(transactions), 'v2_rows': len(native_rows), 'v2_events': len(events),
               'csv_status_counts': counts(csv_details, 'status'), 'v2_status_counts': counts(v2_details, 'status'),
               'csv_currency_counts': counts(csv_details, 'currency'), 'v2_currency_counts': counts(v2_details, 'currency'),
               'unique_time_counts': counts([r for r in csv_details if r['status']=='unique_event_evidence'], 'time_status'),
               'unique_release_time_counts': counts([r for r in csv_details if r['status']=='unique_event_evidence'], 'release_time_status'),
               'v2_unknown_subject_rows': sum(len(e['unknown_subject_rows']) for e in events),
               'v2_invalid_amount_rows': sum(len(e['invalid_amount_rows']) for e in events),
               'v2_duplicate_identity_rows': len(duplicate_indices),
               'csv_currency_status_counts': dict(Counter(r['currency'] + '|' + r['status'] for r in csv_details)),
               'v2_currency_status_counts': dict(Counter(str(r['currency'] or 'missing') + '|' + r['status'] for r in v2_details))}
    assert sum(summary['csv_status_counts'].values()) == len(transactions)
    assert sum(summary['v2_status_counts'].values()) == len(native_rows)
    return {'summary': summary, 'csv_evidence': csv_details, 'v2_evidence': v2_details, 'events': events,
            'duplicate_native_identity_groups': duplicates,
            'limits': ['Snapshot month windows differ; absence is not proof of missing payout.',
                       'Unique event evidence is not a bank receipt or tax policy.',
                       'Unknown subjects are retained, not classified as other.',
                       'Site wall clocks are compared; no assumed UTC conversion is applied.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transactions', required=True)
    parser.add_argument('--native-dir', required=True)
    parser.add_argument('--scope', action='append', required=True)
    parser.add_argument('--currency-map', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = private_output(args.out)
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    scopes = [row for file in args.scope for row in read(file)]
    files = sorted(Path(args.native_dir).glob('settlement_details_*_site_august.json'))
    if not files:
        raise ValueError('no native detail snapshots')
    native = [row for file in files for row in read(file)]
    report = build_bridge(read(args.transactions), native, scopes, read(args.currency_map))
    report['sources'] = {'transactions': args.transactions, 'native_files': [str(f) for f in files],
                         'scope_files': args.scope, 'currency_map': args.currency_map,
                         'native_selection': 'existing site_august snapshots; not a fresh API request'}
    out.mkdir(parents=True, exist_ok=True)
    (out/'payout_activity_bridge.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
