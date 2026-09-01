---
okf: v0.1
type: Spec
title: 先改后台价，再逐票 true-up
tags: [pb, promo, spec]
timestamp: 2026-08-31
---

# 两步方案

Christine 改完 item/PO cost 之后，**从下一张新 PO 起金额应对**。那张合同价新 PO 就是 **True-up 冻结 PO**；那之前的历史票才能冻结，集中交给 Diane。

**扫描截止 ≠ 冻结点。** 08-27 只是当前已操作发货、内部表应扫到的日子。等 Tracy/Christine 期间仍可把匹配规则跑完整（含 08-27+ `invoice x*`），但**不要把未冻结清单当索赔发出**。新边界发现后再改规则，不要静默扩索赔集。

## 第一步 — 立刻改价（进行中）

1. Tracy 确认 `_filled_for_Tracy.xlsx` 的 Correct Wholesale（24 个三角枕回到合同价；Gap Filler / 23.5" / orthopedic = Current）。
2. Tracy 在 Christine 线程 Reply All 授权更新。
3. Christine 改系统。Coffee 不在她的表里（无订单）；若 PB 仍要维护主档，用同一合同价梯。
4. Centrade 抽下一张 SPS PO/发票，确认 64.58 / 71.96 / 75.65 / 87.95。

## 第二步 — 历史票

内部表 `PB_2025_promo_trueup_internal.xlsx`（截止约 08-24 工作数 ~$23,586）需重跑覆盖 08-27+，再与 Diane 的 24 色 report 对。

请对方明确：

- 已付款：debit/credit memo 或 AP 调整；尽量票号级，至少 PDF/Excel 给中国财务。
- 未付款：下一张 remittance 前改应付。
- 时限：改价数个工作日；已付差额例如 30 天出 memo。
- 不要要求我们改已经进钉钉的历史发票号。
