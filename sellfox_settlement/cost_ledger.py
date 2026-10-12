"""Offline component evidence ledger. Snapshot sums are not tax cost amounts."""
from __future__ import annotations

import argparse
import hashlib
import gzip
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sellfox_settlement.cost_validation import base_order_id, normalize_sku, validate_input
from sellfox_settlement.validation_paths import private_output

COMPONENTS = {'product': 'sx_shipping_cost', 'first': 'first_freight',
              'process': 'valuation_rate', 'tail': 'last_leg_fee'}


def amount(value):
    if value is None or value == '':
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('non-finite cost amount')
    return result


def total(items, field):
    values = [amount(item.get(field)) for item in items]
    return None if not values or any(value is None for value in values) else sum(values, Decimal(0))


def text(value):
    return None if value is None else str(value)


def build_ledger(orders, probes=None, coverage=None, *, component_probes=None, component_source_sha256=None):
    """Select child evidence once per native account/base order; hold product conflicts.

    Persisted fields are summed as stored, without quantity multiplication. Current
    BOM probe values retain raw calculation units and never enter these sums.
    Refund references do not reverse cost. No final accounting total is produced.
    """
    validate_input(orders, {'name', 'sale_account', 'platform_order_id', 'order_items'}, 'orders')
    if len({o['name'] for o in orders}) != len(orders):
        raise ValueError('duplicate EN order names')
    by_group = defaultdict(list)
    for order in orders:
        if not order['sale_account'] or not order['platform_order_id']:
            raise ValueError('missing native account/order identity')
        validate_input(order['order_items'], {'platform_sku', 'quantity'}, 'order items')
        for item in order['order_items']:
            try:
                quantity = amount(item['quantity'])
            except Exception as exc:
                raise ValueError('invalid component quantity') from exc
            if isinstance(item['quantity'], bool) or quantity is None or quantity < 0 or quantity != quantity.to_integral_value():
                raise ValueError('invalid component quantity')
        by_group[(order['sale_account'], base_order_id(order['platform_order_id']))].append(order)
    probe_index = defaultdict(list)
    for probe in probes or []:
        probe_index[(probe.get('order'), probe.get('sku'))].append(probe)
    component_index = {}
    if component_probes is not None and not re.fullmatch(r'[0-9a-f]{64}', str(component_source_sha256)):
        raise ValueError('component snapshot hash required')
    for probe in component_probes or []:
        if probe.get('source_orders_sha256') != component_source_sha256:
            raise ValueError('component snapshot hash mismatch')
        key = (probe['order'], probe['item_position'])
        if isinstance(probe['item_position'], bool) or not isinstance(probe['item_position'], int) or probe['item_position'] < 1:
            raise ValueError('invalid component probe position')
        if key in component_index:
            raise ValueError('duplicate component probe identity')
        component_index[key] = probe
    if component_probes is not None:
        expected = {(o['name'], n) for o in orders for n, _ in enumerate(o['order_items'], 1)}
        if expected - component_index.keys():
            raise ValueError('missing component probe identity')
        if component_index.keys() - expected:
            raise ValueError('component probe references unknown component')
    # Probe order is EN name (globally unique), not the platform order ID.
    # The probe still lacks item-row identity; attach only an unambiguous key.
    item_keys = Counter((o['name'], i.get('tongtool_sku'))
                        for o in orders for i in o['order_items'])
    groups, items, status_counts = [], [], Counter()
    for (account, base), group in sorted(by_group.items()):
        parents = [o for o in group if o['platform_order_id'] == base]
        children = [o for o in group if o['platform_order_id'] != base]
        selected = children or parents
        selected_names = {o['name'] for o in selected}
        selected_items = [i for o in selected for i in o['order_items']]
        parent_items = [i for o in parents for i in o['order_items']]
        components = {}
        for component, field in COMPONENTS.items():
            chosen, parent = total(selected_items, field), total(parent_items, field)
            state = 'selected_child_snapshot' if children else 'selected_unsplit_snapshot'
            if not selected_items:
                state = 'hold_missing_items'
            elif chosen is None:
                state = 'hold_missing_amount'
            elif len(parents) > 1:
                state = 'hold_multiple_parents'
            elif component == 'product' and children and parent is not None and parent != 0 and chosen != 0 and parent != chosen:
                state = 'hold_parent_children_difference'
            components[component] = {'field': field, 'status': state,
                                     'parent_snapshot_amount': text(parent),
                                     'selected_snapshot_amount': text(chosen),
                                     'included_snapshot_amount': None if state.startswith('hold_') else text(chosen)}
            status_counts[component + '|' + state] += 1
        for order in group:
            for position, item in enumerate(order['order_items'], 1):
                key = (order['name'], item.get('tongtool_sku'))
                probe = probe_index.get(key, [])
                component_probe = component_index.pop((order['name'], position), None)
                expected_inputs = {'erp_item_code': item.get('erp_item_code'),
                                   'warehouse_name': order.get('warehouse_name'),
                                   'tongtool_sku': item.get('tongtool_sku'),
                                   'quantity': item.get('quantity') or 0,
                                   'split_package_cost_factor': item.get('split_package_cost_factor') or 1}
                if component_probe is not None and component_probe.get('inputs') != expected_inputs:
                    raise ValueError('component probe input mismatch')
                items.append({'native_account': account, 'base_order_id': base,
                              'en_order_name': order['name'], 'platform_order_id': order['platform_order_id'],
                              'item_position': position, 'warehouse': order.get('warehouse_name'),
                              'selected': order['name'] in selected_names,
                              'role': 'child' if order['platform_order_id'] != base else 'parent_or_unsplit',
                              'persisted_item': item,
                              'current_component_probe': component_probe,
                              'current_probe_status': 'unambiguous' if len(probe) == 1 and item_keys[key] == 1 else 'missing_or_ambiguous',
                              'current_bom_raw_probe': probe[0] if len(probe) == 1 and item_keys[key] == 1 else None})
        groups.append({'native_account': account, 'base_order_id': base, 'currency': 'CNY',
                       'parent_order_names': [o['name'] for o in parents],
                       'selected_order_names': [o['name'] for o in selected],
                       'source_order_rows': len(group), 'source_item_rows': sum(len(o['order_items']) for o in group),
                       'selected_item_rows': len(selected_items),
                       'selected_quantity': text(total(selected_items, 'quantity')),
                       'quantity_semantics': 'raw_EN_quantity_not_assumed_shipped_units',
                       'components': components})
    if component_index:
        raise ValueError('component probe references unknown component')
    group_by_name = {o['name']: {'native_account': o['sale_account'],
                               'base_order_id': base_order_id(o['platform_order_id'])} for o in orders}
    evidence = [{**row, 'ledger_group_references': list({
                 (group_by_name[name]['native_account'], group_by_name[name]['base_order_id']): group_by_name[name]
                 for name in row.get('en_order_names', []) if name in group_by_name}.values()),
                 'cost_action': 'hold_refund_policy' if row.get('type') in
                 {'Refund', 'Refund_Retrocharge', 'Chargeback Refund'} else 'reference_only_no_row_cost_allocation'}
                for row in coverage or []]
    summary = {'input_order_rows': len(orders), 'output_groups': len(groups),
               'input_item_rows': sum(len(o['order_items']) for o in orders),
               'output_item_evidence_rows': len(items), 'selected_item_rows': sum(i['selected'] for i in items),
               'excluded_parent_item_rows': sum(not i['selected'] for i in items),
               'input_transaction_rows': len(coverage or []), 'output_transaction_rows': len(evidence),
               'component_status_counts': dict(status_counts),
               'product_hold_groups': sum(g['components']['product']['status'].startswith('hold_') for g in groups),
               'exact_component_probe_rows': sum(i['current_component_probe'] is not None for i in items),
               'selected_zero_product_groups': sum(g['components']['product']['selected_snapshot_amount'] is not None
                                                   and Decimal(g['components']['product']['selected_snapshot_amount']) == 0 for g in groups),
               'failed_rows': 0}
    assert summary['input_item_rows'] == summary['output_item_evidence_rows']
    return {'policy': {'snapshot_date': '2026-10-10', 'current_bom_date': '2026-10-09',
                       'historical_cost_verified': False, 'financial_cost_allocation': 'not_selected',
                       'amount_basis': 'persisted_field_sum_without_quantity_multiplication',
                       'tail_basis': 'selected_child_evidence_only_no_parent_fallback_no_financial_total'},
            'summary': summary, 'groups': groups, 'item_evidence': items, 'transaction_evidence': evidence}


def diagnose_cost_inputs(ledger, bom_rows, warehouse_configs):
    """Classify current calculation blockers and observed split input differences.

    Exact BOM aliases are suggestions only. They never fill missing ERP mappings,
    establish historical costs, or release a financial hold.
    """
    validate_input(bom_rows, {'item_fg', 'customer_item_code'}, 'BOM rows')
    validate_input(warehouse_configs, {'name'}, 'warehouse configs')
    aliases = defaultdict(set)
    for row in bom_rows:
        if normalize_sku(row['customer_item_code']) and row['item_fg']:
            aliases[normalize_sku(row['customer_item_code'])].add(row['item_fg'])
    config_names = {row['name'] for row in warehouse_configs}
    details, reasons = [], Counter()
    by_group = defaultdict(list)
    for record in ledger['item_evidence']:
        item, probe = record['persisted_item'], record.get('current_component_probe')
        status = probe.get('status') if probe else 'component_probe_missing'
        if status == 'no_item':
            if item.get('is_deliver_good') == 0:
                reason = 'non_delivery_missing_item_placeholder'
            elif item.get('is_deliver_good') == 1:
                reason = 'deliver_item_missing_erp_mapping'
            else:
                reason = 'missing_item_delivery_role_unknown'
        elif status == 'no_warehouse_config':
            reason = 'warehouse_name_missing' if not record.get('warehouse') else 'warehouse_config_missing'
        elif status == 'calculated':
            reason = 'current_calculation_available'
        else:
            reason = status or 'component_probe_status_missing'
        candidates = set()
        for field in ('tongtool_sku', 'platform_sku'):
            candidates.update(aliases.get(normalize_sku(item.get(field)), set()))
        detail = {'native_account': record['native_account'], 'base_order_id': record['base_order_id'],
                  'en_order_name': record['en_order_name'], 'item_position': record['item_position'],
                  'reason': reason, 'probe_status': status, 'delivery_flag': item.get('is_deliver_good'),
                  'warehouse': record.get('warehouse'), 'warehouse_config_exists': record.get('warehouse') in config_names,
                  'tongtool_sku_present': bool(item.get('tongtool_sku')),
                  'current_bom_exact_candidates': sorted(candidates),
                  'action': 'evidence_only' if status == 'calculated' else 'hold_no_mapping_write_or_cost_fill'}
        details.append(detail)
        reasons[reason] += 1
        by_group[(record['native_account'], record['base_order_id'])].append(record)
    conflicts = []
    for group in ledger['groups']:
        if group['components']['product']['status'] != 'hold_parent_children_difference':
            continue
        records = by_group[(group['native_account'], group['base_order_id'])]
        parent = [r for r in records if r['en_order_name'] in group['parent_order_names']]
        child = [r for r in records if r['en_order_name'] in group['selected_order_names']]
        def profile(rows):
            def calculation(r):
                return (r.get('current_component_probe') or {}).get('calculated') or {}
            current = [amount(calculation(r).get('sx_shipping_cost')) for r in rows]
            deliver_rows = [r for r in rows if r['persisted_item'].get('is_deliver_good') == 1]
            delivery_values = [amount(calculation(r).get('sx_shipping_cost')) for r in deliver_rows]
            return {'warehouses': sorted({r.get('warehouse') or '' for r in rows}),
                    'erp_items': sorted({r['persisted_item'].get('erp_item_code') or '' for r in rows}),
                    'item_rows': len(rows),
                    'non_delivery_rows': sum(r['persisted_item'].get('is_deliver_good') == 0 for r in rows),
                    'quantity_split_inputs': sorted([(r['persisted_item'].get('erp_item_code') or '',
                        r['persisted_item'].get('tongtool_sku') or '', str(r['persisted_item'].get('quantity')),
                        str(r['persisted_item'].get('split_package_cost_factor'))) for r in rows]),
                    'current_product_amount': text(sum(current, Decimal(0))) if current and all(v is not None for v in current) else None,
                    'current_product_missing_rows': sum(v is None for v in current),
                    'current_explicit_delivery_product_amount': text(sum(delivery_values, Decimal(0))) if delivery_values and all(v is not None for v in delivery_values) else None,
                    'delivery_role_unknown_rows': sum(r['persisted_item'].get('is_deliver_good') not in (0, 1) for r in rows),
                    'persisted_shipping_methods': sorted({r['persisted_item'].get('shipping_method') or '' for r in rows}),
                    'current_shipping_methods': sorted({calculation(r).get('shipping_method') or '' for r in rows})}
        a, b = profile(parent), profile(child)
        observed = [key + '_differ' for key in ('warehouses', 'erp_items', 'quantity_split_inputs',
                    'persisted_shipping_methods', 'current_shipping_methods') if a[key] != b[key]]
        relation = 'incomplete'
        if a['current_product_amount'] is not None and b['current_product_amount'] is not None:
            relation = 'equal' if Decimal(a['current_product_amount']) == Decimal(b['current_product_amount']) else 'different'
        deliver_relation = 'incomplete'
        if not a['delivery_role_unknown_rows'] and not b['delivery_role_unknown_rows'] and a['current_explicit_delivery_product_amount'] is not None and b['current_explicit_delivery_product_amount'] is not None:
            deliver_relation = 'equal' if Decimal(a['current_explicit_delivery_product_amount']) == Decimal(b['current_explicit_delivery_product_amount']) else 'different'
        conflicts.append({'native_account': group['native_account'], 'base_order_id': group['base_order_id'],
                          'parent': a, 'children': b, 'observed_input_differences': observed,
                          'current_calculation_relation': relation, 'financial_status': 'hold_unchanged',
                          'current_explicit_delivery_calculation_relation': deliver_relation,
                          'interpretation': 'Observed input changes are not proof of actual goods movement or historical valuation.'})
    success = reasons['current_calculation_available']
    skipped = reasons['non_delivery_missing_item_placeholder']
    summary = {'input_component_rows': len(ledger['item_evidence']), 'reported_component_rows': len(details),
               'success': success, 'skipped_non_delivery_placeholders': skipped,
               'held_or_unclassified': len(details) - success - skipped, 'failed': 0,
               'reason_counts': dict(reasons), 'product_conflict_groups': len(conflicts),
               'conflict_current_calculation_relations': dict(Counter(r['current_calculation_relation'] for r in conflicts)),
               'conflict_current_explicit_delivery_relations': dict(Counter(r['current_explicit_delivery_calculation_relation'] for r in conflicts)),
               'conflict_observed_difference_counts': dict(Counter(k for r in conflicts for k in r['observed_input_differences']))}
    assert summary['input_component_rows'] == summary['reported_component_rows']
    return {'summary': summary, 'details': details, 'product_conflicts': conflicts,
            'mapping_policy': 'Exact current BOM customer alias candidates only; no SKU suffix removal, sibling borrowing, write, or historical claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cost-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--diagnose-inputs', action='store_true', help='Classify current probe inputs using private BOM/config snapshots')
    args = parser.parse_args()
    out = private_output(args.out)
    names = ['en_orders', 'current_cost_probe_details', 'cost_coverage_details']
    source_paths = [args.cost_root / (name + '.json') for name in names]
    sources = [json.loads(path.read_text(encoding='utf-8')) for path in source_paths]
    component_path = args.cost_root / 'current_cost_probe_components.json'
    components = json.loads(component_path.read_text(encoding='utf-8')) if component_path.exists() else None
    result = build_ledger(*sources, component_probes=components,
                          component_source_sha256=hashlib.sha256(source_paths[0].read_bytes()).hexdigest())
    if component_path.exists():
        source_paths.append(component_path)
    result['source_manifest'] = [{'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                                 for path in source_paths]
    out.mkdir(parents=True, exist_ok=True)
    (out / 'cost_technical_ledger.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.diagnose_inputs:
        bom_path, config_path = args.cost_root / 'current_bom.json.gz', args.cost_root / 'warehouse_configs.json'
        bom = json.loads(gzip.decompress(bom_path.read_bytes()))
        diagnosis = diagnose_cost_inputs(result, bom['result'], json.loads(config_path.read_text(encoding='utf-8')))
        diagnosis['source_manifest'] = [*result['source_manifest'], *[
            {'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (bom_path, config_path)]]
        (out / 'cost_input_diagnosis.json').write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(diagnosis['summary'], ensure_ascii=False))
    print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
