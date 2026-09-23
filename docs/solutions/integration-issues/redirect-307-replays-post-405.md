---
okf: v0.1
type: Solution
title: 重定向用 307 会让浏览器重放 POST —— 退出登录报 405
date: 2026-09-22
category: integration-issues
module: pb_orders
problem_type: integration_issue
component: api-gateway
symptoms:
  - "点「退出」后页面显示 {\"detail\":\"Method Not Allowed\"}"
  - "地址栏停在 …/oidc-login?return_to=…（登录页的地址）"
  - "未登录时点「重新处理」等 POST 按钮，同样落到 405"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [http-redirect, 303, 307, fastapi, authentication, nginx]
related_components: [pb_orders]
---

# 重定向用 307 会让浏览器重放 POST —— 退出登录报 405

## Problem

`pb_orders` 网页版点右上角「退出」，浏览器返回
`{"detail":"Method Not Allowed"}`。退出这个动作本身成功了（cookie 已失效），
但用户看到的是报错页。

## Symptoms

- 退出后地址栏停在 `/pb/oidc-login?return_to=%2Fpb%2F`，页面内容是 405 JSON
- 服务端日志里能看到一串 POST 请求打到了只声明 GET 的路由上
- 同一类问题也会出现在**未登录**时点任何 POST 按钮（例如「用相同输入重新处理」）

## What Didn't Work

把 405 当权限或路由问题查——检查了路由声明、中间件顺序、NGINX location，
都正常。真正的线索是**日志里那些请求的方法**：它们全是 `POST`，
而浏览器地址栏停在的是一个「跳转后」的 URL。

## Solution

**凡是「跳到另一个页面」的重定向，用 303；不要用默认的 307。**

FastAPI/Starlette 的 `RedirectResponse` 默认状态码是 **307 Temporary Redirect**，
而 307 的语义是**保持原请求方法和请求体**。于是这条链成立了：

```
POST /pb/logout          → 307 →  /pb/
POST /pb/                → 405    （首页只声明了 GET）
```

如果 `/` 上有闸门，链路更长、症状更绕：

```
POST /pb/logout          → 307 →  /pb/
POST /pb/                → 闸门拦下 → 307 → /pb/oidc-login?return_to=...
POST /pb/oidc-login      → 405    （登录路由只声明了 GET）
```

修法是给这几处统一 `status_code=303`（See Other = 「去用 GET 取那个资源」）：

```python
# 退出
resp = RedirectResponse(ctx.url("/"), status_code=303)

# 闸门：未登录时把页面请求送去登录页
return RedirectResponse(
    url(f"/oidc-login?return_to={quote(url(path), safe='')}"),
    status_code=303,   # 303 才会把 POST 变成 GET
)
```

## Why This Works

- **303 See Other** 的规范语义就是「去用 GET 取那个资源」，浏览器必须把方法换成 GET；
- **307 Temporary Redirect** 是 302/301 的「不改变方法」版本，专为「同一资源换个地址、照原样重发」设计——
  用在「登录成功后跳首页」这种场景是错的；
- 307 只有在**原请求本来就是 GET** 时才和 303 表现一致，
  所以 GET 页面上的重定向（例如跳去外部 IdP）用哪个都行，
  但**只要这条路径可能被 POST 触发**，就必须是 303。

## Prevention

- **写「跳页面」的重定向时，默认显式写 303**，不要依赖框架默认值。
  Starlette 默认 307，Django 默认 302，都不是「换方法」语义。
- 自查清单：这条重定向的上游会不会是 POST？—— 表单提交后跳转、退出登录、
  「重新处理」按钮、任何带 `<form method="post">` 的动作。
- 回归用例要断言**状态码本身**，而不只是断言「跳到了对的地址」：

  ```python
  logout = client.post("/pb/logout", follow_redirects=False)
  assert logout.status_code == 303, "退出必须是 303，307 会让浏览器继续用 POST"
  ```

  （只断言 `Location` 的用例抓不到这个 bug——地址是对的，方法错了。）
- 同一功能里「路径前缀」和「状态码语义」是两个独立的坑，都会以「跳到了奇怪的地方」
  的面目出现，见 [reverse-proxy-prefix-return-to.md](reverse-proxy-prefix-return-to.md)。

## Related Issues

- [reverse-proxy-prefix-return-to.md](reverse-proxy-prefix-return-to.md) —— 另一个重定向坑：`return_to` 没带反代前缀，登录后落到域名根路径
- [dingtalk-oidc-bridge-client-onboarding.md](dingtalk-oidc-bridge-client-onboarding.md) —— 这条认证链的接线方式
