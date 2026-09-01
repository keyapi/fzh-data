---
okf: v0.1
type: Handoff
title: PB 2025 Early BF 供货价未恢复 — Agent 交接
tags: [pb, potterybarn, promo, wholesale, trueup, handoff]
timestamp: 2026-09-01
---

# PB 2025 Early BF 供货价未恢复

> Agent 接手先读本文，再按需打开 [docs/](docs/)。xlsx/CSV 在仓库外，禁止提交 git。给 PB 的邮件**禁止出现 Tracy 佣金**、**禁止解释双发票号**。

## 1. 现状（2026-09-01 暂停点）

| 步骤 | 状态 |
|------|------|
| 微信 + 邮件 Tracy，报活动价未结束 | 已完成 |
| To Diane Zhang，Cc Christine Padrid + Tracy，附 SKU 表（不是索赔清单） | 已发 2026-08-26 |
| Diane 要 PB item number；回信贴 28 个 + Table B 排除项 | 已发 |
| Diane：Coffee 4 色无订单；另 24 色有 order report | 已回；Coffee 符合「已停产」 |
| Christine 拉系统现价表，请 Tracy validate | 已收到 |
| Key 填 Correct 批发价，微信+单独邮件给 Tracy（不抄 WSI） | 已发 2026-08-28 |
| Tracy → Christine 确认改价（Reply All 附 filled 表） | **已完成** 2026-08-28 |
| Christine：**item master 已更新**（2026-08-31 邮件 "The system has been updated"） | **已完成** |
| Christine → Diane：**update any current orders** | **进行中** — 未开票 PO 仍显示活动价 |
| 我方扣货，等 open PO 打出合同批发后再发 | **2026-09-01 起** |
| 抽第一张 **合同价** 新 PO/发票（True-up 冻结 PO） | **尚未出现** |
| 8/31 北京下午已开票 batch（`invoice x34`，21 张三角枕，PO Date 至 8/30） | 进 true-up；**勿请 Diane 改已传发票** |
| 9/1 检查：6 张未开票 PO（PO Date 8/31）仍活动价 | 等 Diane 改 open PO |
| 历史票冻结后交给 Diane（debit memo / AP 调整） | **未发**；冻结 PO 出现后再做 |
| 内部逐票表 | **待重跑**（含 8/31 `invoice x34` + 9/1 前快照） |

**Christine 改的是商品主档；Diane 还要改已有未开票 PO。** 两者不同步时，下载的 order CSV 仍会显示 51.7/57.6/60.5/70.4。

本地工作目录：`D:\Work\美国\Tracy Miller\打折活动Promotion\`。
草稿邮件（仓库外）：`Email_ReplyAll_Diane_open_vs_invoiced.txt`（已开票 vs 未开票切分；**不说 through 8/31**）。

## 2. 业务口径（已锁定）

- **供应商**：Centrade Inc — Vendor **#5806**。给 PB 不要写 Daneey。
- **产品**：三角枕 headboard wedge，7 色 × 4 尺码 = 28 SKU。Coffee 4 个在合同里但已久未供货，Diane 无订单，改价仍可改、索赔排除。
- **不在范围**：23.5" personal wedge（$32.50）、Gap Filler、orthopedic。
- **2025 约定窗口**：Early BF **11/07–12/02/2025**，20% off headboard only（中文「8 折」= 八折 = 20% off，不是 8% off）。
- **索赔窗口**：**PO Date ≥ 2025-12-03**（不要用「我方开票日 > 12/02」——那会把窗口内 PO 的滞后开票算进去）。
- **合同批发 / 错误活动价 / 零售原价**

| Size | Contract | Promo (still on POs) | Retail regular |
|------|----------|----------------------|----------------|
| Twin | 64.58 | 51.7 | 149 |
| Full | 71.96 | 57.6 | 159 |
| Queen | 75.65 | 60.5 | 169 |
| King | 87.95 | 70.4 | 199 |

- **2024 对照（按 PO Date）**：测试窗 11/29–12/03；**12/04 新 PO 已是合同价**。例：PO 131000475 dated 12/04，我方 12/06 开 INV0580624000006787 Ivory Twin $64.58。不要写「12/06 才改价」——那是开票日。
- **2025**：11/07 起价对；12/03 起新 PO 仍 51.7…。零售在 PO 上已回 149/159/169/199。像是活动价没设结束日，不是新合同。
- **2026 新活动**：必须从**已恢复的合同价**打 20%，禁止在 51.7 上再打一层（会变成 ~41）。

## 3. 联系人

| 人 | 角色 | 邮件 |
|----|------|------|
| Tracy Miller | 品牌中间人 Inventive Sleep | tracy@inventivesleep.com |
| Diane Zhang | WSI 上海 Supply Chain Analyst | DZhang1@wsgc.com |
| Christine Padrid | PB associate buyer（新对接） | CPadrid@wsgc.com |
| Rita Chen | Christine 抄送 | （Christine 线程里） |

Mercy Ung / Melissa Laguerre **已离职，不要再抄**。Diane 改 item cost 需要 **PB Brand/买手确认** = Christine，不是让 Key 绕过 Tracy 另找一圈人。Reply All 保持 Tracy + Christine。

Diane 2024-12-06「PO costs have been updated」改的是不该打折的 23.5"（$26→$32.50），**不是**整条三角枕收尾。不要把 2025 未结束怪到她头上。

## 4. 给谁看哪份文件

| 对象 | 用 | 不要用 |
|------|----|--------|
| Diane / Christine | `PB_2025_promo_for_Diane_Christine.xlsx`（SKU restore，Arial，无佣金无 $28k） | 旧 `PB_2025_promo_cost_not_restored_evidence.xlsx` |
| Tracy 内部（不抄 WSI） | `Christine download Centrade retail and costs 20260828_filled_for_Tracy.xlsx` | — |
| 我方内部 | `PB_2025_promo_trueup_internal.xlsx` | 在改价确认前不要发给 PB |
| 已归档 | `_archive_drafts\`（含 ~$24k 旧证据、filled v1–v3） | 不要再发 |

金额口径：发给 Tracy 的 ~$28k 是含重复 CSV 的粗算。去重后工作数（PO≥12/03，开票到 08-24）约 **$23,586**（1,425 张）。**不要把 $28k 写给 PB**。8/27 发货后要重跑。

## 5. 四数据源与匹配铁律

详见 [docs/reference/matching-rules.md](docs/reference/matching-rules.md)。摘要：

1. **发票源**：日文件夹只认 `invoice x*.csv`（钉钉提交那份）。忽略「再次下载核对 / 作废 / 合并 / Invoice_From_ASN」及 `NotUsed`。
2. **给 PB 的发票号**：以 `payment advice\来自Email Payment Remittance Advice_*.xlsx` 为准（对方付款用的号）。**不要**用「给财务」或「To Tracy Miller」里的号当 PB 号——那些表可能已改成我们本地号。
3. **本地发票号**：另列对照，不在给 PB 的正文里解释「一张货两个号」。
4. **分批发货**：同一 PO 多张真实 INV#、对方各付各的 → 都留。
5. **双号**：SPS 一张货两个号，PB 付其中一个。PB 列用对账单号。已知：`INV…1541`（PB）↔ `INV…1530`（本地），与 `pb_reconciliation` 的 `REMAP` 同一对。
6. **占位号**：对账单偶发非 `INV*`（例 `20230216`）。给 PB 仍写占位号；Tracy/财务表可能已改成本地 INV#。
7. **两个「发票日期」不要混**：我方 = SPS 发货开票日；PB 对账单 = UPS "We Have Your Package"。索赔窗口永远是 **PO Date**。
8. **对账单滞后**：付款日到 8/25 的那份，UPS 发票日大约只到 7/28，盖不到 8 月发货——正常，标「尚未在来自Email」。
9. **订单 CSV（源 D）只核 PO Date / 单价**，不当索赔宇宙；没开票不索赔。
10. **给 Diane 一行一张 INV#**（多 SKU 先汇总）。
11. **`来自Email` 去重键 = 付款日 + PB INV#**（文件会跨账期重叠）。
12. **短收 / credit 不冲活动价差额**；未付请对方改应付。
13. **扫描截止 ≠ 冻结 PO**。冻结 = 改价后第一张合同价新 PO。未冻结清单不发给 Diane。
14. **已开票且已传输**：不要改金额、不要作废重开；进 true-up 另 reconciled。切分用 **invoiced vs not-invoiced**，不要用日历「through 8/31」（8/31 北京开票 batch 的 PO Date 只到 8/30）。
15. **Item master ≠ open PO cost**。Christine 改主档后，Diane 仍须改未开票 PO；看到合同价之前扣货。

## 6. 恢复后怎么做（第二步）

1. 抽下一张 SPS PO / 开票，确认 64.58 / 71.96 / 75.65 / 87.95。这张就是 **True-up 冻结 PO** 的候选。
2. 把内部表扫到最新 `invoice x*`（含 2026-08-27）。扫描可在冻结前反复做。
3. 按 `来自Email` 刷新已付/未付/占位号/双号（付款日+INV# 去重）。
4. 给 Diane 的清单：**一行一张、PB 用的 INV#**、PO#、PO Date、SKU、数量、已开单价、合同单价、差额。已付 vs 未付分开。冻结 PO 出现前不要发。
5. 请对方：已付 → debit/credit memo 或 AP 调整（最好带 INV# 清单给中国财务）；未付 → 下一张 remittance 前改应付，不要靠短收私下抹平。
6. Tracy 佣金按 true-up 后发票金额另表重算，**不抄 PB**。

## 7. 接手清单

- [x] Tracy Reply All 确认 Christine 的 Correct 列（2026-08-28）
- [x] Christine 确认 item master updated（2026-08-31）
- [ ] Diane 更新未开票 open PO 至合同批发
- [ ] 未开票 PO 上出现 64.58 / 71.96 / 75.65 / 87.95 后再发货
- [ ] 记录第一张合同价新 PO/发票 = **冻结 PO**
- [ ] 重跑内部 true-up（含 8/31 `invoice x34`）
- [ ] 可选：Reply All Diane（已开票 leave as billed / open PO update）；先微信 Tracy
- [ ] 冻结 PO 出现后，用户过目金额再发第二封给 Diane
- [ ] 不要把旧 evidence / $28k / 佣金发给 WSI

## 8. 本地文件与一次性脚本

xlsx/CSV **不入 git**。会话里的分析/填表是一次性 `uv run python`（openpyxl），草稿在 `.codex_tmp/`，**不要提交**。重跑按 [docs/reference/matching-rules.md](docs/reference/matching-rules.md)，不要把 CSV 拷进仓库。

| 本地文件（Promotion 目录） | 用途 |
|---------------------------|------|
| `PB_2025_promo_for_Diane_Christine.xlsx` | 给 Diane：28 SKU 改价表，Arial |
| `Christine download Centrade retail and costs 20260828_filled_for_Tracy.xlsx` | 给 Tracy：Correct wholesale；24 个三角枕 = 合同价，其余 = Current |
| `PB_2025_promo_trueup_internal.xlsx` | 内部逐票；约到 08-24，须含 8/31 `invoice x34` 后重跑 |
| `Email_ReplyAll_Diane_open_vs_invoiced.txt` | Diane 草稿：已开票 leave / open PO update（勿写 through 8/31） |
| `WeChat_to_Tracy_system_updated_EN.txt` | Tracy 微信草稿（佣金补差仅私下说） |
| `_archive_drafts\` | 旧 evidence / $28k / filled v1–v3 |

Christine 填表核对：Grey Twin Current 51.7 → Correct **64.58**；23.5" Correct 仍 **32.50**。Coffee 不在她的 37 行里。

## 9. 待深度研究（暂停；数据在仓库外）

下一阶要把 **PO Date ≥ 2025-12-03** 起的四套源对齐成可审计 true-up，边界案例尚未写进脚本：

| 源 | 路径 | 待研究 |
|----|------|--------|
| PO CSV | `PB orders\...\order*.csv` | 12/03 后每单 PO Date / 批发 / 零售；未开票 vs 已开票 |
| Invoice CSV | `...\invoice x*.csv` | 索赔宇宙；8/31 batch（PO Date 至 8/30） |
| 来自Email remittance | `payment advice\来自Email*.xlsx` | PB 付款号、双号、占位号、去重 |
| 给财务 Excel | `payment advice\给财务\*.xlsx` | Key 手工改 INV#、REMAP、短收等特殊行如何映射回 B |

目标：N 张开票 ↔ M 张 PB 认票，差数（滞后 / 双号 / 占位 / 排除 SKU / 手工调整）可追溯。与 `pb_reconciliation/reconcile_pb.py` 共用 REMAP 但 true-up 方向相反（付款号对外）。

**2026-09-01 实测**：`20260831\NotUsed\检查价格是否变化 没变化 0901 20260901_0121_645145.csv` — 6 PO，PO Date 8/31，5 张三角枕仍活动价；`invoice x34`（8/31 北京）21 张三角枕活动价。
