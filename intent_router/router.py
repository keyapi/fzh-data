"""编排：构造请求 → POST（带退避重试）→ 解析 → 阈值闸门。

重试策略：只有 429（限流）与 529（过载）重试，指数退避 1s / 2s，共 3 次尝试。
401（坏 key）与 422（校验失败）立即失败 —— 422 的响应体会指明坏字段，是最有价值的排错信号。
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from . import env as env_mod
from .catalog import Catalog
from .typesafe import (
    DEFAULT_TIMEOUT,
    MAX_ATTEMPTS,
    NONE_OPTION,
    RETRY_STATUSES,
    TYPESAFE_URL,
    HttpError,
    apply_gate,
    build_payload,
    normalize_option,
    parse_answer,
)

GATE_OK = "ok"
GATE_LOW_CONFIDENCE = "low_confidence"
GATE_NONE = "none"

API_KEY_NAME = "TYPESAFE_API_KEY"


@dataclass
class RouteResult:
    gate: str
    skill: str | None
    directory: str | None
    confidence: float
    probabilities: dict[str, float]
    verb: str | None
    ambiguity: float | None
    model: str | None
    min_confidence: float
    usage: dict[str, Any]
    run: str | None = None
    web_task: str | None = None
    reason: str | None = None
    raw_choice: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "skill": self.skill,
            "directory": self.directory,
            "confidence": self.confidence,
            "probabilities": self.probabilities,
            "verb": self.verb,
            "ambiguity": self.ambiguity,
            "model": self.model,
            "min_confidence": self.min_confidence,
            "usage": self.usage,
            "run": self.run,
            "web_task": self.web_task,
            "reason": self.reason,
            "raw_choice": self.raw_choice,
        }


def _post_typesafe(payload: dict, api_key: str, *, timeout: int) -> tuple[int, str]:
    response = requests.post(
        TYPESAFE_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    return response.status_code, response.text


def call_typesafe(payload: dict, api_key: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    status, text = 0, ""
    for attempt in range(MAX_ATTEMPTS):
        status, text = _post_typesafe(payload, api_key, timeout=timeout)
        if status in RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
            wait = 2**attempt
            print(
                f"  [TypeSafe 重试 {attempt + 1}/{MAX_ATTEMPTS}] HTTP {status}，{wait}s 后重试",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue
        break

    if status != 200:
        raise HttpError(status, text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpError(status, f"响应不是合法 JSON：{text[:300]}") from exc


def resolve_api_key(env_file: Path | None = None) -> str | None:
    """已 export 的环境变量永远优先；给了 --env-file 就只认它，否则走上溯加载。"""
    exported = (os.environ.get(API_KEY_NAME) or "").strip()
    if exported:
        return exported
    if env_file is not None:
        return env_mod.parse_env_file(env_file).get(API_KEY_NAME) or None
    return env_mod.get_key(API_KEY_NAME)


def route(
    text: str,
    *,
    catalog: Catalog,
    api_key: str,
    min_confidence: float = 0.5,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> RouteResult:
    payload = build_payload(text, catalog.options, model=model or catalog.model)
    body = call_typesafe(payload, api_key, timeout=timeout)
    parsed = parse_answer(body)

    known = set(catalog.skills) | {NONE_OPTION}
    raw_choice = parsed["choice"]
    skill = normalize_option(raw_choice, known)
    none_winner = skill is None or skill == NONE_OPTION
    gate = apply_gate(
        skill=skill,
        confidence=parsed["confidence"],
        min_confidence=min_confidence,
        none_winner=none_winner,
    )

    option = catalog.option_for(skill)
    reason = None
    if gate == GATE_NONE:
        reason = (
            "模型选择 none（请求与任何模块都不匹配）"
            if skill == NONE_OPTION
            else f"模型返回了 catalog 之外的选项 {raw_choice!r}"
        )
    elif gate == GATE_LOW_CONFIDENCE:
        reason = f"模型置信度 {parsed['confidence']:.2f} < 阈值 {min_confidence:.2f}"

    return RouteResult(
        gate=gate,
        skill=skill,
        directory=(option or {}).get("dir"),
        confidence=parsed["confidence"],
        probabilities=parsed["probabilities"],
        verb=parsed["verb"],
        ambiguity=parsed["ambiguity"],
        model=parsed["model"],
        min_confidence=min_confidence,
        usage=parsed["usage"],
        run=(option or {}).get("run"),
        web_task=(option or {}).get("web_task"),
        reason=reason,
        raw_choice=raw_choice,
    )
