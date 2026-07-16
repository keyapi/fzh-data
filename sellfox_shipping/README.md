---
okf: v0.1
type: Guide
title: sellfox_shipping — 赛狐尾程打单系统
description: 赛狐包裹同步、物流批次、追踪号审核与回写的独立服务
updated: 2026-07-16
---

# sellfox_shipping — 赛狐尾程打单系统

> 目标架构：Web UI（人类）+ REST/JSON CLI（系统与脚本）共享 Service Layer。
> 当前先完成以赛狐包裹为核心的只读同步；物流 Excel 和安全回写按阶段实现。

## 快速开始

```bash
# 启动 Web 服务
uv run python -m sellfox_shipping.cli serve

# P1A：从赛狐订单处理接口同步包裹（只读，不回写）
# 运行前通过环境变量提供 Sellfox proxy key
uv run python -m sellfox_shipping.cli packages-sync --date-start 2026-07-15 --date-end 2026-07-16 --actor <operator-id> --json

# Legacy：从赛狐拉订单
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15

# Legacy：查看订单
uv run python -m sellfox_shipping.cli orders --status to_print
```

打开 http://localhost:8401 查看 Web UI。

## 架构

详见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 和 [docs/index.md](docs/index.md)。

## 当前阶段

**P1A 第一条纵切已完成：**

- 赛狐 camelCase wire payload → Python snake_case 包裹模型
- `(sellfox_account_id, package_sn)` 作用域和订单/包裹多对多持久化
- SQLite WAL + SQLAlchemy repository
- 分页同步、逐行差异报告和失败后部分报告
- `packages-sync` JSON CLI

下一步：schema migration、钉钉 OIDC、包裹查询/审核界面；蜴国际 Excel 依赖真实样例。
