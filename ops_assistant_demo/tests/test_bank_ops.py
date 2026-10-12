import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domain import Store, DomainError, digest
from bank_ops import BankOperations, redact_all


class BankTests(unittest.TestCase):
    def test_no_change_does_not_create_confirmation_or_increase_version(self):
        self.code('NO_CHANGE', lambda: self.prepare(values={'max_concurrency': 8}))
        self.assertEqual(self.state()['version'], 1)
        self.assertEqual(self.store.snapshot('one', 'operator')['proposals'], [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'bank.sqlite')
        self.bank = BankOperations(self.store)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def state(self):
        return self.bank.snapshot('one', 'operator')

    def prepare(self, entity='terminal', action='update', record_id='TERM-DEMO-001', values=None):
        return self.bank.propose('one', 'operator', entity, action, record_id,
                                 values if values is not None else {'max_concurrency': 12}, '演示办理')

    def execute(self, p):
        return self.bank.execute('one', 'operator', p['id'], p['digest'])

    def code(self, code, fn):
        with self.assertRaises(DomainError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_confirm_update_and_readback_persistent_isolated(self):
        p = self.prepare()
        self.assertEqual(self.state()['terminals'][0]['max_concurrency'], 8)
        result = self.execute(p)
        self.assertEqual(result['record']['max_concurrency'], 12)
        self.assertTrue(result['verification']['passed'])
        self.assertEqual(self.execute(p)['code'], 'ALREADY_EXECUTED')
        self.assertEqual(self.state()['version'], 2)
        other = Store(self.store.path)
        self.assertEqual(BankOperations(other).snapshot('one', 'reader')['version'], 2)
        other.db.close()
        self.assertEqual(self.bank.snapshot('other', 'reader')['version'], 1)

    def test_create_update_delete_parameter(self):
        p = self.prepare('parameter', 'create', None, {'terminal_id': 'TERM-DEMO-001',
                         'name': 'response_mode', 'value': 'SYNC', 'value_type': 'text', 'note': '模拟'})
        created = self.execute(p)['record']
        self.execute(self.prepare('parameter', 'update', created['id'], {'value': 'ASYNC'}))
        result = self.execute(self.prepare('parameter', 'delete', created['id'], {}))
        self.assertIsNone(result['record'])
        self.assertTrue(result['verification']['passed'])
        self.assertNotIn(created['id'], [r['id'] for r in self.state()['parameters']])

    def test_ip_create_and_delete(self):
        values = {'terminal_id': 'TERM-DEMO-001', 'tenant_code': 'DEMO-BANK', 'tenant_id': 'TENANT-DEMO-01',
                  'front_address': '198.51.100.42', 'front_port': 8080,
                  'client_address': '203.0.113.42', 'client_port': 9090}
        record = self.execute(self.prepare('ip', 'create', None, values))['record']
        self.execute(self.prepare('ip', 'delete', record['id'], {}))
        self.assertEqual(len(self.state()['ip_configs']), 2)

    def test_roles_and_cross_workspace(self):
        for role in ('reader', 'reviewer', 'anonymous'):
            self.code('FORBIDDEN', lambda: self.bank.propose('one', role, 'terminal', 'update',
                      'TERM-DEMO-001', {'max_concurrency': 9}, '模拟'))
        p = self.prepare()
        self.code('FORBIDDEN', lambda: self.bank.execute('one', 'reviewer', p['id'], p['digest']))
        self.code('NOT_FOUND', lambda: self.bank.execute('other', 'operator', p['id'], p['digest']))

    def test_validation_unique_and_reference(self):
        for values in ({'surprise': 1}, {'max_concurrency': True}, {'max_concurrency': 1.5},
                       {'environment': 'prod'}, {'endpoint': 'https://example.com/api'}):
            self.code('INVALID_CHANGE', lambda: self.prepare(values=values))
        self.code('IN_USE', lambda: self.prepare('terminal', 'delete', 'TERM-DEMO-001', {}))
        self.code('INVALID_CHANGE', lambda: self.prepare('parameter', 'create', None,
                  {'terminal_id': 'missing', 'name': 'x', 'value': 'x', 'value_type': 'text', 'note': ''}))
        existing = self.state()['parameters'][0]
        self.code('DUPLICATE', lambda: self.prepare('parameter', 'create', None,
                  {k: v for k, v in existing.items() if k != 'id'}))
        for values in ({'front_address': '8.8.8.8'}, {'front_port': 0}, {'client_port': 65536}):
            self.code('INVALID_CHANGE', lambda: self.prepare('ip', 'update', 'IP-DEMO-001', values))

    def test_secret_never_echoed(self):
        p = self.prepare('parameter', 'create', None, {'terminal_id': 'TERM-DEMO-001', 'name': 'secondary_api_secret',
                         'value': 'DEMO_not_a_real_secret', 'value_type': 'text', 'note': '模拟'})
        self.assertEqual(p['after']['value'], '••••••')
        self.execute(p)
        import json
        self.assertNotIn('DEMO_not_a_real_secret', json.dumps(self.store.snapshot('one', 'operator')))
        self.assertNotIn('DEMO_SECRET', json.dumps(redact_all(self.store.snapshot('one', 'operator'))))
        self.code('INVALID_CHANGE', lambda: self.prepare('parameter', 'create', None,
                  {'terminal_id': 'TERM-DEMO-001', 'name': 'password', 'value': 'real-secret',
                   'value_type': 'secret', 'note': ''}))

    def test_digest_expiry_and_stale(self):
        p = self.prepare()
        self.code('DIGEST_MISMATCH', lambda: self.bank.execute('one', 'operator', p['id'], 'bad'))
        with patch('bank_ops.time.time', return_value=p['expires_at'] + 1):
            self.code('EXPIRED', lambda: self.execute(p))
        second = self.prepare(values={'max_concurrency': 15})
        self.execute(second)
        self.code('STALE', lambda: self.execute(p))

    def test_mutated_proposal_and_cancelled(self):
        p = self.prepare()
        def mutate(state):
            state['proposals'][-1]['after']['max_concurrency'] = 100
        self.store._transaction('one', 'operator', 'fixture', mutate)
        self.code('DIGEST_MISMATCH', lambda: self.execute(p))
        p = self.prepare()
        self.store.cancel('one', 'operator', p['id'])
        self.code('CANCELLED', lambda: self.execute(p))

    def test_sql_failure_atomic(self):
        p = self.prepare()
        self.store.db.execute("CREATE TRIGGER stop_write BEFORE INSERT ON workspaces BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.execute(p)
        self.store.db.execute('DROP TRIGGER stop_write')
        self.assertEqual(self.state()['terminals'][0]['max_concurrency'], 8)
        self.assertEqual(self.state()['version'], 1)

    def test_terminal_create_unique_and_delete_without_children(self):
        values = {k: v for k, v in self.state()['terminals'][0].items() if k != 'id'}
        self.code('DUPLICATE', lambda: self.prepare('terminal', 'create', None, values))
        values.update(terminal_code='DEMO-002', terminal_name='第二模拟终端')
        record = self.execute(self.prepare('terminal', 'create', None, values))['record']
        self.execute(self.prepare('terminal', 'delete', record['id'], {}))
        self.assertEqual(len(self.state()['terminals']), 1)

    def test_two_connections_approve_same_version_only_one_writes(self):
        from concurrent.futures import ThreadPoolExecutor
        p = self.prepare()
        q = self.prepare(values={'max_concurrency': 20})
        other = Store(self.store.path)
        def run(bank, proposal):
            try:
                return bank.execute('one', 'operator', proposal['id'], proposal['digest'])['code']
            except DomainError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda pair: run(*pair), [(self.bank, p), (BankOperations(other), q)]))
        other.db.close()
        self.assertEqual(sorted(codes), ['EXECUTED', 'STALE'])
        self.assertEqual(self.state()['version'], 2)


if __name__ == '__main__':
    unittest.main()
