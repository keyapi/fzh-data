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


class AgentHttpTests(unittest.TestCase):
    def setUp(self):
        server.BUCKETS.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.store_patch = patch.object(server, 'STORE', server.Store(self.temp.name + '/demo.sqlite3'))
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
        server.STORE.db.close()
        self.store_patch.stop()
        server.BUCKETS.clear()
        self.temp.cleanup()

    def call(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Demo-Request': '1'})
        try:
            response = self.client.open(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def login(self):
        self.assertEqual(self.call('/api/login', {'username': 'operator', 'password': 'demo2026'})[0], 200)

    def test_turn_requires_auth_and_returns_visible_result_and_state(self):
        self.assertEqual(self.call('/api/agent/turn', {'text': '我们有几个工单？'})[0], 401)
        self.login()
        reply = {'turn_id': 'turn-fixture', 'outcome': 'answered', 'text': '当前有 3 份演练工单。',
                 'trace': [{'tool': 'list_workorders', 'result': {'count': 3}}]}
        with patch.object(server, 'unified_agent_turn', return_value=reply) as turn:
            status, data = self.call('/api/agent/turn', {'text': '我们有几个工单？', 'page': 'route-demo'})
        self.assertEqual(status, 200, data)
        self.assertEqual(data['text'], reply['text'])
        self.assertEqual(data['state']['role'], 'operator')
        self.assertEqual(turn.call_args.args[1]['text'], '我们有几个工单？')
        self.assertNotIn('page', turn.call_args.args[1])

    def test_blank_turn_never_reaches_model(self):
        self.login()
        with patch.object(server, 'unified_agent_turn') as turn:
            status, data = self.call('/api/agent/turn', {'text': '   '})
        self.assertEqual(status, 400, data)
        turn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
