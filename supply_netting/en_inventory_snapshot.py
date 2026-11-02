"""Read completed EN inventory mirror runs; preserve their source timestamps."""
from __future__ import annotations

import json
from urllib.parse import quote

import numpy as np
import pandas as pd


def read_pages(session, base, doctype, fields, filters, page_size=500, max_pages=100):
    rows, seen = [], set()
    for page in range(max_pages):
        response = session.get(base.rstrip('/')+'/api/resource/'+quote(doctype,safe=''),
                               params={'fields':json.dumps(fields),'filters':json.dumps(filters),
                                       'order_by':'name asc','limit_start':page*page_size,
                                       'limit_page_length':page_size},timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f'{doctype} page {page}: HTTP {response.status_code}')
        batch = response.json().get('data')
        if not isinstance(batch,list):
            raise ValueError('missing data container')
        for row in batch:
            name = row.get('name')
            if not name or name in seen:
                raise ValueError('missing or duplicate record name during pagination')
            seen.add(name)
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
    raise ValueError('pagination not exhausted')


def validate_run(run, job):
    if run.get('job') != job or run.get('status') != 'Success' or run.get('complete') not in (1,True):
        raise ValueError('source run is not a completed successful inventory snapshot')
    if not run.get('run_id') or not run.get('snapshot_at') or not run.get('snapshot_date'):
        raise ValueError('source run lacks identity or observation time')
    if int(run.get('row_count',-1)) < 0:
        raise ValueError('source run lacks row count')


def stock_frame(rows, run):
    if len(rows) != int(run['row_count']):
        raise ValueError('source run row count does not match exported mirror')
    frame = pd.DataFrame(rows)
    fields = ['stock_key','warehouse_id','warehouse','sku','available','intransit',
              'waiting_shipment','defects','snapshot_at','run_id','schema_version']
    if set(fields)-set(frame):
        raise ValueError('stock snapshot missing required columns')
    if frame['stock_key'].duplicated().any() or frame[['warehouse_id','sku']].duplicated().any():
        raise ValueError('duplicate physical stock key')
    if set(frame['run_id'].astype(str)) != {str(run['run_id'])}:
        raise ValueError('mixed stock run identities')
    parsed = pd.to_datetime(frame['snapshot_at'],errors='coerce')
    if parsed.isna().any() or set(parsed.dt.strftime('%Y-%m-%d')) != {run['snapshot_date']}:
        raise ValueError('mixed or unknown source snapshot dates')
    for column in ['available','intransit','waiting_shipment','defects']:
        frame[column] = pd.to_numeric(frame[column],errors='coerce')
        if not np.isfinite(frame[column]).all():
            raise ValueError('unknown/nonfinite source quantity: '+column)
    result = frame.rename(columns={'warehouse':'warehouse_name'}).copy()
    result['snapshot_date'] = run['snapshot_date']
    result['source'] = 'en_tongtool_stock_latest'
    result['source_timezone'] = 'Asia/Shanghai'
    if 'avg_cost' not in result:
        result['avg_cost'] = np.nan
    return result
