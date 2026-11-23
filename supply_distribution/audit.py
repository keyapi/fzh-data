"""Inspect a working tree or committed git tree without executing repository code."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import subprocess

try:
    import tomllib
except ImportError:  # Python 3.10: report unknown rather than install anything.
    tomllib = None


MODULES = ('self_fulfilled_demand', 'supply_netting', 'demand_collaboration')
SCAN_ROOTS = MODULES + ('demand_forecast', 'supply_chain_visibility', 'supply_copilot')
LOCAL_PATH = re.compile(r'(?:D:[\\/]+Work|C:[\\/]+Users)(?=[\\/]|$)', re.IGNORECASE)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                            encoding='utf-8', errors='replace', timeout=30)
    if result.returncode:
        # Do not echo command output: hooks/config/errors can contain local secrets.
        raise ValueError('无法读取Git版本；请确认仓库及ref存在')
    return result.stdout.strip()


def _read_worktree(repo: Path):
    paths = []
    for root in SCAN_ROOTS + ('scripts', '.agents/skills'):
        directory = repo / root
        if not directory.is_dir() or directory.is_symlink():
            continue
        for current, dirs, names in os.walk(directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in {'__pycache__', '.venv', 'data', 'out', 'node_modules'}
                             and not (Path(current) / d).is_symlink())
            for name in sorted(names):
                path = Path(current) / name
                if path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(repo).as_posix()
                if _selected(relative):
                    paths.append(relative)
    if (repo / 'pyproject.toml').is_file() and not (repo / 'pyproject.toml').is_symlink():
        paths.append('pyproject.toml')

    def read(path):
        file = (repo / path).resolve()
        if not file.is_relative_to(repo):
            raise ValueError('文件越出仓库范围')
        return file.read_text(encoding='utf-8', errors='replace')

    return sorted(set(paths)), read


def _selected(path):
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    if path == 'pyproject.toml':
        return True
    if path.startswith('.agents/skills/'):
        return path.endswith('/SKILL.md')
    if not path.endswith('.py'):
        return False
    if parts[0] in SCAN_ROOTS:
        return True
    return parts[0] == 'scripts' and re.match(r'(?:d[1-6][a-z]?_|s2_|.*(?:forecast|supply|replenish))', parts[-1], re.I) is not None


def run_audit(repo, git_ref=None) -> dict:
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise ValueError('仓库路径不存在')
    if git_ref is not None and (not isinstance(git_ref, str) or not git_ref
            or git_ref.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_./-]+', git_ref)):
        raise ValueError('非法Git ref；只接受分支、标签或提交ID')
    commit = _git(repo, 'rev-parse', '--verify', (git_ref or 'HEAD') + '^{commit}')
    if git_ref:
        listing = _git(repo, 'ls-tree', '-r', '--full-tree', commit)
        files = []
        for line in listing.splitlines():
            metadata, path = line.split('\t', 1)
            # Symbolic links and gitlinks are not read as files.
            if metadata.startswith(('100644 ', '100755 ')) and _selected(path):
                files.append(path)

        def read(path):
            return _git(repo, 'show', f'{commit}:{path}')

        git_info = {'mode': 'tree_ref', 'requested_ref': git_ref, 'commit': commit,
                    'working_tree_changes_included': False}
    else:
        files, read = _read_worktree(repo)
        git_info = {'mode': 'working_tree', 'commit': commit,
                    'dirty': bool(_git(repo, 'status', '--porcelain', '--untracked-files=normal')),
                    'working_tree_changes_included': True}

    present = {module: any(path.startswith(module + '/') for path in files) for module in MODULES}
    forecast_files = [path for path in files if path.startswith('demand_forecast/')
                      or re.match(r'scripts/d5_time_validated[^/]*\.py$', path)]
    missing = [name for name, exists in present.items() if not exists]
    if not forecast_files:
        missing.append('forecast_entry')
    hits = []
    data_root_references = []
    for path in files:
        if not path.endswith('.py'):
            continue
        for line_number, line in enumerate(read(path).splitlines(), 1):
            count = len(LOCAL_PATH.findall(line))
            if count:
                hits.append({'path': path, 'line': line_number, 'count': count})
            if 'FZH_DATA_ROOT' in line:
                data_root_references.append({'path': path, 'line': line_number})

    packaging = {'metadata_present': 'pyproject.toml' in files, 'parse_status': 'missing',
                 'wheel_packages': [], 'dependencies': [], 'missing_from_wheel': []}
    if packaging['metadata_present'] and tomllib:
        try:
            metadata = tomllib.loads(read('pyproject.toml'))
            wheel = metadata.get('tool', {}).get('hatch', {}).get('build', {}).get('targets', {}).get('wheel', {}).get('packages', [])
            dependencies = metadata.get('project', {}).get('dependencies', [])
            if not isinstance(wheel, list) or not isinstance(dependencies, list):
                raise ValueError('metadata types')
            # URLs or arbitrary dependency expressions could embed credentials.
            # Only distribution names are included, not complete expressions.
            names = []
            for item in dependencies:
                match = re.match(r'^([A-Za-z0-9_.-]+)', str(item))
                if match and '://' not in str(item) and '@' not in str(item):
                    names.append(match.group(1))
            packaging.update(parse_status='parsed', wheel_packages=[p for p in wheel
                if isinstance(p, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', p)], dependencies=names)
            packaging['missing_from_wheel'] = [m for m in MODULES if present[m]
                and m not in [p.rstrip('/').split('/')[-1] for p in packaging['wheel_packages']]]
        except (ValueError, TypeError):
            packaging['parse_status'] = 'invalid'
    elif packaging['metadata_present']:
        packaging['parse_status'] = 'parser_unavailable'

    skills = sorted({PurePosixPath(path).parent.name for path in files
                     if path.startswith('.agents/skills/')})
    relevant = [s for s in skills if re.search(r'demand|supply|replenish|forecast', s, re.I)]
    return {
        'schema': 'supply-distribution-audit/v1', 'git': git_info,
        'status': 'blocked' if missing else 'partial',
        'static_checks_complete': True, 'runtime_verification': 'not_run',
        'endtoend_success': False,
        'summary': '缺少分发所需代码入口' if missing else '静态代码入口齐备；数据、权限与整链运行尚未验收',
        'missing_capabilities': missing,
        'capabilities': {
            'ABC': {'assets_availability': 'unknown', 'runtime_verified': False,
                    'requirements': ['商品宇宙版本', '归属/形态/单位政策', '库存来源时间与完整性']},
            'D': {'code_present': bool(forecast_files), 'entries': forecast_files,
                  'historical_orders_code_present': present['self_fulfilled_demand'],
                  'local_data_dependency': bool(forecast_files),
                  'requirements': ['历史订单覆盖对账', 'ABC政策资产', '预测源期间与校准证据']},
            'E': {'code_present': any(p.startswith('supply_chain_visibility/') for p in files),
                  'api_contract_verified': False,
                  'requirements': ['EN权限与分页契约', '供应阶段互斥', 'SKU/单位/分公司身份', '日期和供给余额证据']},
            'modules': present,
        },
        'packaging': packaging,
        'hardcoded_paths': {'match_count': sum(h['count'] for h in hits), 'hits': hits,
                            'scan_scope': list(SCAN_ROOTS) + ['scripts:forecast/supply/demand-prefixes'],
                            'source_contents_included': False},
        'agent_skills': {
            'codex_project': {'relevant_skills': relevant, 'project_trust_required': True,
                              'discovered_does_not_mean_installed_or_runtime_verified': True},
            'claude_desktop': {'manual_install_required': True,
                               'instruction': '需用户级skill安装/注册并重启宿主；git clone不等于Desktop加载成功'},
        },
        'environment': {'ERP_API_KEY_configured': bool(os.environ.get('ERP_API_KEY')),
                        'ERP_API_SECRET_configured': bool(os.environ.get('ERP_API_SECRET')),
                        'FZH_DATA_ROOT_declared': bool(os.environ.get('FZH_DATA_ROOT')),
                        'FZH_DATA_ROOT_code_references': data_root_references,
                        'FZH_DATA_ROOT_is_not_proof_of_portability': True,
                        'dotenv_read': False, 'network_accessed': False},
        'next_checks': ['干净克隆/安装验证', '用本人凭证验证只读权限', '获取政策与历史数据覆盖证据',
                        '限定分公司/SKU运行ABCDE并核对输入输出', '非技术解释工作簿与完整失败去向'],
    }
