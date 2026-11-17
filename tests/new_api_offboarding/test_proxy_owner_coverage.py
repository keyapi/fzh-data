"""只持有赛狐 Key 的人也要被离职巡检覆盖（2026-11-17 补漏）。

离职链路原来只扫「new-api 绑定钉钉的用户」，只在赛狐有 Key 的人永远漏网。
这里固定住两条边界：枚举只取启用中的 Key、按 union_id 分组；已在 new-api
侧检查过的不重复调用钉钉接口。
"""
from __future__ import annotations

import sqlite3

import offboarding_check as oc


def _make_db(tmp_path):
    db_path = tmp_path / "proxy.db"
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE api_keys ("
        "id INTEGER PRIMARY KEY, dingtalk_union_id TEXT, dingtalk_user_name TEXT,"
        " is_active INTEGER)"
    )
    db.executemany(
        "INSERT INTO api_keys(dingtalk_union_id, dingtalk_user_name, is_active)"
        " VALUES (?, ?, ?)",
        [
            ("union-a", "甲", 1),
            ("union-a", "甲-备用Key", 1),
            ("union-b", "乙", 1),
            ("union-c", "丙", 0),
            ("", "无绑定", 1),
            (None, "空", 1),
        ],
    )
    db.commit()
    db.close()
    return db_path


def test_active_keys_grouped_by_union_id(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "_proxy_db_path", lambda: str(_make_db(tmp_path)))
    owners = dict(oc.fetch_active_proxy_owners())
    assert set(owners) == {"union-a", "union-b"}
    assert owners["union-a"] == ["甲", "甲-备用Key"]
    assert owners["union-b"] == ["乙"]


def test_inactive_and_unbound_keys_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "_proxy_db_path", lambda: str(_make_db(tmp_path)))
    owners = dict(oc.fetch_active_proxy_owners())
    assert "union-c" not in owners
    assert "" not in owners


def test_missing_db_raises_so_caller_can_warn(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "_proxy_db_path", lambda: str(tmp_path / "nope.db"))
    try:
        oc.fetch_active_proxy_owners()
    except RuntimeError as error:
        assert "not found" in str(error)
    else:
        raise AssertionError("missing proxy DB must raise")


def test_covered_union_ids_are_not_rechecked():
    owners = [("union-a", ["甲"]), ("union-b", ["乙"])]
    assert oc.uncovered_proxy_owners(owners, {"union-a"}) == [("union-b", ["乙"])]
    assert oc.uncovered_proxy_owners(owners, {"union-a", "union-b"}) == []
