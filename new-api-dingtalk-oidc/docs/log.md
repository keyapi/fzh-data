---
type: log
module: new-api-dingtalk-oidc
date: 2026-06-26
summary: 开发与部署记录
---

# new-api-dingtalk-oidc — 变更日志

## 2026-09-22

### v0.4.0 — 登录闸门只放本公司员工（收口「任何钉钉账号都能登录」）

- **问题**：授权请求只带 `scope=openid`，钉钉不回 `corpId`，`/contact/users/me` 也常常不返回它，
  于是 `ALLOWED_CORP_ID` 的校验被整段跳过 —— **任何钉钉账号（别的企业、外部联系人）都能登录**，
  而下游（new-api、sellfox-proxy、pb_orders）都以为这道闸门在生效。
- **改法**：不再依赖 `corpId` 字段，改用**组织成员查询**做权威判据 ——
  用本公司应用凭证调 `topapi/user/getbyunionid`，查得到=本公司员工，`60121/60111`=通讯录没这个人。
- **新增** `stream_listener.check_org_membership()`：三态返回（在/不在/判定不了），
  与既有 `get_user_id_by_union_id` 的区别是**不把接口抖动压成「不在公司」**。
- **新增** `REQUIRE_COMPANY_MEMBER`（**默认开启**，设 `0` 可临时关掉只记日志）；
  `corpId` 若返回则继续比对。被拒绝返回人话 HTML 页面，不是 JSON。
- **单测** `tests/test_org_membership.py`：60121→不在 / errcode 0→在 / 其它 errcode 与网络错→判定不了 /
  errcode 0 却没有 userid→判定不了（共 7 例）。
- **部署方式**同 v0.3.1：拷 `main.py` + `stream_listener.py` 到 `/opt/new-api-dingtalk-oidc/` →
  `docker build -t new-api-dingtalk-oidc:latest .` → `cd /opt/new-api && docker compose up -d --no-deps bridge`。
  改前备份两个 `.py`；compose 未改（`REQUIRE_COMPANY_MEMBER` 有默认值）。

## 2026-09-08

### v0.3.1 — 加固版已部署生产（实测）

- **已部署**：`stream_listener.py` + `main.py` 新版拷入 `/opt/new-api-dingtalk-oidc/` →
  `docker build -t new-api-dingtalk-oidc:latest .` → `cd /opt/new-api && docker compose up -d --no-deps bridge`。
- **⚠️ 部署前提**：bridge 容器默认看不到 proxy DB。必须给 bridge 服务挂 proxy DB volume
  （`- /data/sellfox-proxy:/data/sellfox-proxy`）+ 设 `PROXY_DB_PATH=/data/sellfox-proxy/sellfox-proxy.db`，
  否则容器内 `disable_proxy_keys` 找不到 sqlite 抛 `ProxyDisableError` → `STATUS_LATER` 无限重投。
  compose 改前备份 `/opt/new-api/docker-compose.yml.bak-<ts>`。
- **实测**：stream 连上 `wss-open-connection-union.dingtalk.com`，bridge health `{"status":"ok"}`；
  容器内对临时测试 key 调 `disable_proxy_keys` 真实置 `is_active=0`（返回 1），测试 key 已清理，
  真实在职 key 不受影响。旧文件备份 `stream_listener.py.bak-<ts>` / `main.py.bak-<ts>`。

### v0.3.0 — 离职自动封号加固（检测盲区修复）

- 修复：真实离职（员工从组织移出 → `getbyunionid` 60121）原逻辑会 [SKIP] 永不封号；
  改用 60121 判 DEPARTED（瞬时错误仍 RETRY，不误封）
- 新增本地 `dingtalk_identity_map`(unionId↔userId)：`user_leave_org` 事件优先查本地映射，
  员工已被移除也能定位账号；登录回调/每日跑批/事件命中三处回填
- `user_leave_org` 事件处理不再依赖离职后实时反查 userId→unionId
- proxy key 禁用失败抛异常 → `STATUS_LATER` 重投，不静默吞错（new-api 封号先无条件执行）
- 新增 `offboarding_audit` 审计表（心跳 + 明细），幂等建表
- 单测：`tests/new_api_offboarding/`（60121→封 / 瞬时错→不封 / 本地映射命中仍封 / proxy 不可达重投）
- 详：`docs/solutions/integration-issues/dingtalk-offboarding-hardening.md`

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
| `user not in allowed corp (got )` | 当时改成「corpId 为空就跳过校验」——**这个判断是错的**，见 2026-09-22 v0.4.0：根因是没申请 corpid，跳过等于不校验 |
| 502 Bad Gateway | 容器崩溃（python-multipart 缺失）|
