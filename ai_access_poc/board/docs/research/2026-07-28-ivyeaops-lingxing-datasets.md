---
okf: v0.1
type: Research
title: IvyeaOps 领星 READ_DATASETS 完整清单
description: 以代码为准穷尽 IvyeaOps-sellfox 领星数据集、optimizer 五杠杆依赖、operate 读前置
tags: [ivyeaops, lingxing, read-datasets, optimizer]
timestamp: 2026-07-28
sources:
  - ../../../../../IvyeaOps-sellfox/server/app/services/lingxing_data.py
  - ../../../../../IvyeaOps-sellfox/server/app/services/lingxing_optimizer.py
  - ../../../../../IvyeaOps-sellfox/server/app/services/lingxing_operate.py
---

# IvyeaOps 领星 READ_DATASETS 完整清单

> 代码真理：`d:\Work\赛狐\IvyeaOps-sellfox`（不依赖 DeepWiki）。本文件回答「IvyeaOps 到底用了哪些领星数据」。

## 架构

- 注册表：`lingxing_data.READ_DATASETS`（**12** 个 key）
- 统一读：`fetch_dataset()` → 领星 OpenAPI（PoC 下部分改赛狐）
- 优化器：`lingxing_optimizer.run_store()` 五杠杆
- 写：`lingxing_operate` 工单；`SELLFOX_READONLY_POC=1` 时写硬禁

## READ_DATASETS 全表

| dataset_key | label | route | method | optimizer? | operate读前置? | 杠杆相关? |
|-------------|-------|-------|--------|------------|----------------|-----------|
| `sellers` | 店铺列表 | `/erp/sc/data/seller/lists` | GET | 否 | 否 | 否 |
| `fba_stock` | FBA 库存 | `/erp/sc/routing/fba/fbaStock/fbaList` | POST | 否 | 否 | 否 |
| `sp_campaigns` | SP 广告活动 | `/pb/openapi/newad/spCampaigns` | POST | **是**（日预算） | **是** | **加预算** |
| `sp_adgroups` | SP 广告组 | `/pb/openapi/newad/spAdGroups` | POST | 否 | **是**（默认竞价） | 否（写路径） |
| `sp_keywords` | SP 关键词 | `/pb/openapi/newad/spKeywords` | POST | **是**（bid/state） | **是** | **降/加 bid** |
| `sp_targets` | SP 定向 | `/pb/openapi/newad/spTargets` | POST | 否 | **是** | 否（写路径） |
| `sp_campaign_report` | SP 活动报表 | `/pb/openapi/newad/spCampaignReports` | POST | **是** | 否 | **加预算** |
| `sp_product_ads` | SP 投放商品 | `/pb/openapi/newad/spProductAds` | POST | **是**（campaign→ASIN） | 否 | 目标 ACOS 辅助 |
| `sp_keyword_report` | SP 关键词报表 | `/pb/openapi/newad/spKeywordReports` | POST | **是** | 否 | **降/加 bid** |
| `sp_target_report` | SP 定向报表 | `/pb/openapi/newad/spTargetReports` | POST | 否 | 否 | 否（已注册未消费） |
| `sp_search_term_report` | SP 搜索词报表 | `/pb/openapi/newad/queryWordReports` | POST | **是** | 否 | **否词/收割** |
| `asin_profit` | ASIN 利润 | `/bd/profit/statistics/open/asin/list` | POST | **是**（grossRate） | 否 | 目标 ACOS 辅助 |

### 两类数据（重要）

| 类型 | dataset 例子 | 回答什么 |
|------|-------------|----------|
| **表现报表** | `sp_*_report`、`sp_search_term_report` | 窗口内花费/点击/订单 |
| **实体配置** | `sp_keywords`、`sp_campaigns`、`sp_product_ads` | **当前** bid / 日预算 / ASIN 绑定 |

降 bid、加预算 = **报表 + 实体** 一起用，缺一不可。

## Optimizer 五杠杆 → dataset

| 杠杆 | 直接依赖 | 共用辅助 |
|------|----------|----------|
| 否词 | `sp_search_term_report` | `asin_profit` + `sp_product_ads` |
| 收割 | `sp_search_term_report` | 同上 |
| 降 bid | `sp_keyword_report` + `sp_keywords` | 同上 |
| 加 bid | `sp_keyword_report` + `sp_keywords` | 同上 |
| 加预算 | `sp_campaign_report` + `sp_campaigns` | 同上 |

**未消费**：`sellers`、`fba_stock`、`sp_adgroups`、`sp_targets`、`sp_target_report`（注册给浏览/写工单用）。

## asin_profit 专节

- 字段：`asin`, `grossProfit`, `grossRate`, …
- 用途：`target_acos ≈ factor × margin`（默认 factor 0.7）；无数据则默认 30%
- 赛狐对照：见 [赛狐全量目录映射](2026-07-28-sellfox-ad-catalog-map.md)；`monthProfit/asin` 已含 `grossProfitRate`（2026-07-28 重测 OK）

## 公开领星路由交叉

SP 核心九路由（实体 5 + 报表 4 含 queryWord）在 READ_DATASETS **均可找到**。  
常见但本仓未注册：广告组报表、广告位报表、小时级、SB/SD、Listing（optimizer 不用）。

公开镜像（绕过官网密码）：[zach22-1999/lingxing-mcp](https://github.com/zach22-1999/lingxing-mcp)、LinkFox lingxing-erp skill 报表清单。

## 相关

- 缺口矩阵（白话）：[../specs/phase2-dataset-gap.md](../specs/phase2-dataset-gap.md)
- 赛狐全量目录：[2026-07-28-sellfox-ad-catalog-map.md](2026-07-28-sellfox-ad-catalog-map.md)
