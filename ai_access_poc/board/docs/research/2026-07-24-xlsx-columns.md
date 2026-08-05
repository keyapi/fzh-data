---
okf: v0.1
type: Research
title: 2026-07-24-xlsx-columns
timestamp: 2026-07-24
---

﻿# Sellfox SP search-term columns (confirmed)

Source file: `ai_access_poc/open_webui/reports/SearchTerm_TOODDLY-Daneey-US_2026-07-17_2026-07-23.xlsx`  
Shape: **1922 rows × 32 columns** (pandas + openpyxl)  
Refs: `board/docs/reference/column-mapping.md`, `_summarize_search_term_xlsx` in `open_webui/tools/sellfox_pull_sp_search_term.py`

## Confirmed optimizer ↔ Sellfox mapping

All keys in `column-mapping.md` are present in this xlsx:

| Optimizer key | Sellfox column | Present | Sample dtype (pandas) | Sample value |
|---------------|----------------|---------|----------------------|--------------|
| `query` | `用户搜索词` | yes | str | `headboard twin xl` |
| `cost` | `广告花费` | yes | float64 | `8.1` |
| `clicks` | `广告点击量` | yes | int64 | `18` |
| `orders` | `广告订单量` | yes | int64 | `0` |
| `sales` | `广告销售额` | yes | float64 | `0.0` |
| `impressions` | `广告曝光量` | yes | int64 | `1162` |
| `campaign_id` | `广告活动ID` | yes | int64 | `243363553018323` |
| `ad_group_id` | `广告组ID` | yes | int64 | `279826522573575` |
| `match_type` | `匹配类型` | yes | str (nullable) | `精确匹配` |
| `campaign_name` | `广告活动` | yes | str | `平条有扣-SP CDC1` |
| `report_date` | `日期` | yes | datetime64[us] / Timestamp | `2026-07-21T00:00:00` |

Notes:
- Board ingest English key for spend is `cost`; `_summarize_search_term_xlsx` uses internal alias `spend` for the same column `广告花费`.
- `匹配类型` values seen: `精确匹配`, `广泛匹配`, `词组匹配`; **572/1922 null** (likely非关键词投放行).
- IDs are large integers (fit int64).

## `_summarize_search_term_xlsx` col_map (tool)

| Internal key | Sellfox column | Present |
|--------------|----------------|---------|
| `term` | `用户搜索词` | yes |
| `spend` | `广告花费` | yes |
| `impr` | `广告曝光量` | yes |
| `clicks` | `广告点击量` | yes |
| `sales` | `广告销售额` | yes |
| `orders` | `广告订单量` | yes |
| `acos` | `ACoS` | yes |
| `roas` | `ROAS` | yes |
| `cpc` | `CPC` | yes |
| `shop` | `店铺` | yes |
| `date` | `日期` | yes |

Required-for-summary columns (`用户搜索词`, `广告花费`) both present.

## Full xlsx columns + sample field types (row 0)

| # | Column | dtype | sample_type | nunique | nulls | sample |
|---|--------|-------|-------------|---------|-------|--------|
| 0 | 店铺 | str | str | 1 | 0 | TOODDLY-Daneey-US |
| 1 | 日期 | datetime64[us] | Timestamp | 7 | 0 | 2026-07-21T00:00:00 |
| 2 | 用户搜索词 | str | str | 1049 | 0 | headboard twin xl |
| 3 | 投放 | str | str | 117 | 0 | headboard twin xl |
| 4 | 匹配类型 | str | str | 3 | 572 | 精确匹配 |
| 5 | 广告活动 | str | str | 37 | 0 | 平条有扣-SP CDC1 |
| 6 | 广告组 | str | str | 38 | 0 | 平条有扣-SP CDC1 |
| 7 | 定位类型 | str | str | 2 | 0 | 手动 |
| 8 | 广告花费 | float64 | float64 | 239 | 0 | 8.1 |
| 9 | 广告曝光量 | int64 | int64 | 333 | 0 | 1162 |
| 10 | 广告点击量 | int64 | int64 | 25 | 0 | 18 |
| 11 | CPC | float64 | float64 | 84 | 0 | 0.45 |
| 12 | 广告点击率 | float64 | float64 | 289 | 0 | 0.0155 |
| 13 | 广告转化率 | float64 | float64 | 17 | 0 | 0.0 |
| 14 | ACoS | float64 | float64 | 57 | 0 | 0.0 |
| 15 | ROAS | float64 | float64 | 59 | 0 | 0.0 |
| 16 | 广告订单量 | int64 | int64 | 3 | 0 | 0 |
| 17 | 本广告产品订单量 | int64 | int64 | 3 | 0 | 0 |
| 18 | 其他产品广告订单量 | int64 | int64 | 3 | 0 | 0 |
| 19 | 广告销售额 | float64 | float64 | 30 | 0 | 0.0 |
| 20 | 本广告产品销售额 | float64 | float64 | 16 | 0 | 0.0 |
| 21 | 其他产品广告销售额 | float64 | float64 | 22 | 0 | 0.0 |
| 22 | 广告销量 | int64 | int64 | 4 | 0 | 0 |
| 23 | 本广告产品销量 | int64 | int64 | 4 | 0 | 0 |
| 24 | 其他产品广告销量 | int64 | int64 | 3 | 0 | 0 |
| 25 | 广告组合名称 | str | str | 7 | 246 | 平条有扣-B0CKQJ5BB7 |
| 26 | 币种 | str | str | 1 | 0 | USD |
| 27 | 广告活动开始时间 | str | str | 20 | 0 | 2026-07-20 |
| 28 | 广告活动结束时间 | str | str | 1 | 0 | 无结束日期 |
| 29 | 广告活动ID | int64 | int64 | 37 | 0 | 243363553018323 |
| 30 | 广告组ID | int64 | int64 | 38 | 0 | 279826522573575 |
| 31 | 广告投放ID | int64 | int64 | 209 | 0 | 101373569428277 |

## Missing / not covered for optimizer

**From `column-mapping.md` expected keys:** none missing in this xlsx.

**Not in this SP search-term export (needed for fuller optimizer beyond negate/harvest — see `deviations.md` D3):**
- Keyword / bid dataset (`sp_keywords`): bid, keyword state, keyword_id as first-class write target
- Campaign budget / campaign-level report fields for “加预算” candidates
- Explicit ASIN / SKU targeting id (only `广告投放ID` + `投放` text / `广告组合名称` here)

**Present in xlsx but unused by board optimizer mapping / `_agg` keys:**
- `投放`, `广告组`, `定位类型`, `CPC`, `广告点击率`, `广告转化率`, `ACoS`, `ROAS`
- SKU-split metrics: `本广告产品*`, `其他产品广告*`
- `广告销量` (+ splits), `广告组合名称`, `币种`, `广告活动开始时间`, `广告活动结束时间`, `广告投放ID`, `店铺`

**Caveats for ingest:**
- `match_type` nulls must be handled (do not assume always str).
- `report_date` arrives as datetime; normalize to date string if cache expects date-only.
- Attribution window for `orders`/`sales` may differ from Lingxing (deviation D1) — column exists, semantics may differ.
