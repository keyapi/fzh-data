---
okf: v0.1
type: Spec
title: 平台账期对账设计
description: OSTKUS 账期费用级对账的设计、输出结构与 Wayfair 扩展方案
tags: [platform, reconciliation, design, wayfair]
timestamp: 2026-08-17
---

# 平台账期对账设计

## 目标

统一处理平台账期文件（Overstock OSTKUS，未来 Wayfair WFUS）与 EN/Tongtool Order 的费用级对账，输出财务可复核的工作簿。

## 输入

- OSTKUS 账期 xlsx：`Payment Summary` + `Detail`。
- EN 生产 ERPNext：`Tongtool Order` REST 只读。
- 可选：平台订单导出 CSV（用于核对不同批次订单，不用于本账期）。

## 处理流程

1. 解析 Payment Summary 与 Detail，建立费用分类。
2. 按基础 OS 订单号发现 EN `Tongtool Order`，包含 `_1/_2/_3` 与 `OSFD-` 变体。
3. 标记重复主单并排除，避免金额双算。
4. 按 SKU、数量、金额、仓库、发货时间做订单级核对。
5. 生成财务工作簿：总览、Payment Summary、Detail、订单级费用、EN 财务明细。

## 输出工作簿

| Sheet | 内容 |
|-------|------|
| 核对总览 | 每个账期文件的 Check Total、Sales、Returns、EN 差异 |
| PaymentSummary逐项 | 账期类别金额 + EN 对照 |
| 账期Detail | 全部明细行与费用分类 |
| 订单级费用核对 | 每个基础订单的账期金额 vs EN 金额/平台费/毛利 |
| EN订单财务明细 | EN 单据金额字段、仓库、发货时间、P号 |

## Wayfair 扩展

- WFUS 账期行使用 `Invoice #`/`PO #`，前缀 `CS.../CA...`。
- Wayfair 账期文件还有 `Vendor Services` 广告扣款段，需要额外解析。
- EN 命名规则可能与 OSTKUS 不同，需先调研 `Tongtool Order` 中 `platform_code=WF` 的单据。
- 匹配键建议复用 `platform_order_id` + 后缀 + SKU + 金额。

## 安全约束

- 只读 EN，不写生产。
- 输出 xlsx 不提交 git。
- 未匹配行保留并说明原因。
