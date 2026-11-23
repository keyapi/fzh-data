"""Loopback workbench; identities come from server configuration, never request headers."""
import io
import json
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import DomainError, Store
from .live_stock import attach_to_snapshot
from .recommendation_scope import filter_snapshot


def demo_baseline():
    return {'version': 'synthetic-weekly-v1', 'as_of': '2026-11-11', 'demo': True,
            'rows': [dict(id=f'demo-{branch}', product_id=f'EXAMPLE-{branch}',
                          sku=f'示例-{branch}', name=name, branch=branch, unit='件',
                          week='2026-11-16', baseline_qty=qty,
                          history=[20, 23, 18, 25, 21, 28], inventory_qty=None,
                          supply_note='构想案例，未读取真实库存或EN供给')
                     for branch, name, qty in [('USNJ', '三角靠枕 · 活动计划', 100),
                                               ('USTX', '弧形靠枕 · 推广收缩', 60),
                                               ('PL', '软包墙围 · 多人共识', 80)]]}


def create_app(db_path, actor='local-operator', role='operator', demo=False, scope_path=None,
               live_stock_provider=None):
    if role not in {'operator', 'reviewer'} or not actor.strip():
        raise ValueError('invalid configured identity')
    store = Store(db_path)
    scope_path = scope_path or os.environ.get('DEMAND_RECOMMENDATION_SCOPE')
    if demo and store.state()['baseline'] is None:
        store.set_baseline(demo_baseline())
    app = FastAPI(title='运营需求协同', docs_url='/api/docs')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.state.store = store

    def with_live(view):
        """Decorate a read-only view with live EN stock; never touch the store."""
        if view is None or live_stock_provider is None:
            return view
        try:
            overlay = live_stock_provider()
        except Exception as exc:  # noqa: BLE001 - the page must stay readable
            overlay = {'schema': 'en-live-stock-overlay/v1', 'status': 'unavailable',
                       'stale': True, 'error': type(exc).__name__ + ': ' + str(exc),
                       'rows': []}
        return attach_to_snapshot(view, overlay)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        # This adapter is intentionally not a public multi-user authentication system.
        origin = request.headers.get('origin')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': '跨站写请求被拒绝'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({'detail': exc.message, 'code': exc.code}, status_code=exc.status_code)

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).parent / 'static' / 'index.html')

    @app.get('/api/state')
    def state():
        payload = store.state()
        payload['recommendation'] = with_live(
            filter_snapshot(payload.get('recommendation'), actor, role, scope_path))
        return {**payload, 'actor': actor, 'role': role}

    @app.get('/api/recommendations')
    def recommendations():
        return with_live(filter_snapshot(store.state()['recommendation'], actor, role, scope_path))

    @app.get('/api/recommendations/{snapshot_id}')
    def recommendation(snapshot_id: str):
        view = filter_snapshot(store.recommendation(snapshot_id), actor, role, scope_path)
        if view is None:
            raise DomainError(404, 'not_found', '建议快照不存在')
        if role == 'operator' and not view.get('visible_count'):
            raise DomainError(403, 'out_of_scope', '该建议快照不在你的范围')
        return with_live(view)

    @app.post('/api/proposals')
    def submit(payload: dict):
        return store.submit(payload, actor)

    @app.post('/api/proposals/{proposal_id}/decision')
    def decide(proposal_id: str, payload: dict):
        if set(payload) != {'status', 'revision', 'reason'}:
            raise DomainError(422, 'invalid_fields', '决策字段必须为status/revision/reason')
        return store.decide(proposal_id, payload['status'], payload['revision'], actor, role, payload['reason'])

    @app.post('/api/publish')
    def publish(payload: dict):
        if set(payload) != {'baseline_version', 'as_of'}:
            raise DomainError(422, 'invalid_fields', '发布必须指定基准版本与截止日')
        return store.publish(payload['baseline_version'], payload['as_of'], actor, role)

    @app.get('/api/publications/{publication_id}/download')
    def download(publication_id: str, format: str = 'json'):
        publication = store.publication(publication_id)
        if format == 'json':
            content = json.dumps(publication, ensure_ascii=False, indent=2).encode('utf-8')
            return Response(content, media_type='application/json',
                            headers={'Content-Disposition': f'attachment; filename="{publication_id}.json"'})
        if format == 'parquet':
            import pyarrow as pa
            import pyarrow.parquet as pq
            table = pa.Table.from_pylist(publication['rows'])
            table = table.replace_schema_metadata({b'publication': publication_id.encode(),
                b'baseline_version': publication['baseline_version'].encode(),
                b'service_certified': b'false'})
            buffer = io.BytesIO()
            pq.write_table(table, buffer)
            return Response(buffer.getvalue(), media_type='application/vnd.apache.parquet',
                            headers={'Content-Disposition': f'attachment; filename="{publication_id}.parquet"'})
        raise DomainError(422, 'invalid_format', '支持json或parquet')

    return app
