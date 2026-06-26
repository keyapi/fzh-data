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

## 调试问题

| 问题 | 修复 |
|------|------|
| `Form data requires python-multipart` | requirements.txt 加 python-multipart |
| `object of type 'NoneType' has no len()` | JWK 用私钥构造（非公钥）|
| `DingTalk user info missing ID` | 钉钉权限 Contact.User.Read 缺失 |
| `user not in allowed corp (got )` | corpId 为空时跳过校验 |
| 502 Bad Gateway | 容器崩溃（python-multipart 缺失）|
