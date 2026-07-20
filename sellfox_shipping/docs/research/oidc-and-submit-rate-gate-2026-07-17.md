---
okf: v0.1
type: Research
title: 钉钉 OIDC 与 submit 多实例限流（2026-07-17）
description: 复用公司 OIDC 桥的可选认证脚手架；SQLite 跨进程 submit 限流；与 Karrio/PR 编号澄清及蜴国际同事测试并行说明
timestamp: 2026-07-17
tags: [sellfox-shipping, oidc, rate-limit, karrio]
---

# 钉钉 OIDC 与 submit 多实例限流

## Karrio 判断（重读 PR#88 + 早期调研后）

- **PR#88** = 本仓综合调研（含 Karrio §7）；**不是** vite-api。vite 文档在 **#87/#89**。
- 早期 comprehensive + solutions 文：借鉴 Karrio **风格**（Proxy/Mapper），不等于引入 Karrio Server 或为 VITE 写 custom connector。
- 与 [vite-httpx-vs-karrio-decision-2026-07-17.md](vite-httpx-vs-karrio-decision-2026-07-17.md) **一致**：VITE 用 httpx；Server 不用；FedEx 将来优先官方 connector。

## submit 多实例

- 进程内 `SubmitRateLimiter` 不够（Web + CLI / 多 worker）。
- 新增 `SqliteSubmitRateLimiter` + 表 `shipping_submit_rate_gate`（Alembic `0007`）。
- CLI 真调路径默认走 SQLite gate；间隔仍读 `submit_min_interval_seconds`。
- **仍依赖**代理侧限速；本 gate 只保证本库多进程不互相踩官方/代理配额。

## 钉钉 OIDC

- 复用 `https://api.vilavi.cn/oidc`（`new-api-dingtalk-oidc`），模式对齐 `sellfox-api-proxy`。
- `auth.enabled: false` 默认；本地开发不挡。
- 打开：`auth.enabled: true`（或 `SELLFOX_SHIPPING_AUTH_ENABLED=true`）+ `SELLFOX_SHIPPING_SESSION_SECRET` + `OIDC_CLIENT_SECRET`，并在钉钉/OIDC 桥登记 `redirect_uri`。
- **启用校验：** 缺 issuer/client/secret/redirect/session_secret 时进程启动失败（不静默放行）。
- **HTTPS cookie：** `redirect_uri` 为 `https://` 时 session cookie 带 `Secure`。
- **审计：** 写操作 actor 优先钉钉 `sub`（`resolve_actor`），表单 `web-user` 仅本地关闭认证时使用。
- 路由：`/oidc-login`、`/oidc-callback`、`/logout`；中间件保护其余路径（`/api/health` 放行）；API 未登录返回 JSON 401。

## 蜴国际（同事并行）

PR **#91** 已合入 main：负余额下 **createOrder / getLabel / cancelOrder** 冒烟通过。详见 [lizard-api-vs-excel-2026-07-17.md](lizard-api-vs-excel-2026-07-17.md)。Excel 仍为生产默认，直至本仓 adapter 受控验证。
