---
okf: v0.1
type: Reference
title: OIDC 回调白名单漏项导致赛狐 API 代理钉钉登录全 400
date: 2026-11-17
last_updated: 2026-11-17
category: integration-issues
module: new-api-deployment
problem_type: auth_regression
component: authentication
severity: high
applies_when:
  - 同事反馈打开 api.vilavi.cn 下某个子应用点「钉钉登录」报「登录回调地址不合法」
  - 新增了一个走公司 OIDC 桥的客户端，验证登录是否可用
  - OIDC 桥 /authorize 返回 400 而不是 307
tags:
  - oidc
  - dingtalk
  - sellfox-api-proxy
  - redirect-uri
  - allowlist
  - new-api
---

# OIDC 回调白名单漏项导致赛狐 API 代理钉钉登录全 400

## 现象（2026-11-17）

同事反馈：打开 `https://api.vilavi.cn/sellfox/admin` 点「钉钉登录」，跳到
`/oidc/authorize?...` 后显示「无法登录 / 登录回调地址不合法，请从公司系统重新进入」，
拿不到赛狐 SK。

关键区分：**赛狐代理本身没坏**。同一时刻实测：

| 检查 | 结果 |
|---|---|
| `GET /sellfox/admin` | 200 |
| `GET /sellfox/health` | `{"status":"ok","sellfox_reachable":true}` |
| `GET /oidc/health` | `{"status":"ok"}` |
| `docker ps` | `sellfox-api-proxy` / `new-api-dingtalk-oidc` 均 Up |

## 根因

`new-api-dingtalk-oidc` 的 `/authorize` 有 `redirect_uri` 白名单（防授权码外送），
白名单来自生产 compose 的 `ALLOWED_REDIRECT_URIS`：

```
https://api.vilavi.cn/oauth/dingtalk          # new-api 自带登录
https://api.vilavi.cn/pb/oidc-callback        # pb-orders
https://wayfair-api.vilavi.cn/portal/oidc-callback
```

**缺了** `https://api.vilavi.cn/sellfox/admin/oidc-callback`。日志直接给出结论：

```
WARNING new-api-dingtalk-oidc 拒绝登录：redirect_uri 不在白名单
  redirect_uri=https://api.vilavi.cn/sellfox/admin/oidc-callback client_id=sellfox-api-proxy
INFO: "GET /authorize?... " 400 Bad Request
```

白名单是 2026-10-29 的安全加固（提交 `562c5988`，此前**只在分支上、未合 main**）
按当时 nginx 日志里的两个客户端生成的，赛狐那条当时没进样本，于是被漏掉。

## 修复

1. 生产 `/opt/new-api/docker-compose.yml` 第 69 行追加赛狐回调（先备份：
   `docker-compose.yml.bak-allowlist-<ts>`）。
2. `cd /opt/new-api && docker compose up -d bridge` —— **只重建桥容器**
   （compose 依赖会把 mysql 一起重启，new-api 与 sellfox-proxy 不受影响）。
3. 仓库 `new-api-dingtalk-oidc/redirect_policy.py` 的默认白名单同步补上，
   `tests/test_redirect_policy.py` 增加放行与近似域名拒绝用例。

## 校验

```bash
# 期望 307（跳 login.dingtalk.com），不是 400
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://api.vilavi.cn/oidc/authorize?client_id=sellfox-api-proxy\
&redirect_uri=https%3A%2F%2Fapi.vilavi.cn%2Fsellfox%2Fadmin%2Foidc-callback\
&response_type=code&scope=openid&state=probe"

docker logs --since 5m new-api-dingtalk-oidc | grep 拒绝登录   # 应为空
```

同事重新登录成功后，代理会自动建 Key，可在
`sellfox-api-proxy` 的 SQLite `api_keys` 表按 `dingtalk_user_name` 看到记录。

## 经验教训

- **新增任何 OIDC 客户端要同步两处**：服务器 compose 的 `ALLOWED_REDIRECT_URIS`
  **和** 仓库 `redirect_policy.py` 默认值。只改一边，下次部署/重建就会回退。
- **白名单要靠日志全量取样**，不能凭记忆列"我记得有两三个客户端"：
  `zgrep -ho 'redirect_uri=[^ &]*' /var/log/nginx/access.log* | sort | uniq -c`
  是一个命令的事，漏一个就是全量用户登不进来。
- **健康检查通过 ≠ 业务可用**：`/health` 全绿，登录仍在入口被 400 挡住。
  排查登录类问题要直接打 `/authorize` 探针，看状态码与桥日志。
- **手工部署的安全加固必须合回 main**：本次的加固在生产跑了一个月而 main 里没有，
  既无法 code review 到白名单默认值，也让"下次部署"变成不可预期的行为。
