---
okf: v0.1
type: Reference
title: new-api 公网端口暴露导致陌生账号密码注册
date: 2026-10-29
last_updated: 2026-10-29
category: integration-issues
module: new-api-deployment
problem_type: security_exposure
component: authentication
severity: high
applies_when:
  - new-api / one-api 等自建 AI 网关出现不认识的用户
  - 需要判断"注册开关到底由哪一层控制"
  - 讨论容器端口该不该暴露到公网
tags:
  - new-api
  - security
  - registration
  - docker-port
  - nginx
---

# new-api 公网端口暴露导致陌生账号密码注册

## 现象

2026-10-29 在 new-api 用户表发现 5 个非公司账号（ID 26-30）：
`RogerMitchel` / `JoshuaRamos2` / `EthanJohnson700` / `oa6d60e4433b` / `oa5f38f98546`。

共同特征：**无 email、无 oidc_id、无 github_id**，即不是钉钉 SSO 建号，而是账号密码注册。
nginx 配置里明明有 `location = /api/user/register { return 403; }`。

## 根因

`/opt/new-api/docker-compose.yml` 把容器映射为 `'3000:3000'`，`ss -lntp` 实际监听
`0.0.0.0:3000`（ufw inactive，只有 fail2ban 守 22/80/443）。公网可直接访问网关端口，
**完全绕过 nginx**。证据：两个来源 IP 在 nginx 全部访问日志中 0 条记录，而
`docker logs new-api` 里有它们的 `POST /api/user/register 200`。

同时 `options` 表没有 `PasswordRegisterEnabled` 键，取源码默认值 `true`，应用层没有兜底。

## 时间线与行为

| 时间(北京) | 用户 | 来源 IP | 行为 |
|-----------|------|---------|------|
| 2026-09-25 起 | — | 8.219.150.152（阿里云·新加坡） | 持续扫描 `/api/status`、`/api/setup`、`/api/verification?email=melaneyesyes+<随机>@gmail.com` |
| 2026-10-09 20:31 | 26 RogerMitchel | 8.219.150.152 | 注册→登录→签到→自建第 2 个令牌 `rt-1791577868` |
| 2026-10-09 23:02 | 27 JoshuaRamos2 | 8.219.150.152 | 仅注册，从未登录 |
| 2026-10-25 00:38 | 28 EthanJohnson700 | 8.219.150.152 | 注册→登录 2 次→签到 |
| 2026-10-27 20:23 | 29 oa6d60e4433b | 131.108.17.226（纽约 Udasha/VPN） | 注册→登录→读自己令牌 key→3 次 `chat/completions` 全 403 |
| 2026-10-27 21:19 | 30 oa5f38f98546 | 131.108.17.226 | 同上 |

**实际消耗为 0**：`users.quota/used_quota/request_count` 全 0，6 个令牌 `used_quota` 全 0，
`logs` 表只有 6 条"密码登录成功"，无模型调用；3 次 `chat/completions` 被
`用户额度不足, 剩余额度: $0.000000` 挡下（HTTP 403）。无订阅、无订单、无充值。

## 一个容易误判的点

`docker logs` 里 `GET /api/option/`、`GET /api/channel/?p=0&size=100` 显示 **200**，
看起来像泄露了配置和渠道密钥。实际是本版本的鉴权约定：`middleware/auth.go` 在
token 无效 / 权限不足 / 用户被封时会返回 **HTTP 200 + `success:false`**。
判断是否真成功要看响应体，不能只看状态码。

## 修复（2026-10-29 已上线）

1. **关闭密码注册**（应用层）：
   ```sql
   INSERT INTO options (`key`, value) VALUES ('PasswordRegisterEnabled','false')
   ON DUPLICATE KEY UPDATE value='false';
   ```
   ⚠️ **不要**关 `RegisterEnabled` —— OIDC 自动建号（`controller/oauth.go`）也会检查它，
   关掉会导致新员工首次钉钉登录失败。两者的分工：
   - `RegisterEnabled`：是否允许**创建新账号**（密码注册 + 第三方登录建号）
   - `PasswordRegisterEnabled`：是否允许**账号密码注册**（只影响密码路径）
   - `options` 表直写后需重启容器才生效（OptionMap 常驻内存）。

2. **收回端口**：compose 改为 `'127.0.0.1:3000:3000'`，`docker compose up -d new-api`。
   nginx 的 `proxy_pass http://127.0.0.1:3000` 不受影响。

3. **nginx 加厚**：`location = /api/user/register` → `location ~* ^/api/user/register`，
   覆盖尾斜杠与大小写变体（实测 `register/`、`REGISTER` 均 403）。

4. **清理**：用户 26-30 `status=2`，其令牌 `status=2`，先观察再删除。

## 第二轮：交叉审核补的两处（同日）

首轮修复后与 Codex 做了独立交叉审核，逐条验证后只采纳成立的部分：

### 1) OIDC 桥 `redirect_uri` 未校验（真实漏洞，已修）

- `/authorize` 接受任意 `redirect_uri`，`/token` 不校验客户端。
- 攻击链：攻击者先在自己浏览器取合法 `state` → 发链接
  `/oidc/authorize?client_id=123456&redirect_uri=https://evil&state=<攻击者的>` → 员工完成钉钉授权
  → 授权码送到攻击者站点 → 攻击者用该 code 换 new-api 会话，**以员工身份登录**。
- 为什么 new-api 的 state 校验挡不住：`state` 存在**攻击者自己**的会话里（`GenerateOAuthCode`），
  所以攻击者用同一个浏览器兑换即可通过校验。
- 修法：`redirect_uri` 精确白名单（`redirect_policy.py` + `ALLOWED_REDIRECT_URIS`），
  默认值取自 nginx 日志里两个真实客户端：`/oauth/dingtalk` 与 `/pb/oidc-callback`。
  实测合法地址 307、`https://evil.example/cb` 与 `dingtalk.evil.example` 均 400。

### 2) `SESSION_SECRET` 是弱口令（已轮换）

生产 compose 里原值是 `new-api-session-secret-shanghai` 这类可猜字面量。gin 用它给 cookie 会话做 HMAC，
猜到即可伪造 `role=100` 的会话。已换成 32 字节随机值。
**轮换只失效浏览器登录态，API 令牌（`tokens.key` 存库的随机串）不受影响** —— 这也是为什么可以放心轮换。

### 3) 审核中判断为"不成立/暂不处理"的项

| 说法 | 核实结论 |
|------|---------|
| OIDC 仍能自动建号 = 漏洞 | 设计如此。桥用 `getbyunionid` 60121 挡非公司成员；new-api 按 `sub=unionId` 匹配、不按 email 合并 |
| `REQUIRE_COMPANY_MEMBER=0` 可绕过 | 理论成立；实测 env 未设 → 默认开启 |
| `auto-bind-subscription` 未按 provider 过滤 | 属实；当前只有一个 provider，暂无利用面，新渠道上线前需补 |
| `/api/user/reset*` 可被滥用 | 该版本没有密码重置路由 |
| 旧会话未撤销 | 已通过轮换 `SESSION_SECRET` 一并解决；令牌在更早已全部禁用 |

### 4) 顺带发现（未处理）

主机上 `mariadbd`(3306)、frappe socketio(9000) 监听 `0.0.0.0`；外部三地探测均超时（云安全组挡住），
MariaDB 用户全为 `@localhost`。属纵深不足，建议改绑回环。

## 验收命令

```bash
# 应用层已关（直连也注册不了）
curl -s -X POST http://127.0.0.1:3000/api/user/register -d '{}'
# → {"message":"Password registration has been disabled ...","success":false}

# nginx 层封堵
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://api.vilavi.cn/api/user/register   # 403
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://api.vilavi.cn/api/user/register/  # 403

# 端口不再公网监听
ss -lntp | grep 3000        # 只有 127.0.0.1:3000
```

## 预防

- 自建网关的容器端口一律绑回环，对外只经 nginx；`ss -lntp` 里出现 `0.0.0.0:<业务端口>` 就要警觉。
- 注册类开关必须应用层关，nginx 只做纵深防御 —— 端口一旦多开一条路，nginx 规则就不算数。
- 新增自建服务时，把"公网监听面"写进该模块的 AGENT_HANDOFF 验收清单。
