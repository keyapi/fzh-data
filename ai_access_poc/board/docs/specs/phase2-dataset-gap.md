---
okf: v0.1
type: Spec
title: Phase2 数据集缺口矩阵 — 赛狐只读 vs IvyeaOps 领星杠杆
description: 白话说明两类数据源 + PoC 接线状态；不是「赛狐没有 Amazon 数据」
tags: [phase2, sellfox, ivyeaops, gap-matrix]
timestamp: 2026-07-28
updated: 2026-07-28
---

# Phase2 数据集缺口矩阵

**标定店**: BJRYECLTD-US (`596841`)  
**报表窗**: 2026-06-28 ~ 2026-07-27（Proxy 重拉 SP7，7/7 成功）  
**写路径**: 仍硬禁（D6）  
**验证包**: [advertise/docs/research/2026-07-28-report-verify/](../../../advertise/docs/research/2026-07-28-report-verify/index.md)

## 先读这段（纠正误解）

**本表不是说「赛狐提供不了领星那种 Amazon 数据」。**

领星和赛狐都是 Amazon 广告/经营数据的中介，本质同源。差异主要在：

1. **API 形状**：领星多为按日 JSON；赛狐多为「下载中心 xlsx」+「基础数据 manageData」。
2. **PoC 接了多少**：目前 IvyeaOps-sellfox **只 ingest 了搜索词**；其它赛狐源多半已验证可映射，但**还没接到** `fetch_dataset`。
3. **两类数据不要混**：

| 类型 | 回答什么问题 | 例子 |
|------|--------------|------|
| **表现报表** | 这段时间花了多少、点了多少、出了几单 | 搜索词/投放/活动报告里的花费、点击、订单 |
| **实体配置** | **现在**竞价多少、开没开、日预算多少 | `spKeyword.json` 的 `bid`/`state`；`spCampaign.json` 的 `budget` |

表现报表**本来就不会**带「当前竞价 / 日预算」——不是赛狐缺列，领星的关键词**报表**同样不替代关键词**实体**列表。降/加 bid、加预算必须 **报表 + 实体** 两份一起用。

### 词义速查

| 词 | 人话 |
|----|------|
| `keyword_id` | 关键词主键。投放报表「广告投放ID」在关键词行上可当它用；商品定向行要过滤。 |
| `bid` / `state` | 当前竞价、开启/暂停。在实体 API，不在表现报表表头。赛狐已测到。 |
| 日预算 | 活动每天预算上限。在实体 `budget`，不在 Campaign 表现报表。赛狐已测到。 |

### 四态（以后只用这四个，避免「不能顶替」误读）

| 状态 | 含义 |
|------|------|
| **已接线** | PoC/`fetch_dataset` 已从赛狐读到并喂给优化器 |
| **源已验证可映射未接线** | 赛狐 API/xlsx 已冒烟，字段够用，差 ingest 代码 |
| **需拼表或过滤** | 有源，但要过滤行类型或报表+实体拼接 |
| **权限或文档未证伪** | 文档有接口，账号权限失败或尚未实拉证伪 |

---

## 优化器相关 dataset（SP7 轮次证据）

| IvyeaOps dataset | 杠杆 | 赛狐来源 | 状态 | 证据 |
|------------------|------|----------|------|------|
| `sp_search_term_report` | 否词 / 收割 | `adSearchTermReport` | **已接线** | PoC ingest；1226 行列对账+analyze PASS |
| `sp_keyword_report` | 降/加 bid（表现） | `adTargeringReport` | **需拼表或过滤** | 1176 行；关键词行 `广告投放ID`=`keywordId`（5/5）；过滤商品定向；无 bid/state |
| `sp_keywords` | 降/加 bid（当前竞价） | `manageData/spKeyword.json` | **源已验证可映射未接线** | 实测 `keywordId/bid/state`；`pageSize`∈[100,1000] |
| `sp_campaign_report` | 加预算（花费） | `adCampaignReport` | **源已验证可映射未接线** | 291 行花费/订单齐全；无预算列（预期） |
| `sp_campaigns` | 加预算（日预算） | `manageData/spCampaign.json` | **源已验证可映射未接线** | 实测 `budget`→`daily_budget` |
| `sp_product_ads` | campaign→ASIN | `adProductReport` 或 `spAdProduct.json` | **源已验证可映射未接线** | 报表 604 行；实体返回 `campaignId/asin/sku` |
| `asin_profit` | 目标 ACOS | `monthProfit/asin.json` | **源已验证可映射未接线** | **2026-07-28 重测 OK**（含 `grossProfit`/`grossProfitRate`）；映射 `grossProfitRate`→`grossRate`。Caveat：成本未落地时毛利可能不准 |
| Placement / PurchasedItem / AdGroup | 非五杠杆必需 | 下载中心对应报表 | 辅助（advertise 侧） | SP7 验证 PASS |

## 实体 API 探测摘要（Proxy，只读）

| endpoint | 结果 | 映射 |
|----------|------|------|
| `spKeyword.json` | OK | → `sp_keywords` |
| `spCampaign.json` | OK | `budget` → `daily_budget` |
| `spAdProduct.json` | OK | → `sp_product_ads` |
| `spProductAd.json` | 错路径 | 应用 `spAdProduct.json` |
| `monthProfit/asin.json` | **OK（2026-07-28 重测）** | `grossProfitRate` → `grossRate`；曾 40021 已解除 |

## 建议移植顺序（实现另开，本文件只调研）

1. Targeting ingest + `spKeyword` 实体 → 降/加 bid  
2. Campaign report + `spCampaign` 实体 → 加预算  
3. 利润权限通过或 hub margin override → 目标 ACOS  

## 与 D3

[`deviations.md`](../reference/deviations.md) D3：不是「赛狐拉不到」，是 **未 ingest + 实体未接线**。

**煮湖续篇（不限 7 表）**：

- 领星侧：[2026-07-28-ivyeaops-lingxing-datasets.md](../research/2026-07-28-ivyeaops-lingxing-datasets.md)
- 赛狐全量目录：[2026-07-28-sellfox-ad-catalog-map.md](../research/2026-07-28-sellfox-ad-catalog-map.md)
