"""Offline tail-fee routing evidence; no production writes or final cost allocation.

Mirrors order_sync._calculate_last_leg_fee routing, using already allocated RMB
fields. Parent/split overlaps are held for allocation evidence, never auto-deduped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sellfox_settlement.cost_validation import base_order_id, normalize_sku, validate_input
from sellfox_settlement.validation_paths import private_output

FIELDS = ('upload_allocated_carrier_fee_rmb', 'allocated_carrier_fee_rmb',
          'hist_predict_fee', 'allocated_tt_fee_rmb')
PRIORITIES = {'历史预估尾程费用': 'hist_predict_fee', '通途尾程费用': 'allocated_tt_fee_rmb'}


def money(value):
    result = Decimal(str(value or 0))
    if not result.is_finite():
        raise ValueError('non-finite fee value')
    # Production flt(value, 4) rounds float inputs to four places.
    return Decimal(str(round(float(result), 4))).quantize(Decimal('.0001'))


def select_tail(order, item, priority='历史预估尾程费用'):
    amounts = {field: money(item.get(field)) for field in FIELDS}
    if order.get('order_type') == 'FBA':
        return Decimal(0), '', 'fba_excluded'
    if str(order.get('platform_code') or '').strip().upper() in {'OS', 'PB', 'WF'} or str(order.get('sale_account') or '').strip().upper() in {'TTTOODDLYUS', 'TTCOZYDOZYUS'}:
        return Decimal(0), '', 'buyer_paid_tail_excluded'
    if '多渠道仓库' in str(order.get('warehouse_name') or ''):
        return Decimal(0), '', 'multichannel_warehouse_excluded'
    for field in FIELDS[:2]:
        if amounts[field] > 0:
            return amounts[field], field, 'actual_carrier_priority'
    third = PRIORITIES.get(priority)
    if third and amounts[third] > 0:
        return amounts[third], third, 'configured_third_priority'
    return Decimal(0), '', 'configured_source_zero_no_fallback' if third else 'unknown_priority_hold'


def parent_child_risks(orders):
    groups = defaultdict(list)
    for order in orders:
        groups[(order['sale_account'], base_order_id(order['platform_order_id']))].append(order)
    risks = []
    for (account, base), members in groups.items():
        parents = [o for o in members if o['platform_order_id'] == base]
        children = [o for o in members if o['platform_order_id'] != base]
        if not parents or not children:
            continue
        def side(rows):
            return {'order_names': [o['name'] for o in rows],
                    'persisted_tail_total': str(sum((money(i.get('last_leg_fee')) for o in rows for i in o['order_items']), Decimal(0))),
                    'package_ids': sorted({p['package'] for o in rows for p in o.get('packages', []) if p.get('package')})}
        parent, child = side(parents), side(children)
        a, b = Decimal(parent['persisted_tail_total']), Decimal(child['persisted_tail_total'])
        risks.append({'account': account, 'base_order_id': base, 'parent': parent, 'children': child,
                      'both_positive': a > 0 and b > 0, 'equal_positive_totals': a == b and a > 0,
                      'shared_package_ids': sorted(set(parent['package_ids']) & set(child['package_ids'])),
                      'status': 'hold_fee_unit_or_allocation_unproven',
                      'rule': 'never_add_parent_and_children; amount_equality_or_package_overlap_alone_is_not_allocation_proof'})
    return risks


def diagnose(orders, coverage, priority='历史预估尾程费用'):
    validate_input(orders, {'name', 'platform_order_id', 'sale_account', 'order_items'}, 'orders')
    validate_input(coverage, {'status'}, 'coverage')
    for order in orders:
        validate_input(order['order_items'], set(FIELDS) | {'platform_sku', 'quantity', 'last_leg_fee'},
                       f"items of {order['name']}")
    by_name = {o['name']: o for o in orders}
    if len(by_name) != len(orders):
        raise ValueError('duplicate order names')
    details, excluded, included_transactions = [], [], 0
    for position, row in enumerate(coverage, 1):
        trace = {'coverage_position': position, 'source_file': row.get('source_file'),
                 'source_line': row.get('source_line'), 'order_id': row.get('order_id'), 'sku': row.get('sku')}
        if row['status'] != 'matched':
            excluded.append({**trace, 'reason': row['status']})
            continue
        names = row.get('en_order_names') or []
        if not names or any(name not in by_name for name in names):
            excluded.append({**trace, 'reason': 'linked_order_missing'})
            continue
        linked = [(by_name[name], n, item) for name in names
                  for n, item in enumerate(by_name[name]['order_items'], 1)
                  if normalize_sku(item.get('platform_sku')) == normalize_sku(row.get('sku')) and row.get('sku')]
        if not linked:
            excluded.append({**trace, 'reason': 'linked_sku_missing'})
            continue
        included_transactions += 1
        for order, item_position, item in linked:
            value, field, reason = select_tail(order, item, priority)
            missing = [f for f in (*FIELDS, 'last_leg_fee') if item.get(f) is None or item.get(f) == '']
            available = {f: str(money(item.get(f))) for f in FIELDS if f != field and money(item.get(f)) > 0}
            details.append({**trace, 'order_name': order['name'], 'account': order['sale_account'],
                            'fulfillment': row.get('fulfillment'), 'item_position': item_position,
                            'quantity': item.get('quantity'), 'split_package_cost_factor': item.get('split_package_cost_factor'),
                            'source_fields': {f: str(money(item.get(f))) for f in FIELDS},
                            'source_missing_fields': missing,
                            'source_completeness': 'missing_values_hold' if missing else 'complete_values',
                            'selected_field': field, 'selected_amount_rmb': str(value), 'selection_reason': reason,
                            'persisted_tail_rmb': str(money(item.get('last_leg_fee'))),
                            'persisted_source': item.get('last_leg_fee_sources'),
                            'selection_matches_persisted_amount': money(item.get('last_leg_fee')) == value,
                            'available_not_selected': available,
                            'amount_basis': 'persisted_allocated_row_amount_not_multiplied_by_quantity',
                            'allocation_status': 'hold_package_fee_unit_and_row_allocation_not_proven'})
    unique = {(r['order_name'], r['item_position']) for r in details}
    tt_unselected = [r for r in details if r['fulfillment'] == 'FBM' and not r['persisted_source'] and
                     r['selection_reason'] == 'configured_source_zero_no_fallback' and 'allocated_tt_fee_rmb' in r['available_not_selected']]
    summary = {'input_transaction_rows': len(coverage), 'included_transaction_rows': included_transactions,
               'excluded_transaction_rows': len(excluded), 'matched_item_occurrences': len(details),
               'unique_matched_items': len(unique), 'selection_reasons': dict(Counter(r['selection_reason'] for r in details)),
               'missing_amount_evidence_occurrences': sum(bool(r['source_missing_fields']) for r in details),
               'persisted_amount_mismatch_occurrences': sum(not r['selection_matches_persisted_amount'] for r in details),
               'tt_positive_unselected_occurrences': len(tt_unselected),
               'tt_positive_unselected_unique_items': len({(r['order_name'], r['item_position']) for r in tt_unselected})}
    assert included_transactions + len(excluded) == len(coverage)
    return {'priority_assumption': priority, 'financial_use': 'diagnostic_only', 'summary': summary,
            'details': details, 'excluded': excluded, 'tt_positive_unselected': tt_unselected,
            'parent_child_risks': parent_child_risks(orders)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orders', type=Path, required=True)
    parser.add_argument('--coverage', type=Path, required=True)
    parser.add_argument('--priority', choices=tuple(PRIORITIES), default='历史预估尾程费用')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = private_output(args.output_dir)
    report = diagnose(json.loads(args.orders.read_text(encoding='utf-8')),
                      json.loads(args.coverage.read_text(encoding='utf-8')), args.priority)
    report['input_manifest'] = [{ 'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (args.orders, args.coverage)]
    out.mkdir(parents=True, exist_ok=True)
    (out/'tail_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
