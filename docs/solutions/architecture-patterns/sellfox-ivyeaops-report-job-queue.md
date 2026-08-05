---
okf: v0.1
type: Solution
title: Sellfox 报表 Job 队列（错开 create + 合并轮询）
description: ERPNext 风格 job id；browse/optimizer 共用 ensure_report_bundle；proxy 2s/1 下 fan-out/fan-in。
date: 2026-07-28
category: architecture-patterns
module: ai_access_poc/board
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - Optimizer or browse cold-start waits on Sellfox createTask/xlsx
  - Progress stuck or misleading (e.g. 4/94) during report pulls
  - Multiple UI clicks would duplicate createTask under shared proxy rate limit
tags:
  - sellfox
  - ivyeaops
  - job-queue
  - createTask
  - rate-limit
sources:
  - IvyeaOps-sellfox/server/app/services/sellfox_jobs.py
  - IvyeaOps-sellfox/server/app/services/lingxing_data.py
  - IvyeaOps-sellfox/server/app/services/lingxing_optimizer.py
  - SELLFOX_API/client.py
---

# Sellfox 报表 Job 队列（错开 create + 合并轮询）

## Context

赛狐下载中心是异步的（`createTask` → `pageList` → xlsx）。公司 proxy 约 **2s/1**。旧路径对 SearchTerm / Targeting / Campaign **一张接一张** create+poll，墙钟≈Σ(生成)；进度分母还曾误用领星「天×报表」公式。

## Guidance

1. **共享报表 Job**：SQLite `sellfox_report_jobs` + `POST/GET /lingxing/sellfox/jobs`；幂等键 `(sid, days, datasets, force)`，已有 `queued/running` 则复用。
2. **单 worker**：`asyncio.Semaphore(1)` + create 间隔 ≥2.1s；等待期一次 `pageList` 带全部 `taskIds`；Targeting **只 create 一次**，ingest 双写 keyword+target cache。
3. **共用入口**：`ensure_report_bundle` — 浏览 miss/`force` 与 `run_store` 都走它；热 TTL → 秒级；冷启动墙钟≈**max(生成)+错开 create**。
4. **不上 Celery/Redis**；不降低 proxy 默认限流。

## Evidence (2026-07-28)

- Unit：`tests/test_sellfox_jobs.py` 幂等 + mock worker（3 create，Targeting 一次）。
- Smoke Centrade `596754`：过期 TTL 报表包 ~44s done；热 cache `ensure` **0.14s cached=True**；`run_store` 候选 **261**。
- Smoke Jalnoddsa `596837`：报表包 **~19s** done（fan-in）。
- 网页：Centrade 点「运行优化引擎」→ 新跑 `16:28:53 · 候选 261 条`（热路径）。
- VERCART-US `596789`：Job/优化均 done 但候选 0；空搜索词/定向表为赛狐真值 + 匹配分流，见 [sellfox-empty-searchterm-vs-target-report-split.md](../best-practices/sellfox-empty-searchterm-vs-target-report-split.md)。
