import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class BankHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = server.Store(self.tmp.name + '/bank.db')
        self.store_patch = patch.object(server, 'STORE', self.store)
        self.store_patch.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.http.server_port)
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
        self.store_patch.stop()
        self.store.db.close()
        self.tmp.cleanup()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Demo-Request': '1'})
        try:
            response = self.client.open(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def login(self, role='operator'):
        self.assertEqual(self.call('/api/login', {'username': role, 'password': 'demo2026'})[0], 200)

    def test_bank_api_requires_cookie_and_reader_cannot_write(self):
        self.assertEqual(self.call('/api/bank/state')[0], 401)
        self.login('reader')
        status, data = self.call('/api/bank/state')
        self.assertEqual(status, 200)
        self.assertTrue(data['bank']['terminals'])
        status, error = self.call('/api/bank/propose', {'entity': 'parameter', 'action': 'delete',
            'record_id': data['bank']['parameters'][0]['id'], 'values': {}, 'reason': '越权删除'})
        self.assertEqual(status, 403)
        self.assertEqual(error['code'], 'FORBIDDEN')

    def test_common_confirmation_executes_and_independently_reads_parameter(self):
        self.login()
        status, data = self.call('/api/bank/state')
        self.assertEqual(status, 200)
        parameter = next(p for p in data['bank']['parameters'] if p['value_type'] != 'secret')
        _, prepared = self.call('/api/bank/propose', {'entity': 'parameter', 'action': 'update',
            'record_id': parameter['id'], 'values': {'value': '75'},
            'reason': '验证修改真实保存'})
        self.assertEqual(prepared['proposal']['status'], 'pending')
        _, before = self.call('/api/bank/state')
        self.assertNotEqual(next(p for p in before['bank']['parameters'] if p['id'] == parameter['id'])['value'], '75')
        proposal = prepared['proposal']
        status, done = self.call('/api/ops/execute', {'proposal_id': proposal['id'], 'digest': proposal['digest']})
        self.assertEqual(status, 200, done)
        self.assertEqual(done['code'], 'EXECUTED')
        self.assertTrue(done['verification'])
        _, after = self.call('/api/bank/state')
        self.assertEqual(next(p for p in after['bank']['parameters'] if p['id'] == parameter['id'])['value'], '75')

    def test_reset_restores_bank_and_invalidates_old_confirmation_and_context(self):
        self.login()
        _, prepared = self.call('/api/bank/propose', {'entity': 'parameter', 'action': 'update',
            'record_id': 'PARAM-DEMO-001', 'values': {'value': '75'}, 'reason': '重置测试'})
        p = prepared['proposal']
        self.call('/api/ops/execute', {'proposal_id': p['id'], 'digest': p['digest']})
        _, prepared = self.call('/api/bank/propose', {'entity': 'parameter', 'action': 'update',
            'record_id': 'PARAM-DEMO-001', 'values': {'value': '90'}, 'reason': '待确认修改'})
        p = prepared['proposal']
        _, result = self.call('/api/ops/reset', {})
        self.assertEqual(next(r for r in result['state']['bank']['parameters'] if r['id']=='PARAM-DEMO-001')['value'], '30')
        self.assertGreater(result['state']['bank']['version'], p['version'])
        self.assertEqual(result['state']['bank']['reset_count'], 1)
        self.assertEqual(self.call('/api/ops/execute', {'proposal_id': p['id'], 'digest': p['digest']})[1]['code'], 'CANCELLED')

    def test_sensitive_values_masked_in_all_http_responses_and_ui_script_only_allowlisted(self):
        self.login()
        _, result = self.call('/api/bank/propose', {'entity': 'parameter', 'action': 'update',
            'record_id': 'PARAM-DEMO-003', 'values': {'value': 'DEMO_FAKE_VALUE'}, 'reason': '敏感占位'})
        # Fixed synthetic secrets never rotate; identical values require no action.
        self.assertEqual(result['code'], 'NO_CHANGE')
        _, state = self.call('/api/ops/state')
        self.assertNotIn('DEMO_SECRET', json.dumps(state))
        self.assertNotIn('DEMO_FAKE_VALUE', json.dumps(state))
        with self.client.open(self.base + '/bank_ui.js') as response:
            self.assertEqual(response.status, 200)
            self.assertIn('javascript', response.headers['Content-Type'])
        self.assertEqual(self.call('/bank_ops.py')[0], 404)

    def test_bank_chat_uses_authenticated_role_and_common_model_limits(self):
        self.login('reader')
        with patch.object(server, 'CONFIG', {'OPENAI_API_BASE_URL': 'http://model.invalid', 'OPENAI_API_KEY': 'dummy'}), \
             patch.object(server, 'run_bank_agent', return_value={'ok': True, 'text': '已读取', 'source': 'live-model'}) as agent:
            status, result = self.call('/api/bank/chat', {'text': '查当前参数', 'entity': 'parameter', 'role': 'operator'})
        self.assertEqual(status, 200)
        self.assertEqual(agent.call_args.args[0]['role'], 'reader')
        self.assertEqual(result['source'], 'live-model')


if __name__ == '__main__':
    unittest.main()
