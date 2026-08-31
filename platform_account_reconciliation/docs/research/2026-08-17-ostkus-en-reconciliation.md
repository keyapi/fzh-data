---
okf: v0.1
type: Research
title: OSTKUS 账期与 EN Tongtool Order 对账调研
description: 2026-08-17 OSTKUS 07-01/07-16 账期与 EN 对账过程、拆单发现与结果
tags: [ostkus, en, tongtool, reconciliation, research]
timestamp: 2026-08-17
---

# OSTKUS 账期与 EN Tongtool Order 对账调研

## 背景

财务提供 `OSTKUS-2026-07-01.xlsx` 与 `OSTKUS-2026-07-16.xlsx`，需要判断是否为账期文件并核对与订单数据的关系。

## 文件判定

两个文件都包含 `Payment Summary`、`Detail`、`Mozart Reports`，是 Overstock 结算文件，不是订单导出。

| 文件 | Check | Sales | Returns | Adjustments | Fees | Check Total |
|------|-------|-------|---------|-------------|------|-------------|
| 07-01 | 469437 | 10,240.44 | -1,025.13 | -1,140.38 | -119.25 | 7,955.68 |
| 07-16 | 471881 | 14,556.24 | -709.19 | -6,808.40 | -116.55 | 6,922.10 |

## 匹配过程

1. 账期 `OS Order #` 与 Overstock 7 月订单 CSV 无交集，因为 CSV 是 6/29-8/1 订单，账期是 3-5 月订单。
2. 通过 EN `Tongtool Order` 用 `OS-{platform_order_id}` 精确匹配。
3. 发现多 SKU/多件订单在通途/EN 拆成 `_1/_2/_3` 子单；`platform_order_id` 保留后缀。
4. 发现另一账号 `OSTK02US` 使用 `OSFD-` 前缀。
5. 发现 4 个订单同时存在无后缀主单与拆分后缀子单，且金额重复，汇总时排除主单。

## 结果

- 两个账期共 350 个基础 OS 订单，全部在 EN 有对应单据。
- 销售金额差异均为 0：07-01 `10,240.44`，07-16 `14,556.24`。
- EN 平台费与账期 Marketing Allowance 差异：-25.73 / -36.52，待确认口径。
- EN 退货原单金额：07-01 `884.41` vs 账期货值 `812.41`（差 72.00）；07-16 `526.32` 一致。
- 4 个跨期退单：`473076088`、`473115387`、`473298864`、`473437955`。
