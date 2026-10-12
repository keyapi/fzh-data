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


@pytest.mark.parametrize('summary', [{}, {'start': '2025-01-01', 'end': '2025-02-28'},
                                    {'start': '2026-08-01', 'end': '2026-08-15'}])
def test_settlement_snapshot_must_cover_requested_month(summary):
    with pytest.raises(ValueError, match='Settlement snapshot'):
        runner.verify_settlement_snapshot_month(summary, '2026-08')


def test_settlement_snapshot_accepts_cross_period_buffer():
    runner.verify_settlement_snapshot_month({'start': '2026-07-31', 'end': '2026-09-30'}, '2026-08')


def test_failed_rerun_invalidates_previous_success_report(tmp_path, monkeypatch):
    output = tmp_path / 'private'
    output.mkdir()
    (output / 'technical_month_report.json').write_text('{"status":"succeeded"}')
    (output / '2026-08-technical-workbook.xlsx').write_bytes(b'previous output')
    def fail(*args, **kwargs):
        raise ValueError('invalid current input')
    monkeypatch.setattr(runner, '_run_month', fail)
    with pytest.raises(ValueError, match='invalid current input'):
        runner.run_month(tmp_path / 'source', output, '2026-08', json_only=True)
    status = runner._load(output / 'run_status.json')
    assert status['status'] == 'failed'
    assert runner._load(output / 'technical_month_report.json')['status'] == 'failed'
    assert not status.get('artifacts')
    assert (output / '2026-08-technical-workbook.xlsx').read_bytes() == b'previous output'


def test_json_only_success_does_not_claim_previous_workbook(tmp_path, monkeypatch):
    output = tmp_path / 'private'
    output.mkdir()
    (output / '2026-08-technical-workbook.xlsx').write_bytes(b'previous output')
    monkeypatch.setattr(runner, '_run_month', lambda *args, **kwargs: {'month':'2026-08', 'stages':[]})
    result = runner.run_month(tmp_path / 'source', output, '2026-08', json_only=True)
    status = runner._load(output / 'run_status.json')
    assert status['status'] == 'succeeded'
    assert result['run_id'] == status['run_id']
    assert not any(a['path'].endswith('.xlsx') for a in status['artifacts'])


def test_native_details_rejects_wrong_site_month_and_count(tmp_path):
    metadata={'details_complete':True,'details_pending_currencies':[], 'details':[{
        'currency':'USD','input_rows':1,'scoped_rows':1,'outside_scope':0,'scope_shops':1,
        'site_august_rows':1,'site_outside_august_rows':0,'site_time_missing':0,'utc_request_start':'2026-07-31','utc_request_end':'2026-09-02'}]}
    runner._write_json(tmp_path/'settlement_details_USD_site_august.json',[
        {'currency':'USD','siteTimeStr':'2026-09-01','amount':'1','amountDescription':'Principal','reportType':'Order'}])
    with pytest.raises(ValueError, match='site month'):
        runner.native_details_report(metadata,tmp_path,'2026-08')
    runner._write_json(tmp_path/'settlement_details_USD_site_august.json',[])
    with pytest.raises(ValueError, match='row count'):
        runner.native_details_report(metadata,tmp_path,'2026-08')


def test_native_details_preserves_currency_and_signed_amount(tmp_path):
    metadata={'details_complete':True,'details_pending_currencies':[], 'details':[{
        'currency':'USD','input_rows':2,'scoped_rows':1,'outside_scope':1,'scope_shops':1,
        'site_august_rows':1,'site_outside_august_rows':0,'site_time_missing':0,'utc_request_start':'2026-07-31','utc_request_end':'2026-09-02'}]}
    runner._write_json(tmp_path/'settlement_details_USD_site_august.json',[
        {'currency':'USD','siteTimeStr':'2026-08-01','amount':'-1.25','amountDescription':'Principal','reportType':'Refund'}])
    report=runner.native_details_report(metadata,tmp_path,'2026-08')
    assert report['input']==report['output']+report['skipped']==2
    assert report['amount_buckets'][0]['signed_amount']=='-1.25'
