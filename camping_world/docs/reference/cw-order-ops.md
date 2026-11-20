---
okf: v0.1
type: Reference
title: Camping World 订单操作 SOP
tags: [campingworld, operations, edi, fedex, sop, dropship]
timestamp: 2026-11-20
---

# CW 订单操作 SOP（上线前版）

> 依据：SPS 官方 *Camping World EDI Operations Guide*（2023-12 版）与 CWI 2025-2026 合规指南 §8.12–8.13。
> 订单模块代码尚未开始，本文是人工操作的基准流程。

## 1. 时间窗（美国中部时间）

| 动作 | 时限 | 说明 |
|---|---|---|
| 850 PO 接收 | 每天 7:00/8:00、11:30/12:30、16:00/17:00 | CW 批量发送 |
| **855 PO 确认** | **PO 发出后 1 个工作日内** | 不能像 PB 那样每周批 2-3 次 |
| 846 库存 | **至少每 72 小时** | 全量或变更均可，按 SPS 规格 |
| 856 ASN | **发货后 1 个工作日内**，且早于 810、早于到货 | |
| 810 发票 | 发货后 | ASN 之后 |
| 860 PO 变更 | 收到即处理，确认差异 | |

## 2. 每日检查（建议固定上午一次）

1. 登录 SPS，检查新 850 / 860。
2. 对每个 PO：确认 SKU、数量、单价、取消日期、Ship No Later。
3. 库存预检：按通途库存筛缺货行（沿用 PB 的"按明细行判定，不按整单"原则）。
4. 当日回 855：全部接受 / 部分接受 / 缺货改期。
5. 把当日要发的单导给仓库（美中 USTX）。

## 3. 发货与标签

### 3.1 选路
- 单箱 ≤150 lb。
- 单次 ≤20 箱或 ≤300 lb → FedEx；>301 lb → LTL（Redwood）。
- 住宅 → **FedEx Home Delivery**；商业 → **FedEx Ground**。
- **禁止 UPS**。

### 3.2 标签链路（三选一，按 SPS 确认结果）

| 方案 | 操作 | 适用 |
|---|---|---|
| A. SPS Fulfillment | 在 SPS 里建单、比价、出 FedEx 标签、回填 tracking | 与 PB 最接近，优先确认 |
| B. FedEx Ship Manager 网页 | 手工建单，3rd Party Bill To CW 账号，reference 填 CW PO# | YTQ 做 Wayfair/Overstock 的现成路径 |
| C. FedEx Ship API | 脚本建单 | 量大后再上；需生产 shipper 权限 |

### 3.3 FedEx 必填字段（逐箱检查）

- **reference = CW PO#**（漏填或填内部单号是头号错误）
- 服务类型：住宅 Home Delivery / 商业 Ground
- 计费：**3rd Party Bill To**，账号用 CW 的（住宅 dropship：`#278463419` / `#908562305`，
  两个账号用途先确认）
- **不要**选 Collect / Payor Recipient
- 单箱价值 >$500 必须申报
- 记录 tracking，回填 856

### 3.4 随箱文件

1. **Branded packing slip**（dropship 每单必需，模板需在 SPS onboarding 提交并获批）
2. **GS1-128/UCC-128 标签**（4×6）：PO#、承运商、SSCC-18、SKU、颜色/尺码、供应商地址、
   收货地址、箱号（1 of N）、原产国、ASN# 条码
3. 箱内不放价格单；退货说明按 CW 政策

## 4. 发货后

1. 做 856 ASN，检查 SSCC 与箱号一致。
2. 出 810 发票（金额 = PO 单价 × 数量，扣 3% + 1% 是 CW 侧折让，不在发票里改价）。
3. 把 tracking 与箱号存档，供对账。

## 5. 缺货与变更

- 缺货：855 里按行改期或取消，不要先建标签再通知。
- PO 变更（860）：核对数量/价格/取消日；有差异当天回复。
- 已发货后不可改 PO；按 810 与 remittance 对账。

## 6. 退货

- CW 是 1% defective allowance（% off invoice），通常不逐单退。
- 若 CW 要求退回残次品，按 Vendor Information Form 的 Return Goods 段执行。
- 记录退货原因，月度复核是否超过 1% 计提。

## 7. 内部先例（YTQ）

YTQ 做 Wayfair/Overstock 的路径：
`平台后台导 CSV → 通途处理 → 导出 → Colab 脚本处理 → FedEx/UPS 后台上传（第三方账号）`。

CW 若不能走 SPS 出标签，直接复用这条路径，只需把承运商换成 FedEx、账号换成 CW 的
third-party 账号、reference 换成 CW PO#。

## 8. 上线前必须确认

1. SPS 能否出 FedEx 标签（方案 A）。
2. 两个住宅 FedEx 账号分别对应什么场景。
3. Branded packing slip 与 GS1-128 模板的审批人。
4. 我方 FedEx 发件账号（Track 的 sandbox key 不能用于 Ship）。
