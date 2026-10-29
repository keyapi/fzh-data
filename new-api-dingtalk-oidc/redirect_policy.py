"""OIDC 回调地址白名单。

单独成模块，是为了能脱离 FastAPI 应用做单测（`main` 导入时会建库、加载私钥）。
"""

from __future__ import annotations

# 值来自 nginx 访问日志里两个真实客户端：
#   new-api 自带登录 → /oauth/dingtalk
#   pb-orders      → /pb/oidc-callback
DEFAULT_ALLOWED_REDIRECT_URIS = (
    "https://api.vilavi.cn/oauth/dingtalk",
    "https://api.vilavi.cn/pb/oidc-callback",
)


def parse_allowed_redirect_uris(raw: str | None) -> list[str]:
    """逗号分隔的 `ALLOWED_REDIRECT_URIS`；未设置时用默认两个真实客户端。"""
    source = DEFAULT_ALLOWED_REDIRECT_URIS if raw is None else raw.split(",")
    return [uri.strip() for uri in source if uri and uri.strip()]


def is_redirect_uri_allowed(redirect_uri: str, allowed: list[str]) -> bool:
    """精确匹配，不做前缀/子串比较——前缀放行会让 evil.com 借域名尾巴混进来。"""
    return bool(redirect_uri) and redirect_uri in allowed
