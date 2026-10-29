---
okf: v0.1
type: Index
title: Wayfair API Proxy — 文档索引
description: 渐进式加载入口
tags: [wayfair, api-proxy, index]
---
# Wayfair API Proxy — 文档索引

> Agent 接手先读 [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md)，需要细节时按下表深入。

| 你需要… | 读这个 |
|---------|--------|
| 了解已验证的上游 operation/字段/授权状态 | [contract.md](contract.md) |
| 开通生产权限、跑 sandbox 测试 | [sandbox-test.md](sandbox-test.md) |
| 接 EN/DuckDB：原始层、分析层、统一层 | [en-integration.md](en-integration.md) |
| 同事自助 key（钉钉登录、一人一枚只读） | [portal.md](portal.md) |
| 相关踩坑（API 契约、库存表粒度、EN 时区、共享 VPS 不装 Docker、gitignore 漏源码） | `../../docs/solutions/integration-issues/wayfair-castlegate-inventory-api.md`、`../../docs/solutions/architecture-patterns/wayfair-cg-stock-table-and-parquet-grain.md`、`../../docs/solutions/developer-experience/erpnext-wayfair-sync-timezone-pitfalls.md`、`../../docs/solutions/architecture-patterns/shared-egress-vps-venv-systemd-no-docker.md`、`../../docs/solutions/developer-experience/gitignore-sensitive-pattern-hides-source-module.md` |
| 了解为什么这样设计、数据怎么流 | [architecture.md](architecture.md) |
| 调接口、看错误码与 freshness | [api.md](api.md) |
| 部署、轮换 secret、验收、回滚 | [operations.md](operations.md) |
| 看变更记录 | [log.md](log.md) |
| 本地运行与 key 管理 | [`../README.md`](../README.md) |

## 目录结构

```text
docs/
├── index.md           本文件
├── log.md             变更记录
├── architecture.md    架构、数据模型、快照语义
├── api.md             下游 API 与错误码
└── operations.md      部署与运维手册
```
