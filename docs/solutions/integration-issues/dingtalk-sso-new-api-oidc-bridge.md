---
title: 钉钉 SSO 登录 new-api（OIDC Bridge 桥接方案）
date: 2026-06-26
last_updated: 2026-06-26
category: integration-issues
module: new-api-deployment
problem_type: architecture_pattern
component: authentication
severity: medium
applies_when:
  - 企业内部需要 SSO 单点登录接入 new-api
  - 使用钉钉作为身份源，new-api 作为 AI API 网关
  - OAuth provider 不支持目标系统的认证协议
tags:
  - dingtalk
  - sso
  - oidc
  - oauth
  - new-api
  - auto-provisioning
  - subscription
  - pricing
  - relay
related_components: [new-api-dingtalk-oidc, deployment, subscription]
---

# 钉钉 SSO 登录 new-api（OIDC Bridge 桥接方案）

## Context

公司内部使用 new-api 作为大模型 API 网关。每次新同事入职需要管理员手动创建账号、分配额度，流程繁琐。

目标：
1. 同事通过钉钉扫码/免登直接登录 new-api，自动创建账号
2. 新用户自动分配每日 ¥20 额度，用完即停，次日自动重置
3. 不改动 new-api 源码

## Guidance

### 架构总览

```
浏览器 → api.vilavi.cn (nginx)
           ├─ /          → new-api:3000
           └─ /oidc/*    → OIDC Bridge:8086

OIDC Bridge (FastAPI) → 钉钉 OAuth v2 API
                      → SQLite (会话/授权码/令牌)
                      → RSA 密钥对 (JWT 签名)

Auto-Bind Cron (每分钟)
  → 查询 MySQL (有钉钉绑定但无活跃订阅的用户)
  → INSERT user_subscriptions (Daily-20RMB 套餐)
```

### 关键决策

**1. OIDC Bridge 而非修改 new-api 源码**

理由：new-api 内置"自定义 OAuth"功能（`controller/custom_oauth.go`），支持 OIDC Discovery，可动态注册任意 OIDC provider。只需一个将钉钉 OAuth 翻译为标准 OIDC 的桥接层。

**2. 钉钉第三方企业应用模式**

选择"第三方企业应用"（标准 OAuth2 授权码流程），而非"企业内部应用"（JSAPI 免登）。前者适用于 Web 浏览器独立访问场景。

**3. 套餐配额而非钱包额度**

new-api 的 billing session 默认 `subscription_first`：有活跃套餐时只查套餐额度，不查钱包。因此：
- `QuotaForNewUser = 0`（新用户无钱包额度）
- 自动绑定 Daily-20RMB 套餐（`quota_reset_period = daily`）
- `allow_wallet_overflow = false`（每日用完即停）

**4. 外部 cron 脚本而非内嵌 bridge**

bridge 的 `/userinfo` 返回时 new-api 尚未创建用户（时序异步），无法在 bridge 中直接绑定套餐。改用每分钟 cron 脚本轮询 MySQL 兜底，幂等安全。

### 配额到金额的换算

new-api 使用配额点数（quota points）作为内部计量单位：

```
$1.00 = 500,000 配额
¥1.00 = 68,493 配额
¥20.00 = 1,370,000 配额
```

ModelRatio 将各模型价格差异编码在配额消耗中：
- DeepSeek V4 Flash: ModelRatio=0.068493 → ¥1.00/1M tokens 输入
- DeepSeek V4 Pro: ModelRatio=0.205479 → ¥3.00/1M tokens 输入
- GPT-5.5 (via CLIProxyAPI): ModelRatio=2.5 → $5.00/1M tokens 输入（对应 OpenAI 官方 API 定价）

**无需为每个模型单独设套餐额度**，同一套配额体系对所有模型生效。

### new-api 多订阅行为

`PreConsumeUserSubscription` 使用 **first-fit** 策略：按 `end_time ASC, id ASC` 遍历活跃订阅，第一个有足够剩余配额的被选中。所有扣费集中在单一订阅上，不会分摊。多订阅并存时需注意早期到期的小套餐会优先被消费。

## Why This Matters

1. **不改源码即可集成**：new-api 的 Custom OAuth + OIDC Discovery 是一个被低估的扩展点
2. **订阅系统已是金额计量**：配额点数的 500,000/$1 换算使 ModelRatio 校准后天然支持"每日 ¥X 限额"
3. **多订阅 first-fit 规则**：套餐设计时需注意排序和到期时间的影响
4. **自动配置的业界标准是 JIT Provisioning**：Grafana/Nextcloud/GitLab 均内置，new-api 缺失需外部脚本弥补

## When to Apply

- 需要将任意 OAuth2-only 身份源接入支持 OIDC 的目标系统
- 企业内部 SSO 但目标系统不支持 JIT provisioning
- 需要自动为新用户设置配额/角色/套餐

## Examples

### OIDC Bridge 端点

| 端点 | 用途 |
|------|------|
| `/.well-known/openid-configuration` | OIDC 发现文档 |
| `/authorize` | 发起授权，重定向到钉钉 |
| `/callback` | 钉钉回调，code→用户信息 |
| `/token` | 用授权码换 id_token（new-api 调用）|
| `/userinfo` | 用 access_token 查用户信息（new-api 调用）|
| `/jwks.json` | JWT 签名公钥 |

### Auto-Bind 脚本核心逻辑

```sql
-- 查找需要绑套餐的用户
SELECT u.id FROM users u
INNER JOIN user_oauth_bindings b ON u.id = b.user_id
LEFT JOIN user_subscriptions s ON u.id = s.user_id AND s.status = 'active'
WHERE s.id IS NULL;

-- 绑定 Daily-20RMB
INSERT INTO user_subscriptions
  (user_id, plan_id, amount_total, amount_used,
   start_time, end_time, status, source,
   last_reset_time, next_reset_time, allow_wallet_overflow)
VALUES
  (?, 2, 1370000, 0, NOW, NOW+365d, 'active', 'admin',
   NOW, tomorrow_midnight, 0);
```

### 钉钉后台配置

- 应用类型：第三方企业应用
- 重定向 URL：`https://api.vilavi.cn/oidc/callback`
- 权限：通讯录个人信息读权限 (`Contact.User.Read`)

### new-api 后台配置

- 自定义 OAuth → Discovery URL：`https://api.vilavi.cn/oidc/.well-known/openid-configuration`
- Slug：`dingtalk`
- 字段映射：`UserIdField=sub`, `UsernameField=name`, `DisplayNameField=name`, `EmailField=email`

## Related

- [AGENT_HANDOFF.md (US Proxy)](../../us_openai_api_proxy/AGENT_HANDOFF.md) — CLIProxyAPI 上游渠道
- [AGENT_HANDOFF.md (new-api)](../../new-api-deployment/AGENT_HANDOFF.md) — 订阅套餐和配额文档
- [sync_pricing.py](../../new-api-deployment/sync_pricing.py) — ModelRatio 计算脚本
- [oidc-bridge/main.py](../../new-api-dingtalk-oidc/main.py) — OIDC Bridge 源码
- [auto-bind-subscription.py](../../new-api-deployment/auto-bind-subscription.py) — 自动绑套餐脚本
- [offboarding-check.py](../../new-api-deployment/offboarding-check.py) — 离职兜底检查脚本
- [test-offboarding.py](../../new-api-deployment/test-offboarding.py) — 离职封号测试脚本
- [stream_listener.py](../../new-api-dingtalk-oidc/stream_listener.py) — Stream 事件监听器

---

## 离职自动封号

### 权限配置

在钉钉开发者后台 → 权限管理 → 开通 **成员信息读权限** (`qyapi_get_member`)，即可用 App Token 查询任意用户（含在职/离职状态）。

### 架构

```
钉钉 Stream (WebSocket)
  ├── user_leave_org 事件 → App Token → getbyunionid → v2/user/get
  │     → 查 unionId (user_oauth_bindings) → UPDATE users SET status=2
  │
  └── 兜底: 每日凌晨 3 点 cron → App Token → getbyunionid
        → 查 active 状态 → 不活跃则禁用
```

### App Token 获取

```python
POST https://api.dingtalk.com/v1.0/oauth2/accessToken
{"appKey": "...", "appSecret": "...", "grantType": "client_credentials"}
# 注意: 参数名用 appKey/appSecret，不是 clientId/clientSecret
```

### 用户状态查询

```python
# Step 1: unionId → userId (需要 qyapi_get_member)
POST https://oapi.dingtalk.com/topapi/user/getbyunionid?access_token=TOKEN
{"unionid": "xxx"}
# → {"errcode": 0, "result": {"userid": "014709..."}}

# Step 2: userId → 完整信息 (含 active 状态)
POST https://oapi.dingtalk.com/topapi/v2/user/get?access_token=TOKEN
{"userid": "014709..."}
# → {"result": {"active": true, "name": "张克勇", ...}}
```

### API 调用注意事项

- 新 OAuth2 App Token 只能调 `api.dingtalk.com/v1.0/` 新端点
- `qyapi_get_member` 权限解锁的是 `oapi.dingtalk.com` 旧端点
- 新端点 `GET /v1.0/contact/users/{userId}` 用 App Token 会报权限不足
- 旧端点 `POST /oapi.dingtalk.com/topapi/v2/user/get` 用 App Token 正常工作
- 参数命名: 新端点用 `appKey`/`appSecret`，旧端点 query param 用 `access_token`

### 密码注册封堵

```nginx
# nginx new-api.conf
location = /api/user/register {
    return 403;  # 仅钉钉 OAuth 可注册
}
```

---

## 附：调试日志

### 错误 1：`Form data requires python-multipart`

new-api 的 `GenericOAuthProvider.ExchangeToken()` 发 POST 时用 `Content-Type: application/x-www-form-urlencoded`，FastAPI 需 `Form()` 参数解析 + `python-multipart` 包。

修复：`requirements.txt` 加 `python-multipart`，`/token` 端点参数改为 `Form(default=...)`。

### 错误 2：`object of type 'NoneType' has no len()`

`jwk.JWK.from_pem()` 传了公钥，JWT 签名时需要私钥。修复：改用 `_PRIVATE_KEY_PEM` 构造 JWK。

### 错误 3：`DingTalk user info missing ID`

钉钉返回字段为 `openId`/`unionId`，代码已正确处理。实际错误是 `Contact.User.Read` 权限缺失。

### 错误 4：`user not in allowed corp (got )`

`/v1.0/contact/users/me` 不返回 `corpId`。修复：仅当 API 实际返回 `corpId` 时才校验。

### 错误 5：`管理员关闭了新用户注册`

`options.RegisterEnabled = false`。修复：MySQL 设为 `true` 并重启 new-api。

### 错误 6：OAuth 新用户无默认令牌

`GENERATE_DEFAULT_TOKEN` 仅对密码注册生效。修复：扩展 auto-bind 脚本同时检测无令牌用户并创建默认令牌。

---

## Docker Compose 统一管理

4 个服务全部由 `/opt/new-api/docker-compose.yml` 管理：

```yaml
services:
  new-api:   # API 网关 + GENERATE_DEFAULT_TOKEN
  mysql:     # 数据库
  redis:     # 缓存
  bridge:    # 钉钉 OIDC (image: new-api-dingtalk-oidc:latest)
```

`docker compose up -d` 一键启动，`docker compose ps` 查看状态。服务器重启后 Docker daemon + restart policy 自动恢复全部服务。
