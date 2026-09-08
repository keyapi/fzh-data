"""Unit tests for stream_listener.py offboarding event handling (no live API)."""
from __future__ import annotations

import asyncio
import logging

import dingtalk_stream

# conftest 已把 new-api-dingtalk-oidc 放入 sys.path 并 stub dingtalk_stream
import stream_listener as sl


def _fake_event(user_ids):
    """Build a minimal EventMessage-shaped object for user_leave_org."""
    class _H:
        event_type = "user_leave_org"
        event_corp_id = "corp-1"
    class _E:
        headers = _H()
        data = {"UserId": user_ids}
    return _E()


def _patch_handler_ok(monkeypatch):
    """Common stubs for a well-configured handler: identity_map 命中即封号。"""
    monkeypatch.setattr(sl, "get_app_access_token", lambda: "tok")
    monkeypatch.setattr(sl, "ensure_schema", lambda: None)
    monkeypatch.setattr(sl, "lookup_union_id_by_user_id", lambda uid: "union-local-1")
    monkeypatch.setattr(sl, "find_user_by_unionid", lambda u: 42)
    monkeypatch.setattr(sl, "find_username_by_unionid", lambda u: "离职测试员工")


def test_non_leave_event_is_ignored():
    handler = sl.OffboardingHandler()

    class _H:
        event_type = "user_open_microapp"
        event_corp_id = "corp-1"
    class _E:
        headers = _H()
        data = {}
    status, _ = asyncio.run(handler.process(_E()))
    assert status == dingtalk_stream.AckMessage.STATUS_OK


def test_token_failure_returns_later(monkeypatch):
    handler = sl.OffboardingHandler()
    monkeypatch.setattr(sl, "get_app_access_token", lambda: (_ for _ in ()).throw(RuntimeError("no token")))
    status, _ = asyncio.run(handler.process(_fake_event(["u1"])))
    assert status == dingtalk_stream.AckMessage.STATUS_LATER


def test_user_removed_before_event_still_disabled_via_local_map(monkeypatch):
    """员工已被移出组织时 DingTalk 不再解析 userId；本地 identity_map 命中→仍封号。

    这是修复的核心：事件处理优先查本地映射，不依赖实时 get_user_by_id。
    """
    handler = sl.OffboardingHandler()
    _patch_handler_ok(monkeypatch)
    # 实时解析不可用（用户已被移除）——但本地映射已命中，不应调用
    monkeypatch.setattr(sl, "get_user_by_id", lambda uid, tok: None)
    disabled = {}
    monkeypatch.setattr(sl, "disable_new_api_user", lambda uid: disabled.update(user=uid) or True)
    monkeypatch.setattr(sl, "disable_proxy_keys", lambda u: 1)
    monkeypatch.setattr(sl, "insert_audit", lambda *a, **k: None)
    monkeypatch.setattr(sl, "delete_identity_map", lambda u: None)

    status, _ = asyncio.run(handler.process(_fake_event(["0147local"])))
    assert disabled.get("user") == 42
    assert status == dingtalk_stream.AckMessage.STATUS_OK


def test_proxy_unreachable_disables_new_api_then_redelivers(monkeypatch):
    """proxy DB 不可达：new-api 仍先被封（幂等），整包 STATUS_LATER 重投直到 proxy 成功。"""
    handler = sl.OffboardingHandler()
    _patch_handler_ok(monkeypatch)
    disabled = {}
    monkeypatch.setattr(sl, "disable_new_api_user", lambda uid: disabled.update(user=uid) or True)
    monkeypatch.setattr(
        sl, "disable_proxy_keys",
        lambda u: (_ for _ in ()).throw(RuntimeError("proxy db missing")),
    )
    audits = []
    monkeypatch.setattr(sl, "insert_audit", lambda *a, **k: audits.append(a))
    monkeypatch.setattr(sl, "delete_identity_map", lambda u: None)

    status, _ = asyncio.run(handler.process(_fake_event(["0147local"])))
    # new-api 必须已封；proxy 失败 → STATUS_LATER（钉钉会重投）
    assert disabled.get("user") == 42
    assert status == dingtalk_stream.AckMessage.STATUS_LATER
    assert any("proxy_pending" in a for a in audits)


def test_no_local_map_and_user_gone_logs_error_not_silent(monkeypatch, caplog):
    """本地映射缺失 + 实时也查不到 → 记 ERROR（不静默 continue，靠每日 60121 兜底）。"""
    handler = sl.OffboardingHandler()
    monkeypatch.setattr(sl, "get_app_access_token", lambda: "tok")
    monkeypatch.setattr(sl, "ensure_schema", lambda: None)
    monkeypatch.setattr(sl, "lookup_union_id_by_user_id", lambda uid: None)
    monkeypatch.setattr(sl, "get_user_by_id", lambda uid, tok: None)
    monkeypatch.setattr(sl, "disable_new_api_user", lambda uid: False)

    with caplog.at_level(logging.ERROR, logger="dingtalk_stream"):
        status, _ = asyncio.run(handler.process(_fake_event(["0147gone"])))
    assert status == dingtalk_stream.AckMessage.STATUS_OK
    assert "no local mapping" in caplog.text
