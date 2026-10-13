"""LangChain-backed, read-first turn runtime for the embedded assistant."""
import json
import re
import time
import uuid

from domain import DomainError


MAX_HISTORY = 16


class AgentRuntime:
    """Keeps a small server-owned conversation envelope around a framework loop."""
    def __init__(self, tools, config=None):
        self.tools = tools
        self.config = config or {}

    def _history(self, session, workspace):
        if session.get('unified_agent_workspace') != workspace:
            session['unified_agent_workspace'] = workspace
            session['unified_agent_history'] = []
        return session.setdefault('unified_agent_history', [])[-MAX_HISTORY:]

    def _prompt(self, workspace, role):
        catalog = self.tools.catalog(role)['items']
        return ('你是受控运营演示助手。只处理模拟数据。先读取再回答；页面只是提示，不是权限或意图。'
                'read工具只读。prepare工具只能在用户给出明确数值时准备测试方案，仍须人工确认，绝不能声称已执行。'
                '所有数量、状态和工单差异必须来自本轮工具结果；'
                '没有对象时直接说未找到。回答先给一到三句结论，再说明依据与下一步。'
                f'当前服务端工作区={workspace}，岗位={role}。能力目录：'
                + json.dumps(catalog, ensure_ascii=False))

    def turn(self, session, text, workspace, role, runner=None):
        if not isinstance(text, str) or not text.strip():
            raise DomainError('INVALID_INPUT', '请输入要查询或办理的事项。')
        text = text.strip()[:3000]
        history = self._history(session, workspace)
        messages = [*history, {'role': 'user', 'content': text}]
        prompt, tools = self._prompt(workspace, role), self.tools.catalog(role)['items']
        turn_id = 'turn-' + uuid.uuid4().hex
        try:
            result = (runner(messages, prompt, tools) if runner
                      else self._langchain_runner(messages, prompt, tools, workspace, role))
        except DomainError:
            raise
        except Exception as exc:
            return {'turn_id': turn_id, 'outcome': 'failed',
                    'text': '本次读取没有完成，业务配置未改变。请稍后重试或使用页面上的明确操作。',
                    'trace': [], 'error': type(exc).__name__}
        answer = str(result.get('text') or '').strip()
        trace = result.get('trace') if isinstance(result.get('trace'), list) else []
        outcome = 'answered'
        if not answer:
            answer = '模型没有形成可核验回复，业务配置未改变。请换一种明确问法或稍后重试。'
            outcome = 'failed'
        session['unified_agent_history'] = [*messages, {'role': 'assistant', 'content': answer}][-MAX_HISTORY:]
        return {'turn_id': turn_id, 'outcome': outcome, 'text': answer, 'trace': trace,
                'source': 'langchain-create-agent' if runner is None else 'test-runner',
                'completed_at': int(time.time())}

    def _langchain_runner(self, messages, system_prompt, _descriptions, workspace, role):
        try:
            from langchain.agents import create_agent
            from langchain.tools import tool
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise DomainError('AGENT_RUNTIME_UNAVAILABLE', '统一助手运行时未安装，业务配置未改变。') from exc
        trace = []

        request = str(messages[-1].get('content') or '')

        def call(name, args):
            result = self.tools.invoke(name, workspace, role, args)
            trace.append({'tool': name, 'result': result})
            return json.dumps(result, ensure_ascii=False)

        @tool
        def list_capabilities():
            """列出当前岗位可调用的受控能力。"""
            return call('list_capabilities', {})
        @tool
        def list_workorders():
            """列出演练工单及它们的真实区别；不会创建任务。"""
            return call('list_workorders', {})
        @tool
        def read_workspace_context():
            """读取当前工作区的配置、任务、路由摘要与版本。"""
            return call('read_workspace_context', {})
        @tool
        def read_workorder(ticket_id: str):
            """读取指定演练工单原文；ticket_id必须来自目录。"""
            return call('read_workorder', {'ticket_id': ticket_id})
        @tool
        def read_records(collection: str):
            """读取一种集合：terminals、parameters、ip_configs、routes 或 adapters。"""
            return call('read_records', {'collection': collection})
        @tool
        def search_rules(query: str):
            """搜索当前岗位可见的模拟规则和依据。"""
            return call('search_rules', {'query': query})
        @tool
        def read_pending_plans():
            """读取当前待确认方案；不会批准或执行。"""
            return call('read_pending_plans', {})
        @tool
        def read_audit():
            """读取当前工作区最近的审计摘要。"""
            return call('read_audit', {})

        def expected_limit():
            match = re.search(r'(?<!\d)(\d+(?:\.\d+)?)\s*万', request)
            if match:
                return int(float(match.group(1)) * 10000)
            match = re.search(r'(?<!\d)(\d{4,})\s*元', request)
            return int(match.group(1)) if match else None

        @tool
        def prepare_counter_change(limit: int, reason: str):
            """准备明确的测试限额（元）方案；不会执行，且数值必须等于本轮用户请求。"""
            expected = expected_limit()
            if expected is None:
                return json.dumps({'error': 'MISSING_VALUE', 'message': '用户没有给出明确限额，先追问，未准备方案。'}, ensure_ascii=False)
            if limit != expected:
                return json.dumps({'error': 'VALUE_MISMATCH', 'message': '工具参数与用户明确限额不一致，未准备方案。'}, ensure_ascii=False)
            return call('prepare_counter_change', {'limit': limit, 'reason': reason})

        @tool
        def prepare_integration_change(timeout: int, retries: int, reason: str):
            """准备明确的测试联调超时（秒）和重试（次）方案；不会执行。"""
            timeout_match = re.search(r'(?:超时(?:调到|为|改为)?\s*)(\d+)\s*秒', request)
            retry_match = re.search(r'(?:重试(?:调到|为|改为)?\s*)(\d+)\s*次?', request)
            if not timeout_match or not retry_match:
                return json.dumps({'error': 'MISSING_VALUE', 'message': '必须同时明确超时秒数与重试次数，未准备方案。'}, ensure_ascii=False)
            if timeout != int(timeout_match.group(1)) or retries != int(retry_match.group(1)):
                return json.dumps({'error': 'VALUE_MISMATCH', 'message': '工具参数与用户明确值不一致，未准备方案。'}, ensure_ascii=False)
            return call('prepare_integration_change', {'timeout': timeout, 'retries': retries, 'reason': reason})

        base, key = self.config.get('OPENAI_API_BASE_URL'), self.config.get('OPENAI_API_KEY')
        if not base or not key:
            raise DomainError('MODEL_UNAVAILABLE', '模型未配置，无法运行统一助手。', 503)
        model = ChatOpenAI(model=self.config.get('OPENAI_MODEL', 'deepseek-v4-flash'), api_key=key,
                           base_url=base.rstrip('/'), temperature=0.2, max_completion_tokens=900,
                           timeout=45, max_retries=0, disabled_params={'parallel_tool_calls': None})
        tools = [list_capabilities, list_workorders, read_workspace_context, read_workorder,
                 read_records, search_rules, read_pending_plans, read_audit]
        if role == 'operator':
            tools.extend([prepare_counter_change, prepare_integration_change])
        agent = create_agent(model, tools,
                             system_prompt=system_prompt, name='controlled_workspace_agent')
        state = agent.invoke({'messages': messages})
        answer = ''
        for message in reversed(state.get('messages', [])):
            content = getattr(message, 'content', None)
            if getattr(message, 'type', '') == 'ai' and content:
                answer = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                break
        return {'text': answer, 'trace': trace}
