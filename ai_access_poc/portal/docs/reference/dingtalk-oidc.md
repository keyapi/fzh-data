---
okf: v0.1
type: Reference
title: Portal 钉钉 OIDC
tags: [portal, dingtalk, oidc]
timestamp: 2026-07-24
resource: new-api-dingtalk-oidc/
---

# 钉钉 OIDC（Portal）

复用仓库已有 `new-api-dingtalk-oidc/`（与 new-api SSO 同桥）。

## Dry-run（默认）

- `DINGTALK_ENABLED=0` 或不启 profile
- `GET /ops/api/auth/status` → `mode: dry-run`
- `GET /oidc/...` → 503 JSON + 启用提示（OIDC 容器未起时）

## 启用 live

1. 钉钉开放平台创建**第三方企业应用**，拿到 AppKey/AppSecret
2. 回调域指向 Portal：`http://<host>:8088/oidc/callback`（公网需 HTTPS 与真实 ISSUER）
3. `.env`：

```text
DINGTALK_ENABLED=1
DINGTALK_CLIENT_ID=...
DINGTALK_CLIENT_SECRET=...
ALLOWED_CORP_ID=...
OIDC_ISSUER=http://127.0.0.1:8088/oidc
```

4. `docker compose --profile dingtalk up -d --build`
5. 校验：`curl http://127.0.0.1:8088/oidc/.well-known/openid-configuration`

## 与 OWUI / IvyeaOps 登录的关系

本 PoC **只验证网关路径与桥可挂**；未强制 OWUI Trusted Header / oauth2-proxy 全链路登录。后续可把 OIDC 接到 oauth2-proxy 再喂两边应用。
