---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-27

- **新增**: `tongtool-inventory-semantics-and-snapshot-timing.md` — 可用/待发/在途/次品四桶，物理在库 = available + waiting（不含次品）；订单占用/发货/拆包事件流；美欧操作节奏（欧洲 09–11、美国 13–17、周一重、周二补发）；快照时点 05:17 开门 + 12:00 波兰 + 18:00 美东/美中；盘中独立 `stock_intraday.parquet`，派生分析放本地 DuckDB。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
