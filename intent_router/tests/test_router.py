"""router 测试：monkeypatch HTTP 边界，覆盖成功 / 429 重试 / 401 快速失败 / 529 耗尽。"""

from __future__ import annotations

import json

import pytest

from intent_router import router
from intent_router.catalog import load_catalog
from intent_router.typesafe import HttpError

CATALOG = load_catalog()

OK_BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "module": {
            "type": "choice",
            "choice": "item-cost",
            "confidence": 0.82,
            "probabilities": {"item-cost": 0.82, "stock-init": 0.1, "none": 0.08},
        },
        "ambiguity": {"type": "noul", "noul": 0.12},
        "verb": {
            "type": "choice",
            "choice": "generate",
            "confidence": 0.9,
            "probabilities": {"generate": 0.9, "apply": 0.1},
        },
    },
    "usage": {"input_tokens": 100, "output_tokens": 10},
}


class FakePost:
    """按顺序吐出预设的 (status, body)，并记录调用次数。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, payload, api_key, *, timeout):
        self.calls += 1
        if not self.responses:
            raise AssertionError("比预期多调用了一次 _post_typesafe")
        return self.responses.pop(0)


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []
    monkeypatch.setattr(router.time, "sleep", lambda seconds: recorded.append(seconds))
    return recorded


def _route(**kwargs):
    return router.route("把 BOM 成本导进赛狐", catalog=CATALOG, api_key="k", **kwargs)


def test_successful_route_fills_every_field(monkeypatch, sleeps):
    monkeypatch.setattr(router, "_post_typesafe", FakePost([(200, json.dumps(OK_BODY))]))
    result = _route()

    assert result.gate == router.GATE_OK
    assert result.skill == "item-cost"
    assert result.directory == "item_cost_sx/"
    assert result.confidence == 0.82
    assert result.verb == "generate"
    assert result.ambiguity == 0.12
    assert result.model == "jev-1.13.0"
    assert result.run == "cd item_cost_sx/ && uv run python bom_cost_to_saihu_item_cost.py"
    assert sleeps == []


def test_low_confidence_sets_reason_and_keeps_best_guess(monkeypatch, sleeps):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["confidence"] = 0.41
    body["answers"]["module"]["probabilities"] = {"item-cost": 0.41, "stock-init": 0.45, "none": 0.14}
    monkeypatch.setattr(router, "_post_typesafe", FakePost([(200, json.dumps(body))]))

    result = _route(min_confidence=0.5)
    assert result.gate == router.GATE_LOW_CONFIDENCE
    assert result.skill == "item-cost"
    assert "0.41" in result.reason and "0.50" in result.reason


def test_model_picking_none_yields_none_gate(monkeypatch, sleeps):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["choice"] = "none"
    body["answers"]["module"]["probabilities"] = {"none": 0.91, "item-cost": 0.09}
    monkeypatch.setattr(router, "_post_typesafe", FakePost([(200, json.dumps(body))]))

    result = _route()
    assert result.gate == router.GATE_NONE
    assert result.skill == "none"
    assert result.directory is None
    assert "none" in result.reason


def test_unknown_option_fails_closed_to_none(monkeypatch, sleeps):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["choice"] = "totally-made-up"
    body["answers"]["module"]["probabilities"] = {"totally-made-up": 0.7, "item-cost": 0.3}
    monkeypatch.setattr(router, "_post_typesafe", FakePost([(200, json.dumps(body))]))

    result = _route()
    assert result.gate == router.GATE_NONE
    assert result.skill is None
    assert "totally-made-up" in result.reason


def test_option_variant_is_normalized(monkeypatch, sleeps):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["choice"] = "item_cost"
    monkeypatch.setattr(router, "_post_typesafe", FakePost([(200, json.dumps(body))]))

    result = _route()
    assert result.gate == router.GATE_OK
    assert result.skill == "item-cost"


def test_429_retries_with_exponential_backoff_then_succeeds(monkeypatch, sleeps):
    post = FakePost([(429, "slow down"), (429, "slow down"), (200, json.dumps(OK_BODY))])
    monkeypatch.setattr(router, "_post_typesafe", post)

    result = _route()
    assert result.gate == router.GATE_OK
    assert post.calls == 3
    assert sleeps == [1, 2]


def test_529_overload_is_retried_then_gives_up(monkeypatch, sleeps):
    post = FakePost([(529, "overloaded"), (529, "overloaded"), (529, "overloaded")])
    monkeypatch.setattr(router, "_post_typesafe", post)

    with pytest.raises(HttpError) as caught:
        router.call_typesafe({"state": "x"}, "k")
    assert caught.value.status == 529
    assert post.calls == 3  # 用尽 3 次尝试
    assert sleeps == [1, 2]


def test_401_fails_fast_without_retrying(monkeypatch, sleeps):
    post = FakePost([(401, "invalid api key")])
    monkeypatch.setattr(router, "_post_typesafe", post)

    with pytest.raises(HttpError) as caught:
        _route()
    assert caught.value.status == 401
    assert post.calls == 1
    assert sleeps == []


def test_422_fails_fast_and_surfaces_body(monkeypatch, sleeps):
    monkeypatch.setattr(
        router, "_post_typesafe", FakePost([(422, "questions.module.criteria: bad field")])
    )

    with pytest.raises(HttpError) as caught:
        _route()
    assert caught.value.status == 422
    assert "bad field" in caught.value.body
    assert sleeps == []


def test_non_json_200_body_raises_http_error(monkeypatch, sleeps):
    monkeypatch.setattr(router, "_post_typesafe", FakePost([(200, "<html>not json</html>")]))

    with pytest.raises(HttpError, match="JSON"):
        _route()


def test_resolve_api_key_prefers_exported_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "exported-key")
    assert router.resolve_api_key() == "exported-key"


def test_resolve_api_key_reads_explicit_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('TYPESAFE_API_KEY="from-file"\n', encoding="utf-8")
    assert router.resolve_api_key(env_file) == "from-file"


def test_resolve_api_key_returns_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    empty = tmp_path / ".env"
    empty.write_text("OTHER=1\n", encoding="utf-8")
    assert router.resolve_api_key(empty) is None
