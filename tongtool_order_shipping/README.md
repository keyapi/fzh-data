---
okf: v0.1
type: Guide
title: tongtool_order_shipping — 通途订单发货处理
description: 通途订单导出 → 组合件合并成「每包裹一行」的承运商批量导入 csv + 仓库背贴 PDF
updated: 2026-09-22
---

# tongtool_order_shipping — 通途订单发货处理

> 本文给人看。Agent 请直接读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。

## 这是什么

把**通途订单导出**变成两样东西：

1. 给承运商**批量导入**用的 csv / xlsx —— **一个包裹一行**（一个包裹只能贴一个面单标签）；
2. 给仓库分拣用的**背贴 PDF** —— 一个包裹一页，页内把该包裹里**所有**仓库 SKU 都列出来。

覆盖的平台：Overstock（走 UPS 模板）、OSTK-Fedex（走 FedEx 模板）、以及同型逻辑的同类自发货订单。

## ⚠️ 代码现在不在本仓库

流水线本体目前是**同事的一个 Google Colab notebook**（「订单处理 Overstock. 炸开SKU别名,不处理MyToys」）。本模块目前只放：

- 这条线的**硬约束与知识**（见下面「三条硬约束」）；
- 将来的**迁移落点** —— 参照先例 `pb_orders/`（另一个对话把「PB 订单处理」从 Colab 迁到了仓库）。

迁的时候，背贴与查名可以直接复用 `sellfox_shipping/sku_label/`（`pdf_generator.py` + `name_lookup.py`）。

## 流水线（现状）

```
通途订单导出 xls（每货品一行）
  → 按「包裹号」分组合并（一个包裹一行）
  → 承运商批量导入 csv/xlsx   ← 字段有硬上限，必须截断
  → 背贴 PDF（每包裹一页，逐 SKU 一行）  ← 品名查不到会留白且不报错
```

**包裹号从哪来**：通途导出里 `Description of Goods` 列放的是**订单号（可能带拆单后缀）**。
对 Overstock 而言**一个订单 = 一个包裹**（需要拆包的订单，负责同事已拆成独立订单），
所以「同一个 `Description of Goods` 值 = 同一个包裹」成立。**不要**用正则剥掉后缀去合并 —— 那会把拆单后的两个包裹并成一个。

## 三条硬约束

1. **承运商字段有长度上限，合并后必须主动截断。**
   UPS `Reference 1~5` 各 **35** 字符（超了**整批被拒**）；FedEx `poNumber` **30**、`itemDescription` **450**。
   同一个拼接串在不同字段要用**不同**上限。详见
   [`docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md`](../docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md)。
2. **背贴品名查不到的键是「导出里原样出现的字符串」。**
   通途SKU 在 EN 有**两种写法**（`X-Foam` 与裸基础码 `X`），背贴用的那张表是 `US SKU Name`。
   缺失时该行**留白且不报错** ⇒ 流水线必须有「背贴缺名」报告行。详见
   [`docs/solutions/integration-issues/sku-name-backfill-via-en-customer-code.md`](../docs/solutions/integration-issues/sku-name-backfill-via-en-customer-code.md)。
3. **notebook 里别用 `!shell` 做文件操作。**
   文件名可能含空格（同事保存时会加「每包裹一行」这类中文后缀），`!zip` 会被 shell 分词 →
   `Nothing to do!` → 压缩包没生成 → `files.download` 抛 `FileNotFoundError`。用 Python `zipfile`。
   详见 [`docs/solutions/developer-experience/colab-shell-out-filename-spaces.md`](../docs/solutions/developer-experience/colab-shell-out-filename-spaces.md)。

## 不要做什么

- **不要**把这个模块和 `sellfox_shipping` 混起来：那个是**赛狐侧**的尾程打单（从赛狐取订单）。
  本模块是**通途侧**的订单导出后处理。两者只是"都用 UPS/FedEx 面单"这点关系。
- **不要**用本模块做承运商轨迹跟踪（那是 `fedex_track` / `gls_track` / `parcel_track`）。
- **不要**用它做通途订单成本（那是 `tongtool_order_cost`）。
