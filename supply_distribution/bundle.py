"""Integrity-only validator for an approved, private capability ZIP.

Never extracts, imports, executes, or contacts services. A valid package is not
proof that its entrypoints work or another machine can independently recompute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import zlib


SCHEMA = 'fzh-supply-capability-bundle/v1'
CAPABILITIES = ('orders_history', 'abc_policy', 'inventory', 'supply_facts',
                'forecast', 'netting', 'explain', 'refresh')
REQUIRED_BRANCHES = {'USNJ', 'USTX', 'PL'}
RECOMPUTATION_INPUT_ROLES = {'data', 'policy', 'history', 'model', 'code', 'input'}


def _safe_path(value):
    return (isinstance(value, str) and bool(value) and '\\' not in value
            and not any(ord(c) < 32 for c in value) and ':' not in value
            and not value.startswith('/') and not value.endswith('/')
            and all(p not in {'', '.', '..'} for p in value.split('/'))
            and not PurePosixPath(value).is_absolute())


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def validate_bundle(path, *, max_file_size=256 * 1024 * 1024,
                    max_total_size=1024 * 1024 * 1024, max_manifest_size=2 * 1024 * 1024,
                    max_entries=10000):
    failures = set()
    counts = {'archive_entry_count': 0, 'registered_file_count': 0,
              'capability_count': 0, 'validated_file_count': 0, 'total_uncompressed_size': 0}

    def result():
        return {'schema': 'supply-capability-bundle-validation/v1', 'bundle_schema': SCHEMA,
                'status': 'rejected' if failures else 'verified',
                'asset_integrity_verified': not failures, 'endtoend_success': False,
                'independence_verified': False, 'execution_performed': False,
                'capability_execution_verified': False,
                'extracted': False, 'network_accessed': False,
                'failure_codes': sorted(failures), **counts,
                'meaning': '仅验证声明范围、资产登记与字节完整性；不证明代码可运行、数据齐全或独立重算成功'}

    try:
        if any(isinstance(n, bool) or not isinstance(n, int) or n <= 0
               for n in (max_file_size, max_total_size, max_manifest_size, max_entries)):
            failures.add('invalid_limits')
            return result()
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            counts['archive_entry_count'] = len(entries)
            counts['total_uncompressed_size'] = sum(info.file_size for info in entries)
            if len(entries) > max_entries:
                failures.add('entry_count_limit')
            if counts['total_uncompressed_size'] > max_total_size:
                failures.add('total_size_limit')
            names = [info.filename for info in entries]
            if len(names) != len(set(names)):
                failures.add('duplicate_archive_name')
            for info in entries:
                # ZipInfo on Windows normalizes backslashes and truncates NULs;
                # validate the original central-directory name as well.
                if not _safe_path(info.filename) or not _safe_path(info.orig_filename):
                    failures.add('unsafe_path')
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    failures.add('symlink_not_allowed')
                if info.file_size > max_file_size:
                    failures.add('file_size_limit')
                if info.flag_bits & 1:
                    failures.add('encrypted_entry_not_supported')
            if 'manifest.json' not in names:
                failures.add('missing_manifest')
            # Check resource and path safety before reading even the manifest.
            if failures:
                return result()
            if archive.getinfo('manifest.json').file_size > max_manifest_size:
                failures.add('manifest_size_limit')
                return result()
            try:
                manifest = json.loads(archive.read('manifest.json').decode('utf-8'),
                    object_pairs_hook=_object,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite_json')))
            except (ValueError, UnicodeError):
                failures.add('invalid_manifest_json')
                return result()
            if not isinstance(manifest, dict):
                failures.add('invalid_manifest')
                return result()
            if manifest.get('schema') != SCHEMA:
                failures.add('unsupported_schema')
            scope = manifest.get('scope')
            if not isinstance(scope, dict) or scope.get('kind') != 'full_approved_universe':
                failures.add('invalid_scope')
            else:
                branches = scope.get('branches')
                if (not isinstance(branches, list) or len(branches) != 3
                        or any(not isinstance(b, str) for b in branches)
                        or set(branches) != REQUIRED_BRANCHES):
                    failures.add('invalid_branch_scope')
            files = manifest.get('files')
            registered = {}
            if not isinstance(files, list) or not files:
                failures.add('missing_files')
            else:
                counts['registered_file_count'] = len(files)
                for record in files:
                    if not isinstance(record, dict) or not {'path', 'sha256', 'size', 'role'} <= set(record):
                        failures.add('invalid_file_record')
                        continue
                    name, size, sha, role = (record[k] for k in ('path', 'size', 'sha256', 'role'))
                    if not _safe_path(name) or name == 'manifest.json':
                        failures.add('unsafe_registered_path')
                        continue
                    if (isinstance(size, bool) or not isinstance(size, int) or size < 0
                            or not isinstance(sha, str) or not re.fullmatch('[a-fA-F0-9]{64}', sha)
                            or not isinstance(role, str) or not role.strip()):
                        failures.add('invalid_file_record')
                        continue
                    if name in registered:
                        failures.add('duplicate_registered_path')
                    registered[name] = record
                    if size > max_file_size:
                        failures.add('file_size_limit')
            if set(names) - {'manifest.json'} - set(registered):
                failures.add('unregistered_archive_entry')
            if set(registered) - set(names):
                failures.add('missing_registered_file')
            capabilities = manifest.get('capabilities')
            if not isinstance(capabilities, dict):
                failures.add('missing_capabilities')
            else:
                counts['capability_count'] = len(capabilities)
                if set(CAPABILITIES) - set(capabilities):
                    failures.add('missing_capabilities')
                if set(capabilities) - set(CAPABILITIES):
                    failures.add('unknown_capabilities')
                for name in CAPABILITIES:
                    definition = capabilities.get(name)
                    if not isinstance(definition, dict):
                        failures.add('invalid_capability_record')
                        continue
                    entrypoint = definition.get('entrypoint')
                    if not isinstance(entrypoint, str) or not entrypoint.strip():
                        failures.add('missing_entrypoint')
                    mode = definition.get('mode')
                    if not isinstance(mode, str) or mode not in {'reference', 'refresh', 'recompute'} or (
                        name in {'forecast', 'netting'} and mode != 'recompute') or (
                        name == 'refresh' and mode != 'refresh') or (
                        name == 'orders_history' and mode == 'reference'):
                        failures.add('invalid_capability_mode')
                    artifacts = definition.get('artifacts')
                    if not isinstance(artifacts, list) or not artifacts:
                        failures.add('missing_capability_artifacts')
                    elif any(not isinstance(p, str) or p not in registered for p in artifacts):
                        failures.add('unregistered_capability_artifact')
                    elif name in {'forecast', 'netting', 'refresh'} and not any(
                        registered[p]['role'].strip().lower() in RECOMPUTATION_INPUT_ROLES
                        for p in artifacts
                    ):
                        # Modes are claims, not evidence: output snapshots and
                        # unknown role labels cannot stand in for executable inputs.
                        # Inputs need not include code if public Git provides it.
                        failures.add('incompatible_capability_artifacts')
            if failures:
                return result()
            for name, record in registered.items():
                info = archive.getinfo(name)
                if info.file_size != record['size']:
                    failures.add('size_mismatch')
                    continue
                digest = hashlib.sha256()
                consumed = 0
                with archive.open(info) as stream:
                    while True:
                        block = stream.read(1024 * 1024)
                        if not block:
                            break
                        consumed += len(block)
                        if consumed > max_file_size or consumed > record['size']:
                            failures.add('stream_size_limit')
                            break
                        digest.update(block)
                if consumed != record['size']:
                    failures.add('size_mismatch')
                elif digest.hexdigest() != record['sha256'].lower():
                    failures.add('hash_mismatch')
                else:
                    counts['validated_file_count'] += 1
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error):
        failures.add('unreadable_or_corrupt_archive')
    return result()


def main():
    parser = argparse.ArgumentParser(description='验证私有能力ZIP完整性；不解压、不联网、不执行')
    parser.add_argument('path', type=Path)
    parser.add_argument('--outreport', type=Path, required=True)
    args = parser.parse_args()
    if args.path.resolve() == args.outreport.resolve():
        parser.error('报告路径不能覆盖输入ZIP')
    report = validate_bundle(args.path)
    args.outreport.parent.mkdir(parents=True, exist_ok=True)
    args.outreport.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'failure_codes': report['failure_codes'],
                      'registered_file_count': report['registered_file_count'],
                      'capability_count': report['capability_count'],
                      'endtoend_success': False, 'independence_verified': False,
                      'capability_execution_verified': False}, ensure_ascii=False))
    return 0 if report['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
