---
okf: v0.1
type: Log
title: pb_promo_trueup 变更日志
tags: [pb, promo, log]
timestamp: 2026-09-01
---

# 变更日志

## 2026-09-02
- **核实 Diane 邮件**：4 张 PO Change 接受后合同价；PO Date 9/1 新单已合同价（冻结点候选）；漏 3 张 8/31 open PO 待提醒；UPS-locked 21/22 = invoice x34。
- **状态**：扣货等 137803269 / 137804289 / 137804323。

## 2026-09-01
- **Christine 改主档**：2026-08-31 邮件 "The system has been updated"；@Diane update current orders。
- **实测**：open PO（PO Date 8/31）仍活动价；8/31 北京 `invoice x34` 21 张三角枕进 true-up；冻结 PO 未出现；扣货。
- **沟通**：Diane 草稿（已开票 leave / open PO update）；Tracy 微信（catch-up + commission 私下）。
- **待研究**：§9 四套源深度对齐（PO CSV / invoice / 来自Email / 给财务 Excel）。

## 2026-08-31
- **初始化** OKF bundle：匹配规则、沟通铁律、两步方案、经验教训、AGENT_HANDOFF。
- **锁定双侧对账**：订单 CSV 只核 PO Date；Diane 一行一张；`来自Email` 按付款日+INV# 去重；短收不冲差额；扫描截止 ≠ 冻结 PO。
