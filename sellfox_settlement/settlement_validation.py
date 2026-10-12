"""Read-only, scoped Settlement V2 and plugin availability probe."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from sellfox_settlement.validation_paths import private_output


def fetch_complete(client, path, body):
    body = dict(body)
    body.setdefault('pageSize', '200')
    rows = []
    expected = None
    seen_pages = set()
    seen_rows = set()
    for page in range(1, 10001):
        response = client.signed_post(path, {**body, 'pageNo':str(page)})
        if not isinstance(response, dict):
            raise ValueError('unexpected pagination response')
        row_keys = ['rows', 'detailPageVoList', 'groupVoList', 'groupList', 'records']
        batch = next((response[key] for key in row_keys if isinstance(response.get(key), list)), None)
        reported = response.get('totalSize', response.get('total'))
        if batch is None:
            explicit_empty = reported is not None and int(reported) == 0 and any(
                key in response and response[key] is None for key in row_keys)
            if not explicit_empty:
                raise ValueError('missing response rows')
            batch = []
        fingerprint = json.dumps(batch, sort_keys=True, ensure_ascii=False)
        if batch and fingerprint in seen_pages:
            raise ValueError('repeated pagination page')
        seen_pages.add(fingerprint)
        for row in batch:
            identity = ('id', str(row['id'])) if row.get('id') is not None else ('row', json.dumps(row, sort_keys=True, ensure_ascii=False))
            if identity in seen_rows:
                raise ValueError('overlapping pagination rows')
            seen_rows.add(identity)
        if reported is not None:
            reported = int(reported)
            if expected is not None and reported != expected:
                raise ValueError('pagination total changed during read')
            expected = reported
        rows.extend(batch)
        if page % 10 == 0:
            print(f'{path.rsplit("/", 1)[-1]} page={page} rows={len(rows)} expected={expected}', flush=True)
        if expected is not None and len(rows) >= expected:
            if len(rows) != expected:
                raise ValueError('pagination total mismatch')
            return rows
        if len(batch) < int(body['pageSize']):
            if expected is not None:
                raise ValueError('incomplete pagination')
            return rows
    raise ValueError('pagination limit exceeded')


def scope_rows(rows, scope):
    validate_scope(scope)
    keys = {(str(s['sellerId']), str(s['marketplaceId'])) for s in scope}
    matched, outside = [], []
    for row in rows:
        target = matched if (str(row.get('sellerId')), str(row.get('marketplaceId'))) in keys else outside
        target.append(row)
    return matched, outside


def validate_scope(scope):
    if not scope:
        raise ValueError('empty settlement scope')
    for row in scope:
        if not all(row.get(key) not in (None, '') for key in ['sellerId','marketplaceId']):
            raise ValueError('missing stable scope key')


def bridge_residual(row):
    components = ['beginningBalance','endingBalance','accountIncome','accountRefund','accountExpenditure']
    return sum((Decimal(str(row[k])) for k in components), Decimal(0)) - Decimal(str(row['accountNetIncome']))


def native_currency_scopes(scope, currency_map):
    """Join absolute source paths to filename-keyed CSV/PDF currency evidence."""
    validate_scope(scope)
    groups = {}
    stable_currencies = {}
    allowed = {'USD', 'CAD', 'MXN', 'EUR', 'GBP', 'PLN', 'SEK'}
    for shop in scope:
        source = str(shop.get('file') or '')
        basename = Path(source.replace('\\', '/')).name
        candidates = [currency_map[key] for key in {source, basename} if key in currency_map]
        currencies = {value.get('currency') for value in candidates if isinstance(value, dict)}
        if len(currencies) > 1:
            raise ValueError('conflicting currency evidence: ' + basename)
        if not currencies or None in currencies or '' in currencies:
            raise ValueError('missing currency evidence: ' + basename)
        currency = next(iter(currencies))
        if currency not in allowed:
            raise ValueError('unsupported currency evidence: ' + basename)
        stable_key = (str(shop['sellerId']), str(shop['marketplaceId']))
        if stable_key in stable_currencies and stable_currencies[stable_key] != currency:
            raise ValueError('conflicting currency for stable shop key')
        stable_currencies[stable_key] = currency
        groups.setdefault(currency, []).append(shop)
    return groups


def fetch_native_details(client, currency_scopes, start, end, output):
    """Read each site's native currency and retain complete private API evidence."""
    output = private_output(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / 'settlement_detail_evidence'
    evidence.mkdir(exist_ok=True)
    details, errors = [], []
    for currency, subset in sorted(currency_scopes.items()):
        try:
            validate_scope(subset)
            body = {'startTime':start, 'endTime':end, 'currency':currency,
                    'shopIds':sorted({s['id'] for s in subset}, key=str),
                    'marketplaceIds':sorted({s['marketplaceId'] for s in subset})}
            raw = fetch_complete(client, '/api/financial/v2/settlementSummary/detailPage.json', body)
            matched, outside = scope_rows(raw, subset)
            (evidence / f'{currency}_raw.json').write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
            (evidence / f'{currency}_outside_scope.json').write_text(json.dumps(outside, ensure_ascii=False), encoding='utf-8')
            (output / f'settlement_details_{currency}.json').write_text(json.dumps(matched, ensure_ascii=False), encoding='utf-8')
            counts = {str(c):sum(r.get('currency') == c for r in matched) for c in {r.get('currency') for r in matched}}
            mismatched = sum(r.get('currency') != currency for r in matched)
            details.append({'currency':currency, 'scope_files':len(subset), 'scope_shops':len(body['shopIds']),
                            'input_rows':len(raw), 'scoped_rows':len(matched), 'outside_scope':len(outside),
                            'start':start, 'end':end, 'amount_fields_present':sum(r.get('amount') is not None for r in matched),
                            'returned_currency_counts':counts, 'returned_currency_mismatch':mismatched})
            if mismatched:
                errors.append({'stage':f'details_{currency}', 'error_type':'returned_currency_mismatch'})
        except (ValueError, RuntimeError, OSError) as exc:
            errors.append({'stage':f'details_{currency}', 'error_type':type(exc).__name__})
    return details, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', type=Path, required=True)
    parser.add_argument('--additional-scope', type=Path)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--start', default='2026-08-01')
    parser.add_argument('--end', default='2026-09-30')
    parser.add_argument('--include-details', action='store_true')
    parser.add_argument('--currency-map', type=Path, help='CSV/PDF evidence keyed by source filename, required for native-currency details')
    parser.add_argument('--detail-start')
    parser.add_argument('--detail-end')
    args = parser.parse_args()
    if args.include_details and not args.currency_map:
        parser.error('--currency-map is required to avoid converting foreign sites')
    try:
        output = private_output(args.out)
    except ValueError as exc:
        parser.error(str(exc))
    scope = json.loads(args.scope.read_text(encoding='utf-8'))
    if args.additional_scope:
        scope.extend(json.loads(args.additional_scope.read_text(encoding='utf-8')))
    validate_scope(scope)
    if not all(row.get('id') not in (None, '') for row in scope):
        parser.error('scope is missing shop id')
    currency_scopes = None
    if args.include_details:
        currency_map = json.loads(args.currency_map.read_text(encoding='utf-8'))
        try:
            currency_scopes = native_currency_scopes(scope, currency_map)
        except ValueError as exc:
            parser.error(str(exc))
    from SELLFOX_API.client import SellfoxClient, SellfoxConfig
    client = SellfoxClient(SellfoxConfig.from_env(args.data_root / '.env', args.data_root / 'SELLFOX_API' / '.env'))
    output.mkdir(parents=True, exist_ok=True)
    body = {'startTime':args.start,'endTime':args.end,
            'shopIds':sorted({s['id'] for s in scope}, key=str),
            'marketplaceIds':sorted({s['marketplaceId'] for s in scope})}
    summary = {'scope_files':len(scope), 'scope_shop_ids':len(set(body['shopIds'])),
               'start':args.start,'end':args.end, 'errors':[]}
    try:
        raw = fetch_complete(client, '/api/financial/v2/settlementSummary/groupPage.json', {**body,'timeType':'settlementEndTime'})
        matched, outside = scope_rows(raw, scope)
        (output / 'settlement_groups_raw.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'settlement_groups_scoped.json').write_text(json.dumps(matched, ensure_ascii=False, indent=2), encoding='utf-8')
        summary.update(groups_input=len(raw), groups_scoped=len(matched), groups_outside_scope=len(outside))
        summary['group_fields'] = sorted({k for r in matched for k in r})
        summary['currencies'] = sorted({str(r.get('currency')) for r in matched})
        summary['missing_bridge_fields'] = {key:sum(r.get(key) is None for r in matched) for key in ['beginningBalance','endingBalance','accountIncome','accountRefund','accountExpenditure','accountNetIncome','transferAmount','arrivalAmount']}
        summary['activity_only_vs_net_nonzero'] = sum(
            Decimal(str(r['accountIncome'])) + Decimal(str(r['accountRefund'])) + Decimal(str(r['accountExpenditure'])) != Decimal(str(r['accountNetIncome']))
            for r in matched if all(r.get(k) is not None for k in ['accountIncome','accountRefund','accountExpenditure','accountNetIncome']))
        summary['bridge_identity_nonzero'] = sum(bridge_residual(r) != 0 for r in matched)
    except (ValueError, RuntimeError, OSError) as exc:
        summary['errors'].append({'stage':'settlement_groups','error_type':type(exc).__name__})
    for report_type in [3, 4]:
        try:
            reports = fetch_complete(client, '/api/report/center/task/getPlugPageList.json',
                {'startTime':args.start,'endTime':args.end,'reportTypeList':[report_type],
                 'statusList':[1],'shopIdList':body['shopIds']})
            (output / f'plugin_reports_{report_type}.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
            summary[f'plugin_type_{report_type}_rows'] = len(reports)
            summary[f'plugin_type_{report_type}_august_rows'] = sum(r.get('reportDayType') == '2026-08' for r in reports)
        except (ValueError, RuntimeError, OSError) as exc:
            summary['errors'].append({'stage':f'plugin_type_{report_type}','error_type':type(exc).__name__})
    if args.include_details:
        details, errors = fetch_native_details(client, currency_scopes,
            args.detail_start or args.start, args.detail_end or args.end, output)
        summary['details'] = details
        summary['errors'].extend(errors)
    (output / 'settlement_validation_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(bool(summary['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
