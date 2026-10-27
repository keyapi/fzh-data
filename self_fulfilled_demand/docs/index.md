---
okf: v0.1
type: Index
title: 自发货需求增量接入 — 文档索引
description: EN Tongtool Order 只读增量、en-demand-v1 本地 Parquet、旧 GS 统一消费接口
tags: [supply-chain, demand, erpnext, parquet, en-demand-v1]
updated: 2026-10-27
---

# 自发货需求增量接入 — 文档索引

> Agent 入口先读 [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) 与 [`../README.md`](../README.md)。

| 你需要… | 读这个 |
|---|---|
| EN 订单真实 schema、字段填充率、分页坑 | [reference/en-order-schema.md](reference/en-order-schema.md) |
| 旧 GS 407,898 行 + 10 月增量怎么拼 | [reference/consumer-interface.md](reference/consumer-interface.md) |
| 规范 SKU×仓×UOM、净额资格、b08acc05 接口 | [reference/canonical-demand.md](reference/canonical-demand.md) |
| 本次验收结果、数量对账、剩余阻塞 | [acceptance-report-2026-10-27.md](acceptance-report-2026-10-27.md) |
| da4fa1e6 审核返修：子仓阻断/四列净额/快照身份 | [review-fix-da4fa1e6.md](review-fix-da4fa1e6.md) |
| 变更时间线 | [log.md](log.md) |

## 产物路径（本地，不进 git）

- 存储：`D:/Work/fzh-order-store/en-demand-v1/`
- 原始订单 payload：`D:/Work/fzh-order-store/en-demand-v1/raw/en_orders_raw.parquet`
- 运行报告：`D:/Work/fzh-order-store/en-demand-v1/runs/<run_id>.json`
- manifest：`D:/Work/fzh-order-store/en-demand-v1/manifest.json`
- 消费输出：`D:/Work/fzh-order-store/en-demand-v1/consumer/`
