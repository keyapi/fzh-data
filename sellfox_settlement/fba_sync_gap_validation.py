"""Dry-run FBA sync gap evidence; never constructs executable import payloads."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

ORDER_SYNC_FIELDS = {'orderId','account','purchaseDate','paymentsDate','currency','salesChannel',
                     'totalItemPrice','totalShippingPrice','orderItem'}
ITEM_SYNC_FIELDS = {'sku','goodsSku','quantityPurchased','itemPrice','itemTax','shippingTax',
                    'orderFinancial'}


def valid_quantity(value):
    try:
        quantity = Decimal(str(value))
        return quantity.is_finite() and quantity > 0 and quantity == quantity.to_integral_value()
    except (InvalidOperation, ValueError):
        return False


def build_gap_report(scope_details, upstream, en_orders, channel_accounts):
    missing = [r for r in scope_details if r['status'] == 'order_unmatched']
    keys = [(r['account'],r['order_id']) for r in missing]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate missing account/order key')
    index = defaultdict(list)
    for row in upstream:
        index[(row.get('account'),row.get('orderId'))].append(row)
    existing = defaultdict(set)
    for row in en_orders:
        existing[row.get('platform_order_id')].add(row.get('sale_account'))
    candidates = []
    for gap in missing:
        account, oid = gap['account'], gap['order_id']
        rows = index.get((account,oid),[])
        entry = {'native_account':account,'order_id':oid,'write_action':'none',
                 'account_configuration_status':'present_current_snapshot' if account in channel_accounts else 'not_in_current_snapshot',
                 'source_key_status':'hold_account_blind_order_id_collision' if existing.get(oid,set())-{account} else 'no_observed_collision',
                 'cause_status':'unproven_requires_sync_error_or_scheduler_logs'}
        if len(rows) != 1:
            entry.update(identity_status='hold_missing_upstream' if not rows else 'hold_duplicate_upstream',
                         full_sync_status='hold_incomplete_snapshot',items=[])
        else:
            row = rows[0]
            items = row.get('orderItem') or []
            missing_identity = [k for k in ('orderId','account','purchaseDate','currency','salesChannel') if not row.get(k)]
            item_records = []
            for item in items:
                identity_missing = [k for k in ('sku','goodsSku','quantityPurchased') if not item.get(k)]
                if not valid_quantity(item.get('quantityPurchased')) and 'quantityPurchased' not in identity_missing:
                    identity_missing.append('quantityPurchased')
                item_records.append({'sku':item.get('sku'),'goods_sku':item.get('goodsSku'),'quantity':item.get('quantityPurchased'),
                                     'identity_missing':identity_missing,'sync_missing_fields':sorted(ITEM_SYNC_FIELDS-item.keys()),
                                     'optional_missing_fields':sorted({'productWeight','goodsWeight'}-item.keys())})
            full_missing = sorted(ORDER_SYNC_FIELDS-row.keys())
            entry.update(purchase_date=row.get('purchaseDate'),currency=row.get('currency'),sales_channel=row.get('salesChannel'),
                         identity_missing=missing_identity,items=item_records,sync_missing_fields=full_missing,
                         identity_status='complete' if items and not missing_identity and not any(i['identity_missing'] for i in item_records) else 'hold_identity_fields',
                         full_sync_status='snapshot_fields_present_not_import_validated' if items and not full_missing and not any(i['sync_missing_fields'] for i in item_records) else 'hold_incomplete_snapshot')
        candidates.append(entry)
    return {'summary':{'scope_input_orders':len(scope_details),'missing_orders':len(missing),'candidate_orders':len(candidates),
                       'candidate_items':sum(len(c['items']) for c in candidates),
                       'identity_statuses':dict(Counter(c['identity_status'] for c in candidates)),
                       'full_sync_statuses':dict(Counter(c['full_sync_status'] for c in candidates)),
                       'account_configuration_statuses':dict(Counter(c['account_configuration_status'] for c in candidates)),
                       'source_key_statuses':dict(Counter(c['source_key_status'] for c in candidates)),
                       'confirmed_missing_causes':0,'imported_orders':0},'candidates':candidates,
            'policy':'No database/API writes; no fabricated missing monetary fields, no finance decision, no scheduler cause inferred from absence.'}
