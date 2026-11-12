"""EN RPC bridge, to be installed in a trusted Frappe app; no automatic deployment.

Uses Frappe's session/CSRF gate and site-private ledger. This module deliberately
does not trust forwarded role/actor headers or expose an arbitrary RPC proxy.
The two custom roles must be provisioned and reviewed by a site administrator.
"""
import json
import re
from pathlib import Path

try:
    import frappe
except ImportError:  # Local core/web development has no Frappe dependency.
    frappe = None

from . import scope


def _exposed(fn):
    return frappe.whitelist(methods=['POST'])(fn) if frappe else fn


def _fail(message, status=422):
    frappe.local.response['http_status_code'] = status
    error = getattr(frappe, 'ValidationError', ValueError)
    frappe.throw(message, error)


def _identity():
    if frappe is None:
        raise RuntimeError('EN bridge requires the Frappe runtime')
    user = frappe.session.user
    if not user or user == 'Guest' or getattr(frappe.request, 'method', None) != 'POST':
        frappe.throw('请登录后使用POST提交需求协同请求', frappe.PermissionError)
    roles = set(frappe.get_roles(user))
    if not roles.intersection({'Demand Contributor', 'Demand Reviewer', 'System Manager'}):
        frappe.throw('没有需求协同访问权限', frappe.PermissionError)
    return user, ('reviewer' if roles.intersection({'Demand Reviewer', 'System Manager'}) else 'operator'), roles


def _store():
    from .core import Store
    path = Path(frappe.get_site_path('private', 'demand_collaboration.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    return Store(path)


def _scope_file():
    return Path(frappe.get_site_path('private', 'demand_scope.json'))


def _allowed(user, roles):
    if scope.all_scope(roles):
        return None
    return scope.keys_for(scope.load(_scope_file()), user)


def _payload(value):
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            _fail('payload必须为JSON对象')
    if value is None:
        return {}
    if not isinstance(value, dict):
        _fail('payload必须为JSON对象')
    if {'role', 'actor', 'author', 'reviewer', 'approved_by'} & value.keys():
        _fail('身份由EN登录会话决定，不接受客户端身份字段')
    return value


def _invoke(action):
    from .core import DomainError
    try:
        return action()
    except DomainError as exc:
        _fail(f'{exc.code}: {exc.message}', exc.status_code)


@_exposed
def gateway(path, method='GET', payload=None):
    """POST /api/method/<installed-module>.gateway with explicit REST-shaped path.

    State/proposals are scoped to the caller's product x branch assignments;
    publication objects are reviewer/System Manager only because each snapshot
    embeds every row.
    """
    actor, role, roles = _identity()
    data = _payload(payload)
    allowed = _allowed(actor, roles)
    if method not in {'GET', 'POST'} or not isinstance(path, str):
        _fail('不支持的方法或路径')
    if path == '/api/state' and method == 'GET':
        return scope.filter_state({**_store().state(), 'actor': actor, 'role': role}, allowed)
    if path == '/api/proposals' and method == 'POST':
        baseline = (_store().state() or {}).get('baseline') or {}
        row = next((r for r in baseline.get('rows', []) if r.get('id') == data.get('row_id')), None)
        if not scope.in_scope(row, allowed):
            frappe.throw('该商品/分公司不在你的授权范围', frappe.PermissionError)
        return _invoke(lambda: _store().submit(data, actor))
    decision = re.fullmatch(r'/api/proposals/([A-Za-z0-9_-]+)/decision', path)
    if decision and method == 'POST':
        if role != 'reviewer':
            frappe.throw('只有需求审核人可裁决提案', frappe.PermissionError)
        if set(data) != {'status', 'revision', 'reason'}:
            _fail('裁决必须包含status/revision/reason')
        return _invoke(lambda: _store().decide(decision[1], data['status'], data['revision'], actor, role, data['reason']))
    if path == '/api/publish' and method == 'POST':
        if role != 'reviewer':
            frappe.throw('只有需求审核人可发布', frappe.PermissionError)
        if set(data) != {'baseline_version', 'as_of'}:
            _fail('发布必须包含baseline_version/as_of')
        return _invoke(lambda: _store().publish(data['baseline_version'], data['as_of'], actor, role))
    publication = re.fullmatch(r'/api/publications/([A-Za-z0-9_-]+)', path)
    if publication and method == 'GET':
        if not scope.can_read_publication(roles):
            frappe.throw('发布快照仅需求审核人可读', frappe.PermissionError)
        return _invoke(lambda: _store().publication(publication[1]))
    _fail('未知需求协同路径')


@_exposed
def set_scope(payload):
    """Replace operator -> product x branch assignments (System Manager only)."""
    actor, _, roles = _identity()
    if 'System Manager' not in roles:
        frappe.throw('只有SystemManager可维护运营范围', frappe.PermissionError)
    data = _payload(payload)
    try:
        normalized = scope.save(_scope_file(), data, actor)
    except scope.ScopeError as exc:
        _fail(str(exc))
    _store().record_audit(actor, 'scope_updated', 'scope',
                          {'assignments': len(normalized['assignments'])})
    return {'ok': True, 'assignments': len(normalized['assignments'])}


@_exposed
def load_baseline(payload):
    """Import an explicit baseline object; never reads a caller-supplied file path."""
    _, _, roles = _identity()
    if 'System Manager' not in roles:
        frappe.throw('只有System Manager可导入基准', frappe.PermissionError)
    return _invoke(lambda: _store().set_baseline(_payload(payload)))


@_exposed
def get_workbench_html():
    """Session-gated UI for a same-origin Desk Page iframe; no install side effects."""
    _identity()
    endpoint = json.dumps(__name__ + '.gateway')
    transport = r"""<script>
window.DEMAND_TRANSPORT = async function(path, options) {
  options = options || {};
  const client = window.parent.frappe;
  if (!client || !client.xcall) throw new Error('请在EN登录页面中打开需求协同');
  const url = new URL(path, window.parent.location.origin);
  let route = url.pathname;
  if (/^\/api\/publications\/[A-Za-z0-9_-]+\/download$/.test(route)) {
    if ((url.searchParams.get('format') || 'json') !== 'json')
      throw new Error('EN桥接当前仅提供JSON快照，Parquet尚未验收');
    route = route.replace(/\/download$/, '');
  }
  try {
    return await client.xcall(ENDPOINT, {
      path: route, method: options.method || 'GET',
      payload: options.body ? JSON.parse(options.body) : null
    });
  } catch (error) {
    const response = error && (error.responseJSON || error);
    let detail = response && (response.message || response.exc_type);
    try {
      const messages = JSON.parse(response._server_messages || '[]');
      if (messages.length) {
        const last = typeof messages[messages.length-1] === 'string'
          ? JSON.parse(messages[messages.length-1]) : messages[messages.length-1];
        detail = last.message || detail;
      }
    } catch (_) {}
    throw new Error(detail || 'EN请求失败，请刷新后核对权限与提案状态');
  }
};
</script>""".replace('ENDPOINT', endpoint)
    markup = (Path(__file__).parent / 'static' / 'index.html').read_text(encoding='utf-8')
    return markup.replace('<head>', '<head>\n' + transport, 1)
