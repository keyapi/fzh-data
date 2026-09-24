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
| `ALLOWED_CORP_ID` | 推荐 | 钉钉企业 corpId。收到 `corpId` 时比对，不一致就拒绝 |
| `REQUIRE_COMPANY_MEMBER` | 否 | **默认开启**。按组织成员判定，只放本公司钉钉通讯录里的人；出问题可临时设 `0` 关掉（只做校验日志） |
| `BIND_HOST` | 否 | 监听地址，默认 `0.0.0.0` |
| `BIND_PORT` | 否 | 监听端口，默认 `8086` |
| `DB_PATH` | 否 | SQLite 数据库路径，默认 `/data/new-api-dingtalk-oidc.db` |
| `KEY_PATH` | 否 | RSA 私钥路径，默认 `/data/oidc-key.pem` |

## 登录闸门：只放本公司员工

**别只依赖 `ALLOWED_CORP_ID`。** 钉钉的 `scope` 只有 `openid` 和 `openid corpid` 两种取值；
本桥发起的授权只带 `openid`，所以拿不到 `corpId`，`/contact/users/me` 也常常不返回它，
只比 corpId 的校验会被**整段跳过** —— 结果是任何钉钉账号（含别的企业、外部联系人）都能登录。

所以要靠组织成员查询来判定（`REQUIRE_COMPANY_MEMBER`，默认开）：

- 用**本公司应用**凭证调 `topapi/user/getbyunionid` 查登录人的 unionId；
- 查得到 → 本公司员工，放行；返回 `60121/60111`（通讯录里没有这个人）→ 拒绝；
- 网络/权限等异常 → **也拒绝**（判定不了就不放行），页面提示稍后重试。

三态判定集中在 `stream_listener.check_org_membership()`，回归用例在
`tests/test_org_membership.py`（`uv run pytest new-api-dingtalk-oidc/tests -q`）。
被拒绝时返回一个人话页面，不是 JSON。

> 想改成「由钉钉自己限制组织」也可以：授权地址加 `scope=openid corpid` 与 `corpId=<本公司>`，
> `corpId` 会直接在 `userAccessToken` 响应里返回。当前没这么做，是因为它依赖钉钉应用侧
> 的权限开通情况未经验证，而成员查询这条路已经在本仓库的离职检测里跑通了。

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

## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/integration-issues/dingtalk-oidc-bridge-client-onboarding.md` —— 自建服务接入公司钉钉 OIDC 桥（客户端侧做法）
- `docs/solutions/integration-issues/redirect-307-replays-post-405.md` —— 重定向用 307 会让浏览器重放 POST —— 退出登录报 405
- `docs/solutions/integration-issues/reverse-proxy-prefix-return-to.md` —— 前缀化反向代理下的登录跳转：`return_to` 必须用浏览器可见路径
