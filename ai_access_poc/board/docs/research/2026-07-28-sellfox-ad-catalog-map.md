---
okf: v0.1
type: Research
title: 赛狐广告/财务只读全量目录 × IvyeaOps 映射
description: 不限 SP7：下载中心 reportTypeCode、小时报告、manageData、利润 V2，与 READ_DATASETS 候选映射
tags: [sellfox, catalog, mapping, ivyeaops]
timestamp: 2026-07-28
---

# 赛狐广告/财务只读全量目录 × IvyeaOps 映射

> 回答：「不只有 7 表；赛狐还能拿什么；能否顶领星 READ_DATASETS」。  
> 文档源：`SELLFOX_API/docs`（已爬取）。利润权限 **2026-07-28 重测已通**。

## 1. 天维度下载中心（10 种 reportTypeCode）

任务：`/api/cpc/download/createTask.json` + `pageList.json`

| reportTypeCode | 中文 | adType | SP7 验证 | → IvyeaOps |
|----------------|------|--------|----------|------------|
| `adCampaignReport` | 广告活动 | sp/sb/sd | ✅ | `sp_campaign_report` |
| `adGroupReport` | 广告组 | sp/sb/sd | ✅ | （优化器非必需） |
| `adProductReport` | 广告产品 | sp/sb/sd | ✅ | `sp_product_ads`（报表侧） |
| `adSpaceReport` | 广告位 | sp/sb | ✅ | （非必需） |
| `adTargeringReport` | 投放 | sp/sb（sd 不用） | ✅ | `sp_keyword_report` / `sp_target_report`（需行过滤） |
| `adSearchTermReport` | 搜索词 | sp/sb | ✅ | `sp_search_term_report` **已接线** |
| `adPurchasedItemReport` | 已购商品 | sp/sb/sd | ✅ | （非必需） |
| `amazonBusinessReport` | 企业购广告位 | sp | 未本轮拉 | — |
| `adCampaignMatchedTargetReport` | 匹配目标 | sd | 未本轮拉 | — |
| `sdTargetListReport` | SD 投放 | sd | 未本轮拉 | SD 定向报表 |

## 2. 小时维度（13 端点）

前缀 `/api/cpc/hourData/`：`spCampaign/spGroup/spAdProduct/spPlacement/spTarget` + SB/SD 对应。  
IvyeaOps READ_DATASETS：**无对等键**（领星也未注册小时级）。状态：**能力存在，优化器不用**。

## 3. 基础数据 manageData（21 端点，只读分页）

| Path | → IvyeaOps | 状态 |
|------|------------|------|
| `spCampaign.json` | `sp_campaigns`（`budget`→`daily_budget`） | **源已验证可映射未接线** |
| `spKeyword.json` | `sp_keywords`（`bid`/`state`） | **源已验证可映射未接线** |
| `spAdProduct.json` | `sp_product_ads` | **源已验证可映射未接线** |
| `spGroup.json` | `sp_adgroups` | 文档对齐；优化器不直接消费 |
| `spTarget.json` | `sp_targets` | 文档对齐；operate 写前置用 |
| `spNeKeyword.json` / `spNeTarget.json` | — | 只读否词实体 |
| SB/SD 全套 `sb*` / `sd*` | — | IvyeaOps 当前仅 SP |
| `portfolio.json` | — | 广告组合 |

误路径：`spProductAd.json` → 应用 `spAdProduct.json`。

## 4. 财务利润（asin_profit）

| Path | 2026-07-28 重测 | 字段 |
|------|-----------------|------|
| `/api/financial/v2/monthProfit/asin.json` | **OK**（`totalSize=13` 样例店） | 含 `grossProfit`、`grossProfitRate`、`asinList` |
| `/api/financial/v2/dailyProfit/asin.json` | **OK** | 日结算利润 |
| `monthProfit/msku.json` | **OK** | MSKU 粒度 |

**Caveat**：成本未落地时毛利可能不准；领星同样用利润推目标 ACOS——可用，但须标注「数据可能滞后/不准」，或 hub `lingxing_margin_override`。

另有：parentAsin/sku/spu/shop、广告发票 V2、旧版即将下线接口（勿新接）。

## 5. 其它只读

| 能力 | Path | 备注 |
|------|------|------|
| 店铺列表 | `/api/shop/pageList.json` | → `sellers`（已接线 PoC） |
| FBA 库存 | `/api/inventoryManage/fba/pageList.json` | → `fba_stock` 候选 |
| ABA 搜索词 | `/api/cpc/searchTerms/pageList.json` | 非优化器 |
| 报告中心 Amazon 原表 / 插件 | `/api/report/center/*` | SP-API/插件源报告通道；去年项目有记录，非优化器主路径 |

## 6. READ_DATASETS 总映射（四态）

| IvyeaOps | 赛狐源 | 状态 |
|----------|--------|------|
| `sellers` | `shop/pageList` | **已接线** |
| `sp_search_term_report` | `adSearchTermReport` | **已接线** |
| `sp_keyword_report` | `adTargeringReport`（过滤关键词行） | **需拼表或过滤** |
| `sp_keywords` | `manageData/spKeyword` | **源已验证可映射未接线** |
| `sp_campaign_report` | `adCampaignReport` | **源已验证可映射未接线** |
| `sp_campaigns` | `manageData/spCampaign` | **源已验证可映射未接线** |
| `sp_product_ads` | `adProductReport` 或 `spAdProduct` | **源已验证可映射未接线** |
| `asin_profit` | `monthProfit/asin`（`grossProfitRate`→`grossRate`） | **源已验证可映射未接线**（权限已通；数值 caveat） |
| `sp_target_report` | Targeting 定向行 / `sdTargetListReport` | **需拼表或过滤**（优化器未消费） |
| `sp_targets` / `sp_adgroups` | `spTarget` / `spGroup` | **源已验证可映射未接线**（写前置） |
| `fba_stock` | FBA pageList | **权限或文档未证伪**（未本轮实拉） |

**结论（阶段性）**：赛狐 **不是**「顶替不了领星」。优化器必需的 SP 数据在赛狐侧均有对等源（报表和/或实体）；缺口是 **PoC ingest 未接** + 归因/拼表规则，不是能力真空。SB/SD/小时/ABA/原表为扩展面。

## 7. 历史记录索引

- `advertise/docs/lessons/2026-06-25-sellfox-integration-lessons.md`（勿「赛狐不够加领星」；可考虑 SP-API）
- `advertise/docs/reference/data-sources.md`（Amazon Ads 报告生态）
- `SELLFOX_API/docs/api-reference/报告中心/`（插件/原表）
- 领星侧清单：[2026-07-28-ivyeaops-lingxing-datasets.md](2026-07-28-ivyeaops-lingxing-datasets.md)

## 相关

- [phase2-dataset-gap.md](../specs/phase2-dataset-gap.md)
- SP7 验证包：`advertise/docs/research/2026-07-28-report-verify/`
