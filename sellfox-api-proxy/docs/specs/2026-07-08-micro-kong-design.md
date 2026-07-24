---
okf: v0.1
type: Spec
title: sellfox-api-proxy 设计规格 — Micro Kong 简化版
description: 最终设计：无管线框架、无插件 ABC、无流式、无排队。硬编码函数调用链 + Vue 3 CDN 管理页。
tags: [sellfox, api-proxy, spec, design, micro-kong]
created: 2026-07-08
updated: 2026-07-08
---

# sellfox-api-proxy — Micro Kong 简化版设计规格

## 架构

```
POST /v1/{provider}/{path}  (Bearer sk-xxx)
  │
  ▼
main.py: proxy_route()     ← 硬编码函数调用链，清晰直观
  │
  ├─ key = auth.verify(header)          → 查 SQLite，返回 key_record
  ├─ ratelimit.check(key.id, key.limit) → 超限返回 429
  ├─ token = tokencache.get(provider)   → 命中返回缓存，miss 获取+缓存
  ├─ signed_url = signing.compute(      → HMAC-SHA256 + 注入 query params
  │       provider, path, token)
  └─ resp = httpx.post(signed_url,      → 转发，返回 JSONResponse
          json=body, headers=headers)
```

不做管线调度、不做插件动态加载、不做流式转发、不做请求排队。

## 文件职责

| 文件 | 行数 | 职责 |
|------|:--:|------|
| `main.py` | ~100 | FastAPI app + lifespan + /health + /v1/{provider}/{path} 路由 |
| `config.py` | ~30 | Pydantic BaseSettings, 读环境变量 |
| `db.py` | ~80 | aiosqlite 建表 + api_keys CRUD |
| `auth.py` | ~50 | Key 验证 (SHA-256 + timing-safe) + admin 认证 |
| `rate_limit.py` | ~40 | 内存滑动窗口，per-key + global，超限 429 |
| `token_cache.py` | ~40 | OAuth2 token 内存缓存 + asyncio.Lock + 5min 提前刷新 |
| `signing.py` | ~30 | 赛狐 HMAC-SHA256 签名 (移植 fetch_ad_reports.py:55-69) |
| `admin.py` | ~120 | Key CRUD API + Jinja2 + Vue 3 CDN 页面 |
| `admin/static/app.js` | ~100 | Vue 3 应用 (列表/创建/删除/复制) |

**总计: ~590 行 Python + JS**

## 数据模型

```sql
CREATE TABLE api_keys (
    id              TEXT PRIMARY KEY,        -- uuid4
    key_hash        TEXT NOT NULL UNIQUE,    -- SHA-256(raw_key)
    key_prefix      TEXT NOT NULL,           -- 前 8 字符，显示用
    name            TEXT NOT NULL,           -- 可读名称
    dingtalk_union_id TEXT,                 -- 钉钉用户，管理员创建的为 NULL
    dingtalk_user_name TEXT,               -- 冗余，审计用
    provider        TEXT NOT NULL DEFAULT '*', -- * 或 sellfox/tongtu
    permissions     TEXT NOT NULL DEFAULT '["*"]', -- JSON 数组
    rate_limit_rps  REAL NOT NULL DEFAULT 1.0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      REAL NOT NULL,
    last_used_at    REAL,
    request_count   INTEGER NOT NULL DEFAULT 0
);
```

## Provider 配置 (config.yaml)

```yaml
providers:
  sellfox:
    name: 赛狐 ERP
    upstream: https://openapi.sellfox.com
    auth_type: oauth2_cc             # static_key | oauth2_cc
    signing_type: sellfox_hmac       # none | sellfox_hmac
    oauth:
      token_url: /api/oauth/v2/token.json
      client_id: ${SELLFOX_APP_ID}
      client_secret: ${SELLFOX_APP_SECRET}
    rate_limit:
      global_rps: 1.0
      default_key_rps: 0.5
```

## 管理页面 (Vue 3 CDN SPA)

- 单文件 `admin/templates/admin.html`
- `<script src="unpkg.com/vue@3/dist/vue.global.prod.js">`
- `<script src="/admin/static/app.js">`
- 组件: KeyList / KeyCreateModal (v-if 切换)
- API 调用: fetch() 带 Authorization header
- Key 创建后展示一次 + 一键复制按钮

## Admin 路由认证

双通道：
1. `X-DingTalk-User-Id` 头 (生产，nginx auth_request 注入)
2. `X-Admin-Key` 头 (开发/CI fallback)

## 不做的

- 插件框架/管线调度器（Provider < 5 个时过度抽象）
- 流式代理（赛狐全是 POST JSON → JSON）
- 请求排队（改 429 + Retry-After 让客户端重试）
- 多 Provider 策略模式（加第二个时再抽）
