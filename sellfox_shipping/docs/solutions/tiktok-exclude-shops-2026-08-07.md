---
okf: v0.1
type: Solution
title: TikTok 排除店铺 — 赛狐 API 核实 + 单点配置驱动两处过滤
description: 通过赛狐 OpenAPI 核实 TikTok 店铺真实 shop_name，将 TT_Tooddly / TTCozydozy 加入 exclude_shops 单点配置，同时驱动 Transactions 列表过滤与路由建议
timestamp: 2026-08-07
tags: [sellfox-shipping, tiktok, exclude-shops, routing]
---

# TikTok 排除店铺 — 赛狐 API 核实 + 单点配置驱动两处过滤

## 背景

用户希望把两家 TikTok 店铺（最初提供的名称 `TTTOODDLYUS` / `TTCozyDozyUS`）加入"排除平台物流店铺"过滤，同时让"建议渠道方式"也不给这两家路由建议。但用户不确定赛狐如何定义 TikTok 店铺，要求先通过 API 核实。

## 核实过程（关键）

1. **赛狐 OpenAPI** `POST /api/multiplatform/shop/list.json`（经 `DirectSellfoxClient._post`）返回 8 个多平台店铺，其中 `platformType=TIKTOK` 共 4 家：
   - 688441 `TTCozydozy`（自运营-跨境）
   - 688281 `TT_Tooddly`（自运营-本土）
   - 688205 `TTBNKC`（自运营-跨境）
   - 598458 `DaneeyGo`（自运营-本土·美国受益人）

2. **本地包裹数据** `shipping_packages.shop_name` 与 API 的 `name` 字段完全一致（TTCozydozy×11、TT_Tooddly×1、TTBNKC×11、DaneeyGo×20）。

3. **结论**：用户提供的 `TTTOODDLYUS` / `TTCozyDozyUS` 在系统中**不存在**，真实 `shop_name` 是 `TT_Tooddly` / `TTCozydozy`。

## 实现

按用户确认只排除 2 家（TTBNKC / DaneeyGo 保留）：

- `routing/routing_rules.yaml` 的 `exclude_shops` 追加 `TT_Tooddly`、`TTCozydozy`
- `routing/models.py` 删除无运行时调用方的 `is_excluded_shop` 硬编码属性，避免配置漂移
- `tests/sellfox_shipping/test_package_repository.py::test_exclude_shops_filter` 扩展 TikTok 场景

## 关键设计点

`exclude_shops` 是**单点配置**，同时驱动两处逻辑：

1. **Transactions 列表"排除平台物流店铺"复选框**：`app.py::_routing_exclude_shops()` 读 YAML → `repository.list_packages/count_packages` 按 `shop_name.notin_(exclude_shops)` 过滤。
2. **包裹详情"建议渠道方式"**：`RuleEngine.from_yaml()` 读同一 YAML → `engine.route()` 对排除店铺返回 `carrier=excluded`。

改一处（YAML），两处生效；无需改代码。

## 验证

- 浏览器：勾选排除后总数 2898→2334（-564 = WFUS 325 + OSTK 186 + PotteryBarnUS 41 + TTCozydozy 11 + TT_Tooddly 1）；TTCozydozy 包裹详情"建议渠道方式"显示"排除（平台物流）/ 已排除"。
- 测试：281 passed。
