---
okf: v0.1
type: Spec
title: 先改后台价，再逐票 true-up
tags: [pb, promo, spec]
timestamp: 2026-09-01
---

# 两步方案

Christine 改完 item/PO cost 之后，**从下一张新 PO 起金额应对**。那张合同价新 PO 就是 **True-up 冻结 PO**；那之前的历史票才能冻结，集中交给 Diane。

**扫描截止 ≠ 冻结点。** 08-31 北京 `invoice x34` 是已开票 batch，不是冻结点。等 Diane 改 open PO 期间仍可重扫内部表，但**不要把未冻结清单当索赔发出**。

## 第一步 — 改价（2026-09-01 进度）

| 子步 | 状态 |
|------|------|
| Tracy 确认 `_filled_for_Tracy.xlsx` Correct Wholesale | ✅ 2026-08-28 |
| Tracy Reply All Christine 线程 | ✅ |
| Christine **item master updated** | ✅ 2026-08-31 |
| Diane **update current orders**（未开票 PO） | ⏳ 4 张已接受 PO Change；**3 张待补** 137803269 / 137804289 / 137804323 |
| 第一张合同价 SPS **新 PO**（冻结点候选） | ✅ PO Date **09/01/2026** New 三角枕已是合同价 |
| 第一张合同价 **发票**（冻结确认） | ❌ 扣货中，尚未开票 |
| 扣货至剩余 open PO 显示合同批发 | ✅ 继续，等上述 3 单 |

Coffee 不在 Christine 37 行里（无订单）；若 PB 仍要维护主档，用同一合同价梯。

## 第二步 — 历史票（冻结 PO 之后）

内部表 `PB_2025_promo_trueup_internal.xlsx`（截止约 08-24 工作数 ~$23,586）需重跑覆盖 8/31 `invoice x34`，再与 Diane 的 24 色 report 对。

请对方明确：

- 已付款：debit/credit memo 或 AP 调整；尽量票号级，至少 PDF/Excel 给中国财务。
- 未付款：下一张 remittance 前改应付。
- 时限：改价数个工作日；已付差额例如 30 天出 memo。
- 不要要求我们改已经进钉钉的历史发票号。

## 待深度研究

见 [AGENT_HANDOFF.md §9](../AGENT_HANDOFF.md) — PO CSV + invoice x* + 来自Email + 给财务 Excel 四套源对齐与手工调整边界。
