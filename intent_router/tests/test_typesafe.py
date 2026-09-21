"""纯函数测试：请求体形状、答案解析、选项归一化、阈值闸门。"""

from __future__ import annotations

import json

import pytest

from intent_router.catalog import load_catalog
from intent_router.typesafe import (
    AMBIGUITY_QUESTION,
    MAX_CHOICE_OPTIONS,
    MODULE_QUESTION,
    NONE_OPTION,
    VERB_QUESTION,
    HttpError,
    apply_gate,
    build_payload,
    normalize_option,
    parse_answer,
    render_criteria,
)

CATALOG = load_catalog()
SKILLS = set(CATALOG.skills)


def _payload(state: str = "导入库存初始值", **kwargs):
    return build_payload(state, CATALOG.options, **kwargs)


# --- build_payload -----------------------------------------------------------


def test_payload_has_one_key_per_module_plus_none():
    criteria = _payload()["questions"][MODULE_QUESTION]["criteria"]
    assert len(criteria) == len(CATALOG.options) + 1
    assert set(criteria) == SKILLS | {NONE_OPTION}


def test_payload_state_model_and_question_keys():
    payload = _payload("导入库存初始值")
    assert payload["state"] == "导入库存初始值"
    assert payload["model"] == "jev-latest"
    assert set(payload["questions"]) == {MODULE_QUESTION, AMBIGUITY_QUESTION, VERB_QUESTION}
    assert payload["questions"][AMBIGUITY_QUESTION]["type"] == "noul"
    assert payload["questions"][MODULE_QUESTION]["type"] == "choice"


def test_object_criteria_carry_coverage_exclusions_examples():
    criteria = _payload()["questions"][MODULE_QUESTION]["criteria"]
    for name, value in criteria.items():
        assert set(value) == {"coverage", "exclusions", "examples"}, name
        assert isinstance(value["coverage"], str) and value["coverage"]
        assert isinstance(value["exclusions"], str) and value["exclusions"]
        assert isinstance(value["examples"], list)


def test_string_criteria_style_flattens_to_string():
    criteria = _payload(criteria_style="string")["questions"][MODULE_QUESTION]["criteria"]
    for name, value in criteria.items():
        assert isinstance(value, str), name
        assert "覆盖：" in value and "排除：" in value


def test_examples_are_always_strings_even_when_yaml_coerces_numbers():
    # catalog 里曾把裸写的 401 解析成 int，这条守住回归
    criteria = _payload()["questions"][MODULE_QUESTION]["criteria"]
    for name, value in criteria.items():
        for example in value["examples"]:
            assert isinstance(example, str), (name, example)


def test_render_criteria_rejects_unknown_style():
    with pytest.raises(ValueError):
        render_criteria(CATALOG.option_for("item-cost"), style="xml")


def test_build_payload_rejects_none_in_catalog():
    with pytest.raises(ValueError):
        build_payload("x", [{"skill": "none", "coverage": "c", "exclusions": "e"}])


def test_build_payload_enforces_option_limit():
    options = [
        {"skill": f"mod-{index}", "coverage": "c", "exclusions": "e"}
        for index in range(MAX_CHOICE_OPTIONS)
    ]
    with pytest.raises(ValueError):
        build_payload("x", options)


def test_payload_is_json_serializable():
    json.dumps(_payload(), ensure_ascii=False)


# --- normalize_option --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("item-cost", "item-cost"),
        ("item_cost", "item-cost"),
        ("ITEM-COST", "item-cost"),
        ("Item Cost", "item-cost"),
        ("itemcost", "item-cost"),
        ("none", "none"),
    ],
)
def test_normalize_option_maps_variants(raw, expected):
    assert normalize_option(raw, SKILLS | {NONE_OPTION}) == expected


@pytest.mark.parametrize("raw", ["bogus", "", "   ", "totally-unknown", None, 42])
def test_normalize_option_fails_closed(raw):
    assert normalize_option(raw, SKILLS | {NONE_OPTION}) is None


# --- apply_gate -------------------------------------------------------------


def test_gate_none_wins_regardless_of_confidence():
    assert apply_gate(skill="none", confidence=0.99, min_confidence=0.5, none_winner=True) == "none"


def test_gate_low_confidence_below_threshold():
    assert apply_gate(skill="item-cost", confidence=0.41, min_confidence=0.5, none_winner=False) == "low_confidence"


def test_gate_threshold_boundary_is_inclusive():
    assert apply_gate(skill="item-cost", confidence=0.5, min_confidence=0.5, none_winner=False) == "ok"


def test_gate_ok_above_threshold():
    assert apply_gate(skill="item-cost", confidence=0.82, min_confidence=0.5, none_winner=False) == "ok"


def test_gate_unresolved_skill_is_none():
    assert apply_gate(skill=None, confidence=0.99, min_confidence=0.5, none_winner=False) == "none"


# --- parse_answer -----------------------------------------------------------


def _response(**overrides) -> dict:
    body = {
        "model": "jev-1.13.0",
        "answers": {
            MODULE_QUESTION: {
                "type": "choice",
                "choice": "item-cost",
                "confidence": 0.82,
                "probabilities": {"item-cost": 0.82, "stock-init": 0.1, NONE_OPTION: 0.08},
            },
            AMBIGUITY_QUESTION: {"type": "noul", "noul": 0.12},
            VERB_QUESTION: {
                "type": "choice",
                "choice": "generate",
                "confidence": 0.9,
                "probabilities": {"generate": 0.9, "apply": 0.1},
            },
        },
        "usage": {"input_tokens": 100, "output_tokens": 10},
    }
    body.update(overrides)
    return body


def test_parse_answer_extracts_every_field():
    parsed = parse_answer(_response())
    assert parsed["choice"] == "item-cost"
    assert parsed["confidence"] == 0.82
    assert parsed["verb"] == "generate"
    assert parsed["ambiguity"] == 0.12
    assert parsed["model"] == "jev-1.13.0"
    assert parsed["usage"]["input_tokens"] == 100


def test_parse_answer_requires_answers_block():
    with pytest.raises(ValueError, match="answers"):
        parse_answer({"model": "jev-1.13.0"})


def test_parse_answer_requires_module_question():
    body = _response()
    del body["answers"][MODULE_QUESTION]
    with pytest.raises(ValueError, match=MODULE_QUESTION):
        parse_answer(body)


def test_parse_answer_rejects_probabilities_not_summing_to_one():
    body = _response()
    body["answers"][MODULE_QUESTION]["probabilities"] = {"item-cost": 0.5, NONE_OPTION: 0.2}
    with pytest.raises(ValueError, match="之和"):
        parse_answer(body)


def test_parse_answer_rejects_non_numeric_confidence():
    body = _response()
    body["answers"][MODULE_QUESTION]["confidence"] = "high"
    with pytest.raises(ValueError, match="confidence"):
        parse_answer(body)


def test_parse_answer_rejects_missing_noul():
    body = _response()
    del body["answers"][AMBIGUITY_QUESTION]
    with pytest.raises(ValueError, match=AMBIGUITY_QUESTION):
        parse_answer(body)


def test_parse_answer_rejects_wrong_answer_type():
    body = _response()
    body["answers"][MODULE_QUESTION]["type"] = "noul"
    with pytest.raises(ValueError, match="choice"):
        parse_answer(body)


# --- HttpError --------------------------------------------------------------


def test_http_error_carries_status_and_body():
    error = HttpError(401, "invalid key")
    assert error.status == 401
    assert "invalid key" in error.body
