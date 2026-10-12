from sellfox_settlement.account_cost_bridge import build_bridge

def tx(file='a.csv', oid='1', sku='S'):
 return {'source_file':file,'order_id':oid,'sku':sku,'type':'Order'}
def order(account='Native', oid='1', sku='S'):
 return {'platform_order_id':oid,'sale_account':account,'order_items':[{'platform_sku':sku}]}
def report(account='Native'):
 return {'files':[{'file':'a.csv','account_candidate':account,'match':{'status':'matched'}}]}
def test_unique_corroboration():
 r=build_bridge([tx()],report(),[order()],[])
 assert r['account_by_file']=={'a.csv':'Native'}
def test_no_evidence_no_mapping():
 assert build_bridge([tx()],report(),[],[])['account_by_file']=={}
def test_conflicting_native_account_is_held():
 r=build_bridge([tx()],report(),[order('Other')],[])
 assert r['account_by_file']=={}
 assert r['files'][0]['status']=='native_identifier_conflict'
def test_same_order_across_accounts_not_global():
 r=build_bridge([tx()],report(),[order(),order('Other')],[])
 assert r['account_by_file']=={}
 assert r['files'][0]['status']=='ambiguous_native_evidence'
def test_unicode_sku_and_upstream():
 r=build_bridge([tx(sku='A\u00a0B')],report(),[],[{'orderId':'1','account':'Native','orderItem':[{'sku':'A B'}]}])
 assert r['account_by_file']=={'a.csv':'Native'}
def test_unknown_standard_retained():
 r=build_bridge([tx()],report(None),[order()],[])
 assert r['files'][0]['status']=='standard_account_unmapped'
 assert len(r['files'])==1

def test_duplicate_file_records_fail_closed():
 import pytest
 data=report(); data['files'].append({'file':'other/a.csv','account_candidate':'Other','match':{'status':'matched'}})
 with pytest.raises(ValueError,match='duplicate account-report filename'):
  build_bridge([tx()],data,[order()],[])

def test_no_native_evidence_rows_retained_and_count_conserved():
 r=build_bridge([tx()],report(),[],[])
 assert r['summary']['reported_rows']==r['summary']['input_rows']==1
 assert r['files'][0]['no_evidence'][0]['order_id']=='1'
 assert r['files'][0]['no_evidence'][0]['native_accounts']==[]
