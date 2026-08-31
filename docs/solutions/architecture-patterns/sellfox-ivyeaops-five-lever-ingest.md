---
okf: v0.1
type: Solution
title: 赛狐 Phase2 ingest — IvyeaOps 五杠杆优化器数据接线
description: 表现报表 + manageData 实体 + asin_profit 必须一并接线；Targeting 过滤关键词行；monthProfit 用 reportList 且 pageSize≤200。
date: 2026-07-28
category: architecture-patterns
module: ai_access_poc/board
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - Wiring Sellfox read-only sources into IvyeaOps sellfox_cache for lingxing_optimizer
  - Phase2 beyond search-term-only PoC
  - Optimizer shows only 否词/收割 and missing 降/加 bid
tags:
  - sellfox
  - ivyeaops
  - five-lever
  - phase2-ingest
  - sellfox-cache
sources:
  - ai_access_poc/board/scripts/ingest_sellfox_phase2.ps1
  - ai_access_poc/board/docs/specs/phase2-dataset-gap.md
  - docs/superpowers/plans/2026-07-28-phase2-sellfox-ingest.md
---

# 赛狐 Phase2 ingest — IvyeaOps 五杠杆优化器数据接线

## Context

板 PoC 早期只把赛狐 **搜索词报表** ingest 进 `sellfox_cache`，optimizer 只能稳定出 **否词 / 收割**。降/加 bid、加预算需要「表现报表 + 实体配置」两套源；曾被误读成「赛狐顶替不了领星」。2026-07-28 煮湖证明赛狐源齐全，缺口是 **未接线**。同日 Phase2 ingest 落地后，标定店 BJRYECLTD-US（`596841`）`run_store` 出 **35** 候选（否词 15 / 收割 2 / 降bid 17 / 加bid 1）。

勿与 **五桶**（advertise Harvest/Negate/Monitor/Protect/Ignore）混淆——见根目录 `CONCEPTS.md`。

## Guidance

### 1. 两类数据一起接

| 类型 | 回答 | 赛狐形态 | IvyeaOps 用途 |
|------|------|----------|---------------|
| 表现报表 | 窗内花费/点击/订单 | 下载中心 xlsx | `_agg` 汇总指标 |
| 实体配置 | 当前 bid / state / 日预算 | `manageData/*.json` | 提案 `current` 与改幅 |

缺实体时：有高 ACOS 词也算不出「从多少降到多少」。

### 2. 接线清单（已验证）

| Dataset | 赛狐源 | 要点 |
|---------|--------|------|
| `sp_search_term_report` | `adSearchTermReport` | 否词/收割 |
| `sp_keyword_report` | `adTargeringReport` | **只保留**匹配类型 ∈ 广泛/词组/精确/主题；`广告投放ID`→`keyword_id` |
| `sp_keywords` | `spKeyword.json` | `bid`/`state`；`nextToken` 分页 |
| `sp_campaign_report` | `adCampaignReport` | 无预算列（预期） |
| `sp_campaigns` | `spCampaign.json` | `budget`→`daily_budget` |
| `sp_product_ads` | `spAdProduct.json`（勿用 `spProductAd`） | campaign→ASIN |
| `asin_profit` | `monthProfit/asin.json` | 列表键 **`reportList`**；`grossProfitRate`→`grossRate`；**`pageSize`≤200** |

缓存：`{data_dir}/sellfox_cache/{dataset}__{sid}.json`。`SELLFOX_READONLY_POC=1` + `SELLFOX_WINDOW_MODE=aggregate` 时 `fetch_dataset` 读 cache。

### 3. 入口

```powershell
# 默认 BJRYECLTD-US / 30 天
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\ingest_sellfox_phase2.ps1
```

实现在仓外 fork：`IvyeaOps-sellfox` 的 `sellfox_ingest.py` + `lingxing_data.fetch_dataset`（勿 vendor AGPL 进 fzh-data）。

### 4. 写路径仍硬禁

ingest 只服务只读候选；`confirm_ticket` / 赛狐广告写 API 不放开。

## Why This Matters

- 避免「加领星账号」弯路——能力在赛狐，差的是 ingest。  
- Targeting 不过滤会把商品定向 ID 当 keyword_id，污染 bid 杠杆。  
- `rows` vs `reportList`、`pageSize=500` 会静默空利润 → 目标 ACOS 退回默认 30%。

## When to Apply

- 新店 / 换窗后要跑全杠杆候选  
- 只有否词收割、没有降加 bid  
- 利润权限刚开通，要接 `asin_profit`  
- 文档或同事把「五桶」说成「五杠杆」时先对齐词汇

## Examples

**Before：** 仅 `ingest_sellfox_for_ivyeaops.ps1`（搜索词）→ 候选无 bid 类。  

**After：** `ingest_sellfox_phase2.ps1` → 实体 611/94/277 + Targeting 1034 关键词行 + Campaign 291 + 利润 24 → `run_store(596841)` 含降/加 bid。加预算可为 0（阈值严，非未接线）。

## Related

- Spec：[phase2-dataset-gap.md](../../../ai_access_poc/board/docs/specs/phase2-dataset-gap.md)
- Backlog：[phase2-backlog.md](../../../ai_access_poc/board/docs/specs/phase2-backlog.md)
- 计划：[2026-07-28-phase2-sellfox-ingest.md](../../superpowers/plans/2026-07-28-phase2-sellfox-ingest.md)
- 相邻 E2E：[ivyeaops-assistant-deepseek-v4-model-name.md](../integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md)
- 词汇：`CONCEPTS.md`（五杠杆 / 五桶）
