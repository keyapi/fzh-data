---
okf: v0.1
type: Research
title: 杠杆关键字段释义与归因窗口 D1
description: 赛狐中文表头 ↔ Amazon 官方含义；D1 归因窗口对否词/收割的影响
tags: [sellfox, amazon-ads, attribution, field-definitions]
timestamp: 2026-07-28
sources:
  - advertise/docs/reference/amazon-official-docs/field-definitions-quick-reference.md
  - advertise/docs/reference/sp-report-column-reference.md
  - https://m.media-amazon.com/images/G/28/AS/AGS/SU/CN_GS_Ads_3.5_Performance_Reporting_EN.pdf
---

# 杠杆关键字段释义与归因窗口 D1

## 关键字段（无猜）

| 赛狐列名 | advertise 映射 | IvyeaOps 统一键 | 含义 |
|----------|----------------|-----------------|------|
| 广告花费 | `spend` | `cost`（ingest 须 rename） | 广告花费；ACOS 分子 |
| 广告销售额 | `sales` | `sales` | 归因期内广告带来的销售额；ACOS 分母 |
| 广告点击量 | `clicks` | `clicks` | 点击次数；否词阈值常用「高点击 0 单」 |
| 广告订单量 | `orders` | `orders` | 归因订单数；收割阈值「≥N 单」 |
| 广告曝光量 | `impressions` | `impressions` | 曝光 |
| 用户搜索词 | `search_term` | `query` | 顾客实际搜索词（至少 1 次点击才出现在报告） |
| 投放 | `targeting` | （关键词文本侧） | 触发广告的投放关键词/定向 |
| 匹配类型 | `match_type` | `match_type` | 精确/词组/广泛等 |
| 广告活动ID | `campaign_id` | `campaign_id` | 活动主键 |
| 广告组ID | `ad_group_id` | `ad_group_id` | 广告组主键 |
| 广告投放ID | `target_id` | 关键词行上 **= `keyword_id`** | 投放实体 ID；对关键词匹配类型行与 `spKeyword.keywordId` 一致（已交叉验证）；商品定向行勿当 keyword_id；bid 仍须实体 API |
| ACoS | `acos` | 派生 `cost/sales` | Advertising Cost of Sales = 花费/销售额 |
| ROAS | `roas` | 派生 | 销售额/花费 |
| （实体）bid | — | `bid` | 当前关键词竞价（`spKeyword.json`） |
| （实体）budget | — | `daily_budget` | 活动日预算（`spCampaign.json` 的 `budget`） |
| （财务）毛利率 | — | `grossRate` | 本账号 **无权限**；目标 ACOS = factor × margin |

公式：

- **ACOS** = 广告花费 ÷ 广告销售额（官方定义，百分比时常 ×100）  
- **目标 ACOS（IvyeaOps）** = `lingxing_target_acos_factor` × 毛利率；无毛利时默认 30%

## D1 归因窗口专项

| 系统 | 行为 | 风险 |
|------|------|------|
| Amazon SP（官方惯例） | 点击后约 **7 天**归因窗；近 1–2 日订单可能回填 | 用「昨天」数据否词易误杀 |
| IvyeaOps 领星原生 | 按日拉窗，并 **排除近 2 天**（`_window_dates`） | 故意避开未成熟归因 |
| 赛狐 PoC aggregate | 一次下载整窗 daily 行再 sum（本轮 30 天） | 与领星「逐日 API」路径不同，但同窗合计可近似；**近端日期仍含未成熟归因** |

**运营含义**：否词/收割阈值沿用 IvyeaOps 默认前，应用「排除最近 2–3 天」或接受 D1 偏差；不得把候选当自动执行依据（运营审仍 DEFERRED）。

## 本轮实拉对账要点

- Campaign 报表 **无预算列** → 加预算必须配 `spCampaign.json`。  
- Targeting 是 **投放报告** 而非 Amazon 独立 Keyword Report；降/加 bid 的 `keyword_id` 不能默认 = `广告投放ID`。  
- SearchTerm 的 `广告活动结束时间` 可出现中文占位「无结束日期」→ analyze 须 `errors="coerce"`（已修）。

## 参考

- 项目内：`advertise/docs/reference/sp-report-column-reference.md`  
- 项目内：`advertise/docs/reference/amazon-official-docs/field-definitions-quick-reference.md`  
- 缺口矩阵：[`phase2-dataset-gap.md`](../../../ai_access_poc/board/docs/specs/phase2-dataset-gap.md)
