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


def test_cost_stage_counts_all_unmatched_states():
    report = {'input_rows': 7, 'eligible_rows': 6, 'excluded_rows': 1,
              'statuses': {'matched': 1, 'account_unmapped': 2, 'ambiguous_account': 1,
                           'fulfillment_conflict': 1, 'ambiguous_parent_child': 1,
                           'excluded_non_order_or_missing_id': 1}}
    stage = runner.cost_stage(report)
    assert stage['success'] + stage['unmatched'] + stage['skipped'] == stage['input']
    assert stage['unmatched'] == 5


def test_snapshot_purchase_month_mismatch_fails():
    with pytest.raises(ValueError, match='snapshot'):
        runner.verify_fba_snapshot_month({'query_start':'2026-08-01 00:00:00', 'query_end':'2026-08-31 23:59:59'}, '2026-09')


def test_empty_fba_snapshot_is_missing_evidence():
    with pytest.raises(ValueError, match='snapshot'):
        runner.verify_fba_snapshot_month({}, '2026-08')


def test_empty_input_month_cannot_pass(tmp_path):
    from sellfox_settlement.monthly_validation import validate_month
    assert validate_month(tmp_path, '2026-08')['summary']['fatal_validation_errors']
