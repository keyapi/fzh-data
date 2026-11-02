"""Offline artifact export from EN read-only inventory mirrors, not a sync trigger."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests
from dotenv import dotenv_values

from supply_netting.en_inventory_snapshot import read_pages,stock_frame,validate_run


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get_run(session,base,doctype,job):
    response=session.get(base.rstrip('/')+'/api/resource/'+requests.utils.quote(doctype,safe=''),
                         params={'fields':json.dumps(['*']),
                                 'filters':json.dumps([['job','=',job]]),
                                 'order_by':'snapshot_at desc','limit_page_length':1},timeout=30)
    if response.status_code!=200:
        raise RuntimeError(f'{doctype}: HTTP {response.status_code}')
    rows=response.json().get('data',[])
    if len(rows)!=1:
        raise ValueError('no snapshot run found: '+doctype)
    validate_run(rows[0],job)
    return rows[0]


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',default='https://erpnext.vilavi.cn')
    ap.add_argument('--env-file',default='D:/Work/赛狐/Cursor/EN_API/.env')
    ap.add_argument('--out',required=True)
    args=ap.parse_args(argv)
    out=Path(args.out)
    if out.exists():
        raise ValueError('immutable output already exists')
    env=dotenv_values(args.env_file)
    key=env.get('ERP_API_KEY') or env.get('PROD_ERP_API_KEY')
    secret=env.get('ERP_API_SECRET') or env.get('PROD_ERP_API_SECRET')
    if not key or not secret:
        raise ValueError('EN read credentials unavailable')
    session=requests.Session()
    session.headers['Authorization']='token '+key+':'+secret
    stock_run=get_run(session,args.base,'Tongtool Stock Run','stock_snapshot')
    cg_run=get_run(session,args.base,'Wayfair CG Stock Run','snapshot')
    stock_rows=read_pages(session,args.base,'Tongtool Stock Latest',['*'],[['run_id','=',stock_run['run_id']]])
    cg_rows=read_pages(session,args.base,'Wayfair CG Stock Latest',['*'],[['run_id','=',cg_run['run_id']]])
    stock=stock_frame(stock_rows,stock_run)
    if len(cg_rows)!=int(cg_run['row_count']):
        raise ValueError('CG source run row count mismatch')
    cg=pd.DataFrame(cg_rows)
    required={'name','stock_key','warehouse_id','sku','snapshot_at','run_id','available','available_missing','stale'}
    if required-set(cg) or cg['stock_key'].duplicated().any():
        raise ValueError('CG required columns/physical key mismatch')
    if set(cg['run_id'].astype(str))!={str(cg_run['run_id'])}:
        raise ValueError('CG mixed run identities')
    if pd.to_datetime(cg['snapshot_at'],errors='coerce').isna().any():
        raise ValueError('CG unknown observation time')
    # Verify the selected run metadata has not changed while pages were read.
    for doctype,job,prior in [('Tongtool Stock Run','stock_snapshot',stock_run),('Wayfair CG Stock Run','snapshot',cg_run)]:
        current=get_run(session,args.base,doctype,job)
        if any(current.get(k)!=prior.get(k) for k in ['run_id','snapshot_at','complete','row_count']):
            raise ValueError('source snapshot changed during export')
    report={'observed_at':datetime.now(timezone.utc).isoformat(),
            'stock':{'rows':len(stock),'warehouses':int(stock.warehouse_id.nunique()),
                     'snapshot_at':stock_run['snapshot_at'],'run_id':stock_run['run_id']},
            'cg':{'rows':len(cg),'aggregate_rows':int((cg.warehouse_id=='CG').sum()),
                  'available_unknown':int(pd.to_numeric(cg.available_missing,errors='coerce').fillna(1).sum()),
                  'stale':int(pd.to_numeric(cg.stale,errors='coerce').fillna(1).sum()),
                  'snapshot_at':cg_run['snapshot_at'],'run_id':cg_run['run_id']},
            'source_timezone':'Asia/Shanghai','read_only':True,'source_run_complete':True}
    out.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.en-inventory-',dir=out.parent))
    stock.to_parquet(stage/'en_stock.parquet',index=False)
    cg.to_parquet(stage/'cg_stock.parquet',index=False)
    if len(pd.read_parquet(stage/'en_stock.parquet'))!=len(stock) or len(pd.read_parquet(stage/'cg_stock.parquet'))!=len(cg):
        raise ValueError('Parquet readback row mismatch')
    (stage/'source_runs.json').write_text(json.dumps({'stock':stock_run,'cg':cg_run},ensure_ascii=False,indent=2),encoding='utf-8')
    (stage/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={'schema_version':'en-inventory-snapshot/v1','report':report,
              'code':{str(p):sha(p) for p in [Path(__file__),Path(__file__).parents[1]/'supply_netting/en_inventory_snapshot.py']},
              'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in stage.iterdir()}}
    (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    stage.rename(out)
    print(json.dumps({'out':str(out),**report},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
