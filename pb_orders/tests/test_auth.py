#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证闸门：未登录拦截、签名会话、白名单、登录回调、URL 前缀。

不需要真钉钉：回调里对 OIDC 桥的两次 HTTP 调用被替换成桩。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import web.app as web_app
import web.auth as web_auth
import web.tasks as web_tasks
from sellfox_shipping.auth_oidc import make_session_token
from conftest import StripPrefix
from web.config import get_settings, reset_settings
from web.repository import Repository

ISSUER = "https://api.example.test/oidc"
REDIRECT = "https://api.example.test/pb/oidc-callback"
SECRET = "test-session-secret"
PREFIX = "/pb"


def _enable_auth(monkeypatch, *, allowed: str = ""):
    monkeypatch.setenv("PB_ORDERS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("PB_ORDERS_OIDC_CLIENT_ID", "pb-orders")
    monkeypatch.setenv("PB_ORDERS_OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("PB_ORDERS_OIDC_REDIRECT_URI", REDIRECT)
    monkeypatch.setenv("PB_ORDERS_SESSION_SECRET", SECRET)
    monkeypatch.setenv("PB_ORDERS_ALLOWED_USERS", allowed)
    reset_settings()


@pytest.fixture
def auth_client(pb_env, monkeypatch):
    """开启认证、带 /pb 前缀的客户端；队列替换成同步执行。"""
    _enable_auth(monkeypatch)
    monkeypatch.setenv("PB_ORDERS_URL_PREFIX", PREFIX)
    reset_settings()

    def sync_enqueue(settings, repo, job_id):
        repo.mark_queued(job_id, "test-worker-job")
        web_tasks.run_job(job_id)

    monkeypatch.setattr(web_app, "enqueue_job", sync_enqueue)
    app = web_app.create_app()
    with TestClient(StripPrefix(app, PREFIX)) as c:
        c.repo = Repository(get_settings().db_path)
        yield c


def _cookie(name="张三", sub="user-123") -> str:
    return make_session_token(sub, name, secret=SECRET, ttl=3600)


def _expired_cookie(seed=40000, sub="user-123", name="张三") -> str:
    """手工造一个「签名正确但时间戳很旧」的 token（TTL 8h，seed 秒之前）。"""
    import hashlib
    import hmac
    from urllib.parse import quote

    ts = str(int(time.time()) - seed)
    payload = f"{ts}|{sub}|{quote(name, safe='')}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}|{sig}"


def _login(c, name="张三", sub="user-123"):
    # path 必须与后端 set_cookie 的 path 一致，否则 logout 的 delete 不会命中
    c.cookies.set(web_auth.COOKIE_NAME, _cookie(name, sub), path=PREFIX + "/")


def _csrf(c) -> str:
    page = c.get(f"{PREFIX}/jobs/new")
    assert page.status_code == 200
    token = c.cookies.get("pb_orders_csrf")
    assert token
    return token


# ---------- 未登录拦截 ----------

def test_anonymous_settings_redirects_to_login(auth_client):
    """设置页也要登录 —— 它决定以后每次出件怎么过滤 SKU。"""
    resp = auth_client.get(PREFIX + "/settings", follow_redirects=False)
    assert resp.status_code == 303
    assert "/oidc-login" in resp.headers["location"]


def test_anonymous_cannot_save_settings(auth_client):
    resp = auth_client.post(
        PREFIX + "/settings/no-stock", data={"no_stock": "X-1"}, follow_redirects=False
    )
    assert resp.status_code == 303  # 闸门拦下，且用 303（POST 不会被重放）
    assert auth_client.repo.get_setting("default_no_stock") is None


def test_anonymous_page_redirects_to_login(auth_client):
    resp = auth_client.get(PREFIX + "/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/pb/oidc-login" in resp.headers["location"]
    # return_to 必须带前缀：不带的话登录后会跳到域名根路径（那是别的服务）
    assert "return_to=%2Fpb%2F" in resp.headers["location"]


def test_anonymous_download_redirects_to_login(auth_client):
    resp = auth_client.get(f"{PREFIX}/artifacts/art-x/download", follow_redirects=False)
    assert resp.status_code == 303
    assert "/pb/oidc-login" in resp.headers["location"]


def test_anonymous_poll_gets_401_not_login_html(auth_client):
    """轮询片段被拦时必须是 401，否则登录页 HTML 会被塞进面板。"""
    resp = auth_client.get(
        f"{PREFIX}/jobs/job-x/status",
        headers={"X-Requested-With": "fetch"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


def test_healthz_is_public(auth_client):
    resp = auth_client.get(f"{PREFIX}/healthz")
    assert resp.status_code in (200, 503)


def test_static_is_public(auth_client):
    assert auth_client.get(f"{PREFIX}/static/style.css").status_code == 200


# ---------- 会话 cookie ----------

def test_valid_cookie_reaches_page(auth_client):
    _login(auth_client)
    resp = auth_client.get(PREFIX + "/")
    assert resp.status_code == 200
    assert "历史任务" in resp.text


def test_tampered_cookie_is_rejected(auth_client):
    token = _cookie()
    auth_client.cookies.set(web_auth.COOKIE_NAME, token[:-4] + "aaaa", path=PREFIX + "/")
    assert auth_client.get(PREFIX + "/", follow_redirects=False).status_code == 303


def test_expired_cookie_is_rejected(auth_client):
    auth_client.cookies.set(web_auth.COOKIE_NAME, _expired_cookie(), path=PREFIX + "/")
    assert auth_client.get(PREFIX + "/", follow_redirects=False).status_code == 303


def test_cookie_signed_with_other_secret_is_rejected(auth_client):
    auth_client.cookies.set(
        web_auth.COOKIE_NAME,
        make_session_token("u", "x", secret="wrong-secret", ttl=3600),
        path=f"{PREFIX}/",
    )
    assert auth_client.get(PREFIX + "/", follow_redirects=False).status_code == 303


# ---------- 白名单 ----------

def test_allowlist_blocks_unknown_user(pb_env, monkeypatch):
    _enable_auth(monkeypatch, allowed="王五")
    monkeypatch.setenv("PB_ORDERS_URL_PREFIX", PREFIX)
    reset_settings()
    app = web_app.create_app()
    with TestClient(app) as c:
        c.cookies.set(web_auth.COOKIE_NAME, _cookie("张三", "user-123"))
        resp = c.get("/")
        assert resp.status_code == 403
        assert "不在允许名单内" in resp.text


def test_allowlist_accepts_listed_user_by_name_or_sub(pb_env, monkeypatch):
    _enable_auth(monkeypatch, allowed="张三,user-999")
    monkeypatch.setenv("PB_ORDERS_URL_PREFIX", PREFIX)
    reset_settings()
    app = web_app.create_app()
    with TestClient(app) as c:
        c.cookies.set(web_auth.COOKIE_NAME, _cookie("张三", "user-123"))
        assert c.get("/").status_code == 200
        # 命中 sub 而非显示名
        c.cookies.set(web_auth.COOKIE_NAME, _cookie("别人", "user-999"))
        assert c.get("/").status_code == 200


# ---------- 登录流程 ----------

def test_login_redirects_to_issuer_with_state(auth_client):
    resp = auth_client.get(f"{PREFIX}/oidc-login?return_to=/pb/jobs/abc", follow_redirects=False)
    assert resp.status_code in (302, 307)  # 跳到外部 IdP，不是闸门
    loc = resp.headers["location"]
    assert loc.startswith(f"{ISSUER}/authorize?")
    assert "state=" in loc and "client_id=pb-orders" in loc


def test_login_state_is_one_shot_and_return_to_survives(auth_client, monkeypatch):
    """state 只能用一次；回调后回到原本想去的页面。"""
    from urllib.parse import parse_qs, urlparse

    login = auth_client.get(f"{PREFIX}/oidc-login?return_to=/pb/jobs/abc", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    seen = {}

    class _Resp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload
            self.text = "ok"

        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None, timeout=None):
            seen["token_url"] = url
            seen["data"] = data
            return _Resp({"access_token": "tok"})

        async def get(self, url, headers=None, timeout=None):
            seen["auth_header"] = (headers or {}).get("Authorization")
            return _Resp({"sub": "user-123", "name": "张三"})

    monkeypatch.setattr(web_auth.httpx, "AsyncClient", lambda *a, **k: _Client())

    cb = auth_client.get(f"{PREFIX}/oidc-callback?code=abc&state={state}", follow_redirects=False)
    assert cb.status_code == 303
    assert cb.headers["location"] == "/pb/jobs/abc"
    assert web_auth.COOKIE_NAME in cb.cookies or web_auth.COOKIE_NAME in auth_client.cookies
    assert seen["token_url"] == f"{ISSUER}/token"
    assert seen["data"]["redirect_uri"] == REDIRECT
    assert seen["auth_header"] == "Bearer tok"

    # 同一个 state 再来一次必须失败
    again = auth_client.get(f"{PREFIX}/oidc-callback?code=abc&state={state}", follow_redirects=False)
    assert again.status_code == 400


def test_callback_rejects_unknown_state(auth_client):
    resp = auth_client.get(f"{PREFIX}/oidc-callback?code=abc&state=forged")
    assert resp.status_code == 400


def test_safe_return_to_stays_inside_the_service():
    """挡三种越界：外站、同域其它服务、空值。"""
    from web.config import Settings

    ctx = web_auth.AuthContext(settings=Settings(url_prefix="/pb"))
    assert web_auth.safe_return_to("//evil.example", ctx) == "/pb/"
    assert web_auth.safe_return_to("https://evil.example", ctx) == "/pb/"
    assert web_auth.safe_return_to("", ctx) == "/pb/"
    # 算上前缀才放行
    assert web_auth.safe_return_to("/pb/jobs/x", ctx) == "/pb/jobs/x"
    assert web_auth.safe_return_to("/pb", ctx) == "/pb"
    # 不带前缀 = 会跳到 api.vilavi.cn 根路径（公司大模型路由），必须挡回本服务
    assert web_auth.safe_return_to("/jobs/x", ctx) == "/pb/"
    assert web_auth.safe_return_to("/sellfox/admin", ctx) == "/pb/"


def test_return_to_falls_back_to_service_root_not_domain_root(auth_client):
    """真 bug 回归：登录前访问 /pb/jobs/xxx，登录后必须回到 /pb/ 下，不能落到域名根。"""
    page = auth_client.get(f"{PREFIX}/jobs/does-not-exist", follow_redirects=False)
    assert page.status_code == 303
    assert "return_to=%2Fpb%2Fjobs%2Fdoes-not-exist" in page.headers["location"]


def test_logout_expires_the_session_cookie(auth_client):
    """退出要下发一个「立刻过期 + 路径正确」的 Set-Cookie。

    断言头部而不是 cookie jar：httpx 的 jar 不按 Path 删除，浏览器会按。
    路径必须是 /pb/，否则删不掉 set_cookie 时用同一路径种下的 cookie。
    """
    _login(auth_client)
    assert auth_client.get(PREFIX + "/").status_code == 200

    resp = auth_client.post(
        f"{PREFIX}/logout", data={"csrf": _csrf(auth_client)}, follow_redirects=False
    )
    # 必须 303：307 会保留 POST，浏览器会拿 POST 去请求只接受 GET 的首页 -> 405
    assert resp.status_code == 303
    header = resp.headers.get("set-cookie", "")
    assert web_auth.COOKIE_NAME in header
    assert "Max-Age=0" in header
    assert f"Path={PREFIX}/" in header


# ---------- 关闭认证时 ----------

def test_auth_disabled_allows_everything(pb_env, monkeypatch):
    monkeypatch.setenv("PB_ORDERS_OIDC_ISSUER", "")
    reset_settings()
    app = web_app.create_app()
    with TestClient(app) as c:
        assert c.get("/").status_code == 200


def test_partial_auth_config_fails_fast(pb_env, monkeypatch):
    """配了 ISSUER 却漏了密钥要立刻报错，而不是静默变成无认证。"""
    monkeypatch.setenv("PB_ORDERS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("PB_ORDERS_SESSION_SECRET", "")
    reset_settings()
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        get_settings()


# ---------- URL 前缀 ----------

def test_all_links_carry_prefix(auth_client):
    _login(auth_client)
    resp = auth_client.get(f"{PREFIX}/jobs/new")
    text = resp.text
    assert 'href="/pb/"' in text
    assert 'action="/pb/jobs/new"' in text
    assert 'href="/pb/static/style.css"' in text
    # 不该再有裸的根绝对路径链接
    assert 'href="/jobs/new"' not in text
    assert 'action="/jobs/new"' not in text


def test_no_prefix_when_unset(client):
    """不配前缀时仍是根绝对路径（本机开发形态）。"""
    text = client.get("/jobs/new").text
    assert 'action="/jobs/new"' in text
    assert "/pb/" not in text


def test_default_no_stock_prefilled(pb_env, monkeypatch):
    monkeypatch.setenv(
        "PB_ORDERS_DEFAULT_NO_STOCK", "CENKZ1324-SkyBlue-97, CENKZ1325-Yellow-97"
    )
    reset_settings()
    app = web_app.create_app()
    with TestClient(app) as c:
        text = c.get("/jobs/new").text
    assert "CENKZ1324-SkyBlue-97,CENKZ1325-Yellow-97" in text


def test_prefix_applies_to_redirects_and_polling(auth_client):
    """带前缀时表单提交的跳转也要带前缀（.pdf/.csv 扩展名合法即入队）。"""
    _login(auth_client)
    resp = auth_client.post(f"{PREFIX}/jobs/new",
        files={
            "packslip": ("p.pdf", open(__file__, "rb").read()[:64], "application/pdf"),
            "order_csv": ("o.csv", b"a", "text/csv"),
        },
        data={"actor": "t", "no_stock": "", "no_stock_note": "",
              "validate_only": "", "allow_unmatched": "", "csrf": _csrf(auth_client)},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith(f"{PREFIX}/jobs/")


def test_logout_does_not_end_in_405(auth_client):
    """真 bug 回归：退出后浏览器会带着 POST 去请求首页 -> `{"detail":"Method Not Allowed"}`。

    `RedirectResponse` 默认是 307，会**保留请求方法**；退出是 POST，
    于是浏览器 POST 到只接受 GET 的 `/`，再被闸门拦下时又 POST 到只接受 GET 的
    `/oidc-login`，最终 405。改 303 后浏览器改用 GET 走完整条链。
    """
    _login(auth_client)
    assert auth_client.get(PREFIX + "/").status_code == 200

    logout = auth_client.post(
        f"{PREFIX}/logout", data={"csrf": _csrf(auth_client)}, follow_redirects=False
    )
    assert logout.status_code == 303, "退出必须是 303，307 会让浏览器继续用 POST"

    # 浏览器按 303 改用 GET 请求 Location，不应再出现 405。
    # （测试环境里 httpx 的 cookie jar 不按 Path 删除，所以这里可能仍是 200 已登录态；
    #   真正钉住原 bug 的是上面那条「必须是 303」。）
    after = auth_client.get(logout.headers["location"], follow_redirects=False)
    assert after.status_code != 405


def test_gate_redirect_is_303_not_307(auth_client):
    """闸门拦截也要用 303，否则 POST 类请求（如「重新处理」）会被原样重放。"""
    resp = auth_client.post(f"{PREFIX}/jobs/job-x/retry", follow_redirects=False)
    assert resp.status_code == 303
