import copy
import json
import unittest
from unittest.mock import Mock

from domain import DomainError
from bank_task_agent import run_task_agent


def reply(*calls, text=''):
    return {'choices': [{'message': {'content': text, 'tool_calls': [
        {'id': 'call-' + str(i), 'type': 'function', 'function':
         {'name': name, 'arguments': json.dumps(args)}} for i, (name, args) in enumerate(calls)]}}]}


class TaskAgentTests(unittest.TestCase):
    def setUp(self):
        self.tasks, self.store = Mock(), Mock()
        self.session = {'workspace': 'w', 'role': 'operator'}
        self.body = {'task_id': 't', 'text': '根据工单完成测试接入'}
        self.tasks.state.return_value = {'task': {'id': 't', 'status': 'draft', 'questions': []}, 'proposal': None, 'report': None}
        self.tasks.context.return_value = {'task': {'id': 't'}, 'bank': {'version': 1}, 'evidence': []}
        self.tasks.knowledge.return_value = {'documents': [], 'evidence': []}
        self.tasks.prepare.return_value = {'id': 'p', 'status': 'pending', 'summary': {'operation_count': 5}}
        self.plan = {'operations': [], 'explanation': '按现行规范补齐接入'}

    def test_reads_then_prepares_without_execution(self):
        model = Mock(side_effect=[reply(('read_task_context', {}), ('search_task_knowledge', {'query': '异步接入'})),
                                  reply(('prepare_task_plan', self.plan))])
        out = run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.assertEqual(out['outcome'], 'ready')
        self.tasks.prepare.assert_called_once()
        self.tasks.execute.assert_not_called()
        self.assertNotIn('已保存', out['text'])

    def test_parallel_prepare_cannot_use_unseen_read_results(self):
        model = Mock(side_effect=[reply(('read_task_context', {}), ('search_task_knowledge', {'query': ''}),
                                       ('prepare_task_plan', self.plan)), reply(text='请补充工单信息。')])
        out = run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.tasks.prepare.assert_not_called()
        self.assertIsNone(out['proposal'])

    def test_backend_evidence_error_can_be_corrected_once(self):
        self.tasks.prepare.side_effect = [DomainError('INVALID_EVIDENCE', '来源不适用'), self.tasks.prepare.return_value]
        model = Mock(side_effect=[reply(('read_task_context', {}), ('search_task_knowledge', {'query': ''})),
                                  reply(('prepare_task_plan', self.plan)), reply(('prepare_task_plan', self.plan))])
        out = run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.assertEqual(out['outcome'], 'ready')
        self.assertEqual(self.tasks.prepare.call_count, 2)

    def test_repeated_invalid_evidence_stops(self):
        self.tasks.prepare.side_effect = DomainError('INVALID_EVIDENCE', '来源不适用')
        model = Mock(side_effect=[reply(('read_task_context', {}), ('search_task_knowledge', {'query': ''})),
                                  reply(('prepare_task_plan', self.plan)), reply(('prepare_task_plan', self.plan))])
        out = run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.assertEqual(out['outcome'], 'denied')
        self.assertEqual(self.tasks.prepare.call_count, 2)

    def test_plain_success_cannot_claim_execution(self):
        model = Mock(return_value=reply(text='所有配置已保存成功，已完成接入。'))
        out = run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.assertEqual(out['outcome'], 'not_prepared')
        self.assertNotIn('已保存成功', out['text'])

    def test_port_answer_is_scoped_to_current_question(self):
        self.tasks.state.return_value['task']['questions'] = [{'id': 'client_port', 'field': 'client_port'}]
        self.body['text'] = '端口是9443'
        model = Mock(return_value=reply(text='继续核对工单。'))
        run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.tasks.answer.assert_called_once_with('w', 'operator', 't', 'client_port', 9443)

    def test_unrelated_number_is_not_port_answer(self):
        self.tasks.state.return_value['task']['questions'] = [{'id': 'client_port', 'field': 'client_port'}]
        self.body['text'] = '超时改成80秒'
        model = Mock(return_value=reply(text='当前缺的是客户端端口，请明确端口。'))
        run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.tasks.answer.assert_not_called()

    def test_reader_cannot_reach_model_or_mutation(self):
        self.session['role'] = 'reader'
        self.tasks.state.side_effect = DomainError('FORBIDDEN', '当前岗位不能办理', 403)
        model = Mock()
        with self.assertRaises(DomainError):
            run_task_agent(self.session, self.body, self.tasks, self.store, model)
        model.assert_not_called()

    def test_tool_budget_stops_read_loop(self):
        model = Mock(return_value=reply(('read_task_context', {})))
        out = run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.assertLessEqual(model.call_count, 8)
        self.assertEqual(out['outcome'], 'not_prepared')

    def test_history_is_task_scoped(self):
        self.session['task_history'] = {'other': [{'role': 'user', 'content': '私有旧任务'}]}
        captured = []
        def model(messages, tools):
            captured.append(copy.deepcopy(messages))
            return reply(text='请核对任务。')
        run_task_agent(self.session, self.body, self.tasks, self.store, model)
        self.assertNotIn('私有旧任务', json.dumps(captured, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
