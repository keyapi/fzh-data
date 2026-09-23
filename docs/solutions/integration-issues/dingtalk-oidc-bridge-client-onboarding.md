---
okf: v0.1
type: Reference
title: 自建服务接入公司钉钉 OIDC 桥（客户端侧做法）
date: 2026-09-22
category: integration-issues
module: pb_orders
problem_type: architecture_pattern
component: authentication
severity: medium
applies_when:
  - "自建的内网/公网 Web 服务需要挂钉钉登录，而不是自己写一套账号体系"
  - "服务要通过 NGINX 以路径前缀形式暴露（如 /pb/）并复用公司统一的登录入口"
  - "要判断该用应用中间件还是 nginx auth_request 做登录闸门"
tags: [dingtalk, oidc, sso, session, redis, reverse-proxy, authentication]
related_components: [new-api-dingtalk-oidc, pb_orders, sellfox_shipping]
---

# 自建服务接入公司钉钉 OIDC 桥（客户端侧做法）

## Context

公司有一台常驻的 OIDC 桥 `new-api-dingtalk-oidc`（容器监听 `127.0.0.1:8086`，
经 NGINX 暴露在 `https://api.vilavi.cn/oidc/`），把钉钉身份包装成标准 OIDC，
最初是为 new-api 的登录做的。

后续自建的服务（sellfox-api-proxy、pb_orders）也想复用同一套登录，而不是各写一套。
[dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md) 讲的是**桥本身**
（自动开户、配额、离职封号）；本篇讲**客户端侧**——一个新服务该怎么接。

## Guidance

### 不用改钉钉后台

桥会把使用方传入的 `redirect_uri` 透传给钉钉，钉钉侧的回调地址固定是
`https://api.vilavi.cn/oidc/callback`。所以新增一个使用方**只需要在服务侧配置**，
不需要动钉钉应用、也不需要动桥。

### 会话：复用签名 cookie，不要自己发明

`sellfox_shipping/auth_oidc.py` 里的 `make_session_token` / `parse_session_token`
是 HMAC-SHA256 签名的无状态 cookie（格式 `ts|identity|display_name|sig[:32]`）。
直接 import 复用，别重写——同一套格式意味着全公司的服务行为一致。

```python
from sellfox_shipping.auth_oidc import make_session_token, parse_session_token
```

无状态的好处是**重启不丢登录**（容器重建后用户不用重新扫码）。

### OIDC `state` 必须存外部存储

上游模块把 `state` 放在**进程内 dict**（`_oidc_states`）。单进程单 worker 能用，
但多 worker 或容器重启后，回调会因为找不到 state 报 `Invalid state`。

pb_orders 自带 Redis，直接把 state 放进去，并设 5 分钟过期；Redis 不可用时
降级为进程内（会打 WARNING，仅适合单进程开发）：

```python
# pb_orders/web/auth.py
class StateStore:
    def put(self, state: str, return_to: str) -> None: ...
    def pop(self, state: str) -> str | None: ...   # 取出即作废，防重放
```

### 闸门写在应用中间件里，不要指望 nginx `auth_request`

桥**没有** `/verify`、`/auth` 这类校验端点，它的 `/userinfo` 只认
`Authorization: Bearer`、不认 cookie。所以 `auth_request` 无处可指。

仓库里现役做法就是在应用里做闸门（`sellfox_shipping/app.py` 的
`oidc_gate` 中间件；`sellfox-api-proxy` 的设计文档也明确写了
"不依赖 nginx auth_request"）。照抄这个模式即可。

闸门要区分两类被拦请求：

- **页面/下载**（浏览器导航）→ 302 去登录，并记住原地址
- **轮询/异步拉取** → 401 JSON。否则登录页的 HTML 会被塞进轮询片段里

### 身份限制：桥已负责「只放本公司员工」（2026-09-23 起）

> ⚠️ **本节的旧结论已作废。** 曾经的情况是：桥的授权请求只带 `scope=openid`，
> 钉钉不回 `corpId`，`ALLOWED_CORP_ID` 的比对写成「返回了才比」——等于从不生效，
> 于是**任何钉钉账号都能登录**，客户端只能自己加白名单兜底。
>
> **2026-09-23 起桥已收口**：登录回调改用**组织成员查询**（`topapi/user/getbyunionid`，
> 用本公司应用凭证），不在本公司通讯录的人返回 `60121` → 拒绝；判定不了也拒绝。
> 已实测：真实员工放行、伪造账号拒绝，并留下日志行
> `登录校验 union_id=… 显示名=… corp_id=(未返回) 公司成员=True`。
> 详见 [dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md) 错误 4。

**所以客户端不需要再加白名单。** 有权限的钉钉账号 = 本公司员工，这正是要的语义。
若某个服务确实需要再窄一层（例如只给某几个人用），再在服务侧加白名单作为**加码**，
而不是把它当成「桥管不了」的替代品。

拿不准时先登录一次，服务端页头 / 桥的日志会显示显示名与判定结果，再决定要不要收窄。

## Why This Works

- 复用桥 ⇒ 不用改钉钉后台、不用维护第二套账号；
- 复用签名 cookie ⇒ 与公司其它服务行为一致，且重启不掉登录；
- state 外置 ⇒ 多 worker / 重启后回调仍能完成；
- 应用层闸门 ⇒ 不依赖桥没有的能力（`/verify`）；
- 身份边界由桥统一收口 ⇒ 每个客户端不必各写一套「谁算公司人」的判断。

## When to Apply

- 新起一个内部 Web 服务，需要登录但不想自建账号体系；
- 服务要挂在网关域名的某个路径前缀下（如 `/pb/`）与其它服务共址；
- 需要判断登录闸门该放 NGINX 还是应用里。

## Examples

一次完整接入（pb_orders）改动面：

| 项 | 值 / 做法 |
|---|---|
| 桥地址 | `https://api.vilavi.cn/oidc`（不用改） |
| `redirect_uri` | `https://api.vilavi.cn/pb/oidc-callback`（**要带前缀**） |
| cookie 名 / 有效期 | `pb_orders_session` / 8h，`path` 限定为 `/pb/` |
| state 存储 | 服务自带的 Redis，key 前缀 `pb-orders:oidc-state:`，TTL 300s |
| 闸门 | FastAPI 中间件；放行 `/healthz`、`/oidc-login`、`/oidc-callback`、`/logout`、`/static/` |
| 登录后去向 | `return_to`，且只允许落在 `/pb/` 之下 |

⚠️ 前缀化部署时，**回写给浏览器的 URL 都要带前缀**（`redirect_uri`、`return_to`、
cookie `path`）。这一条踩过坑，见
[reverse-proxy-prefix-return-to.md](reverse-proxy-prefix-return-to.md)。

## Related Issues

- [dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md) —— 桥本身的方案与运维
- [reverse-proxy-prefix-return-to.md](reverse-proxy-prefix-return-to.md) —— 前缀化部署下登录跳转踩的坑
- [dingtalk-offboarding-hardening.md](dingtalk-offboarding-hardening.md) —— 离职人员的访问收口
