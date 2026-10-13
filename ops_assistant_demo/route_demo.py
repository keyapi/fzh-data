"""Synthetic adapter and route workbench; no connection to a bank system."""
import copy
import hashlib
import json
import re
import time
import uuid

from domain import DomainError


RULE = {'id': 'ROUTE-DEMO-01', 'version': '1.0', 'status': 'active',
        'title': '渠道业务路由映射规范（模拟）',
        'content': '每项业务分别匹配请求与应答适配器；客户端采用同步调用、终端输入、业务终端输出。路由业务码必须唯一，保存后按业务码做模拟命中验收。'}
SERVICES = {
    'balance': {'name': '余额查询', 'code': 'D201', 'aliases': ('余额', '账户余额'), 'request': 'BAL-REQ', 'response': 'BAL-RES'},
    'statement': {'name': '明细查询', 'code': 'D202', 'aliases': ('明细', '流水'), 'request': 'STM-REQ', 'response': 'STM-RES'},
    'bill': {'name': '票据查询', 'code': 'D203', 'aliases': ('票据', '票据业务'), 'request': 'BIL-REQ', 'response': 'BIL-RES'},
}
CLIENT = {'id': 'CLIENT-DEMO-01', 'name': '星河渠道业务客户端', 'mode': '同步',
          'input_type': '终端', 'output_terminal': 'TERM-DEMO-01'}


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _fresh():
    return {'version': 1, 'reset_count': 0, 'client': None,
            'adapters': [{'key': 'BAL-REQ', 'name': '余额查询请求适配器', 'service': 'balance', 'direction': '请求'},
                         {'key': 'BAL-RES', 'name': '余额查询应答适配器', 'service': 'balance', 'direction': '应答'}],
            'routes': [], 'proposal': None, 'report': None}


class RouteDemo:
    def __init__(self, store):
        self.store = store

    def _data(self, state):
        return state.setdefault('route_demo', _fresh())

    def snapshot(self, workspace, role):
        def read(state):
            self.store._role(role)
            data = self._data(state)
            result = copy.deepcopy(data)
            if role != 'operator':
                result['proposal'] = None
            return {'route': result, 'rule': RULE, 'services': SERVICES}
        return self.store._transaction(workspace, role, 'route_read', read)

    @staticmethod
    def explicit_services(text):
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise DomainError('INVALID_INPUT', '请说明要开通的业务（不超过1000字）。')
        names = {key for key, item in SERVICES.items() if any(alias in text for alias in item['aliases'])}
        if not names:
            raise DomainError('NEED_BUSINESS', '请明确要开通余额查询、明细查询或票据查询中的哪项；不会猜测业务范围。')
        if re.search(r'(?:不|别|取消|除外|除了|只读).{0,8}(?:余额|明细|流水|票据)|(?:余额|明细|流水|票据).{0,8}(?:不要|不需要|不开通)', text):
            raise DomainError('AMBIGUOUS_SCOPE', '检测到业务排除或取消条件，请只列本次要开通的业务。尚未准备修改。')
        if re.search(r'贷款|支付|转账|代发|生产|全部|所有', text):
            raise DomainError('UNSUPPORTED_SCOPE', '本模拟只支持明确的余额、明细、票据查询；包含其他业务或生产要求时需先澄清。')
        return names

    def plan(self, workspace, role, text, selected=None):
        requested = self.explicit_services(text)
        if selected is not None:
            if not isinstance(selected, list) or set(selected) != requested or len(selected) != len(requested):
                raise DomainError('SCOPE_MISMATCH', '模型选择与本轮明确业务范围不一致，未形成方案。')
        def prepare(state):
            self.store._role(role, 'operator')
            data = self._data(state)
            changes = []
            if data['client'] != CLIENT:
                changes.append({'kind': 'client', 'action': '配置', 'key': CLIENT['id'], 'after': CLIENT,
                                'before': data['client'], 'source': RULE['id']})
            for key in SERVICES:
                if key not in requested:
                    continue
                item = SERVICES[key]
                for direction, adapter_key in (('请求', item['request']), ('应答', item['response'])):
                    expected = {'key': adapter_key, 'name': item['name'] + direction + '适配器',
                                'service': key, 'direction': direction}
                    existing = next((a for a in data['adapters'] if a['key'] == adapter_key), None)
                    if existing is not None and existing != expected:
                        raise DomainError('ADAPTER_CONFLICT', '已有适配器定义冲突，请人工核对；未覆盖。', 409)
                    if existing is None:
                        changes.append({'kind': 'adapter', 'action': '新增', 'key': adapter_key, 'before': None,
                                        'after': expected, 'source': RULE['id']})
                expected_route = {'code': item['code'], 'service': key, 'name': item['name'],
                                  'client': CLIENT['id'], 'request_adapter': item['request'],
                                  'response_adapter': item['response'], 'output_terminal': CLIENT['output_terminal']}
                existing_route = next((r for r in data['routes'] if r['code'] == item['code']), None)
                if existing_route is not None and existing_route != expected_route:
                    raise DomainError('ROUTE_CONFLICT', '已有业务码路由指向不同目标，请人工核对；未覆盖。', 409)
                if existing_route is None:
                    changes.append({'kind': 'route', 'action': '新增', 'key': item['code'], 'before': None,
                                    'after': expected_route, 'source': RULE['id']})
            if not changes:
                data['proposal'] = None
                return {'route': copy.deepcopy(data), 'no_change': True,
                        'message': '所选业务的客户端、适配器和路由已经达标，无需重复办理。'}
            proposal = {'id': 'route-' + uuid.uuid4().hex, 'status': 'pending', 'role': role,
                        'base_version': data['version'], 'reset_count': data['reset_count'],
                        'scope': sorted(requested), 'changes': changes, 'source': RULE['id'],
                        'source_version': RULE['version'], 'expires_at': time.time() + 900}
            proposal['digest'] = _hash(proposal)
            data['proposal'] = proposal
            self.store._record(state, role, 'route_plan', 'success', correlation=proposal['id'])
            return {'route': copy.deepcopy(data), 'no_change': False,
                    'message': f'已按现行模拟映射准备{len(changes)}项差异。请核对业务范围、适配器和路由后确认。'}
        return self.store._transaction(workspace, role, 'route_plan', prepare)

    def execute(self, workspace, role, proposal_id, expected_digest):
        def commit(state):
            self.store._role(role, 'operator')
            data = self._data(state)
            proposal = data.get('proposal')
            if not proposal or proposal['id'] != proposal_id or proposal['status'] != 'pending':
                raise DomainError('NO_PROPOSAL', '没有待确认的当前路由方案。', 409)
            if proposal['digest'] != expected_digest or proposal['digest'] != _hash({k: v for k, v in proposal.items() if k != 'digest'}):
                raise DomainError('PLAN_CHANGED', '方案内容已变化，请重新分析。', 409)
            if proposal['expires_at'] < time.time() or proposal['base_version'] != data['version'] or proposal['reset_count'] != data['reset_count']:
                raise DomainError('STALE', '当前配置或工作区已变化，请重新分析。', 409)
            before = copy.deepcopy({'client': data['client'], 'adapters': data['adapters'], 'routes': data['routes']})
            for change in proposal['changes']:
                if change['kind'] == 'client':
                    data['client'] = copy.deepcopy(change['after'])
                elif change['kind'] == 'adapter':
                    data['adapters'].append(copy.deepcopy(change['after']))
                elif change['kind'] == 'route':
                    data['routes'].append(copy.deepcopy(change['after']))
            data['version'] += 1
            proposal['status'] = 'executed'
            checks = []
            for service_id in proposal['scope']:
                service = SERVICES[service_id]
                route = next((r for r in data['routes'] if r['code'] == service['code']), None)
                adapter_keys = {a['key'] for a in data['adapters']}
                passed = bool(route and route['request_adapter'] in adapter_keys and route['response_adapter'] in adapter_keys
                              and route['client'] == data['client']['id'] and route['output_terminal'] == data['client']['output_terminal'])
                checks.append({'service': service['name'], 'code': service['code'], 'passed': passed,
                               'detail': '模拟业务码命中并找到请求/应答适配器' if passed else '模拟命中失败'})
            unchanged_outside = all(r['service'] in proposal['scope'] or r in before['routes'] for r in data['routes'])
            checks.append({'service': '范围外配置', 'passed': unchanged_outside, 'detail': '未扩展到未申请业务' if unchanged_outside else '发现范围外写入'})
            report = {'id': 'route-report-' + uuid.uuid4().hex, 'passed': all(c['passed'] for c in checks),
                      'checks': checks, 'before': before, 'after_version': data['version'], 'simulated': True}
            data['report'] = report
            self.store._record(state, role, 'route_execute', 'success', before,
                               {'client': data['client'], 'adapters': data['adapters'], 'routes': data['routes']}, proposal['id'])
            return {'route': copy.deepcopy(data), 'message': '整组已保存；模拟路由命中测试完成。'}
        result = self.store._transaction(workspace, role, 'route_execute', commit)
        readback = self.snapshot(workspace, role)['route']
        result['readback'] = {'passed': all(readback[key] == result['route'][key] for key in ('client', 'adapters', 'routes', 'version')),
                              'version': readback['version']}
        result['message'] = ('整组已保存并独立读回；模拟路由命中测试完成。' if result['readback']['passed']
                             else '整组已保存，但独立读回发现后续变化，请刷新核对。')
        return result

    def cancel(self, workspace, role):
        def stop(state):
            self.store._role(role, 'operator')
            data = self._data(state)
            if (data.get('proposal') or {}).get('status') == 'pending':
                data['proposal']['status'] = 'cancelled'
            return {'route': copy.deepcopy(data), 'message': '路由方案已取消，未保存。'}
        return self.store._transaction(workspace, role, 'route_cancel', stop)
