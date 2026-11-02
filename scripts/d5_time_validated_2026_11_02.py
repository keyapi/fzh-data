"""Chronological D5 repair. Offline inputs, immutable output run, no service promise."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from supply_netting.temporal_demand import (
    forecast_cache, choose_model, demand_quantiles, calendar_total,
    fast_ets, next_month, nonoverlapping_starts, calibration_pool,
)
from supply_netting.demand_input import canonical_order_dates

VERSION = 'D5-v6.2-event-time-ordered-2026-11-02'
KEY = ['product_id', 'pool', 'physical_form', 'canonical_uom']
DATA = Path('D:/Work/fzh-order-store')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path):
    spec = importlib.util.spec_from_file_location('d3_repaired_reference', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_history(args, models):
    """Reuse the frozen D3 identity bridge; do not consume its final model choices."""
    classes = pd.read_excel(args.d3b, sheet_name='3_分类')
    if classes.duplicated(KEY).any():
        raise ValueError('duplicate target identity')
    keys = sorted(set(map(tuple, classes[KEY].astype(str).values)))
    bridge = pd.read_excel(args.d3b, sheet_name='1_映射桥')
    bridge = bridge[bridge['status'] == '唯一'][['sku_tongtool', 'product']]
    if bridge['sku_tongtool'].duplicated().any():
        raise ValueError('ambiguous raw SKU bridge')
    a = pd.read_excel(args.a_final, sheet_name='活跃宇宙')
    roles = dict(zip(a['EN物料'].astype(str), a['角色'].astype(str)))
    owners = pd.read_excel(args.b10, sheet_name='主表')
    owners = owners[owners['地区'].astype(str) == 'US']
    owner_sets = owners.groupby('产品键')['美国责任方'].agg(
        lambda s: sorted(set(str(x) for x in s.dropna() if str(x).strip())))
    owner_map = {str(k): values[0] for k, values in owner_sets.items() if len(values) == 1}
    orders = pd.read_parquet(args.orders)
    required = {'sku_tongtool', 'qty', 'month', 'sale_date', 'warehouse'}
    if required-set(orders):
        raise ValueError('missing order columns: '+str(sorted(required-set(orders))))
    orders['sku_tongtool'] = orders['sku_tongtool'].astype(str)
    orders = orders.merge(bridge, on='sku_tongtool', how='left', validate='many_to_one')
    orders['qty'] = pd.to_numeric(orders['qty'], errors='raise')
    if orders['qty'].isna().any() or not np.isfinite(orders['qty']).all():
        raise ValueError('unknown/nonfinite order quantity')
    orders, event_date_report = canonical_order_dates(orders)
    orders['date'] = orders['demand_event_date']
    orders['pool'] = orders['warehouse'].map(models.POOL_OF_WAREHOUSE).fillna('其他')
    cg = orders['warehouse'].astype(str).str.startswith('WayfairCG')
    orders.loc[cg, 'pool'] = orders.loc[cg, 'product'].map(owner_map).fillna('其他')
    by_product = defaultdict(list)
    for key in keys:
        by_product[key[0]].append(key)
    fixed = []
    for row in orders.itertuples(index=False):
        product = '' if pd.isna(row.product) else str(row.product)
        form = models.form_of(product, roles.get(product, '')) if product else ''
        uom = '套' if form == '套件' else '个'
        key = (product, row.pool, form, uom)
        if key not in by_product.get(product, []):
            candidates = [k for k in by_product.get(product, []) if k[1] == row.pool and k[3] == uom]
            if len(candidates) == 1:
                key = candidates[0]
        fixed.append(key)
    key_set = set(keys)
    orders['key'] = fixed
    orders['bucket'] = [
        'date_unknown' if pd.isna(dt) else
        'future_order_excluded' if dt >= date.fromisoformat(args.as_of) else
        'mapped' if key in key_set else 'no_target_or_identity'
        for key, dt in zip(fixed, orders['date'])]
    report = orders.groupby('bucket', dropna=False).agg(rows=('qty', 'size'), qty=('qty', 'sum'))
    if int(report['rows'].sum()) != len(orders):
        raise ValueError('input row conservation failed')
    mapped = orders[orders['bucket'] == 'mapped'].copy()
    monthly = mapped.groupby(['key', 'month'])['qty'].sum().to_dict()
    daily = {k: g.groupby('date')['qty'].sum().sort_index() for k, g in mapped.groupby('key')}
    cens = pd.read_excel(args.censor, sheet_name='2_删失')
    cens_set = set(zip(cens['product_id'].astype(str), cens['month'].astype(str).str.replace('-', '', regex=False)))
    input_report = report.reset_index().to_dict('records')
    return classes, keys, monthly, daily, cens_set, input_report, event_date_report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d3b', default=str(DATA/'analysis/codex-repair-20261102/D_历史归一与回测_D3b_v3_4_2026-11-02.xlsx'))
    ap.add_argument('--d3-script', default=str(Path(__file__).with_name('d3b_history_backtest_v3_2_2026-11-02.py')))
    ap.add_argument('--orders', default=str(DATA/'orders_unified.parquet'))
    ap.add_argument('--a-final', default=str(DATA/'analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx'))
    ap.add_argument('--b10', default=str(DATA/'analysis/仓库归属_A337_v6r10_2026-10-30.xlsx'))
    ap.add_argument('--censor', default=str(DATA/'analysis/D_销量清洗_v3_2026-11-02.xlsx'))
    ap.add_argument('--as-of', default='2026-11-02')
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-keys', type=int, default=0)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        raise ValueError('output run already exists; choose a new immutable run directory')
    as_of = date.fromisoformat(args.as_of)
    models = load_module(args.d3_script)
    classes, all_keys, monthly, daily, cens, input_report, date_report = load_history(args, models)
    keys = all_keys[:args.max_keys] if args.max_keys else all_keys
    # Complete source months only; no partial-month actuals in historical validation.
    last_complete = date(as_of.year, as_of.month, 1)
    months = [m for m in models.OBS_MONTHS if date(int(m[:4]), int(m[4:]), 1) < last_complete]
    if not months:
        raise ValueError('no complete history months')
    horizon_days = (97, 157)
    funcs = dict(models.BASELINES, **models.NEW_MODELS)
    funcs['ets_ann'] = fast_ets  # vectorized equivalent of existing scalar alpha search
    historical, current = [], []
    banks, per_key_banks = defaultdict(list), defaultdict(list)
    errors = []
    for key_index, key in enumerate(keys):
        y = np.array([monthly.get((key, int(m)), monthly.get((key, m), 0.)) for m in months], dtype=float)
        positives = np.flatnonzero(y > 0)
        if not len(positives):
            current.append(dict(key=key, model='none', predictions=None, reason='no_observed_history'))
            continue
        y[:positives[0]] = np.nan
        for i, month in enumerate(months):
            if (key[0], month) in cens:
                y[i] = np.nan
        cache = forecast_cache(y, funcs)
        for cutoff in range(12, len(months)):
            start = date(int(months[cutoff][:4]), int(months[cutoff][4:]), 1)
            if start < date(2024, 1, 1):
                continue
            model, selection = choose_model(y, cache, cutoff)
            if model == 'none':
                continue
            fc = cache[cutoff][model]
            for days in horizon_days:
                end = start+timedelta(days=days)
                if end > last_complete:
                    continue
                test_months = [i for i, month in enumerate(months)
                               if start <= date(int(month[:4]), int(month[4:]), 1) < end]
                if not all(np.isfinite(y[i]) for i in test_months):
                    continue  # censored outcome cannot be treated as observed truth
                point = calendar_total(fc, start, days)
                series = daily.get(key)
                actual = float(series.loc[start:end-timedelta(days=1)].sum()) if series is not None else 0.
                naive_fc = cache[cutoff].get('naive')
                baseline = calendar_total(naive_fc, start, days) if naive_fc is not None else np.nan
                record = dict(key=key, start=start, available_at=end, days=days,
                              point=point, actual=actual, model=model,
                              baseline_point=baseline, residual=(actual-point)/days,
                              selection_basis=selection['basis'])
                historical.append(record)
                banks[(key[1:], days)].append(record)
                per_key_banks[(key, days)].append(record)
        model, selection = choose_model(y, cache, len(y))
        current.append(dict(key=key, model=model,
                            predictions=cache[len(y)].get(model), reason=selection['basis']))
        if (key_index+1) % 200 == 0:
            print(json.dumps({'phase':'forecast', 'keys':key_index+1, 'total':len(keys)}), flush=True)

    grouped_cache = {}
    def residual_pool(key, days, cutoff):
        own = [r['residual'] for r in per_key_banks[(key, days)] if r['available_at'] <= cutoff]
        if len(own) >= 30:
            return own, 'key', len(own)
        token = (key[1:], days, cutoff)
        if token not in grouped_cache:
            grouped_cache[token] = [r['residual'] for r in banks[(key[1:], days)] if r['available_at'] <= cutoff]
        pool = grouped_cache[token]
        return calibration_pool(own, pool)

    evaluation = []
    for row in historical:
        residuals, source, count = residual_pool(row['key'], row['days'], row['start'])
        qs = demand_quantiles(row['point'], residuals, row['days'])
        evaluation.append(dict(zip(KEY, row['key']), start=row['start'].isoformat(),
                               outcome_available_at=row['available_at'].isoformat(),
                               horizon=row['days'], model=row['model'], actual=row['actual'],
                               point_forecast=row['point'], baseline_point=row['baseline_point'],
                               calibration_source=source, calibration_n=count, **qs))
    ev = pd.DataFrame(evaluation, columns=KEY+[
        'start','outcome_available_at','horizon','model','actual','point_forecast',
        'baseline_point','calibration_source','calibration_n','q10','q50','q85','q90','q95'])
    predicted, service = [], []
    for row in current:
        key = row['key']
        for days in horizon_days:
            point = calendar_total(row['predictions'], as_of, days) if row['predictions'] is not None else np.nan
            residuals, source, count = residual_pool(key, days, as_of)
            qs = demand_quantiles(point, residuals, days)
            base = dict(zip(KEY, key), key_version='D1b-v2.3-2026-11-02',
                        horizon=days, horizon_days=days, point_forecast=point,
                        p10=qs['q10'], p50=qs['q50'] if np.isfinite(qs['q50']) else point,
                        p90=qs['q90'], q85=qs['q85'], q90=qs['q90'], q95=qs['q95'],
                        model=row['model'], adopted_model=row['model'],
                        fallback_model='', demand_basis='observed_no_censor_imputation',
                        interval_method='chronological_empirical_horizon_residual',
                        interval_level=source,
                        calibration_status='empirical_time_ordered' if np.isfinite(qs['q95']) else 'interval_uncalibrated',
                        calibration_n=count, service_validation_status='retrospective_no_service_guarantee',
                        manual_review_required=True, auto_order=False,
                        seasonality_status='not_overridden', promo_status='unknown',
                        selection_basis=row['reason'])
            predicted.append(base)
            for level in (85, 90, 95):
                service.append(dict(zip(KEY, key), horizon=days, service_level=level/100.,
                                    quantile=base[f'q{level}'], basis_level=source,
                                    calibrated='否：回溯经验区间，非服务承诺'))
    pred, svc = pd.DataFrame(predicted), pd.DataFrame(service)
    coverage = []
    for days in horizon_days:
        frame = ev[ev.horizon == days]
        spaced = set(nonoverlapping_starts([date.fromisoformat(x) for x in frame.start.unique()], days))
        for scope, part in [('all',frame), ('nonoverlapping_dates',frame[frame.start.isin([d.isoformat() for d in spaced])])]:
            for level in (85,90,95):
                valid = part[part[f'q{level}'].notna()]
                if valid.empty:
                    continue
                delta = valid.actual-valid[f'q{level}']
                positive = valid.actual > 0
                coverage.append(dict(horizon=days, level=level/100., scope=scope, n=len(valid),
                                     keys=len(valid[KEY].drop_duplicates()),
                                     coverage=float((delta<=0).mean()),
                                     coverage_positive=float((delta[positive]<=0).mean()) if positive.any() else np.nan,
                                     mean_shortfall=float(delta.clip(lower=0).mean()),
                                     mean_excess=float((-delta).clip(lower=0).mean()),
                                     point_mae=float((valid.actual-valid.point_forecast).abs().mean()),
                                     naive_mae=float((valid.actual-valid.baseline_point).abs().mean()),
                                     validation_status='retrospective_not_prospective_service'))
    out.mkdir(parents=True, exist_ok=False)
    xlsx = out/'D_概率与服务_D5_v6_2026-11-02.xlsx'
    manifest = dict(schema_version='demand-forecast/v1', rule_version=VERSION, as_of=args.as_of,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    rows=len(pred), target_keys=len(keys), historical_windows=len(ev),
                    minimum_key_calibration_samples=30, minimum_pool_calibration_samples=30,
                    input_report=input_report, event_date_report=date_report, no_service_guarantee=True,
                    source_history_last_complete_month=months[-1],
                    mapping_mode='retrospective_frozen_identity_not_historical_approval',
                    inputs={name:dict(path=str(path),sha256=sha(path)) for name,path in
                            [('d3b',args.d3b),('orders',args.orders),('a_final',args.a_final),('b10',args.b10),('censor',args.censor)]},
                    code={str(p):sha(p) for p in [Path(__file__),Path(args.d3_script),Path(__file__).parents[1]/'supply_netting/temporal_demand.py']})
    with pd.ExcelWriter(xlsx, engine='openpyxl') as writer:
        pred.to_excel(writer,sheet_name='1_预测',index=False)
        svc.to_excel(writer,sheet_name='3_服务水平',index=False)
        pd.DataFrame(coverage).to_excel(writer,sheet_name='4_时间验证',index=False)
        pd.DataFrame(input_report).to_excel(writer,sheet_name='5_输入去向',index=False)
    pred.to_parquet(out/'forecast.parquet',index=False)
    ev.to_parquet(out/'historical_windows.parquet',index=False)
    report = dict(**{k:v for k,v in manifest.items() if k not in ('inputs','code')},coverage=coverage)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    manifest['outputs']={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in out.iterdir() if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'out':str(out),'keys':len(keys),'forecast_rows':len(pred),'historical_windows':len(ev),'coverage':coverage},ensure_ascii=False),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
