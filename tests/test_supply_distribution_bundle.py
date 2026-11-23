import hashlib
import json
import stat
import zipfile

import pytest

from supply_distribution.bundle import CAPABILITIES, validate_bundle


def fixture_manifest(data=b'private-material'):
    return {'schema': 'fzh-supply-capability-bundle/v1',
            'scope': {'kind': 'full_approved_universe', 'branches': ['USNJ', 'USTX', 'PL']},
            'files': [{'path': 'assets/input.bin', 'sha256': hashlib.sha256(data).hexdigest(),
                       'size': len(data), 'role': 'input'}],
            'capabilities': {name: {'artifacts': ['assets/input.bin'],
                'entrypoint': 'python -m existing_tool',
                'mode': 'refresh' if name == 'refresh' else 'recompute' if name in
                    {'orders_history', 'forecast', 'netting'} else 'reference'} for name in CAPABILITIES}}


def write_bundle(path, manifest=None, data=b'private-material', extras=()):
    with zipfile.ZipFile(path, 'w') as bundle:
        if manifest is not False:
            bundle.writestr('manifest.json', json.dumps(manifest or fixture_manifest(data)))
        bundle.writestr('assets/input.bin', data)
        for name, value in extras:
            info = zipfile.ZipInfo(name)
            info.filename = name  # Windows ZipInfo normalizes backslashes at construction.
            bundle.writestr(info, value)
    return path


def test_full_bundle_is_integrity_only_not_execution(tmp_path):
    result = validate_bundle(write_bundle(tmp_path / 'bundle.zip'))
    assert result['status'] == 'verified'
    assert result['asset_integrity_verified'] is True
    assert result['endtoend_success'] is False
    assert result['independence_verified'] is False
    assert result['capability_count'] == 8


@pytest.mark.parametrize('missing', CAPABILITIES)
def test_each_capability_mandatory(tmp_path, missing):
    manifest = fixture_manifest()
    del manifest['capabilities'][missing]
    result = validate_bundle(write_bundle(tmp_path / 'bundle.zip', manifest))
    assert result['status'] == 'rejected'
    assert 'missing_capabilities' in result['failure_codes']


@pytest.mark.parametrize('change', ['single_sku', 'missing_branch', 'missing_scope'])
def test_single_sku_and_partial_scope_rejected(tmp_path, change):
    manifest = fixture_manifest()
    if change == 'single_sku':
        manifest['scope']['kind'] = 'single_sku'
    elif change == 'missing_branch':
        manifest['scope']['branches'].remove('PL')
    else:
        del manifest['scope']
    assert validate_bundle(write_bundle(tmp_path / 'bundle.zip', manifest))['status'] == 'rejected'


@pytest.mark.parametrize('capability', ['orders_history', 'forecast', 'netting', 'refresh'])
def test_reference_is_not_recomputation(tmp_path, capability):
    manifest = fixture_manifest()
    manifest['capabilities'][capability]['mode'] = 'reference'
    assert 'invalid_capability_mode' in validate_bundle(
        write_bundle(tmp_path / 'bundle.zip', manifest))['failure_codes']


@pytest.mark.parametrize('field,value,code', [('sha256', '0' * 64, 'hash_mismatch'),
    ('size', 1, 'size_mismatch'), ('size', True, 'invalid_file_record')])
def test_hash_and_size_verified(tmp_path, field, value, code):
    manifest = fixture_manifest()
    manifest['files'][0][field] = value
    result = validate_bundle(write_bundle(tmp_path / 'bundle.zip', manifest))
    assert code in result['failure_codes']


@pytest.mark.parametrize('name', ['../secret', '/absolute', 'C:/secret', 'a\\b', 'a/../b'])
def test_unsafe_paths_rejected_without_extraction(tmp_path, name):
    result = validate_bundle(write_bundle(tmp_path / 'bundle.zip', extras=[(name, b'x')]))
    assert 'unsafe_path' in result['failure_codes']
    assert not (tmp_path / 'secret').exists()


def test_symlink_rejected(tmp_path):
    path = write_bundle(tmp_path / 'bundle.zip')
    with zipfile.ZipFile(path, 'a') as bundle:
        info = zipfile.ZipInfo('symlink')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, '../private')
    assert 'symlink_not_allowed' in validate_bundle(path)['failure_codes']


def test_duplicate_and_unregistered_files_rejected(tmp_path):
    path = write_bundle(tmp_path / 'bundle.zip', extras=[('unregistered-secret.txt', b'password')])
    assert 'unregistered_archive_entry' in validate_bundle(path)['failure_codes']
    with zipfile.ZipFile(path, 'a') as bundle:
        with pytest.warns(UserWarning):
            bundle.writestr('assets/input.bin', b'other')
    result = validate_bundle(path)
    assert 'duplicate_archive_name' in result['failure_codes']
    assert 'password' not in json.dumps(result)
    assert 'unregistered-secret' not in json.dumps(result)


def test_resource_limits_checked_before_read(tmp_path):
    path = write_bundle(tmp_path / 'bundle.zip')
    assert 'file_size_limit' in validate_bundle(path, max_file_size=2)['failure_codes']
    assert 'total_size_limit' in validate_bundle(path, max_total_size=2)['failure_codes']


def test_missing_manifest_or_artifact_and_bad_references(tmp_path):
    assert 'missing_manifest' in validate_bundle(write_bundle(tmp_path / 'none.zip', False))['failure_codes']
    manifest = fixture_manifest()
    manifest['capabilities']['forecast']['artifacts'] = ['not-registered.bin']
    assert 'unregistered_capability_artifact' in validate_bundle(
        write_bundle(tmp_path / 'ref.zip', manifest))['failure_codes']
    manifest = fixture_manifest()
    manifest['files'][0]['path'] = 'missing.bin'
    assert 'missing_registered_file' in validate_bundle(
        write_bundle(tmp_path / 'missing.zip', manifest))['failure_codes']


def test_entrypoint_required_and_never_executed(tmp_path):
    manifest = fixture_manifest()
    manifest['capabilities']['forecast']['entrypoint'] = ''
    assert 'missing_entrypoint' in validate_bundle(
        write_bundle(tmp_path / 'empty.zip', manifest))['failure_codes']
    manifest['capabilities']['forecast']['entrypoint'] = 'echo super-secret-do-not-run'
    result = validate_bundle(write_bundle(tmp_path / 'safe.zip', manifest))
    assert result['status'] == 'verified'
    assert 'super-secret-do-not-run' not in json.dumps(result)


def test_malformed_mode_fails_closed(tmp_path):
    manifest = fixture_manifest()
    manifest['capabilities']['forecast']['mode'] = ['recompute']
    assert 'invalid_capability_mode' in validate_bundle(
        write_bundle(tmp_path / 'badmode.zip', manifest))['failure_codes']


def test_cli_cannot_overwrite_input_archive(tmp_path, monkeypatch):
    from supply_distribution.bundle import main
    path = write_bundle(tmp_path / 'bundle.zip')
    original = path.read_bytes()
    monkeypatch.setattr('sys.argv', ['bundle', str(path), '--outreport', str(path)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert path.read_bytes() == original


@pytest.mark.parametrize('role', ['reference_only', 'result', 'report', 'read_only_snapshot',
                                'forecast_output', 'decision_output', 'unrecognized_role'])
def test_outputs_cannot_impersonate_recomputation_inputs(tmp_path, role):
    manifest = fixture_manifest()
    manifest['files'][0]['role'] = role
    result = validate_bundle(write_bundle(tmp_path / 'outputs.zip', manifest))
    assert result['status'] == 'rejected'
    assert 'incompatible_capability_artifacts' in result['failure_codes']
    assert result['capability_execution_verified'] is False


@pytest.mark.parametrize('role', ['data', 'policy', 'history', 'model', 'code', 'input'])
def test_declared_inputs_still_do_not_prove_execution(tmp_path, role):
    manifest = fixture_manifest()
    manifest['files'][0]['role'] = role
    result = validate_bundle(write_bundle(tmp_path / 'inputs.zip', manifest))
    assert result['status'] == 'verified'
    assert result['capability_execution_verified'] is False
