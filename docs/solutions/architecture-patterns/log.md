---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-20

- **新增**: `order-history-duckdb-store.md` — 销量预测/补货的历史数据架构：GS 月表（2023-01 起）+ EN 并集进 DuckDB；实测通途 API 历史可见性有限（不带 accountCode 约 5–6 千条封顶、可见性跟最近更新时间走），**不能用来补齐历史**；含运费口径演进（运费 → 通途运费/物流商运费）、子表 REST 403 的绕法、SKU 归一 99.2%、补货快照首版。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
