#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`check_org_membership` 的三态契约。

桥的登录闸门（`main.py` 的 `/callback`）用它判定「是不是本公司员工」，
所以**「不在组织」（60121/60111）必须和「判定不了」（网络/权限/异常响应）
区分开**：两者都拒绝登录，但要给用户不同的话，也要在日志里看得出来。

`stream_listener` 依赖 `dingtalk_stream` / `pymysql`（只在桥的镜像里，本仓库根
venv 没有），所以这里用桩模块替掉，让测试能在仓库根直接跑：

    uv run pytest new-api-dingtalk-oidc/tests -q
"""

from __future__ import annotations

import pathlib
import sys
import types

import pytest

_MODULE_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))


class _Any:
    """松散替身：stream_listener 的注解会即时求值（`pymysql.Connection`、
    `dingtalk_stream.EventMessage`），所以桩模块得能长出任意属性。"""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return _Any


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any


for _name in ("dingtalk_stream", "pymysql"):
    sys.modules.setdefault(_name, _StubModule(_name))

import httpx  # noqa: E402
import stream_listener  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _reply(monkeypatch, payload):
    monkeypatch.setattr(stream_listener.httpx, "post", lambda *a, **k: _Resp(payload))


@pytest.mark.parametrize("code", [60121, 60111])
def test_not_in_org_is_false(monkeypatch, code):
    """不在本公司通讯录（含已离职被移出）—— 必须判成 False，不是「判定不了」。"""
    _reply(monkeypatch, {"errcode": code, "errmsg": "user not exist"})
    assert stream_listener.check_org_membership("u1", "token") is False


def test_member_is_true(monkeypatch):
    _reply(monkeypatch, {"errcode": 0, "result": {"userid": "0123456789"}})
    assert stream_listener.check_org_membership("u1", "token") is True


def test_invalid_unionid_errcode_is_unknown(monkeypatch):
    """实测：格式非法的 unionId 返回 40035「不合法的参数」，不是 60121 —— 归入判定不了。"""
    _reply(monkeypatch, {"errcode": 40035, "errmsg": "不合法的参数 unionid"})
    assert stream_listener.check_org_membership("bad-unionid", "token") is None


def test_other_errcode_is_unknown(monkeypatch):
    """权限/限流等错误不能当成「不是成员」——否则一旦接口出问题就会误拒在职同事。"""
    _reply(monkeypatch, {"errcode": 88, "errmsg": "permission denied"})
    assert stream_listener.check_org_membership("u1", "token") is None


def test_network_error_is_unknown(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(stream_listener.httpx, "post", boom)
    assert stream_listener.check_org_membership("u1", "token") is None


def test_unparsable_errcode_is_unknown(monkeypatch):
    _reply(monkeypatch, {"errcode": "oops"})
    assert stream_listener.check_org_membership("u1", "token") is None


def test_ok_without_userid_is_unknown(monkeypatch):
    """errcode=0 却没有 userid 属异常响应，归入「判定不了」而不是「不是成员」。"""
    _reply(monkeypatch, {"errcode": 0, "result": {}})
    assert stream_listener.check_org_membership("u1", "token") is None
