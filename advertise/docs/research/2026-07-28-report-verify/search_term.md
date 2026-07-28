---
okf: v0.1
type: Research
title: 验证 — search_term
description: 独立验证 search_term 列对账与 analyze
tags: [sellfox, verify]
timestamp: 2026-07-28
---

# 验证 — search_term

- **文件**: `advertise\data\SearchTerm_BJRYECLTD-US_2026-06-28_2026-07-27.xlsx`
- **行数**: 1226；原始列 32；映射后 32
- **verdict**: PASS

## 列对账

- missing vs `column_maps.py`: 无
- unexpected: 无
- 全空映射列: 无

## 实际表头

```
店铺
日期
用户搜索词
投放
匹配类型
广告活动
广告组
定位类型
广告花费
广告曝光量
广告点击量
CPC
广告点击率
广告转化率
ACoS
ROAS
广告订单量
本广告产品订单量
其他产品广告订单量
广告销售额
本广告产品销售额
其他产品广告销售额
广告销量
本广告产品销量
其他产品广告销量
广告组合名称
币种
广告活动开始时间
广告活动结束时间
广告活动ID
广告组ID
广告投放ID
```

## 关键指标样例（映射后）

```json
{
  "spend": {
    "sum": 1494.1599999999999,
    "null_pct": 0.0,
    "non_null": 1226
  },
  "sales": {
    "sum": 5064.7300000000005,
    "null_pct": 0.0,
    "non_null": 1226
  },
  "orders": {
    "sum": 25.0,
    "null_pct": 0.0,
    "non_null": 1226
  },
  "clicks": {
    "sum": 1731.0,
    "null_pct": 0.0,
    "non_null": 1226
  },
  "impressions": {
    "sum": 67862.0,
    "null_pct": 0.0,
    "non_null": 1226
  }
}
```

## analyze 复跑

```json
{
  "ran": true,
  "ok": true,
  "error": null,
  "keys": [
    "summary",
    "harvest_keywords",
    "negative_candidates",
    "monitor_list",
    "protect_list",
    "category_distribution",
    "strategic_tiers",
    "thresholds"
  ],
  "out": "advertise\\out\\verify_2026-07-28\\search_term_analysis.json"
}
```
