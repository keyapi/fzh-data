import pandas as pd
import pytest

from supply_netting.en_inventory_snapshot import read_pages, stock_frame, validate_run


class Response:
    status_code = 200
    def __init__(self, rows): self.rows=rows
    def json(self): return {'data':self.rows}


class Session:
    def __init__(self,pages): self.pages=iter(pages)
    def get(self,*args,**kwargs): return Response(next(self.pages))


def test_pagination_duplicate_names_fail_instead_of_silent_dedup():
    session=Session([[{'name':'A'},{'name':'B'}],[{'name':'B'}]])
    with pytest.raises(ValueError,match='duplicate'):
        read_pages(session,'https://example.invalid','Stock',[],[],page_size=2)


def test_non_snapshot_or_incomplete_run_is_not_accepted():
    with pytest.raises(ValueError):
        validate_run({'job':'stock_change','complete':1,'status':'Success'},'stock_snapshot')
    with pytest.raises(ValueError):
        validate_run({'job':'stock_snapshot','complete':0,'status':'Success'},'stock_snapshot')


def test_stock_frame_preserves_source_observation_time_and_unknown_cost():
    row=dict(stock_key='W:S',warehouse_id='W',warehouse='warehouse',sku='S',
             available=2,intransit=3,waiting_shipment=4,defects=0,avg_cost=None,
             snapshot_at='2026-11-02 05:18:00',run_id='R',schema_version=1)
    data=stock_frame([row],{'run_id':'R','row_count':1,'snapshot_date':'2026-11-02'})
    assert data.loc[0,'snapshot_at']==row['snapshot_at']
    assert data.loc[0,'snapshot_date']=='2026-11-02'
    assert pd.isna(data.loc[0,'avg_cost'])
    assert data.loc[0,'warehouse_name']=='warehouse'


def test_incomplete_count_and_unknown_quantity_do_not_publish_as_complete():
    with pytest.raises(ValueError,match='row count'):
        stock_frame([],{'row_count':1,'run_id':'R'})
    row=dict(stock_key='W:S',warehouse_id='W',warehouse='warehouse',sku='S',
             available=None,intransit=0,waiting_shipment=0,defects=0,
             snapshot_at='2026-11-02 05:18:00',run_id='R',schema_version=1)
    with pytest.raises(ValueError,match='quantity'):
        stock_frame([row],{'run_id':'R','row_count':1,'snapshot_date':'2026-11-02'})
