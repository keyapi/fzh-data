import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


def runner():
    path = Path(__file__).parents[2] / 'scripts/d5_time_validated_2026_11_02.py'
    spec = importlib.util.spec_from_file_location('d5_test_runner', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('history_present', [True, False])
def test_offline_integer_and_no_history_inputs_export_consistent_quantiles(tmp_path, monkeypatch, history_present):
    module = runner()
    months = [f'{y}{m:02d}' for y in range(2023,2027) for m in range(1,13) if f'{y}{m:02d}' <= '202610']
    models = SimpleNamespace(OBS_MONTHS=months,
                             BASELINES={'naive':lambda y,h:np.repeat(y[-1],h)}, NEW_MODELS={})
    key = ('ITEM', 'POOL', 'FORM', 'UNIT')
    monthly = {(key,m):1 for m in months} if history_present else {}
    monkeypatch.setattr(module,'load_module',lambda path:models)
    monkeypatch.setattr(module,'load_history',lambda args,m:(None,[key],monthly,{},set(),[],{}))
    monkeypatch.setattr(module,'sha',lambda path:'test-fixture-hash')
    out = tmp_path/'run'
    assert module.main(['--out',str(out)]) == 0
    pred = pd.read_parquet(out/'forecast.parquet')
    assert len(pred) == 2
    svc = pd.read_excel(out/'D_概率与服务_D5_v6_2026-11-02.xlsx',sheet_name='3_服务水平')
    for horizon in [97,157]:
        expected = pred.loc[pred.horizon==horizon,'q95'].iloc[0]
        actual = svc.loc[(svc.horizon==horizon)&(svc.service_level==.95),'quantile'].iloc[0]
        assert (pd.isna(expected) and pd.isna(actual)) or expected==pytest.approx(actual)
    with pytest.raises(ValueError,match='already exists'):
        module.main(['--out',str(out)])
