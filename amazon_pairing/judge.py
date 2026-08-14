from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from .candidates import CandidateProduct
from .candidates_v2 import CandidateScore


ALLOWED_FIELDS = {"listing_id", "target_sku", "confidence", "reason", "abstain", "missing_info"}
CONFIDENCE_TEXT = {
    "high": 0.9,
    "medium": 0.65,
    "low": 0.4,
    "very high": 0.98,
    "very low": 0.2,
}


@dataclass(frozen=True)
class JudgeResult:
    target_sku: str
    confidence: float
    reason: str
    abstain: bool
    missing_info: tuple[str, ...]


def parse_judge_response(
    content: str,
    listing_id: str,
    allowed_skus: set[str],
) -> JudgeResult:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("judge response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("judge response must be a JSON object")
    unknown = set(payload) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"unknown field: {sorted(unknown)[0]}")
    if payload.get("listing_id") != listing_id:
        raise ValueError("judge response listing_id does not match")
    target = str(payload.get("target_sku") or "")
    if target not in allowed_skus:
        raise ValueError(f"target {target or '<empty>'} not in candidate list")
    confidence = payload.get("confidence", 0)
    if isinstance(confidence, str):
        confidence = CONFIDENCE_TEXT.get(confidence.casefold(), 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric or high/medium/low") from exc
    abstain = bool(payload.get("abstain")) or confidence < 0.55
    missing = tuple(str(item) for item in (payload.get("missing_info") or []))
    return JudgeResult(
        target_sku=target,
        confidence=max(0.0, min(1.0, confidence)),
        reason=str(payload.get("reason") or ""),
        abstain=abstain,
        missing_info=missing,
    )


def build_judge_prompt(
    listing: dict,
    candidates: list[CandidateScore],
    catalog: dict[str, CandidateProduct],
) -> str:
    product_lines = []
    for row in candidates:
        product = catalog[row.sku]
        product_lines.append(
            f"- {row.sku} | {product.name} | score={row.score:.2f} | "
            f"evidence={','.join(row.evidence)} | conflicts={row.hard_conflicts}"
        )
    return (
        "你是跨境电商产品匹配助手。请判断以下 Amazon 在线商品与候选本地商品是否匹配。\n"
        "只输出 JSON，schema 必须严格为：\n"
        '{"listing_id":"<id>","target_sku":"<candidate sku>","confidence":<0-1>,"reason":"<原因>","abstain":<true/false>,"missing_info":["<缺什么>"]}\n'
        "confidence 低于 0.55、证据不足或属性冲突时必须 abstain=true。\n\n"
        f"Listing ID: {listing.get('listingId', '')}\n"
        f"MSKU: {listing.get('sku', '')}\n"
        f"标题: {listing.get('title', '')}\n"
        "候选：\n"
        + "\n".join(product_lines)
        + "\n"
    )


def _dashscope_api_key() -> str | None:
    key = os.getenv("DASHSCOPE_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DASHSCOPE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def judge_via_dashscope(
    prompt: str,
    listing_id: str,
    allowed_skus: set[str],
    api_key: str | None = None,
    model: str = "qwen3.7-flash",
) -> JudgeResult | None:
    key = api_key or _dashscope_api_key()
    if not key:
        return None
    response = requests.post(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 800,
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    try:
        return parse_judge_response(content, listing_id, allowed_skus)
    except ValueError:
        return None
