"""python -m supply_distribution audit --repo PATH --out private/report.json"""
import argparse
import json
from pathlib import Path

from .audit import run_audit


def main():
    parser = argparse.ArgumentParser(description='只读检查供应链能力的Agent分发条件；不执行被审代码')
    commands = parser.add_subparsers(dest='command', required=True)
    audit = commands.add_parser('audit')
    audit.add_argument('--repo', type=Path, required=True)
    audit.add_argument('--git-ref', default=None, help='检查提交树，不checkout；缺省检查当前工作区')
    audit.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_audit(args.repo, args.git_ref)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'endtoend_success': False,
                      'summary': result['summary']}, ensure_ascii=False))
    return {'ready': 0, 'partial': 1, 'blocked': 2}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
