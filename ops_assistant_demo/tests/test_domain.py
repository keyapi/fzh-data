import tempfile
import unittest
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from domain import Store, DomainError


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / 'state.sqlite'))

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def propose(self, **kw):
        return self.store.propose('one', 'operator', 'integration',
                                  [{'field': 'timeout', 'value': 60}, {'field': 'retries', 'value': 1}],
                                  '根据有效规范与复盘调整联调配置', **kw)

    def config(self, workspace='one', scenario='integration', env='test'):
        return next(c for c in self.store.snapshot(workspace, 'operator')['configs']
                    if c['scenario'] == scenario and c['environment'] == env)

    def assertCode(self, code, fn):
        with self.assertRaises(DomainError) as raised:
            fn()
        self.assertEqual(raised.exception.code, code)

    def test_propose_does_not_write_execute_readbacks_and_is_idempotent(self):
        p = self.propose()
        self.assertEqual(self.config()['values']['timeout'], 30)
        result = self.store.execute('one', 'operator', p['id'], p['digest'])
        self.assertTrue(result['ok'])
        self.assertEqual(self.config()['values'], {'timeout': 60, 'retries': 1})
        self.assertEqual(self.config(env='prod')['values']['timeout'], 30)
        self.store.execute('one', 'operator', p['id'], p['digest'])
        self.assertEqual(len(self.store.snapshot('one', 'operator')['tickets']), 1)
        self.assertEqual(self.config()['version'], 2)

    def test_workspace_and_persistent_state(self):
        p = self.propose()
        self.store.execute('one', 'operator', p['id'], p['digest'])
        self.assertEqual(self.config('other')['values']['timeout'], 30)
        new = Store(self.store.path)
        self.assertEqual(new.snapshot('one', 'operator')['configs'][0]['version'], 2)
        new.db.close()
        self.assertCode('NOT_FOUND', lambda: self.store.execute('other', 'operator', p['id'], p['digest']))

    def test_permissions_are_rechecked_at_execution(self):
        p = self.propose()
        self.assertCode('FORBIDDEN', lambda: self.store.execute('one', 'reader', p['id'], p['digest']))
        self.assertCode('FORBIDDEN', lambda: self.store.execute('one', 'reviewer', p['id'], p['digest']))
        self.assertTrue(all(c['environment'] == 'test' for c in self.store.snapshot('one', 'reader')['configs']))

    def test_tamper_stale_expired_cancelled(self):
        p = self.propose()
        self.assertCode('DIGEST_MISMATCH', lambda: self.store.execute('one', 'operator', p['id'], 'fake'))
        other = self.propose(submit=False)
        self.store.execute('one', 'operator', other['id'], other['digest'])
        self.assertCode('STALE', lambda: self.store.execute('one', 'operator', p['id'], p['digest']))
        p = self.store.propose('two', 'operator', 'counter', [{'field': 'limit', 'value': 150000}], 'test')
        with patch('domain.time.time', return_value=p['expires_at'] + 1):
            self.assertCode('EXPIRED', lambda: self.store.execute('two', 'operator', p['id'], p['digest']))
        p = self.store.propose('three', 'operator', 'counter', [{'field': 'limit', 'value': 150000}], 'test')
        self.store.cancel('three', 'operator', p['id'])
        self.assertCode('CANCELLED', lambda: self.store.execute('three', 'operator', p['id'], p['digest']))

    def test_structured_validation_fails_closed(self):
        for changes in ([{'field': 'timeout', 'value': 999}], [{'field': 'password', 'value': 1}],
                        [{'field': 'timeout', 'value': True}], [{'field': 'timeout', 'value': float('nan')}],
                        [{'field': 'timeout', 'value': 60, 'environment': 'prod'}],
                        [{'field': 'timeout', 'value': 60}] * 2):
            self.assertCode('INVALID_CHANGE', lambda: self.store.propose('one', 'operator', 'integration', changes, 'x'))

    def test_noop_does_not_submit_production_ticket(self):
        p = self.store.propose('one', 'operator', 'counter', [{'field': 'limit', 'value': 500000}], 'x')
        result = self.store.execute('one', 'operator', p['id'], p['digest'])
        self.assertEqual(result['code'], 'NO_CHANGE')
        self.assertEqual(self.store.snapshot('one', 'operator')['tickets'], [])

    def test_rollback_requires_fresh_confirmation(self):
        p = self.propose()
        self.store.execute('one', 'operator', p['id'], p['digest'])
        restore = self.store.rollback('one', 'operator', p['id'])
        self.assertEqual(self.config()['values']['timeout'], 60)
        self.store.execute('one', 'operator', restore['id'], restore['digest'])
        self.assertEqual(self.config()['values']['timeout'], 30)

    def test_review_changes_request_only(self):
        p = self.propose()
        self.store.execute('one', 'operator', p['id'], p['digest'])
        ticket = self.store.snapshot('one', 'operator')['tickets'][0]
        self.assertCode('FORBIDDEN', lambda: self.store.review('one', 'operator', ticket['id'], True))
        self.store.review('one', 'reviewer', ticket['id'], True)
        self.assertEqual(self.config(env='prod')['values']['timeout'], 30)

    def test_all_safety_cases_isolated_and_real_guards(self):
        before = self.store.snapshot('one', 'operator')['configs']
        for case in ('unauthorized', 'tamper', 'stale', 'repeat', 'injection', 'production', 'unknown', 'failure'):
            with self.subTest(case=case):
                self.assertTrue(self.store.safety_test('one', 'operator', case)['passed'])
        self.assertEqual(self.store.snapshot('one', 'operator')['configs'], before)

    def test_knowledge_filters_invalid_documents_before_retrieval(self):
        docs = self.store.knowledge('超时', 'reader')
        self.assertTrue(docs)
        self.assertTrue(all(d['status'] == 'active' and d['environment'] != 'prod' for d in docs))
        self.assertTrue(all('忽略规则' not in d['content'] for d in docs))

    def test_parallel_execute_writes_once(self):
        p = self.propose()
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.store.execute('one', 'operator', p['id'], p['digest']), range(8)))
        self.assertEqual(sum(r['code'] == 'EXECUTED' for r in results), 1)
        self.assertEqual(len(self.store.snapshot('one', 'operator')['tickets']), 1)

    def test_storage_abort_rolls_back_config_ticket_and_proposal(self):
        p = self.propose()
        before = self.store.snapshot('one', 'operator')
        self.store.db.execute("CREATE TEMP TRIGGER fail_save BEFORE INSERT ON workspaces BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.execute('one', 'operator', p['id'], p['digest'])
        self.store.db.execute('DROP TRIGGER fail_save')
        after = self.store.snapshot('one', 'operator')
        for key in ('configs', 'tickets', 'proposals'):
            self.assertEqual(after[key], before[key])

    def test_reset_cancels_pending_proposals_and_keeps_audit(self):
        p = self.propose()
        self.store.reset('one', 'operator')
        self.assertCode('CANCELLED', lambda: self.store.execute('one', 'operator', p['id'], p['digest']))
        self.assertTrue(any(a['action'] == 'reset' for a in self.store.audit('one', 'operator')))

    def test_rollback_does_not_overwrite_later_changes(self):
        p = self.propose()
        self.store.execute('one', 'operator', p['id'], p['digest'])
        later = self.store.propose('one', 'operator', 'integration', [{'field': 'timeout', 'value': 45}], 'later', False)
        self.store.execute('one', 'operator', later['id'], later['digest'])
        self.assertCode('STALE', lambda: self.store.rollback('one', 'operator', p['id']))
        self.assertEqual(self.config()['values']['timeout'], 45)

    def test_denial_audit_cannot_overwrite_another_store_commit(self):
        p = self.propose()
        peer = Store(self.store.path)
        started, finished = threading.Event(), threading.Event()
        original_record = self.store._record
        futures = []
        def peer_change():
            started.set()
            newer = peer.propose('one', 'operator', 'integration',
                                 [{'field': 'timeout', 'value': 45}], 'another session', False)
            peer.execute('one', 'operator', newer['id'], newer['digest'])
            finished.set()
        with ThreadPoolExecutor(max_workers=1) as pool:
            def record(*args, **kwargs):
                if len(args) > 3 and args[3] == 'denied':
                    futures.append(pool.submit(peer_change))
                    self.assertTrue(started.wait(1))
                    # Allow the peer to commit if denial processing released the
                    # SQLite lock. Correct code keeps it until audit commit.
                    finished.wait(0.25)
                return original_record(*args, **kwargs)
            try:
                with patch.object(self.store, '_record', side_effect=record):
                    self.assertCode('DIGEST_MISMATCH', lambda: self.store.execute('one', 'operator', p['id'], 'tampered'))
                for future in futures:
                    future.result(timeout=6)
                self.assertEqual(self.config()['values']['timeout'], 45)
                history = self.store.audit('one', 'operator')
                self.assertTrue(any(a['outcome'] == 'denied' for a in history))
                self.assertTrue(any(a['outcome'] == 'success' for a in history))
            finally:
                peer.db.close()

    def test_counter_rejects_fractional_and_boolean_amounts(self):
        for value in (150000.5, True, False, 10 ** 400):
            with self.subTest(value=value):
                self.assertCode('INVALID_CHANGE', lambda: self.store.propose('one', 'operator', 'counter',
                               [{'field': 'limit', 'value': value}], 'explicit amount'))

    def test_review_requires_boolean_and_retains_pending_ticket(self):
        p = self.propose()
        self.store.execute('one', 'operator', p['id'], p['digest'])
        ticket = self.store.snapshot('one', 'reviewer')['tickets'][0]
        for value in ('false', 1, None):
            self.assertCode('INVALID_CHANGE', lambda: self.store.review('one', 'reviewer', ticket['id'], value))
        self.assertEqual(self.store.snapshot('one', 'reviewer')['tickets'][0]['status'], 'pending_review')

    def test_noop_audit_is_queryable_and_does_not_change_version(self):
        p = self.store.propose('one', 'operator', 'counter', [{'field': 'limit', 'value': 500000}], 'same amount')
        self.store.execute('one', 'operator', p['id'], p['digest'])
        self.assertEqual(self.config(scenario='counter')['version'], 1)
        record = next(a for a in self.store.audit('one', 'operator') if a['outcome'] == 'no_change')
        self.assertEqual(record['before'], record['after'])
        self.assertEqual(record['proposal_id'], p['id'])
        self.assertEqual(self.store.audit('other', 'operator'), [])
        self.assertEqual(self.store.audit('one', 'reader'), [])

    def test_injection_case_describes_executor_boundary_not_detection(self):
        result = self.store.safety_test('one', 'operator', 'injection')
        self.assertIn('不宣称检测全部提示注入', result['detail'])
        self.assertEqual(result['document']['status'], 'fixture')

    def test_record_denial_preserves_configs_and_exposes_structured_audit(self):
        before = self.store.snapshot('one', 'operator')['configs']
        result = self.store.record_denial('one', 'operator', 'request_production_write',
                                         'PRODUCTION_FORBIDDEN', '生产写入能力未开放')
        self.assertTrue(result['ok'])
        self.assertEqual(self.store.snapshot('one', 'operator')['configs'], before)
        record = self.store.audit('one', 'operator')[-1]
        self.assertEqual(record['action'], 'request_production_write')
        self.assertEqual(record['outcome'], 'denied')
        self.assertEqual(record['code'], 'PRODUCTION_FORBIDDEN')
        self.assertEqual(record['detail'], '生产写入能力未开放')

    def test_reader_denial_is_recorded_without_exposing_audit(self):
        self.store.record_denial('one', 'reader', 'export_customers', 'EXPORT_FORBIDDEN', '未开放导出能力')
        self.assertEqual(self.store.snapshot('one', 'reader')['audit'], [])
        record = self.store.audit('one', 'operator')[-1]
        self.assertEqual(record['actor'], 'reader')
        self.assertEqual(record['code'], 'EXPORT_FORBIDDEN')
        self.assertEqual(self.store.audit('other', 'operator'), [])


if __name__ == '__main__':
    unittest.main()
