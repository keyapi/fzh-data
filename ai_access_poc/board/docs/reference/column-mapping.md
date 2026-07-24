---
okf: v0.1
type: Reference
title: 搜索词列映射（优化器 ↔ 赛狐 xlsx）
tags: [reference, sellfox, column-mapping]
timestamp: 2026-07-24
resource: ai_access_poc/open_webui/tools/sellfox_pull_sp_search_term.py
---

# 列映射

标定来源：赛狐 SP 搜索词导出（壳 PoC 同款 `adSearchTermReport`）。  
窗口：`SELLFOX_WINDOW_MODE=aggregate`（整窗一行一词可再 groupby）。

| 优化器期望 | 赛狐 xlsx 列 | 备注 |
|------------|--------------|------|
| `query` | `用户搜索词` | 必填 |
| `cost` | `广告花费` | |
| `clicks` | `广告点击量` | |
| `orders` | `广告订单量` | **窗口定义可能与领星「7天归因」不完全同构** — 见 deviations |
| `sales` | `广告销售额` | |
| `impressions` | `广告曝光量` | 可选 |
| `campaign_id` | `广告活动ID` | |
| `ad_group_id` | `广告组ID` | |
| `match_type` | `匹配类型` | |
| `campaign_name` | `广告活动` | 可选展示 |
| `report_date` | `日期` | aggregate 模式可保留日行或再聚合 |

ingest 输出规范化行应使用**英文 key**（上表左列），供 `lingxing_optimizer` 的 `_agg` 消费。
