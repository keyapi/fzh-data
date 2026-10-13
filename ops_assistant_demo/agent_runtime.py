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
                'read工具只读。prepare工具只生成待确认方案，助手自己不能落库。'
                '用户在界面确认之后，系统才执行测试环境变更、独立读回并验收；生产只生成申请，不能直接改。'
                '不要说本演示不执行任何变更。准确说法是：助手只准备方案；确认后才执行测试变更。'
                '先概括三类业务：核对工单并说明三张演练工单的差别；调整柜面测试限额；处理联调超时与重试，以及按用户点名的余额、明细或票据查询准备路由整组方案。'
                '用户只问能处理什么时，总回复不超过180字，恰好用三条简短业务概览，并附一句确认边界。不要罗列工单数量、编号、地址、规则号或参数范围；用户追问某项后再展开依据。概览不能声称未注册的自动办理已完成。'
                '只有用户点名要开通的业务时才调用prepare_route_plan。缺端口、协议或排除项时只追问这一项。'
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
