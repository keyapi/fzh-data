"""Persistent, synthetic work-order orchestration for the three bank pages.

The model may select registered evidence and suggest operations. This service
resolves every source, checks the entire plan and commits it in one Store
transaction. It never connects to a bank or to any network endpoint.
"""
import copy
import hashlib
import json
import time
import uuid

from bank_ops import BankOperations, COLLECTIONS, MASK, redact_all
from domain import DomainError, POLICY, Store, digest


DOCUMENTS = [
    {'id': 'CHANNEL-ASYNC', 'version': '2.0', 'title': '渠道异步接入规范（模拟）',
     'status': 'active', 'environment': 'test', 'profiles': ['standard', 'conservative'],
     'content': '标准异步档：最大并发12、异步回调、超时60秒、重试1次，须启用幂等参数。保守异步档：最大并发4、异步回调、超时45秒、重试0次，须启用幂等参数。'},
    {'id': 'CHANNEL-TEMPLATE', 'version': '1.0', 'title': '旧版接入模板（已取代，模拟）',
     'status': 'superseded', 'environment': 'test', 'profiles': ['standard', 'conservative'],
     'content': '旧栏位：最大并发8、同步回调、超时30秒、重试2次。仅用于解释冲突，不能作为变更目标来源。'},
    {'id': 'CHANNEL-VERIFY', 'version': '1.0', 'title': '模拟接入验收清单',
     'status': 'active', 'environment': 'test', 'profiles': ['standard', 'conservative'],
     'content': '保存后独立读取整组三页记录，核对未触及备用链路与敏感占位，再运行模拟回调契约检查。'},
]

_COMMON = ('渠道测试接入工单 {id}（模拟）。渠道：星河对公服务；终端代码 DEMO-001；'
           '租户 DEMO-BANK / TENANT-DEMO-01；本次申请按“{profile_text}”接入档完成测试环境接入。'
           '工单采用接入模板1.0，旧模板栏：新增终端、最大并发8、同步回调、超时30秒、重试2次。'
           '目标前置192.0.2.10:8443，客户端198.51.100.10，{port_text}。'
           '接入地址 https://192.0.2.10:8443/demo，签名HMAC-SHA256，编码UTF-8。'
           '请沿用既有终端身份，不创建重复代码；按当前生效规范校准模板项，补齐必备注册参数。'
           '只办理这份工单涉及的测试记录，不调整备用链路。')


def _ticket(ticket_id, profile, port, receiver='accept'):
    text = _COMMON.format(id=ticket_id,
                          profile_text='保守异步' if profile == 'conservative' else '标准异步回调',
                          port_text='客户端实际监听端口' + str(port) if port else '实际监听端口待渠道补充')
    if receiver == 'reject':
        text += ' 模拟联调测试夹具：callback_receiver=reject，用于验证失败后恢复。'
    return {'id': ticket_id, 'version': '1.0', 'title': '星河渠道异步回调接入（模拟）',
            'status': 'active', 'environment': 'test', 'profile': profile,
            'terminal_code': 'DEMO-001', 'client_port': port,
            'callback_receiver': receiver, 'text': text,
            'hash': hashlib.sha256(text.encode('utf-8')).hexdigest()}


TICKETS = {
    'WO-DEMO-001': _ticket('WO-DEMO-001', 'standard', None),
    'WO-DEMO-002': _ticket('WO-DEMO-002', 'conservative', 8443),
    'WO-DEMO-003': _ticket('WO-DEMO-003', 'standard', 9443, 'reject'),
}
PROFILES = {'standard': (12, 60, 1), 'conservative': (4, 45, 0)}
MAX_OPERATIONS = 12
FIXTURE_VERSION = '1.0'
CHECK_READBACK = '整组逐记录独立读回'


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


class BankTasks:
    def __init__(self, store):
        self.store = store
        self.bank_ops = BankOperations(store)

    @staticmethod
    def _error(code, message, status=400):
        raise DomainError(code, message, status)

    @staticmethod
    def _task(state, task_id):
        task = next((t for t in state.setdefault('bank_tasks', []) if t['id'] == task_id), None)
        if task is None:
            raise DomainError('NOT_FOUND', '此工作区不存在该任务', 404)
        return task

    @staticmethod
    def _public_task(task):
        return redact_all({k: copy.deepcopy(v) for k, v in task.items()
                           if k not in {'evidence', 'answers', 'before_bank', 'last_report'}})

    @staticmethod
    def _public_proposal(proposal):
        if proposal is None:
            return None
        return redact_all({k: copy.deepcopy(v) for k, v in proposal.items() if not k.startswith('_')})

    @staticmethod
    def _active_proposal(state, task):
        proposal_id = task.get('active_proposal_id')
        return next((p for p in state['proposals'] if p['id'] == proposal_id), None) if proposal_id else None

    @staticmethod
    def _bank(state):
        return BankOperations(None)._bank(state)

    def _register(self, task):
        """Rebuild facts whenever task revision changes; stale IDs cease to resolve."""
        ticket = TICKETS[task['ticket_id']]
        profile = ticket['profile']
        concurrency, timeout, retries = PROFILES[profile]
        task['evidence'] = []

        def add(kind, source_id, version, field, value, targets, status='active', content=''):
            fact = {'id': 'ev-' + uuid.uuid4().hex, 'kind': kind, 'task_id': task['id'],
                    'reset_count': task['reset_count'], 'task_revision': task['revision'],
                    'source_id': source_id, 'source_version': version, 'field': field,
                    'typed_value': value, 'allowed_targets': targets, 'profile': profile,
                    'environment': 'test', 'status': status,
                    'content_hash': _hash(content or {'field': field, 'value': value})}
            task['evidence'].append(fact)

        rule = next(d for d in DOCUMENTS if d['id'] == 'CHANNEL-ASYNC')
        for field, value, target in [
            ('max_concurrency', concurrency, 'terminal.max_concurrency'),
            ('callback_mode', 'ASYNC', 'terminal.callback_mode'),
            ('timeout_seconds', str(timeout), 'parameter:timeout_seconds.value'),
            ('retry_count', str(retries), 'parameter:retry_count.value'),
            ('idempotency_enabled', 'true', 'parameter:idempotency_enabled.value'),
        ]:
            add('knowledge', rule['id'], rule['version'], field, value, [target], content=rule['content'])
        port = task['answers'].get('client_port', ticket['client_port'])
        if port is not None:
            kind = 'user_answer' if 'client_port' in task['answers'] else 'ticket'
            add(kind, task['id'] if kind == 'user_answer' else ticket['id'],
                str(task['revision']) if kind == 'user_answer' else ticket['version'],
                'client_port', port, ['ip.client_port'], content=str(port) if kind == 'user_answer' else ticket['text'])
        # The old template is visible as a finding, but its superseded facts
        # cannot authorize an operation.
        add('ticket', ticket['id'], ticket['version'], 'template_version', '1.0', [],
            status='superseded', content=ticket['text'])

    def catalog(self, workspace, role):
        self.store._role(role)
        return {'tickets': [{k: t[k] for k in ('id', 'version', 'title', 'status', 'environment', 'hash', 'text')}
                            for t in TICKETS.values()],
                'documents': [{k: d[k] for k in ('id', 'version', 'title', 'status', 'environment')}
                              for d in DOCUMENTS],
                'downloads': [{'id': 'ticket-' + t['id'], 'title': t['title']} for t in TICKETS.values()]}

    def start(self, workspace, role, ticket_id):
        def create(state):
            self.store._role(role, 'operator')
            ticket = TICKETS.get(ticket_id)
            if ticket is None:
                self._error('NOT_FOUND', '工单样本不存在', 404)
            bank = self._bank(state)
            task = {'id': 'task-' + uuid.uuid4().hex, 'ticket_id': ticket_id,
                    'ticket_version': ticket['version'], 'ticket_hash': ticket['hash'],
                    'title': ticket['title'], 'status': 'needs_input' if ticket['client_port'] is None else 'draft',
                    'owner_role': 'operator', 'environment': 'test', 'terminal_code': ticket['terminal_code'],
                    'reset_count': bank['reset_count'], 'revision': 1, 'bank_version': bank['version'],
                    'request_text': '按这份工单完成测试接入，发现问题请先核对，只问必要缺项。',
                    'findings': [
                        {'code': 'EXISTING_TERMINAL', 'severity': 'info', 'text': '已有同代码终端，应复用并补齐'},
                        {'code': 'OUTDATED_TEMPLATE', 'severity': 'warning', 'text': '工单旧模板与现行异步规范冲突'}],
                    'questions': ([{'id': 'client_port', 'field': 'client_port', 'text': '客户端实际监听端口是多少？',
                                   'type': 'integer', 'min': 1, 'max': 65535, 'required': True}]
                                  if ticket['client_port'] is None else []),
                    'answers': {}, 'active_proposal_id': None, 'last_report_id': None,
                    'last_report': None, 'evidence': []}
            self._register(task)
            state.setdefault('bank_tasks', []).append(task)
            self.store._record(state, role, 'bank_task_start', 'success', correlation=task['id'])
            return self._public_task(task)
        return self.store._transaction(workspace, role, 'bank_task_start', create)

    def state(self, workspace, role, task_id):
        def read(state):
            task = self._task(state, task_id)
            if role != 'operator':
                self._error('FORBIDDEN', '当前岗位不能查看操作员任务', 403)
            return {'task': self._public_task(task),
                    'proposal': self._public_proposal(self._active_proposal(state, task)),
                    'report': redact_all(copy.deepcopy(task.get('last_report')))}
        return self.store._transaction(workspace, role, 'bank_task_state', read)

    def context(self, workspace, role, task_id):
        def read(state):
            self.store._role(role, 'operator')
            task = self._task(state, task_id)
            ticket = TICKETS[task['ticket_id']]
            bank = self._bank(state)
            terminal = next((t for t in bank['terminals'] if t['terminal_code'] == ticket['terminal_code']), None)
            if terminal is None:
                self._error('STALE', '工单终端已变化，请重置演练', 409)
            scoped = {'version': bank['version'], 'reset_count': bank['reset_count'],
                      'terminals': [terminal],
                      'parameters': [p for p in bank['parameters'] if p['terminal_id'] == terminal['id']],
                      'ip_configs': [p for p in bank['ip_configs'] if p['terminal_id'] == terminal['id']]}
            return {'task': self._public_task(task), 'ticket': copy.deepcopy(ticket),
                    'bank': redact_all(scoped), 'evidence': copy.deepcopy(task['evidence']),
                    'answers': copy.deepcopy(task['answers'])}
        return self.store._transaction(workspace, role, 'bank_task_context', read)

    def knowledge(self, workspace, role, task_id, query):
        def read(state):
            self.store._role(role, 'operator')
            task = self._task(state, task_id)
            return {'documents': copy.deepcopy(DOCUMENTS),
                    'evidence': [copy.deepcopy(e) for e in task['evidence'] if e['kind'] == 'knowledge']}
        return self.store._transaction(workspace, role, 'bank_task_knowledge', read)

    def ask(self, workspace, role, task_id, field, question):
        def ask_in_state(state):
            self.store._role(role, 'operator')
            task = self._task(state, task_id)
            if task['status'] in ('invalidated', 'cancelled', 'completed', 'recovered'):
                self._error('INVALID_STATE', '任务当前不可追问', 409)
            if field != 'client_port' or TICKETS[task['ticket_id']]['client_port'] is not None:
                self._error('INVALID_QUESTION', '工单没有这一项缺失信息')
            pending = next((q for q in task['questions'] if q['field'] == field), None)
            if pending is None:
                # Already answered in this task: hand back the known value instead of re-asking.
                return {'question': None, 'known': {field: task['answers'].get(field)},
                        'task': self._public_task(task)}
            return {'question': copy.deepcopy(pending), 'task': self._public_task(task)}
        return self.store._transaction(workspace, role, 'bank_task_ask', ask_in_state)

    def answer(self, workspace, role, task_id, question_id, value):
        def save(state):
            self.store._role(role, 'operator')
            task = self._task(state, task_id)
            if task['status'] in ('invalidated', 'completed', 'recovered'):
                self._error('INVALID_STATE', '任务当前不能回答缺项', 409)
            if question_id != 'client_port':
                self._error('INVALID_QUESTION', '此任务没有当前待答问题')
            if type(value) is not int or not 1 <= value <= 65535:
                self._error('INVALID_ANSWER', '客户端端口必须为1–65535的整数')
            pending = next((q for q in task['questions'] if q['id'] == question_id), None)
            if pending is None:
                if task['answers'].get(question_id) == value:
                    return {'task': self._public_task(task), 'evidence': copy.deepcopy(task['evidence'])}
                self._error('INVALID_QUESTION', '此任务没有当前待答问题')
            active = self._active_proposal(state, task)
            if active and active['status'] == 'pending':
                active['status'] = 'cancelled'
            task['answers'][question_id] = value
            task['questions'] = [q for q in task['questions'] if q['id'] != question_id]
            task.setdefault('answered_questions', []).append(
                {'id': question_id, 'field': 'client_port', 'value': value, 'answered': True})
            task['revision'] += 1
            task['active_proposal_id'] = None
            task['status'] = 'draft'
            self._register(task)
            self.store._record(state, role, 'bank_task_answer', 'success', correlation=task['id'])
            return {'task': self._public_task(task), 'evidence': copy.deepcopy(task['evidence'])}
        return self.store._transaction(workspace, role, 'bank_task_answer', save)

    def _expected(self, bank, task):
        ticket = TICKETS[task['ticket_id']]
        concurrency, timeout, retries = PROFILES[ticket['profile']]
        port = task['answers'].get('client_port', ticket['client_port'])
        if port is None:
            self._error('MISSING_INPUT', '需要先补充客户端实际监听端口')
        terminal = next((t for t in bank['terminals'] if t['terminal_code'] == ticket['terminal_code']), None)
        if terminal is None or terminal['tenant_code'] != 'DEMO-BANK' or terminal['environment'] != 'test':
            self._error('STALE', '目标终端不再匹配工单', 409)
        params = {p['name']: p for p in bank['parameters'] if p['terminal_id'] == terminal['id']}
        ips = [p for p in bank['ip_configs'] if p['terminal_id'] == terminal['id']
               and p['tenant_code'] == 'DEMO-BANK' and p['tenant_id'] == 'TENANT-DEMO-01'
               and p['front_address'] == '192.0.2.10' and p['front_port'] == 8443
               and p['client_address'] == '198.51.100.10']
        if len(ips) != 1 or 'timeout_seconds' not in params or 'retry_count' not in params:
            self._error('STALE', '目标记录不唯一或已变化', 409)
        desired = [
            ('terminal', 'update', terminal['id'], {'max_concurrency': concurrency, 'callback_mode': 'ASYNC'}),
            ('parameter', 'update', params['timeout_seconds']['id'], {'value': str(timeout)}),
            ('parameter', 'update', params['retry_count']['id'], {'value': str(retries)}),
            ('parameter', 'create' if 'idempotency_enabled' not in params else 'update',
             params.get('idempotency_enabled', {}).get('id'), {'value': 'true'}),
            ('ip', 'update', ips[0]['id'], {'client_port': port}),
        ]
        return [(entity, action, rid, values) for entity, action, rid, values in desired
                if action == 'create' or any((next((r for r in bank[COLLECTIONS[entity]] if r['id'] == rid), {})
                                               .get(key) != value) for key, value in values.items())]

    def _check_source(self, task, refs, target, value):
        if not isinstance(refs, list) or not refs:
            self._error('INVALID_EVIDENCE', '变更字段缺少后台登记的来源', 409)
        registry = {e['id']: e for e in task['evidence']}
        for reference in refs:
            fact = registry.get(reference)
            if not fact or fact['task_id'] != task['id'] or fact['task_revision'] != task['revision'] or \
                    fact['reset_count'] != task['reset_count'] or fact['status'] != 'active' or \
                    fact['environment'] != 'test' or fact['profile'] != TICKETS[task['ticket_id']]['profile'] or \
                    target not in fact['allowed_targets'] or type(fact['typed_value']) is not type(value) or \
                    fact['typed_value'] != value:
                self._error('INVALID_EVIDENCE', '来源不适用、已失效或与目标值不符', 409)
            if fact['kind'] == 'knowledge' and not any(d['id'] == fact['source_id'] and
                    d['version'] == fact['source_version'] and d['status'] == 'active' and
                    d['environment'] == 'test' and fact['profile'] in d['profiles'] and
                    fact['content_hash'] == _hash(d['content']) for d in DOCUMENTS):
                self._error('INVALID_EVIDENCE', '知识版本已失效', 409)
            if fact['kind'] == 'ticket' and (fact['source_id'] != task['ticket_id'] or
                    fact['content_hash'] != _hash(TICKETS[task['ticket_id']]['text'])):
                self._error('INVALID_EVIDENCE', '工单版本或正文已变化', 409)

    def prepare(self, workspace, role, task_id, operations, explanation):
        def prepare_in_state(state):
            self.store._role(role, 'operator')
            task = self._task(state, task_id)
            if task['status'] in ('invalidated', 'cancelled', 'completed', 'verification_failed',
                                  'verification_pending', 'recovered'):
                self._error('INVALID_STATE', '任务当前不能准备新的办理', 409)
            bank = self._bank(state)
            if bank['version'] != task['bank_version'] or bank['reset_count'] != task['reset_count']:
                self._error('STALE', '任务所读配置已变化，请重新建立任务', 409)
            expected = self._expected(bank, task)
            if not expected:
                self._error('NO_CHANGE', '工单目标已达标，无需重复办理', 409)
            if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 2000:
                self._error('INVALID_PLAN', '请给出方案说明')
            if not isinstance(operations, list) or len(operations) != len(expected) or len(operations) > MAX_OPERATIONS:
                self._error('INCOMPLETE_PLAN', '方案未覆盖工单所需全部差异', 409)
            expected_by_key = {(e, a, rid): values for e, a, rid, values in expected}
            normalized, used = [], set()
            for proposed in operations:
                if not isinstance(proposed, dict) or set(proposed) - {'entity', 'action', 'record_id', 'values', 'source_refs'}:
                    self._error('INVALID_PLAN', '方案包含未开放字段')
                entity, action, rid = proposed.get('entity'), proposed.get('action'), proposed.get('record_id')
                key = (entity, action, rid)
                if key not in expected_by_key or key in used or action == 'delete':
                    self._error('INVALID_PLAN', '方案包含越界、重复或未要求的操作', 409)
                used.add(key)
                target_values = expected_by_key[key]
                values, refs = proposed.get('values'), proposed.get('source_refs')
                if not isinstance(values, dict) or not isinstance(refs, dict):
                    self._error('INVALID_PLAN', '操作缺少值或来源')
                if action == 'create':
                    # The model may describe the full new record; the backend owns the definition.
                    if values.get('name') != 'idempotency_enabled' or values.get('value') != 'true':
                        self._error('INVALID_PLAN', '幂等参数只能使用固定模拟定义', 409)
                    target_keys = {'value'}
                else:
                    # Compare only the fields the task actually changes; the stored record is
                    # rebuilt from the backend-computed target, so extra keys can be ignored.
                    if not set(target_values) <= set(values) or \
                            any(values[key] != value for key, value in target_values.items()):
                        self._error('INVALID_EVIDENCE', '操作值与工单现行规则不一致', 409)
                    target_keys = set(target_values)
                if not target_keys <= set(refs):
                    self._error('INVALID_EVIDENCE', '每个变更字段都须有相应来源', 409)
                record = next((r for r in bank[COLLECTIONS[entity]] if r['id'] == rid), None)
                if action == 'create':
                    after = {'id': 'PARAM-' + uuid.uuid4().hex[:12], 'terminal_id': 'TERM-DEMO-001',
                             'name': 'idempotency_enabled', 'value': 'true',
                             'note': '模拟异步接入必备幂等开关', 'value_type': 'text'}
                    before = None
                    changed = {'value': 'true'}
                else:
                    before = copy.deepcopy(record)
                    after = {**before, **target_values}
                    changed = target_values
                for field, value in changed.items():
                    target = ('parameter:' + after['name'] + '.' + field if entity == 'parameter'
                              else entity + '.' + field)
                    self._check_source(task, refs[field], target, value)
                self.bank_ops._validate(bank, entity, copy.deepcopy(after))
                normalized.append({'id': 'op-' + uuid.uuid4().hex[:8], 'entity': entity, 'action': action,
                                   'record_id': after['id'], 'before': redact_all(before),
                                   'after': redact_all(after), 'values': copy.deepcopy(changed),
                                   'changes': [{'field': field, 'before': before.get(field) if before else None,
                                                'after': value, 'evidence_ids': refs[field]}
                                               for field, value in changed.items()]})
            if set(expected_by_key) != used:
                self._error('INCOMPLETE_PLAN', '方案遗漏必要操作', 409)
            prior = self._active_proposal(state, task)
            if prior and prior['status'] == 'pending':
                prior['status'] = 'cancelled'
            task['revision'] += 1
            task['status'] = 'ready'
            proposal = {'id': uuid.uuid4().hex, 'scenario': 'bank_task', 'task_id': task['id'],
                        'kind': 'apply', 'environment': 'test', 'terminal_code': task['terminal_code'],
                        'owner_role': 'operator', 'version': bank['version'], 'reset_count': bank['reset_count'],
                        'task_revision': task['revision'], 'created_at': time.time(),
                        'expires_at': time.time() + 600, 'status': 'pending',
                        'operations': normalized, 'sources': [copy.deepcopy(e) for e in task['evidence']
                          if any(e['id'] in change['evidence_ids'] for op in normalized for change in op['changes'])],
                        'reason': explanation.strip(), 'policy_version': POLICY,
                        'summary': {'operation_count': len(normalized),
                            'pages': sorted({op['entity'] for op in normalized}), 'reused_terminal': True},
                        'steps': ['核对批准与证据', '整组事务写入', '独立读取比对', '运行模拟验收']}
            proposal['digest'] = digest(proposal)
            state['proposals'].append(proposal)
            task['active_proposal_id'] = proposal['id']
            self.store._record(state, role, 'bank_task_prepare', 'pending', correlation=proposal['id'])
            return self._public_proposal(proposal)
        return self.store._transaction(workspace, role, 'bank_task_prepare', prepare_in_state)

    def cancel(self, workspace, role, proposal_id):
        def cancel_in_state(state):
            self.store._role(role, 'operator')
            p = self.store._proposal(state, proposal_id)
            if p.get('scenario') != 'bank_task':
                self._error('INVALID_PLAN', '不是任务整组提案')
            task = self._task(state, p['task_id'])
            if p['status'] != 'pending':
                self._error('CANCELLED', '整组提案已失效', 409)
            p['status'] = 'cancelled'
            task['status'] = 'cancelled'
            task['active_proposal_id'] = None
            task['revision'] += 1
            self.store._record(state, role, 'bank_task_cancel', 'success', correlation=proposal_id)
            return {'ok': True, 'code': 'CANCELLED', 'task': self._public_task(task),
                    'proposal': self._public_proposal(p)}
        return self.store._transaction(workspace, role, 'bank_task_cancel', cancel_in_state)

    def _apply(self, bank, operations, kind):
        for op in operations:
            entity, action, rid = op['entity'], op['action'], op['record_id']
            records = bank[COLLECTIONS[entity]]
            before = next((r for r in records if r['id'] == rid), None)
            if action == 'create':
                if before is not None:
                    self._error('STALE', '新增ID已有记录', 409)
                after = copy.deepcopy(op['after'])
                self.bank_ops._validate(bank, entity, after)
                records.append(after)
            elif action == 'update':
                if before is None or redact_all(before) != op['before']:
                    self._error('STALE', '记录在确认后发生变化', 409)
                after = {**before, **op['values']}
                self.bank_ops._validate(bank, entity, after)
                records[records.index(before)] = after
            elif action == 'delete' and kind == 'recover' and entity == 'parameter':
                if before is None or redact_all(before) != op['before'] or \
                        before['name'] != 'idempotency_enabled':
                    self._error('STALE', '恢复目标已变化', 409)
                records.remove(before)
            else:
                self._error('INVALID_PLAN', '不允许的整组动作')

    def execute(self, workspace, role, proposal_id, approved_digest):
        def execute_in_state(state):
            self.store._role(role, 'operator')
            p = self.store._proposal(state, proposal_id)
            if p.get('scenario') != 'bank_task':
                self._error('INVALID_PLAN', '不是任务整组提案')
            task = self._task(state, p['task_id'])
            if approved_digest != p['digest'] or digest(p) != p['digest']:
                self._error('DIGEST_MISMATCH', '确认内容与整组提案不一致', 409)
            if p['status'] == 'executed':
                return {'already': True, 'task_id': task['id'], 'proposal': self._public_proposal(p),
                        'execution': copy.deepcopy(p.get('_execution'))}
            if p['status'] != 'pending':
                self._error('CANCELLED', '整组确认已取消或失效', 409)
            if time.time() > p['expires_at']:
                self._error('EXPIRED', '整组确认已过期', 409)
            bank = self._bank(state)
            if bank['version'] != p['version'] or bank['reset_count'] != p['reset_count'] or \
                    task['revision'] != p['task_revision'] or task['active_proposal_id'] != p['id']:
                self._error('STALE', '配置或任务版本变化，需要重新准备', 409)
            if p.get('policy_version') != POLICY or task['ticket_hash'] != TICKETS[task['ticket_id']]['hash'] or \
                    any(e['source_id'] == 'CHANNEL-ASYNC' and not any(d['id'] == e['source_id'] and
                        d['version'] == e['source_version'] and d['status'] == 'active' and
                        e['content_hash'] == _hash(d['content']) for d in DOCUMENTS)
                        for e in p['sources']):
                self._error('INVALID_EVIDENCE', '工单、知识或策略版本已变化', 409)
            before = copy.deepcopy(bank)
            self._apply(bank, p['operations'], p['kind'])
            bank['version'] += 1
            p['status'], p['executed_version'] = 'executed', bank['version']
            p['_expected_hash'] = _hash(bank)
            p['_execution'] = {'id': 'exec-' + uuid.uuid4().hex, 'status': 'committed',
                               'committed': True, 'kind': p['kind'],
                               'operation_count': len(p['operations']),
                               'version': bank['version'], 'version_before': p['version'],
                               'version_after': bank['version'], 'committed_at': time.time()}
            task['status'] = 'verification_pending'
            task['active_proposal_id'] = None
            task['bank_version'] = bank['version']
            if p['kind'] == 'apply':
                task['before_bank'] = before
            self.store._record(state, role, 'bank_task_execute', 'success', redact_all(before),
                               redact_all(bank), p['id'])
            return {'already': False, 'task_id': task['id'], 'proposal': self._public_proposal(p),
                    'execution': copy.deepcopy(p['_execution'])}
        committed = self.store._transaction(workspace, role, 'bank_task_execute', execute_in_state)
        if committed['already']:
            current = self.state(workspace, role, committed['task_id'])
            return {'ok': True, 'code': 'ALREADY_EXECUTED', 'proposal': committed['proposal'],
                    'execution': committed['execution'], 'verification': current['report'].get('verification')
                    if current['report'] else None, 'report': current['report'], 'task': current['task']}
        try:
            checked = self.verify(workspace, role, committed['task_id'])
        except Exception:
            checked = self.state(workspace, role, committed['task_id'])
        return {'ok': True, 'code': 'EXECUTED', 'proposal': committed['proposal'],
                'execution': committed['execution'], 'verification':
                checked['report']['verification'] if checked.get('report') else {'passed': False, 'pending': True},
                'report': checked.get('report'), 'task': checked['task']}

    @staticmethod
    def _fixture(ticket):
        return {'callback_receiver': ticket['callback_receiver'],
                'virtual_elapsed_seconds': 50 if ticket['profile'] == 'standard' else 40,
                'receiver_port': 9443 if ticket['profile'] == 'standard' else 8443}

    @staticmethod
    def _first_failure(checks):
        failed = [c for c in checks if not c['passed']]
        if not failed:
            return '全部通过'
        return '；'.join(c['name'] + '：' + c.get('detail', '') for c in failed)[:300]

    def _simulate(self, bank, proposal, task, ticket):
        """Deterministic local contract simulation. No network, no model verdicts."""
        checks = []
        ids, mismatched, readback_ok = [], [], True
        for op in proposal['operations']:
            found = next((r for r in bank[COLLECTIONS[op['entity']]] if r['id'] == op['record_id']), None)
            ids.append(op['record_id'])
            good = found is None if op['action'] == 'delete' else (found is not None and redact_all(found) == op['after'])
            if not good:
                readback_ok = False
                mismatched.append(op['record_id'])
        checks.append({'name': CHECK_READBACK, 'passed': readback_ok,
                       'detail': ('逐记录一致：' + '、'.join(ids)) if readback_ok else ('不一致：' + '、'.join(mismatched))})
        baseline = task.get('before_bank')
        same_as_before = baseline is None or all(
            sorted(bank[key], key=lambda r: r['id']) == sorted(baseline[key], key=lambda r: r['id'])
            for key in COLLECTIONS.values())
        if proposal['kind'] == 'recover':
            checks.append({'name': '恢复后与执行前像一致', 'passed': same_as_before,
                           'detail': '已回到办理前配置' if same_as_before else '恢复值与执行前像不一致'})
            secret = next((p for p in bank['parameters'] if p['name'] == 'api_secret'), None)
            checks.append({'name': '范围未扩大', 'passed': same_as_before and (secret is None or secret['value'] == 'DEMO_SECRET'),
                           'detail': '敏感占位保持=%s' % (secret['value'] if secret else '—')})
            return checks

        terminal = next((t for t in bank['terminals'] if t['terminal_code'] == ticket['terminal_code']), None)
        parameters = {p['name']: p for p in bank['parameters'] if terminal and p['terminal_id'] == terminal['id']}
        ips = [p for p in bank['ip_configs'] if terminal and p['terminal_id'] == terminal['id']]
        port = task['answers'].get('client_port', ticket['client_port'])
        concurrency, timeout, retries = PROFILES[ticket['profile']]

        unique = sum(1 for t in bank['terminals'] if t['terminal_code'] == ticket['terminal_code']) == 1
        linked = all(p['terminal_id'] in {t['id'] for t in bank['terminals']} for p in bank['parameters'])
        tenant = terminal is not None and terminal['tenant_code'] == 'DEMO-BANK' and bool(ips) and \
            all(i['tenant_id'] == 'TENANT-DEMO-01' for i in ips)
        values_ok = bool(terminal) and terminal['max_concurrency'] == concurrency and terminal['callback_mode'] == 'ASYNC' and \
            parameters.get('timeout_seconds', {}).get('value') == str(timeout) and \
            parameters.get('retry_count', {}).get('value') == str(retries) and \
            parameters.get('idempotency_enabled', {}).get('value') == 'true'
        checks.append({'name': '三页终端·参数·IP 一致性', 'passed': unique and linked and tenant and values_ok,
                       'detail': '终端唯一=%s 参数关联=%s 租户一致=%s 档位值=%s' % (unique, linked, tenant, values_ok)})

        front = next((i for i in ips if i['front_address'] == '192.0.2.10' and i['front_port'] == 8443 and
                      i['client_address'] == '198.51.100.10'), None)
        contract = bool(terminal) and terminal['protocol'] == 'HTTPS' and terminal['sign_method'] == 'HMAC-SHA256' and \
            terminal['encoding'] == 'UTF-8' and terminal['callback_mode'] == 'ASYNC' and \
            terminal['endpoint'] == 'https://192.0.2.10:8443/demo' and bool(front) and front['client_port'] == port
        receiver = ticket['callback_receiver']
        checks.append({'name': '地址与回调契约（模拟）', 'passed': contract and receiver == 'accept',
                       'detail': 'HTTPS/HMAC/异步/地址端口=%s 接收方=%s' % (contract, receiver)})

        idem = parameters.get('idempotency_enabled', {}).get('value') == 'true'
        ledger = {}

        def deliver(request_id):
            if idem and request_id in ledger:
                ledger[request_id] += 1
                return 'duplicate_ignored'
            ledger[request_id] = 0
            return 'accepted'

        first, second = deliver('req-1'), deliver('req-1')
        checks.append({'name': '幂等重复请求（模拟账本）',
                       'passed': first == 'accepted' and second == 'duplicate_ignored' and len(ledger) == 1,
                       'detail': 'first=%s second=%s side_effect_count=%d' % (first, second, len(ledger))})

        try:
            budget_timeout = int(parameters.get('timeout_seconds', {}).get('value') or 0)
            budget_retry = int(parameters.get('retry_count', {}).get('value') or 0)
        except ValueError:
            budget_timeout, budget_retry = 0, 0
        remaining, attempt = (50 if ticket['profile'] == 'standard' else 40), 0
        while True:
            attempt += 1
            if remaining <= budget_timeout:
                break
            if attempt > budget_retry:
                break
            remaining -= budget_timeout
        completed = remaining <= budget_timeout
        checks.append({'name': '超时与重试（虚拟耗时）', 'passed': completed,
                       'detail': 'attempts=%d 预算=%ds/%d次 虚拟耗时完成=%s' % (attempt, budget_timeout, budget_retry, completed)})

        touched = {(op['entity'], op['record_id']) for op in proposal['operations']}
        scope_ok = True
        for entity, key in COLLECTIONS.items():
            before_by_id = {r['id']: r for r in (baseline or {}).get(key, [])}
            for record in bank[key]:
                if (entity, record['id']) not in touched and before_by_id.get(record['id']) != record:
                    scope_ok = False
        secret = next((p for p in bank['parameters'] if p['name'] == 'api_secret'), None)
        backup = next((i for i in bank['ip_configs'] if i['id'] == 'IP-DEMO-002'), None)
        backup_ok = backup is not None and backup['front_address'] == '192.0.2.11' and backup['client_address'] == '203.0.113.10'
        checks.append({'name': '范围未扩大',
                       'passed': scope_ok and backup_ok and (secret is None or secret['value'] == 'DEMO_SECRET'),
                       'detail': '未触及记录不变=%s 备用链路(%s)不变=%s 敏感占位=%s'
                                 % (scope_ok, backup['id'] if backup else '—', backup_ok,
                                    secret['value'] if secret else '—')})
        return checks

    def verify(self, workspace, role, task_id):
        self.store._role(role, 'operator')
        current = self.state(workspace, role, task_id)
        task = current['task']
        if task['status'] not in ('verification_pending', 'verification_failed', 'completed', 'recovered'):
            self._error('INVALID_STATE', '当前任务尚未执行', 409)
        # Independent connection proves the committed SQLite image is readable.
        other = Store(self.store.path) if self.store.path != ':memory:' else self.store
        try:
            bank = other._transaction(workspace, role, 'bank_task_independent_readback',
                                      lambda state: copy.deepcopy(self._bank(state)))
        finally:
            if other is not self.store:
                other.db.close()

        def finish(state):
            internal = self._task(state, task_id)
            proposals = [p for p in state['proposals'] if p.get('task_id') == task_id and p['status'] == 'executed']
            if not proposals:
                self._error('INVALID_STATE', '没有已执行整组提案', 409)
            p = proposals[-1]
            if bank['version'] != p['executed_version']:
                self._error('READBACK_STALE', '已提交但读回版本已被其他操作推进，请重新读取', 409)
            ticket = TICKETS[internal['ticket_id']]
            checks = self._simulate(bank, p, internal, ticket)
            readback = next(c['passed'] for c in checks if c['name'] == CHECK_READBACK)
            business = all(c['passed'] for c in checks)
            if p['kind'] == 'recover':
                status = 'recovered' if business else 'verification_failed'
                expected, actual = '恢复任务前配置', '已恢复' if business else self._first_failure(checks)
            else:
                status = 'completed' if business else 'verification_failed'
                expected, actual = '模拟契约全部通过', self._first_failure(checks)
            verification = {'passed': readback, 'source': 'sqlite_independent_readback',
                            'version': bank['version'], 'operation_count': len(p['operations'])}
            report = {'id': 'report-' + uuid.uuid4().hex, 'task_id': task_id, 'proposal_id': p['id'],
                      'ticket_id': internal['ticket_id'], 'kind': p['kind'], 'status': status,
                      'simulation': True, 'source': 'local_contract_simulator', 'fixture_version': FIXTURE_VERSION,
                      'bank_version': bank['version'], 'fixture': self._fixture(ticket),
                      'verification': verification, 'execution': copy.deepcopy(p.get('_execution') or {}),
                      'passed': bool(business), 'business_passed': bool(business),
                      'expected': expected, 'actual': actual, 'checks': checks,
                      'summary': '本地模拟契约测试通过' if business
                                 else '本地模拟契约测试未通过：' + self._first_failure(checks),
                      'created_at': time.time()}
            internal['status'] = status
            internal['last_report_id'] = report['id']
            internal['last_report'] = report
            self.store._record(state, role, 'bank_task_verify', status, correlation=p['id'])
            return {'report': copy.deepcopy(report), 'task': self._public_task(internal)}
        return self.store._transaction(workspace, role, 'bank_task_verify', finish)

    def recover(self, workspace, role, task_id):
        def prepare_recovery(state):
            self.store._role(role, 'operator')
            task = self._task(state, task_id)
            if task['status'] == 'recovered':
                # Repeat recovery returns the existing result instead of writing again.
                existing = next((p for p in state['proposals'] if p.get('task_id') == task_id and
                                 p.get('kind') == 'recover' and p['status'] == 'executed'), None)
                if existing is not None:
                    return self._public_proposal(existing)
            if task['status'] != 'verification_failed' or task.get('before_bank') is None:
                self._error('INVALID_STATE', '仅验收失败的已执行任务可准备恢复', 409)
            bank = self._bank(state)
            if bank['version'] != task['bank_version'] or bank['reset_count'] != task['reset_count']:
                self._error('STALE', '后续配置变化，不能覆盖他人操作', 409)
            applied = next((p for p in state['proposals'] if p.get('task_id') == task_id and
                            p.get('kind') == 'apply' and p['status'] == 'executed'), None)
            if applied is None:
                self._error('INVALID_STATE', '缺少原始执行记录', 409)
            operations = []
            for op in reversed(applied['operations']):
                current = next((r for r in bank[COLLECTIONS[op['entity']]] if r['id'] == op['record_id']), None)
                if current is None or redact_all(current) != op['after']:
                    self._error('STALE', '恢复目标已发生变化', 409)
                if op['action'] == 'create':
                    action, values, after = 'delete', {}, None
                else:
                    action = 'update'
                    values = {c['field']: c['before'] for c in op['changes']}
                    after = {**current, **values}
                operations.append({'id': 'op-' + uuid.uuid4().hex[:8], 'entity': op['entity'],
                                   'action': action, 'record_id': op['record_id'],
                                   'before': redact_all(current), 'after': redact_all(after),
                                   'values': values, 'changes': copy.deepcopy(op['changes'])})
            task['revision'] += 1
            task['status'] = 'ready'
            p = {'id': uuid.uuid4().hex, 'scenario': 'bank_task', 'task_id': task_id,
                 'kind': 'recover', 'environment': 'test', 'terminal_code': task['terminal_code'],
                 'owner_role': 'operator', 'version': bank['version'], 'reset_count': bank['reset_count'],
                 'task_revision': task['revision'], 'created_at': time.time(), 'expires_at': time.time() + 600,
                 'status': 'pending', 'operations': operations, 'sources': [],
                 'reason': '模拟验收失败，恢复本任务执行前值', 'policy_version': POLICY,
                 'summary': {'operation_count': len(operations),
                             'pages': sorted({op['entity'] for op in operations}), 'reused_terminal': True},
                 'steps': ['重新核对版本', '整组事务恢复', '独立读取恢复结果']}
            p['digest'] = digest(p)
            state['proposals'].append(p)
            task['active_proposal_id'] = p['id']
            self.store._record(state, role, 'bank_task_recover_prepare', 'pending', correlation=p['id'])
            return self._public_proposal(p)
        return self.store._transaction(workspace, role, 'bank_task_recover_prepare', prepare_recovery)

    def download(self, workspace, role, download_id):
        self.store._role(role)
        if download_id.startswith('ticket-') and download_id[7:] in TICKETS:
            ticket = TICKETS[download_id[7:]]
            return {'filename': ticket['id'] + '.txt', 'content': ticket['text']}
        if download_id.startswith('report-'):
            def read(state):
                for task in state.get('bank_tasks', []):
                    report = task.get('last_report')
                    if report and report['id'] == download_id:
                        if role != 'operator':
                            self._error('FORBIDDEN', '当前岗位不能下载任务报告', 403)
                        return {'filename': report['id'] + '.json',
                                'content': json.dumps(redact_all(report), ensure_ascii=False, indent=2)}
                self._error('NOT_FOUND', '下载项不存在', 404)
            return self.store._transaction(workspace, role, 'bank_task_download', read)
        self._error('NOT_FOUND', '下载项不在固定目录', 404)
