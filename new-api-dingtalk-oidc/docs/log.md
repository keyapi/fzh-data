---
type: log
module: new-api-dingtalk-oidc
date: 2026-06-26
summary: 开发与部署记录
---

# new-api-dingtalk-oidc — 变更日志

## 2026-06-26

- 初始版本 v0.1.0
- 实现 OIDC Discovery (`.well-known/openid-configuration`)
- 实现 `/authorize` → 钉钉 OAuth 授权页重定向
- 实现 `/callback` → 钉钉 code 换 token + 用户信息
- 实现 `/token` → OIDC 授权码换 id_token (JWT RS256)
- 实现 `/userinfo` → access_token 查用户信息
- 实现 `/jwks.json` → JWT 签名公钥
- 实现 `/health` → 健康检查
- 固定 RSA 密钥对持久化 (文件存储)
- SQLite 存储 state/code/token (持久化)
- ALLOWED_CORP_ID 可选校验

### v0.2.0 — 离职自动封号

- 集成 `dingtalk-stream` SDK，Stream 模式监听 `user_leave_org` 事件
- App Token (client_credentials) 驱动，不依赖 per-user refreshToken
- 需要 `qyapi_get_member` 权限，使用旧 API `getbyunionid` + `v2/user/get`
- 新 API 参数命名: `appKey`/`appSecret` (非 `clientId`/`clientSecret`)
- `pymysql` 直连 new-api MySQL 禁用用户
- 移除 refreshToken 存储逻辑 (v0.1 遗留)
- nginx 封堵 `POST /api/user/register` 密码注册

### 新增文件

- `stream_listener.py` — Stream 事件监听器
- `new-api-deployment/offboarding-check.py` — 定时兜底脚本
- `new-api-deployment/test-offboarding.py` — 测试脚本

## 调试问题

| 问题 | 修复 |
|------|------|
| `Form data requires python-multipart` | requirements.txt 加 python-multipart |
| `object of type 'NoneType' has no len()` | JWK 用私钥构造（非公钥）|
| `DingTalk user info missing ID` | 钉钉权限 Contact.User.Read 缺失 |
| `user not in allowed corp (got )` | corpId 为空时跳过校验 |
| 502 Bad Gateway | 容器崩溃（python-multipart 缺失）|
