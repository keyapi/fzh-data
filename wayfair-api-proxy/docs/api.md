---
okf: v0.1
type: Reference
title: 下游 API
description: Wayfair API Proxy 的端点、权限、请求响应示例与错误码
tags: [wayfair, api, errors, freshness]
---

# 下游 API

所有业务端点使用 `Authorization: Bearer <key>`。key 由 `manage.py` 创建，权限按
“账号 + operation”双维度授予。

## 端点

| 方法与路径 | 所需 operation | 说明 |
|------------|----------------|------|
| `GET /health` | 无 | 进程存活，不访问数据库/上游 |
| `GET /ready` | 无 | 数据库状态与各账号快照年龄 |
| `GET /v1/accounts` | 任意有效 key | 仅列出该 key 被授权的账号与 capability |
| `POST /v1/accounts/{account}/inventory/query` | `inventory:snapshot:read` 或 `inventory:live:read` | 按 `mode` 二选一 |
| `GET /v1/accounts/{account}/inventory/snapshot` | `inventory:snapshot:read` | 一次返回整份当前快照（供 EN 每日备份/转 parquet） |
| `POST /v1/accounts/{account}/inventory/transactions/query` | `inventory:transactions:read` | 库存变动流水（实时上游，按 SKU/日期过滤） |
| `POST /v1/offboarding/owners/{owner}/deactivate` | `offboarding:deactivate` | 停用该 owner 的全部 key（离职自动撤销） |
| `POST /v1/accounts/{account}/inbound/query` | `inbound:read` | 未验证时 501 |
| `POST /admin/api/accounts/{account}/snapshot-runs` | `snapshot:run` | 未验证时 501 |

## 库存查询

```http
POST /v1/accounts/centrade/inventory/query
Authorization: Bearer wf-...
Content-Type: application/json

{"skus": ["SKU-1", "SKU-2"], "mode": "snapshot"}
```

`skus` 长度 1–100；`mode` 只能是 `snapshot`（默认）或 `live`。

```json
{
  "items": [
    {
      "sku": "SKU-1",
      "warehouse": "CG",
      "available": 12,
      "on_hand": 15,
      "reserved": 3,
      "unavailable": 0
    }
  ],
  "meta": {
    "account": "centrade",
    "source": "snapshot",
    "fetched_at": "2026-10-28T08:00:00+00:00",
    "age_seconds": 300,
    "stale": false,
    "snapshot_run_id": "…"
  }
}
```

数量字段为 `null` 表示上游未提供该字段或不适用，**不等于 0**。

### freshness

- `source=snapshot`：读最后一次成功 run；没有成功 run 时 `404 snapshot_missing`。
- `source=live`：直接访问上游；失败明确报错，不降级伪装成实时。
- `stale=true` 表示快照年龄超过配置阈值（默认 3600 秒），数据仍返回。

### 整份快照导出

```http
GET /v1/accounts/centrade/inventory/snapshot
Authorization: Bearer wf-...
```

返回与 `mode=snapshot` 相同的 `items/meta`，但包含当前 run 的全部仓位。EN 可每天
调用一次，写入 `stock_latest` 等价表并追加 parquet/JSONL；VPS 只保留
`snapshot_retention_days`（默认 7 天）的 run，不作为长期备份。

### 库存变动流水

```http
POST /v1/accounts/centrade/inventory/transactions/query
Authorization: Bearer wf-...

{"from_date": "2026-10-01T00:00:00+00:00",
 "to_date": "2026-10-28T23:59:59+00:00",
 "sku": "CEN-No/B-967-Linen-Beige-194"}
```

`sku` 可省略；日期可省略。返回：

```json
{"items": [{
  "event_date": "2026-08-31T04:13:20-05:00",
  "adjustment_type": "Cycle Count Adjustment",
  "sku": "CEN-No/B-967-Linen-Beige-194",
  "quantity": -1,
  "warehouse_id": 323010,
  "warehouse_name": "Lancaster",
  "description": "Adj Out - Inventory missing in cycle count process"
}], "meta": {"source": "live", "...": "..."}}
```

`quantity` 带符号（入库为正、出库/调整损失为负）。适合 EN 模仿通途库存操作记录做
每日变动备份；不提供当前库存。

## 在途查询

```http
POST /v1/accounts/centrade/inbound/query
Authorization: Bearer wf-...

{"skus": ["SKU-1"]}
```

当前所有账号 `inbound_live=false`，因此返回 `501 capability_unavailable`。
只有在认证环境确认官方 operation、字段、分页后，才会定义响应结构。

## 错误码

| HTTP | code | 含义 |
|------|------|------|
| 401 | `unauthorized` | 缺少/无效/已停用 key |
| 403 | `forbidden_account` | key 未授权该账号 |
| 403 | `forbidden_operation` | key 未授权该 operation |
| 404 | `unknown_account` | 配置中不存在该账号 |
| 404 | `snapshot_missing` | 该账号还没有成功快照 |
| 422 | `invalid_mode` | `mode` 不是 snapshot/live |
| 429 | `rate_limited` | key 或账号额度耗尽，带 `Retry-After` |
| 501 | `capability_unavailable` | 能力未验证或未开启 |
| 502 | `upstream_auth_failed` | Wayfair 拒绝了 client 凭证或 token |
| 502 | `upstream_forbidden` | 应用未被授权该 operation |
| 429 | `upstream_rate_limited` | Wayfair 限流 |
| 502 | `upstream_unavailable` | 上游网络/5xx/GraphQL 异常 |

上游接入后新增：`upstream_auth_failed`、`upstream_rate_limited`、`upstream_unavailable`。
上游原始错误、token 响应与完整 payload 不会透传给调用方。

## 管理入口

仅在配置了 `oidc` 且环境变量 `WAYFAIR_ADMIN_SESSION_SECRET` 非空时注册；否则全部 404。

| 方法与路径 | 说明 |
|------------|------|
| `GET /admin/oidc-login` | 跳转 OIDC issuer 授权页 |
| `GET /admin/oidc-callback` | 校验 state、换取 token、写入 HttpOnly 会话 cookie |
| `GET /admin/api/me` | 当前管理员身份 |
| `GET /admin/api/keys` | key 列表（不含哈希与明文） |
| `POST /admin/api/keys` | 创建 key，明文只在本次响应出现一次 |
| `POST /admin/api/keys/{id}/deactivate` | 停用 key |
| `POST /admin/api/owners/{owner}/deactivate` | 离职批量停用该 owner 的全部 key |
| `POST /admin/logout` | 清除会话 |

只有 `oidc.admin_identities` 中的 OIDC `sub` 能访问管理接口。登录不会自动创建 key，
也不会授予任何账号权限。管理请求必须是 `application/json`，配合 `SameSite=Lax`
会话 cookie 降低 CSRF 风险。

```json
POST /admin/api/keys
{"name": "forecast", "owner": "ding-user-id",
 "accounts": ["centrade"],
 "operations": ["inventory:snapshot:read"], "rate_limit_rps": 1.0}
```

## 自助门户

仅在配置了 `oidc.portal_redirect_uri`、`WAYFAIR_PORTAL_SESSION_SECRET` 且
`portal_account` 存在时注册；否则 404。详细启用步骤见 [portal.md](portal.md)。

| 方法与路径 | 说明 |
|------------|------|
| `GET /portal/` | 门户页；未登录显示钉钉登录入口 |
| `GET /portal/oidc-login` | 跳转 OIDC |
| `GET /portal/oidc-callback` | state + HttpOnly 会话 |
| `POST /portal/key/issue` | 领取/重建（固定 snapshot 只读，一人一枚） |
| `POST /portal/key/deactivate` | 停用本人 portal key |
| `GET /portal/api/key` | 当前 key 元数据（无明文） |
| `POST /portal/logout` | 退出 |

写操作要求 CSRF double-submit + 同源校验；会话 cookie `Secure` + `SameSite=Lax`。
门户停用不影响管理员/EN 发的 manual key。

## 请求标识

每个响应带 `X-Request-ID`。Nginx 会注入 `$request_id`；应用也接受调用方传入的值用于
跨系统关联。该 ID 只用于日志与审计，不参与鉴权。
