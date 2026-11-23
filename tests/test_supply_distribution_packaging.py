from pathlib import Path
import pytest

tomllib = pytest.importorskip('tomllib')


def test_runtime_capabilities_are_in_wheel():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    packages = set(project['tool']['hatch']['build']['targets']['wheel']['packages'])
    required = {'self_fulfilled_demand', 'supply_netting', 'supply_chain_visibility',
                'demand_collaboration', 'supply_distribution'}
    assert required <= packages, f'wheel缺少能力包: {sorted(required - packages)}'


def test_cli_preserves_unspecified_credential_source(monkeypatch, tmp_path):
    import sys
    import uvicorn
    from demand_collaboration import __main__, live_stock

    captured = {}

    class Source:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get(self):
            raise AssertionError('CLI启动测试不应发起网络请求')

    monkeypatch.setattr(live_stock, 'LiveStockSource', Source)
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, 'argv', ['demand_collaboration', '--db', str(tmp_path / 'demo.db')])
    __main__.main()
    assert captured['env_file'] is None
