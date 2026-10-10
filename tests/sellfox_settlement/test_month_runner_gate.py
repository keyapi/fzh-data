import pytest

from sellfox_settlement import run_technical_month as runner


def test_fatal_month_keeps_evidence_and_stops_before_cost_or_workbook(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    output = tmp_path / 'private'
    result = {'summary': {'fatal_validation_errors': True}, 'source_manifest': {'files': []},
              'csv_validation': {'rows': []}}
    monkeypatch.setattr(runner, 'validate_month', lambda *args: result)
    with pytest.raises(ValueError, match='fatal'):
        runner.run_month(source, output, '2026-08')
    assert (output / 'monthly_validation.json').exists()
    assert not (output / '2026-08-technical-workbook.xlsx').exists()
