"""CLI 测试：三态输出与退出码。HTTP 边界用 monkeypatch 打桩，不打网。"""

from __future__ import annotations

import json
import os

import pytest

from intent_router import cli, router
from intent_router.catalog import load_catalog


@pytest.fixture(autouse=True)
def _isolate_environment():
    """--verbose 会真的走一遍 .env 上溯并写 os.environ，快照还原以免污染其它测试。"""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


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


def _stub(monkeypatch, status: int, body: str):
    monkeypatch.setattr(router, "_post_typesafe", lambda payload, api_key, *, timeout: (status, body))


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")


def _run(argv):
    return cli.main(argv)


def test_hit_returns_exit_zero_and_prints_module(monkeypatch, api_key, capsys):
    _stub(monkeypatch, 200, json.dumps(OK_BODY))
    code = _run(["route", "把 BOM 成本导进赛狐"])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "item-cost" in out
    assert "item_cost_sx/" in out
    assert "0.82" in out
    assert "下一步" in out


def test_low_confidence_returns_exit_three(monkeypatch, api_key, capsys):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["confidence"] = 0.41
    body["answers"]["module"]["probabilities"] = {"item-cost": 0.41, "stock-init": 0.45, "none": 0.14}
    _stub(monkeypatch, 200, json.dumps(body))

    code = _run(["route", "那个东西弄一下"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_NEED_ACTION
    assert "无法判定，需人工/澄清" in out
    assert "最佳猜测" in out


def test_none_winner_omits_best_guess(monkeypatch, api_key, capsys):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["choice"] = "none"
    body["answers"]["module"]["probabilities"] = {"none": 0.9, "item-cost": 0.1}
    _stub(monkeypatch, 200, json.dumps(body))

    code = _run(["route", "帮我订机票"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_NEED_ACTION
    assert "无法判定，需人工/澄清" in out
    assert "最佳猜测" not in out


def test_api_error_returns_exit_two(monkeypatch, api_key, capsys):
    _stub(monkeypatch, 401, "invalid api key")

    code = _run(["route", "导入库存初始值"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_API_ERROR
    assert "调用失败" in out
    assert "401" in out


def test_missing_api_key_returns_exit_one(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    empty = tmp_path / ".env"
    empty.write_text("OTHER=1\n", encoding="utf-8")

    code = _run(["route", "导入库存初始值", "--env-file", str(empty)])
    out = capsys.readouterr().out
    assert code == cli.EXIT_USAGE
    assert "缺少凭证" in out
    assert out.count("结果") == 1  # 不能同时出现「缺少凭证」和「调用失败」


def test_json_output_is_parseable(monkeypatch, api_key, capsys):
    _stub(monkeypatch, 200, json.dumps(OK_BODY))
    code = _run(["route", "把 BOM 成本导进赛狐", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert payload["gate"] == "ok"
    assert payload["skill"] == "item-cost"
    assert payload["directory"] == "item_cost_sx/"
    assert payload["confidence"] == 0.82


def test_json_error_output(monkeypatch, api_key, capsys):
    _stub(monkeypatch, 422, "questions.module.criteria: bad field")
    code = _run(["route", "导入库存初始值", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_API_ERROR
    assert payload["gate"] == "api_error"
    assert payload["status"] == 422


def test_show_candidates_prints_full_distribution(monkeypatch, api_key, capsys):
    body = json.loads(json.dumps(OK_BODY))
    body["answers"]["module"]["confidence"] = 0.3
    body["answers"]["module"]["probabilities"] = {
        "item-cost": 0.3,
        "stock-init": 0.25,
        "item-weight": 0.2,
        "warehouse-restock": 0.15,
        "none": 0.1,
    }
    _stub(monkeypatch, 200, json.dumps(body))

    _run(["route", "成本", "--show-candidates"])
    out = capsys.readouterr().out
    assert "warehouse-restock" in out


def test_catalog_subcommand_lists_modules(capsys):
    code = _run(["catalog"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "item-cost" in out
    assert "stock-init" in out
    assert f"{len(load_catalog().options)} 个模块" in out


def test_catalog_json_lists_skills(capsys):
    code = _run(["catalog", "--json"])
    skills = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    # CLI 忠实反映 catalog，不另立一套
    assert set(skills) == set(load_catalog().skills)


def test_verbose_reports_loaded_env_files(monkeypatch, api_key, capsys):
    _stub(monkeypatch, 200, json.dumps(OK_BODY))
    _run(["route", "把 BOM 成本导进赛狐", "--verbose"])
    assert "已加载的 .env" in capsys.readouterr().err
