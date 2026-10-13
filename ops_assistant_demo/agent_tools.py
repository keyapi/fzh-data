"""Allowlisted observations for the unified assistant.

These tools deliberately return small, redacted domain snapshots.  They are
not a generic database or HTTP bridge: the server supplies the authenticated
workspace and role for every call.
"""
import copy

from bank_ops import BankOperations, redact_all
from bank_tasks import BankTasks, DOCUMENTS, TICKETS
from domain import DomainError
from route_demo import RouteDemo, RULE, SERVICES


class AgentTools:
    """Capability directory and server-owned read tools for one turn."""

    _COLLECTIONS = frozenset({'terminals', 'parameters', 'ip_configs', 'routes', 'adapters'})

    def __init__(self, store):
        self.store = store

    @staticmethod
    def _source(kind, **values):
        return {'kind': kind, **values}

    def catalog(self, role):
        capabilities = [
            {'name': 'list_workorders', 'kind': 'read', 'roles': ['operator', 'reader', 'reviewer'],
             'description': '列出演练工单及其差异，不建立任务。'},
            {'name': 'read_workspace_context', 'kind': 'read', 'roles': ['operator', 'reader', 'reviewer'],
             'description': '读取当前工作区的摘要和版本。'},
            {'name': 'read_workorder', 'kind': 'read', 'roles': ['operator'],
             'description': '读取指定工单原文与模拟资料。'},
            {'name': 'read_records', 'kind': 'read', 'roles': ['operator', 'reader', 'reviewer'],
             'description': '读取许可的终端、参数、地址、适配器或路由集合。'},
            {'name': 'search_rules', 'kind': 'read', 'roles': ['operator', 'reader', 'reviewer'],
             'description': '检索当前可见的模拟规则；规则不授予执行权限。'},
            {'name': 'read_pending_plans', 'kind': 'read', 'roles': ['operator', 'reader', 'reviewer'],
             'description': '读取当前工作区待确认方案；不确认、不执行。'},
            {'name': 'read_audit', 'kind': 'read', 'roles': ['operator', 'reviewer'],
             'description': '读取当前工作区审计摘要。'},
            {'name': 'prepare_counter_change', 'kind': 'prepare', 'roles': ['operator'],
             'description': '准备柜面测试限额方案。用户确认后系统才写入测试环境并读回；生产不直接改。'},
            {'name': 'prepare_integration_change', 'kind': 'prepare', 'roles': ['operator'],
             'description': '准备联调超时与重试方案。用户确认后系统才写入测试环境并读回；生产不直接改。'},
            {'name': 'prepare_route_plan', 'kind': 'prepare', 'roles': ['operator'],
             'description': '按点名的余额、明细或票据查询准备测试路由整组方案。用户确认后才写入；缺关键项只追问该项。'},
        ]
        return {'items': [item for item in capabilities if role in item['roles']],
                'source': self._source('capability_catalog', version='1')}

    def invoke(self, name, workspace, role, args):
        if not isinstance(args, dict):
            raise DomainError('INVALID_TOOL_INPUT', '工具参数必须是对象。')
        methods = {
            'list_capabilities': self.list_capabilities,
            'list_workorders': self.list_workorders,
            'read_workspace_context': self.read_workspace_context,
            'read_workorder': self.read_workorder,
            'read_records': self.read_records,
            'search_rules': self.search_rules,
            'read_pending_plans': self.read_pending_plans,
            'read_audit': self.read_audit,
            'prepare_counter_change': self.prepare_counter_change,
            'prepare_integration_change': self.prepare_integration_change,
            'prepare_route_plan': self.prepare_route_plan,
        }
        method = methods.get(name)
        if method is None:
            raise DomainError('UNKNOWN_CAPABILITY', '该能力未开放。', 404)
        return method(workspace, role, args)

    def list_capabilities(self, _workspace, role, _args):
        return self.catalog(role)

    def list_workorders(self, workspace, role, _args):
        catalog = BankTasks(self.store).catalog(workspace, role)
        differences = {
            'WO-DEMO-001': '标准档，缺少客户端端口，需要追问。',
            'WO-DEMO-002': '保守档，资料已齐全，使用4/45/0与8443。',
            'WO-DEMO-003': '标准档，模拟回调验收失败，用于恢复演练。',
        }
        items = [{**{key: ticket[key] for key in ('id', 'title', 'summary', 'status', 'environment')},
                  'difference': differences[ticket['id']]}
                 for ticket in catalog['tickets']]
        return {'count': len(items), 'items': items,
                'source': self._source('workorder_catalog', fixture_version='1.0')}

    def read_workspace_context(self, workspace, role, _args):
        self.store._role(role)
        state = redact_all(self.store.snapshot(workspace, role))
        bank = BankOperations(self.store).snapshot(workspace, role)
        route = RouteDemo(self.store).snapshot(workspace, role)['route']
        return {'workspace': {'role': role, 'config_version': state.get('version'),
                              'proposal_count': len(state.get('proposals', [])),
                              'task_count': len(state.get('bank_tasks', []))},
                'bank': bank, 'route': route,
                'source': self._source('workspace_snapshot', config_version=state.get('version'))}

    def read_workorder(self, workspace, role, args):
        self.store._role(role, 'operator')
        ticket_id = str(args.get('ticket_id') or '')
        ticket = TICKETS.get(ticket_id)
        if ticket is None:
            raise DomainError('NOT_FOUND', '未找到该工单。', 404)
        return {'ticket': copy.deepcopy(ticket),
                'documents': [{key: item[key] for key in ('id', 'version', 'title', 'status', 'environment')}
                              for item in DOCUMENTS],
                'source': self._source('workorder_fixture', ticket_id=ticket_id,
                                       version=ticket['version'])}

    def read_records(self, workspace, role, args):
        collection = str(args.get('collection') or '')
        if collection not in self._COLLECTIONS:
            raise DomainError('INVALID_COLLECTION', '只能读取已登记的业务集合。')
        if collection in {'routes', 'adapters'}:
            route = RouteDemo(self.store).snapshot(workspace, role)['route']
            return {'collection': collection, 'items': copy.deepcopy(route[collection]),
                    'version': route['version'], 'source': self._source('route_snapshot', version=route['version'])}
        bank = BankOperations(self.store).snapshot(workspace, role)
        return {'collection': collection, 'items': copy.deepcopy(bank[collection]),
                'version': bank['version'], 'source': self._source('bank_snapshot', version=bank['version'])}

    def search_rules(self, workspace, role, args):
        self.store._role(role)
        query = str(args.get('query') or '')[:200]
        documents = self.store.knowledge(query, role)
        route_text = (RULE['title'] + RULE['content']).lower()
        if not query or query.lower() in route_text:
            documents = [*documents, copy.deepcopy(RULE)]
        return {'query': query, 'documents': redact_all(documents),
                'source': self._source('rule_search', query=query)}

    def read_pending_plans(self, workspace, role, _args):
        state = redact_all(self.store.snapshot(workspace, role))
        items = [proposal for proposal in state.get('proposals', []) if proposal.get('status') == 'pending']
        return {'count': len(items), 'items': items,
                'source': self._source('pending_plan_snapshot', config_version=state.get('version'))}

    def read_audit(self, workspace, role, _args):
        self.store._role(role)
        if role == 'reader':
            raise DomainError('FORBIDDEN', '当前岗位不能读取办理审计。', 403)
        items = self.store.audit(workspace, role)[-20:]
        return {'count': len(items), 'items': redact_all(items),
                'source': self._source('audit_snapshot')}

    def prepare_counter_change(self, workspace, role, args):
        limit = args.get('limit')
        if type(limit) is not int:
            raise DomainError('INVALID_VALUE', '限额必须是明确的整数元。')
        proposal = self.store.propose(workspace, role, 'counter', [{'field': 'limit', 'value': limit}],
                                      str(args.get('reason') or '用户明确要求的测试限额'), False)
        return {'proposal': redact_all(proposal),
                'source': self._source('backend_proposal', scenario='counter')}

    def prepare_integration_change(self, workspace, role, args):
        timeout, retries = args.get('timeout'), args.get('retries')
        if type(timeout) is not int or type(retries) is not int:
            raise DomainError('INVALID_VALUE', '超时和重试必须是明确整数。')
        proposal = self.store.propose(workspace, role, 'integration',
                                      [{'field': 'timeout', 'value': timeout}, {'field': 'retries', 'value': retries}],
                                      str(args.get('reason') or '用户明确要求的测试联调参数'), False)
        return {'proposal': redact_all(proposal),
                'source': self._source('backend_proposal', scenario='integration')}


    def prepare_route_plan(self, workspace, role, args):
        request = str(args.get('request') or '')
        selected = args.get('services')
        result = RouteDemo(self.store).plan(workspace, role, request, selected)
        return {'plan': redact_all(result),
                'source': self._source('route_plan')}
