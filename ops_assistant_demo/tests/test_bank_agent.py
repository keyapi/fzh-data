import json
import unittest
from unittest.mock import Mock

from domain import DomainError
from domain import Store
from bank_ops import BankOperations
from bank_agent import run_bank_agent


def response(*calls, content=''):
    return {'choices': [{'message': {'role': 'assistant', 'content': content,
        'tool_calls': [{'id': str(i), 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(args)}} for i, (name, args) in enumerate(calls)]}}]}


class BankAgentTests(unittest.TestCase):
    def test_negative_numeric_target_must_be_explicit(self):
        from bank_agent import _check_targets
        with self.assertRaises(DomainError):
            _check_targets({'value': '-999'}, ['改一下'])
        _check_targets({'value': '-999'}, ['改为-999'])

    def setUp(self):
        self.session = {'role': 'operator', 'workspace': 'isolated-demo'}
        self.bank = Mock()
        self.bank.snapshot.return_value = {'terminals': [], 'parameters': [], 'ip_configs': []}
        self.bank.propose.return_value = {'id': 'p1', 'status': 'pending'}
        self.store = Mock()
        self.body = {'text': '把前置端口改为9001', 'entity': 'ip', 'active_terminal_id': 'TERM-DEMO-01'}
        self.args = {'entity': 'ip', 'action': 'update', 'record_id': 'IP-DEMO-01',
                     'values': {'front_port': 9001}, 'reason': '用户要求'}

    def test_reads_and_rules_before_prepare(self):
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', self.args))])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'ready')
        self.assertEqual(result['proposal']['id'], 'p1')
        self.bank.propose.assert_called_once()
        self.assertNotIn('已保存', result['text'])

    def test_reader_cannot_prepare(self):
        self.session['role'] = 'reader'
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', self.args))])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'denied')
        self.bank.propose.assert_not_called()

    def test_plain_model_success_is_not_a_saved_result(self):
        model = Mock(return_value=response(content='已经保存成功。'))
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'not_prepared')
        self.assertNotIn('已经保存成功', result['text'])
        self.bank.propose.assert_not_called()

    def test_stale_record_backend_denial_wins(self):
        self.bank.propose.side_effect = DomainError('NOT_FOUND', '记录不存在，请重新选择。')
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', self.args), content='已成功。')])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'denied')
        self.assertIsNone(result['proposal'])
        self.assertIn('记录不存在', result['text'])

    def test_numeric_value_not_in_user_request_is_rejected(self):
        self.args['values']['front_port'] = 9002
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', self.args))])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'denied')
        self.bank.propose.assert_not_called()

    def test_same_round_prepare_cannot_use_unread_tool_results(self):
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {}),
                                  ('prepare_bank_change', self.args)), response(content='请确认目标记录。')])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertIsNone(result['proposal'])
        self.bank.propose.assert_not_called()

    def test_parameter_numeric_text_cannot_be_invented(self):
        self.body.update(entity='parameter', text='把超时改成70秒')
        args = dict(self.args, entity='parameter', values={'value': '90'})
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', args))])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'denied')
        self.bank.propose.assert_not_called()

    def test_same_entity_recent_user_goal_can_be_continued(self):
        self.body.update(entity='parameter', text='那就按刚才说的修改')
        self.session['bank_history'] = {'parameter': [{'role': 'user', 'content': '超时改为70秒'},
                                                   {'role': 'assistant', 'content': '请确认终端。'}]}
        args = dict(self.args, entity='parameter', values={'value': '70'})
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', args))])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'ready')

    def test_other_entity_history_cannot_supply_target(self):
        self.session['bank_history'] = {'terminal': [{'role': 'user', 'content': '端口改为9002'}]}
        self.args['values']['front_port'] = 9002
        model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                  response(('prepare_bank_change', self.args))])
        result = run_bank_agent(self.session, self.body, self.bank, self.store, model)
        self.assertEqual(result['outcome'], 'denied')


class BankAgentBackendTests(unittest.TestCase):
    def test_real_prepare_does_not_write_parameter(self):
        store = Store(':memory:')
        try:
            bank = BankOperations(store)
            session = {'role': 'operator', 'workspace': 'real-controller'}
            body = {'entity': 'parameter', 'text': '把超时改成70秒', 'active_terminal_id': 'TERM-DEMO-001'}
            args = {'entity': 'parameter', 'action': 'update', 'record_id': 'PARAM-DEMO-001',
                    'values': {'value': '70'}, 'reason': '模拟超时调整'}
            model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                      response(('prepare_bank_change', args))])
            result = run_bank_agent(session, body, bank, store, model)
            self.assertEqual(result['outcome'], 'ready')
            self.assertEqual(bank.snapshot(session['workspace'], 'operator')['parameters'][0]['value'], '30')
            self.assertEqual(result['proposal']['status'], 'pending')
        finally:
            store.db.close()

    def test_missing_create_fields_get_backend_denial(self):
        store = Store(':memory:')
        try:
            bank = BankOperations(store)
            session = {'role': 'operator', 'workspace': 'real-controller'}
            body = {'entity': 'terminal', 'text': '新增终端名字叫演示终端'}
            args = {'entity': 'terminal', 'action': 'create', 'values': {'terminal_name': '演示终端'}, 'reason': '新增演示'}
            model = Mock(side_effect=[response(('read_bank_state', {}), ('search_bank_rules', {})),
                                      response(('prepare_bank_change', args))])
            result = run_bank_agent(session, body, bank, store, model)
            self.assertEqual(result['outcome'], 'denied')
            self.assertIsNone(result['proposal'])
            self.assertEqual(len(bank.snapshot(session['workspace'], 'operator')['terminals']), 1)
        finally:
            store.db.close()


if __name__ == '__main__':
    unittest.main()
