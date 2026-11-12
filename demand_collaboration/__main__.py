"""Run the workbench, or import an explicit weekly baseline without touching production."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='运营需求协同（本地试运行）')
    parser.add_argument('--db', type=Path, required=True, help='私有目录的SQLite台账')
    parser.add_argument('--baseline', type=Path, help='导入规范JSON基准；不能把97天总量当周预测')
    parser.add_argument('--demo', action='store_true', help='显式加载虚构案例')
    parser.add_argument('--actor', default='local-operator')
    parser.add_argument('--role', choices=['operator', 'reviewer'], default='operator')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    from .core import Store
    if args.baseline:
        print(json.dumps(Store(args.db).set_baseline(json.loads(args.baseline.read_text(encoding='utf-8'))), ensure_ascii=False))
        return
    from .web import create_app
    import uvicorn
    uvicorn.run(create_app(args.db, actor=args.actor, role=args.role, demo=args.demo),
                host='127.0.0.1', port=args.port, log_level='info')


if __name__ == '__main__':
    main()
