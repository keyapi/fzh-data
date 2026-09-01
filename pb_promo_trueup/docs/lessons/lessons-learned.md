---
okf: v0.1
type: Lesson
title: PB 活动价未恢复 — 经验教训
tags: [pb, promo, lessons]
timestamp: 2026-08-31
---

# 经验教训

1. **中文「8 折」是 20% off**，不是 8% off。对外英文必须写 20% off。
2. **结束日看 PO Date，不看我们点开票的那天。** 2024-12-04 新 PO 已是合同价；12/06 00:16 只是开票操作时间。
3. **给 Tracy 的调查总额不能直接给 PB。** `$28k` 混进了重复 CSV；去重后约 `$23.6k`，且会随新发票增加。
4. **SKU 表给 Diane 要可操作**：PB SKU + 我方 SKU + 合同价 vs 当前价。她可能不打开 Excel，回信里再贴一遍号码。
5. **改价列表可以含无货色（SkyBlue Twin、Coffee）**；差额清单按实际订单。全量 Vendor 表会把价正确的 23.5"/Gap Filler 拉进来。
6. **Diane 管供应链主档，买手管确认。** “reach out to the PB Brand” ≠ 绕过 Tracy。
7. **给 PB 的 INV# 用对方付款号**（`来自Email`）。财务/Tracy 表可能已改成本地号。月度 `REMAP` 是付款号→本地号；索赔是本地号→付款号。
8. **不要在第一封索赔。** 先改后台，抽一单验证，再交逐票表。
9. **佣金只跟 Tracy 说。**
10. **新活动禁止叠折。** 必须先恢复合同价再打 20%。
11. **扫描截止不是冻结点。** 某日 `invoice x*` 只说明内部表扫到哪；冻结是改价后第一张合同价新 PO。
12. **订单 CSV 不是索赔宇宙。** 没开票的 PO 不向 PB 要。重复订单导出会让未开票行看起来像漏索赔。
13. **给 Diane 必须票级一行。** 同一 INV# 多 SKU 行先汇总，否则她后台 pull 对不上张数。
14. **来自Email 文件会重叠。** 去重键是付款日 + PB INV#，不是文件名。
15. **短收不冲活动价差额。** 运费扣、以前的 credit、少付，另账；不要在 true-up 里净额化。
16. **Item master 更新 ≠ open PO 已改价。** Christine 2026-08-31 改主档后，9/1 下载的 PO Date 8/31 订单仍活动价 — Diane 还要改 current orders。扣货直到 SPS 打出合同批发。
17. **已开票 leave as billed。** 8/31 北京 `invoice x34`（PO Date 至 8/30）进 true-up，不要请 Diane 改已传发票。切分用 invoiced vs not-invoiced，不说 through 8/31。
