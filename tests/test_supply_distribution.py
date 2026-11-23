import json
import os
import subprocess

import pytest

from supply_distribution.audit import run_audit


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init')
    git(tmp_path, 'config', 'user.email', 'test@example.invalid')
    git(tmp_path, 'config', 'user.name', 'Test')
    return tmp_path


def populate(repo):
    for module in ('self_fulfilled_demand', 'supply_netting', 'demand_collaboration'):
        (repo / module).mkdir()
        (repo / module / '__init__.py').write_text('', encoding='utf-8')
    (repo / 'scripts').mkdir()
    (repo / 'scripts' / 'd5_time_validated_v1.py').write_text("ROOT = 'D:/Work/private'\n", encoding='utf-8')
    (repo / 'pyproject.toml').write_text('[project]\ndependencies=["requests"]\n'
        '[tool.hatch.build.targets.wheel]\npackages=["self_fulfilled_demand"]\n', encoding='utf-8')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'fixture')


def test_missing_capabilities_are_blocked(repo):
    (repo / 'readme.txt').write_text('empty')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'empty')
    result = run_audit(repo)
    assert result['status'] == 'blocked'
    assert result['endtoend_success'] is False
    assert result['capabilities']['D']['code_present'] is False


def test_complete_static_tree_is_never_runtime_ready(repo):
    populate(repo)
    result = run_audit(repo)
    assert result['status'] == 'partial'
    assert result['runtime_verification'] == 'not_run'
    assert result['endtoend_success'] is False
    assert result['capabilities']['D']['local_data_dependency'] is True
    assert result['capabilities']['ABC']['assets_availability'] == 'unknown'


def test_wheel_omissions_and_paths_have_locations_not_source(repo):
    populate(repo)
    result = run_audit(repo)
    assert 'supply_netting' in result['packaging']['missing_from_wheel']
    assert result['hardcoded_paths']['hits'] == [
        {'path': 'scripts/d5_time_validated_v1.py', 'line': 1, 'count': 1}]
    assert 'private' not in json.dumps(result['hardcoded_paths'])


def test_secrets_never_read_or_emitted(repo, monkeypatch):
    populate(repo)
    marker = 'secret-do-not-emit-123456789'
    (repo / '.env').write_text('ERP_API_KEY=' + marker)
    monkeypatch.setenv('ERP_API_KEY', marker)
    monkeypatch.delenv('ERP_API_SECRET', raising=False)
    monkeypatch.setenv('FZH_DATA_ROOT', 'C:/Users/private-not-emitted')
    result = run_audit(repo)
    encoded = json.dumps(result)
    assert marker not in encoded and 'private-not-emitted' not in encoded
    assert result['environment']['ERP_API_KEY_configured'] is True
    assert result['environment']['ERP_API_SECRET_configured'] is False
    assert result['environment']['FZH_DATA_ROOT_declared'] is True
    assert result['environment']['dotenv_read'] is False


@pytest.mark.parametrize('ref', ['--help', '-HEAD', 'HEAD:pyproject.toml', 'main;echo secret'])
def test_invalid_ref_rejected_without_shell(repo, ref):
    with pytest.raises(ValueError):
        run_audit(repo, ref)


def test_tree_ref_does_not_read_uncommitted_code(repo):
    populate(repo)
    (repo / 'supply_netting' / '__init__.py').write_text("x='C:/Users/new-path'\n")
    frozen = run_audit(repo, 'HEAD')
    current = run_audit(repo)
    assert frozen['hardcoded_paths']['match_count'] == 1
    assert current['hardcoded_paths']['match_count'] == 2
    assert frozen['git']['mode'] == 'tree_ref'
    assert frozen['git']['commit'] == git(repo, 'rev-parse', 'HEAD')


def test_claude_skill_install_not_claimed_automatic(repo):
    populate(repo)
    p = repo / '.agents' / 'skills' / 'replenishment-decision'
    p.mkdir(parents=True)
    (p / 'SKILL.md').write_text('No executable instructions are executed')
    result = run_audit(repo)
    assert result['agent_skills']['codex_project']['relevant_skills'] == ['replenishment-decision']
    assert result['agent_skills']['claude_desktop']['manual_install_required'] is True
