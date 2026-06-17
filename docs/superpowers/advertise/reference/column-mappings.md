# 列名映射参考

> 何时读: 需要了解 Amazon 中文后台导出 → 英文标准字段名的完整映射。
> 入口: `advertise/__init__.py` 中的 `CAMPAIGN_COLUMN_MAP` / `TARGETING_COLUMN_MAP` / `SEARCH_TERM_COLUMN_MAP` / `PLACEMENT_COLUMN_MAP`

## 广告活动报告 (25 列, CSV)

| 中文 | 英文 | 说明 |
|------|------|------|
| 开始日期 | start_date | |
| 结束日期 | end_date | |
| 广告组合名称 | portfolio_name | Portfolio 分组 |
| 广告活动类型 | campaign_type | 商品推广 |
| 广告活动名称 | campaign_name | |
| 零售商 | retailer | Amazon |
| 国家/地区 | country | |
| 状态 | status | ENABLED/PAUSED |
| 货币 | currency | USD |
| 预算 | budget | 日预算，带 `$` 前缀 |
| 定位类型 | targeting_type | 自动投放/手动投放 |
| 竞价策略 | bidding_strategy | 固定/动态 |
| 展示量 | impressions | |
| 去年曝光量 | impressions_dedup | 去重展示量（列名编码错位） |
| 点击量 | clicks | |
| 去年点击量 | clicks_dedup | 去重点击量 |
| 点击率 (CTR) | ctr | |
| 花费 | spend | 带 `$` 前缀 |
| 去年支出 | spend_dedup | 去重花费 |
| 单次点击成本 (CPC) | cpc | 带 `$` 前缀 |
| 去年每次点击成本(CPC) | cpc_dedup | 去重 CPC |
| 7天总订单数(#) | orders_7d | |
| 广告投入产出比 (ACOS) 总计 | acos | |
| 总广告投资回报率 (ROAS) | roas | |
| 7天总销售额 | sales_7d | 带 `$` 前缀 |

## 投放报告 (26 列, XLSX)

| 中文 | 英文 | 说明 |
|------|------|------|
| 开始日期 | start_date | |
| 结束日期 | end_date | |
| 广告组合名称 | portfolio_name | |
| 货币 | currency | |
| 广告活动名称 | campaign_name | |
| 国家/地区 | country | |
| 广告组名称 | ad_group_name | |
| 零售商 | retailer | |
| 投放 | targeting | 投放关键词/商品 ASIN |
| 匹配类型 | match_type | Broad/Phrase/Exact |
| 展示量 | impressions | |
| 搜索结果首页首位展示量份额 | top_search_is | |
| 点击量 | clicks | |
| 点击率 (CTR) | ctr | |
| 单次点击成本 (CPC) | cpc | |
| 花费 | spend | |
| 广告投入产出比 (ACOS) 总计 | acos | |
| 总广告投资回报率 (ROAS) | roas | |
| 7天总销售额 | sales_7d | |
| 7天总订单数(#) | orders_7d | |
| 7天总销售量(#) | units_7d | |
| 7天的转化率 | conversion_rate_7d | |
| 7天内广告SKU销售量(#) | advertised_sku_units_7d | |
| 7天内其他SKU销售量(#) | other_sku_units_7d | |
| 7天内广告SKU销售额 | advertised_sku_sales_7d | |
| 7天内其他SKU销售额 | other_sku_sales_7d | |

## 搜索词报告 (26 列, XLSX)

与投放报告结构相同，仅多了这一列：

| 中文 | 英文 | 说明 |
|------|------|------|
| 客户搜索词 | search_term | 买家实际输入的搜索词 |

## 广告位报告 (18 列, XLSX)

| 中文 | 英文 | 分类 |
|------|------|------|
| 放置 | placement | |
| 亚马逊站内的搜索结果顶部 | → Top of Search | |
| 亚马逊站内的商品页面 | → Product Pages | |
| 亚马逊站内搜索结果的其余位置 | → Rest of Search | |
| 亚马逊站外 | → 站外 | |

## 已知坑

1. **CSV 金额列带 `$` 前缀**: `__init__.py` 做 `str.replace(r"[$,\s]", "", regex=True)` 清洗
2. **百分比可能以整数返回**（30 = 30%）: 自动除以 100
3. **去重列名编码错位**: "去年"开头的列实际是"去重"列
4. **搜索词匹配类型显示 `-`**: 自动广告的 Close/Loose/Substitutes/Complements 在中文后台显示为空

## See also
- [数据源全图](data-sources.md)
- [调研报告](../research/2026-06-16-amazon-advertising-analysis-research.md)
- [`advertise/__init__.py`](../../../advertise/__init__.py)
