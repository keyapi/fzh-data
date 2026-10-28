---
okf: v0.1
type: HowTo
title: 同事自助 key 门户
description: 独立 /portal 钉钉登录、一人一枚只读 key 的准入、生命周期与启用步骤
tags: [wayfair, portal, oidc, api-key, self-service]
---

# 同事自助 key 门户

Codex 评审结论：**A 方案**——独立准入白名单，自助只能领取
`inventory:snapshot:read`，账号固定为 `portal_account`（默认 centrade）；
`inventory:live:read` / `inventory:transactions:read` 仍由管理员按需授予。

## 行为

- 钉钉 OIDC 登录（独立 `/portal` 会话，不复用 admin 会话）
- 只有 `oidc.portal_identities` 中的 `sub` 能进入
- 一人只有一枚 active portal key；重建会立即停用旧 key
- 明文 key 只显示一次，响应 `Cache-Control: no-store`；数据库只存哈希
- 每 60 秒最多重建一次，每天最多 3 次（可配置）
- 停用只影响 `source=portal` 的 key；EN/管理员发的 key 不受影响
- 公网 `/admin` 继续 404；管理仍走 Tailscale/SSH

## 端点

| 方法与路径 | 说明 |
|------------|------|
| `GET /portal/` | 门户页（未登录显示登录入口） |
| `GET /portal/oidc-login` | 跳转 OIDC issuer |
| `GET /portal/oidc-callback` | 校验 state、写入 HttpOnly 会话 |
| `POST /portal/key/issue` | 领取/重建 key（CSRF + 同源校验） |
| `POST /portal/key/deactivate` | 停用本人 portal key |
| `GET /portal/api/key` | 当前 key 元数据（无明文） |
| `POST /portal/logout` | 退出 |

## 启用条件

1. `config.yaml` 配置 `oidc`：issuer、client_id、client_secret、`portal_redirect_uri`
   （例如 `https://wayfair-api.vilavi.cn/portal/oidc-callback`）。
2. OIDC issuer 必须接受该回调地址。当前公司钉钉 OIDC 桥会保存任意 redirect_uri，
   但仍建议在桥侧确认。
3. `/etc/wayfair-api-proxy/env` 设置 `WAYFAIR_PORTAL_SESSION_SECRET`
   （`openssl rand -hex 32`，独立于 admin）。
4. `oidc.portal_identities` 填入允许的钉钉 `sub`；留空则无人可进。
5. Nginx 公网放行 `/portal/`（当前 `location /` 已覆盖）；`/admin` 保持 404。

首次启用时白名单为空：本人登录后会收到 403，错误信息里带自己的 `sub`，
交给管理员加入 `portal_identities` 并重启即可。

## 安全边界

- OIDC state 与 HttpOnly cookie 绑定；会话 cookie `Secure` + `SameSite=Lax`
- 写操作要求 CSRF double-submit + Origin/Sec-Fetch-Site 校验
- 不提供账号/operation 选择，避免自助扩大权限
- live/transactions 不走门户；需要时由管理员发独立 key

## 测试

`uv run pytest wayfair-api-proxy/tests/test_portal.py` 覆盖：

- 未配置 secret 时路由不存在
- 非白名单 403
- 领取 → 重建（旧 key 失效）→ 停用
- 缺 CSRF、跨源 POST 被拒
- portal 停用不影响 manual key
