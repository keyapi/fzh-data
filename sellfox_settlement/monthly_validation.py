"""Offline monthly technical validation; private outputs and no finance-policy decisions."""
from __future__ import annotations

import argparse
import calendar
from collections import Counter, defaultdict
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sellfox_settlement.non_v2_validation import candidate_totals, validate_directory
from sellfox_settlement.pdf_validation import csv_controls, extract_pdf
from sellfox_settlement.validation_paths import private_output


def compare_controls(csv_result, pdf_result):
    """Preserve source controls, and mark missing PDF components partial even at zero."""
    checks = []
    groups = csv_result.get('comparison_groups', {})
    for key, value in sorted(csv_result['controls'].items()):
        components = groups.get(key, [key])
        if key not in groups and key not in pdf_result['controls']:
            continue  # The template prints no such standalone line; PDF issues retain gaps.
        missing = sorted(c for c in components if c not in pdf_result['controls'])
        pdf_value = sum((pdf_result['controls'][c] for c in components
                         if c in pdf_result['controls']), Decimal(0))
        difference = value - pdf_value
        checks.append({'control': key, 'csv_value': str(value), 'pdf_value': str(pdf_value),
            'difference': str(difference), 'components': components, 'missing_components': missing,
            'status': 'partial' if missing else ('difference' if difference else 'complete'),
            'csv_evidence': csv_result.get('control_evidence', {}).get(key, []),
            'pdf_evidence': {c: pdf_result.get('control_evidence', {}).get(c, []) for c in components}})
    return checks


def refund_other_bridge(csv_result, pdf_result):
    """An aggregate explanatory bridge, never an allocation or source-value rewrite."""
    keys = ('refunds_non_fba', 'refunds_fba', 'shipping_refunds', 'gift_wrap_refunds',
            'promotion_refunds', 'tax_refunded')
    other_rows = [r for r in csv_result.get('unallocated', [])
                  if r['reason'] == 'refund_other_combines_components']
    other = sum((Decimal(str(r['amount'])) for r in other_rows), Decimal(0))
    deltas = {k: pdf_result['controls'].get(k, Decimal(0)) - csv_result['controls'].get(k, Decimal(0))
              for k in keys if k in csv_result['controls'] or k in pdf_result['controls']}
    residual = other - sum(deltas.values(), Decimal(0))
    missing = [k for k in deltas if k not in pdf_result['controls']
               and csv_result['controls'].get(k, Decimal(0))]
    return {'csv_refund_other': str(other), 'pdf_minus_csv_deltas': {k: str(v) for k, v in deltas.items()},
        'residual': str(residual), 'status': 'partial' if missing else ('difference' if residual else 'complete'),
        'missing_components': missing, 'other_rows': other_rows,
        'interpretation': 'Aggregate reclassification explains the combined other bucket; individual components remain unallocated.'}


def candidate_groups(rows, currency_map):
    grouped = defaultdict(list)
    for row in rows:
        source = row['source_file']
        mapped = currency_map.get(source, '')
        currency = row.get('currency') or (mapped.get('currency', '') if isinstance(mapped, dict) else mapped)
        grouped[(source, currency, row.get('transaction_status', 'Unknown'))].append(row)
    return [{'source_file': source, 'currency': currency, 'transaction_status': status,
             'input_rows': len(items), 'output_rows': len(items), **candidate_totals(items)}
            for (source, currency, status), items in sorted(grouped.items())]


def source_manifest(root):
    files = []
    for path in sorted(Path(root).iterdir()):
        if path.is_file() and path.suffix.lower() in ('.csv', '.pdf'):
            data = path.read_bytes()
            files.append({'source_file': path.name, 'path': str(path.resolve()),
                          'kind': path.suffix.lower()[1:], 'size_bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest()})
    return {'files': files, 'counts': dict(Counter(f['kind'] for f in files)), 'total_files': len(files)}


def pdf_window_checks(rows, pdf):
    """Compare timestamp calendar dates in the PDF's own explicit timezone.

    The printed Summary end time can be clipped, so this check deliberately uses
    date boundaries rather than supplying an unobserved final time.
    """
    zone = pdf.get('timezone')
    offsets = {'PDT': -7, 'PST': -8, 'UTC': 0, 'CST': -6, 'BST': 1, 'CET': 1, 'CEST': 2}
    if zone and zone.startswith('GMT'):
        offset = int(zone[3:])
    elif zone in offsets:
        offset = offsets[zone]
    else:
        return [{'reason': 'pdf_timezone_unresolved'}]
    if not pdf.get('period_start') or not pdf.get('period_end'):
        return [{'reason': 'pdf_period_unresolved'}]
    timezone = dt.timezone(dt.timedelta(hours=offset))
    issues = []
    for row in rows:
        timestamp = dt.datetime.fromisoformat(row['date_time'])
        converted = timestamp.astimezone(timezone).date().isoformat()
        if not pdf['period_start'] <= converted <= pdf['period_end']:
            issues.append({'source_file': row['source_file'], 'source_line': row['source_line'],
                'csv_timestamp': row['date_time'], 'pdf_timezone': zone, 'converted_date': converted,
                'reason': 'csv_timestamp_outside_pdf_timezone_window'})
    return issues


def validate_month(root, month):
    before = source_manifest(root)
    csv_validation = validate_directory(root, month)
    csv_files = {r['source_file']: r for r in csv_validation['files']}
    pairs = []
    currency_map = {}
    pdf_errors = []
    for pair in csv_validation['pairs']:
        result = {'key': pair['key'], 'status': pair['status'], 'csv_paths': pair['csv'], 'pdf_paths': pair['pdf']}
        if pair['status'] != 'paired':
            pairs.append(result)
            continue
        source = Path(pair['csv'][0]).name
        csv_file = csv_files.get(source)
        if csv_file is None:
            result['status'] = 'csv_failed'
            pairs.append(result)
            continue
        try:
            pdf = extract_pdf(pair['pdf'][0])
        except Exception as exc:
            # Keep every unreadable source; do not suppress failed files from counts.
            pdf_errors.append({'source_file': Path(pair['pdf'][0]).name,
                               'reason': type(exc).__name__ + ': ' + str(exc)})
            result['status'] = 'pdf_failed'
            pairs.append(result)
            continue
        currency = csv_file['currency'] or pdf['currency'] or ''
        currency_map[source] = {'currency': currency,
            'kind': csv_file['currency_evidence'] if csv_file['currency'] else pdf['currency_evidence']['kind']}
        rows = [{**r, 'currency': r['currency'] or currency} for r in csv_file['rows']]
        projection = csv_controls(rows)
        checks = compare_controls(projection, pdf)
        metadata_issues = []
        if csv_file['currency'] and pdf['currency'] and csv_file['currency'] != pdf['currency']:
            metadata_issues.append('csv_pdf_currency_mismatch')
        if not currency:
            metadata_issues.append('currency_unresolved')
        if pdf['period_start'] is None or pdf['period_end'] is None:
            metadata_issues.append('pdf_period_unresolved')
        elif pdf['period_start'][:7] != month or pdf['period_end'][:7] != month:
            metadata_issues.append('pdf_period_outside_month')
        else:
            year, month_number = map(int, month.split('-'))
            expected_start = month + '-01'
            expected_end = f'{month}-{calendar.monthrange(year, month_number)[1]:02d}'
            if pdf['period_start'] != expected_start or pdf['period_end'] != expected_end:
                metadata_issues.append('pdf_period_not_full_month')
        window_issues = pdf_window_checks(rows, pdf)
        result.update(source_file=source, currency=currency, currency_evidence=currency_map[source],
            input_rows=csv_file['input_rows'], normalized_rows=len(rows), rejected_rows=len(csv_file['rejected_rows']),
            pdf=pdf, csv_controls=projection, comparisons=checks,
            refund_other_bridge=refund_other_bridge(projection, pdf), metadata_issues=metadata_issues,
            pdf_window_checked_rows=len(rows), pdf_window_issues=window_issues)
        pairs.append(result)
    after = source_manifest(root)
    sources_unchanged = before == after
    checks = [c for p in pairs for c in p.get('comparisons', [])]
    candidates = candidate_groups(csv_validation['rows'], currency_map)
    summary = {**csv_validation['summary'], 'source_files': before['total_files'],
        'source_hashes': len(before['files']), 'sources_unchanged': sources_unchanged,
        'pdf_success': sum('pdf' in p for p in pairs), 'pdf_failed': len(pdf_errors),
        'comparison_count': len(checks), 'comparison_status_counts': dict(Counter(c['status'] for c in checks)),
        'refund_bridge_status_counts': dict(Counter(p['refund_other_bridge']['status'] for p in pairs if 'refund_other_bridge' in p)),
        'pdf_issue_counts': dict(Counter(i['reason'] for p in pairs for i in p.get('pdf', {}).get('issues', []))),
        'candidate_groups': len(candidates), 'candidate_rows': sum(c['input_rows'] for c in candidates),
        'pdf_window_checked_rows': sum(p.get('pdf_window_checked_rows', 0) for p in pairs),
        'pdf_window_issue_count': sum(len(p.get('pdf_window_issues', [])) for p in pairs),
        'metadata_issue_counts': dict(Counter(i for p in pairs for i in p.get('metadata_issues', [])))}
    # Differences explained by opaque Refund.other and known PDF blanks remain reportable
    # exceptions. Fatal parser/schema/period/amount problems must never yield a clean gate.
    explained_controls = {'refunds_non_fba', 'refunds_fba', 'shipping_refunds',
                          'gift_wrap_refunds', 'promotion_refunds', 'tax_refunded', 'tax'}
    fatal_pdf_issues = []
    for pair in pairs:
        for issue in pair.get('pdf', {}).get('issues', []):
            known_blank = issue['reason'] == 'missing_amount_row' and pair.get('currency') == 'CAD'
            known_blank = known_blank and issue.get('candidate_keys') == ['inventory_inbound_fees']
            if issue['reason'] != 'truncated_period_end_time' and not known_blank:
                fatal_pdf_issues.append({'source_file': pair.get('source_file'), **issue})
    unexplained_differences = [c for c in checks if c['status'] == 'difference'
                              and c['control'] not in explained_controls]
    fatal = bool(csv_validation['file_errors'] or csv_validation['rejected_rows'] or pdf_errors
        or any(p['status'] != 'paired' or p.get('metadata_issues') or p.get('pdf_window_issues') for p in pairs)
        or csv_validation['summary']['row_total_nonzero'] or not sources_unchanged
        or any(r['issues'] for r in csv_validation['rows'])
        or fatal_pdf_issues or unexplained_differences
        or any(p.get('refund_other_bridge', {}).get('status') == 'difference' for p in pairs))
    summary['fatal_validation_errors'] = fatal
    summary['finance_rules_status'] = 'pending_ZJ'
    return {'summary': summary, 'pairs': pairs, 'candidate_groups': candidates,
            'csv_validation': csv_validation, 'pdf_errors': pdf_errors,
            'source_manifest': before, 'currency_map': currency_map,
            'fatal_pdf_issues': fatal_pdf_issues, 'unexplained_differences': unexplained_differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--month', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    dt.datetime.strptime(args.month, '%Y-%m')
    try:
        output = private_output(args.out, input_root=args.input)
    except ValueError as exc:
        parser.error(str(exc))
    result = validate_month(args.input, args.month)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'monthly_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (output / 'source_manifest.json').write_text(json.dumps(result['source_manifest'], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
    return int(result['summary']['fatal_validation_errors'])


if __name__ == '__main__':
    raise SystemExit(main())
