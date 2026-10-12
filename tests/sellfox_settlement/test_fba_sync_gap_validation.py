import pytest
from sellfox_settlement.fba_sync_gap_validation import build_gap_report

def upstream():
 return [{'orderId':'one','account':'shopUS','purchaseDate':123,'currency':'USD','salesChannel':'Amazon.com','orderItem':[{'sku':'s','goodsSku':'g','quantityPurchased':1}]}]
def gaps():
 return [{'order_id':'one','account':'shopUS','status':'order_unmatched'}]
def test_stripped_snapshot_is_held_never_imported():
 r=build_gap_report(gaps(),upstream(),[],{'shopUS'})
 assert r['summary']['missing_orders']==1
 assert r['candidates'][0]['write_action']=='none'
 assert r['candidates'][0]['full_sync_status']=='hold_incomplete_snapshot'
 assert r['candidates'][0]['identity_status']=='complete'
def test_missing_upstream_kept():
 r=build_gap_report(gaps(),[],[],set())
 assert len(r['candidates'])==1
 assert r['candidates'][0]['identity_status']=='hold_missing_upstream'
def test_duplicate_gap_fail_closed():
 with pytest.raises(ValueError,match='duplicate'):
  build_gap_report(gaps()*2,upstream(),[],set())
def test_account_blind_source_collision_is_held():
 r=build_gap_report(gaps(),upstream(),[{'platform_order_id':'one','sale_account':'other'}],{'shopUS'})
 assert r['candidates'][0]['source_key_status']=='hold_account_blind_order_id_collision'

def test_zero_quantity_held_without_defaulting_to_one():
 data=upstream(); data[0]['orderItem'][0]['quantityPurchased']=0
 r=build_gap_report(gaps(),data,[],{'shopUS'})
 assert r['candidates'][0]['identity_status']=='hold_identity_fields'
 assert r['candidates'][0]['items'][0]['quantity']==0
 assert r['summary']['candidate_items']==1

@pytest.mark.parametrize('qty',['NaN',-1,'1.5'])
def test_invalid_quantities_never_complete(qty):
 data=upstream();data[0]['orderItem'][0]['quantityPurchased']=qty
 assert build_gap_report(gaps(),data,[],{'shopUS'})['candidates'][0]['identity_status']=='hold_identity_fields'
