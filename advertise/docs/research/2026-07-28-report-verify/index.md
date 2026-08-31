---
okf: v0.1
type: Index
title: 2026-07-28 SP7 报表独立验证
description: BJRYECLTD-US 七表重拉后的列对账与 analyze 复跑索引
tags: [sellfox, sp-report, verify, ivyeaops]
timestamp: 2026-07-28
---

# 2026-07-28 SP7 报表独立验证

| 报表 | 行数 | 列对账 | analyze | verdict | 详情 |
|------|------|--------|---------|---------|------|
| campaign | 291 | OK | PASS | **PASS** | [campaign.md](campaign.md) |
| targeting | 1176 | OK | PASS | **PASS** | [targeting.md](targeting.md) |
| search_term | 1226 | OK | PASS | **PASS** | [search_term.md](search_term.md) |
| placement | 911 | OK | PASS | **PASS** | [placement.md](placement.md) |
| ad_group | 282 | OK | PASS | **PASS** | [ad_group.md](ad_group.md) |
| advertised_product | 604 | OK | PASS | **PASS** | [advertised_product.md](advertised_product.md) |
| purchased_item | 14 | OK | PASS | **PASS** | [purchased_item.md](purchased_item.md) |

拉取 meta：`advertise/data/_pull_meta_*.json` — ok=7 fail=0

## 相关

- [字段释义与 D1](field-meanings-and-d1.md)
- [Phase2 缺口矩阵](../../../ai_access_poc/board/docs/specs/phase2-dataset-gap.md)

## README 纠偏

- `fetch_ad_reports.py` 只拉 4 表；额外 3 表需 `fetch_extra_reports.py` 或 `advertise/scripts/pull_sp7_verify.py`（Proxy 一键 7 表）。
- 旧 `advertise/out/*_analysis.json` **不可信**；本轮产物在 `advertise/out/verify_2026-07-28/`。
- SearchTerm analyze 曾因「无结束日期」失败 → 已修 `analyze_search_term.py`（`errors="coerce"`）。
