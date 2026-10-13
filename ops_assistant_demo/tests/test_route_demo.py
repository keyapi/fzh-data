import tempfile
import unittest
from pathlib import Path

from domain import DomainError, Store
from route_demo import RouteDemo


class RouteDemoTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.folder.name) / 'demo.sqlite3'))
        self.routes = RouteDemo(self.store)
        self.workspace = 'route-test'

    def tearDown(self):
        self.store.db.close()
        self.folder.cleanup()

    def test_scope_guard_atomic_execution_and_no_duplicate(self):
        text = '请开通余额查询、明细查询和票据查询'
        with self.assertRaises(DomainError) as wrong:
            self.routes.plan(self.workspace, 'operator', text, ['balance', 'statement'])
        self.assertEqual(wrong.exception.code, 'SCOPE_MISMATCH')
        before = self.routes.snapshot(self.workspace, 'operator')['route']
        planned = self.routes.plan(self.workspace, 'operator', text, ['balance', 'statement', 'bill'])['route']
        self.assertEqual(len(planned['proposal']['changes']), 8)  # Existing balance adapters are reused.
        self.assertEqual(before['routes'], planned['routes'])
        self.assertIsNone(planned['client'])
        proposal = planned['proposal']
        with self.assertRaises(DomainError) as denied:
            self.routes.execute(self.workspace, 'reader', proposal['id'], proposal['digest'])
        self.assertEqual(denied.exception.code, 'FORBIDDEN')
        saved = self.routes.execute(self.workspace, 'operator', proposal['id'], proposal['digest'])['route']
        self.assertTrue(saved['report']['passed'])
        self.assertEqual(len(saved['routes']), 3)
        self.assertEqual(len(saved['report']['checks']), 4)
        self.assertTrue(self.routes.plan(self.workspace, 'operator', text)['no_change'])

    def test_unknown_business_and_reset_invalidate_confirmation(self):
        with self.assertRaises(DomainError) as unknown:
            self.routes.plan(self.workspace, 'operator', '帮我开通贷款业务')
        self.assertEqual(unknown.exception.code, 'NEED_BUSINESS')
        plan = self.routes.plan(self.workspace, 'operator', '开通余额查询')['route']['proposal']
        self.store.reset(self.workspace, 'operator')
        with self.assertRaises(DomainError) as stale:
            self.routes.execute(self.workspace, 'operator', plan['id'], plan['digest'])
        self.assertEqual(stale.exception.code, 'NO_PROPOSAL')


if __name__ == '__main__':
    unittest.main()
