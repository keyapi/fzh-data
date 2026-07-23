---
okf: v0.1
type: Research
title: 规则引擎 V1 — YAML 驱动路由
description: 可扩展规则引擎，YAML 配置驱动，支持多规则优先级匹配 + 排除店铺
tags: [sellfox-shipping, routing-engine, carrier-selection, yaml]
timestamp: 2026-07-24
---

# 规则引擎 V1 — YAML 驱动路由

## 设计

YAML 配置文件 + Python 求值引擎。新增/修改规则只需编辑 `routing/routing_rules.yaml`，无需代码变更。

## 架构

```
routing/
├── __init__.py
├── models.py          # RoutingRule, Condition, RuleAction, RoutingResult, PackageRoutingData
├── conditions.py      # 10 种运算符注册表 + evaluate_condition()
├── engine.py          # RuleEngine: from_yaml() → route()
└── routing_rules.yaml # 规则定义（可独立修改）
```

## 规则文件结构

```yaml
exclude_shops: [WFUS, OSTK, PotteryBarnUS]

rules:
  - name: "规则名称"
    priority: 10          # 升序，越小越先匹配
    conditions:
      - field: weight_kg  # 字段名（来自 PackageRoutingData）
        op: lte           # 运算符
        value: 15         # 阈值
    match: all            # all=全部满足 / any=任一满足
    action:
      carrier: lizard     # 内部标识
      label: "蜴国际"     # 展示名
      reason: "..."       # 匹配说明
```

## 支持的运算符

eq, neq, gt, gte, lt, lte, in, not_in, contains, between

## 可用字段

| 字段 | 来源 | 说明 |
|------|------|------|
| longest_side_cm | package_dims | 最长边（降序） |
| second_side_cm | package_dims | 次长边 |
| third_side_cm | package_dims | 最短边 |
| weight_kg | package_dims | 包裹总重 |
| total_quantity | package_items | 商品总数累加 |
| shop_name | packages | 店铺名 |
| warehouse_name | packages | 仓库 |
| destination_country | address | 目的国 |
| destination_state | address | 目的州 |
| postal_code | address | 邮编 |

## 当前规则

| 优先级 | 规则 | 条件 | 结果 |
|--------|------|------|------|
| — | exclude_shops | shop ∈ {WFUS,OSTK,PotteryBarnUS} | 排除（平台物流） |
| 10 | 蜴国际-小件标准 | 三边≤68×43×43 重量≤15kg 数量≤1 | 蜴国际 |
| 100 | VITE-默认 | 无条件（兜底） | VITE-FedEx |

## 数据持久化

- `shipping_package_dims` — 包裹合并重尺
- `shipping_package_routing` — 路由结果（carrier/label/reason/rule_name/matched）

详情页打开时自动计算并落库，下游可直接读表传输。
