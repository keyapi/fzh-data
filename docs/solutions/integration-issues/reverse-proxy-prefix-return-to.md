---
okf: v0.1
type: Solution
title: 前缀化反向代理下的登录跳转：`return_to` 必须用浏览器可见路径
date: 2026-09-22
category: integration-issues
module: pb_orders
problem_type: integration_issue
component: api-gateway
symptoms:
  - "未登录访问 /pb/ 能正常跳到钉钉登录，扫码也成功，但登录完落到域名根路径"
  - "根路径上是**另一个服务**（公司大模型路由）的界面，不是本服务页面"
  - "服务端日志里的 return_to 是 `/`、`/jobs/xxx`，没有 `/pb` 前缀"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [reverse-proxy, url-prefix, open-redirect, oidc, redirect, nginx]
related_components: [pb_orders, new-api-dingtalk-oidc]
---

# 前缀化反向代理下的登录跳转：`return_to` 必须用浏览器可见路径

## Problem

`pb_orders` 挂在 `https://api.vilavi.cn/pb/` 下，NGINX 用
`proxy_pass http://127.0.0.1:8412/;`（末尾斜杠）把 `/pb` 前缀**剥掉**再转给应用。

未登录用户被认证闸门拦下、跳到钉钉登录，扫码也成功 —— 但登录完成后浏览器落在
`https://api.vilavi.cn/`，也就是域名**根路径**。而根路径挂的是公司的大模型路由
（new-api），不是本服务。使用者看到的是另一个系统的界面，会以为登录错了地方。

## Symptoms

- 未登录访问 `/pb/` → 307 到 `/pb/oidc-login?return_to=%2F`（注意是 `%2F`，没有 `pb`）
- 扫码登录成功，钉钉桥回调正常，会话 cookie 也正常种下
- 最终落在域名根路径，而不是回到 `/pb/`

## What Didn't Work

**直接拿 `request.url.path` 当 `return_to`。** 看起来最自然：拦下请求时"记住想去哪"，
登录后跳回去。但在前缀化部署下，`request.url.path` 是**反代剥掉前缀之后**的
应用侧路径 —— 用户访问 `/pb/jobs/x` 时，应用看到的是 `/jobs/x`。
把它原样回写给浏览器，就等于把用户送到 `/jobs/x`，而那个路径在域名上属于别的服务。

## Solution

闸门构造 `return_to` 时补上前缀（`PB_ORDERS_URL_PREFIX`），让它变成**浏览器可见**的路径：

```python
# pb_orders/web/app.py —— 闸门中间件
user = auth_mod.current_user(request, settings)
if user is None:
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"detail": "登录已失效"}, status_code=401)
    # return_to 必须是浏览器看到的地址（带前缀）。
    # request.url.path 是反代剥掉前缀后的应用侧路径（如 "/"），
    # 直接用它会让登录后跳到域名根路径 —— 而根路径是别的服务。
    return RedirectResponse(
        url(f"/oidc-login?return_to={quote(url(path), safe='')}")
    )
```

同时给 `safe_return_to` 加第二层限制：配了前缀时，只允许跳回**该前缀之下**
（顺带挡住同域名下跳到别的服务）：

```python
# pb_orders/web/auth.py
def safe_return_to(value: str, ctx: AuthContext) -> str:
    root = ctx.url("/")                      # "/pb/" 或 "/"
    raw = (value or "").strip()
    if not raw.startswith("/") or raw.startswith("//"):
        return root                          # 挡 //evil.com 这类开放重定向
    if ctx.prefix and not (raw == ctx.prefix or raw.startswith(f"{ctx.prefix}/")):
        return root                          # 挡跳到同域其它服务
    return raw
```

测试侧补一个和 NGINX 行为一致的 strip-prefix 中间件，否则测不到这个 bug：

```python
# pb_orders/tests/conftest.py
class StripPrefix:
    """模拟 NGINX 的 `proxy_pass .../`：把 `/pb/...` 剥成 `/...` 再交给应用。"""
```

## Why This Works

把「应用侧路径」和「浏览器可见路径」当成两个东西对待。
反代剥离前缀后，应用只能看到前者；**任何回写给浏览器的 URL 都必须是后者**。
前缀是部署参数，应用自己知道（配置里就有），补回去即可。

`safe_return_to` 的前缀校验则顺手关掉一个同域横向跳转的口子：
网关域名上同时挂着多个服务，不做这层限制，构造一个
`return_to=/sellfox/admin` 就能把刚登录的用户送到隔壁系统。

## Prevention

- **前缀化部署时，先列一张「会回写给浏览器的 URL」清单**，逐个确认带了前缀：
  重定向、cookie `path`、模板里的 `href`/`action`、OIDC `redirect_uri`、
  以及任何拼在 query 里的 `return_to`/`next`。
- **测试要模拟反代**，不要直接请求应用侧路径 —— 本项目测试里的
  `StripPrefix` 中间件就是干这个的。用错的路径测，等于把 bug 写进断言
  （这次就是：老测试断言 `location == "/jobs/abc"`，等于把没前缀的行为固化了）。
- **回归用例**：未登录访问一个深层路径，断言 `return_to` 带前缀。
- 本 bug 是**使用者实际登录时发现**的，不是自测发现的 —— 这也说明
  「登录一次」这类人工走查在自动化覆盖不到的地方仍然必要。

## Related Issues

- [dingtalk-oidc-bridge-client-onboarding.md](dingtalk-oidc-bridge-client-onboarding.md)
  —— 自建服务接入公司钉钉 OIDC 桥的完整做法（本 bug 出自这条接入路径）
- [../tooling-decisions/tailscale-relay-vs-public-https-china.md](../tooling-decisions/tailscale-relay-vs-public-https-china.md)
  —— 为什么会走到「挂公网 + 加登录」这条路上
- `pb_orders/docs/reference/server-deployment-architecture.md` 第 11 节 —— 部署与验收记录
