import tempfile
import unittest
from pathlib import Path

from agent_tools import AgentTools
from domain import DomainError, Store


class AgentToolsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.folder.name) / 'agent.sqlite3'))
        self.tools = AgentTools(self.store)
        self.workspace = 'agent-tools-test'

    def tearDown(self):
        self.store.db.close()
        self.folder.cleanup()

    def test_catalog_is_real_and_distinguishes_all_workorders(self):
        result = self.tools.invoke('list_workorders', self.workspace, 'operator', {})
        self.assertEqual(result['count'], 3)
        self.assertEqual([item['id'] for item in result['items']],
                         ['WO-DEMO-001', 'WO-DEMO-002', 'WO-DEMO-003'])
        self.assertIn('缺少客户端端口', result['items'][0]['difference'])
        self.assertIn('4/45/0', result['items'][1]['difference'])
        self.assertIn('恢复演练', result['items'][2]['difference'])

    def test_reading_has_no_write_side_effect_or_task_creation(self):
        before = self.store.snapshot(self.workspace, 'operator')
        result = self.tools.invoke('read_workspace_context', self.workspace, 'operator', {})
        after = self.store.snapshot(self.workspace, 'operator')
        self.assertEqual(before['proposals'], after['proposals'])
        self.assertEqual(before.get('bank_tasks', []), after.get('bank_tasks', []))
        self.assertEqual(result['source']['kind'], 'workspace_snapshot')
        self.assertIn('bank', result)

    def test_cross_page_records_have_a_real_source_and_allowlist(self):
        result = self.tools.invoke('read_records', self.workspace, 'operator', {'collection': 'routes'})
        self.assertEqual(result['source']['kind'], 'route_snapshot')
        self.assertEqual(result['items'], [])
        with self.assertRaises(DomainError) as raised:
            self.tools.invoke('read_records', self.workspace, 'operator', {'collection': 'sqlite_master'})
        self.assertEqual(raised.exception.code, 'INVALID_COLLECTION')

    def test_reader_is_refused_operator_only_workorder_content(self):
        with self.assertRaises(DomainError) as raised:
            self.tools.invoke('read_workorder', self.workspace, 'reader', {'ticket_id': 'WO-DEMO-001'})
        self.assertEqual(raised.exception.code, 'FORBIDDEN')

    def test_unknown_tool_and_ticket_are_explicit(self):
        with self.assertRaises(DomainError) as unknown_tool:
            self.tools.invoke('open_everything', self.workspace, 'operator', {})
        self.assertEqual(unknown_tool.exception.code, 'UNKNOWN_CAPABILITY')
        with self.assertRaises(DomainError) as unknown_ticket:
            self.tools.invoke('read_workorder', self.workspace, 'operator', {'ticket_id': 'WO-NOPE'})
        self.assertEqual(unknown_ticket.exception.code, 'NOT_FOUND')

    def test_prepare_change_creates_only_a_pending_backend_checked_plan(self):
        before = self.tools.invoke('read_workspace_context', self.workspace, 'operator', {})
        result = self.tools.invoke('prepare_counter_change', self.workspace, 'operator',
                                   {'limit': 200000, 'reason': '用户明确要求的测试限额'})
        self.assertEqual(result['proposal']['status'], 'pending')
        after = self.tools.invoke('read_workspace_context', self.workspace, 'operator', {})
        self.assertEqual(before['bank']['version'], after['bank']['version'])
        with self.assertRaises(DomainError) as denied:
            self.tools.invoke('prepare_counter_change', self.workspace, 'reader',
                              {'limit': 200000, 'reason': '越权测试'})
        self.assertEqual(denied.exception.code, 'FORBIDDEN')


    def test_route_plan_is_prepared_without_writing_routes(self):
        names = [item['name'] for item in self.tools.catalog('operator')['items']]
        self.assertIn('prepare_route_plan', names)
        reader = [item['name'] for item in self.tools.catalog('reader')['items']]
        self.assertNotIn('prepare_route_plan', reader)
        result = self.tools.invoke('prepare_route_plan', self.workspace, 'operator',
                                   {'request': '只开通余额查询，不要明细和票据'})
        self.assertIn('message', result['plan'])
        routes = self.tools.invoke('read_records', self.workspace, 'operator', {'collection': 'routes'})
        self.assertEqual(routes['items'], [])


if __name__ == '__main__':
    unittest.main()
