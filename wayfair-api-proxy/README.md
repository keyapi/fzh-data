---
okf: v0.1
type: Reference
title: Wayfair API Proxy
description: 美国 Vultr 上的 Wayfair 库存/在途只读网关，供销量预测系统与内部工具调用
tags: [wayfair, inventory, api-proxy, vultr, fastapi]
---

# Wayfair API Proxy

部署在美国 Vultr VPS 上的 Wayfair 只读网关。目标是让销量预测/下单决策系统读取
Centrade CastleGate 库存，同时避免中国侧直接携带 Wayfair 凭证访问上游。

## 当前状态（重要）

| 能力 | 状态 |
|------|------|
| 下游 API、鉴权、限流、审计 | 已实现并有测试 |
| 快照数据库与发布语义 | 已实现并有测试 |
| Wayfair OAuth / 库存 operation | 已实测：token 与 `inventorySummaryList` 存在；应用缺 `read:inventory_visibility` 生产权限 |
| 在途（inbound）operation | 无官方独立 operation，`inbound_live` 保持关闭 |
| 钉钉 OIDC 管理入口 | 已实现：管理员登录 + key 创建/停用（JSON API，无自动授权） |

三个账号的 capability 在示例配置中全部为 `false`。在认证环境里用真实
Centrade CastleGate SKU 完成字段对账之前，不得打开任何能力。

## 目录

```text
wayfair-api-proxy/
├── main.py              FastAPI 应用与固定业务路由
├── config.py            账号、capability、限流、陈旧阈值
├── wayfair_client.py    上游客户端（当前为安全闸门，未实现真实调用）
├── service.py           快照/live 业务逻辑与 freshness
├── db.py                SQLite：key、快照、审计
├── auth.py              账号 + operation 双重授权
├── rate_limit.py        进程内 token bucket
├── token_cache.py       每账号持久锁的 single-flight token 缓存
├── snapshot.py          一次性快照 worker（当前 BLOCKED 退出）
├── manage.py            API key 创建/列出/停用
├── smoke_test.py        localhost 与公网双路径验收
├── deploy/              Docker Compose、Nginx、systemd 示例
└── docs/                OKF 文档
```

## 本地运行

```bash
uv run pytest wayfair-api-proxy/tests
uv run uvicorn main:create_runtime_app --factory --app-dir wayfair-api-proxy --port 8410
```

运行前需要 `WAYFAIR_CONFIG` 指向配置文件；默认读取当前目录 `config.yaml`。
数据库默认 `/data/wayfair.db`，本地可用 `WAYFAIR_DATABASE` 覆盖。

## 创建调用方 key

```bash
WAYFAIR_CONFIG=wayfair-api-proxy/config.example.yaml \
WAYFAIR_DATABASE=/tmp/wayfair.db \
uv run python wayfair-api-proxy/manage.py create \
  --name forecast \
  --account centrade \
  --operation inventory:snapshot:read
```

明文 key 只在创建时打印一次；数据库只保存 SHA-256 哈希与前缀。
停用用 `manage.py deactivate --id <id>`。

## 相关文档

- [AGENT_HANDOFF.md](AGENT_HANDOFF.md) — Agent 接手入口
- [docs/index.md](docs/index.md) — 文档索引
- [docs/architecture.md](docs/architecture.md) — 架构与数据流
- [docs/api.md](docs/api.md) — 下游 API 与错误码
- [docs/operations.md](docs/operations.md) — 部署、轮换与验收

## 安全边界

- 应用只监听 `127.0.0.1`；公网和 Tailscale 都经 Nginx HTTPS。
- 不做任意 Wayfair path / GraphQL 透传，只暴露固定 operation。
- 不保存可恢复的明文 key，不提供 reveal 接口。
- 日志与审计不记录 Authorization、secret、token 或完整 payload。
- 任何共享 VPS 的部署、重启、Nginx/防火墙修改、secret 轮换都需用户明确授权。
