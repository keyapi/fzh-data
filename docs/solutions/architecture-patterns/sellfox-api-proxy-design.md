---
module: sellfox-api-proxy
date: 2026-07-09
problem_type: architecture_pattern
component: tooling
severity: medium
tags: [api-gateway, proxy, multi-tenant, oidc, dingtalk, sellfox, key-management, offboarding, smoke-testing, agent-skill]
---

# API 代理网关设计、演进与运维

## Context

赛狐 OpenAPI 要求 IP 白名单 + 最多 5 个 API 账号。团队需要多同事共用一套凭证，同时解决凭证安全分发、权限控制和离职自动封号。

自建轻量 Python 代理网关，部署在固定 IP 的 VPS (82.156.238.248) 上。借鉴 Kong 的插件阶段模型和声明式配置思想，但不照搬其臃肿的 Lua 实现。

当前版本 v0.4.3，代码约 1,500 行 (Python + JS + HTML)，已通过 9 条冒烟测试。

## Guidance

### 架构原则

**不要为 2-3 个 Provider 建插件框架。** 硬编码调用链 (`key_auth → rate_limit → token_cache → signing → httpx`)，等 Provider 到 5+ 再抽象。当前 1 个 Provider (赛狐)，4 个阶段 5 步，清晰直观。

**借鉴 Kong 的阶段模型，不照搬 Kong。** Kong 15 万行 Lua、需 PostgreSQL 或受限的 DB-less 模式。取其设计思想（按阶段分组、声明式配置），用 Python/FastAPI 实现 ~500 行核心代码。

**双层存储**：静态配置 (accounts, rate limits) 放 YAML (`config.yaml`)，动态数据 (API keys) 放 SQLite。YAML 管"一年改不了几次"的配置，SQLite 管"每天都要改"的数据。避免 Kong DB-less "改 Key 要 reload"的痛点。

**自包含 OIDC 验证**：不依赖 nginx auth_request。proxy 自己完成 OIDC code 交换和 session 签发。

### 请求管线

```
客户端 (Bearer sk-xxx, 任意 IP)
  → Nginx (api.vilavi.cn/sellfox/)
    → sellfox-api-proxy :8400
      ├─ Key 验证 (SHA-256 hash → SQLite lookup)
      ├─ 限流 (per-key + per-account global, 滑动窗口)
      ├─ OAuth2 Token (缓存 + single-flight refresh, 提前 5min)
      ├─ HMAC-SHA256 签名 (access_token + client_id + nonce + timestamp + sign)
      └─ httpx 转发 → 赛狐上游 (openapi.sellfox.com)
```

### 安全模型

| 层面 | 机制 |
|------|------|
| 身份认证 | 钉钉 OIDC 登录 (复用已有 new-api-dingtalk-oidc 桥) |
| Key 管理 | Admin Key (管理员) + 钉钉用户自助创建 |
| Key 存储 | XOR + SHA-256 加密 (纯 Python 零依赖)，`POST /api/keys/{id}/reveal` 随时复制 |
| 离职封号 | 双通道 — 每日 cron (offboarding-check.py) + 实时 Stream (stream_listener.py) |
| 角色隔离 | Admin 看全部 Key，钉钉用户只看自己的 Key |
| 权限控制 | Key 绑定 Account (当前 sellfox-main)，可扩展到多 Account |

### 部署架构

```
VPS (82.156.238.248)
├── Nginx :443
│   ├── /sellfox/admin → proxy :8400/admin
│   └── /sellfox/      → proxy :8400/
├── sellfox-api-proxy (Docker, :8400)
│   └── SQLite: /data/sellfox-proxy/sellfox-proxy.db
└── new-api + oidc-bridge (Docker Compose)
    └── .secrets.env (ADMIN_API_KEY, SELLFOX 凭证)
```

### v0.4.3 新增

**离职封号集成**：`offboarding-check.py` (每日 cron) 和 `stream_listener.py` (实时 Stream) 在封禁 new-api 账号后同步禁用 proxy keys。按 `dingtalk_union_id` 匹配。SQLite 直连，无额外依赖。PROXY_DB_PATH 环境变量可配置。

**冒烟测试**：`smoke_test.py` (290 行，纯 stdlib urllib)，9 条用例覆盖 health / admin login / create key / reveal key / proxy API / concurrent rate limit / invalid key / toggle disable / delete key。支持 `--local` (localhost:8400) 和远程 (api.vilavi.cn) 双模式。测试结果：本地 9/9，远程 8/8。

**OIDC 刷新修复**：OIDC 回调后浏览器 URL 残留 `?code=...&state=...`，刷新时重新提交已消费的 state → "Invalid state"。修复：回调返回 JS 重定向页面 (`window.location.replace("/sellfox/admin")`) 而非直接返回 admin.html。同样修复了 dev-login。

**Agent Skill**：`.agents/skills/sellfox-api/SKILL.md` (374 行)，Agent 自动发现。包含：用户身份路由 (运营 vs 开发)、代理 API curl 模板、3 个可复用 Python 脚本 (列店铺、拉报告、通用模板)、直接 API 签名参考、419 个 API 文档索引。

## Why This Matters

完整经验教训见 `sellfox-api-proxy/docs/lessons/2026-07-09-full-architecture-evolution.md` (17 条)。

核心教训：
- **nginx 后面的相对 URL 是噩梦**：必须 `<base href>` + 相对路径 + cookie `path="/"`
- **OIDC 回调不能直接返回 HTML**：URL 残留导致刷新失败，必须 JS redirect 到干净 URL
- **Key 加密上线后旧 Key 不可恢复**：migration 添加列时 DEFAULT '' 导致旧 key 空值，需删除重建
- **冒烟测试救了部署**：每次修改后跑测试，本地 + 远程双模式验证

## When to Apply

- 需要给多个同事安全分发第三方 API 凭证
- 上游 API 有 IP 白名单限制 + 自定义签名算法 (HMAC-SHA256 等)
- 团队已有 OIDC/SSO 登录基础设施，需要复用身份体系
- 需要离职自动封号 (cron + 实时双通道)
- 需要为 Agent (AI 助手) 构建可自动发现的 API 访问文档

## Examples

### 运营同事获取 API Key (Agent 引导)
```
1. 打开 https://api.vilavi.cn/sellfox/admin
2. 点击「钉钉登录」→ 扫码
3. 首次登录自动创建 Key，点击「复制」得到 sk-xxx
4. Agent 用 Key 调用代理 API
```

### 通过代理调用赛狐 API
```bash
curl -X POST https://api.vilavi.cn/sellfox/v1/sellfox-main/api/shop/pageList.json \
  -H "Authorization: Bearer $SAIFU_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pageSize":20,"pageNum":1}'
```

### 运行冒烟测试
```bash
# VPS 本地模式
cd /opt/sellfox-api-proxy
ADMIN_API_KEY=xxx python3 smoke_test.py --local

# 远程模式
ADMIN_API_KEY=xxx python3 smoke_test.py
```

## Related

- `sellfox-api-proxy/AGENT_HANDOFF.md` — Agent 接手文档
- `sellfox-api-proxy/docs/lessons/2026-07-09-full-architecture-evolution.md` — 17 条完整经验教训
- `sellfox-api-proxy/docs/research/` — 5 篇调研文档 (方案对比、Kong 分析等)
- `.agents/skills/sellfox-api/SKILL.md` — Agent 自动发现 Skill
- `SELLFOX_API/` — 419 个 API 端点文档 + 3 个报告脚本
- `docs/solutions/integration-issues/dingtalk-sso-new-api-oidc-bridge.md` — 钉钉 OIDC 桥方案
