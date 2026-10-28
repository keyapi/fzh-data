---
okf: v0.1
type: Explanation
title: 架构设计
description: Wayfair API Proxy 的组件边界、请求流、数据模型与快照发布语义
tags: [wayfair, architecture, sqlite, snapshot, rate-limit]
---

# 架构设计

## 拓扑

```text
内部工具 ──Tailscale──┐
                      ├─ Nginx 443 (TLS) ── 127.0.0.1:8410 FastAPI ── Wayfair API
公网客户端 ──HTTPS─────┘                         │
                                                └─ SQLite (WAL) /data/wayfair.db

systemd timer ── docker run --rm ── snapshot.py ── 同一 SQLite 卷
```

公网与 Tailscale 走同一个 HTTPS 入口、同一套 Bearer key 鉴权；网络来源不构成授权。
应用端口不发布到公网，只绑定 `127.0.0.1`。

## 组件职责

| 组件 | 职责 | 不做什么 |
|------|------|----------|
| `main.py` | 路由、鉴权、限流、审计、`/ready` | 不拼 Wayfair 请求 |
| `service.py` | 快照/live 分支、freshness、capability 判定 | 不直接访问 HTTP |
| `wayfair_client.py` | 上游 OAuth 与固定 operation | 不接受调用方提交的 query/path |
| `db.py` | key、快照、审计、ready 数据 | 不存明文 key |
| `snapshot.py` | 一次性采集并发布 | 不在 Web 进程内常驻调度 |
| `admin.py` | DingTalk OIDC 管理员会话、key 创建/停用 | 不做自动授权、不提供 HTML 或 key reveal |
| `manage.py` | key 生命周期 | 不提供 HTTP reveal |

## 请求流（库存查询）

1. 解析 `Authorization: Bearer`，用 SHA-256 查 active key；更新 `last_used_at` 与计数。
2. 按 `mode` 选权限：`snapshot` → `inventory:snapshot:read`；`live` → `inventory:live:read`。
3. 校验 key 允许的账号与 operation，两者缺一即 403。
4. 两层限流：key 维度、账号 + mode 维度；超限返回 429 与 `Retry-After`。
5. 读取 capability；未开启直接 501，不触达上游。
6. `snapshot` 读最后一次成功 run；`live` 调用上游客户端并获得 `fetched_at`。
7. 返回 `items` + `meta`（`source`、`fetched_at`、`age_seconds`、`stale`、`snapshot_run_id`）。

## 数据模型

- `api_keys`：id、`key_hash`（唯一）、`key_prefix`、名称、`owner`、账号 JSON、operation JSON、
  限流、启停、创建/最后使用/请求计数。没有明文列。
- `snapshot_runs`：每次 run 的状态、起止、上游行数、写入/跳过/失败数、错误分类。
- `inventory_positions`：以 `account + sku + warehouse + run_id` 为主键；数量字段在契约
  验证后冻结。
- `current_snapshots`：每账号指向当前成功 run。
- `audit_events`：请求级审计，不含 header、body、token、secret。

## 快照发布语义

成功 run 在单个 `BEGIN IMMEDIATE` 事务中：

1. 插入 `snapshot_runs`（status=success）。
2. 插入该 run 的全部 `inventory_positions`。
3. 切换 `current_snapshots`。

失败 run 只插入 `snapshot_runs`（status=failed），不触碰 `current_snapshots`。
因此下游永远读到“最后一次成功”，失败不会把好数据清空。

`age_seconds` 基于 run 的 `finished_at` 计算；超过 `snapshot_stale_after_seconds`
（默认 3600）标记 `stale=true`，数据仍返回以便预测系统自行决策。

## capability 闸门

每账号三个静态开关：`inventory_snapshot`、`inventory_live`、`inbound_live`，默认全关。
只有认证环境里实测通过的 operation 才能打开。未开启时：

- 库存查询返回 `501 capability_unavailable`；
- inbound 返回 `501`；
- 手动快照入口返回 `501`；
- worker 以 `BLOCKED` 退出。

上游契约与授权状态见 [contract.md](contract.md)。库存查询走
`inventorySummaryList`，按 `pageInfo` 游标翻页；`available` 取
`inStock.fulfillableQty`，`reserved` 取 `allocatedQty`，`unavailable` 取
`unfulfillableQty`。token 由 `TokenCache` 按账号单飞刷新。

## 限流与并发

- 限流是进程内 token bucket，因此部署固定单 worker。多 worker 会把额度放大。
- `live_rate_limit_rps` 可为小数，`0.2` 表示平均每 5 秒一次，带 1 次突发容量。
- `token_cache.py` 为每账号复用同一个 `asyncio.Lock`，避免并发刷新风暴；当前尚未接入
  主流程，接入真实 OAuth 时使用。

## 为什么不用更重的组件

单 VPS、低频查询、单团队使用。SQLite WAL 足以支撑快照与审计；引入 PostgreSQL、
消息队列或通用网关只会增加运维面，不解决这里的问题。
