import hashlib
import json

import pytest

from sellfox_settlement import verify_technical_run as verifier


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / 'source.csv'
    source.write_text('synthetic input', encoding='utf-8')
    output = tmp_path / 'reports'
    output.mkdir()
    files = {
        'technical_month_report.json': {'run_id': 'run1', 'month': '2026-08', 'status': 'succeeded',
                                        'snapshot_manifest': [], 'stages': []},
        'source_manifest.json': {'files': [{'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]},
        'monthly_validation.json': {'summary': {'month': '2026-08', 'fatal_validation_errors': False}},
        'workbook_tables.json': {'month': '2026-08', 'sheets': [{'name': 'Evidence', 'note': 'technical only',
                                                            'headers': ['amount'], 'rows': [[0]]}]},
    }
    for name, value in files.items():
        write_json(output / name, value)
    write_json(output / 'run_status.json', {
        'run_id': 'run1', 'month': '2026-08', 'status': 'succeeded',
        'artifacts': [{'path': name, 'sha256': hashlib.sha256((output / name).read_bytes()).hexdigest()} for name in files],
    })
    return output, source


def test_successful_json_run_verifies_all_artifacts_and_inputs(bundle):
    output, _ = bundle
    result = verifier.verify_run(output)
    assert result['run_id'] == 'run1'
    assert result['verified_artifacts'] == 4
    assert result['verified_inputs'] == 1
    assert result['workbook_status'] == 'not_requested'


def test_changed_source_is_rejected_even_when_reports_are_unchanged(bundle):
    output, source = bundle
    source.write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='input hash'):
        verifier.verify_run(output)


def test_tampered_report_is_rejected(bundle):
    output, _ = bundle
    (output / 'workbook_tables.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact hash'):
        verifier.verify_run(output)


@pytest.mark.parametrize('status', ['running', 'failed'])
def test_old_outputs_do_not_make_unsuccessful_current_run_valid(bundle, status):
    output, _ = bundle
    run = verifier.load_json(output / 'run_status.json')
    run['status'] = status
    write_json(output / 'run_status.json', run)
    with pytest.raises(ValueError, match='succeeded'):
        verifier.verify_run(output)


def test_artifact_path_cannot_escape_output_directory(bundle):
    output, _ = bundle
    run = verifier.load_json(output / 'run_status.json')
    run['artifacts'].append({'path': '../source.csv', 'sha256': 'irrelevant'})
    write_json(output / 'run_status.json', run)
    with pytest.raises(ValueError, match='escape'):
        verifier.verify_run(output)


def test_required_artifacts_cannot_be_removed_from_manifest(bundle):
    output, _ = bundle
    run = verifier.load_json(output / 'run_status.json')
    run['artifacts'] = run['artifacts'][:-1]
    write_json(output / 'run_status.json', run)
    with pytest.raises(ValueError, match='required artifacts'):
        verifier.verify_run(output)


def test_blank_zero_and_boolean_are_not_interchangeable():
    assert verifier.same_cell(None, '')
    assert not verifier.same_cell(None, 0)
    assert not verifier.same_cell(False, 0)
    assert verifier.same_cell(0, 0)
    assert verifier.same_cell("'=cmd", '=cmd')


def test_leftover_workbook_requires_matching_current_export_manifest(bundle):
    output, _ = bundle
    (output / '2026-08-technical-workbook.xlsx').write_bytes(b'old workbook')
    with pytest.raises(ValueError, match='current export'):
        verifier.verify_run(output, require_workbook=True)
