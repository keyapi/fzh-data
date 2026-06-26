# new-api-dingtalk-oidc

将钉钉 OAuth 包装为标准 OpenID Connect 协议，使 new-api 的自定义 OAuth 功能可以直接接入钉钉登录。

## 工作原理

```
浏览器 → new-api (Custom OAuth) → new-api-dingtalk-oidc → 钉钉 OAuth API
```

new-api-dingtalk-oidc 暴露标准 OIDC 端点（discovery / authorize / token / userinfo / jwks），
内部对接钉钉第三方企业应用的 OAuth2 授权码流程。

## 前置条件

1. 在 [钉钉开放平台](https://open.dingtalk.com) 创建**第三方企业应用**
2. 获取 AppKey（即 client_id）和 AppSecret（即 client_secret）
3. 配置回调域名为 new-api-dingtalk-oidc 的地址（例如 `https://your-domain.com/oidc`）
4. 授权通讯录权限（`contact/users/me` 读权限）

## 快速启动

### 1. 构建镜像

```bash
cd new-api-dingtalk-oidc
docker build -t new-api-dingtalk-oidc .
```

### 2. 运行

```bash
docker run -d \
  --name new-api-dingtalk-oidc \
  -p 8086:8086 \
  -v new-api-dingtalk-oidc-data:/data \
  -e ISSUER=https://your-domain.com/oidc \
  -e DINGTALK_CLIENT_ID=your_app_key \
  -e DINGTALK_CLIENT_SECRET=your_app_secret \
  -e ALLOWED_CORP_ID=your_corp_id \
  new-api-dingtalk-oidc
```

### 3. 验证

```bash
curl http://localhost:8086/.well-known/openid-configuration
# 应返回完整的 OIDC discovery 文档
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `ISSUER` | 是 | new-api-dingtalk-oidc 的公网 URL（例如 `https://api.your-company.com/oidc`）|
| `DINGTALK_CLIENT_ID` | 是 | 钉钉应用 AppKey |
| `DINGTALK_CLIENT_SECRET` | 是 | 钉钉应用 AppSecret |
| `ALLOWED_CORP_ID` | 推荐 | 限制只能本公司员工登录（钉钉企业 corpId）|
| `BIND_HOST` | 否 | 监听地址，默认 `0.0.0.0` |
| `BIND_PORT` | 否 | 监听端口，默认 `8086` |
| `DB_PATH` | 否 | SQLite 数据库路径，默认 `/data/new-api-dingtalk-oidc.db` |
| `KEY_PATH` | 否 | RSA 私钥路径，默认 `/data/oidc-key.pem` |

## 在 new-api 中配置

1. 登录 new-api 管理后台
2. 设置 → 自定义 OAuth → 添加提供商
3. 填入 new-api-dingtalk-oidc 的 discovery URL：`https://your-domain.com/oidc/.well-known/openid-configuration`
4. 点击"自动填充"，系统会自动读取端点配置
5. 填入 client_id 和 client_secret（任意值即可，本桥接不校验）
6. 保存并启用

用户即可在 new-api 登录页看到"钉钉登录"按钮。

## 数据持久化

- `/data/new-api-dingtalk-oidc.db` — SQLite，存储授权码和 token 会话
- `/data/oidc-key.pem` — RSA 私钥，首次启动自动生成，保持不变

## 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/.well-known/openid-configuration` | GET | OIDC Discovery |
| `/jwks.json` | GET | 签名公钥 |
| `/authorize` | GET | 发起授权（重定向到钉钉）|
| `/callback` | GET | 钉钉回调（内部使用）|
| `/token` | POST | 授权码换 id_token |
| `/userinfo` | GET | 用户信息 |
| `/health` | GET | 健康检查 |
