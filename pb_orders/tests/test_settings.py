#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""断货 SKU 设置页：在页面上自己维护，不必再改服务器 `.env`。

覆盖三件事：解析与去重规则、保存后新建任务页的预填跟着变、以及没 CSRF 时不允许改。
"""

from __future__ import annotations

import pytest

from web.app import parse_sku_list


def _csrf(client) -> str:
    page = client.get("/settings")
    assert page.status_code == 200
    token = client.cookies.get("pb_orders_csrf")
    assert token
    return token


# ---------- 解析规则 ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A-1, B-2", ["A-1", "B-2"]),
        ("A-1\nB-2\n\n", ["A-1", "B-2"]),
        ("A-1，B-2；C-3", ["A-1", "B-2", "C-3"]),   # 中文逗号 / 分号也认
        ("  A-1   B-2  ", ["A-1", "B-2"]),           # 空格分隔
        ("cen-a-97,CEN-A-97", ["cen-a-97"]),         # 大小写不敏感去重，保留首次写法
        ("", []),
        ("   \n  ", []),
    ],
)
def test_parse_sku_list(raw, expected):
    assert parse_sku_list(raw) == expected


# ---------- 页面与保存 ----------

def test_settings_page_falls_back_to_env_default(client, pb_env):
    page = client.get("/settings")
    assert page.status_code == 200
    # 没在页面里设过 -> 显示 .env 的初始值
    assert client.repo.get_setting("default_no_stock") is None
    assert "还没有在页面里改过" in page.text


def test_save_then_new_job_prefills_the_saved_list(client, pb_env):
    resp = client.post(
        "/settings/no-stock",
        data={"no_stock": "CEN-A-97\ncen-b-138", "csrf": _csrf(client)},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/settings?saved=1")

    stored = client.repo.get_setting("default_no_stock")
    assert stored["value"] == "CEN-A-97,cen-b-138"
    assert stored["updated_by"], "要记下是谁改的"
    assert stored["updated_at"]

    assert "CEN-A-97,cen-b-138" in client.get("/jobs/new").text


def test_save_can_clear_the_list(client, pb_env):
    client.post("/settings/no-stock", data={"no_stock": "X-1", "csrf": _csrf(client)})
    client.post("/settings/no-stock", data={"no_stock": "", "csrf": _csrf(client)})
    assert client.repo.get_setting("default_no_stock")["value"] == ""
    # 留空 = 任务页不预填
    assert "X-1" not in client.get("/jobs/new").text


def test_save_without_csrf_is_rejected(client):
    resp = client.post("/settings/no-stock", data={"no_stock": "X-1"})
    assert resp.status_code == 403
    assert client.repo.get_setting("default_no_stock") is None


def test_page_has_nav_entry(client):
    """导航里要能点到，不然等于藏着。"""
    assert "断货 SKU" in client.get("/").text
