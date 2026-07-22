---
okf: v0.1
type: Guide
title: sellfox_shipping — 赛狐尾程打单系统
description: 赛狐包裹同步、物流批次、追踪号审核与回写的独立服务
updated: 2026-07-22
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

# 本地包裹列表（只读本地库）
uv run python -m sellfox_shipping.cli packages-list --status to_audit --json

# Legacy：从赛狐拉订单
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15

# Legacy：查看订单
uv run python -m sellfox_shipping.cli orders --status to_print
```

打开 http://localhost:8401 查看 Web UI。

## 架构

详见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 与 [docs/index.md](docs/index.md)。

## 当前阶段

**P1A–P1C 代码主路径已合入 main（PR #96 / #97）。** Excel 本地闭环可用；Intent/CAS 默认 dry-run。  
产品缺口：赛狐可见 `trackNo`（live 曾 401）。通途写平台；自动推送关。Excel 生产默认；API 可选。

接手：只读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
