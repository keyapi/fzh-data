import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domain import DomainError, Store
from bank_ops import BankOperations
from bank_tasks import BankTasks


class BankTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'tasks.sqlite')
        self.tasks = BankTasks(self.store)
        self.workspace = 'one'

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def code(self, code, call):
        with self.assertRaises(DomainError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def begin(self, ticket='WO-DEMO-001'):
        return self.tasks.start(self.workspace, 'operator', ticket)

    def plan(self, task, port=None):
        if task['ticket_id'] == 'WO-DEMO-001':
            self.tasks.ask(self.workspace, 'operator', task['id'], 'client_port', '客户端端口？')
            self.tasks.answer(self.workspace, 'operator', task['id'], 'client_port', 9443 if port is None else port)
        context = self.tasks.context(self.workspace, 'operator', task['id'])
        self.tasks.knowledge(self.workspace, 'operator', task['id'], '异步回调')
        task = context['task']
        profile = 'conservative' if task['ticket_id'] == 'WO-DEMO-002' else 'standard'
        values = {'standard': (12, 60, 1), 'conservative': (4, 45, 0)}[profile]
        client_port = 8443 if task['ticket_id'] == 'WO-DEMO-002' else 9443
        facts = context['evidence'] + self.tasks.knowledge(self.workspace, 'operator', task['id'], '异步回调')['evidence']

        def ref(target, value):
            return next(e['id'] for e in facts if target in e['allowed_targets'] and e['typed_value'] == value)

        operations = [
            {'entity': 'terminal', 'action': 'update', 'record_id': 'TERM-DEMO-001',
             'values': {'max_concurrency': values[0], 'callback_mode': 'ASYNC'},
             'source_refs': {'max_concurrency': [ref('terminal.max_concurrency', values[0])],
                             'callback_mode': [ref('terminal.callback_mode', 'ASYNC')]}},
            {'entity': 'parameter', 'action': 'update', 'record_id': 'PARAM-DEMO-001',
             'values': {'value': str(values[1])},
             'source_refs': {'value': [ref('parameter:timeout_seconds.value', str(values[1]))]}},
            {'entity': 'parameter', 'action': 'update', 'record_id': 'PARAM-DEMO-002',
             'values': {'value': str(values[2])},
             'source_refs': {'value': [ref('parameter:retry_count.value', str(values[2]))]}},
            {'entity': 'parameter', 'action': 'create', 'values': {'name': 'idempotency_enabled', 'value': 'true'},
             'source_refs': {'value': [ref('parameter:idempotency_enabled.value', 'true')]}},
            {'entity': 'ip', 'action': 'update', 'record_id': 'IP-DEMO-001',
             'values': {'client_port': client_port},
             'source_refs': {'client_port': [ref('ip.client_port', client_port)]}},
        ]
        return operations

    def test_question_source_and_complete_atomic_plan(self):
        task = self.begin()
        self.assertEqual(task['ticket_id'], 'WO-DEMO-001')
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['version'], 1)
        self.code('MISSING_INPUT', lambda: self.tasks.prepare('one', 'operator', task['id'], [], '办理'))
        ops = self.plan(task)
        proposal = self.tasks.prepare('one', 'operator', task['id'], ops, '依据当前规范办理')
        self.assertEqual(len(proposal['operations']), 5)
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['version'], 1)
        done = self.tasks.execute('one', 'operator', proposal['id'], proposal['digest'])
        self.assertTrue(done['verification']['passed'])
        self.assertTrue(done['report']['business_passed'])
        self.assertEqual(done['task']['status'], 'completed')
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['version'], 2)
        self.assertEqual(self.tasks.execute('one', 'operator', proposal['id'], proposal['digest'])['code'], 'ALREADY_EXECUTED')
        bank = BankOperations(self.store).snapshot('one', 'operator')
        self.assertEqual(bank['ip_configs'][1]['client_port'], 8080)
        self.assertEqual(len([p for p in bank['parameters'] if p['name'] == 'idempotency_enabled']), 1)

    def test_evidence_field_value_version_and_scope_are_server_checked(self):
        task = self.begin()
        ops = self.plan(task)
        ops[0]['values']['max_concurrency'] = 99
        self.code('INVALID_EVIDENCE', lambda: self.tasks.prepare('one', 'operator', task['id'], ops, '误用来源'))
        ops = self.plan(task)
        ops[2]['source_refs']['value'] = ops[1]['source_refs']['value']
        self.code('INVALID_EVIDENCE', lambda: self.tasks.prepare('one', 'operator', task['id'], ops, '错字段'))
        ops = self.plan(task)
        ops[0]['source_refs']['max_concurrency'] = ['ev-invented']
        self.code('INVALID_EVIDENCE', lambda: self.tasks.prepare('one', 'operator', task['id'], ops, '伪造'))
        self.code('FORBIDDEN', lambda: self.tasks.start('one', 'reader', 'WO-DEMO-001'))
        self.code('NOT_FOUND', lambda: self.tasks.context('other', 'operator', task['id']))

    def test_expiry_stale_reset_and_failed_sql_commit(self):
        task = self.begin()
        proposal = self.tasks.prepare('one', 'operator', task['id'], self.plan(task), '办理')
        self.code('DIGEST_MISMATCH', lambda: self.tasks.execute('one', 'operator', proposal['id'], 'bad'))
        with patch('bank_tasks.time.time', return_value=proposal['expires_at'] + 1):
            self.code('EXPIRED', lambda: self.tasks.execute('one', 'operator', proposal['id'], proposal['digest']))
        self.store.db.execute("CREATE TRIGGER stop_write BEFORE INSERT ON workspaces BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.tasks.execute('one', 'operator', proposal['id'], proposal['digest'])
        self.store.db.execute('DROP TRIGGER stop_write')
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['version'], 1)
        self.store.reset('one', 'operator')
        self.code('CANCELLED', lambda: self.tasks.execute('one', 'operator', proposal['id'], proposal['digest']))
        self.assertEqual(self.tasks.state('one', 'operator', task['id'])['task']['status'], 'invalidated')

    def test_variant_and_failed_business_acceptance_then_recover(self):
        variant = self.begin('WO-DEMO-002')
        p = self.tasks.prepare('one', 'operator', variant['id'], self.plan(variant), '保守档')
        result = self.tasks.execute('one', 'operator', p['id'], p['digest'])
        self.assertEqual(result['task']['status'], 'completed')
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['terminals'][0]['max_concurrency'], 4)
        self.store.reset('one', 'operator')
        failed = self.begin('WO-DEMO-003')
        p = self.tasks.prepare('one', 'operator', failed['id'], self.plan(failed), '失败夹具')
        result = self.tasks.execute('one', 'operator', p['id'], p['digest'])
        self.assertTrue(result['verification']['passed'])
        self.assertFalse(result['report']['business_passed'])
        self.assertEqual(result['task']['status'], 'verification_failed')
        recovery = self.tasks.recover('one', 'operator', failed['id'])
        restored = self.tasks.execute('one', 'operator', recovery['id'], recovery['digest'])
        self.assertEqual(restored['task']['status'], 'recovered')
        bank = BankOperations(self.store).snapshot('one', 'operator')
        self.assertEqual(bank['terminals'][0]['max_concurrency'], 8)
        self.assertFalse(any(p['name'] == 'idempotency_enabled' for p in bank['parameters']))

    def test_catalog_exposes_ticket_text_for_the_ui(self):
        catalog = self.tasks.catalog('one', 'operator')
        self.assertTrue(catalog['tickets'])
        self.assertTrue(all(t.get('text') for t in catalog['tickets']))
        self.assertTrue(all(d['id'].startswith('ticket-') for d in catalog['downloads']))

    def test_answer_clears_the_question_and_reask_returns_known_value(self):
        task = self.begin()
        self.assertEqual([q['id'] for q in task['questions']], ['client_port'])
        self.tasks.answer('one', 'operator', task['id'], 'client_port', 9443)
        state = self.tasks.state('one', 'operator', task['id'])['task']
        self.assertEqual(state['questions'], [])
        self.assertEqual(state['answered_questions'][0]['value'], 9443)
        asked = self.tasks.ask('one', 'operator', task['id'], 'client_port', '端口是多少？')
        self.assertIsNone(asked['question'])
        self.assertEqual(asked['known']['client_port'], 9443)

    def test_answer_rejects_string_port(self):
        task = self.begin()
        self.code('INVALID_ANSWER',
                  lambda: self.tasks.answer('one', 'operator', task['id'], 'client_port', '9443'))

    def test_verification_report_is_per_check_and_simulated(self):
        task = self.begin()
        p = self.tasks.prepare('one', 'operator', task['id'], self.plan(task), '办理')
        report = self.tasks.execute('one', 'operator', p['id'], p['digest'])['report']
        self.assertTrue(report['simulation'])
        self.assertEqual(report['source'], 'local_contract_simulator')
        self.assertEqual(report['fixture_version'], '1.0')
        self.assertTrue(report['passed'])
        names = [c['name'] for c in report['checks']]
        for expected in ('整组逐记录独立读回', '三页终端·参数·IP 一致性', '地址与回调契约（模拟）',
                         '幂等重复请求（模拟账本）', '超时与重试（虚拟耗时）', '范围未扩大'):
            self.assertIn(expected, names)
        readback = next(c for c in report['checks'] if c['name'] == '整组逐记录独立读回')
        self.assertIn('IP-DEMO-001', readback['detail'])
        self.assertIn('IP-DEMO-002', report['checks'][-1]['detail'])
        self.assertEqual(report['execution']['version_before'], 1)
        self.assertEqual(report['execution']['version_after'], 2)

    def test_rejected_receiver_reports_each_check_not_one_blob(self):
        task = self.begin('WO-DEMO-003')
        p = self.tasks.prepare('one', 'operator', task['id'], self.plan(task), '失败夹具')
        report = self.tasks.execute('one', 'operator', p['id'], p['digest'])['report']
        self.assertFalse(report['passed'])
        self.assertEqual([c['name'] for c in report['checks'] if not c['passed']],
                         ['地址与回调契约（模拟）'])
        self.assertEqual(len([c for c in report['checks'] if c['passed']]), 5)

    def test_readback_stale_when_bank_advances_after_commit(self):
        task = self.begin()
        p = self.tasks.prepare('one', 'operator', task['id'], self.plan(task), '办理')
        self.tasks.execute('one', 'operator', p['id'], p['digest'])
        follow = BankOperations(self.store).propose('one', 'operator', 'ip', 'update',
                                                    'IP-DEMO-002', {'client_port': 8081}, '他人后续修改')
        BankOperations(self.store).execute('one', 'operator', follow['id'], follow['digest'])
        self.code('READBACK_STALE', lambda: self.tasks.verify('one', 'operator', task['id']))

    def test_recovery_is_idempotent(self):
        task = self.begin('WO-DEMO-003')
        p = self.tasks.prepare('one', 'operator', task['id'], self.plan(task), '失败夹具')
        self.tasks.execute('one', 'operator', p['id'], p['digest'])
        recovery = self.tasks.recover('one', 'operator', task['id'])
        first = self.tasks.execute('one', 'operator', recovery['id'], recovery['digest'])
        self.assertEqual(first['task']['status'], 'recovered')
        version = BankOperations(self.store).snapshot('one', 'operator')['version']
        # Executing the same recovery proposal again is a no-op.
        again = self.tasks.execute('one', 'operator', recovery['id'], recovery['digest'])
        self.assertEqual(again['code'], 'ALREADY_EXECUTED')
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['version'], version)
        # Asking to recover again returns the existing result, not a new proposal.
        repeat = self.tasks.recover('one', 'operator', task['id'])
        self.assertEqual(repeat['id'], recovery['id'])
        self.assertEqual(repeat['status'], 'executed')
        self.assertEqual(BankOperations(self.store).snapshot('one', 'operator')['version'], version)


    def test_extra_value_keys_are_tolerated_but_wrong_values_are_not(self):
        task = self.begin()
        ops = self.plan(task)
        ops[1]['values'].update({'name': 'timeout_seconds', 'value_type': 'number'})
        ops[2]['values'].update({'name': 'retry_count', 'value_type': 'number'})
        ops[3]['values'].update({'terminal_id': 'TERM-DEMO-001', 'value_type': 'boolean', 'note': '备注'})
        proposal = self.tasks.prepare('one', 'operator', task['id'], ops, '多余字段应被忽略')
        self.assertEqual(len(proposal['operations']), 5)
        changed = next(op for op in proposal['operations'] if op['record_id'] == 'PARAM-DEMO-001')
        self.assertEqual(changed['values'], {'value': '60'})
        created = next(op for op in proposal['operations'] if op['action'] == 'create')
        self.assertEqual(created['after']['value_type'], 'text')

    def test_wrong_create_definition_is_rejected(self):
        task = self.begin()
        ops = self.plan(task)
        ops[3]['values'] = {'name': 'idempotency_enabled', 'value': 'false'}
        self.code('INVALID_PLAN', lambda: self.tasks.prepare('one', 'operator', task['id'], ops, '错值'))

    def test_already_compliant_ticket_reports_no_change(self):
        task = self.begin()
        p = self.tasks.prepare('one', 'operator', task['id'], self.plan(task), '办理')
        self.tasks.execute('one', 'operator', p['id'], p['digest'])
        again = self.begin()
        self.code('NO_CHANGE', lambda: self.tasks.prepare('one', 'operator', again['id'], self.plan(again), '再办一次'))
        bank = BankOperations(self.store).snapshot('one', 'operator')
        self.assertEqual(len([x for x in bank['parameters'] if x['name'] == 'idempotency_enabled']), 1)


if __name__ == '__main__':
    unittest.main()
