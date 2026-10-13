#!/usr/bin/env python3
"""Drive one bank-task scenario against a running demo server with the real model.

Each invocation logs in fresh (a new workspace), so repeated runs are independent.

    python scripts/task_eval.py --ticket WO-DEMO-001 --port 9443
    python scripts/task_eval.py --ticket WO-DEMO-003 --port 9443 --recover

Prints one JSON summary per run: model, outcome, task status, report checks, elapsed.
It only talks to the local demo server; no bank or external endpoint is contacted.
"""
import argparse
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request


def connect(base):
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(opener, base, path, body=None, timeout=180):
    request = urllib.request.Request(
        base + path, data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'X-Demo-Request': '1'})
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read().decode('utf-8'))


def run(base, ticket, port, text, recover):
    started_at = time.time()
    opener = connect(base)
    password = os.environ.get('DEMO_LOGIN_PASSWORD')
    if not password:
        raise SystemExit('Set DEMO_LOGIN_PASSWORD for the local demo login before running this script.')
    call(opener, base, '/api/login', {'username': 'operator', 'password': password})
    _, created = call(opener, base, '/api/bank/tasks/start', {'ticket_id': ticket})
    task = created['task']
    steps, chat = [], None
    for _ in range(4):
        _, chat = call(opener, base, '/api/bank/tasks/chat', {'task_id': task['id'], 'text': text})
        steps.append(chat.get('outcome'))
        if chat.get('question'):
            call(opener, base, '/api/bank/tasks/answer',
                 {'task_id': task['id'], 'question_id': chat['question']['id'], 'value': port})
            text = '已补充客户端端口，请继续核对现行依据并形成整组方案。'
            continue
        break
    summary = {'ticket': ticket, 'model': chat.get('model'), 'outcome': chat.get('outcome'),
               'citations': len(chat.get('citations') or []), 'steps': steps,
               'text': chat.get('text')}
    if chat.get('denied'):
        summary['denied'] = chat['denied']
        summary['trace'] = [{'step': t.get('step'), 'result': t.get('result')} for t in chat.get('trace') or []]
    proposal = chat.get('proposal')
    if proposal:
        _, done = call(opener, base, '/api/execute',
                       {'proposal_id': proposal['id'], 'digest': proposal['digest']})
        summary['execute_code'] = done.get('code')
        summary['operations'] = len(proposal.get('operations') or [])
        report = done.get('report') or {}
        summary['status'] = (done.get('task') or {}).get('status')
        summary['report_passed'] = report.get('passed')
        summary['checks'] = [{'name': c['name'], 'passed': c['passed']} for c in report.get('checks') or []]
        summary['failed_checks'] = [c['name'] for c in report.get('checks') or [] if not c['passed']]
        if recover and (done.get('task') or {}).get('status') == 'verification_failed':
            _, prepared = call(opener, base, '/api/bank/tasks/recover', {'task_id': task['id']})
            recovery = prepared.get('proposal')
            if recovery:
                _, restored = call(opener, base, '/api/execute',
                                   {'proposal_id': recovery['id'], 'digest': recovery['digest']})
                summary['recover_status'] = (restored.get('task') or {}).get('status')
    summary['elapsed_seconds'] = round(time.time() - started_at, 1)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8766')
    parser.add_argument('--ticket', default='WO-DEMO-001')
    parser.add_argument('--port', type=int, default=9443)
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--text', default='按这份工单完成测试环境接入，发现问题请先核对，只问必要缺项。')
    args = parser.parse_args()
    print(json.dumps(run(args.base, args.ticket, args.port, args.text, args.recover),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
