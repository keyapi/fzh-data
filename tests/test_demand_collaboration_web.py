from fastapi.testclient import TestClient

from demand_collaboration.web import create_app


def test_actor_headers_cannot_impersonate_reviewer(tmp_path):
    client = TestClient(create_app(tmp_path / 'work.db', actor='alice', role='operator', demo=True))
    state = client.get('/api/state', headers={'X-Actor': 'boss', 'X-Role': 'reviewer'}).json()
    assert (state['actor'], state['role']) == ('alice', 'operator')
    assert client.post('/api/publish', json={'baseline_version': state['baseline']['version'],
                                           'as_of': '2026-11-16'}).status_code == 403


def test_demo_is_labelled_and_real_page_served(tmp_path):
    client = TestClient(create_app(tmp_path / 'work.db', demo=True))
    assert client.get('/api/state').json()['baseline']['demo'] is True
    assert client.get('/').status_code == 200


def test_cross_site_mutation_rejected(tmp_path):
    client = TestClient(create_app(tmp_path / 'work.db', demo=True))
    assert client.post('/api/proposals', json={}, headers={'Origin': 'https://attacker.invalid'}).status_code == 403


def test_no_silent_demo_when_not_enabled(tmp_path):
    state = TestClient(create_app(tmp_path / 'work.db')).get('/api/state').json()
    assert state['baseline'] is None


def test_publication_download_is_reviewer_only(tmp_path):
    operator = TestClient(create_app(tmp_path / 'work.db', actor='alice', role='operator'))
    assert operator.get('/api/publications/missing/download?format=json').status_code == 403
    reviewer = TestClient(create_app(tmp_path / 'work.db', actor='bob', role='reviewer'))
    assert reviewer.get('/api/publications/missing/download?format=json').status_code == 404


def test_untrusted_host_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path / 'work.db', demo=True))
    assert client.post('/api/proposals', json={}, headers={
        'Host': 'attacker.invalid', 'Origin': 'http://attacker.invalid'}).status_code == 400


def test_publication_json_and_parquet_keep_same_quantities(tmp_path):
    import io
    import pyarrow.parquet as pq
    client = TestClient(create_app(tmp_path / 'work.db', actor='manager', role='reviewer', demo=True))
    store = client.app.state.store
    store.submit(dict(id='p', row_id='demo-USNJ', event_id='promo', kind='delta', value=30,
                      start='2026-11-16', end='2026-11-22', reason='促销', evidence='示例计划',
                      baseline_version='synthetic-weekly-v1'), 'alice')
    decision = client.post('/api/proposals/p/decision', json={
        'status': 'approved', 'revision': 1, 'reason': '独立复核示例'})
    assert decision.status_code == 200, decision.text
    pub = client.post('/api/publish', json={
        'baseline_version': 'synthetic-weekly-v1', 'as_of': '2026-11-11'}).json()
    saved = client.get(f"/api/publications/{pub['id']}/download?format=json").json()
    parquet = client.get(f"/api/publications/{pub['id']}/download?format=parquet")
    table = pq.read_table(io.BytesIO(parquet.content))
    assert table.to_pylist() == saved['rows']
    assert table.schema.metadata[b'service_certified'] == b'false'
