---
name: pb-promo-cost
description: >
  Pottery Barn Vendor 5806 活动供货价未恢复 / Early BF wholesale still on PO、
  三角枕 headboard wedge 合同价 vs 20% 活动价、Diane Zhang / Christine Padrid 改 item cost、
  历史 PO 差额 true-up。当用户提到 PB promo、Early Black Friday、wholesale not reverted、
  Vendor 5806、Centrade 三角枕改价、Diane 拉单、Christine retail and costs、
  PO Date 12/03 之后发票差额时触发。
  不用于每月给财务/Tracy 的付款对账（那是 pb-reconciliation）。
---

# PB 2025 Early BF 供货价未恢复

## 先读

1. `pb_promo_trueup/AGENT_HANDOFF.md` — 暂停点、价梯、联系人、发什么附件
2. `pb_promo_trueup/docs/reference/matching-rules.md` — 三数据源与双号/占位号
3. `pb_promo_trueup/docs/reference/communications.md` — 给 PB 禁止佣金/双号/$28k

数据在仓库外 `D:\Work\美国\Tracy Miller\打折活动Promotion\` 与 `...\PB orders\`。xlsx/CSV 不入 git。

## 铁律

- 给 Diane/Christine：**Centrade Inc — Vendor #5806**；禁止 Tracy 佣金、禁止解释双发票号、禁止 $28k 粗算。
- 索赔窗口：**PO Date ≥ 2025-12-03**，不是我方开票日。
- 给 PB 的 INV#：以 `来自Email` 原始对账单为准，不是「给财务」/「To Tracy Miller」。
- 发票 CSV：只认日文件夹 `invoice x*`。
- 先改后台价、抽下一单验证，再发明细。等 Tracy 确认 Christine 表期间可内部重跑（含 08-27+），不要把未冻结清单发出。
- 月度对账用 `pb-reconciliation` skill。

## 当前等待（2026-08-31）

Tracy 确认已填的 Christine Correct 批发价 → Christine 改系统 → 抽 SPS 新单 → 冻结历史票给 Diane。
