"""Synthetic terminal onboarding CRUD. Never opens network connections."""
import copy
import ipaddress
import re
import time
import uuid
from urllib.parse import urlsplit

from domain import DomainError, POLICY, digest

SCHEMAS = {
    'terminal': {'terminal_code': 'text', 'terminal_name': 'text', 'tenant_code': 'text',
                 'max_concurrency': 'integer', 'protocol': 'enum', 'encoding': 'enum',
                 'endpoint': 'text', 'sign_method': 'enum', 'callback_mode': 'enum', 'environment': 'enum'},
    'parameter': {'terminal_id': 'text', 'name': 'text', 'value': 'text', 'note': 'text', 'value_type': 'enum'},
    'ip': {'terminal_id': 'text', 'tenant_code': 'text', 'tenant_id': 'text', 'front_address': 'text',
           'front_port': 'integer', 'client_address': 'text', 'client_port': 'integer'},
}
LABELS = {'terminal_code': '终端代码', 'terminal_name': '终端名称', 'tenant_code': '租户代码',
          'max_concurrency': '最大并发数', 'protocol': '协议', 'encoding': '编码', 'endpoint': '接入地址',
          'sign_method': '签名方式', 'callback_mode': '回调方式', 'environment': '环境',
          'terminal_id': '终端', 'name': '参数名', 'value': '参数值', 'note': '说明',
          'value_type': '值类型', 'tenant_id': '租户ID', 'front_address': '前置地址',
          'front_port': '前置端口', 'client_address': '客户端地址', 'client_port': '客户端端口'}
COLLECTIONS = {'terminal': 'terminals', 'parameter': 'parameters', 'ip': 'ip_configs'}
MASK = '••••••'
SAFE_NETWORKS = [ipaddress.ip_network(n) for n in ('192.0.2.0/24', '198.51.100.0/24',
                                                '203.0.113.0/24', '198.18.0.0/15', '127.0.0.0/8', '::1/128')]


def redact_all(value):
    if isinstance(value, dict):
        return {k: redact_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_all(v) for v in value]
    return MASK if value == 'DEMO_SECRET' else value


def initial_bank():
    return {'version': 1, 'reset_count': 0, 'terminals': [{
        'id': 'TERM-DEMO-001', 'terminal_code': 'DEMO-001', 'terminal_name': '模拟联调终端',
        'tenant_code': 'DEMO-BANK', 'max_concurrency': 8, 'protocol': 'HTTPS', 'encoding': 'UTF-8',
        'endpoint': 'https://192.0.2.10:8443/demo', 'sign_method': 'HMAC-SHA256',
        'callback_mode': 'SYNC', 'environment': 'test'}],
        'parameters': [
            {'id': 'PARAM-DEMO-001', 'terminal_id': 'TERM-DEMO-001', 'name': 'timeout_seconds',
             'value': '30', 'note': '模拟超时秒数', 'value_type': 'number'},
            {'id': 'PARAM-DEMO-002', 'terminal_id': 'TERM-DEMO-001', 'name': 'retry_count',
             'value': '2', 'note': '模拟重试次数', 'value_type': 'number'},
            {'id': 'PARAM-DEMO-003', 'terminal_id': 'TERM-DEMO-001', 'name': 'api_secret',
             'value': 'DEMO_SECRET', 'note': '仅固定演示占位，无真实凭证', 'value_type': 'secret'}],
        'ip_configs': [
            {'id': 'IP-DEMO-001', 'terminal_id': 'TERM-DEMO-001', 'tenant_code': 'DEMO-BANK',
             'tenant_id': 'TENANT-DEMO-01', 'front_address': '192.0.2.10', 'front_port': 8443,
             'client_address': '198.51.100.10', 'client_port': 8080},
            {'id': 'IP-DEMO-002', 'terminal_id': 'TERM-DEMO-001', 'tenant_code': 'DEMO-BANK',
             'tenant_id': 'TENANT-DEMO-01', 'front_address': '192.0.2.11', 'front_port': 8443,
             'client_address': '203.0.113.10', 'client_port': 8080}]}


class BankOperations:
    def __init__(self, store):
        self.store = store

    def _bank(self, state):
        return state.setdefault('bank', initial_bank())

    def snapshot(self, workspace, role):
        return self.store._transaction(workspace, role, 'bank_snapshot',
                                       lambda state: redact_all(copy.deepcopy(self._bank(state))))

    @staticmethod
    def _invalid(message):
        raise DomainError('INVALID_CHANGE', message)

    def _address(self, value):
        if value == 'localhost':
            return
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            self._invalid('地址只允许文档网段、基准测试地址或localhost')
        if not any(address in network for network in SAFE_NETWORKS):
            self._invalid('禁止真实外网地址；本演示不发起网络连接')

    def _validate(self, bank, entity, record):
        if set(record) != set(SCHEMAS[entity]) | {'id'}:
            self._invalid('字段不完整或包含未知字段')
        for key, kind in SCHEMAS[entity].items():
            value = record[key]
            if kind == 'integer':
                hi = 65535 if key.endswith('_port') else 1000
                if type(value) is not int or not 1 <= value <= hi:
                    self._invalid(LABELS[key] + '必须是范围内整数')
            elif not isinstance(value, str) or len(value) > (1000 if key in ('value', 'note') else 200):
                self._invalid(LABELS[key] + '格式或长度无效')
            elif not value.strip() and key != 'note':
                self._invalid(LABELS[key] + '不能为空')
        if entity == 'terminal':
            enums = {'protocol': ('HTTP', 'HTTPS'), 'encoding': ('UTF-8', 'GBK'),
                     'sign_method': ('HMAC-SHA256', 'RSA-SHA256', 'NONE'),
                     'callback_mode': ('SYNC', 'ASYNC'), 'environment': ('test',)}
            for key, allowed in enums.items():
                if record[key] not in allowed:
                    self._invalid(LABELS[key] + '不在模拟允许范围')
            try:
                endpoint = urlsplit(record['endpoint'])
                if endpoint.scheme.lower() != record['protocol'].lower() or endpoint.username or endpoint.password:
                    self._invalid('接入地址协议不匹配或包含凭证')
                self._address(endpoint.hostname)
                if endpoint.port is not None and not 1 <= endpoint.port <= 65535:
                    self._invalid('接入端口无效')
            except (ValueError, TypeError):
                self._invalid('接入地址无效')
            unique = ('terminal_code',)
        else:
            if record['terminal_id'] not in [t['id'] for t in bank['terminals']]:
                self._invalid('关联终端不存在')
            if entity == 'parameter':
                if record['value_type'] not in ('text', 'number', 'secret'):
                    self._invalid('参数类型只允许text、number或secret')
                sensitive = re.search(r'secret|password|token|api[_-]?key|密钥|密码', record['name'], re.I)
                if sensitive:
                    record['value_type'] = 'secret'
                if record['value_type'] == 'secret':
                    if not record['value'].startswith('DEMO_') and record['value'] != MASK:
                        self._invalid('敏感值只允许DEMO_开头的模拟占位')
                    record['value'] = 'DEMO_SECRET'
                elif record['value_type'] == 'number' and not re.fullmatch(r'-?\d+(?:\.\d+)?', record['value']):
                    self._invalid('数字参数必须填写数字文本')
                unique = ('terminal_id', 'name')
            else:
                self._address(record['front_address'])
                self._address(record['client_address'])
                unique = ('terminal_id', 'front_address', 'front_port', 'client_address', 'client_port')
        for other in bank[COLLECTIONS[entity]]:
            if other['id'] != record['id'] and all(other[k] == record[k] for k in unique):
                raise DomainError('DUPLICATE', '已存在相同代码、参数名或地址组合', 409)

    def propose(self, workspace, role, entity, action, record_id, values, reason):
        def prepare(state):
            self.store._role(role, 'operator')
            if entity not in SCHEMAS or action not in ('create', 'update', 'delete'):
                self._invalid('未知业务对象或动作')
            if not isinstance(values, dict) or set(values) - set(SCHEMAS[entity]):
                self._invalid('存在未知字段')
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
                self._invalid('请提供办理理由')
            bank = self._bank(state)
            records = bank[COLLECTIONS[entity]]
            before = None
            if action == 'create':
                if record_id:
                    self._invalid('新增ID由后台生成')
                after = {'id': entity.upper() + '-' + uuid.uuid4().hex[:12], **values}
            else:
                before = next((r for r in records if r['id'] == record_id), None)
                if before is None:
                    raise DomainError('NOT_FOUND', '记录不存在', 404)
                if action == 'delete':
                    if values:
                        self._invalid('删除不接受字段修改')
                    if entity == 'terminal' and any(r['terminal_id'] == record_id for r in bank['parameters'] + bank['ip_configs']):
                        raise DomainError('IN_USE', '终端仍有参数或IP配置，不能删除', 409)
                    after = None
                else:
                    if not values:
                        self._invalid('请指定修改字段')
                    after = {**before, **values}
            if after is not None:
                self._validate(bank, entity, after)
            safe_before, safe_after = redact_all(copy.deepcopy(before)), redact_all(copy.deepcopy(after))
            if action == 'update' and safe_before == safe_after:
                raise DomainError('NO_CHANGE', '当前已是这些值，无需重复保存。')
            keys = SCHEMAS[entity]
            changes = [{'field': key, 'before': safe_before.get(key) if safe_before else None,
                        'after': safe_after.get(key) if safe_after else None} for key in keys
                       if (safe_before.get(key) if safe_before else None) != (safe_after.get(key) if safe_after else None)]
            p = {'id': uuid.uuid4().hex, 'scenario': 'bank_' + entity, 'entity': entity, 'action': action,
                 'record_id': after['id'] if after else record_id, 'values': {k: safe_after[k] for k in keys} if safe_after else {},
                 'before': safe_before, 'after': safe_after, 'changes': changes, 'environment': 'test',
                 'version': bank['version'], 'expires_at': time.time() + 600, 'created_at': time.time(),
                 'status': 'pending', 'reason': reason.strip(), 'submit': False, 'actor': role,
                 'policy_version': POLICY, 'rails': [
                     {'name': '岗位权限', 'result': 'pass', 'detail': '仅操作员可批准模拟配置办理'},
                     {'name': '确认绑定', 'result': 'pass', 'detail': '摘要、有效期与版本在执行时重查'},
                     {'name': '模拟边界', 'result': 'pass', 'detail': '不连接网络，不写任何真实业务系统'}],
                 'steps': ['校验批准内容与版本', '原子保存模拟记录', '独立读取并验证', '记录前后值']}
            p['digest'] = digest(p)
            state['proposals'].append(p)
            self.store._record(state, role, 'bank_propose', 'pending', safe_before, safe_after, p['id'])
            return p
        return self.store._transaction(workspace, role, 'bank_propose', prepare)

    def execute(self, workspace, role, proposal_id, approved_digest):
        def execute(state):
            self.store._role(role, 'operator')
            p = self.store._proposal(state, proposal_id)
            if p.get('scenario') not in {'bank_' + e for e in SCHEMAS}:
                self._invalid('不是终端配置办理')
            if p['digest'] != approved_digest or digest(p) != p['digest']:
                raise DomainError('DIGEST_MISMATCH', '批准内容与准备内容不一致', 409)
            if p['status'] == 'executed':
                return {'ok': True, 'code': 'ALREADY_EXECUTED', 'proposal': p,
                        'record': p['after'], 'message': '已经办理，没有重复写入'}
            if p['status'] != 'pending':
                raise DomainError('CANCELLED', '此次办理已取消', 409)
            if time.time() > p['expires_at']:
                raise DomainError('EXPIRED', '批准已过期，请重新准备', 409)
            bank = self._bank(state)
            if bank['version'] != p['version']:
                raise DomainError('STALE', '配置已变化，请重新读取并批准', 409)
            records = bank[COLLECTIONS[p['entity']]]
            after = copy.deepcopy(p['after'])
            if after is not None:
                self._validate(bank, p['entity'], after)
            if p['action'] == 'delete' and p['entity'] == 'terminal' and any(
                    r['terminal_id'] == p['record_id'] for r in bank['parameters'] + bank['ip_configs']):
                raise DomainError('IN_USE', '终端仍有下游记录', 409)
            records[:] = [r for r in records if r['id'] != p['record_id']]
            if after is not None:
                records.append(after)
            bank['version'] += 1
            p['status'], p['executed_version'] = 'executed', bank['version']
            self.store._record(state, role, 'bank_execute', 'success', p['before'], p['after'], p['id'])
            return {'ok': True, 'code': 'EXECUTED', 'proposal': p, 'record': p['after'],
                    'message': '模拟记录已保存' if after else '模拟记录已删除'}
        result = self.store._transaction(workspace, role, 'bank_execute', execute)
        current = self.snapshot(workspace, role)
        p = result['proposal']
        found = next((r for r in current[COLLECTIONS[p['entity']]] if r['id'] == p['record_id']), None)
        result['verification'] = {'passed': found == p['after'], 'source': 'sqlite_independent_readback',
                                  'record': found, 'version': current['version']}
        return result
