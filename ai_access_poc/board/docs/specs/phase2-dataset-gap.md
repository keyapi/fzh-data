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

## 五杠杆 ≠ 五桶（易混）

| 名称 | 出处 | 是什么 |
|------|------|--------|
| **五杠杆** | IvyeaOps `lingxing_optimizer` | 对广告的五类**动作候选**：否词、收割、降 bid、加 bid、加预算 |
| **五桶** | `advertise` 搜索词分析（约 2026-07） | 对搜索词的五类**标签**：Harvest / Negate / Monitor / Protect / Ignore |

二者相关（Harvest↔收割、Negate↔否词）但**不是同一套体系**。详见根目录 `CONCEPTS.md`。

## 先读这段（纠正误解）

**本表不是说「赛狐提供不了领星那种 Amazon 数据」。**

领星和赛狐都是 Amazon 广告/经营数据的中介，本质同源。差异主要在：

1. **API 形状**：领星多为按日 JSON；赛狐多为「下载中心 xlsx」+「基础数据 manageData」。
2. **PoC 接了多少（2026-07-28）**：READ_DATASETS **12/12** 已接线且对齐原生 **按需拉取**（`fetch_dataset` → `ensure_dataset`）；离线 `ingest_sellfox_phase2.ps1` 仅可选预热。写路径仍禁。
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
| `sp_search_term_report` | 否词 / 收割 | `adSearchTermReport` | **已接线** | Phase2 ingest；1226 行 |
| `sp_keyword_report` | 降/加 bid（表现） | `adTargeringReport` | **已接线** | 1176→1034 关键词行（跳过非关键词 142）；`广告投放ID`→`keyword_id` |
| `sp_keywords` | 降/加 bid（当前竞价） | `manageData/spKeyword.json` | **已接线** | 611 行 `bid/state` |
| `sp_campaign_report` | 加预算（花费） | `adCampaignReport` | **已接线** | 291 行 |
| `sp_campaigns` | 加预算（日预算） | `manageData/spCampaign.json` | **已接线** | 94 行 `budget`→`daily_budget` |
| `sp_product_ads` | campaign→ASIN | `spAdProduct.json` | **已接线** | 277 行实体 |
| `asin_profit` | 目标 ACOS | `monthProfit/asin.json` | **已接线** | 24 行；`reportList`→`grossRate`；毛利率 caveat 仍在 |
| Placement / PurchasedItem / AdGroup | 非五杠杆必需 | 下载中心对应报表 | 辅助（advertise 侧） | SP7 验证 PASS |

## 实体 API 探测摘要（Proxy，只读）

| endpoint | 结果 | 映射 |
|----------|------|------|
| `spKeyword.json` | OK | → `sp_keywords` |
| `spCampaign.json` | OK | `budget` → `daily_budget` |
| `spAdProduct.json` | OK | → `sp_product_ads` |
| `spProductAd.json` | 错路径 | 应用 `spAdProduct.json` |
| `monthProfit/asin.json` | **OK（2026-07-28 重测）** | `reportList` + `grossProfitRate` → `grossRate` |

## 实现入口（2026-07-28）

- IvyeaOps：`sellfox_ingest.py` + `fetch_dataset` PoC 分支  
- fzh-data：`ai_access_poc/board/scripts/ingest_sellfox_phase2.ps1`  
- 标定店冒烟：`run_store(596841)` → 候选 35（否词 15 / 收割 2 / 降bid 17 / 加bid 1；加预算视阈值可能为 0）  
- 计划：`docs/superpowers/plans/2026-07-28-phase2-sellfox-ingest.md`

## 与 D3

[`deviations.md`](../reference/deviations.md) D3：报表+实体 **已 ingest**；写路径仍禁。

**煮湖续篇（不限 7 表）**：

- 领星侧：[2026-07-28-ivyeaops-lingxing-datasets.md](../research/2026-07-28-ivyeaops-lingxing-datasets.md)
- 赛狐全量目录：[2026-07-28-sellfox-ad-catalog-map.md](../research/2026-07-28-sellfox-ad-catalog-map.md)
