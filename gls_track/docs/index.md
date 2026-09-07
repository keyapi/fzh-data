---
okf: v0.1
type: Index
title: gls_track 文档索引
description: GLS 波兰自发货跟踪模块（公开无鉴权 REST，免开发者账号）文档
tags: [gls, track, module]
---

# gls_track

GLS(波兰自发货)单号批量跟踪 + FedEx 风格运营异常表。**无需开发者账号 / 无需波兰 GLS 登录**：
走 GLS 消费级网页的**公开无鉴权 REST**（摘要 `rstt029`；明细 `rstt028` 需目的邮编）。

## 关键决策

- 公开无鉴权 REST（免账号）而非官方 ShipIT：官方需 GLS 波兰客户 + WebAPI 开通（业务协调），公开路径零账号可全量。
- GLS 口径独立：`HANDLING_DAYS=2`、营业日用**波兰 2026 法定假日**（起运/交接在 GLS 波兰），不用 FedEx 美国联邦假日；周末天然排除。
- `monthly` 一步整月：批量查 → 出 8-Sheet 运营异常表。
- loader 自动拆**一格多号**；非 GLS 号(1Z/…U/碎片)照查 404 → 报表「数据异常/查无」。

## 目录

| 文档 | 说明 |
|---|---|
| [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) | Agent 入口：端点/命令/口径/坑/parcel_track 接入 |
| [README.md](../README.md) | 人读：怎么跑 |
| [log.md](log.md) | 变更日志 |
