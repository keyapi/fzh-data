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


def reply(text='', calls=None):
    return {'choices': [{'message': {'content': text, 'tool_calls': [
        {'id': 'call-%d' % index, 'type': 'function',
         'function': {'name': name, 'arguments': json.dumps(args)}}
        for index, (name, args) in enumerate(calls or [])]}}]}


def plan_operations(messages):
    """Build the five operations the backend expects, reusing the evidence ids
    the backend actually registered for this run (they are random per revision)."""
    context = knowledge = None
    for message in messages:
        if message.get('role') != 'tool':
            continue
        try:
            payload = json.loads(message.get('content') or '{}')
        except ValueError:
            continue
        if isinstance(payload, dict) and 'ticket' in payload and 'bank' in payload:
            context = payload
        elif isinstance(payload, dict) and 'documents' in payload and 'evidence' in payload:
            knowledge = payload
    evidence = ((context or {}).get('evidence') or []) + ((knowledge or {}).get('evidence') or [])

    def ref(target, value):
        return next(e['id'] for e in evidence
                    if target in e['allowed_targets'] and e['typed_value'] == value)

    return [
        {'entity': 'terminal', 'action': 'update', 'record_id': 'TERM-DEMO-001',
         'values': {'max_concurrency': 12, 'callback_mode': 'ASYNC'},
         'source_refs': {'max_concurrency': [ref('terminal.max_concurrency', 12)],
                         'callback_mode': [ref('terminal.callback_mode', 'ASYNC')]}},
        {'entity': 'parameter', 'action': 'update', 'record_id': 'PARAM-DEMO-001',
         'values': {'value': '60'},
         'source_refs': {'value': [ref('parameter:timeout_seconds.value', '60')]}},
        {'entity': 'parameter', 'action': 'update', 'record_id': 'PARAM-DEMO-002',
         'values': {'value': '1'},
         'source_refs': {'value': [ref('parameter:retry_count.value', '1')]}},
        {'entity': 'parameter', 'action': 'create',
         'values': {'name': 'idempotency_enabled', 'value': 'true'},
         'source_refs': {'value': [ref('parameter:idempotency_enabled.value', 'true')]}},
        {'entity': 'ip', 'action': 'update', 'record_id': 'IP-DEMO-001',
         'values': {'client_port': 9443},
         'source_refs': {'client_port': [ref('ip.client_port', 9443)]}},
    ]


def responder(base, key, messages, tools):
    """Scripted model: read first turn, then prepare the full plan next turn."""
    if not any(m.get('role') == 'tool' for m in messages):
        return reply(calls=[('read_task_context', {}), ('search_task_knowledge', {'query': '异步接入'})])
    return reply(calls=[('prepare_task_plan', {
        'operations': plan_operations(messages), 'explanation': '依据现行异步接入规范办理'})])


class BankTaskHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = server.Store(self.tmp.name + '/tasks.db')
        self.store_patch = patch.object(server, 'STORE', self.store)
        self.store_patch.start()
        self.config_patch = patch.dict(server.CONFIG, {
            'OPENAI_API_BASE_URL': 'https://model.invalid/v1', 'OPENAI_API_KEY': 'dummy',
            'OPENAI_MODEL': 'fixture-model'})
        self.config_patch.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.http.server_port)
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
        self.config_patch.stop()
        self.store_patch.stop()
        self.store.db.close()
        self.tmp.cleanup()

    def raw(self, path, body=None):
        req = urllib.request.Request(self.base + path,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Demo-Request': '1'})
        try:
            response = self.client.open(req)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode('utf-8')

    def call(self, path, body=None):
        status, raw = self.raw(path, body)
        return status, json.loads(raw)

    def login(self, role='operator'):
        self.assertEqual(self.call('/api/login', {'username': role, 'password': 'demo2026'})[0], 200)

    def begin(self, ticket='WO-DEMO-001'):
        status, started = self.call('/api/bank/tasks/start', {'ticket_id': ticket})
        self.assertEqual(status, 200, started)
        return started['task']

    def test_default_001_main_line_end_to_end(self):
        self.login()
        task = self.begin()
        self.assertEqual(task['status'], 'needs_input')
        status, answered = self.call('/api/bank/tasks/answer',
                                     {'task_id': task['id'], 'question_id': 'client_port', 'value': 9443})
        self.assertEqual(status, 200, answered)
        with patch.object(server, 'model_call', side_effect=responder):
            status, chat = self.call('/api/bank/tasks/chat', {'task_id': task['id'], 'text': '按这份工单完成测试接入'})
        self.assertEqual(status, 200, chat)
        self.assertEqual(chat['model'], server.MODEL)
        self.assertEqual(chat['source'], 'live-model')
        proposal = chat['proposal']
        self.assertEqual(len(proposal['operations']), 5)
        # Nothing is written before the single confirmation.
        _, before = self.call('/api/bank/state')
        self.assertEqual(before['bank']['version'], 1)
        status, done = self.call('/api/execute', {'proposal_id': proposal['id'], 'digest': proposal['digest']})
        self.assertEqual(status, 200, done)
        self.assertEqual(done['code'], 'EXECUTED')
        self.assertTrue(done['verification']['passed'])
        self.assertEqual(done['task']['status'], 'completed')
        _, after = self.call('/api/bank/state')
        self.assertEqual(after['bank']['version'], 2)
        terminal = next(t for t in after['bank']['terminals'] if t['terminal_code'] == 'DEMO-001')
        self.assertEqual(terminal['max_concurrency'], 12)
        self.assertEqual(terminal['callback_mode'], 'ASYNC')
        self.assertEqual(next(p for p in after['bank']['parameters'] if p['id'] == 'PARAM-DEMO-001')['value'], '60')
        self.assertEqual(len([p for p in after['bank']['parameters'] if p['name'] == 'idempotency_enabled']), 1)
        self.assertEqual(next(p for p in after['bank']['ip_configs'] if p['id'] == 'IP-DEMO-001')['client_port'], 9443)
        self.assertEqual(next(p for p in after['bank']['ip_configs'] if p['id'] == 'IP-DEMO-002')['client_port'], 8080)

    def test_cancel_routes_to_bank_tasks_and_keeps_records(self):
        self.login()
        task = self.begin()
        self.call('/api/bank/tasks/answer', {'task_id': task['id'], 'question_id': 'client_port', 'value': 9443})
        with patch.object(server, 'model_call', side_effect=responder):
            _, chat = self.call('/api/bank/tasks/chat', {'task_id': task['id'], 'text': '办理'})
        proposal = chat['proposal']
        status, cancelled = self.call('/api/cancel', {'proposal_id': proposal['id']})
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled['code'], 'CANCELLED')
        self.assertEqual(cancelled['task']['status'], 'cancelled')
        _, after = self.call('/api/bank/state')
        self.assertEqual(after['bank']['version'], 1)
        self.assertEqual(after['bank']['terminals'][0]['max_concurrency'], 8)

    def test_reader_cannot_start_or_read_operator_task(self):
        status, started = self.call('/api/bank/tasks/start', {'ticket_id': 'WO-DEMO-001'})
        self.assertEqual(status, 401)
        self.login('reader')
        status, denied = self.call('/api/bank/tasks/start', {'ticket_id': 'WO-DEMO-001'})
        self.assertEqual(status, 403)
        self.assertEqual(denied['code'], 'FORBIDDEN')

    def test_download_serves_allowlisted_ticket_only(self):
        self.login()
        status, body = self.raw('/api/bank/tasks/download?id=ticket-WO-DEMO-001')
        self.assertEqual(status, 200)
        self.assertIn('WO-DEMO-001', body)
        self.assertEqual(self.call('/api/bank/tasks/download?id=../server.py')[0], 404)
        self.assertEqual(self.call('/api/bank/tasks/download?id=ticket-NOPE')[0], 404)


if __name__ == '__main__':
    unittest.main()
