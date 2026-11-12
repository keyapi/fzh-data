"""Frappe gateway contract tests with a stub runtime, NOT bench/HTTP acceptance."""
import importlib
import sys
from types import SimpleNamespace

import pytest


class Denied(Exception):
    pass


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    calls = []
    runtime = SimpleNamespace(session=SimpleNamespace(user='alice'),
        request=SimpleNamespace(method='POST'), local=SimpleNamespace(response={}),
        get_roles=lambda user: ['Demand Contributor'],
        get_site_path=lambda *parts: str(tmp_path.joinpath(*parts)),
        whitelist=lambda **kw: lambda fn: fn,
        PermissionError=Denied, throw=lambda message, exc=None: (_ for _ in ()).throw((exc or ValueError)(message)))
    monkeypatch.setitem(sys.modules, 'frappe', runtime)
    import demand_collaboration.frappe_bridge as module
    importlib.reload(module)
    store = SimpleNamespace(state=lambda: {'baseline': None, 'proposals': [], 'publications': []},
        submit=lambda payload, actor: calls.append(('submit', payload, actor)) or {'ok': True},
        decide=lambda *args: calls.append(('decide', *args)) or {'ok': True},
        publish=lambda *args: calls.append(('publish', *args)) or {'ok': True},
        publication=lambda ident: {'id': ident},
        record_audit=lambda *args: calls.append(('audit', *args)),
        set_baseline=lambda payload: calls.append(('baseline', payload)) or {'ok': True})
    monkeypatch.setattr(module, '_store', lambda: store)
    monkeypatch.setattr(module, '_allowed', lambda user, roles: None)
    return module, runtime, calls


def test_guest_and_unassigned_roles_denied(bridge):
    module, runtime, _ = bridge
    runtime.session.user = 'Guest'
    with pytest.raises(Denied):
        module.gateway('/api/state', 'GET')
    runtime.session.user = 'alice'
    runtime.get_roles = lambda user: []
    with pytest.raises(Denied):
        module.gateway('/api/state', 'GET')


def test_state_identity_comes_from_session(bridge):
    module, _, _ = bridge
    state = module.gateway('/api/state', 'GET')
    assert state['actor'] == 'alice' and state['role'] == 'operator'


def test_get_rpc_cannot_write_or_even_read(bridge):
    module, runtime, _ = bridge
    runtime.request.method = 'GET'
    with pytest.raises(Denied):
        module.gateway('/api/state', 'GET')


def test_role_and_author_spoof_rejected(bridge):
    module, _, calls = bridge
    with pytest.raises(ValueError):
        module.gateway('/api/proposals', 'POST', {'author': 'boss', 'role': 'reviewer'})
    assert calls == []


def test_submit_uses_actual_user(bridge):
    module, _, calls = bridge
    assert module.gateway('/api/proposals', 'POST', {'id': 'proposal-1'}) == {'ok': True}
    assert calls[0][-1] == 'alice'


def test_contributor_cannot_review_or_load(bridge):
    module, _, calls = bridge
    with pytest.raises(Denied):
        module.gateway('/api/proposals/p1/decision', 'POST', {'status': 'approved', 'revision': 1, 'reason': 'checked'})
    with pytest.raises(Denied):
        module.load_baseline({'version': 'bad'})
    assert calls == []


def test_reviewer_identity_and_revision_forwarded(bridge):
    module, runtime, calls = bridge
    runtime.session.user = 'manager'
    runtime.get_roles = lambda user: ['Demand Reviewer']
    module.gateway('/api/proposals/p1/decision', 'POST', {'status': 'approved', 'revision': 3, 'reason': 'checked'})
    assert calls == [('decide', 'p1', 'approved', 3, 'manager', 'reviewer', 'checked')]


def test_unknown_route_and_method_rejected(bridge):
    module, _, _ = bridge
    for path in ['/api/method/frappe.client.delete', '/api/publications/../secret', '/api/state/extra']:
        with pytest.raises(ValueError):
            module.gateway(path, 'GET')
    with pytest.raises(ValueError):
        module.gateway('/api/state', 'DELETE')


def test_only_system_manager_can_import(bridge):
    module, runtime, calls = bridge
    runtime.get_roles = lambda user: ['System Manager']
    module.load_baseline({'version': 'v1'})
    assert calls == [('baseline', {'version': 'v1'})]


def test_real_core_blocks_self_approval_and_accepts_other_reviewer(bridge, monkeypatch, tmp_path):
    module, runtime, _ = bridge
    from demand_collaboration.core import Store
    from demand_collaboration.web import demo_baseline
    store = Store(tmp_path / 'real-ledger.db')
    baseline = demo_baseline()
    store.set_baseline(baseline)
    monkeypatch.setattr(module, '_store', lambda: store)
    proposal = module.gateway('/api/proposals', 'POST', {
        'id': 'alice-event', 'row_id': 'demo-USNJ', 'event_id': 'promo-1',
        'kind': 'delta', 'value': 10, 'start': '2026-11-16', 'end': '2026-11-22',
        'reason': 'future campaign', 'evidence': 'confirmed plan',
        'baseline_version': baseline['version']})
    runtime.get_roles = lambda user: ['Demand Reviewer']
    with pytest.raises(ValueError):
        module.gateway('/api/proposals/alice-event/decision', 'POST', {
            'status': 'approved', 'revision': proposal['revision'], 'reason': 'reviewed'})
    runtime.session.user = 'bob'
    result = module.gateway('/api/proposals/alice-event/decision', 'POST', {
        'status': 'approved', 'revision': proposal['revision'], 'reason': 'independently reviewed'})
    assert result['status'] == 'approved'


def test_workbench_markup_has_session_transport_and_guest_gate(bridge):
    module, runtime, _ = bridge
    html = module.get_workbench_html()
    assert 'window.DEMAND_TRANSPORT' in html
    assert 'window.parent.frappe' in html
    assert '.gateway' in html
    assert html.index('window.DEMAND_TRANSPORT') < html.index("let state=")
    runtime.session.user = 'Guest'
    with pytest.raises(Denied):
        module.get_workbench_html()


def test_en_page_uses_srcdoc_without_top_navigation():
    from pathlib import Path
    script = Path('demand_collaboration/en_page.js').read_text(encoding='utf-8')
    assert 'get_workbench_html' in script
    assert 'srcdoc' in script
    assert 'allow-scripts allow-same-origin allow-forms' in script
    assert 'allow-top-navigation' not in script


def test_scope_filters_rows_and_blocks_cross_scope_submit(bridge, monkeypatch, tmp_path):
    module, runtime, _ = bridge
    from demand_collaboration.core import Store
    store = Store(tmp_path / 'real.db')
    store.set_baseline({"version": "v1", "as_of": "2026-11-11", "demo": True, "rows": [
        {"id": "a", "product_id": "KS1", "sku": "TT1", "name": "A", "branch": "USNJ",
         "unit": "件", "week": "2026-11-16", "baseline_qty": 100},
        {"id": "b", "product_id": "KS2", "sku": "TT2", "name": "B", "branch": "PL",
         "unit": "件", "week": "2026-11-16", "baseline_qty": 80}]})
    monkeypatch.setattr(module, '_store', lambda: store)
    monkeypatch.setattr(module, '_allowed', lambda user, roles: {("KS1", "USNJ")})
    state = module.gateway('/api/state', 'GET')
    assert [r['id'] for r in state['baseline']['rows']] == ['a']
    assert state['coverage'] == {'visible_rows': 1, 'baseline_rows': 2, 'scope': 'assigned'}
    assert state['publications'] == []
    base = {"event_id": "e", "kind": "delta", "value": 1, "start": "2026-11-16",
            "end": "2026-11-22", "reason": "r", "evidence": "e", "baseline_version": "v1"}
    with pytest.raises(Denied):
        module.gateway('/api/proposals', 'POST', dict(base, id='p2', row_id='b'))
    result = module.gateway('/api/proposals', 'POST', dict(base, id='p1', row_id='a'))
    assert result['status'] == 'submitted' and result['author'] == 'alice'


def test_contributor_cannot_read_publication_but_reviewer_can(bridge):
    module, runtime, _ = bridge
    with pytest.raises(Denied):
        module.gateway('/api/publications/p1', 'GET')
    runtime.get_roles = lambda user: ['Demand Reviewer']
    assert module.gateway('/api/publications/p1', 'GET') == {'id': 'p1'}


def test_set_scope_requires_system_manager_and_writes_site_private_file(bridge, tmp_path):
    module, runtime, _ = bridge
    with pytest.raises(Denied):
        module.set_scope({'assignments': []})
    runtime.get_roles = lambda user: ['System Manager']
    result = module.set_scope({'assignments': [
        {'user': 'alice', 'product_id': 'KS1', 'branch': 'USNJ', 'source': 'pilot'}]})
    assert result == {'ok': True, 'assignments': 1}
    from demand_collaboration import scope
    loaded = scope.load(tmp_path / 'private' / 'demand_scope.json')
    assert loaded['assignments'][0]['product_id'] == 'KS1'


def test_empty_payload_string_is_treated_as_empty_object(bridge):
    module, _, _ = bridge
    state = module.gateway('/api/state', 'GET', '')
    assert state['actor'] == 'alice'
