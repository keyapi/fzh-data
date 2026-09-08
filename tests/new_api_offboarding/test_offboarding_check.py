"""Unit tests for offboarding-check.py detection logic (no live API / docker)."""
from __future__ import annotations

import sqlite3

import pytest

import offboarding_check as oc


# ── classify_employment：离职信号判定 ─────────────────────────────────

def test_60121_not_found_is_departed(monkeypatch):
    """getbyunionid 返回 60121（员工已不在组织）→ 必须判 DEPARTED（应封号）。"""
    monkeypatch.setattr(oc, "api_post", lambda url, body: {
        "errcode": 60121, "errmsg": "not found",
    })
    state, userid, reason = oc.classify_employment("union-1", "tok")
    assert state == "DEPARTED"
    assert userid is None
    assert "60121" in reason


def test_system_busy_is_retry_not_departed(monkeypatch):
    """errcode=-1（系统繁忙/瞬时错误）→ RETRY，绝不因瞬时错误误封在职员工。"""
    monkeypatch.setattr(oc, "api_post", lambda url, body: {
        "errcode": -1, "errmsg": "system busy",
    })
    state, _, reason = oc.classify_employment("union-1", "tok")
    assert state == "RETRY"
    assert "-1" in reason


def test_other_errcode_is_retry(monkeypatch):
    monkeypatch.setattr(oc, "api_post", lambda url, body: {
        "errcode": 88, "errmsg": "permission",
    })
    state, _, _ = oc.classify_employment("union-1", "tok")
    assert state == "RETRY"


def test_network_error_is_retry(monkeypatch):
    def boom(url, body):
        raise RuntimeError("timeout")
    monkeypatch.setattr(oc, "api_post", boom)
    state, _, _ = oc.classify_employment("union-1", "tok")
    assert state == "RETRY"


def test_found_in_org_is_ok(monkeypatch):
    """getbyunionid 成功 → 员工仍在组织内 → OK（不封号），并返回 numeric userId。"""
    monkeypatch.setattr(oc, "api_post", lambda url, body: {
        "errcode": 0, "result": {"userid": "0147xxx", "contact_type": 0},
    })
    state, userid, reason = oc.classify_employment("union-1", "tok")
    assert state == "OK"
    assert userid == "0147xxx"
    assert reason == ""


def test_found_but_no_userid_is_retry(monkeypatch):
    monkeypatch.setattr(oc, "api_post", lambda url, body: {
        "errcode": 0, "result": {},
    })
    state, _, _ = oc.classify_employment("union-1", "tok")
    assert state == "RETRY"


# ── disable_proxy_keys：真实 sqlite 操作 ─────────────────────────────

def _make_proxy_db(path) -> None:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, dingtalk_union_id TEXT, is_active INTEGER)")
    db.execute("INSERT INTO api_keys (dingtalk_union_id, is_active) VALUES ('union-1', 1)")
    db.execute("INSERT INTO api_keys (dingtalk_union_id, is_active) VALUES ('union-1', 1)")
    db.execute("INSERT INTO api_keys (dingtalk_union_id, is_active) VALUES ('union-2', 1)")
    db.commit()
    db.close()


def test_disable_proxy_keys_only_target_union(tmp_path, monkeypatch):
    db_path = tmp_path / "sellfox-proxy.db"
    _make_proxy_db(str(db_path))
    monkeypatch.setenv("PROXY_DB_PATH", str(db_path))
    # monkeypatch 的是函数名，先复算一次拿到正确路径后调用
    count = oc.disable_proxy_keys("union-1")
    assert count == 2
    db = sqlite3.connect(str(db_path))
    active = db.execute(
        "SELECT COUNT(*) FROM api_keys WHERE is_active = 1"
    ).fetchone()[0]
    db.close()
    assert active == 1  # union-2 的 key 不受影响


def test_disable_proxy_keys_raises_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXY_DB_PATH", str(tmp_path / "nope.db"))
    with pytest.raises(RuntimeError):
        oc.disable_proxy_keys("union-1")


# ── upsert_identity_map / audit SQL 形状 ────────────────────────────

def test_upsert_identity_map_sql_is_idempotent(monkeypatch):
    captured = {}
    def fake_run_mysql(query):
        captured["query"] = query
        return ""
    monkeypatch.setattr(oc, "run_mysql", fake_run_mysql)
    monkeypatch.setattr(oc.time, "time", lambda: 1000)
    oc.upsert_identity_map("union-1", "0147xxx", "离职测试员工")
    assert "ON DUPLICATE KEY UPDATE" in captured["query"]
    assert "dingtalk_identity_map" in captured["query"]
    assert "0147xxx" in captured["query"]


def test_ddl_tables_cover_both_tables():
    ddl = " ".join(oc.DDL_TABLES)
    assert "dingtalk_identity_map" in ddl
    assert "offboarding_audit" in ddl
