---
okf: v0.1
type: Reference
title: UPS 交付核查 — 判断迟发还是 PB 漏结算
tags: [pb, reconciliation, ups, delivery, tracking]
timestamp: 2026-08-14
---

# UPS 交付核查流程

## 目的

当月"本轮未付"发票，判断是**我们迟发/漏发**（交付晚于账期截止，PB 顺延下账期）还是 **PB 忘记结算**（发货及时但 PB 没付）。

## 关键机制

- PB 按 **UPS 实际发货日**（"We Have Your Package" 日期 = 仓库实际交给 UPS 的时间）后约 1 个月付款，系统看 UPS 跟踪记录。
- 账期结算覆盖范围 ≈ 结算日前 1 个月的交付。例：8/13 批次覆盖 ~07/15 前的交付；交付 07/23–08/04 的顺延到 ~09/13 下账期。

## 步骤

1. **发票号 → PO 号**：从 Invoice to PB 表（C 列）或对应发票 CSV（第 3 列 PO or Vendor Number）取。
2. **PO 号 → UPS 跟踪号**：找该发票的日文件夹（`YYYYMM\YYYYMMDD\`），读 `shipment*.csv`，匹配 PO #（第 16 列）取 `Carrier Tracking`（第 5 列）。可能有多个（一单多件）。
3. **查 UPS**：浏览器访问 `https://www.ups.com/track?tracknum=<跟踪号>` → 点 "Show Details" 看 **Package History**。
   - 关键时间点：**Label Created**（标签创建）、**We Have Your Package**（仓库实际发货，PB 按此付款）、**Delivered**（交付）。
4. **校验跟踪号**：UPS 交付地址应与 shipment CSV 收货地址（Ship To Name/Address/City）一致，避免查错件。
5. **判定**：
   - 交付日 ≤ 账期截止 → 应已付 → **PB 漏结算**（问 PB/投诉）。
   - 交付日 > 账期截止 → **迟发**，顺延下账期，非 PB 问题。
   - 若 "We Have Your Package" 明显晚于 CSV 发货日 → 仓库迟发/漏发后补发，或标签创建后发现无货等补货后再发。

> 说明：UPS 跟踪页是 JS 渲染，普通 HTTP 抓取（WebFetch）拿不到数据，需要浏览器（Playwright/Chrome）。跟踪号有效期约 120 天。

## 2026-08-14 核查结果（5 张未付）

| 发票 | PO | 标签创建 | UPS实际发货(We Have Your Package) | 交付 | 跟踪号 |
|------|-----|---------|----------------------------------|------|--------|
| INV...1362 | 137292021 | 06/09 | **07/30**（隔51天） | 08/04 West Roxbury MA | 1ZC0019E0301406005 |
| INV...1507 | 137424983 | 07/02 | **07/20**（隔18天） | 07/23 Blue Ash OH | 1ZC0019E0314557560 |
| INV...1521 | 137430920 | 07/06 | **07/20**（隔14天） | 07/23 Maspeth NY | 1ZC0019E0318578736 |
| INV...1528 | 137432874 | 07/06 | **07/20**（隔14天） | 07/23 East Aurora NY | 1ZC0019E0327032370 |
| INV...1535 | 137443744 | 07/06 | **07/20**（隔14天） | 07/23 Valencia CA | 1ZC0019E0329334504 |

**结论**：5 张都是**我们迟发**，不是 PB 漏结算。标签在发货日创建，但包裹 1-7 周后才交给 UPS（全从 Stafford/Houston TX 起运），交付 07/23–08/04 晚于 8/13 账期截止，顺延到 ~09/13 下账期付款。下月对账确认即可。

**备注**：已写入 Notes "本轮未付" 区块 N 列（脚本 `UNPAID_NOTES` 配置）。
