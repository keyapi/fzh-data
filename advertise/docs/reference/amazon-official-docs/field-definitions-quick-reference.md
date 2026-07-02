---
okf: v0.1
type: Reference
title: SP 广告报告字段定义速查表
description: 从多个权威来源提取的 SP 字段精确定义
created: 2026-07-02
sources:
  - Supermetrics Amazon Ads Fields (docs.supermetrics.com)
  - Two Minute Reports (twominutereports.com)
  - Openbridge Attribution Metrics (docs.openbridge.com)
---

# SP 广告报告字段定义速查表

## 字段完整定义 (按类别)

### 流量指标 (Traffic Metrics)

| 字段名 (API v3) | 赛狐中文名 | 精确定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `impressions` | 广告曝光量 | "The number of times ads were displayed." 广告每次在页面上渲染一次计数为 1，同一用户多次看到也多次计数。 | int.number.value | Supermetrics |
| `clicks` | 广告点击量 | "The number of times your ads were clicked." 每次用户点击广告计为 1 次点击，同一用户多次点击也多次计数。 | int.number.value | Supermetrics |
| `cost` | 广告花费 | "Total cost of all clicks. Can be divided by clicks to obtain average CPC." 所有点击的 CPC 之和，以当地货币计价。注意：API 字段名为 `cost` 而非 `spend`。 | float.currency.value | Supermetrics |
| `costPerClick` (CPC) | CPC | "Cost per click, spend divided by the number of clicks. CPC = Spend / Clicks." 广告主为每次点击支付的平均金额。 | float.currency.value | Supermetrics |
| `clickThroughRate` (CTR) | 广告点击率 | "Click through rate, clicks divided by impressions." 广告展示后用户实际点击的概率。CTR = Clicks / Impressions。 | float.number.percentage | Supermetrics |
| `viewImpressions` | 可见展示次数 | "Estimated impressions meeting MRC viewability standards." 至少 50% 的广告像素在可视区域持续至少 1 秒的展示。仅 vCPM 广告类型相关。 | float.currency.value | Supermetrics |

### 转化指标 (Conversion Metrics)

| 字段名 (API v3) | 赛狐中文名 | 精确定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `purchases7d` | 广告订单量 | "Number of Amazon orders attributed to ads within 7 days of a click." 买家点击广告后 7 天内下的订单数。包括所有归因订单，不管购买的是广告商品还是其他商品。 | int.number.value | Supermetrics + Openbridge |
| `attributedConversions7dSameSKU` | 本广告产品订单量 | "Attributed conversions where purchased SKU matched advertised SKU." 仅统计购买商品=广告商品的订单。 | int.number.value | Supermetrics + Openbridge |
| `attributedConversions7dOtherSKU` | 其他产品广告订单量 | Orders where purchased SKU differed from advertised SKU. 购买商品!=广告商品的订单。 | int.number.value | [推断] |
| `sales7d` | 广告销售额 | "Total sale amount resulting from an ad click within 7 days." 归因订单中所有商品的售价总和。 | float.currency.value | Supermetrics + Openbridge |
| `attributedSales7dSameSKU` | 本广告产品销售额 | "Total sale amount counting only the advertised product's revenue." 仅计算广告商品自身的售价金额。 | float.currency.value | Openbridge |
| `attributedSales7dOtherSKU` | 其他产品广告销售额 | Total sale amount for products different from the advertised SKU within 7 days. 非广告商品的售价金额 (品牌光环)。 | float.currency.value | Openbridge |
| `unitsSoldClicks7d` | 广告销量 | "Total number of individual units ordered across all sales from a conversion." 归因订单中所有商品的总件数。 | int.number.value | Openbridge |
| `attributedUnitsOrdered7dSameSKU` | 本广告产品销量 | "Counts only those units that are the advertised ASIN from the conversion." 仅广告商品自身的销售件数。 | int.number.value | Openbridge |
| `attributedUnitsOrdered7dOtherSKU` | 其他产品广告销量 | "Counts units that are different from the advertised ASIN." 也称为 "品牌光环" (Brand Halo)。非广告商品的销售件数。 | int.number.value | Openbridge |

### 效率指标 (Efficiency Metrics)

| 字段名 (API v3) | 赛狐中文名 | 精确定义 | 公式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `acos7d` | ACoS | "Advertising cost of sales. Spend / Sales * 100." 广告花费占广告带来销售额的百分比。衡量广告支出的销售效率。 | (cost / sales7d) * 100 | float.number.percentage | Supermetrics |
| `roas7d` | ROAS | "Return On Ad Spend. Sales / Spend." 每花 1 美元广告费带来的销售额。ROAS = 1 / (ACoS/100)。 | sales7d / cost | float.number.ratio | Supermetrics |
| `conversionRate7d` | 广告转化率 | "Conversion rate. Orders / Clicks * 100." 点击广告后实际产生购买的概率。 | (purchases7d / clicks) * 100 | float.number.percentage | Supermetrics |

### 维度字段 (Dimensions)

| 字段名 (API v3) | 赛狐中文名 | 精确定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `date` | 日期 | 数据日期。格式: YYYY-MM-DD。时区取决于 profile 设置。 | DATE | Amazon API |
| `campaignName` | 广告活动 | "Advertiser created campaign name." 广告主自己设置的活动名称。 | string.text.value | Supermetrics |
| `campaignId` | 广告活动ID | "Unique campaign ID." 数字字符串。 | string.text.value | Supermetrics |
| `campaignStatus` | 广告活动运行状态 | "Campaign's current status represents user action." 可能值: ENABLED (已开启), PAUSED (已暂停), ARCHIVED (已归档)。 | string.text.value | Supermetrics |
| `campaignBudgetType` | 预算类型 | "One of 'daily' or 'lifetime'." | string.text.value | Supermetrics |
| `campaignBudget` | 预算 | "The campaign budget." 广告活动日预算金额。 | float | Supermetrics |
| `campaignTargetingType` | 定位类型 | "For Sponsored Products, one of Manual, Auto." | string.text.value | Two Minute Reports |
| `campaignBiddingStrategy` | 竞价策略 | "For Sponsored Products and Sponsored Display only." 竞价策略: 固定出价/动态出价 (只降低/提高和降低)。 | string.text.value | Supermetrics |
| `startDate` | 广告活动开始时间 | "Start date of the campaign." | DATE | Supermetrics |
| `endDate` | 广告活动结束时间 | "End date of the campaign." 无结束日期时显示为 "无结束日期" 或 null。 | DATE | Supermetrics |
| `adGroupName` | 广告组 | "Name of the ad group." 广告主设置的广告组名称。 | string.text.value | Supermetrics |
| `adGroupId` | 广告组ID | "Unique ad group ID." | string.text.value | Supermetrics |
| `adGroupStatus` | 广告组运行状态 | "State of the ad group." ENABLED/PAUSED/ARCHIVED。 | string.text.value | Supermetrics |
| `portfolioName` | 广告组合名称 | Portfolio 名称。广告组合是广告活动的逻辑分组。 | string.text.value | Two Minute Reports |
| `portfolioId` | 广告组合ID | Portfolio 唯一标识。 | string.text.value | Two Minute Reports |
| `currency` | 币种 | 货币代码 (如 USD)。对应 marketplace profile 的货币设置。 | string.text.value | Supermetrics |
| `asin` | ASIN | Amazon Standard Identification Number。Amazon 标准识别码，10 位字母数字。 | string.text.value | Scaleleap |
| `sku` | SKU | Stock Keeping Unit。卖家自定义的库存单位编码。Vendor 账号不可用。 | string.text.value | Scaleleap |
| `targeting` | 投放 | 投放的目标关键词文本 (手动广告) 或自动投放类型名称 (如"紧密匹配")。 | string.text.value | Amazon API |
| `matchType` | 匹配类型 | 关键词匹配类型: BROAD (广泛匹配), PHRASE (词组匹配), EXACT (精确匹配)。自动广告还可能有: CLOSE_MATCH, LOOSE_MATCH, SUBSTITUTES, COMPLEMENTS。 | string.text.value | Two Minute Reports |
| `searchTerm` | 用户搜索词 | "The search term used by the customer." 买家在 Amazon 搜索框中实际输入的内容。注意区分 searchTerm (用户输入) 和 keyword (卖家投放)。 | string.text.value | Two Minute Reports |
| `placement` | 广告位 | "The page location where an ad appeared." SP 取值: Top of Search (搜索结果顶部首页), Product Pages (产品页面), Rest of Search (搜索结果的其余位置)。 | string.text.value | Two Minute Reports |
| `purchasedAsin` | 其他ASIN (已购) | "A non-dimensional metric for ASINs other than the one advertised." 实际被购买的 ASIN (可能与广告 ASIN 不同)。 | string.text.value | Scaleleap |
| `advertisedAsin` | 广告ASIN | 被点击的广告商品的 ASIN。 | string.text.value | Scaleleap |

---

## 归因窗口对比

| 窗口 | API 后缀 | SP Sellers | SP Vendors |
|------|----------|------------|------------|
| 1 天 | `1d` | API only | API only |
| 7 天 | `7d` | **Console 默认** | API only |
| 14 天 | `14d` | API only | **Console 默认** |
| 30 天 | `30d` | API only | API only |

---

## SameSKU / OtherSKU / Total 关系

```
Total = SameSKU + OtherSKU

举例 (来自 Openbridge):
- 买家点击广告后购买了 2 个广告商品 ($12 each) + 1 个其他商品 ($12):
  - attributedSales7d = $36 (2*12 + 12)
  - attributedSales7dSameSKU = $24 (2*12)
  - attributedSales7dOtherSKU = $12
  - attributedUnitsOrdered7d = 3
  - attributedUnitsOrdered7dSameSKU = 2
  - attributedUnitsOrdered7dOtherSKU = 1
  - attributedConversions7d = 1 (这是一个订单)
```
