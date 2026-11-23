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
    parser.add_argument('--live-stock', action=argparse.BooleanOptionalAction, default=True,
                        help='读取 EN Tongtool Stock Latest 只读实时库存覆盖层（默认开）')
    parser.add_argument('--live-stock-env', default=None,
                        help='显式EN凭证文件；否则先读ERP_API_KEY/ERP_API_SECRET，再读仓库EN_API/.env')
    parser.add_argument('--live-stock-base', default=None, help='EN 站点基地址')
    parser.add_argument('--live-stock-cache', default=None,
                        help='实时库存私有缓存 JSON；默认 db 同目录 en_live_stock.json')
    parser.add_argument('--live-stock-ttl', type=int, default=60,
                        help='实时库存内存缓存秒数（默认60）')
    parser.add_argument('--live-stock-timeout', type=float, default=10,
                        help='EN 读取超时秒数（默认10）')
    args = parser.parse_args()
    from .core import Store
    if args.baseline:
        print(json.dumps(Store(args.db).set_baseline(json.loads(args.baseline.read_text(encoding='utf-8'))), ensure_ascii=False))
        return
    from .web import create_app
    provider = None
    if args.live_stock:
        from .live_stock import LiveStockSource
        cache = args.live_stock_cache
        if cache is None:
            cache = str(Path(args.db).parent / 'en_live_stock.json')
        source = LiveStockSource(env_file=args.live_stock_env,
                                 base=args.live_stock_base, cache_path=cache,
                                 timeout=args.live_stock_timeout,
                                 ttl_seconds=args.live_stock_ttl)
        provider = source.get
    import uvicorn
    uvicorn.run(create_app(args.db, actor=args.actor, role=args.role, demo=args.demo,
                          live_stock_provider=provider),
                host='127.0.0.1', port=args.port, log_level='info')


if __name__ == '__main__':
    main()
