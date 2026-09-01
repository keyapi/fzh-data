---
okf: v0.1
type: Reference
title: PB 2025 Early BF 供货价未恢复 — 沟通与逐票对账
date: 2026-08-31
last_updated: 2026-09-01
category: workflow-issues
module: pb_promo_trueup
problem_type: workflow_issue
component: payments
severity: high
applies_when:
  - "Vendor 5806 活动供货价在约定窗口结束后仍停在 PO/item 上"
  - "要把 SPS 发票、来自Email 对账单、给财务/Tracy 表对成可给 PB 的差额清单"
  - "给 Diane/Christine 写信且不能出现中间人佣金或双发票号解释"
  - "Christine 已改 item master 但 Diane 尚未改 open PO，需要扣货并区分已开票与未开票"
tags: [pb, potterybarn, promo, wholesale, trueup, remittance]
related_components: [pb_reconciliation, documentation]
---

# PB 2025 Early BF 供货价未恢复 — 沟通与逐票对账

## Context

Centrade Inc（Vendor **#5806**）经 Tracy Miller 供 Pottery Barn 三角枕。2025 Early BF 约定 11/07–12/02、20% off headboard。窗口结束后网站/PO 零售已回 149/159/169/199，供货价仍是 51.7/57.6/60.5/70.4。像是活动价没设结束日。2024 测试窗按 **PO Date** 在次日已自动回合同价。

会话在 Christine 2026-08-31 确认 item master updated、Diane 仍须改 current orders 时暂停。9/1 实测：6 张未开票 PO（PO Date 8/31）仍活动价；8/31 北京 `invoice x34` 21 张三角枕已开票进 true-up；**冻结 PO 尚未出现**。需要把 item master vs open PO 滞后、已开票 leave as billed、以及四数据源未来深度对齐写下来。

## Guidance

完整交接：`pb_promo_trueup/AGENT_HANDOFF.md`。匹配细节：`pb_promo_trueup/docs/reference/matching-rules.md`。

1. **两步**：先改 item/PO cost 并抽下一单验证；再交逐票清单。第一封不要当借记通知。
2. **窗口用 PO Date ≥ 2025-12-03**。不要用我方开票日（会把窗口内滞后开票算进索赔）。
3. **发票只认 `invoice x*`**。重复下载会把同一张票加两次（~$28k vs 去重后 ~$23.6k 到 08-24）。
4. **给 PB 的 INV# = `来自Email` 付款号**。给财务/To Tracy Miller 可能已改成本地号或补了占位号。
5. **双号对外用对方付的号**；内部对照。不要写信解释「我们有两个号」。方向与月度 `REMAP`（付款号→本地号）相反。
6. **占位号**（如 `20230216`）给 PB 仍写占位号。
7. **给 WSI 禁止**：Tracy 佣金、$28k、Daneey、本地 CSV 文件名、Mercy 离职揣测。
8. **SKU**：改价 28 个（含无货 SkyBlue Twin、无单 Coffee）；差额按实际订单；23.5"/Gap Filler 排除。
9. **双侧对账**：内部列本地 INV#；给 PB 列 `来自Email` 号。N 张开票对上 M 张对方认的票，差数（滞后 / 双号 / 占位 / 排除 SKU）必须可追溯。xlsx 与一次性填表脚本在仓库外，见 `pb_promo_trueup/AGENT_HANDOFF.md` 第 8 节。
10. **订单 CSV 只交叉核 PO Date / 单价**，不当索赔宇宙；没开票不索赔。
11. **给 Diane 一行一张 INV#**。同一票多 SKU 先汇总。
12. **`来自Email` 去重 = 付款日 + PB INV#**（文件跨账期重叠）。
13. **短收 / credit 不冲活动价差额**；未付请对方改应付。
14. **扫描截止 ≠ 冻结 PO**。冻结 = 改价后第一张合同价新 PO。未冻结清单不发给 Diane。
15. **Item master ≠ open PO cost。** Christine 改主档后 Diane 仍须改未开票 PO；扣货至合同价出现。
16. **已开票 and transmitted：leave as billed。** 用 invoiced vs not-invoiced 切分，不说 through 8/31。8/31 batch PO Date 至 8/30 进 true-up。

## Why This Matters

错误口径会把窗口内合法活动价、重复 CSV、未开票订单、或对方不认的发票号送进索赔，对不上 Diane 后台和 AP。把扫描截止当成冻结点会把还在增长的集合当索赔发出。佣金出现在 WSI 邮件里会破坏中间人关系。叠折会把下一轮活动做成 ~41 的批发价。

## When to Apply

- 本 case 从 Diane 改 open PO、出现冻结 PO 起继续。Christine 主档已更新。
- 任何「SPS 发票 vs PB remittance vs 已加工财务表」三方对票；订单 CSV 只做交叉核。
- 给 PB 写活动价/PO cost 邮件。

## Examples

- 2024：PO 131000475 dated **12/04** 已是 $64.58；INV 开在 12/06 只是操作日。
- 双号：PB `INV…1541` ↔ 本地 `INV…1530`（`pb_reconciliation` `REMAP` 同一对）。
- Christine 表 37 行：24 个三角枕 Correct wholesale = 合同价；其余 Correct = Current。Coffee 不在她的文件里。
- 08-24 内部快照：1,425 张 / ~$23,586.17；1 双号、1 占位、173 未付。8/31 `invoice x34` +21 张三角枕待并入重跑。
- 2026-09-01：6 open PO PO Date 8/31 仍活动价；Christine 主档已改、Diane open PO 待改；冻结 PO 未出现。

## Related

- [pb-reconciliation-monthly-update.md](pb-reconciliation-monthly-update.md) — 月度付款对账（同一 CSV/`来自Email`，目的不同）
- `pb_promo_trueup/docs/lessons/lessons-learned.md`
