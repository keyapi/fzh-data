"""System One 请求体构造与答案解析 —— 纯函数，无网络、无文件 IO，便于单测。

契约来源：https://docs.typesafe.ai/api.md 与 /primitives/choice.md
关键点：
  - 一次 POST 问三个问题（官方文档：并行评估，几乎不额外增加延迟）
  - choice 的 criteria 是 {选项名: 描述}；选项名和描述都会送给模型
  - criteria 值可以是 string / object / array（官方示例即用 object 带自定义字段）
  - 只有输入计费；输出免费
"""

from __future__ import annotations

from typing import Any, Iterable

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
RETRY_STATUSES = frozenset({429, 529})
MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT = 60
MAX_CHOICE_OPTIONS = 255

NONE_OPTION = "none"
MODULE_QUESTION = "module"
AMBIGUITY_QUESTION = "ambiguity"
VERB_QUESTION = "verb"

MODULE_INSTRUCTIONS = (
    "把用户的中文请求路由到本仓库的一个业务模块。"
    "只依据请求本身可推断的意图选择；信息不足或与任何模块都不匹配时选 none。"
)

AMBIGUITY_INSTRUCTIONS = (
    "用户请求是否缺少做出路由所必需的关键限定（平台/系统、时间范围、SKU 或单据范围、数据源文件）。"
    "表述清楚且限定充分→接近 0；含糊、缺关键限定、或可能指向多个模块→接近 1。"
)

AMBIGUITY_CRITERIA = {
    "true": "含糊、缺关键限定、或可能指向多个模块",
    "false": "意图清楚、限定充分",
}

VERB_INSTRUCTIONS = "用户请求里的主要动作类型。"

VERB_CRITERIA = {
    "query": "只读查询/查看/排查",
    "generate": "生成导入文件或报表",
    "apply": "写回/创建/更新到业务系统",
    "reconcile": "对账/比对",
    "other": None,
    "unclear": None,
}

NONE_OPTION_CRITERIA = {
    "coverage": "请求与本仓库任何模块都不匹配，或信息不足以判断是哪一个",
    "exclusions": "只要能归到某个模块就不要选这项",
    "examples": ["今天天气怎么样", "帮我订机票", "随便弄一下"],
}


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def render_criteria(option: dict[str, Any], *, style: str = "object") -> Any:
    """把 catalog 条目渲染成 criteria 值。style="string" 是保险丝：万一带 object 的
    criteria 被 API 拒绝（422），切过去即可发同一份信息。"""
    if style == "string":
        parts = [f"覆盖：{option['coverage']}", f"排除：{option['exclusions']}"]
        examples = option.get("examples")
        if examples:
            parts.append("例：" + "、".join(str(example) for example in examples))
        return " ".join(parts)
    if style != "object":
        raise ValueError(f"未知的 criteria style：{style!r}")
    return {
        "coverage": option["coverage"],
        "exclusions": option["exclusions"],
        # 显式 str()：YAML 会把裸写的 401 / 1.7 这类标量解析成数字
        "examples": [str(example) for example in option.get("examples", [])],
    }


def build_payload(
    state: str,
    options: Iterable[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    criteria_style: str = "object",
) -> dict[str, Any]:
    """构造 System One 请求体。none 选项恒由此处追加，不进 catalog。"""
    options = list(options)
    criteria: dict[str, Any] = {}
    for option in options:
        skill = option["skill"]
        if skill == NONE_OPTION:
            raise ValueError("none 选项由 build_payload 追加，不应出现在 catalog 里")
        criteria[skill] = render_criteria(option, style=criteria_style)
    criteria[NONE_OPTION] = render_criteria(NONE_OPTION_CRITERIA, style=criteria_style)

    if len(criteria) > MAX_CHOICE_OPTIONS:
        raise ValueError(f"选项数 {len(criteria)} 超过 Choice 上限 {MAX_CHOICE_OPTIONS}")

    return {
        "state": state,
        "model": model,
        "questions": {
            MODULE_QUESTION: {
                "type": "choice",
                "instructions": MODULE_INSTRUCTIONS,
                "criteria": criteria,
            },
            AMBIGUITY_QUESTION: {
                "type": "noul",
                "instructions": AMBIGUITY_INSTRUCTIONS,
                "criteria": AMBIGUITY_CRITERIA,
            },
            VERB_QUESTION: {
                "type": "choice",
                "instructions": VERB_INSTRUCTIONS,
                "criteria": VERB_CRITERIA,
            },
        },
    }


def _squash(raw: str) -> str:
    return raw.strip().lower().replace("_", "-").replace(" ", "-").replace("/", "-")


def normalize_option(raw: str, known: Iterable[str]) -> str | None:
    """把模型可能回显的变体归一到 catalog 的规范名；归不了一律返回 None（fail closed）。"""
    if not isinstance(raw, str):
        return None
    known = set(known)
    if raw in known:
        return raw
    squashed = _squash(raw)
    if squashed in known:
        return squashed
    compact = squashed.replace("-", "")
    for candidate in known:
        if candidate.replace("-", "") == compact:
            return candidate
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _choice_answer(answers: dict[str, Any], key: str) -> tuple[str, float, dict[str, float]]:
    answer = answers.get(key)
    if not isinstance(answer, dict):
        raise ValueError(f"响应缺少 answers.{key}")
    if answer.get("type") != "choice":
        raise ValueError(f"answers.{key}.type 应为 choice，实际为 {answer.get('type')!r}")
    choice = answer.get("choice")
    if not isinstance(choice, str) or not choice:
        raise ValueError(f"answers.{key}.choice 缺失或不是非空字符串")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or not probabilities:
        raise ValueError(f"answers.{key}.probabilities 缺失或不是对象")
    for name, value in probabilities.items():
        if not _is_number(value):
            raise ValueError(f"answers.{key}.probabilities[{name!r}] 不是数值")
    total = sum(probabilities.values())
    if not 0.98 <= total <= 1.02:
        raise ValueError(f"answers.{key}.probabilities 之和为 {total:.4f}，应接近 1")
    confidence = answer.get("confidence")
    if not _is_number(confidence):
        raise ValueError(f"answers.{key}.confidence 缺失或不是数值")
    return choice, float(confidence), {name: float(value) for name, value in probabilities.items()}


def parse_answer(body: dict[str, Any]) -> dict[str, Any]:
    """抽取并严格校验三个答案。字段缺失/类型不符一律抛 ValueError（fail closed）。"""
    if not isinstance(body, dict):
        raise ValueError("响应不是 JSON 对象")
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("响应缺少 answers 字段")

    choice, confidence, probabilities = _choice_answer(answers, MODULE_QUESTION)
    verb, _, _ = _choice_answer(answers, VERB_QUESTION)

    ambiguity_answer = answers.get(AMBIGUITY_QUESTION)
    if not isinstance(ambiguity_answer, dict) or ambiguity_answer.get("type") != "noul":
        raise ValueError(f"响应缺少 answers.{AMBIGUITY_QUESTION}（noul）")
    ambiguity = ambiguity_answer.get("noul")
    if not _is_number(ambiguity):
        raise ValueError(f"answers.{AMBIGUITY_QUESTION}.noul 不是数值")

    return {
        "choice": choice,
        "confidence": confidence,
        "probabilities": probabilities,
        "verb": verb,
        "ambiguity": float(ambiguity),
        "model": body.get("model"),
        "usage": body.get("usage") or {},
    }


def apply_gate(
    *,
    skill: str | None,
    confidence: float,
    min_confidence: float,
    none_winner: bool,
) -> str:
    """三态闸门。code 拥有 dispatch —— 模型只给分布，阈值判断在这里。"""
    if none_winner or skill is None:
        return "none"
    if confidence < min_confidence:
        return "low_confidence"
    return "ok"
