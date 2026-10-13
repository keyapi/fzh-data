import unittest

from agent_runtime import AgentRuntime


class StubTools:
    def catalog(self, role):
        return {'items': [{'name': 'list_workorders', 'kind': 'read', 'roles': [role], 'description': '列工单'}]}

    def invoke(self, name, workspace, role, args):
        if name == 'list_workorders':
            return {'count': 3, 'items': [{'id': 'WO-DEMO-001'}], 'source': {'kind': 'fixture'}}
        raise AssertionError(name)


class AgentRuntimeTests(unittest.TestCase):
    def test_nonempty_reply_and_trace_are_returned_from_framework_result(self):
        runtime = AgentRuntime(StubTools())
        session = {}

        def runner(messages, system_prompt, tools):
            self.assertIn('能力目录', system_prompt)
            self.assertEqual(tools[0]['name'], 'list_workorders')
            return {'text': '当前有 3 份演练工单。',
                    'trace': [{'tool': 'list_workorders', 'result': {'count': 3}}]}

        result = runtime.turn(session, '我们有几个工单？', 'ws-1', 'operator', runner=runner)
        self.assertEqual(result['outcome'], 'answered')
        self.assertEqual(result['text'], '当前有 3 份演练工单。')
        self.assertEqual(result['trace'][0]['result']['count'], 3)
        self.assertEqual(len(session['unified_agent_history']), 2)

    def test_blank_model_reply_has_visible_terminal_fallback(self):
        runtime = AgentRuntime(StubTools())
        result = runtime.turn({}, '问一下', 'ws-1', 'operator',
                              runner=lambda *_: {'text': '', 'trace': []})
        self.assertEqual(result['outcome'], 'failed')
        self.assertIn('没有形成可核验回复', result['text'])

    def test_history_is_scoped_to_workspace_and_bounded(self):
        runtime = AgentRuntime(StubTools())
        session = {'unified_agent_history': [{'role': 'user', 'content': str(i)} for i in range(50)],
                   'unified_agent_workspace': 'old'}
        runtime.turn(session, '工单', 'new', 'operator',
                     runner=lambda *_: {'text': '已读取目录。', 'trace': []})
        self.assertEqual(session['unified_agent_workspace'], 'new')
        self.assertEqual(len(session['unified_agent_history']), 2)


if __name__ == '__main__':
    unittest.main()
