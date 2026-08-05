---
okf: v0.1
type: Solution
title: Sellfox 对齐原生按需拉取 — READ_DATASETS 12/12
description: fetch_dataset miss/force 调赛狐 ensure_dataset；TTL cache；PoC 禁止回落领星；离线 ingest 仅可选预热。
date: 2026-07-28
category: architecture-patterns
module: ai_access_poc/board
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - Exposing IvyeaOps Sellfox PoC to ops colleagues for self-serve browse/optimizer
  - Fixing「未配置领星 OpenAPI 凭证」on FBA/adgroups/targets under SELLFOX_READONLY_POC
  - Replacing pre-ingest-only cache with native on-demand semantics
tags:
  - sellfox
  - ivyeaops
  - fetch_dataset
  - on-demand
  - sellfox-cache
sources:
  - IvyeaOps-sellfox/server/app/services/lingxing_data.py
  - IvyeaOps-sellfox/server/app/services/sellfox_ingest.py
  - ai_access_poc/board/docs/research/2026-07-28-sellfox-ad-catalog-map.md
---

# Sellfox 对齐原生按需拉取 — READ_DATASETS 12/12

## Context

原生领星：数据浏览切表/换店/查询 → `fetch_dataset` → TTL 缓存命中或 **实时 OpenAPI**。  
Sellfox PoC 曾误做成「必须先跑 ingest 脚本」；未接线的 4 表 fallthrough 领星 → 「未配置领星 OpenAPI 凭证」。

## Guidance

1. **`SELLFOX_READONLY_POC=1` 时**：`sellers` 实时；其余 11 键走 `sellfox_ingest.ensure_dataset`（TTL 默认 1800s；miss/`force` 拉赛狐写 `sellfox_cache`）。
2. **禁止 fallthrough 领星**；失败只抛赛狐错误文案。
3. **4 表接线**：`sp_adgroups`←`spGroup`；`sp_targets`←`spTarget`；`fba_stock`←FBA pageList；`sp_target_report` 与 `sp_keyword_report` **共享** `adTargeringReport` 一次下载后行过滤。
4. **aggregate 消费者**（dashboard/automation/report）：与优化器一样一次取窗，禁止按天 ×N。
5. **离线** `ingest_sellfox_phase2.ps1`：**可选预热/对账**，非产品前置。
6. **写路径**：继续硬阻断。

## Smoke (2026-07-28)

Jalnoddsa-US `596837`：`fetch_dataset` 对 `READ_DATASETS` 全 12 键 **OK**，零「领星」错误文案。浏览器：数据浏览 SP 活动表有数；优化建议可运行。
