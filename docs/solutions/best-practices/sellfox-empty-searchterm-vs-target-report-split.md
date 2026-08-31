---
okf: v0.1
type: Solution
title: 浏览空表 ≠ 拉取失败 — VERCART 搜索词/定向复验
description: 赛狐下载中心对部分店返回空搜索词表；定向 xlsx 全是关键词匹配时「SP 定向报表」为 0 属归一化分流。
date: 2026-07-28
category: best-practices
module: ai_access_poc/board
problem_type: operational_knowledge
component: tooling
severity: medium
applies_when:
  - Optimizer returns 0 candidates and browse shows empty SP search-term / target reports
  - Suspecting Job queue or ingest dropped rows after a successful run
tags:
  - sellfox
  - ivyeaops
  - search-term
  - targeting
  - empty-report
sources:
  - IvyeaOps-sellfox/server/app/services/sellfox_ingest.py
  - SELLFOX_API/client.py
  - docs/solutions/architecture-patterns/sellfox-ivyeaops-report-job-queue.md
---

# 浏览空表 ≠ 拉取失败 — VERCART 搜索词/定向复验

## Context

PR #124 之后落地报表 Job 队列。运营在 **VERCART-US（sid `596789`）** 跑近 30 天优化引擎（约 16:50→16:53）得 **0 候选**；数据浏览见 **SP 搜索词报表**、**SP 定向报表**为空，易误判为拉数失败。

## Guidance

1. **先看 cache / 原始 xlsx 行数**，再下结论。Job `done` + `synced_at` 有值仍可能是 **0 行真值**。
2. **搜索词空**：`pull_cpc_report(adSearchTermReport)` 得到的 xlsx 可以只有表头（VERCART 复验 shape `(0, 32)`，~4KB）。不是归一化丢列。
3. **「SP 定向报表」空 ≠ Targeting 没拉到**：`adTargeringReport` 按「匹配类型」分流——关键词匹配进 `sp_keyword_report`，非关键词（ASIN/品类等）进 `sp_target_report`。VERCART Targeting 97 行全是「广泛匹配」→ 关键词 97、定向 0。
4. **0 候选**还要看阈值：VERCART 关键词行点击全为 0 → 否词/收割/bid 杠杆均无法触发。

## Evidence (2026-07-28)

- 优化运行 `c9ee794dd3a5`：候选 0，报表 Job `b1264042cecd` done。
- 后端重拉：`adSearchTermReport` → 0 行；`adTargeringReport` → 97 行 / normalize keyword=97 target=0。
