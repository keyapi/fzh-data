"""LangChain-backed, read-first turn runtime for the embedded assistant."""
import json
import re
import time
import uuid

from domain import DomainError


MAX_HISTORY = 16
_CAPABILITY_QUESTION = re.compile(r'能执行什么|能做什么|能处理什么|哪些工具|什么权限|现行规则|可办事项|有哪些规则')
_ROLE_TITLE = {
    'operator': '林晓 · 柜面主管',
    'reader': '陈默 · 综合柜员（只读）',
    'reviewer': '周宁 · 参数管理员（复核）',
}
_ROLE_BOUNDARY = {
    'operator': '可读取工作区，并可准备测试环境方案。人确认后系统才写入测试环境。生产不直接改。',
    'reader': '只读。可查看测试资料和待确认方案，不能准备变更，也不返回生产制度全文。',
    'reviewer': '可查看审计和待确认方案。不准备变更。复核只处理模拟申请，不执行生产变更。',
}


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
                'read工具只读。prepare工具只生成待确认方案，助手自己不能落库。'
                '用户在界面确认之后，系统才执行测试环境变更、独立读回并验收；生产只生成申请，不能直接改。'
                '不要说本演示不执行任何变更。准确说法是：助手只准备方案；确认后才执行测试变更。'
                '用户问能执行什么、有哪些工具、什么权限或有哪些规则时，必须先调用list_capabilities和search_rules，再按本轮工具结果回答。即使历史对话里曾缩成三类，也以本轮工具结果重新回答，不要沿用旧的三类概括。'
                '回答顺序：当前岗位可直接读取的事项；可准备的方案，以及确认后才写入测试环境；知识库现行规则的标题和要点。'
                '接入工单在对话里只能列出和读取，不能在对话里建立任务或改配置。建立任务、补端口和整组确认在接入工单页面完成。'
                '业务路由只有用户点名余额、明细或票据时才调用prepare_route_plan。缺端口、协议或排除项时只追问这一项。确认后才写入。'
                '终端注册、注册参数、固定IP在对应页面办理，不在这组对话工具里。'
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
        citations = []
        if _CAPABILITY_QUESTION.search(text):
            answer, citations = self._readable_brief(workspace, role, trace)
        session['unified_agent_history'] = [*messages, {'role': 'assistant', 'content': answer}][-MAX_HISTORY:]
        return {'turn_id': turn_id, 'outcome': outcome, 'text': answer, 'trace': trace,
                'citations': citations,
                'source': 'langchain-create-agent' if runner is None else 'test-runner',
                'completed_at': int(time.time())}

    def _readable_brief(self, workspace, role, trace):
        """Render a capability answer from this turn's tool results, not model wording."""
        items, documents = [], []
        for entry in trace:
            result = entry.get('result') if isinstance(entry, dict) else None
            if not isinstance(result, dict):
                continue
            if entry.get('tool') == 'list_capabilities':
                items = result.get('items') or items
            elif entry.get('tool') == 'search_rules' and result.get('documents'):
                documents = result['documents']
        if not items:
            found = self.tools.invoke('list_capabilities', workspace, role, {})
            items = found.get('items') or []
            trace.append({'tool': 'list_capabilities', 'result': found})
        if not documents:
            found = self.tools.invoke('search_rules', workspace, role, {'query': '现行规则'})
            documents = found.get('documents') or []
            trace.append({'tool': 'search_rules', 'result': found})
        reads = [item for item in items if item.get('kind') == 'read']
        prepares = [item for item in items if item.get('kind') == 'prepare']
        lines = [
            f"当前岗位：{_ROLE_TITLE.get(role, role)}",
            _ROLE_BOUNDARY.get(role, ''),
            '以下来自本轮能力登记和规则检索。助手只准备方案；确认后系统才写入测试环境并读回。生产只生成申请。',
            '',
            '可直接读取',
        ]
        lines.extend(f"{index}. {item.get('description')}" for index, item in enumerate(reads, 1))
        lines.append('')
        if prepares:
            lines.append('可准备方案，确认后才写入测试环境')
            lines.extend(f"{index}. {item.get('description')}" for index, item in enumerate(prepares, 1))
        else:
            lines.append('当前岗位不能准备变更。')
        lines.extend(['', '模拟知识库现行规则'])
        lines.extend(
            f"{index}. {doc.get('id')} {doc.get('title')}（v{doc.get('version')}）。{doc.get('content')}"
            for index, doc in enumerate(documents, 1))
        lines.extend(['', '过期规范和安全测试夹具不进入这份现行清单。'])
        citations = [{'id': doc.get('id'), 'title': doc.get('title'), 'version': doc.get('version'),
                      'content': doc.get('content'), 'status': doc.get('status')} for doc in documents]
        return '\n'.join(lines), citations

    def _langchain_runner(self, messages, system_prompt, _descriptions, workspace, role):
        try:
            from langchain.agents import create_agent
            from langchain_core.tools import StructuredTool
            from langchain_openai import ChatOpenAI
            from pydantic import create_model
        except ImportError as exc:
            raise DomainError('AGENT_RUNTIME_UNAVAILABLE', '统一助手运行时未安装，业务配置未改变。') from exc
        trace = []
        request = str(messages[-1].get('content') or '')

        def expected_limit():
            match = re.search(r'(?<!\d)(\d+(?:\.\d+)?)\s*万', request)
            if match:
                return int(float(match.group(1)) * 10000)
            match = re.search(r'(?<!\d)(\d{4,})\s*元', request)
            return int(match.group(1)) if match else None

        def call(name, args):
            # Semantic guards belong beside the registry dispatch, not in a
            # second hand-written LangChain tool list.
            if name == 'prepare_counter_change':
                expected = expected_limit()
                if expected is None:
                    return json.dumps({'error': 'MISSING_VALUE', 'message': '用户没有给出明确限额，先追问，未准备方案。'}, ensure_ascii=False)
                if args.get('limit') != expected:
                    return json.dumps({'error': 'VALUE_MISMATCH', 'message': '工具参数与用户明确限额不一致，未准备方案。'}, ensure_ascii=False)
            if name == 'prepare_integration_change':
                timeout_match = re.search(r'(?:超时(?:调到|为|改为)?\s*)(\d+)\s*秒', request)
                retry_match = re.search(r'(?:重试(?:调到|为|改为)?\s*)(\d+)\s*次?', request)
                if not timeout_match or not retry_match:
                    return json.dumps({'error': 'MISSING_VALUE', 'message': '必须同时明确超时秒数与重试次数，未准备方案。'}, ensure_ascii=False)
                if args.get('timeout') != int(timeout_match.group(1)) or args.get('retries') != int(retry_match.group(1)):
                    return json.dumps({'error': 'VALUE_MISMATCH', 'message': '工具参数与用户明确值不一致，未准备方案。'}, ensure_ascii=False)
            result = self.tools.invoke(name, workspace, role, args)
            trace.append({'tool': name, 'result': result})
            return json.dumps(result, ensure_ascii=False)

        def make_tool(spec):
            fields = {key: (value, ...) for key, value in spec['arguments'].items()}
            schema = create_model(f"{spec['name'].title().replace('_', '')}Input", **fields)
            def handler(**args):
                return call(spec['name'], args)
            return StructuredTool.from_function(handler, name=spec['name'], description=spec['description'], args_schema=schema)

        base, key = self.config.get('OPENAI_API_BASE_URL'), self.config.get('OPENAI_API_KEY')
        if not base or not key:
            raise DomainError('MODEL_UNAVAILABLE', '模型未配置，无法运行统一助手。', 503)
        model = ChatOpenAI(model=self.config.get('OPENAI_MODEL', 'deepseek-v4-flash'), api_key=key,
                           base_url=base.rstrip('/'), temperature=0.2, max_completion_tokens=900,
                           timeout=45, max_retries=0, disabled_params={'parallel_tool_calls': None})
        tools = [make_tool(spec) for spec in self.tools.capability_specs(role)]
        agent = create_agent(model, tools, system_prompt=system_prompt, name='controlled_workspace_agent')
        state = agent.invoke({'messages': messages})
        answer = ''
        for message in reversed(state.get('messages', [])):
            content = getattr(message, 'content', None)
            if getattr(message, 'type', '') == 'ai' and content:
                answer = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                break
        return {'text': answer, 'trace': trace}
