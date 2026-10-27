"""Regression cases for reviewed supply and receipt safety failures."""
from datetime import datetime, timezone
from dataclasses import replace
from decimal import Decimal
from supply_chain_visibility.receipt_bridge import PoOpenRow, TransitRow, build_receipt_bridge
from supply_chain_visibility.receipt_reconciliation import ReceiptEvent, SnapshotWindow
from supply_chain_visibility.supply_integration import build_supply_integration
from supply_chain_visibility.receipt_coverage import build_coverage_report
from tongtool_api.receipt_collector import collect_receipts

def po(**changes):
    return replace(PoOpenRow('PO-A','S','WH',Decimal(10),'Nos',as_of=None,status='4'),**changes)

def receipt():
    return ReceiptEvent('R','1','PO-A','S','WH','Nos',2,'2026-10-26T09:00:00+08:00')

def response(rows,args):
    return {'code':200,'datas':{'array':rows,'pageNo':args['pageNo'],'pageSize':args['pageSize']}}

def raw():
    return {'purchaseOrderCode':'PO-A','goodsDetailId':'G','sku':'S','warehouseId':'W','warehouseName':'WH','warehousingNum':2,'warehousingDate':'2026-10-07T09:00:00+08:00'}

def test_unverified_po_status4_is_not_lower_bound():
    result=build_supply_integration([po()],[],[],[])
    assert result['summary']['b_min_by_uom']=={}

def test_unequal_quantity_does_not_prove_distinct_batch():
    result=build_supply_integration([po()],[],[TransitRow('S','WH',Decimal(7),'Nos')],[])
    assert 'distinct' not in result['summary']['by_overlap_status']

def test_unknown_units_are_not_summed_across_skus():
    result=build_supply_integration([po(sku='A',uom=None),po(sku='B',uom=None,qty=Decimal(7))],[],[],[])
    assert '(unknown)' not in result['summary']['b_max_by_uom']

def test_receipt_uses_its_own_po_asof():
    rows=build_receipt_bridge([po(as_of='2026-10-26T06:00:00+08:00'),po(po_code='PO-B',as_of='2026-10-26T10:00:00+08:00')],[receipt()],[])
    assert sum(r['after_po_as_of_rows'] for r in rows)==1

def test_missing_inventory_is_not_known_zero():
    row=build_receipt_bridge([],[receipt()],[])[0]
    assert row['inventory_qty'] is None

def test_later_window_extra_same_key_is_not_lost():
    calls=[]
    def caller(tool,args):
        calls.append(args)
        return response([raw()] if len(calls)==1 else [raw(),raw()],args)
    result=collect_receipts(caller,'2026-10-01','2026-10-13',sleep=lambda _:None)
    assert result.unique_count==2

def test_actual_collection_bounds_reach_reconciliation():
    def caller(tool,args):
        return response([dict(raw(),receiptId='R',lineId='1',uom='Nos',warehousingDate='2026-10-20T09:00:00+08:00')],args)
    result=collect_receipts(caller,'2026-10-01','2026-10-01',sleep=lambda _:None)
    report=build_coverage_report(result,run_window=SnapshotWindow('2026-10-01T05:17:00+08:00','2026-10-01T05:31:00+08:00'))
    assert report['reconciliation']['not_collected_count']==1

def test_mutable_current_window_can_refresh(tmp_path):
    clock=lambda: datetime(2026,10,26,12,tzinfo=timezone.utc)
    calls=[]
    def caller(tool,args):
        calls.append(args)
        return response([] if len(calls)==1 else [raw()],args)
    collect_receipts(caller,'2026-10-26','2026-10-26',cache_dir=tmp_path, cache_namespace="synthetic",now=clock,sleep=lambda _:None)
    result=collect_receipts(caller,'2026-10-26','2026-10-26',cache_dir=tmp_path, cache_namespace="synthetic",now=clock,sleep=lambda _:None)
    assert result.unique_count==1


from supply_chain_visibility.supply_row import SourceProof, SupplyRow
from supply_chain_visibility.receipt_bridge import InventoryRow
import pytest

ASOF = '2026-10-26T05:17:00+08:00'
END = '2026-10-26T05:31:00+08:00'

def proof(key, **changes):
    return replace(SourceProof(source_key=key, uom_proven=True, identity_proven=True,
                               complete=True, warehouse_confidence='confirmed', role='finished'), **changes)

def proven_po(**changes):
    return replace(po(as_of=ASOF, status='3', status_semantics='open', proof=proof('po')), **changes)


def test_proven_independent_batches_can_enter_lower_bound():
    p=proven_po(proof=proof('po',batch_key='B1',batch_proven=True))
    t=TransitRow('S','WH',Decimal(7),'Nos',ASOF,proof=proof('transit',batch_key='B2',batch_proven=True))
    result=build_supply_integration([p],[],[t],[])
    assert result['summary']['b_min_by_uom']=={'Nos':'17'}
    assert result['summary']['by_overlap_status']=={'distinct':2}
    assert result['summary']['committable'] is False


def test_same_proven_batch_keeps_one_side():
    p=proven_po(proof=proof('po',batch_key='B1',batch_proven=True))
    t=TransitRow('S','WH',Decimal(10),'Nos',ASOF,proof=proof('transit',batch_key='B1',batch_proven=True))
    result=build_supply_integration([p],[],[t],[])
    assert result['summary']['b_min_by_uom']=={'Nos':'10'}
    assert result['summary']['by_overlap_status']=={'proven':2}

    assert result['summary']['b_max_by_uom']=={'Nos':'10'}


@pytest.mark.parametrize('change',[
    {'complete':False},{'identity_proven':False},{'source_key':None},
    {'uom_proven':False},{'warehouse_confidence':'unmapped'},{'scope':'external_fba'},
])
def test_unproven_source_cannot_enter_either_bound(change):
    result=build_supply_integration([proven_po(proof=proof('po',**change))],[],[],[])
    assert result['summary']['b_min_by_uom']=={}
    assert result['summary']['b_max_by_uom']=={}


def test_status4_is_upper_only_even_with_other_proofs():
    result=build_supply_integration([proven_po(status='4')],[],[],[])
    assert result['summary']['b_min_by_uom']=={}
    assert result['summary']['b_max_by_uom']=={'Nos':'10'}


@pytest.mark.parametrize('status',['closed','cancelled'])
def test_proven_closed_po_is_not_supply(status):
    result=build_supply_integration([proven_po(status_semantics=status)],[],[],[])
    assert result['summary']['b_max_by_uom']=={}


def test_exact_source_replay_is_counted_once_and_conflicts_are_quarantined():
    p=proven_po()
    result=build_supply_integration([p,p],[],[],[])
    assert result['summary']['b_min_by_uom']=={'Nos':'10'}
    assert result['summary']['by_exclusion_reason']['exact_replay']==1
    result=build_supply_integration([p,replace(p,qty=Decimal(11))],[],[],[])
    assert result['summary']['b_min_by_uom']=={}
    assert result['summary']['b_max_by_uom']=={}


def test_multiple_inventory_versions_cannot_be_added():
    stock=InventoryRow('S','WH',5,'Nos',ASOF,ASOF,END,proof('stock'))
    other=replace(stock,proof=proof('other-stock'))
    result=build_supply_integration([], [stock,other],[],[])
    assert result['summary']['b_max_by_uom']=={}


def test_mixed_source_instants_are_not_a_lower_bound():
    p=proven_po(proof=proof('po',batch_key='B1',batch_proven=True))
    t=TransitRow('S','WH',Decimal(7),'Nos','2026-10-26T09:00:00+08:00',proof=proof('transit',batch_key='B2',batch_proven=True))
    result=build_supply_integration([p],[],[t],[])
    assert result['summary']['b_min_by_uom']=={}


def test_invalid_extra_row_stops_publication():
    bad=SupplyRow('S','WH','on_hand','inventory_snapshot',Decimal('-1'),'known','Nos',True,
                  None,None,'unknown','unverified','unproven')
    with pytest.raises(ValueError,match='finite nonnegative'):
        build_supply_integration([],[],[],[],extra_rows=[bad])


def test_receipt_bridge_does_not_sum_unproven_receipt_quantity():
    row=build_receipt_bridge([], [receipt(),replace(receipt(),line_id='2')],[])[0]
    assert row['receipt_qty'] is None


def test_empty_collection_is_not_unlimited_coverage():
    row=build_receipt_bridge([], [receipt()],[],collection_windows=[])[0]
    assert row['not_collected_rows']==1
    result=build_supply_integration([],[],[],[receipt()],collection_windows=[])
    assert result['rows'][0]['not_collected'] is True


def test_conflicting_po_versions_do_not_enter_upper_bound():
    p=proven_po()
    second=replace(p,as_of='2026-10-26T09:00:00+08:00',proof=proof('po-later'))
    result=build_supply_integration([p,second],[],[],[])
    assert result['summary']['b_max_by_uom']=={}
    assert sum(result['summary']['partition'].values())==result['summary']['input_rows']==2


def test_batch_proof_is_shared_by_bridge_and_supply_gates():
    p=proven_po(proof=proof('po',batch_key='A',batch_proven=True))
    t=TransitRow('S','WH',Decimal(7),'Nos',ASOF,proof=proof('transit',batch_key='B',batch_proven=True))
    result=build_supply_integration([p],[],[t],[])
    assert result['bridge_rows'][0]['overlap_status']=='distinct'
    assert {r['overlap_status'] for r in result['rows']}=={'distinct'}


def test_receipt_identity_conflict_across_skus_is_quarantined():
    first=replace(receipt(),uom_proven=True,quantity_semantics_proven=True)
    second=replace(first,sku='OTHER')
    rows=build_receipt_bridge([], [first,second],[])
    assert sum(r['receipt_conflicts'] for r in rows)==2
    assert all(r['receipt_qty'] is None for r in rows)


def test_missing_receipt_keys_are_preserved_as_unknown_evidence():
    e=replace(receipt(),sku=None,warehouse=None)
    result=build_supply_integration([],[],[],[e])
    assert len(result['rows'])==1
    assert result['summary']['b_max_by_uom']=={}


def test_invalid_snapshot_window_is_not_replaced_by_point_asof():
    stock=InventoryRow('S','WH',5,'Nos',ASOF,'invalid',END)
    row=build_receipt_bridge([], [receipt()],[stock])[0]
    assert row['missing_snapshot_window_rows']==1
    assert row['after_snapshot_rows']==0


def test_bridge_exposes_actual_stale_snapshot_gap_and_reverse_overlap():
    stock=InventoryRow('S','WH',5,'Nos',ASOF,ASOF,END)
    current=proven_po(as_of='2026-10-26T10:00:00+08:00')
    row=build_receipt_bridge([current],[receipt()],[stock])[0]
    assert row['flags']['receipt_gap_risk']
    assert row['gap_candidate_qty'] is None
    late_stock=replace(stock,as_of='2026-10-26T10:00:00+08:00',
                       window_start='2026-10-26T10:00:00+08:00',window_end='2026-10-26T10:14:00+08:00')
    row=build_receipt_bridge([proven_po()],[receipt()],[late_stock])[0]
    assert row['flags']['receipt_overlap_risk']


def test_proven_batch_unequal_quantities_require_allocation_evidence():
    p=proven_po(proof=proof('po',batch_key='B1',batch_proven=True))
    t=TransitRow('S','WH',Decimal(7),'Nos',ASOF,proof=proof('transit',batch_key='B1',batch_proven=True))
    result=build_supply_integration([p],[],[t],[])
    assert result['summary']['b_min_by_uom']=={}
    assert result['summary']['b_max_by_uom']=={}
    assert result['summary']['by_overlap_status']=={'batch_quantity_conflict':2}


def test_exact_replay_does_not_change_proven_batch_overlap():
    p=proven_po(proof=proof('po',batch_key='B1',batch_proven=True))
    t=TransitRow('S','WH',Decimal(10),'Nos',ASOF,proof=proof('transit',batch_key='B1',batch_proven=True))
    result=build_supply_integration([p,p],[],[t],[])
    assert result['summary']['b_min_by_uom']=={'Nos':'10'}
    assert result['summary']['b_max_by_uom']=={'Nos':'10'}
