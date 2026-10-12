"""Corroborate standard file accounts against native snapshot identifiers.

Unique order/SKU joins are evidence, never a global cost fallback. Conflicting
or missing identifiers retain their files in the report and receive no scope.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from sellfox_settlement.cost_validation import base_order_id, normalize_sku
from sellfox_settlement.validation_paths import private_output


def build_bridge(transactions, account_report, en_orders, upstream_orders):
    names = [Path(file['file']).name for file in account_report['files']]
    if len(set(names)) != len(names):
        raise ValueError('duplicate account-report filename')
    evidence = defaultdict(lambda: defaultdict(set))
    for source, orders in [('en', en_orders), ('tongtool', upstream_orders)]:
        for order in orders:
            oid = base_order_id(order.get('platform_order_id') if source == 'en' else order.get('orderId'))
            account = order.get('sale_account') if source == 'en' else order.get('account')
            items = order.get('order_items', []) if source == 'en' else order.get('orderItem', [])
            for item in items:
                sku = normalize_sku(item.get('platform_sku') if source == 'en' else item.get('sku'))
                if oid and sku and account:
                    evidence[(oid, sku)][str(account)].add(source)
    by_file = defaultdict(list)
    for row in transactions:
        by_file[Path(row['source_file']).name].append(row)
    mappings, files = {}, []
    for file in account_report['files']:
        name = Path(file['file']).name
        standard = file.get('account_candidate') if file.get('match', {}).get('status') == 'matched' else None
        links, ambiguous, no_evidence = [], [], []
        for row in by_file[name]:
            if row.get('type') not in {'Order', 'Refund', 'Refund_Retrocharge', 'Chargeback Refund'}:
                continue
            candidates = evidence.get((str(row.get('order_id') or ''), normalize_sku(row.get('sku'))), {})
            record = {'source_line':row.get('source_line'), 'order_id':row.get('order_id'),
                      'sku':row.get('sku'), 'native_accounts':sorted(candidates),
                      'sources':{k:sorted(v) for k,v in candidates.items()}}
            if len(candidates) == 1:
                links.append(record)
            elif candidates:
                ambiguous.append(record)
            else:
                no_evidence.append(record)
        native = sorted({a for r in links for a in r['native_accounts']})
        if not standard:
            status = 'standard_account_unmapped'
        elif ambiguous:
            status = 'ambiguous_native_evidence'
        elif not native:
            status = 'no_native_evidence'
        elif native != [standard]:
            status = 'native_identifier_conflict'
        else:
            status = 'corroborated_exact_identifier'
            mappings[name] = standard
        files.append({'file':name,'standard_account':standard,'status':status,
                      'native_accounts':native,'unique_evidence_rows':len(links),
                      'ambiguous_evidence_rows':len(ambiguous),'evidence':links,'ambiguous_evidence':ambiguous,
                      'no_evidence_rows':len(no_evidence),'no_evidence':no_evidence,
                      'input_rows':len(by_file[name])})
    known = {f['file'] for f in files}
    for name in sorted(set(by_file)-known):
        files.append({'file':name,'status':'file_missing_from_account_report','input_rows':len(by_file[name]),
                      'no_evidence':[{'source_line':r.get('source_line'),'order_id':r.get('order_id'),
                                      'sku':r.get('sku'),'native_accounts':[],'sources':{}}
                                     for r in by_file[name] if r.get('type') in
                                     {'Order','Refund','Refund_Retrocharge','Chargeback Refund'}]})
    assert sum(file['input_rows'] for file in files) == len(transactions)
    return {'summary':{'files':len(files),'scoped_files':len(mappings),
                       'statuses':dict(Counter(f['status'] for f in files)),
                       'input_rows':len(transactions),'reported_rows':sum(f['input_rows'] for f in files)},
            'account_by_file':mappings,'files':files,
            'scope_basis':'Exact standard/native identifier corroborated by unique order+SKU snapshot evidence; not historical ownership certification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transactions', type=Path, required=True)
    parser.add_argument('--account-report', type=Path, required=True)
    parser.add_argument('--orders', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, action='append', default=[])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        out = private_output(args.out)
    except ValueError as exc:
        parser.error(str(exc))
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    upstream = [row for path in args.upstream for row in read(path)]
    report = build_bridge(read(args.transactions),read(args.account_report),read(args.orders),upstream)
    out.mkdir(parents=True, exist_ok=True)
    (out/'account_cost_bridge.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'account_by_file.json').write_text(json.dumps(report['account_by_file'],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False))


if __name__ == '__main__':
    main()
