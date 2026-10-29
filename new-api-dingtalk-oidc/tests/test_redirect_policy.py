#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回调地址白名单的可执行契约。

桥的 `/authorize` 不校验 `redirect_uri` 时，攻击者可以把授权码引到自己的站点，
再用该 code 换 new-api 会话（接管员工账号）。这里固定住三条边界：
默认放行两个真实客户端、环境变量可覆盖、只做精确匹配。

    uv run pytest new-api-dingtalk-oidc/tests -q
"""

from __future__ import annotations

import pathlib
import sys

_MODULE_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from redirect_policy import (  # noqa: E402
    DEFAULT_ALLOWED_REDIRECT_URIS,
    is_redirect_uri_allowed,
    parse_allowed_redirect_uris,
)


def test_defaults_cover_the_two_real_clients():
    allowed = parse_allowed_redirect_uris(None)
    assert allowed == list(DEFAULT_ALLOWED_REDIRECT_URIS)
    assert "https://api.vilavi.cn/oauth/dingtalk" in allowed
    assert "https://api.vilavi.cn/pb/oidc-callback" in allowed


def test_env_override_parsing_trims_and_drops_blanks():
    allowed = parse_allowed_redirect_uris(" https://a.example/cb , ,https://b.example/cb ")
    assert allowed == ["https://a.example/cb", "https://b.example/cb"]


def test_unknown_redirect_is_rejected():
    allowed = parse_allowed_redirect_uris(None)
    assert not is_redirect_uri_allowed("https://evil.example/cb", allowed)


def test_empty_redirect_is_rejected():
    allowed = parse_allowed_redirect_uris(None)
    assert not is_redirect_uri_allowed("", allowed)


def test_matching_is_exact_not_prefix():
    allowed = parse_allowed_redirect_uris(None)
    for candidate in (
        "https://api.vilavi.cn/oauth/dingtalk/",
        "https://api.vilavi.cn/oauth/dingtalk?x=1",
        "http://api.vilavi.cn/oauth/dingtalk",
        "https://api.vilavi.cn/oauth/dingtalk.evil.example",
        "https://evil.example/https://api.vilavi.cn/oauth/dingtalk",
    ):
        assert not is_redirect_uri_allowed(candidate, allowed), candidate
